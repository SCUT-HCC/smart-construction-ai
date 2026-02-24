"""章节分割器 — 将 final.md 按标题层级切分并映射到标准 10 章结构。

核心挑战：16 份文档有 560 种章节标题变体，需要三级回退映射策略。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from utils.logger_system import log_msg
from knowledge_extraction.config import (
    CHAPTER_MAPPING,
    STANDARD_CHAPTERS,
    ADMIN_KEYWORDS,
    ADMIN_TITLE_KEYWORDS,
    COVER_PATTERNS,
    CHAPTER_PRIORITY,
)


@dataclass
class Section:
    """切分后的章节片段。"""

    title: str
    content: str
    level: int
    mapped_chapter: str  # "Ch1"-"Ch10" 或 "unmapped"
    mapped_chapter_name: str  # "一、编制依据" 等，unmapped 时为空
    sub_section_id: str  # "7.3" 等
    source_doc: int = 0
    has_table: bool = False


# ── 标题正则 ──────────────────────────────────────────────────
# 匹配 Markdown 标题行：# / ## / ### / ####
_HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

# 匹配 "第一章"/"第二章" 等中文格式
_CHAPTER_CN_RE = re.compile(r"第[一二三四五六七八九十百千]+章\s*")

# 匹配中文数字前缀 "一、" / "二、"
_CN_NUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十]+、\s*")

# 匹配数字编号 "1.2" / "3.2.1"
_NUM_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")


class ChapterSplitter:
    """将 Markdown 文档切分为 Section 列表，并映射到标准 10 章结构。

    映射策略（三级回退）：
      L1 精确匹配 — 标题包含标准名称关键词
      L2 变体匹配 — 常见别名映射表
      L3 未匹配   — 标记为 unmapped
    """

    def split(self, content: str, source_doc: int) -> List[Section]:
        """切分文档并映射章节。

        Args:
            content: final.md 的完整文本
            source_doc: 文档编号（1-16）

        Returns:
            映射后的 Section 列表（已过滤行政内容）
        """
        raw_sections = self._split_by_headers(content)
        log_msg("INFO", f"DOC {source_doc}: 切分出 {len(raw_sections)} 个原始片段")

        sections: List[Section] = []
        current_chapter = "unmapped"
        current_chapter_level = 99  # 当前章节的标题层级

        for title, body, level in raw_sections:
            # 跳过行政内容
            if self._is_admin_content(title, body):
                continue

            # 映射章节
            mapped, mapped_name = self._map_chapter(title)

            # 判断是新章节还是子章节：
            # - 同层级或更浅 + 有映射结果 → 新章节，更新 current_chapter
            # - 更深层级 → 子章节，继承 current_chapter
            if mapped != "unmapped" and level <= current_chapter_level:
                current_chapter = mapped
                current_chapter_level = level

            if level > current_chapter_level and current_chapter != "unmapped":
                # 子章节：始终继承父章节
                effective_chapter = current_chapter
                effective_name = STANDARD_CHAPTERS.get(current_chapter, "")
            elif mapped != "unmapped":
                effective_chapter = mapped
                effective_name = mapped_name
            else:
                effective_chapter = current_chapter
                effective_name = STANDARD_CHAPTERS.get(current_chapter, "")

            sub_id = self._extract_sub_section_id(title)
            has_table = self._detect_table(body)

            sections.append(
                Section(
                    title=title.strip(),
                    content=body.strip(),
                    level=level,
                    mapped_chapter=effective_chapter,
                    mapped_chapter_name=effective_name,
                    sub_section_id=sub_id,
                    source_doc=source_doc,
                    has_table=has_table,
                )
            )

        mapped_count = sum(1 for s in sections if s.mapped_chapter != "unmapped")
        total = len(sections)
        rate = (mapped_count / total * 100) if total > 0 else 0
        log_msg(
            "INFO",
            f"DOC {source_doc}: 有效片段 {total}，映射成功 {mapped_count} ({rate:.1f}%)",
        )
        return sections

    # ── 内部方法 ──────────────────────────────────────────────

    def _split_by_headers(self, content: str) -> List[Tuple[str, str, int]]:
        """按 Markdown 标题切分，返回 (title, body, level) 列表。

        Args:
            content: Markdown 全文

        Returns:
            [(标题文本, 标题下方正文, 标题层级), ...]
        """
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

    def _is_admin_content(self, title: str, body: str) -> bool:
        """判断是否为行政内容（报审表/签字栏/目录/封面）。

        Args:
            title: 标题文本
            body: 正文文本

        Returns:
            True 表示应跳过
        """
        # 标题级过滤
        for kw in ADMIN_TITLE_KEYWORDS:
            if kw in title:
                return True

        # 正文级过滤：正文前 200 字包含行政关键词密度过高
        preview = body[:200] if body else ""
        admin_hits = sum(1 for kw in ADMIN_KEYWORDS if kw in preview)
        if admin_hits >= 2:
            return True

        # 封面/签字栏检测：正文前 300 字包含多个封面模式
        preview_cover = body[:300] if body else ""
        cover_hits = sum(1 for p in COVER_PATTERNS if p in preview_cover)
        if cover_hits >= 3:
            return True

        # 短正文 + 含签字/日期模式 → 签字栏残留
        if len(body) < 100:
            date_pattern = re.search(r"\d{4}[./年]\d{1,2}[./月]\d{1,2}", body)
            name_pattern = re.search(r"[：:]\s*[\u4e00-\u9fff]{2,4}\s*$", body, re.MULTILINE)
            if date_pattern and name_pattern:
                return True

        return False

    def _map_chapter(self, title: str) -> Tuple[str, str]:
        """将标题映射到标准 10 章结构。

        Args:
            title: 原始标题文本

        Returns:
            (chapter_id, chapter_name)，未匹配时返回 ("unmapped", "")
        """
        # 清理标题：去掉 "第X章" 前缀、中文数字前缀
        clean_title = _CHAPTER_CN_RE.sub("", title)
        clean_title = _CN_NUM_PREFIX_RE.sub("", clean_title)
        clean_title = _NUM_SECTION_RE.sub("", clean_title)
        clean_title = clean_title.strip()

        # L1: 精确匹配
        for ch_id, rules in CHAPTER_MAPPING.items():
            for kw in rules["exact"]:
                if kw in clean_title or kw in title:
                    return ch_id, STANDARD_CHAPTERS[ch_id]

        # L2: 变体匹配
        for ch_id, rules in CHAPTER_MAPPING.items():
            for kw in rules["variant"]:
                if kw in clean_title or kw in title:
                    return ch_id, STANDARD_CHAPTERS[ch_id]

        return "unmapped", ""

    def _extract_sub_section_id(self, title: str) -> str:
        """从标题中提取子章节编号（如 "7.3"、"3.2.1"）。

        Args:
            title: 标题文本

        Returns:
            编号字符串，无编号时返回空字符串
        """
        m = _NUM_SECTION_RE.search(title)
        if m:
            return m.group(1)

        # 尝试匹配中文数字开头 "一、" → "1"
        cn_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                  "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        m_cn = _CN_NUM_PREFIX_RE.match(title)
        if m_cn:
            cn_char = title[0]
            return cn_map.get(cn_char, "")

        return ""

    def _detect_table(self, body: str) -> bool:
        """检测正文中是否包含表格。

        Args:
            body: 正文文本

        Returns:
            True 表示包含表格
        """
        if "<table" in body.lower():
            return True
        # Markdown 表格：至少 2 行 |...|
        table_lines = [line for line in body.split("\n") if line.strip().startswith("|")]
        return len(table_lines) >= 2
