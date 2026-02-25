"""Reranker 模型评测脚本。

基于嵌入模型 top-10 召回结果，对候选 Reranker 逐个评测：
重排 top-10 → 计算 MRR/Hit@k → 测速+显存。

用法：
    conda run -n sca python scripts/eval_reranker_models.py \
        --eval-dataset eval/embedding/eval_dataset.jsonl \
        --embedding-results eval/embedding/results/ \
        --fragments docs/knowledge_base/fragments/fragments.jsonl \
        --output eval/embedding/results/
"""

import argparse
import gc
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 候选 Reranker 配置 ────────────────────────────────────────────────────

RERANKER_CANDIDATES: list[dict[str, Any]] = [
    {
        "name": "BAAI/bge-reranker-v2-m3",
        "short": "bge-reranker",
        "max_seq_length": 8192,
        "use_fp16": True,
        "type": "cross_encoder",
    },
    {
        "name": "Qwen/Qwen3-Reranker-0.6B",
        "short": "qwen3-reranker-0.6b",
        "max_seq_length": 8192,
        "use_fp16": True,
        "type": "qwen3_causal",
    },
    {
        "name": "Qwen/Qwen3-Reranker-4B",
        "short": "qwen3-reranker-4b",
        "max_seq_length": 8192,
        "use_fp16": True,
        "type": "qwen3_causal",
    },
    {
        "name": "Qwen/Qwen3-Reranker-8B",
        "short": "qwen3-reranker-8b",
        "max_seq_length": 8192,
        "use_fp16": True,
        "type": "qwen3_causal",
    },
]


