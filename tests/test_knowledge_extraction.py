"""知识提取模块单元测试。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from knowledge_extraction.chapter_splitter import ChapterSplitter, Section
from knowledge_extraction.metadata_annotator import MetadataAnnotator
from knowledge_extraction.density_evaluator import DensityEvaluator
from knowledge_extraction.content_refiner import ContentRefiner
from knowledge_extraction.deduplicator import Deduplicator


# ═══════════════════════════════════════════════════════════════
# ChapterSplitter 测试
# ═══════════════════════════════════════════════════════════════

class TestChapterSplitterParseHeaders:
    """测试 Markdown 标题层级识别。"""

    def test_basic_headers(self):
        """正确识别 #/##/### 层级。"""
        md = "# 标题一\n\n内容A\n\n## 标题二\n\n内容B\n\n### 标题三\n\n内容C"
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=99)
        levels = [s.level for s in sections]
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels

    def test_empty_content(self):
        """空文档返回空列表。"""
        splitter = ChapterSplitter()
        sections = splitter.split("", source_doc=99)
        assert sections == []


class TestChapterSplitterMapping:
    """测试章节映射逻辑。"""

    def test_exact_match(self):
        """精确关键词匹配。"""
        md = "# 一、编制依据\n\n引用标准列表..."
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=1)
        assert sections[0].mapped_chapter == "Ch1"

    def test_variant_match(self):
        """变体关键词匹配。"""
        md = "# 编制说明\n\n本方案编写依据..."
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=1)
        assert sections[0].mapped_chapter == "Ch1"

    def test_chapter_cn_format(self):
        """兼容"第一章"格式（DOC 12 风格）。"""
        md = "# 第一章 编制依据\n\n标准列表...\n\n# 第二章 工程概况\n\n工程简介..."
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=12)
        assert sections[0].mapped_chapter == "Ch1"
        assert sections[1].mapped_chapter == "Ch2"

    def test_unmapped_fallback(self):
        """无法匹配的标题标记为 unmapped。"""
        md = "# 完全无关的标题\n\n一些内容..."
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=1)
        assert sections[0].mapped_chapter == "unmapped"

    def test_subsection_inherits_parent(self):
        """子章节继承父章节映射。"""
        md = (
            "# 七、质量管理与控制措施\n\n总述\n\n"
            "## 7.1 质量管理组织机构\n\n组织机构内容\n\n"
            "## 7.2 质量保证措施\n\n措施内容"
        )
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=6)
        assert all(s.mapped_chapter == "Ch7" for s in sections)

    def test_施工工艺技术_maps_to_ch6(self):
        """DOC 11 的"施工工艺技术"映射到 Ch6。"""
        md = "# 施工工艺技术\n\n## 4.1 工艺流程\n\n流程内容"
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=11)
        assert sections[0].mapped_chapter == "Ch6"


class TestChapterSplitterAdminFilter:
    """测试行政内容过滤。"""

    def test_skip_report_form(self):
        """报审表应被过滤。"""
        md = (
            "# 表B.0.1 施工组织设计/专项施工方案报审表\n\n"
            "致：广东创成建设监理 盖章 签字 一式5份\n\n"
            "# 一、编制依据\n\n有效内容"
        )
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=1)
        titles = [s.title for s in sections]
        assert not any("报审" in t for t in titles)
        assert any("编制依据" in t for t in titles)

    def test_skip_toc(self):
        """目录应被过滤。"""
        md = "# 目录\n\n1. 编制依据\n2. 工程概况\n\n# 一、编制依据\n\n内容"
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=1)
        titles = [s.title for s in sections]
        assert "目录" not in titles


class TestChapterSplitterTable:
    """测试表格检测。"""

    def test_detect_markdown_table(self):
        """检测 Markdown 表格。"""
        md = "# 设备清单\n\n| 设备 | 数量 |\n|------|------|\n| 吊车 | 2 |"
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=10)
        assert sections[0].has_table is True

    def test_detect_html_table(self):
        """检测 HTML 表格。"""
        md = "# 参数表\n\n<table><tr><td>参数</td></tr></table>"
        splitter = ChapterSplitter()
        sections = splitter.split(md, source_doc=10)
        assert sections[0].has_table is True


# ═══════════════════════════════════════════════════════════════
# MetadataAnnotator 测试
# ═══════════════════════════════════════════════════════════════

