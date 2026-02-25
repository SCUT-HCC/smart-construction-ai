"""K21 实体/关系抽取 — 单元测试"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from entity_extraction.schema import Entity, KnowledgeGraph, Relation
from entity_extraction.rule_extractor import (
    _parse_table_rows,
    _split_sections,
    parse_hazard_sources,
    parse_quality_points,
    parse_process_references,
    parse_safety_measures,
)
from entity_extraction.normalizer import (
    normalize_name,
    _edit_distance,
    deduplicate_entities,
    deduplicate_relations,
    assign_ids,
)
from entity_extraction.llm_extractor import LLMExtractor
from entity_extraction.config import (
    HAZARD_SOURCES_PATH,
    QUALITY_POINTS_PATH,
    SAFETY_MEASURES_PATH,
    PROCESS_REFS_DIR,
)


# ===================================================================
# schema.py 测试
# ===================================================================


class TestEntity:
    """Entity 数据模型测试。"""

    def test_create_entity(self) -> None:
        """创建实体，验证默认值。"""
        e = Entity(type="process", name="混凝土浇筑")
        assert e.type == "process"
        assert e.name == "混凝土浇筑"
        assert e.aliases == []
        assert e.engineering_type == "通用"
        assert e.source == "rule"
        assert e.confidence == 1.0

    def test_entity_with_attributes(self) -> None:
        """创建带属性的危险源实体。"""
        e = Entity(
            type="hazard",
            name="坍塌",
            engineering_type="变电土建",
            attributes={"risk_level": "4", "accident_type": "坍塌"},
        )
        assert e.attributes["risk_level"] == "4"

    def test_entity_with_aliases(self) -> None:
        """创建带别名的工序实体。"""
        e = Entity(
            type="process",
            name="混凝土浇筑",
            aliases=["浇筑混凝土", "混凝土灌注"],
        )
        assert len(e.aliases) == 2


class TestRelation:
    """Relation 数据模型测试。"""

    def test_create_relation(self) -> None:
        """创建关系三元组。"""
        r = Relation(
            source_entity_id="proc_001",
            target_entity_id="hazard_001",
            relation_type="produces_hazard",
            evidence="基坑开挖 → 坍塌风险",
            source_doc="hazard_sources.md",
        )
        assert r.relation_type == "produces_hazard"
        assert r.confidence == 1.0


class TestKnowledgeGraph:
    """KnowledgeGraph 查找功能测试。"""

    @pytest.fixture()
    def sample_graph(self) -> KnowledgeGraph:
        """构造测试用知识图谱。"""
        return KnowledgeGraph(
            entities=[
                Entity(type="process", name="混凝土浇筑", engineering_type="变电土建"),
                Entity(
                    type="process",
                    name="钻孔",
                    aliases=["钻孔施工"],
                    engineering_type="线路塔基",
                ),
                Entity(type="hazard", name="坍塌", engineering_type="变电土建"),
            ],
        )

    def test_entity_by_name(self, sample_graph: KnowledgeGraph) -> None:
        """按名称精确查找。"""
        e = sample_graph.entity_by_name("混凝土浇筑")
        assert e is not None
        assert e.type == "process"

    def test_entity_by_name_not_found(self, sample_graph: KnowledgeGraph) -> None:
        """名称不存在返回 None。"""
        assert sample_graph.entity_by_name("不存在的实体") is None

    def test_entity_by_name_with_type(self, sample_graph: KnowledgeGraph) -> None:
        """按名称+类型过滤。"""
        assert sample_graph.entity_by_name("坍塌", "hazard") is not None
        assert sample_graph.entity_by_name("坍塌", "process") is None

    def test_find_entity_by_alias(self, sample_graph: KnowledgeGraph) -> None:
        """通过别名查找实体。"""
        e = sample_graph.find_entity("钻孔施工")
        assert e is not None
        assert e.name == "钻孔"

    def test_find_entity_with_engineering_type(
        self, sample_graph: KnowledgeGraph
    ) -> None:
        """按工程类型过滤。"""
        e = sample_graph.find_entity("混凝土浇筑", engineering_type="变电土建")
        assert e is not None
        e2 = sample_graph.find_entity("混凝土浇筑", engineering_type="线路塔基")
        assert e2 is None


# ===================================================================
# 通用解析工具测试
# ===================================================================


class TestParseTableRows:
    """Markdown 表格解析测试。"""

    def test_basic_table(self) -> None:
        """解析标准 Markdown 表格。"""
        md = """\