class Qwen3Reranker:
    """Qwen3 CausalLM 重排序器封装。

    Qwen3 Reranker 基于 CausalLM 架构，通过判断 yes/no 概率来打分。
    """

    def __init__(self, model_name: str, use_fp16: bool = True, max_length: int = 8192):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dtype = torch.float16 if use_fp16 else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, padding_side="left",
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=dtype,
        ).cuda().eval()

        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.max_length = max_length

        self.prefix = (
            "<|im_start|>system\n"
            "Judge whether the Document meets the requirements based on the "
            "Query and the Instruct provided. Note that the answer can only "
            'be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        )
        self.suffix = (
            "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )
        self.prefix_tokens = self.tokenizer.encode(self.prefix, add_special_tokens=False)
        self.suffix_tokens = self.tokenizer.encode(self.suffix, add_special_tokens=False)

    def _format_pair(self, query: str, document: str) -> str:
        """格式化 query-document 对。"""
        instruction = "给定一个施工方案相关的检索查询，判断文档是否与查询相关"
        return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"

    @torch.no_grad()
    def _score_single(self, query: str, document: str) -> float:
        """对单个 query-document 对打分。"""
        text = self._format_pair(query, document)
        max_text_len = self.max_length - len(self.prefix_tokens) - len(self.suffix_tokens)
        encoded = self.tokenizer(
            text,
            padding=False,
            truncation=True,
            return_attention_mask=False,
            max_length=max_text_len,
        )
        input_ids = self.prefix_tokens + encoded["input_ids"] + self.suffix_tokens
        inputs = self.tokenizer.pad(
            {"input_ids": [input_ids]},
            padding=True,
            return_tensors="pt",
        )
        for key in inputs:
            inputs[key] = inputs[key].to(self.model.device)

        logits = self.model(**inputs).logits[:, -1, :]
        true_score = logits[:, self.token_true_id]
        false_score = logits[:, self.token_false_id]
        stacked = torch.stack([false_score, true_score], dim=1)
        probs = torch.nn.functional.log_softmax(stacked, dim=1)
        return probs[:, 1].exp().item()

    def predict(self, pairs: list[list[str]]) -> list[float]:
        """对 query-document 对逐个打分。

        Args:
            pairs: [[query, document], ...] 格式

        Returns:
            分数列表（0-1 之间的概率）
        """
        return [self._score_single(q, d) for q, d in pairs]


@dataclass
class RerankerEvalResult:
    """单个 Reranker 的评测结果。"""

    model_name: str
    model_short: str
    embedding_source: str = ""
    # 检索指标
    rerank_mrr_at_1: float = 0.0
    rerank_mrr_at_3: float = 0.0
    rerank_hit_at_1: float = 0.0
    rerank_hit_at_3: float = 0.0
    # MRR 增益（相比 embedding only）
    mrr_gain: float = 0.0
    # 按章节
    mrr_by_chapter: dict[str, float] = field(default_factory=dict)
    # 按长度
    mrr_by_length: dict[str, float] = field(default_factory=dict)
    # 性能
    single_rerank_ms: float = 0.0
    vram_peak_mb: float = 0.0


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """加载 JSONL 文件。"""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def get_gpu_memory_mb() -> float:
    """获取当前 GPU 显存使用量（MB）。"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0.0


def release_gpu() -> None:
    """释放 GPU 显存。"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def find_best_embedding_top10(results_dir: str) -> tuple[str, str]:
    """找到 MRR@3 最高的嵌入模型及其 top-10 结果文件。

    Args:
        results_dir: 评测结果目录

    Returns:
        (top10 文件路径, 模型 short name)
    """
    best_mrr = -1.0
    best_short = ""
    best_path = ""

    for fname in os.listdir(results_dir):
        if fname.startswith("result_") and fname.endswith(".json"):
            fpath = os.path.join(results_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            mrr3 = data.get("mrr_at_3", 0)
            short = data.get("model_short", "")
            if mrr3 > best_mrr:
                best_mrr = mrr3
                best_short = short
                best_path = os.path.join(results_dir, f"top10_{short}.jsonl")

    if not best_path or not os.path.exists(best_path):
        raise FileNotFoundError(
            f"找不到最优嵌入模型的 top-10 结果。best_short={best_short}, "
            f"expected={best_path}"
        )

    print(f"最优嵌入模型: {best_short} (MRR@3={best_mrr:.4f})")
    return best_path, best_short


def rerank_with_model(
    reranker: Any,
    query: str,
    candidates: list[dict[str, Any]],
    fragments_dict: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """使用 reranker 模型对候选重排序。

    支持 CrossEncoder 和 Qwen3Reranker 两种模型类型。

    Args:
        reranker: CrossEncoder 或 Qwen3Reranker 模型实例
        query: 查询文本
        candidates: top-10 候选列表 [{id, score}, ...]
        fragments_dict: {fragment_id: fragment_dict}

    Returns:
        重排序后的候选列表（含 rerank_score）
    """
    pairs = []
    valid_candidates = []
    for cand in candidates:
        frag = fragments_dict.get(cand["id"])
        if frag and frag.get("content"):
            pairs.append([query, frag["content"]])
            valid_candidates.append(cand)

    if not pairs:
        return candidates

    scores = reranker.predict(pairs)
    if isinstance(scores, np.ndarray):
        scores = scores.tolist()

    for cand, score in zip(valid_candidates, scores):
        cand["rerank_score"] = float(score)

    reranked = sorted(valid_candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
    return reranked


def compute_rerank_metrics(
    reranked_results: list[dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
    embedding_mrr3: float,
) -> dict[str, float]:
    """计算 Reranker 评测指标。

    Args:
        reranked_results: [{query_id, reranked: [{id, rerank_score}]}]
        eval_dataset: 评测数据集
        embedding_mrr3: 嵌入模型的 MRR@3（用于计算增益）

    Returns:
        指标字典
    """
    dataset_map = {item["query_id"]: item for item in eval_dataset}

    mrr_1_sum = 0.0
    mrr_3_sum = 0.0
    hit_1_sum = 0.0
    hit_3_sum = 0.0
    n = 0

    for result in reranked_results:
        qid = result["query_id"]
        item = dataset_map.get(qid)
        if not item:
            continue

        pos_id = item["positive_id"]
        reranked = result.get("reranked", [])

        pos_rank = -1
        for rank, cand in enumerate(reranked):
            if cand["id"] == pos_id:
                pos_rank = rank + 1
                break

        if pos_rank == -1:
            n += 1
            continue

        if pos_rank <= 1:
            mrr_1_sum += 1.0 / pos_rank
        if pos_rank <= 3:
            mrr_3_sum += 1.0 / pos_rank
        if pos_rank <= 1:
            hit_1_sum += 1.0
        if pos_rank <= 3:
            hit_3_sum += 1.0
        n += 1

    return {
        "rerank_mrr_at_1": mrr_1_sum / n if n > 0 else 0,
        "rerank_mrr_at_3": mrr_3_sum / n if n > 0 else 0,
        "rerank_hit_at_1": hit_1_sum / n if n > 0 else 0,
        "rerank_hit_at_3": hit_3_sum / n if n > 0 else 0,
        "mrr_gain": (mrr_3_sum / n - embedding_mrr3) if n > 0 else 0,
    }


def compute_rerank_by_chapter(
    reranked_results: list[dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
) -> dict[str, float]:
    """按章节计算 Rerank MRR@3。"""
    from collections import defaultdict

    dataset_map = {item["query_id"]: item for item in eval_dataset}
    chapter_data: dict[str, list[float]] = defaultdict(list)

    for result in reranked_results:
        qid = result["query_id"]
        item = dataset_map.get(qid)
        if not item:
            continue

        chapter = item.get("positive_chapter", "")[:6] or "未知"
        pos_id = item["positive_id"]
        reranked = result.get("reranked", [])

        rr = 0.0
        for rank, cand in enumerate(reranked[:3]):
            if cand["id"] == pos_id:
                rr = 1.0 / (rank + 1)
                break
        chapter_data[chapter].append(rr)

    return {ch: float(np.mean(vals)) for ch, vals in chapter_data.items()}


def compute_rerank_by_length(
    reranked_results: list[dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
) -> dict[str, float]:
    """按片段长度分层计算 Rerank MRR@3。"""
    dataset_map = {item["query_id"]: item for item in eval_dataset}
    length_bins = [
        ("<512", lambda x: x <= 512),
        ("512-1024", lambda x: 512 < x <= 1024),
        (">1024", lambda x: x > 1024),
    ]

    results: dict[str, float] = {}
    for bin_name, bin_fn in length_bins:
        rr_values = []
        for result in reranked_results:
            qid = result["query_id"]
            item = dataset_map.get(qid)
            if not item or not bin_fn(item.get("positive_char_count", 0)):
                continue

            pos_id = item["positive_id"]
            reranked = result.get("reranked", [])
            rr = 0.0
            for rank, cand in enumerate(reranked[:3]):
                if cand["id"] == pos_id:
                    rr = 1.0 / (rank + 1)
                    break
            rr_values.append(rr)

        results[bin_name] = float(np.mean(rr_values)) if rr_values else 0.0

    return results


def evaluate_reranker(
    reranker_config: dict[str, Any],
    top10_data: list[dict[str, Any]],
    fragments_dict: dict[str, dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
    embedding_mrr3: float,
    embedding_source: str,
) -> RerankerEvalResult:
    """评测单个 Reranker 模型。

    Args:
        reranker_config: Reranker 配置
        top10_data: 嵌入模型 top-10 召回结果
        fragments_dict: {fragment_id: fragment}
        eval_dataset: 评测数据集
        embedding_mrr3: 嵌入模型 MRR@3
        embedding_source: 嵌入模型名称

    Returns:
        评测结果
    """
    model_name = reranker_config["name"]
    model_short = reranker_config["short"]
    print(f"\n{'='*60}")
    print(f"评测 Reranker: {model_name}")
    print(f"{'='*60}")

    result = RerankerEvalResult(
        model_name=model_name,
        model_short=model_short,
        embedding_source=embedding_source,
    )

    release_gpu()
    vram_before = get_gpu_memory_mb()

    # 加载模型
    print("  加载 Reranker...")
    t0 = time.time()

    reranker_type = reranker_config.get("type", "cross_encoder")
    if reranker_type == "qwen3_causal":
        reranker = Qwen3Reranker(
            model_name,
            use_fp16=reranker_config.get("use_fp16", True),
            max_length=reranker_config.get("max_seq_length", 8192),
        )
    else:
        from sentence_transformers import CrossEncoder
        model_kwargs = {}
        if reranker_config.get("use_fp16") and torch.cuda.is_available():
            model_kwargs["torch_dtype"] = torch.float16
        reranker = CrossEncoder(model_name, model_kwargs=model_kwargs)

    load_time = time.time() - t0
    print(f"  加载耗时: {load_time:.1f}s")

    vram_after = get_gpu_memory_mb()
    result.vram_peak_mb = vram_after - vram_before
    print(f"  显存占用: {result.vram_peak_mb:.0f} MB")

    # ── 对每个 query 的 top-10 重排 ──
    print(f"  重排 {len(top10_data)} 组查询的 top-10...")
    reranked_results = []

    for i, top10_item in enumerate(top10_data):
        query = top10_item["query"]
        candidates = top10_item["top10"]

        reranked = rerank_with_model(reranker, query, candidates, fragments_dict)
        reranked_results.append({
            "query_id": top10_item["query_id"],
            "reranked": reranked,
        })

        if (i + 1) % 20 == 0:
            print(f"    [{i+1}/{len(top10_data)}] 完成")

    # ── 单 query 重排延迟 ──
    if top10_data:
        sample = top10_data[0]
        sample_candidates = sample["top10"]
        times = []
        for _ in range(10):
            t0 = time.time()
            rerank_with_model(reranker, sample["query"], sample_candidates, fragments_dict)
            times.append((time.time() - t0) * 1000)
        result.single_rerank_ms = float(np.median(times))
        print(f"  单 query 重排延迟: {result.single_rerank_ms:.1f} ms (median of 10)")

    # ── 计算指标 ──
    print("  计算 Rerank 指标...")
    metrics = compute_rerank_metrics(reranked_results, eval_dataset, embedding_mrr3)
    result.rerank_mrr_at_1 = metrics["rerank_mrr_at_1"]
    result.rerank_mrr_at_3 = metrics["rerank_mrr_at_3"]
    result.rerank_hit_at_1 = metrics["rerank_hit_at_1"]
    result.rerank_hit_at_3 = metrics["rerank_hit_at_3"]
    result.mrr_gain = metrics["mrr_gain"]

    print(f"  Rerank MRR@1={result.rerank_mrr_at_1:.4f} MRR@3={result.rerank_mrr_at_3:.4f}")
    print(f"  Rerank Hit@1={result.rerank_hit_at_1:.2%} Hit@3={result.rerank_hit_at_3:.2%}")
    print(f"  MRR 增益: {result.mrr_gain:+.4f}")

    # 按章节
    result.mrr_by_chapter = compute_rerank_by_chapter(reranked_results, eval_dataset)
    print("  按章节 Rerank MRR@3:")
    for ch, mrr in sorted(result.mrr_by_chapter.items()):
        print(f"    {ch}: {mrr:.4f}")

    # 按长度
    result.mrr_by_length = compute_rerank_by_length(reranked_results, eval_dataset)
    print("  按长度 Rerank MRR@3:")
    for length_bin, mrr in result.mrr_by_length.items():
        print(f"    {length_bin}: {mrr:.4f}")

    # 更新显存峰值
    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / 1024 / 1024
        result.vram_peak_mb = max(result.vram_peak_mb, peak - vram_before)

    # 释放模型
    del reranker
    release_gpu()

    return result


def generate_reranker_report(
    results: list[RerankerEvalResult],
    output_path: str,
) -> None:
    """生成 Reranker 评测报告。"""
    lines = [
        "# Reranker 模型评测报告",
        "",
        f"> 评测时间: {time.strftime('%Y-%m-%d %H:%M')}",
        f"> 基于嵌入模型 {results[0].embedding_source if results else '?'} 的 top-10 召回",
        f"> 硬件: RTX 4090 (24GB), i9-13900K, 64GB RAM",
        "",
        "## 综合排名",
        "",
        "| # | Reranker | Rerank MRR@3 | Hit@1 | Hit@3 | MRR增益 | 延迟(ms) | 显存(MB) |",
        "|---|---------|-------------|-------|-------|--------|---------|---------|",
    ]

    sorted_results = sorted(results, key=lambda r: r.rerank_mrr_at_3, reverse=True)
    for i, r in enumerate(sorted_results, 1):
        lines.append(
            f"| {i} | {r.model_short} | {r.rerank_mrr_at_3:.4f} | "
            f"{r.rerank_hit_at_1:.2%} | {r.rerank_hit_at_3:.2%} | "
            f"{r.mrr_gain:+.4f} | {r.single_rerank_ms:.1f} | {r.vram_peak_mb:.0f} |"
        )

    # 长文本分析
    lines.extend([
        "",
        "## 按长度 Rerank MRR@3",
        "",
        "| 片段长度 | " + " | ".join(r.model_short for r in sorted_results) + " |",
        "|---------|" + "|".join("-------" for _ in sorted_results) + "|",
    ])
    for length_bin in ["<512", "512-1024", ">1024"]:
        row = f"| {length_bin} |"
        for r in sorted_results:
            val = r.mrr_by_length.get(length_bin, 0)
            row += f" {val:.4f} |"
        lines.append(row)

    # 按章节
    lines.extend(["", "## 按章节 Rerank MRR@3", ""])
    all_chapters = sorted(set(ch for r in results for ch in r.mrr_by_chapter))
    header = "| 章节 | " + " | ".join(r.model_short for r in sorted_results) + " |"
    sep = "|------|" + "|".join("------" for _ in sorted_results) + "|"
    lines.extend([header, sep])
    for ch in all_chapters:
        row = f"| {ch} |"
        for r in sorted_results:
            val = r.mrr_by_chapter.get(ch, 0)
            row += f" {val:.4f} |"
        lines.append(row)

    report = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReranker 评测报告已保存: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reranker 模型评测")
    parser.add_argument("--eval-dataset", default="eval/embedding/eval_dataset.jsonl")
    parser.add_argument("--embedding-results", default="eval/embedding/results/")
    parser.add_argument("--fragments", default="docs/knowledge_base/fragments/fragments.jsonl")
    parser.add_argument("--output", default="eval/embedding/results/")
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="指定要评测的 Reranker short name，默认全部",
    )
    parser.add_argument(
        "--embedding-top10",
        default=None,
        help="指定嵌入模型的 top-10 文件路径（默认自动选择最优）",
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 加载数据
    print("加载评测数据集...")
    eval_dataset = load_jsonl(args.eval_dataset)
    print(f"  评测组数: {len(eval_dataset)}")

    print("加载知识片段...")
    fragments = load_jsonl(args.fragments)
    fragments_dict = {f["id"]: f for f in fragments}
    print(f"  片段数: {len(fragments)}")

    # 获取嵌入模型 top-10 结果
    if args.embedding_top10:
        top10_path = args.embedding_top10
        embedding_source = os.path.basename(top10_path).replace("top10_", "").replace(".jsonl", "")
    else:
        top10_path, embedding_source = find_best_embedding_top10(args.embedding_results)
    print(f"使用嵌入 top-10: {top10_path}")

    top10_data = load_jsonl(top10_path)
    print(f"  top-10 组数: {len(top10_data)}")

    # 获取嵌入模型 MRR@3（用于计算增益）
    emb_result_path = os.path.join(args.embedding_results, f"result_{embedding_source}.json")
    embedding_mrr3 = 0.0
    if os.path.exists(emb_result_path):
        with open(emb_result_path, encoding="utf-8") as f:
            emb_data = json.load(f)
        embedding_mrr3 = emb_data.get("mrr_at_3", 0)
    print(f"嵌入模型 MRR@3: {embedding_mrr3:.4f}")

    # 筛选候选
    candidates = RERANKER_CANDIDATES
    if args.models:
        candidates = [c for c in candidates if c["short"] in args.models]
    print(f"候选 Reranker: {[c['short'] for c in candidates]}")

    # 逐个评测
    all_results: list[RerankerEvalResult] = []
    for config in candidates:
        try:
            result = evaluate_reranker(
                config, top10_data, fragments_dict, eval_dataset,
                embedding_mrr3, embedding_source,
            )
            all_results.append(result)

            with open(os.path.join(args.output, f"reranker_{config['short']}.json"), "w") as f:
                json.dump(asdict(result), f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"\n[ERROR] Reranker {config['name']} 评测失败: {e}")
            import traceback
            traceback.print_exc()

    # 生成报告
    if all_results:
        report_path = os.path.join(args.output, "reranker_report.md")
        generate_reranker_report(all_results, report_path)

    print(f"\n{'='*60}")
    print(f"Reranker 评测完成: {len(all_results)}/{len(candidates)} 个模型")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
