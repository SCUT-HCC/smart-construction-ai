"""元数据标注器 — 为每个 Section 标注结构化元数据。

标注字段：source_doc, chapter, section, engineering_type, quality_rating, tags。
"""

from typing import Dict, List

from knowledge_extraction.chapter_splitter import Section
from knowledge_extraction.config import (
    DOC_QUALITY,
    DOC_ENGINEERING_TYPE,
    ENGINEERING_TYPE_KEYWORDS,
    DOMAIN_KEYWORDS,
    CHAPTER_PRIORITY,
)


class MetadataAnnotator:
    """为 Section 列表标注元数据。

    - source_doc / chapter / section：来自 ChapterSplitter，直接透传
    - engineering_type：文档级默认 + 子章节级关键词覆盖
    - quality_rating：基于语料分析的文档评级 (1-3)
    - tags：领域关键词提取 Top-5
    """

    def annotate(self, sections: List[Section]) -> List[Dict]:
        """为 Section 列表标注元数据，输出字典列表。

        Args:
            sections: ChapterSplitter 输出的 Section 列表

        Returns:
            带元数据的字典列表，每个字典对应一个知识片段
        """
        results: List[Dict] = []
        for section in sections:
            doc_id = section.source_doc
            eng_type = self._infer_engineering_type(
                doc_id, section.content, section.title
            )
            tags = self._extract_tags(section.content)
            priority = CHAPTER_PRIORITY.get(section.mapped_chapter, "P3")

            fragment = {
                "source_doc": doc_id,
                "chapter": section.mapped_chapter_name,
                "chapter_id": section.mapped_chapter,
                "section": section.title,
                "engineering_type": eng_type,
                "quality_rating": DOC_QUALITY.get(doc_id, 2),
                "tags": tags,
                "content": section.content,
                "raw_content": section.content,
                "char_count": len(section.content),
                "has_table": section.has_table,
                "priority": priority,
                "sub_section_id": section.sub_section_id,
                "level": section.level,
            }
            results.append(fragment)

        return results

    def _infer_engineering_type(
        self, doc_id: int, content: str, title: str
    ) -> str:
        """推断工程类型：先用子章节关键词覆盖，否则回退到文档级默认。

        Args:
            doc_id: 文档编号
            content: 子章节正文
            title: 子章节标题

        Returns:
            工程类型字符串
        """
        text = title + " " + content[:500]

        # 子章节级关键词检测
        type_scores: Dict[str, int] = {}
        for eng_type, keywords in ENGINEERING_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                type_scores[eng_type] = score

        if type_scores:
            # 取命中最多关键词的类型
            best_type = max(type_scores, key=type_scores.get)  # type: ignore[arg-type]
            if type_scores[best_type] >= 2:
                return best_type

        # 回退到文档级默认
        return DOC_ENGINEERING_TYPE.get(doc_id, "未知")

    def _extract_tags(self, content: str) -> List[str]:
        """从内容中提取领域关键词 Top-5。

        Args:
            content: 片段正文

        Returns:
            最多 5 个领域关键词
        """
        tag_counts: Dict[str, int] = {}
        for kw in DOMAIN_KEYWORDS:
            count = content.count(kw)
            if count > 0:
                tag_counts[kw] = count

        # 按出现次数降序，取 Top-5
        sorted_tags = sorted(tag_counts, key=tag_counts.get, reverse=True)  # type: ignore[arg-type]
        return sorted_tags[:5]
