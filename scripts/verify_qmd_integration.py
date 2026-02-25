"""qmd 端到端集成验证脚本。

验证选定的 Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B 模型组合
与 qmd + sqlite-vec 的完整集成兼容性。

验证项：
  1. SentenceTransformerBackend 加载 Qwen3-Embedding-0.6B
  2. embed() / embed_batch() 返回正确维度（1024）向量
  3. sqlite-vec 存储和检索 1024 维向量
  4. 端到端流程：index → embed → search → 返回结果
  5. Qwen3-Reranker-0.6B CausalLM 加载 + 打分验证
  6. 双模型同时加载显存验证

用法：
    conda run -n sca python scripts/verify_qmd_integration.py
    conda run -n sca python scripts/verify_qmd_integration.py --fragments docs/knowledge_base/fragments/fragments.jsonl
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 默认配置（K20 评测选定组合）
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"
EXPECTED_DIM = 1024

# 施工方案领域测试数据
BUILTIN_DOCS = [
    {
        "collection": "ch06_methods",
        "id": "test_ch6_s01",
        "content": (
            "混凝土浇筑施工工艺：采用商品混凝土，强度等级C30，坍落度控制在160±20mm。"
            "浇筑前应对模板、钢筋进行隐蔽工程验收。浇筑时应分层浇筑，每层厚度不超过500mm，"
            "振捣棒插入下层50mm，振捣至混凝土表面不再下沉、无气泡冒出为止。"
        ),
    },
    {
        "collection": "ch06_methods",
        "id": "test_ch6_s02",
        "content": (
            "钢结构吊装施工方案：采用QY160汽车起重机进行构件吊装，吊装前应检查吊具、索具的"
            "完好性，确认起重机的稳定性。构件就位后立即进行临时固定，高强螺栓初拧扭矩应符合"
            "设计要求。所有吊装作业应在风速不超过六级时进行。"
        ),
    },
    {
        "collection": "ch07_quality",
        "id": "test_ch7_s01",
        "content": (
            "混凝土质量控制措施：每100m³取样一组标准养护试件，同条件养护试件与结构同条件放置。"
            "坍落度每车检测，偏差超过±30mm的退回。振捣质量由专人负责旁站监督。"
        ),
    },
    {
        "collection": "ch08_safety",
        "id": "test_ch8_s01",
        "content": (
            "高处作业安全措施：作业人员必须佩戴安全带，安全带应高挂低用。临边防护栏杆高度不低于"
            "1.2米，设置上下两道横杆和挡脚板。夜间施工应设置足够照明，照度不低于50lx。"
        ),
    },
]

BUILTIN_QUERIES = [
    ("混凝土浇筑的振捣要求是什么", "test_ch6_s01"),
    ("高处作业需要哪些安全防护措施", "test_ch8_s01"),
    ("钢结构吊装使用什么起重设备", "test_ch6_s02"),
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _get_vram_mb() -> float:
    """获取当前 GPU 显存占用（MB）。"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0.0


