"""联合管道评测脚本：Embedding + Reranker 组合。

选取 top-2 Embedding × top-2 Reranker 的组合，评测端到端 MRR@3、延迟、显存。
两模型同时加载以验证生产部署可行性。

用法：
    conda run -n sca python scripts/eval_combined_pipeline.py \
        --eval-dataset eval/embedding/eval_dataset.jsonl \
        --fragments docs/knowledge_base/fragments/fragments.jsonl \
        --output eval/embedding/results/
"""

import argparse
import gc
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CombinedEvalResult:
    """联合管道评测结果。"""

    embedding_model: str
    reranker_model: str
    # 端到端指标
    e2e_mrr_at_3: float = 0.0
    e2e_hit_at_1: float = 0.0
    e2e_hit_at_3: float = 0.0
    # 延迟
    e2e_latency_ms: float = 0.0
    embed_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0
    # 显存
    combined_vram_mb: float = 0.0
    embedding_vram_mb: float = 0.0
    reranker_vram_mb: float = 0.0
    # 部署可行性
    deployable: bool = True
    note: str = ""


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """加载 JSONL 文件。"""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def release_gpu() -> None:
    """释放 GPU 显存。"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def get_top_models(results_dir: str) -> tuple[list[dict], list[dict]]:
    """从评测结果中获取 top-2 Embedding 和 top-2 Reranker。

    Args:
        results_dir: 评测结果目录

    Returns:
        (top2_embeddings, top2_rerankers)
    """
    # 读取 embedding 结果
    embedding_results = []
    for fname in os.listdir(results_dir):
        if fname.startswith("result_") and fname.endswith(".json"):
            with open(os.path.join(results_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            embedding_results.append(data)

    embedding_results.sort(key=lambda x: x.get("mrr_at_3", 0), reverse=True)
    top2_emb = embedding_results[:2]

    # 读取 reranker 结果
    reranker_results = []
    for fname in os.listdir(results_dir):
        if fname.startswith("reranker_") and fname.endswith(".json"):
            with open(os.path.join(results_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            reranker_results.append(data)

    reranker_results.sort(key=lambda x: x.get("rerank_mrr_at_3", 0), reverse=True)
    top2_rr = reranker_results[:2]

    return top2_emb, top2_rr


# ── 嵌入模型配置映射 ──

EMBEDDING_CONFIGS: dict[str, dict[str, Any]] = {
    "bge-m3": {
        "name": "BAAI/bge-m3",
        "st_kwargs": {},
        "encode_kwargs": {},
    },
    "bge-large-zh": {
        "name": "BAAI/bge-large-zh-v1.5",
        "st_kwargs": {},
        "encode_kwargs": {},
    },
    "qwen3-0.6b": {
        "name": "Qwen/Qwen3-Embedding-0.6B",
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
    "qwen3-4b": {
        "name": "Qwen/Qwen3-Embedding-4B",
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
    "qwen3-8b": {
        "name": "Qwen/Qwen3-Embedding-8B",
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
}

RERANKER_CONFIGS: dict[str, dict[str, Any]] = {
    "bge-reranker": {"name": "BAAI/bge-reranker-v2-m3", "use_fp16": True, "type": "cross_encoder"},
    "qwen3-reranker-0.6b": {"name": "Qwen/Qwen3-Reranker-0.6B", "use_fp16": True, "type": "qwen3_causal"},
    "qwen3-reranker-4b": {"name": "Qwen/Qwen3-Reranker-4B", "use_fp16": True, "type": "qwen3_causal"},
    "qwen3-reranker-8b": {"name": "Qwen/Qwen3-Reranker-8B", "use_fp16": True, "type": "qwen3_causal"},
}


# 复用 Qwen3Reranker，避免代码重复
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_reranker_models import Qwen3Reranker


def evaluate_combined(
    emb_short: str,
    rr_short: str,
    fragments: list[dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
) -> CombinedEvalResult:
    """评测一个 Embedding + Reranker 组合。

    同时加载两个模型，测量端到端指标。

    Args:
        emb_short: 嵌入模型 short name
        rr_short: Reranker short name
        fragments: 全量片段
        eval_dataset: 评测数据集

    Returns:
        联合评测结果
    """
    from sentence_transformers import SentenceTransformer

    emb_config = EMBEDDING_CONFIGS.get(emb_short)
    rr_config = RERANKER_CONFIGS.get(rr_short)

    if not emb_config or not rr_config:
        raise ValueError(f"未知模型: emb={emb_short}, rr={rr_short}")

    result = CombinedEvalResult(
        embedding_model=emb_config["name"],
        reranker_model=rr_config["name"],
    )

    print(f"\n{'='*60}")
    print(f"联合评测: {emb_short} + {rr_short}")
    print(f"{'='*60}")

    release_gpu()

    # ── 同时加载两个模型 ──
    print("  加载嵌入模型...")
    try:
        emb_model = SentenceTransformer(emb_config["name"], **emb_config.get("st_kwargs", {}))
    except Exception as e:
        result.deployable = False
        result.note = f"嵌入模型加载失败: {e}"
        print(f"  [ERROR] {result.note}")
        return result

    if torch.cuda.is_available():
        result.embedding_vram_mb = torch.cuda.memory_allocated() / 1024 / 1024

    print("  加载 Reranker...")
    try:
        rr_type = rr_config.get("type", "cross_encoder")
        if rr_type == "qwen3_causal":
            reranker = Qwen3Reranker(
                rr_config["name"],
                use_fp16=rr_config.get("use_fp16", True),
            )
        else:
            from sentence_transformers import CrossEncoder
            rr_model_kwargs = {}
            if rr_config.get("use_fp16"):
                rr_model_kwargs["torch_dtype"] = torch.float16
            reranker = CrossEncoder(rr_config["name"], model_kwargs=rr_model_kwargs)
    except Exception as e:
        result.deployable = False
        result.note = f"Reranker 加载失败: {e}"
        del emb_model
        release_gpu()
        print(f"  [ERROR] {result.note}")
        return result

    if torch.cuda.is_available():
        result.combined_vram_mb = torch.cuda.memory_allocated() / 1024 / 1024
        result.reranker_vram_mb = result.combined_vram_mb - result.embedding_vram_mb

    print(f"  组合显存: {result.combined_vram_mb:.0f} MB "
          f"(emb={result.embedding_vram_mb:.0f} + rr={result.reranker_vram_mb:.0f})")

    if result.combined_vram_mb > 23000:  # 23GB 安全阈值
        result.note = f"显存 {result.combined_vram_mb:.0f}MB 接近 24GB 上限"

    # ── 准备数据 ──
    passage_texts = [f.get("content", "") for f in fragments]
    passage_ids = [f["id"] for f in fragments]
    fragments_dict = {f["id"]: f for f in fragments}

    # ── 嵌入全量片段 ──
    # Qwen3 模型需要较小的 batch_size 以避免 OOM
    emb_batch_size = 2 if "qwen3" in emb_short else 32
    print(f"  嵌入全量片段 (batch_size={emb_batch_size})...")
    passage_embs = emb_model.encode(
        passage_texts,
        batch_size=emb_batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    passage_matrix = np.array(passage_embs)

    # ── 端到端评测 ──
    print(f"  端到端评测 {len(eval_dataset)} 组...")
    encode_kwargs = emb_config.get("encode_kwargs", {})

    mrr_3_sum = 0.0
    hit_1_sum = 0.0
    hit_3_sum = 0.0
    latencies = []
    n = 0

    for item in eval_dataset:
        query = item["query"]
        pos_id = item["positive_id"]

        t0 = time.time()

        # Step 1: 嵌入查询
        q_emb = emb_model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            **encode_kwargs,
        )[0]

        t_embed = time.time()

        # Step 2: 余弦相似度 top-10
        q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-10)
        p_norms = passage_matrix / (np.linalg.norm(passage_matrix, axis=1, keepdims=True) + 1e-10)
        sims = p_norms @ q_norm
        top10_indices = np.argsort(-sims)[:10]

        # Step 3: Rerank top-10
        pairs = []
        top10_ids = []
        for idx in top10_indices:
            frag = fragments_dict.get(passage_ids[idx])
            if frag and frag.get("content"):
                pairs.append([query, frag["content"]])
                top10_ids.append(passage_ids[idx])

        if pairs:
            scores = reranker.predict(pairs)
            if isinstance(scores, np.ndarray):
                scores = scores.tolist()
            ranked = sorted(zip(top10_ids, scores), key=lambda x: x[1], reverse=True)
        else:
            ranked = [(passage_ids[idx], float(sims[idx])) for idx in top10_indices]

        t_end = time.time()
        latencies.append((t_end - t0) * 1000)

        # 评估
        for rank, (doc_id, _) in enumerate(ranked[:3]):
            if doc_id == pos_id:
                mrr_3_sum += 1.0 / (rank + 1)
                if rank == 0:
                    hit_1_sum += 1.0
                hit_3_sum += 1.0
                break
        n += 1

    result.e2e_mrr_at_3 = mrr_3_sum / n if n > 0 else 0
    result.e2e_hit_at_1 = hit_1_sum / n if n > 0 else 0
    result.e2e_hit_at_3 = hit_3_sum / n if n > 0 else 0
    result.e2e_latency_ms = float(np.median(latencies)) if latencies else 0

    print(f"  E2E MRR@3={result.e2e_mrr_at_3:.4f} Hit@1={result.e2e_hit_at_1:.2%} "
          f"Hit@3={result.e2e_hit_at_3:.2%}")
    print(f"  E2E 延迟: {result.e2e_latency_ms:.1f} ms (median)")

    # 释放
    del emb_model, reranker
    release_gpu()

    return result


def generate_combined_report(
    results: list[CombinedEvalResult],
    embedding_results_dir: str,
    output_path: str,
) -> None:
    """生成综合评测报告（嵌入 + Reranker + 联合）。"""
    lines = [
        "# 嵌入模型 + Reranker 综合评测报告",
        "",
        f"> 评测时间: {time.strftime('%Y-%m-%d %H:%M')}",
        "> 数据集: 100 组 query-passage 对，692 条全量片段",
        "> 硬件: RTX 4090 (24GB), i9-13900K, 64GB RAM",
        "",
    ]

    # ── 嵌入模型排名（从已有结果读取）──
    emb_results = []
    for fname in os.listdir(embedding_results_dir):
        if fname.startswith("result_") and fname.endswith(".json"):
            with open(os.path.join(embedding_results_dir, fname), encoding="utf-8") as f:
                emb_results.append(json.load(f))
    emb_results.sort(key=lambda x: x.get("mrr_at_3", 0), reverse=True)

    if emb_results:
        lines.extend([
            "## 一、嵌入模型综合排名",
            "",
            "| # | 模型 | MRR@3 | Hit@1 | Hit@3 | Hit@10 | 区分度 | 延迟(ms) | batch(s) | 显存(MB) |",
            "|---|------|-------|-------|-------|--------|--------|---------|---------|---------|",
        ])
        for i, r in enumerate(emb_results, 1):
            lines.append(
                f"| {i} | {r.get('model_short', '?')} | {r.get('mrr_at_3', 0):.4f} | "
                f"{r.get('hit_at_1', 0):.2%} | {r.get('hit_at_3', 0):.2%} | "
                f"{r.get('hit_at_10', 0):.2%} | {r.get('avg_score_gap', 0):.4f} | "
                f"{r.get('single_embed_ms', 0):.1f} | {r.get('batch_embed_s', 0):.1f} | "
                f"{r.get('vram_peak_mb', 0):.0f} |"
            )

        # 长文本衰减
        lines.extend(["", "### 长文本衰减分析", ""])
        header = "| 片段长度 | " + " | ".join(r.get("model_short", "?") for r in emb_results) + " |"
        sep = "|---------|" + "|".join("-------" for _ in emb_results) + "|"
        lines.extend([header, sep])
        for lb in ["<512", "512-1024", ">1024"]:
            row = f"| {lb} MRR@3 |"
            for r in emb_results:
                val = r.get("mrr_by_length", {}).get(lb, 0)
                row += f" {val:.4f} |"
            lines.append(row)

    # ── Reranker 排名 ──
    rr_results = []
    for fname in os.listdir(embedding_results_dir):
        if fname.startswith("reranker_") and fname.endswith(".json"):
            with open(os.path.join(embedding_results_dir, fname), encoding="utf-8") as f:
                rr_results.append(json.load(f))
    rr_results.sort(key=lambda x: x.get("rerank_mrr_at_3", 0), reverse=True)

    if rr_results:
        lines.extend([
            "",
            "## 二、Reranker 综合排名",
            "",
            "| # | Reranker | Rerank MRR@3 | Hit@1 | Hit@3 | MRR增益 | 延迟(ms) | 显存(MB) |",
            "|---|---------|-------------|-------|-------|--------|---------|---------|",
        ])
        for i, r in enumerate(rr_results, 1):
            lines.append(
                f"| {i} | {r.get('model_short', '?')} | {r.get('rerank_mrr_at_3', 0):.4f} | "
                f"{r.get('rerank_hit_at_1', 0):.2%} | {r.get('rerank_hit_at_3', 0):.2%} | "
                f"{r.get('mrr_gain', 0):+.4f} | {r.get('single_rerank_ms', 0):.1f} | "
                f"{r.get('vram_peak_mb', 0):.0f} |"
            )

    # ── 联合管道 ──
    if results:
        lines.extend([
            "",
            "## 三、联合管道最优组合",
            "",
            "| # | 组合 | E2E MRR@3 | Hit@1 | Hit@3 | 延迟(ms) | 组合显存(MB) | 部署可行 |",
            "|---|------|-----------|-------|-------|---------|-------------|---------|",
        ])
        sorted_combined = sorted(results, key=lambda r: r.e2e_mrr_at_3, reverse=True)
        for i, r in enumerate(sorted_combined, 1):
            emb_short = r.embedding_model.split("/")[-1] if "/" in r.embedding_model else r.embedding_model
            rr_short = r.reranker_model.split("/")[-1] if "/" in r.reranker_model else r.reranker_model
            deploy = "✅" if r.deployable and r.combined_vram_mb < 23000 else "⚠️"
            lines.append(
                f"| {i} | {emb_short}+{rr_short} | {r.e2e_mrr_at_3:.4f} | "
                f"{r.e2e_hit_at_1:.2%} | {r.e2e_hit_at_3:.2%} | "
                f"{r.e2e_latency_ms:.1f} | {r.combined_vram_mb:.0f} | {deploy} |"
            )

    # ── 选型决策 ──
    if results:
        best = sorted_combined[0]
        emb_name = best.embedding_model.split("/")[-1]
        rr_name = best.reranker_model.split("/")[-1]

        # 找最优的可部署组合
        deployable = [r for r in sorted_combined if r.deployable and r.combined_vram_mb < 23000]
        best_deploy = deployable[0] if deployable else best

        lines.extend([
            "",
            "## 四、选型决策",
            "",
            f"**最高精度组合**: {emb_name} + {rr_name} "
            f"(E2E MRR@3={best.e2e_mrr_at_3:.4f}, 显存={best.combined_vram_mb:.0f}MB)",
            "",
        ])

        if best_deploy != best:
            bd_emb = best_deploy.embedding_model.split("/")[-1]
            bd_rr = best_deploy.reranker_model.split("/")[-1]
            lines.append(
                f"**推荐部署组合**: {bd_emb} + {bd_rr} "
                f"(E2E MRR@3={best_deploy.e2e_mrr_at_3:.4f}, 显存={best_deploy.combined_vram_mb:.0f}MB)"
            )
        else:
            lines.append("**推荐部署组合**: 同上（最高精度组合即可部署）")

    report = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n综合评测报告已保存: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="联合管道评测")
    parser.add_argument("--eval-dataset", default="eval/embedding/eval_dataset.jsonl")
    parser.add_argument("--fragments", default="docs/knowledge_base/fragments/fragments.jsonl")
    parser.add_argument("--output", default="eval/embedding/results/")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    eval_dataset = load_jsonl(args.eval_dataset)
    fragments = load_jsonl(args.fragments)

    # 获取 top-2 模型
    top2_emb, top2_rr = get_top_models(args.output)

    if not top2_emb:
        print("[ERROR] 未找到嵌入模型评测结果，请先运行 eval_embedding_models.py")
        sys.exit(1)
    if not top2_rr:
        print("[ERROR] 未找到 Reranker 评测结果，请先运行 eval_reranker_models.py")
        sys.exit(1)

    print(f"Top-2 嵌入: {[e.get('model_short') for e in top2_emb]}")
    print(f"Top-2 Reranker: {[r.get('model_short') for r in top2_rr]}")

    # 评测所有组合
    all_results: list[CombinedEvalResult] = []
    for emb in top2_emb:
        for rr in top2_rr:
            emb_short = emb.get("model_short", "")
            rr_short = rr.get("model_short", "")
            try:
                result = evaluate_combined(emb_short, rr_short, fragments, eval_dataset)
                all_results.append(result)

                fname = f"combined_{emb_short}_{rr_short}.json"
                with open(os.path.join(args.output, fname), "w") as f:
                    json.dump(asdict(result), f, ensure_ascii=False, indent=2)

            except Exception as e:
                print(f"\n[ERROR] 组合 {emb_short}+{rr_short} 评测失败: {e}")
                import traceback
                traceback.print_exc()

    # 生成综合报告
    if all_results:
        report_path = os.path.join(args.output, "eval_report.md")
        generate_combined_report(all_results, args.output, report_path)

    print(f"\n{'='*60}")
    print(f"联合评测完成: {len(all_results)} 个组合")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