| 序号 | 作业活动 | 危险因素 |
|------|---------|---------|
| 1 | 土方工程 | 坍塌 |
| 2 | 吊装 | 高处坠落 |
"""
        rows = _parse_table_rows(md)
        assert len(rows) == 2
        assert rows[0] == ["1", "土方工程", "坍塌"]
        assert rows[1] == ["2", "吊装", "高处坠落"]

    def test_empty_table(self) -> None:
        """空表格返回空列表。"""
        md = "没有表格的文本"
        assert _parse_table_rows(md) == []

    def test_table_with_extra_spaces(self) -> None:
        """表格单元格内有多余空格。"""
        md = """\
| 序号 |  内容  |
|------|--------|
|  1   |  措施A  |
"""
        rows = _parse_table_rows(md)
        assert rows[0] == ["1", "措施A"]


class TestSplitSections:
    """Markdown 章节分割测试。"""

    def test_split_h2_sections(self) -> None:
        """按 ## 分割章节。"""
        md = """\
## 1. 概述
第一章内容
## 2. 土建
第二章内容
## 3. 电气
第三章内容
"""
        sections = _split_sections(md)
        assert "1" in sections
        assert "2" in sections
        assert "3" in sections
        assert "第一章内容" in sections["1"]

    def test_split_h3_sections(self) -> None:
        """按 ### 分割子章节。"""
        md = """\
## 5. 特殊作业
### 5.1 有限空间
内容A
### 5.2 起重吊装
内容B
"""
        sections = _split_sections(md)
        assert "5" in sections
        assert "5.1" in sections
        assert "5.2" in sections
        assert "内容A" in sections["5.1"]
        assert "内容B" in sections["5.2"]


# ===================================================================
# hazard_sources.md 解析测试
# ===================================================================