def _print_result(name: str, passed: bool, detail: str = "") -> None:
    """打印验证结果。"""
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f"  {status}  {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """加载 JSONL 文件。"""
    items: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# ---------------------------------------------------------------------------
# 验证步骤
# ---------------------------------------------------------------------------


def verify_embedding_load(model_name: str) -> tuple[bool, int]:
    """验证 1: SentenceTransformerBackend 加载嵌入模型。

    Args:
        model_name: HuggingFace 模型名称

    Returns:
        (通过/失败, 向量维度)
    """
    from qmd.llm.sentence_tf import SentenceTransformerBackend

    backend = SentenceTransformerBackend(model_name=model_name, device="cuda")
    dim = backend.get_embedding_dimensions()
    passed = dim == EXPECTED_DIM
    _print_result("Embedding 模型加载", passed, f"维度={dim}, 预期={EXPECTED_DIM}")
    return passed, dim


def verify_embed_ops(model_name: str) -> bool:
    """验证 2: embed() 和 embed_batch() 正确性。

    Args:
        model_name: HuggingFace 模型名称

    Returns:
        通过/失败
    """
    from qmd.llm.sentence_tf import SentenceTransformerBackend

    backend = SentenceTransformerBackend(model_name=model_name, device="cuda")

    # 单条嵌入
    result_single = backend.embed("混凝土浇筑施工工艺要求", is_query=True)
    if result_single is None:
        _print_result("embed() 单条", False, "返回 None")
        return False

    dim = len(result_single.embedding)
    single_ok = dim == EXPECTED_DIM and result_single.model == model_name
    _print_result("embed() 单条", single_ok, f"维度={dim}, model={result_single.model}")

    # 批量嵌入
    texts = [d["content"] for d in BUILTIN_DOCS]
    results_batch = backend.embed_batch(texts)
    batch_ok = (
        len(results_batch) == len(texts)
        and all(r is not None for r in results_batch)
        and all(len(r.embedding) == EXPECTED_DIM for r in results_batch if r is not None)
    )
    _print_result("embed_batch() 批量", batch_ok, f"{len(results_batch)} 条, 维度均为 {EXPECTED_DIM}")

    return single_ok and batch_ok


def verify_sqlite_vec(model_name: str) -> bool:
    """验证 3: sqlite-vec 存储 + 检索 + qmd search 端到端。

    Args:
        model_name: 嵌入模型名称

    Returns:
        通过/失败
    """
    import qmd
    from qmd.llm.sentence_tf import SentenceTransformerBackend

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        db, store = qmd.create_store(str(db_path))

        # 索引文档
        for doc in BUILTIN_DOCS:
            store.index_document(doc["collection"], doc["id"], doc["content"])
        doc_count = store.get_document_count("ch06_methods")

        # 嵌入
        backend = SentenceTransformerBackend(model_name=model_name, device="cuda")
        store.embed_documents(backend, force=False, batch_size=2)

        # 检索（需传入 llm_backend 以启用向量检索）
        results = qmd.search(
            db, "混凝土浇筑振捣要求", collection="ch06_methods", limit=3, llm_backend=backend
        )

        passed = doc_count > 0 and len(results) > 0
        top_body = results[0].body[:50] if results and results[0].body else "N/A"
        _print_result(
            "sqlite-vec 存储+检索",
            passed,
            f"索引 {doc_count} 条, 检索 {len(results)} 条, top1={top_body}...",
        )
        return passed


def verify_e2e_accuracy(model_name: str) -> bool:
    """验证 4: 端到端检索准确性（内置测试用例）。

    Args:
        model_name: 嵌入模型名称

    Returns:
        通过/失败
    """
    import qmd
    from qmd.llm.sentence_tf import SentenceTransformerBackend

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_e2e.db"
        db, store = qmd.create_store(str(db_path))

        for doc in BUILTIN_DOCS:
            store.index_document(doc["collection"], doc["id"], doc["content"])

        backend = SentenceTransformerBackend(model_name=model_name, device="cuda")
        store.embed_documents(backend, force=False, batch_size=2)

        correct = 0
        for query, expected_id in BUILTIN_QUERIES:
            results = qmd.search(db, query, limit=3, llm_backend=backend)
            top_bodies = [r.body for r in results[:3] if r.body]
            # 查找预期文档内容的关键前缀
            expected_content = next(d["content"][:30] for d in BUILTIN_DOCS if d["id"] == expected_id)
            found = any(expected_content[:20] in b for b in top_bodies)
            if found:
                correct += 1

        accuracy = correct / len(BUILTIN_QUERIES)
        passed = accuracy >= 0.66
        _print_result(
            "端到端检索准确性",
            passed,
            f"{correct}/{len(BUILTIN_QUERIES)} 正确 ({accuracy:.0%})",
        )
        return passed


def verify_reranker_causal(model_name: str) -> bool:
    """验证 5: Qwen3-Reranker CausalLM 模型加载 + yes/no 打分。

    Qwen3-Reranker 使用 CausalLM 架构（非 CrossEncoder），
    通过 yes/no token 的 log_softmax 概率作为相关性分数。

    Args:
        model_name: Reranker 模型名称

    Returns:
        通过/失败
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(
        model_name, torch_dtype=torch.float16
    ).cuda().eval()

    # 验证 yes/no token 存在
    yes_id = tokenizer.convert_tokens_to_ids("yes")
    no_id = tokenizer.convert_tokens_to_ids("no")
    vocab_ok = yes_id != tokenizer.unk_token_id and no_id != tokenizer.unk_token_id
    _print_result("Reranker yes/no token", vocab_ok, f"yes={yes_id}, no={no_id}")

    if not vocab_ok:
        del model
        torch.cuda.empty_cache()
        return False

    # 测试打分
    instruction = "给定一个施工方案相关的检索查询，判断文档是否与查询相关"
    query = "混凝土浇筑的振捣要求"
    doc_pos = BUILTIN_DOCS[0]["content"]  # 混凝土浇筑 → 相关
    doc_neg = BUILTIN_DOCS[3]["content"]  # 高处作业安全 → 不相关

    prefix = "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    scores: list[float] = []
    for doc in [doc_pos, doc_neg]:
        content = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
        text = prefix + content + suffix
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=4096).to("cuda")
        with torch.no_grad():
            logits = model(**inputs).logits[:, -1, :]
        true_score = logits[:, yes_id]
        false_score = logits[:, no_id]
        stacked = torch.stack([false_score, true_score], dim=1)
        probs = torch.nn.functional.log_softmax(stacked, dim=1)
        score = probs[:, 1].exp().item()
        scores.append(score)

    score_ok = scores[0] > scores[1]  # 相关文档分数应高于不相关
    _print_result(
        "Reranker CausalLM 打分",
        score_ok,
        f"相关={scores[0]:.4f} > 不相关={scores[1]:.4f}",
    )

    del model
    torch.cuda.empty_cache()

    print("  ⚠️  注意: qmd 当前 rerank() 使用余弦相似度，需实现 Qwen3CausalLMBackend 以集成")
    return vocab_ok and score_ok