class TestMetadataAnnotator:
    """测试元数据标注。"""

    def _make_section(self, **kwargs) -> Section:
        defaults = {
            "title": "7.1 质量管理",
            "content": "混凝土浇筑振捣密实，保护层厚度25mm。",
            "level": 2,
            "mapped_chapter": "Ch7",
            "mapped_chapter_name": "七、质量管理与控制措施",
            "sub_section_id": "7.1",
            "source_doc": 6,
            "has_table": False,
        }
        defaults.update(kwargs)
        return Section(**defaults)

    def test_all_fields_present(self):
        """元数据 6 个核心字段全部非空。"""
        annotator = MetadataAnnotator()
        sections = [self._make_section()]
        results = annotator.annotate(sections)
        frag = results[0]

        assert frag["source_doc"] == 6
        assert frag["chapter"] == "七、质量管理与控制措施"
        assert frag["section"] == "7.1 质量管理"
        assert frag["engineering_type"] != ""
        assert frag["quality_rating"] == 3  # DOC 6 高质量
        assert isinstance(frag["tags"], list)

    def test_engineering_type_doc7(self):
        """DOC 7 默认为变电电气。"""
        annotator = MetadataAnnotator()
        sections = [self._make_section(source_doc=7, content="一般内容")]
        results = annotator.annotate(sections)
        assert results[0]["engineering_type"] == "变电电气"

    def test_engineering_type_override(self):
        """子章节关键词可覆盖文档级默认类型。"""
        annotator = MetadataAnnotator()
        # DOC 6 默认变电土建，但主变内容应识别为变电电气
        sections = [self._make_section(
            source_doc=6,
            content="主变压器安装 GIS 室开关柜调试 主变就位后进行绝缘检测",
        )]
        results = annotator.annotate(sections)
        assert results[0]["engineering_type"] == "变电电气"

    def test_tags_extraction(self):
        """标签提取包含领域关键词。"""
        annotator = MetadataAnnotator()
        sections = [self._make_section(
            content="混凝土浇筑后应充分振捣，保护层厚度不小于25mm，养护期不少于14天。"
        )]
        results = annotator.annotate(sections)
        tags = results[0]["tags"]
        assert "混凝土" in tags or "浇筑" in tags or "振捣" in tags


# ═══════════════════════════════════════════════════════════════
# DensityEvaluator 测试
# ═══════════════════════════════════════════════════════════════

class TestDensityEvaluator:
    """测试密度评估器（Mock LLM）。"""

    def _mock_client(self, response_text: str) -> MagicMock:
        """创建返回指定文本的 Mock OpenAI 客户端。"""
        mock = MagicMock()
        mock.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=response_text))]
        )
        return mock

    def test_returns_density_and_reason(self):
        """LLM 返回合法 JSON 时正确解析。"""
        resp = '{"density": "high", "reason": "包含具体参数"}'
        evaluator = DensityEvaluator(client=self._mock_client(resp))
        fragments = [{"content": "text", "chapter": "c", "section": "s",
                       "engineering_type": "t", "source_doc": 1}]
        result = evaluator.evaluate(fragments)
        assert result[0]["density"] == "high"
        assert result[0]["density_reason"] == "包含具体参数"

    def test_handles_markdown_wrapped_json(self):
        """处理 LLM 返回被 ```json 包裹的情况。"""
        resp = '```json\n{"density": "low", "reason": "套话"}\n```'
        evaluator = DensityEvaluator(client=self._mock_client(resp))
        fragments = [{"content": "text", "chapter": "c", "section": "s",
                       "engineering_type": "t", "source_doc": 1}]
        result = evaluator.evaluate(fragments)
        assert result[0]["density"] == "low"

    def test_fallback_on_invalid_json(self):
        """JSON 解析失败时从文本提取或默认 medium。"""
        resp = "这是一段 high 密度的内容"
        evaluator = DensityEvaluator(client=self._mock_client(resp))
        fragments = [{"content": "text", "chapter": "c", "section": "s",
                       "engineering_type": "t", "source_doc": 1}]
        result = evaluator.evaluate(fragments)
        assert result[0]["density"] == "high"  # 从文本提取


# ═══════════════════════════════════════════════════════════════
# ContentRefiner 测试
# ═══════════════════════════════════════════════════════════════