class TestParseHazardSources:
    """危险源清单解析测试 — 使用真实数据文件。"""

    @pytest.fixture()
    def result(self) -> tuple[list[Entity], list[Relation]]:
        """解析真实 hazard_sources.md。"""
        assert HAZARD_SOURCES_PATH.exists(), f"数据文件不存在: {HAZARD_SOURCES_PATH}"
        return parse_hazard_sources()

    def test_entities_not_empty(self, result: tuple) -> None:
        """应产出实体。"""
        entities, _ = result
        assert len(entities) > 0

    def test_relations_not_empty(self, result: tuple) -> None:
        """应产出关系。"""
        _, relations = result
        assert len(relations) > 0

    def test_entity_types_coverage(self, result: tuple) -> None:
        """应覆盖 process、hazard、safety_measure 三种实体类型。"""
        entities, _ = result
        types = {e.type for e in entities}
        assert "process" in types
        assert "hazard" in types
        assert "safety_measure" in types

    def test_engineering_types_coverage(self, result: tuple) -> None:
        """应覆盖 4 种工程类型。"""
        entities, _ = result
        eng_types = {e.engineering_type for e in entities}
        assert "变电土建" in eng_types
        assert "变电电气" in eng_types
        assert "线路塔基" in eng_types
        assert "特殊作业" in eng_types

    def test_relation_types(self, result: tuple) -> None:
        """应包含 produces_hazard 和 mitigated_by 两种关系。"""
        _, relations = result
        rel_types = {r.relation_type for r in relations}
        assert "produces_hazard" in rel_types
        assert "mitigated_by" in rel_types

    def test_civil_hazard_count(self, result: tuple) -> None:
        """变电土建危险源应有 15 条（对应表格 15 行）。"""
        entities, _ = result
        civil_hazards = [
            e
            for e in entities
            if e.type == "hazard" and e.engineering_type == "变电土建"
        ]
        assert len(civil_hazards) == 15

    def test_electrical_hazard_count(self, result: tuple) -> None:
        """变电电气危险源应有 9 条。"""
        entities, _ = result
        elec_hazards = [
            e
            for e in entities
            if e.type == "hazard" and e.engineering_type == "变电电气"
        ]
        assert len(elec_hazards) == 9

    def test_line_tower_hazard_count(self, result: tuple) -> None:
        """线路塔基危险源应有 7 条。"""
        entities, _ = result
        line_hazards = [
            e
            for e in entities
            if e.type == "hazard" and e.engineering_type == "线路塔基"
        ]
        assert len(line_hazards) == 7

    def test_special_hazard_count(self, result: tuple) -> None:
        """特殊作业危险源应有 12 条（4+5+3）。"""
        entities, _ = result
        special_hazards = [
            e
            for e in entities
            if e.type == "hazard" and e.engineering_type == "特殊作业"
        ]
        assert len(special_hazards) == 12

    def test_hazard_has_risk_level(self, result: tuple) -> None:
        """危险源实体应包含 risk_level 属性。"""
        entities, _ = result
        hazards = [e for e in entities if e.type == "hazard"]
        for h in hazards:
            assert "risk_level" in h.attributes, f"危险源 '{h.name}' 缺少 risk_level"

    def test_relation_evidence_not_empty(self, result: tuple) -> None:
        """关系应有非空证据。"""
        _, relations = result
        for r in relations:
            assert r.evidence, f"关系 {r.relation_type} 缺少 evidence"


# ===================================================================
# safety_measures.md 解析测试
# ===================================================================


class TestParseSafetyMeasures:
    """安全措施库解析测试。"""

    @pytest.fixture()
    def result(self) -> list[Entity]:
        assert SAFETY_MEASURES_PATH.exists()
        return parse_safety_measures()

    def test_entities_not_empty(self, result: list[Entity]) -> None:
        """应产出安全措施实体。"""
        assert len(result) > 0

    def test_all_safety_measure_type(self, result: list[Entity]) -> None:
        """所有实体类型应为 safety_measure。"""
        for e in result:
            assert e.type == "safety_measure"

    def test_has_scene_attribute(self, result: list[Entity]) -> None:
        """部分实体应有 scene 属性。"""
        with_scene = [e for e in result if "scene" in e.attributes]
        assert len(with_scene) > 0


# ===================================================================
# quality_control_points.md 解析测试
# ===================================================================


class TestParseQualityPoints:
    """质量控制点解析测试。"""

    @pytest.fixture()
    def result(self) -> tuple[list[Entity], list[Relation]]:
        assert QUALITY_POINTS_PATH.exists()
        return parse_quality_points()

    def test_entities_not_empty(self, result: tuple) -> None:
        entities, _ = result
        assert len(entities) > 0

    def test_relations_not_empty(self, result: tuple) -> None:
        _, relations = result
        assert len(relations) > 0

    def test_has_quality_point_entities(self, result: tuple) -> None:
        """应包含 quality_point 类型实体。"""
        entities, _ = result
        qp = [e for e in entities if e.type == "quality_point"]
        assert len(qp) > 0

    def test_relation_type(self, result: tuple) -> None:
        """关系类型应为 requires_quality_check。"""
        _, relations = result
        for r in relations:
            assert r.relation_type == "requires_quality_check"

    def test_electrical_quality_points(self, result: tuple) -> None:
        """变电电气应有主变安装质量控制点。"""
        entities, _ = result
        elec_qp = [
            e
            for e in entities
            if e.type == "quality_point" and e.engineering_type == "变电电气"
        ]
        assert len(elec_qp) >= 7  # 主变 7 个 + 建筑电气 4 个


