"""嵌入模型评测脚本。

对候选嵌入模型逐个评测：嵌入全量片段 + 查询，计算 MRR/Hit@k，
按章节和文本长度分层分析，测速+显存。

用法：
    conda run -n sca python scripts/eval_embedding_models.py \
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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 候选模型配置 ──────────────────────────────────────────────────────────

EMBEDDING_CANDIDATES: list[dict[str, Any]] = [
    {
        "name": "BAAI/bge-m3",
        "short": "bge-m3",
        "max_seq_length": 8192,
        "batch_size": 32,
        "st_kwargs": {},
        "encode_kwargs": {},
    },
    {
        "name": "BAAI/bge-large-zh-v1.5",
        "short": "bge-large-zh",
        "max_seq_length": 512,
        "batch_size": 32,
        "st_kwargs": {},
        "encode_kwargs": {},
    },
    {
        "name": "Qwen/Qwen3-Embedding-0.6B",
        "short": "qwen3-0.6b",
        "max_seq_length": 32768,
        "batch_size": 2,
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
    {
        "name": "Qwen/Qwen3-Embedding-4B",
        "short": "qwen3-4b",
        "max_seq_length": 32768,
        "batch_size": 1,
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
    {
        "name": "Qwen/Qwen3-Embedding-8B",
        "short": "qwen3-8b",
        "max_seq_length": 32768,
        "batch_size": 1,
        "st_kwargs": {
            "model_kwargs": {"torch_dtype": torch.float16},
            "tokenizer_kwargs": {"padding_side": "left"},
        },
        "encode_kwargs": {"prompt_name": "query"},
    },
]


@dataclass
class EvalResult:
    """单个模型的评测结果。"""
    model_name: str
    model_short: str
    embedding_dim: int = 0
    # 检索指标
    mrr_at_1: float = 0.0
    mrr_at_3: float = 0.0
    hit_at_1: float = 0.0
    hit_at_3: float = 0.0
    hit_at_10: float = 0.0
    # 按章节细粒度
    mrr_by_chapter: dict[str, float] = field(default_factory=dict)
    # 按文本长度分层
    mrr_by_length: dict[str, float] = field(default_factory=dict)
    hit3_by_length: dict[str, float] = field(default_factory=dict)
    # 性能
    single_embed_ms: float = 0.0
    batch_embed_s: float = 0.0
    vram_peak_mb: float = 0.0
    # hard negative 区分度
    avg_score_gap: float = 0.0


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


def compute_cosine_similarity(
    query_emb: np.ndarray,
    passage_embs: np.ndarray,
) -> np.ndarray:
    """计算 query 与多个 passage 的余弦相似度。

    Args:
        query_emb: (D,) 查询向量
        passage_embs: (N, D) 文档向量矩阵

    Returns:
        (N,) 相似度数组
    """
    q_norm = query_emb / (np.linalg.norm(query_emb) + 1e-10)
    p_norms = passage_embs / (np.linalg.norm(passage_embs, axis=1, keepdims=True) + 1e-10)
    return p_norms @ q_norm


def compute_retrieval_metrics(
    query_embeddings: dict[str, np.ndarray],
    passage_embeddings: dict[str, np.ndarray],
    eval_dataset: list[dict[str, Any]],
    all_passage_ids: list[str],
    all_passage_matrix: np.ndarray,
) -> dict[str, Any]:
    """计算检索指标。

    Args:
        query_embeddings: {query_id: embedding}
        passage_embeddings: {fragment_id: embedding}
        eval_dataset: 评测数据集
        all_passage_ids: 全量片段 ID 列表（与 matrix 行对齐）
        all_passage_matrix: (N, D) 全量片段嵌入矩阵

    Returns:
        包含 MRR@k, Hit@k 等指标的字典
    """
    mrr_1_sum = 0.0
    mrr_3_sum = 0.0
    hit_1_sum = 0.0
    hit_3_sum = 0.0
    hit_10_sum = 0.0
    score_gaps = []
    n = len(eval_dataset)

    for item in eval_dataset:
        qid = item["query_id"]
        pos_id = item["positive_id"]

        if qid not in query_embeddings:
            continue

        q_emb = query_embeddings[qid]
        # 全量检索
        sims = compute_cosine_similarity(q_emb, all_passage_matrix)
        ranked_indices = np.argsort(-sims)

        # 找到 positive 的排名
        pos_rank = -1
        for rank, idx in enumerate(ranked_indices):
            if all_passage_ids[idx] == pos_id:
                pos_rank = rank + 1  # 1-indexed
                break

        if pos_rank == -1:
            continue

        # MRR@k
        if pos_rank <= 1:
            mrr_1_sum += 1.0 / pos_rank
        if pos_rank <= 3:
            mrr_3_sum += 1.0 / pos_rank
        # Hit@k
        if pos_rank <= 1:
            hit_1_sum += 1.0
        if pos_rank <= 3:
            hit_3_sum += 1.0
        if pos_rank <= 10:
            hit_10_sum += 1.0

        # Hard negative 区分度
        pos_score = sims[all_passage_ids.index(pos_id)] if pos_id in all_passage_ids else 0
        neg_scores = []
        for neg in item.get("hard_negatives", []):
            neg_id = neg["id"]
            if neg_id in all_passage_ids:
                neg_idx = all_passage_ids.index(neg_id)
                neg_scores.append(sims[neg_idx])
        if neg_scores:
            avg_neg = np.mean(neg_scores)
            score_gaps.append(float(pos_score - avg_neg))

    return {
        "mrr_at_1": mrr_1_sum / n if n > 0 else 0,
        "mrr_at_3": mrr_3_sum / n if n > 0 else 0,
        "hit_at_1": hit_1_sum / n if n > 0 else 0,
        "hit_at_3": hit_3_sum / n if n > 0 else 0,
        "hit_at_10": hit_10_sum / n if n > 0 else 0,
        "avg_score_gap": float(np.mean(score_gaps)) if score_gaps else 0,
    }


def compute_metrics_by_chapter(
    query_embeddings: dict[str, np.ndarray],
    eval_dataset: list[dict[str, Any]],
    all_passage_ids: list[str],
    all_passage_matrix: np.ndarray,
) -> dict[str, float]:
    """按章节计算 MRR@3。"""
    from collections import defaultdict

    chapter_items: dict[str, list] = defaultdict(list)
    for item in eval_dataset:
        ch = item.get("positive_chapter", "")
        chapter_items[ch].append(item)

    results = {}
    for ch, items in chapter_items.items():
        mrr_sum = 0.0
        n = 0
        for item in items:
            qid = item["query_id"]
            pos_id = item["positive_id"]
            if qid not in query_embeddings:
                continue
            q_emb = query_embeddings[qid]
            sims = compute_cosine_similarity(q_emb, all_passage_matrix)
            ranked_indices = np.argsort(-sims)
            for rank, idx in enumerate(ranked_indices[:3]):
                if all_passage_ids[idx] == pos_id:
                    mrr_sum += 1.0 / (rank + 1)
                    break
            n += 1
        short_ch = ch[:6] if ch else "未知"
        results[short_ch] = mrr_sum / n if n > 0 else 0

    return results


def compute_metrics_by_length(
    query_embeddings: dict[str, np.ndarray],
    eval_dataset: list[dict[str, Any]],
    all_passage_ids: list[str],
    all_passage_matrix: np.ndarray,
) -> tuple[dict[str, float], dict[str, float]]:
    """按片段长度分层计算 MRR@3 和 Hit@3。"""
    length_bins = [
        ("<512", lambda x: x <= 512),
        ("512-1024", lambda x: 512 < x <= 1024),
        (">1024", lambda x: x > 1024),
    ]

    mrr_results: dict[str, float] = {}
    hit3_results: dict[str, float] = {}

    for bin_name, bin_fn in length_bins:
        items = [it for it in eval_dataset if bin_fn(it.get("positive_char_count", 0))]
        if not items:
            mrr_results[bin_name] = 0
            hit3_results[bin_name] = 0
            continue

        mrr_sum = 0.0
        hit3_sum = 0.0
        n = 0
        for item in items:
            qid = item["query_id"]
            pos_id = item["positive_id"]
            if qid not in query_embeddings:
                continue
            q_emb = query_embeddings[qid]
            sims = compute_cosine_similarity(q_emb, all_passage_matrix)
            ranked_indices = np.argsort(-sims)
            for rank, idx in enumerate(ranked_indices[:3]):
                if all_passage_ids[idx] == pos_id:
                    mrr_sum += 1.0 / (rank + 1)
                    hit3_sum += 1.0
                    break
            n += 1
        mrr_results[bin_name] = mrr_sum / n if n > 0 else 0
        hit3_results[bin_name] = hit3_sum / n if n > 0 else 0

    return mrr_results, hit3_results


def save_top10_results(
    query_embeddings: dict[str, np.ndarray],
    eval_dataset: list[dict[str, Any]],
    all_passage_ids: list[str],
    all_passage_matrix: np.ndarray,
    output_path: str,
) -> None:
    """保存 top-10 召回结果供 Reranker 评测使用。"""
    results = []
    for item in eval_dataset:
        qid = item["query_id"]
        pos_id = item["positive_id"]
        if qid not in query_embeddings:
            continue
        q_emb = query_embeddings[qid]
        sims = compute_cosine_similarity(q_emb, all_passage_matrix)
        ranked_indices = np.argsort(-sims)[:10]

        top10 = []
        for idx in ranked_indices:
            top10.append({
                "id": all_passage_ids[idx],
                "score": float(sims[idx]),
            })

        results.append({
            "query_id": qid,
            "query": item["query"],
            "positive_id": pos_id,
            "positive_chapter": item.get("positive_chapter", ""),
            "positive_char_count": item.get("positive_char_count", 0),
            "top10": top10,
        })

    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def evaluate_model(
    model_config: dict[str, Any],
    fragments: list[dict[str, Any]],
    eval_dataset: list[dict[str, Any]],
    output_dir: str,
) -> EvalResult:
    """评测单个嵌入模型。

    Args:
        model_config: 模型配置
        fragments: 全量知识片段
        eval_dataset: 评测数据集
        output_dir: 输出目录

    Returns:
        评测结果
    """
    from sentence_transformers import SentenceTransformer

    model_name = model_config["name"]
    model_short = model_config["short"]
    print(f"\n{'='*60}")
    print(f"评测模型: {model_name}")
    print(f"{'='*60}")

    result = EvalResult(model_name=model_name, model_short=model_short)

    # 释放旧显存
    release_gpu()
    vram_before = get_gpu_memory_mb()

    # 加载模型
    print("  加载模型...")
    t0 = time.time()
    st_kwargs = model_config.get("st_kwargs", {})
    model = SentenceTransformer(model_name, **st_kwargs)
    load_time = time.time() - t0
    print(f"  加载耗时: {load_time:.1f}s")

    result.embedding_dim = model.get_sentence_embedding_dimension()
    print(f"  维度: {result.embedding_dim}")

    vram_after = get_gpu_memory_mb()
    result.vram_peak_mb = vram_after - vram_before
    print(f"  显存占用: {result.vram_peak_mb:.0f} MB")

    # ── 嵌入全量片段 ──
    print("  嵌入全量片段 (692 条)...")
    passage_texts = [f.get("content", "") for f in fragments]
    passage_ids = [f["id"] for f in fragments]

    batch_size = model_config.get("batch_size", 32)
    print(f"  batch_size: {batch_size}")

    t0 = time.time()
    passage_embs = model.encode(
        passage_texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    result.batch_embed_s = time.time() - t0
    print(f"  batch 嵌入耗时: {result.batch_embed_s:.1f}s")

    # ── 嵌入查询 ──
    print("  嵌入查询 (100 条)...")
    query_texts = [item["query"] for item in eval_dataset]
    query_ids = [item["query_id"] for item in eval_dataset]

    encode_kwargs = model_config.get("encode_kwargs", {})
    query_embs = model.encode(
        query_texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        **encode_kwargs,
    )

    # ── 单条延迟 ──
    sample_text = "灌注桩基础混凝土浇筑有什么工艺要求？"
    times = []
    for _ in range(10):
        t0 = time.time()
        model.encode([sample_text], convert_to_numpy=True, normalize_embeddings=True)
        times.append((time.time() - t0) * 1000)
    result.single_embed_ms = float(np.median(times))
    print(f"  单条延迟: {result.single_embed_ms:.1f} ms (median of 10)")

    # ── 计算检索指标 ──
    print("  计算检索指标...")
    query_emb_dict = {qid: emb for qid, emb in zip(query_ids, query_embs)}
    passage_matrix = np.array(passage_embs)

    metrics = compute_retrieval_metrics(
        query_emb_dict, {}, eval_dataset, passage_ids, passage_matrix,
    )
    result.mrr_at_1 = metrics["mrr_at_1"]
    result.mrr_at_3 = metrics["mrr_at_3"]
    result.hit_at_1 = metrics["hit_at_1"]
    result.hit_at_3 = metrics["hit_at_3"]
    result.hit_at_10 = metrics["hit_at_10"]
    result.avg_score_gap = metrics["avg_score_gap"]

    print(f"  MRR@1={result.mrr_at_1:.4f} MRR@3={result.mrr_at_3:.4f}")
    print(f"  Hit@1={result.hit_at_1:.2%} Hit@3={result.hit_at_3:.2%} Hit@10={result.hit_at_10:.2%}")
    print(f"  Hard Neg 区分度: {result.avg_score_gap:.4f}")

    # ── 按章节分析 ──
    result.mrr_by_chapter = compute_metrics_by_chapter(
        query_emb_dict, eval_dataset, passage_ids, passage_matrix,
    )
    print("  按章节 MRR@3:")
    for ch, mrr in sorted(result.mrr_by_chapter.items()):
        print(f"    {ch}: {mrr:.4f}")

    # ── 按长度分析 ──
    result.mrr_by_length, result.hit3_by_length = compute_metrics_by_length(
        query_emb_dict, eval_dataset, passage_ids, passage_matrix,
    )
    print("  按长度 MRR@3 / Hit@3:")
    for length_bin in ["<512", "512-1024", ">1024"]:
        mrr = result.mrr_by_length.get(length_bin, 0)
        hit3 = result.hit3_by_length.get(length_bin, 0)
        print(f"    {length_bin}: MRR@3={mrr:.4f} Hit@3={hit3:.2%}")

    # ── 保存 top-10 召回（供 Reranker 评测） ──
    top10_path = os.path.join(output_dir, f"top10_{model_short}.jsonl")
    save_top10_results(query_emb_dict, eval_dataset, passage_ids, passage_matrix, top10_path)
    print(f"  top-10 结果已保存: {top10_path}")

    # 更新显存峰值
    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / 1024 / 1024
        result.vram_peak_mb = max(result.vram_peak_mb, peak - vram_before)

    # 释放模型
    del model
    release_gpu()

    return result


def generate_report(results: list[EvalResult], output_path: str) -> None:
    """生成 Markdown 评测报告。"""
    lines = [
        "# 嵌入模型评测报告",
        "",
        f"> 评测时间: {time.strftime('%Y-%m-%d %H:%M')}",
        f"> 评测数据: 100 组 query-passage 对，692 条全量片段",
        f"> 硬件: RTX 4090 (24GB), i9-13900K, 64GB RAM",
        "",
        "## 综合排名",
        "",
        "| # | 模型 | MRR@3 | Hit@1 | Hit@3 | Hit@10 | 区分度 | 延迟(ms) | batch(s) | 显存(MB) | 维度 |",
        "|---|------|-------|-------|-------|--------|--------|---------|---------|---------|------|",
    ]

    # 按 MRR@3 排序
    sorted_results = sorted(results, key=lambda r: r.mrr_at_3, reverse=True)
    for i, r in enumerate(sorted_results, 1):
        lines.append(
            f"| {i} | {r.model_short} | {r.mrr_at_3:.4f} | {r.hit_at_1:.2%} | "
            f"{r.hit_at_3:.2%} | {r.hit_at_10:.2%} | {r.avg_score_gap:.4f} | "
            f"{r.single_embed_ms:.1f} | {r.batch_embed_s:.1f} | "
            f"{r.vram_peak_mb:.0f} | {r.embedding_dim} |"
        )

    # 长文本衰减
    lines.extend([
        "",
        "## 长文本衰减分析",
        "",
        "| 片段长度 | " + " | ".join(r.model_short for r in sorted_results) + " |",
        "|---------|" + "|".join("-------" for _ in sorted_results) + "|",
    ])
    for length_bin in ["<512", "512-1024", ">1024"]:
        row = f"| {length_bin} MRR@3 |"
        for r in sorted_results:
            val = r.mrr_by_length.get(length_bin, 0)
            row += f" {val:.4f} |"
        lines.append(row)
    for length_bin in ["<512", "512-1024", ">1024"]:
        row = f"| {length_bin} Hit@3 |"
        for r in sorted_results:
            val = r.hit3_by_length.get(length_bin, 0)
            row += f" {val:.2%} |"
        lines.append(row)

    # 按章节
    lines.extend([
        "",
        "## 按章节 MRR@3",
        "",
    ])
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

    print(f"\n评测报告已保存: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="嵌入模型评测")
    parser.add_argument("--eval-dataset", default="eval/embedding/eval_dataset.jsonl")
    parser.add_argument("--fragments", default="docs/knowledge_base/fragments/fragments.jsonl")
    parser.add_argument("--output", default="eval/embedding/results/")
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="指定要评测的模型 short name（如 bge-m3 qwen3-4b），默认全部",
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 加载数据
    print("加载评测数据集...")
    eval_dataset = load_jsonl(args.eval_dataset)
    print(f"  评测组数: {len(eval_dataset)}")

    print("加载知识片段...")
    fragments = load_jsonl(args.fragments)
    print(f"  片段数: {len(fragments)}")

    # 筛选候选模型
    candidates = EMBEDDING_CANDIDATES
    if args.models:
        candidates = [c for c in candidates if c["short"] in args.models]
    print(f"候选模型: {[c['short'] for c in candidates]}")

    # 逐个评测
    all_results: list[EvalResult] = []
    for config in candidates:
        try:
            result = evaluate_model(config, fragments, eval_dataset, args.output)
            all_results.append(result)

            # 保存中间结果
            with open(os.path.join(args.output, f"result_{config['short']}.json"), "w") as f:
                json.dump(asdict(result), f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"\n[ERROR] 模型 {config['name']} 评测失败: {e}")
            import traceback
            traceback.print_exc()

    # 生成报告
    if all_results:
        report_path = os.path.join(args.output, "embedding_report.md")
        generate_report(all_results, report_path)

    print(f"\n{'='*60}")
    print(f"评测完成: {len(all_results)}/{len(candidates)} 个模型")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
