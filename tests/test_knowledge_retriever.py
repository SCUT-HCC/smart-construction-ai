"""S10 统一检索接口单元测试。

覆盖 config.py、models.py、retriever.py 的核心逻辑。
使用 Mock 双引擎，不依赖真实数据库或模型。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from knowledge_graph.retriever import KGRetriever, ProcessRequirements
from knowledge_retriever.config import (
    CHAPTERS_NEED_KG,
    DEFAULT_VECTOR_THRESHOLD,
    DEFAULT_VECTOR_TOP_K,
    PRIORITY_KG_RULE,
    PRIORITY_TEMPLATE,
    PRIORITY_VECTOR_CASE,
    TEMPLATE_COLLECTION,
)
from knowledge_retriever.models import RetrievalItem, RetrievalResponse
from knowledge_retriever.retriever import (
    KnowledgeRetriever,
    _chapter_needs_kg,
    _merge_and_sort,
    _process_requirements_to_items,
)
from vector_store.retriever import RetrievalResult, VectorRetriever


# ═══════════════════════════════════════════════════════════════
# 测试 Fixture
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def mock_vector() -> MagicMock:
    """Mock VectorRetriever。"""
    mock = MagicMock(spec=VectorRetriever)
    mock.search.return_value = [
        RetrievalResult(
            content="混凝土浇筑施工应分层进行",
            score=0.92,
            collection="ch06_methods",
            file_id="doc01",
            context=None,
        ),
        RetrievalResult(
            content="项目经理负责全面管理",
            score=0.75,
            collection="templates",
            file_id="doc03",
            context=None,
        ),
    ]
    return mock


@pytest.fixture
def mock_kg() -> MagicMock:
    """Mock KGRetriever。"""
    mock = MagicMock(spec=KGRetriever)
    mock.infer_process_chain.return_value = ProcessRequirements(
        process_name="钢筋绑扎",
        equipment=["塔吊"],
        hazards=["高处坠落"],
        safety_measures={"高处坠落": ["佩戴安全带"]},
        quality_points=["钢筋间距检查"],
    )
    return mock


@pytest.fixture
def retriever(mock_vector: MagicMock, mock_kg: MagicMock) -> KnowledgeRetriever:
    """带双引擎的 KnowledgeRetriever。"""
    return KnowledgeRetriever(
        vector_retriever=mock_vector,
        kg_retriever=mock_kg,
    )


@pytest.fixture
def retriever_vector_only(mock_vector: MagicMock) -> KnowledgeRetriever:
    """仅向量引擎的 KnowledgeRetriever。"""
    return KnowledgeRetriever(vector_retriever=mock_vector)


@pytest.fixture
def retriever_kg_only(mock_kg: MagicMock) -> KnowledgeRetriever:
    """仅 KG 引擎的 KnowledgeRetriever。"""
    return KnowledgeRetriever(kg_retriever=mock_kg)


@pytest.fixture
def retriever_empty() -> KnowledgeRetriever:
    """无引擎的 KnowledgeRetriever。"""
    return KnowledgeRetriever()


# ═══════════════════════════════════════════════════════════════
# config.py 测试
# ═══════════════════════════════════════════════════════════════


class TestConfig:
    """测试配置常量。"""

    def test_priority_ordering(self) -> None:
        """优先级数值正确排序。"""
        assert PRIORITY_KG_RULE < PRIORITY_VECTOR_CASE < PRIORITY_TEMPLATE

    def test_chapters_need_kg(self) -> None:
        """需要 KG 推理的章节包含安全/质量/应急。"""
        assert "ch07_quality" in CHAPTERS_NEED_KG
        assert "ch08_safety" in CHAPTERS_NEED_KG
        assert "ch09_emergency" in CHAPTERS_NEED_KG

    def test_chapters_not_need_kg(self) -> None:
        """编制依据/施工方法等章节不需要 KG 推理。"""
        assert "ch01_basis" not in CHAPTERS_NEED_KG
        assert "ch06_methods" not in CHAPTERS_NEED_KG

    def test_default_params(self) -> None:
        """默认检索参数合理。"""
        assert DEFAULT_VECTOR_TOP_K == 3
        assert DEFAULT_VECTOR_THRESHOLD == 0.6

    def test_template_collection_name(self) -> None:
        """模板 collection 名称。"""
        assert TEMPLATE_COLLECTION == "templates"


# ═══════════════════════════════════════════════════════════════
# models.py — RetrievalItem 测试
# ═══════════════════════════════════════════════════════════════


class TestRetrievalItem:
    """测试统一检索结果条目。"""

    def test_to_dict(self) -> None:
        """转换为字典包含所有字段。"""
        item = RetrievalItem(
            content="测试内容",
            source="vector",
            priority=2,
            score=0.85,
            metadata={"collection": "ch06_methods"},
        )
        d = item.to_dict()
        assert d["content"] == "测试内容"
        assert d["source"] == "vector"
        assert d["priority"] == 2
        assert d["score"] == 0.85
        assert d["metadata"]["collection"] == "ch06_methods"

    def test_default_metadata(self) -> None:
        """metadata 默认为空字典。"""
        item = RetrievalItem(content="x", source="kg_rule", priority=1, score=1.0)
        assert item.metadata == {}

    def test_kg_rule_item(self) -> None:
        """KG 规则条目属性正确。"""
        item = RetrievalItem(
            content="工序需要设备",
            source="kg_rule",
            priority=PRIORITY_KG_RULE,
            score=1.0,
        )
        assert item.source == "kg_rule"
        assert item.priority == 1

    def test_template_item(self) -> None:
        """模板条目属性正确。"""
        item = RetrievalItem(
            content="通用模板内容",
            source="template",
            priority=PRIORITY_TEMPLATE,
            score=0.7,
        )
        assert item.source == "template"
        assert item.priority == 3


# ═══════════════════════════════════════════════════════════════
# models.py — RetrievalResponse 测试
# ═══════════════════════════════════════════════════════════════


class TestRetrievalResponse:
    """测试统一检索响应。"""

    def test_empty_response(self) -> None:
        """空响应默认值正确。"""
        resp = RetrievalResponse()
        assert resp.items == []
        assert resp.regulations == []
        assert resp.cases == []
        assert resp.query_context == {}

    def test_to_dict(self) -> None:
        """转换为字典结构正确。"""
        item = RetrievalItem(content="x", source="vector", priority=2, score=0.8)
        resp = RetrievalResponse(
            items=[item],
            cases=[item],
            query_context={"chapter": "ch06_methods"},
        )
        d = resp.to_dict()
        assert len(d["items"]) == 1
        assert d["items"][0]["content"] == "x"
        assert d["query_context"]["chapter"] == "ch06_methods"

    def test_response_classification(self) -> None:
        """响应按来源正确分类。"""
        reg = RetrievalItem(content="规范", source="kg_rule", priority=1, score=1.0)
        case = RetrievalItem(content="案例", source="vector", priority=2, score=0.9)
        tpl = RetrievalItem(content="模板", source="template", priority=3, score=0.7)
        resp = RetrievalResponse(
            items=[reg, case, tpl],
            regulations=[reg],
            cases=[case, tpl],
        )
        assert len(resp.regulations) == 1
        assert len(resp.cases) == 2


# ═══════════════════════════════════════════════════════════════
# retriever.py — 内部辅助函数测试
# ═══════════════════════════════════════════════════════════════


class TestChapterNeedsKG:
    """测试章节 KG 需求判断。"""

    def test_quality_chapter(self) -> None:
        """质量章节需要 KG。"""
        assert _chapter_needs_kg("ch07_quality") is True

    def test_safety_chapter(self) -> None:
        """安全章节需要 KG。"""
        assert _chapter_needs_kg("ch08_safety") is True

    def test_emergency_chapter(self) -> None:
        """应急章节需要 KG。"""
        assert _chapter_needs_kg("ch09_emergency") is True

    def test_methods_chapter(self) -> None:
        """施工方法章节不需要 KG。"""
        assert _chapter_needs_kg("ch06_methods") is False

    def test_basis_chapter(self) -> None:
        """编制依据章节不需要 KG。"""
        assert _chapter_needs_kg("ch01_basis") is False

    def test_none_chapter(self) -> None:
        """未指定章节时默认启用 KG。"""
        assert _chapter_needs_kg(None) is True


class TestMergeAndSort:
    """测试融合排序。"""

    def test_sort_by_priority(self) -> None:
        """按优先级升序排列。"""
        items = [
            RetrievalItem(content="c", source="template", priority=3, score=0.9),
            RetrievalItem(content="a", source="kg_rule", priority=1, score=0.8),
            RetrievalItem(content="b", source="vector", priority=2, score=0.85),
        ]
        sorted_items = _merge_and_sort(items)
        assert [i.priority for i in sorted_items] == [1, 2, 3]

    def test_sort_by_score_within_priority(self) -> None:
        """同优先级内按评分降序。"""
        items = [
            RetrievalItem(content="low", source="vector", priority=2, score=0.6),
            RetrievalItem(content="high", source="vector", priority=2, score=0.95),
            RetrievalItem(content="mid", source="vector", priority=2, score=0.8),
        ]
        sorted_items = _merge_and_sort(items)
        assert [i.score for i in sorted_items] == [0.95, 0.8, 0.6]

    def test_empty_list(self) -> None:
        """空列表返回空。"""
        assert _merge_and_sort([]) == []

    def test_immutability(self) -> None:
        """排序不修改原列表。"""
        items = [
            RetrievalItem(content="b", source="vector", priority=2, score=0.5),
            RetrievalItem(content="a", source="kg_rule", priority=1, score=1.0),
        ]
        original_order = [i.content for i in items]
        _merge_and_sort(items)
        assert [i.content for i in items] == original_order


class TestProcessRequirementsToItems:
    """测试 ProcessRequirements → RetrievalItem 转换。"""

    def test_full_chain(self) -> None:
        """完整要求链转换。"""
        req = ProcessRequirements(
            process_name="钢筋绑扎",
            equipment=["塔吊"],
            hazards=["高处坠落"],
            safety_measures={"高处坠落": ["佩戴安全带"]},
            quality_points=["钢筋间距检查"],
        )
        items = _process_requirements_to_items(req)
        # 设备 + 危险源+措施 + 质量要点 = 3 条
        assert len(items) == 3
        assert all(i.source == "kg_rule" for i in items)
        assert all(i.priority == PRIORITY_KG_RULE for i in items)
        assert all(i.score == 1.0 for i in items)

    def test_equipment_item(self) -> None:
        """设备条目内容正确。"""
        req = ProcessRequirements(
            process_name="混凝土浇筑",
            equipment=["搅拌车", "泵车"],
        )
        items = _process_requirements_to_items(req)
        assert len(items) == 1
        assert "搅拌车" in items[0].content
        assert "泵车" in items[0].content
        assert items[0].metadata["rule_type"] == "equipment"

    def test_hazard_with_measures(self) -> None:
        """危险源+安全措施条目。"""
        req = ProcessRequirements(
            process_name="高处作业",
            hazards=["坠落"],
            safety_measures={"坠落": ["安全带", "防护栏"]},
        )
        items = _process_requirements_to_items(req)
        assert len(items) == 1
        assert "坠落" in items[0].content
        assert "安全带" in items[0].content
        assert items[0].metadata["rule_type"] == "hazard_measure"

    def test_hazard_without_measures(self) -> None:
        """危险源无安全措施时仍生成条目。"""
        req = ProcessRequirements(
            process_name="测试工序",
            hazards=["触电"],
        )
        items = _process_requirements_to_items(req)
        assert len(items) == 1
        assert "触电" in items[0].content
        assert items[0].metadata["measures"] == []

    def test_quality_item(self) -> None:
        """质量要点条目。"""
        req = ProcessRequirements(
            process_name="混凝土浇筑",
            quality_points=["振捣密实度", "保护层厚度"],
        )
        items = _process_requirements_to_items(req)
        assert len(items) == 1
        assert "振捣密实度" in items[0].content
        assert items[0].metadata["rule_type"] == "quality"

    def test_empty_requirements(self) -> None:
        """空要求链返回空列表。"""
        req = ProcessRequirements(process_name="空工序")
        items = _process_requirements_to_items(req)
        assert items == []

    def test_multiple_hazards(self) -> None:
        """多个危险源生成多条。"""
        req = ProcessRequirements(
            process_name="基坑开挖",
            hazards=["坍塌", "触电", "高处坠落"],
            safety_measures={
                "坍塌": ["支护"],
                "触电": ["绝缘"],
            },
        )
        items = _process_requirements_to_items(req)
        assert len(items) == 3
        hazards_in_content = [i.metadata["hazard"] for i in items]
        assert "坍塌" in hazards_in_content
        assert "触电" in hazards_in_content
        assert "高处坠落" in hazards_in_content


# ═══════════════════════════════════════════════════════════════
# retriever.py — KnowledgeRetriever 主类测试
# ═══════════════════════════════════════════════════════════════


class TestKnowledgeRetrieverRetrieve:
    """测试统一检索入口 retrieve()。"""

    def test_dual_engine_with_kg_chapter(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock, mock_kg: MagicMock
    ) -> None:
        """KG 章节同时触发双引擎。"""
        resp = retriever.retrieve(
            query="钢筋绑扎质量控制",
            chapter="ch07_quality",
            engineering_type="变电土建",
            processes=["钢筋绑扎"],
        )
        # KG 应被调用
        mock_kg.infer_process_chain.assert_called_once_with("钢筋绑扎")
        # 向量检索也应被调用
        mock_vector.search.assert_called_once()
        # 结果非空
        assert len(resp.items) > 0
        assert len(resp.regulations) > 0
        assert len(resp.cases) > 0

    def test_non_kg_chapter_skips_kg(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """非 KG 章节不触发 KG 推理。"""
        resp = retriever.retrieve(
            query="施工方法",
            chapter="ch06_methods",
            processes=["钢筋绑扎"],
        )
        mock_kg.infer_process_chain.assert_not_called()
        assert resp.regulations == []

    def test_none_chapter_triggers_kg(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """未指定章节时触发 KG。"""
        retriever.retrieve(
            query="通用查询",
            chapter=None,
            processes=["钢筋绑扎"],
        )
        mock_kg.infer_process_chain.assert_called()

    def test_fusion_order(self, retriever: KnowledgeRetriever) -> None:
        """融合结果按 priority ASC 排列。"""
        resp = retriever.retrieve(
            query="质量管理",
            chapter="ch08_safety",
            processes=["钢筋绑扎"],
        )
        priorities = [i.priority for i in resp.items]
        assert priorities == sorted(priorities)

    def test_query_context(self, retriever: KnowledgeRetriever) -> None:
        """查询上下文正确记录。"""
        resp = retriever.retrieve(
            query="测试查询",
            chapter="ch07_quality",
            engineering_type="变电土建",
            processes=["钢筋绑扎"],
        )
        ctx = resp.query_context
        assert ctx["query"] == "测试查询"
        assert ctx["chapter"] == "ch07_quality"
        assert ctx["engineering_type"] == "变电土建"
        assert ctx["processes"] == ["钢筋绑扎"]

    def test_template_results_priority(self, retriever: KnowledgeRetriever) -> None:
        """templates collection 结果 priority 为 PRIORITY_TEMPLATE。"""
        resp = retriever.retrieve(
            query="组织机构",
            chapter="ch06_methods",
        )
        template_items = [i for i in resp.items if i.source == "template"]
        for item in template_items:
            assert item.priority == PRIORITY_TEMPLATE


class TestKnowledgeRetrieverRegulations:
    """测试 retrieve_regulations()。"""

    def test_basic_regulations(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """基本规范检索。"""
        items = retriever.retrieve_regulations(processes=["钢筋绑扎"])
        assert len(items) == 3  # 设备 + 危险源 + 质量
        assert all(i.source == "kg_rule" for i in items)
        mock_kg.infer_process_chain.assert_called_once_with("钢筋绑扎")

    def test_no_processes(self, retriever: KnowledgeRetriever) -> None:
        """无工序时返回空。"""
        items = retriever.retrieve_regulations(processes=None)
        assert items == []

    def test_empty_processes(self, retriever: KnowledgeRetriever) -> None:
        """空工序列表返回空。"""
        items = retriever.retrieve_regulations(processes=[])
        assert items == []

    def test_multiple_processes(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """多个工序逐一推理。"""
        retriever.retrieve_regulations(processes=["钢筋绑扎", "混凝土浇筑"])
        assert mock_kg.infer_process_chain.call_count == 2

    def test_no_kg_engine(self, retriever_vector_only: KnowledgeRetriever) -> None:
        """无 KG 引擎时返回空。"""
        items = retriever_vector_only.retrieve_regulations(processes=["钢筋绑扎"])
        assert items == []


class TestKnowledgeRetrieverCases:
    """测试 retrieve_cases()。"""

    def test_basic_cases(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """基本案例检索。"""
        items = retriever.retrieve_cases(query="混凝土浇筑")
        assert len(items) == 2
        mock_vector.search.assert_called_once_with(
            query="混凝土浇筑",
            collection=None,
            engineering_type=None,
            limit=DEFAULT_VECTOR_TOP_K,
            threshold=DEFAULT_VECTOR_THRESHOLD,
        )

    def test_case_source_tagging(self, retriever: KnowledgeRetriever) -> None:
        """非模板结果 source="vector"，模板结果 source="template"。"""
        items = retriever.retrieve_cases(query="混凝土浇筑")
        vector_items = [i for i in items if i.source == "vector"]
        template_items = [i for i in items if i.source == "template"]
        assert len(vector_items) == 1
        assert len(template_items) == 1

    def test_case_priority_tagging(self, retriever: KnowledgeRetriever) -> None:
        """向量案例 priority=2，模板 priority=3。"""
        items = retriever.retrieve_cases(query="混凝土浇筑")
        for item in items:
            if item.source == "vector":
                assert item.priority == PRIORITY_VECTOR_CASE
            elif item.source == "template":
                assert item.priority == PRIORITY_TEMPLATE

    def test_case_metadata(self, retriever: KnowledgeRetriever) -> None:
        """元数据包含 collection 和 file_id。"""
        items = retriever.retrieve_cases(query="混凝土浇筑")
        for item in items:
            assert "collection" in item.metadata
            assert "file_id" in item.metadata

    def test_with_chapter_filter(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """章节过滤透传给向量检索器。"""
        retriever.retrieve_cases(query="安全措施", chapter="ch08_safety")
        call_kwargs = mock_vector.search.call_args.kwargs
        assert call_kwargs["collection"] == "ch08_safety"

    def test_with_engineering_type(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """工程类型过滤透传。"""
        retriever.retrieve_cases(query="混凝土", engineering_type="变电土建")
        call_kwargs = mock_vector.search.call_args.kwargs
        assert call_kwargs["engineering_type"] == "变电土建"

    def test_custom_limit(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """自定义 limit 透传。"""
        retriever.retrieve_cases(query="测试", limit=5)
        call_kwargs = mock_vector.search.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_no_vector_engine(self, retriever_kg_only: KnowledgeRetriever) -> None:
        """无向量引擎时返回空。"""
        items = retriever_kg_only.retrieve_cases(query="测试")
        assert items == []


class TestKnowledgeRetrieverInferRules:
    """测试 infer_rules()。"""

    def test_basic_inference(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """基本推理。"""
        items = retriever.infer_rules(context="灌注桩基础施工", processes=["钢筋绑扎"])
        assert len(items) == 3
        mock_kg.infer_process_chain.assert_called_once_with("钢筋绑扎")

    def test_no_processes(self, retriever: KnowledgeRetriever) -> None:
        """无工序时返回空。"""
        items = retriever.infer_rules(context="测试", processes=None)
        assert items == []

    def test_empty_processes(self, retriever: KnowledgeRetriever) -> None:
        """空工序列表返回空。"""
        items = retriever.infer_rules(context="测试", processes=[])
        assert items == []

    def test_no_kg_engine(self, retriever_vector_only: KnowledgeRetriever) -> None:
        """无 KG 引擎时返回空。"""
        items = retriever_vector_only.infer_rules(
            context="测试", processes=["钢筋绑扎"]
        )
        assert items == []


class TestKnowledgeRetrieverSingleEngine:
    """测试单引擎模式。"""

    def test_vector_only(
        self, retriever_vector_only: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """仅向量引擎：KG 相关章节也正常工作。"""
        resp = retriever_vector_only.retrieve(
            query="安全措施",
            chapter="ch08_safety",
            processes=["钢筋绑扎"],
        )
        # 无规范，有案例
        assert resp.regulations == []
        assert len(resp.cases) > 0
        mock_vector.search.assert_called_once()

    def test_kg_only(
        self, retriever_kg_only: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """仅 KG 引擎：无案例但有规范。"""
        resp = retriever_kg_only.retrieve(
            query="质量管理",
            chapter="ch07_quality",
            processes=["钢筋绑扎"],
        )
        assert len(resp.regulations) > 0
        assert resp.cases == []
        mock_kg.infer_process_chain.assert_called_once()

    def test_no_engine(self, retriever_empty: KnowledgeRetriever) -> None:
        """双引擎均不可用时返回空结果。"""
        resp = retriever_empty.retrieve(
            query="测试",
            chapter="ch08_safety",
            processes=["钢筋绑扎"],
        )
        assert resp.items == []
        assert resp.regulations == []
        assert resp.cases == []


class TestKnowledgeRetrieverDegradation:
    """测试降级行为。"""

    def test_kg_empty_result(
        self, retriever: KnowledgeRetriever, mock_kg: MagicMock
    ) -> None:
        """KG 返回空结果时仍有 vector 结果。"""
        mock_kg.infer_process_chain.return_value = ProcessRequirements(
            process_name="空工序"
        )
        resp = retriever.retrieve(
            query="施工方法",
            chapter="ch08_safety",
            processes=["空工序"],
        )
        # KG 无结果，但 vector 有
        assert resp.regulations == []
        assert len(resp.cases) > 0

    def test_vector_empty_result(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """向量检索无结果时仍有 KG 结果。"""
        mock_vector.search.return_value = []
        resp = retriever.retrieve(
            query="质量控制",
            chapter="ch07_quality",
            processes=["钢筋绑扎"],
        )
        assert len(resp.regulations) > 0
        assert resp.cases == []


class TestKnowledgeRetrieverClose:
    """测试资源释放。"""

    def test_close_releases_engines(
        self, retriever: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """close() 释放双引擎。"""
        retriever.close()
        mock_vector.close.assert_called_once()
        assert retriever._vector is None
        assert retriever._kg is None

    def test_close_without_engines(self, retriever_empty: KnowledgeRetriever) -> None:
        """无引擎时 close() 不报错。"""
        retriever_empty.close()
        assert retriever_empty._vector is None
        assert retriever_empty._kg is None

    def test_close_vector_only(
        self, retriever_vector_only: KnowledgeRetriever, mock_vector: MagicMock
    ) -> None:
        """仅向量引擎时 close() 正常。"""
        retriever_vector_only.close()
        mock_vector.close.assert_called_once()