# ===================================================================
# process_references/*.md 解析测试
# ===================================================================


class TestParseProcessReferences:
    """工艺参考文件解析测试。"""

    @pytest.fixture()
    def result(self) -> tuple[list[Entity], list[Relation]]:
        assert PROCESS_REFS_DIR.exists()
        return parse_process_references()

    def test_entities_not_empty(self, result: tuple) -> None:
        entities, _ = result
        assert len(entities) > 0

    def test_has_process_entities(self, result: tuple) -> None:
        """应包含 process 类型实体。"""
        entities, _ = result
        procs = [e for e in entities if e.type == "process"]
        assert len(procs) > 0

    def test_multiple_engineering_types(self, result: tuple) -> None:
        """应覆盖多种工程类型。"""
        entities, _ = result
        eng_types = {e.engineering_type for e in entities}
        assert len(eng_types) >= 3


# ===================================================================
# normalizer.py 测试
# ===================================================================


class TestNormalizeName:
    """名称归一化测试。"""

    def test_strip_whitespace(self) -> None:
        """去除首尾空白。"""
        assert normalize_name("  混凝土浇筑  ") == "混凝土浇筑"

    def test_remove_suffix_work(self) -> None:
        """去除后缀虚词'工作'。"""
        assert normalize_name("安全检查工作") == "安全检查"

    def test_remove_suffix_construction(self) -> None:
        """去除后缀虚词'施工'。"""
        assert normalize_name("基坑开挖施工") == "基坑开挖"

    def test_keep_short_name(self) -> None:
        """短名称不去后缀（保留≥2字）。"""
        # "施工" 去掉 "施工" 后只剩 ""，不应去除
        assert normalize_name("施工") == "施工"

    def test_remove_prefix(self) -> None:
        """去除前缀虚词'进行'。"""
        assert normalize_name("进行焊接") == "焊接"

    def test_remove_prefix_implement(self) -> None:
        """去除前缀虚词'实施'。"""
        assert normalize_name("实施吊装") == "吊装"

    def test_collapse_spaces(self) -> None:
        """合并多余空格。"""
        assert normalize_name("混凝土  浇筑") == "混凝土浇筑"

    def test_empty_string(self) -> None:
        """空字符串返回空。"""
        assert normalize_name("") == ""

    def test_preserve_meaningful_suffix(self) -> None:
        """保留有意义的后缀（如高处作业→高处, 因为'高处'≥2字）。"""
        result = normalize_name("高处作业")
        assert result == "高处"


class TestEditDistance:
    """编辑距离测试。"""

    def test_identical(self) -> None:
        assert _edit_distance("abc", "abc") == 0

    def test_one_insert(self) -> None:
        assert _edit_distance("abc", "abcd") == 1

    def test_one_delete(self) -> None:
        assert _edit_distance("abcd", "abc") == 1

    def test_one_replace(self) -> None:
        assert _edit_distance("abc", "aXc") == 1

    def test_empty_strings(self) -> None:
        assert _edit_distance("", "") == 0

    def test_one_empty(self) -> None:
        assert _edit_distance("", "abc") == 3
        assert _edit_distance("abc", "") == 3

    def test_chinese(self) -> None:
        """中文字符的编辑距离。"""
        assert _edit_distance("混凝土浇筑", "混凝土灌注") == 2