class TestContentRefiner:
    """测试内容改写器（Mock LLM）。"""

    def _mock_client(self, response_text: str) -> MagicMock:
        mock = MagicMock()
        mock.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=response_text))]
        )
        return mock

    def test_sets_refined_fields(self):
        """改写后 is_refined=true，raw_content 保留原文。"""
        refiner = ContentRefiner(client=self._mock_client("精简后的高质量内容描述"))
        fragments = [{
            "content": "原始内容加上一些套话和冗余描述",
            "raw_content": "原始内容加上一些套话和冗余描述",
            "density": "medium",
            "density_reason": "中密度",
            "chapter": "c",
            "engineering_type": "t",
            "source_doc": 1,
            "section": "s",
        }]
        result = refiner.refine(fragments)
        assert result[0]["is_refined"] is True
        assert result[0]["raw_content"] == "原始内容加上一些套话和冗余描述"
        assert result[0]["content"] == "精简后的高质量内容描述"

    def test_high_density_not_refined(self):
        """high 密度片段不改写。"""
        refiner = ContentRefiner(client=self._mock_client("不应该被调用"))
        fragments = [{
            "content": "高密度原始内容",
            "raw_content": "高密度原始内容",
            "density": "high",
            "density_reason": "高密度",
            "chapter": "c",
            "engineering_type": "t",
            "source_doc": 1,
            "section": "s",
        }]
        result = refiner.refine(fragments)
        assert result[0]["is_refined"] is False
        assert result[0]["content"] == "高密度原始内容"

    def test_demote_short_refined(self):
        """改写后字数 < 30 降级为 low。"""
        refiner = ContentRefiner(client=self._mock_client("太短了"))
        fragments = [{
            "content": "原始的中密度内容，包含一些有用信息",
            "raw_content": "原始的中密度内容，包含一些有用信息",
            "density": "medium",
            "density_reason": "中密度",
            "chapter": "c",
            "engineering_type": "t",
            "source_doc": 1,
            "section": "s",
        }]
        result = refiner.refine(fragments)
        assert result[0]["density"] == "low"
        assert "降级" in result[0]["density_reason"]


# ═══════════════════════════════════════════════════════════════
# Deduplicator 测试
# ═══════════════════════════════════════════════════════════════

class TestDeduplicator:
    """测试去重器。"""

    def test_identical_texts(self):
        """完全重复文本仅保留 1 份。"""
        dedup = Deduplicator(threshold=0.8)
        fragments = [
            {"content": "混凝土浇筑应充分振捣确保密实", "chapter_id": "Ch7",
             "density": "high", "quality_rating": 3, "source_doc": 6},
            {"content": "混凝土浇筑应充分振捣确保密实", "chapter_id": "Ch7",
             "density": "high", "quality_rating": 2, "source_doc": 12},
        ]
        result = dedup.deduplicate(fragments)
        high_medium = [f for f in result if f["density"] in ("high", "medium")]
        assert len(high_medium) == 1
        assert high_medium[0]["source_doc"] == 6  # 保留 quality 更高的

    def test_similar_texts(self):
        """高相似文本（Jaccard>0.8）保留 quality_rating 更高者。"""
        dedup = Deduplicator(threshold=0.8)
        base = "混凝土浇筑施工时应充分振捣，确保振捣密实，不得漏振和过振"
        similar = "混凝土浇筑施工时应充分振捣，确保振捣密实，不得出现漏振和过振现象"
        fragments = [
            {"content": base, "chapter_id": "Ch7",
             "density": "high", "quality_rating": 2, "source_doc": 1},
            {"content": similar, "chapter_id": "Ch7",
             "density": "high", "quality_rating": 3, "source_doc": 6},
        ]
        result = dedup.deduplicate(fragments)
        high_medium = [f for f in result if f["density"] in ("high", "medium")]
        assert len(high_medium) == 1
        assert high_medium[0]["source_doc"] == 6

    def test_cross_chapter_no_dedup(self):
        """不同章节的相似文本不去重。"""
        dedup = Deduplicator(threshold=0.8)
        text = "安全管理组织机构应明确职责分工确保施工安全"
        fragments = [
            {"content": text, "chapter_id": "Ch7",
             "density": "high", "quality_rating": 3, "source_doc": 6},
            {"content": text, "chapter_id": "Ch8",
             "density": "high", "quality_rating": 3, "source_doc": 6},
        ]
        result = dedup.deduplicate(fragments)
        high_medium = [f for f in result if f["density"] in ("high", "medium")]
        assert len(high_medium) == 2

    def test_low_density_excluded(self):
        """low 密度片段不参与去重。"""
        dedup = Deduplicator(threshold=0.8)
        fragments = [
            {"content": "低密度内容", "chapter_id": "Ch7",
             "density": "low", "quality_rating": 3, "source_doc": 6},
        ]
        result = dedup.deduplicate(fragments)
        assert len(result) == 1
        assert result[0]["density"] == "low"
