"""知识提取管道 — 串联所有模块，输出 fragments.jsonl + 统计报告。

使用方式：
    conda run -n sca python -u -m knowledge_extraction
"""

import json
import os
import time
from collections import Counter
from typing import Dict, List

from tqdm import tqdm

from utils.logger_system import log_msg
from knowledge_extraction.config import (
    DOCS_TO_PROCESS,
    INPUT_PATH_TEMPLATE,
    OUTPUT_DIR,
    FRAGMENTS_FILE,
    REPORT_FILE,
    STANDARD_CHAPTERS,
)
from knowledge_extraction.chapter_splitter import ChapterSplitter
from knowledge_extraction.metadata_annotator import MetadataAnnotator
from knowledge_extraction.density_evaluator import DensityEvaluator
from knowledge_extraction.content_refiner import ContentRefiner
from knowledge_extraction.deduplicator import Deduplicator


def _fmt_elapsed(seconds: float) -> str:
    """将秒数格式化为 mm:ss 或 hh:mm:ss。"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class Pipeline:
    """知识提取管道，串联 5 个核心模块。

    流程：
      ChapterSplitter → MetadataAnnotator → DensityEvaluator
      → ContentRefiner → Deduplicator → 过滤 + 序列化
    """

    def __init__(self) -> None:
        """初始化各模块实例。"""
        self._splitter = ChapterSplitter()
        self._annotator = MetadataAnnotator()
        self._evaluator = DensityEvaluator()
        self._refiner = ContentRefiner()
        self._deduplicator = Deduplicator()

    def run(self) -> None:
        """执行完整提取管道。"""
        pipeline_start = time.time()
        print("\n" + "=" * 60)
        print("  知识提取管道  |  Knowledge Extraction Pipeline")
        print("=" * 60)
        print(f"  待处理文档: {len(DOCS_TO_PROCESS)} 份 — {DOCS_TO_PROCESS}")
        print(f"  输出目录:   {OUTPUT_DIR}/")
        print("=" * 60 + "\n")

        # ── Step 1-2: 逐文档切分 + 标注 ─────────────────────────
        step_start = time.time()
        print("▶ [Step 1/6] 章节切分 + 元数据标注")
        all_fragments: List[Dict] = []
        unmapped_log: List[Dict] = []

        for doc_id in tqdm(DOCS_TO_PROCESS, desc="  文档处理", unit="doc"):
            path = INPUT_PATH_TEMPLATE.format(doc_id=doc_id)
            if not os.path.exists(path):
                tqdm.write(f"  ⚠ DOC {doc_id}: 文件不存在，跳过 ({path})")
                continue

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Step 1: 章节切分
            sections = self._splitter.split(content, doc_id)

            # 记录 unmapped
            for s in sections:
                if s.mapped_chapter == "unmapped":
                    unmapped_log.append({
                        "source_doc": doc_id,
                        "title": s.title,
                        "level": s.level,
                        "char_count": len(s.content),
                    })

            # 过滤 unmapped（不参与后续处理）
            mapped_sections = [s for s in sections if s.mapped_chapter != "unmapped"]

            # Step 2: 元数据标注
            fragments = self._annotator.annotate(mapped_sections)
            all_fragments.extend(fragments)

            mapped_rate = len(mapped_sections) / len(sections) * 100 if sections else 0
            tqdm.write(
                f"  ✓ DOC {doc_id:2d}: {len(sections):3d} 片段, "
                f"映射 {len(mapped_sections):3d} ({mapped_rate:.0f}%), "
                f"unmapped {len(sections) - len(mapped_sections)}"
            )

        elapsed = time.time() - step_start
        print(f"  ── Step 1/6 完成: {len(all_fragments)} 条有效片段, "
              f"unmapped {len(unmapped_log)} 条 [{_fmt_elapsed(elapsed)}]\n")

        # ── Step 3: LLM 密度评估 ──────────────────────────────
        step_start = time.time()
        print(f"▶ [Step 2/6] LLM 密度评估 ({len(all_fragments)} 条)")
        all_fragments = self._evaluator.evaluate(all_fragments)
        elapsed = time.time() - step_start
        print(f"  ── Step 2/6 完成 [{_fmt_elapsed(elapsed)}]\n")

        # ── Step 4: 中密度片段 LLM 改写 ────────────────────────
        step_start = time.time()
        medium_count = sum(1 for f in all_fragments if f.get("density") == "medium")
        print(f"▶ [Step 3/6] 中密度片段改写 ({medium_count} 条需要改写)")
        all_fragments = self._refiner.refine(all_fragments)
        elapsed = time.time() - step_start
        print(f"  ── Step 3/6 完成 [{_fmt_elapsed(elapsed)}]\n")

        # ── Step 5: 去重 ──────────────────────────────────────
        step_start = time.time()
        before_dedup = sum(1 for f in all_fragments if f.get("density") in ("high", "medium"))
        print(f"▶ [Step 4/6] 跨文档去重 ({before_dedup} 条参与)")
        all_fragments = self._deduplicator.deduplicate(all_fragments)

        after_dedup = sum(1 for f in all_fragments if f.get("density") in ("high", "medium"))
        elapsed = time.time() - step_start
        print(f"  ── Step 4/6 完成: 移除 {before_dedup - after_dedup} 条重复 [{_fmt_elapsed(elapsed)}]\n")

        # ── Step 5: 过滤 low ──────────────────────────────────
        print("▶ [Step 5/6] 过滤 low 密度 + 生成 ID + 序列化")
        final_fragments = [
            f for f in all_fragments if f.get("density") in ("high", "medium")
        ]
        low_count = len(all_fragments) - len(final_fragments)
        print(f"  过滤 low 密度: {low_count} 条丢弃, {len(final_fragments)} 条入库")

        # 生成 ID
        id_counter: Dict[str, int] = {}
        for frag in final_fragments:
            ch_id = frag.get("chapter_id", "unmapped")
            doc_id = frag.get("source_doc", 0)
            key = f"doc{doc_id:02d}_{ch_id.lower()}"
            id_counter[key] = id_counter.get(key, 0) + 1
            frag["id"] = f"{key}_s{id_counter[key]:02d}"

        # 清理内部字段
        output_fields = [
            "id", "source_doc", "chapter", "section", "engineering_type",
            "quality_rating", "density", "density_reason", "is_refined",
            "tags", "content", "raw_content", "char_count", "has_table",
            "priority",
        ]
        clean_fragments = [
            {k: frag[k] for k in output_fields if k in frag}
            for frag in final_fragments
        ]

        # 按优先级排序：P0 > P1 > P2 > P3，同优先级按 source_doc 排序
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        clean_fragments.sort(
            key=lambda f: (
                priority_order.get(f.get("priority", "P3"), 3),
                f.get("source_doc", 99),
            )
        )

        # 写入 JSONL
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, FRAGMENTS_FILE)
        with open(output_path, "w", encoding="utf-8") as f:
            for frag in clean_fragments:
                f.write(json.dumps(frag, ensure_ascii=False) + "\n")

        print(f"  ✓ 输出 {len(clean_fragments)} 条知识片段 → {output_path}")
        print(f"  ── Step 5/6 完成\n")

        # ── Step 6: 生成统计报告 ──────────────────────────────
        print("▶ [Step 6/6] 生成统计报告")
        self._write_report(
            clean_fragments, all_fragments, unmapped_log
        )

        # ── 总结 ──────────────────────────────────────────────
        total_elapsed = time.time() - pipeline_start
        density_counts = Counter(f.get("density") for f in all_fragments)
        print("\n" + "=" * 60)
        print("  管道执行完毕  ✓")
        print("=" * 60)
        print(f"  总耗时:       {_fmt_elapsed(total_elapsed)}")
        print(f"  原始片段:     {len(all_fragments) + len(unmapped_log)}")
        print(f"  映射成功:     {len(all_fragments)}")
        print(f"  未映射:       {len(unmapped_log)}")
        print(f"  密度分布:     high={density_counts.get('high', 0)}, "
              f"medium={density_counts.get('medium', 0)}, "
              f"low={density_counts.get('low', 0)}")
        print(f"  最终入库:     {len(clean_fragments)} 条")
        print(f"  输出文件:     {output_path}")
        print("=" * 60 + "\n")

    def _write_report(
        self,
        final: List[Dict],
        all_frags: List[Dict],
        unmapped: List[Dict],
    ) -> None:
        """生成统计报告。

        Args:
            final: 最终入库的片段
            all_frags: 全部片段（含 low）
            unmapped: 未映射的片段信息
        """
        report_path = os.path.join(OUTPUT_DIR, REPORT_FILE)

        # 统计
        total_raw = len(all_frags) + len(unmapped)
        total_mapped = len(all_frags)
        density_counts = Counter(f.get("density") for f in all_frags)
        refined_count = sum(1 for f in final if f.get("is_refined"))
        not_refined_count = len(final) - refined_count
        low_in_all = density_counts.get("low", 0)
        dedup_removed = (
            density_counts.get("high", 0) + density_counts.get("medium", 0) - len(final)
        )

        ch_dist = Counter(f.get("chapter", "未知") for f in final)
        eng_dist = Counter(f.get("engineering_type", "未知") for f in final)
        doc_dist = Counter(f.get("source_doc") for f in final)

        lines = [
            "# 知识提取统计报告\n",
            f"> 生成时间: 管道运行完毕后自动生成\n",
            "",
            "## 总览\n",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 处理文档 | {len(DOCS_TO_PROCESS)} / 16（跳过 DOC 13, 14） |",
            f"| 总切分片段 | {total_raw} |",
            f"| 映射成功 | {total_mapped} ({total_mapped/total_raw*100:.1f}%) |" if total_raw > 0 else f"| 映射成功 | 0 |",
            f"| 未映射(unmapped) | {len(unmapped)} |",
            f"| 密度=high | {density_counts.get('high', 0)} |",
            f"| 密度=medium | {density_counts.get('medium', 0)} |",
            f"| 密度=low（丢弃） | {low_in_all} |",
            f"| 去重移除 | {max(dedup_removed, 0)} |",
            f"| **最终入库** | **{len(final)}** |",
            f"| 其中 is_refined=true | {refined_count} |",
            f"| 其中 is_refined=false | {not_refined_count} |",
            "",
            "## 按章节分布\n",
            "| 章节 | 片段数 |",
            "|------|--------|",
        ]
        for ch_name in STANDARD_CHAPTERS.values():
            count = ch_dist.get(ch_name, 0)
            lines.append(f"| {ch_name} | {count} |")

        lines.extend([
            "",
            "## 按工程类型分布\n",
            "| 工程类型 | 片段数 |",
            "|---------|--------|",
        ])
        for eng_type, count in eng_dist.most_common():
            lines.append(f"| {eng_type} | {count} |")

        lines.extend([
            "",
            "## 按文档分布\n",
            "| DOC | 片段数 |",
            "|-----|--------|",
        ])
        for doc_id in sorted(doc_dist):
            lines.append(f"| DOC {doc_id} | {doc_dist[doc_id]} |")

        if unmapped:
            lines.extend([
                "",
                "## 未映射片段清单（供人工复查）\n",
                "| DOC | 标题 | 层级 | 字数 |",
                "|-----|------|------|------|",
            ])
            for u in unmapped:
                lines.append(
                    f"| DOC {u['source_doc']} | {u['title'][:40]} | "
                    f"H{u['level']} | {u['char_count']} |"
                )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"  ✓ 统计报告 → {report_path}")
        print(f"  ── Step 6/6 完成")


def main() -> None:
    """管道入口。"""
    pipeline = Pipeline()
    pipeline.run()


if __name__ == "__main__":
    main()