class TestDeduplicateEntities:
    """实体去重测试。"""

    def test_exact_dedup(self) -> None:
        """精确匹配去重：同名同类型合并。"""
        entities = [
            Entity(
                type="hazard", name="坍塌", engineering_type="变电土建", source="rule"
            ),
            Entity(
                type="hazard", name="坍塌", engineering_type="变电土建", source="llm"
            ),
        ]
        result, name_map = deduplicate_entities(entities)
        hazards = [e for e in result if e.type == "hazard" and e.name == "坍塌"]
        assert len(hazards) == 1

    def test_multi_source_boost(self) -> None:
        """多源确认提升置信度。"""
        entities = [
            Entity(
                type="hazard",
                name="坍塌",
                engineering_type="变电土建",
                source="rule",
                confidence=0.9,
            ),
            Entity(
                type="hazard",
                name="坍塌",
                engineering_type="变电土建",
                source="llm",
                confidence=0.8,
            ),
        ]
        result, _ = deduplicate_entities(entities)
        hazards = [e for e in result if e.name == "坍塌"]
        assert len(hazards) == 1
        assert hazards[0].confidence == 1.0  # 0.9 + 0.1 = 1.0

    def test_different_type_not_merged(self) -> None:
        """不同类型的同名实体不合并。"""
        entities = [
            Entity(type="process", name="焊接", engineering_type="通用"),
            Entity(type="hazard", name="焊接", engineering_type="通用"),
        ]
        result, _ = deduplicate_entities(entities)
        assert len(result) == 2

    def test_fuzzy_merge(self) -> None:
        """模糊匹配：编辑距离≤2的同类型实体合并。"""
        entities = [
            Entity(type="process", name="混凝土浇筑", engineering_type="变电土建"),
            Entity(type="process", name="混凝土灌注", engineering_type="变电土建"),
        ]
        result, name_map = deduplicate_entities(entities)
        procs = [e for e in result if e.type == "process"]
        assert len(procs) == 1
        assert len(name_map) == 1  # 一个名称被映射

    def test_empty_name_filtered(self) -> None:
        """空名称实体被过滤。"""
        entities = [
            Entity(type="process", name="", engineering_type="通用"),
            Entity(type="process", name="焊接", engineering_type="通用"),
        ]
        result, _ = deduplicate_entities(entities)
        assert len(result) == 1
        assert result[0].name == "焊接"


class TestDeduplicateRelations:
    """关系去重测试。"""

    def test_basic_dedup(self) -> None:
        """相同三元组去重，保留高 confidence。"""
        relations = [
            Relation(
                source_entity_id="A",
                target_entity_id="B",
                relation_type="produces_hazard",
                confidence=0.8,
                evidence="短证据",
            ),
            Relation(
                source_entity_id="A",
                target_entity_id="B",
                relation_type="produces_hazard",
                confidence=0.9,
                evidence="长一点的证据",
            ),
        ]
        result = deduplicate_relations(relations, {})
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_name_map_applied(self) -> None:
        """名称映射应用到关系的实体引用。"""
        relations = [
            Relation(
                source_entity_id="混凝土灌注",
                target_entity_id="坍塌",
                relation_type="produces_hazard",
            ),
        ]
        name_map = {"混凝土灌注": "混凝土浇筑"}
        result = deduplicate_relations(relations, name_map)
        assert result[0].source_entity_id == "混凝土浇筑"

    def test_different_triples_kept(self) -> None:
        """不同三元组保留。"""
        relations = [
            Relation(
                source_entity_id="A",
                target_entity_id="B",
                relation_type="produces_hazard",
            ),
            Relation(
                source_entity_id="A",
                target_entity_id="C",
                relation_type="produces_hazard",
            ),
        ]
        result = deduplicate_relations(relations, {})
        assert len(result) == 2