def verify_vram_budget(embedding_model: str, reranker_model: str) -> bool:
    """验证 6: 双模型同时加载的显存预算（需 < 24GB）。

    Args:
        embedding_model: 嵌入模型名称
        reranker_model: Reranker 模型名称

    Returns:
        通过/失败
    """
    from qmd.llm.sentence_tf import SentenceTransformerBackend
    from transformers import AutoModelForCausalLM, AutoTokenizer

    vram_before = _get_vram_mb()

    # 加载 Embedding
    backend = SentenceTransformerBackend(model_name=embedding_model, device="cuda")
    _ = backend.embed("test", is_query=True)
    vram_after_emb = _get_vram_mb()
    emb_vram = vram_after_emb - vram_before

    # 加载 Reranker
    tokenizer = AutoTokenizer.from_pretrained(reranker_model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(
        reranker_model, torch_dtype=torch.float16
    ).cuda().eval()
    vram_after_both = _get_vram_mb()
    rr_vram = vram_after_both - vram_after_emb
    total = vram_after_both - vram_before

    del model, tokenizer
    torch.cuda.empty_cache()

    passed = total < 24000
    _print_result(
        "显存预算 (<24GB)",
        passed,
        f"Embedding={emb_vram:.0f}MB + Reranker={rr_vram:.0f}MB = {total:.0f}MB",
    )
    return passed


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> None:
    """运行所有验证项。"""
    parser = argparse.ArgumentParser(description="K20 qmd 集成验证")
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"嵌入模型 (默认: {DEFAULT_EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--reranker-model",
        default=DEFAULT_RERANKER_MODEL,
        help=f"Reranker 模型 (默认: {DEFAULT_RERANKER_MODEL})",
    )
    parser.add_argument(
        "--fragments",
        default=None,
        help="可选: 外部 JSONL 片段文件路径（不提供则用内置测试数据）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("K20 qmd 集成验证")
    print(f"  嵌入模型: {args.embedding_model}")
    print(f"  Reranker: {args.reranker_model}")
    print(f"  预期维度: {EXPECTED_DIM}")
    print("=" * 60)

    steps: list[tuple[str, Any]] = [
        ("1. Embedding 模型加载", lambda: verify_embedding_load(args.embedding_model)[0]),
        ("2. embed()/embed_batch()", lambda: verify_embed_ops(args.embedding_model)),
        ("3. sqlite-vec 存储+检索", lambda: verify_sqlite_vec(args.embedding_model)),
        ("4. 端到端检索准确性", lambda: verify_e2e_accuracy(args.embedding_model)),
        ("5. Reranker CausalLM", lambda: verify_reranker_causal(args.reranker_model)),
        (
            "6. 显存预算",
            lambda: verify_vram_budget(args.embedding_model, args.reranker_model),
        ),
    ]

    results: list[tuple[str, bool]] = []
    for name, func in steps:
        print(f"\n[{name}]")
        try:
            passed = func()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ FAIL  异常: {e}")
            results.append((name, False))

    # 汇总
    print("\n" + "=" * 60)
    print("验证汇总")
    print("=" * 60)
    passed_count = sum(1 for _, p in results if p)
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
    print(f"\n  结果: {passed_count}/{len(results)} 通过")

    if passed_count == len(results):
        print("\n  🎉 所有验证通过！模型组合可集成到 qmd。")
    else:
        print("\n  ⚠️  部分验证未通过，请检查失败项。")
        sys.exit(1)


if __name__ == "__main__":
    main()
