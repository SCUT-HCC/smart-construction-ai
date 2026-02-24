"""K19 阶段1 — 全量映射覆盖分析。

遍历 14 份 final.md，逐标题运行现有 ChapterSplitter._map_chapter()，
统计 L1/L2 命中率、未映射清单、各章分布。

用法:
    conda run -n sca python scripts/analyze_mapping_coverage.py
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_extraction.config import (
    CHAPTER_MAPPING,
    DOCS_TO_PROCESS,
    INPUT_PATH_TEMPLATE,
    STANDARD_CHAPTERS,
    ADMIN_KEYWORDS,
    ADMIN_TITLE_KEYWORDS,
    COVER_PATTERNS,
)

# ── 标题正则（复用 chapter_splitter.py 的逻辑） ─────────────────
_HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_CHAPTER_CN_RE = re.compile(r"第[一二三四五六七八九十百千]+章\s*")
_CN_NUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十]+、\s*")
_NUM_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")


def clean_title(title: str) -> str:
    """去掉编号前缀，返回清理后的标题。"""
    clean = _CHAPTER_CN_RE.sub("", title)
    clean = _CN_NUM_PREFIX_RE.sub("", clean)
    clean = _NUM_SECTION_RE.sub("", clean)
    return clean.strip()


def map_chapter_detailed(title: str) -> Tuple[str, str, str, str]:
    """映射标题，返回 (chapter_id, chapter_name, match_type, matched_keyword)。

    match_type: "exact" | "variant" | "unmapped"
    """
    cleaned = clean_title(title)

    # L1: 精确匹配
    for ch_id, rules in CHAPTER_MAPPING.items():
        for kw in rules["exact"]:
            if kw in cleaned or kw in title:
                return ch_id, STANDARD_CHAPTERS[ch_id], "exact", kw

    # L2: 变体匹配
    for ch_id, rules in CHAPTER_MAPPING.items():
        for kw in rules["variant"]:
            if kw in cleaned or kw in title:
                return ch_id, STANDARD_CHAPTERS[ch_id], "variant", kw

    return "unmapped", "", "unmapped", ""


def split_headers(content: str) -> List[Tuple[str, str, int]]:
    """按 Markdown 标题切分，返回 (title, body, level) 列表。"""
    matches = list(_HEADER_RE.finditer(content))
    if not matches:
        return []
    results: List[Tuple[str, str, int]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        results.append((title, body, level))
    return results


def is_admin_content(title: str, body: str) -> bool:
    """判断是否为行政内容。"""
    for kw in ADMIN_TITLE_KEYWORDS:
        if kw in title:
            return True
    preview = body[:200] if body else ""
    admin_hits = sum(1 for kw in ADMIN_KEYWORDS if kw in preview)
    if admin_hits >= 2:
        return True
    preview_cover = body[:300] if body else ""
    cover_hits = sum(1 for p in COVER_PATTERNS if p in preview_cover)
    if cover_hits >= 3:
        return True
    return False


def analyze() -> None:
    """运行全量分析并打印报告。"""
    # 统计计数器
    total_sections = 0
    l1_hits = 0
    l2_hits = 0
    unmapped_count = 0
    admin_filtered = 0
    chapter_dist: Dict[str, int] = Counter()
    unmapped_list: List[Tuple[int, str, int, str]] = []  # (doc, title, level, body_preview)
    match_details: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)  # kw -> [(doc, title, type)]
    ambiguous: List[Tuple[int, str, str, str]] = []  # 可能误映射

    # 宽泛关键词列表（可能误映射）
    broad_keywords = {"施工", "质量", "安全", "应急", "概述"}

    for doc_id in DOCS_TO_PROCESS:
        path = PROJECT_ROOT / INPUT_PATH_TEMPLATE.format(doc_id=doc_id)
        if not path.exists():
            print(f"⚠️ 文件不存在: {path}")
            continue

        content = path.read_text(encoding="utf-8")
        sections = split_headers(content)

        for title, body, level in sections:
            if is_admin_content(title, body):
                admin_filtered += 1
                continue

            total_sections += 1
            ch_id, ch_name, match_type, matched_kw = map_chapter_detailed(title)

            if match_type == "exact":
                l1_hits += 1
                chapter_dist[ch_id] += 1
                match_details[matched_kw].append((doc_id, title, "exact"))
            elif match_type == "variant":
                l2_hits += 1
                chapter_dist[ch_id] += 1
                match_details[matched_kw].append((doc_id, title, "variant"))
            else:
                unmapped_count += 1
                body_preview = body[:60].replace("\n", " ") if body else ""
                unmapped_list.append((doc_id, title, level, body_preview))

            # 检测宽泛匹配：标题很短且命中的关键词是宽泛词
            cleaned = clean_title(title)
            if matched_kw and len(cleaned) <= 4 and cleaned in broad_keywords:
                ambiguous.append((doc_id, title, ch_id, matched_kw))

    # ── 打印报告 ────────────────────────────────────────────
    print("=" * 60)
    print("K19 阶段1：全量映射覆盖分析报告")
    print("=" * 60)
    print()
    print(f"处理文档数: {len(DOCS_TO_PROCESS)}")
    print(f"总标题数(含行政): {total_sections + admin_filtered}")
    print(f"行政内容过滤: {admin_filtered}")
    print(f"有效片段数: {total_sections}")
    print()
    print("── 映射统计 ──")
    print(f"  L1 精确命中: {l1_hits:4d} ({l1_hits / total_sections * 100:.1f}%)")
    print(f"  L2 变体命中: {l2_hits:4d} ({l2_hits / total_sections * 100:.1f}%)")
    mapped = l1_hits + l2_hits
    print(f"  总映射成功: {mapped:4d} ({mapped / total_sections * 100:.1f}%)")
    print(f"  未映射:      {unmapped_count:4d} ({unmapped_count / total_sections * 100:.1f}%)")
    print()

    print("── 各章命中分布 ──")
    for ch_id in sorted(chapter_dist.keys(), key=lambda x: int(x.replace("Ch", ""))):
        name = STANDARD_CHAPTERS.get(ch_id, "?")
        count = chapter_dist[ch_id]
        print(f"  {ch_id} {name}: {count}")
    print()

    print("── 未映射标题清单 ──")
    if unmapped_list:
        for doc_id, title, level, preview in unmapped_list:
            print(f"  DOC {doc_id:2d} | H{level} | {title}")
            if preview:
                print(f"         └── {preview}...")
    else:
        print("  （无未映射标题）")
    print()

    print("── 宽泛/歧义匹配 ──")
    if ambiguous:
        for doc_id, title, ch_id, kw in ambiguous:
            print(f"  DOC {doc_id:2d} | \"{title}\" → {ch_id} (命中: \"{kw}\")")
    else:
        print("  （无歧义匹配）")
    print()

    # 高频命中关键词 TOP 15
    print("── 高频命中关键词 TOP 15 ──")
    kw_counts = {kw: len(hits) for kw, hits in match_details.items()}
    for kw, count in sorted(kw_counts.items(), key=lambda x: -x[1])[:15]:
        sample_type = match_details[kw][0][2]
        print(f"  {count:4d} | [{sample_type:7s}] \"{kw}\"")
    print()

    print("=" * 60)
    print("分析完成")
    print("=" * 60)


if __name__ == "__main__":
    analyze()