class TestAssignIds:
    """ID 分配测试。"""

    def test_entity_id_format(self) -> None:
        """验证实体 ID 格式。"""
        entities = [
            Entity(type="process", name="焊接", engineering_type="变电土建"),
            Entity(type="hazard", name="坍塌", engineering_type="变电土建"),
        ]
        relations: list[Relation] = []
        assign_ids(entities, relations)
        assert entities[0].id == "process_civil_001"
        assert entities[1].id == "hazard_civil_001"

    def test_relation_id_format(self) -> None:
        """验证关系 ID 格式。"""
        entities = [
            Entity(type="process", name="焊接", engineering_type="变电土建"),
            Entity(type="hazard", name="坍塌", engineering_type="变电土建"),
        ]
        relations = [
            Relation(
                source_entity_id="焊接",
                target_entity_id="坍塌",
                relation_type="produces_hazard",
            ),
        ]
        assign_ids(entities, relations)
        assert relations[0].id == "rel_0001"
        assert relations[0].source_entity_id == "process_civil_001"
        assert relations[0].target_entity_id == "hazard_civil_001"

    def test_alias_mapping(self) -> None:
        """别名也映射到正确的实体 ID。"""
        entities = [
            Entity(
                type="process",
                name="焊接",
                aliases=["电焊"],
                engineering_type="变电土建",
            ),
        ]
        relations = [
            Relation(
                source_entity_id="电焊",
                target_entity_id="X",
                relation_type="produces_hazard",
            ),
        ]
        assign_ids(entities, relations)
        assert relations[0].source_entity_id == "process_civil_001"


# ===================================================================
# llm_extractor.py 测试
# ===================================================================


class TestLLMExtractorParseJson:
    """LLM JSON 解析测试。"""

    def test_parse_valid_json(self) -> None:
        """解析有效 JSON。"""
        text = '{"entities": [], "relations": []}'
        result = LLMExtractor._try_parse_json(text)
        assert result is not None
        assert result["entities"] == []

    def test_parse_json_with_markdown_block(self) -> None:
        """解析带 ```json 标记的文本。"""
        text = '```json\n{"entities": [{"type": "process", "name": "焊接"}], "relations": []}\n```'
        result = LLMExtractor._try_parse_json(text)
        assert result is not None
        assert len(result["entities"]) == 1

    def test_parse_json_embedded_in_text(self) -> None:
        """从文本中提取嵌入的 JSON。"""
        text = '以下是抽取结果：\n{"entities": [], "relations": [{"source": "A", "target": "B", "type": "produces_hazard"}]}\n结束'
        result = LLMExtractor._try_parse_json(text)
        assert result is not None
        assert len(result["relations"]) == 1

    def test_parse_invalid_json(self) -> None:
        """无效 JSON 返回 None。"""
        result = LLMExtractor._try_parse_json("这不是JSON")
        assert result is None


class TestLLMExtractorParseResponse:
    """LLM 响应解析测试。"""

    def test_parse_entities(self) -> None:
        """解析实体列表。"""
        client = MagicMock()
        extractor = LLMExtractor(client=client)
        text = json.dumps(
            {
                "entities": [
                    {"type": "process", "name": "混凝土浇筑", "attributes": {}},
                    {
                        "type": "hazard",
                        "name": "坍塌",
                        "attributes": {"risk_level": "4"},
                    },
                ],
                "relations": [],
            }
        )
        entities, relations = extractor._parse_response(text, "变电土建", "doc1")
        assert len(entities) == 2
        assert entities[0].type == "process"
        assert entities[0].source == "llm"
        assert entities[0].confidence == 0.8

    def test_parse_relations(self) -> None:
        """解析关系列表。"""
        client = MagicMock()
        extractor = LLMExtractor(client=client)
        text = json.dumps(
            {
                "entities": [],
                "relations": [
                    {
                        "source": "焊接",
                        "target": "触电",
                        "type": "produces_hazard",
                        "evidence": "焊接时存在触电风险",
                    },
                ],
            }
        )
        entities, relations = extractor._parse_response(text, "变电土建", "doc1")
        assert len(relations) == 1
        assert relations[0].relation_type == "produces_hazard"
        assert relations[0].source_doc == "doc1"

    def test_filter_invalid_entity_type(self) -> None:
        """过滤无效实体类型。"""
        client = MagicMock()
        extractor = LLMExtractor(client=client)
        text = json.dumps(
            {
                "entities": [
                    {"type": "unknown_type", "name": "测试"},
                    {"type": "process", "name": "焊接"},
                ],
                "relations": [],
            }
        )
        entities, _ = extractor._parse_response(text, "通用", "doc1")
        assert len(entities) == 1
        assert entities[0].name == "焊接"

    def test_filter_invalid_relation_type(self) -> None:
        """过滤无效关系类型。"""
        client = MagicMock()
        extractor = LLMExtractor(client=client)
        text = json.dumps(
            {
                "entities": [],
                "relations": [
                    {
                        "source": "A",
                        "target": "B",
                        "type": "invalid_type",
                        "evidence": "e",
                    },
                    {
                        "source": "A",
                        "target": "B",
                        "type": "produces_hazard",
                        "evidence": "e",
                    },
                ],
            }
        )
        _, relations = extractor._parse_response(text, "通用", "doc1")
        assert len(relations) == 1

    def test_empty_response(self) -> None:
        """空响应返回空列表。"""
        client = MagicMock()
        extractor = LLMExtractor(client=client)
        entities, relations = extractor._parse_response("无效文本", "通用", "doc1")
        assert entities == []
        assert relations == []


# ===================================================================
# pipeline.py 测试
# ===================================================================


class TestPipeline:
    """管道端到端测试（skip_llm 模式）。"""

    def test_run_pipeline_skip_llm(self, tmp_path: Path) -> None:
        """skip_llm 模式下管道正常运行并输出文件。"""
        from entity_extraction.pipeline import run_pipeline

        output_dir = tmp_path / "kg_output"
        graph = run_pipeline(skip_llm=True, output_dir=output_dir)

        # 检查实体和关系数量
        assert len(graph.entities) >= 100
        assert len(graph.relations) >= 50

        # 检查输出文件
        assert (output_dir / "entities.json").exists()
        assert (output_dir / "relations.json").exists()
        assert (output_dir / "knowledge_graph.json").exists()
        assert (output_dir / "extraction_report.md").exists()

    def test_pipeline_entities_have_ids(self, tmp_path: Path) -> None:
        """管道输出的实体都有 ID。"""
        from entity_extraction.pipeline import run_pipeline

        output_dir = tmp_path / "kg_output"
        graph = run_pipeline(skip_llm=True, output_dir=output_dir)

        for e in graph.entities:
            assert e.id, f"实体 '{e.name}' 缺少 ID"

    def test_pipeline_relations_have_ids(self, tmp_path: Path) -> None:
        """管道输出的关系都有 ID。"""
        from entity_extraction.pipeline import run_pipeline

        output_dir = tmp_path / "kg_output"
        graph = run_pipeline(skip_llm=True, output_dir=output_dir)

        for r in graph.relations:
            assert r.id, "关系缺少 ID"

    def test_pipeline_metadata(self, tmp_path: Path) -> None:
        """管道输出包含元信息。"""
        from entity_extraction.pipeline import run_pipeline

        output_dir = tmp_path / "kg_output"
        graph = run_pipeline(skip_llm=True, output_dir=output_dir)

        assert "generated_at" in graph.metadata
        assert graph.metadata["skip_llm"] is True
        assert "entity_type_distribution" in graph.metadata

    def test_pipeline_output_json_valid(self, tmp_path: Path) -> None:
        """输出的 JSON 文件可被正确解析。"""
        from entity_extraction.pipeline import run_pipeline

        output_dir = tmp_path / "kg_output"
        run_pipeline(skip_llm=True, output_dir=output_dir)

        entities_data = json.loads(
            (output_dir / "entities.json").read_text(encoding="utf-8")
        )
        assert isinstance(entities_data, list)
        assert len(entities_data) > 0

        relations_data = json.loads(
            (output_dir / "relations.json").read_text(encoding="utf-8")
        )
        assert isinstance(relations_data, list)
