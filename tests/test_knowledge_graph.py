"""K22 知识图谱模块单元测试。

覆盖 converter.py、builder.py、retriever.py 的核心逻辑。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import networkx as nx
import numpy as np
import pytest

from knowledge_graph.converter import (
    _build_chunks,
    _build_entity_description,
    _convert_entities,
    _convert_relationships,
    convert_k21_to_lightrag,
)
from knowledge_graph.builder import _fallback_embedding, create_rag_instance
from knowledge_graph.retriever import KGRetriever, ProcessRequirements


# ═══════════════════════════════════════════════════════════════
# 测试 Fixture
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_entities() -> list[dict]:
    """K21 格式的样本实体。"""
    return [
        {
            "id": "process_001",
            "type": "process",
            "name": "钢筋绑扎",
            "engineering_type": "土建",
            "attributes": {"工序阶段": "主体施工"},
            "aliases": ["扎筋", "钢筋安装"],
            "source": "rule",
            "confidence": 1.0,
        },
        {
            "id": "equipment_001",
            "type": "equipment",
            "name": "塔吊",
            "engineering_type": "通用",
            "attributes": {},
            "aliases": [],
            "source": "rule",
            "confidence": 0.9,
        },
        {
            "id": "hazard_001",
            "type": "hazard",
            "name": "高处坠落",
            "engineering_type": "通用",
            "attributes": {"风险等级": "重大"},
            "aliases": ["坠落"],
            "source": "llm",
            "confidence": 0.8,
        },
        {
            "id": "safety_001",
            "type": "safety_measure",
            "name": "佩戴安全带",
            "engineering_type": "通用",
            "attributes": {},
            "aliases": [],
            "source": "rule",
            "confidence": 1.0,
        },
        {
            "id": "quality_001",
            "type": "quality_point",
            "name": "钢筋间距检查",
            "engineering_type": "土建",
            "attributes": {},
            "aliases": [],
            "source": "rule",
            "confidence": 1.0,
        },
    ]


@pytest.fixture
def sample_relations() -> list[dict]:
    """K21 格式的样本关系。"""
    return [
        {
            "id": "rel_001",
            "source_entity_id": "process_001",
            "target_entity_id": "equipment_001",
            "relation_type": "requires_equipment",
            "confidence": 1.0,
            "evidence": "钢筋绑扎施工需要使用塔吊进行钢筋吊装",
            "source_doc": "doc_01.md",
        },
        {
            "id": "rel_002",
            "source_entity_id": "process_001",
            "target_entity_id": "hazard_001",
            "relation_type": "produces_hazard",
            "confidence": 0.9,
            "evidence": "高处作业绑扎钢筋存在坠落风险",
            "source_doc": "doc_01.md",
        },
        {
            "id": "rel_003",
            "source_entity_id": "hazard_001",
            "target_entity_id": "safety_001",
            "relation_type": "mitigated_by",
            "confidence": 1.0,
            "evidence": "高处坠落 → 佩戴安全带",
            "source_doc": "doc_02.md",
        },
        {
            "id": "rel_004",
            "source_entity_id": "process_001",
            "target_entity_id": "quality_001",
            "relation_type": "requires_quality_check",
            "confidence": 1.0,
            "evidence": "钢筋绑扎完成后需检查钢筋间距",
            "source_doc": "doc_01.md",
        },
    ]


@pytest.fixture
def sample_relations_with_unmapped() -> list[dict]:
    """包含无法映射实体的关系。"""
    return [
        {
            "id": "rel_100",
            "source_entity_id": "不存在的实体",
            "target_entity_id": "equipment_001",
            "relation_type": "requires_equipment",
            "confidence": 1.0,
            "evidence": "某工序需要设备",
            "source_doc": "doc_03.md",
        },
        {
            "id": "rel_101",
            "source_entity_id": "process_001",
            "target_entity_id": "不存在的设备",
            "relation_type": "requires_equipment",
            "confidence": 1.0,
            "evidence": "某工序需要设备",
            "source_doc": "doc_03.md",
        },
    ]


@pytest.fixture
def id_to_name(sample_entities: list[dict]) -> dict[str, str]:
    """实体 ID → 名称映射。"""
    return {e["id"]: e["name"] for e in sample_entities}


@pytest.fixture
def sample_graph() -> nx.Graph:
    """构建一个测试用 NetworkX 图。"""
    g = nx.Graph()
    g.add_node("钢筋绑扎", entity_type="process", description="[施工工序]")
    g.add_node("塔吊", entity_type="equipment", description="[施工设备]")
    g.add_node("高处坠落", entity_type="hazard", description="[危险源]")
    g.add_node("佩戴安全带", entity_type="safety_measure", description="[安全措施]")
    g.add_node(
        "钢筋间距检查", entity_type="quality_point", description="[质量控制要点]"
    )

    g.add_edge("钢筋绑扎", "塔吊", keywords="需要设备,工序设备")
    g.add_edge("钢筋绑扎", "高处坠落", keywords="产生危险源,工序危险")
    g.add_edge("高处坠落", "佩戴安全带", keywords="安全措施,控制措施,风险缓解")
    g.add_edge("钢筋绑扎", "钢筋间距检查", keywords="质量控制,质量要点,质量检查")
    return g


# ═══════════════════════════════════════════════════════════════
# converter.py — _build_entity_description 测试
# ═══════════════════════════════════════════════════════════════


class TestBuildEntityDescription:
    """测试实体描述生成。"""

    def test_full_entity(self, sample_entities: list[dict]) -> None:
        """包含所有字段的实体生成完整描述。"""
        desc = _build_entity_description(sample_entities[0])
        assert "[施工工序]" in desc
        assert "工程类型: 土建" in desc
        assert "工序阶段=主体施工" in desc
        assert "别名: 扎筋, 钢筋安装" in desc
        assert "来源: rule" in desc
        assert "置信度: 1.0" in desc

    def test_generic_engineering_type(self, sample_entities: list[dict]) -> None:
        """通用工程类型不显示工程类型字段。"""
        desc = _build_entity_description(sample_entities[1])
        assert "工程类型" not in desc

    def test_no_attributes(self, sample_entities: list[dict]) -> None:
        """无属性的实体不显示属性字段。"""
        desc = _build_entity_description(sample_entities[1])
        assert "属性" not in desc

    def test_no_aliases(self, sample_entities: list[dict]) -> None:
        """无别名的实体不显示别名字段。"""
        desc = _build_entity_description(sample_entities[1])
        assert "别名" not in desc

    def test_llm_source(self, sample_entities: list[dict]) -> None:
        """LLM 来源和低置信度正确显示。"""
        desc = _build_entity_description(sample_entities[2])
        assert "来源: llm" in desc
        assert "置信度: 0.8" in desc

    def test_entity_type_labels(self) -> None:
        """所有 5 种实体类型都有中文标签。"""
        type_map = {
            "process": "施工工序",
            "equipment": "施工设备",
            "hazard": "危险源",
            "safety_measure": "安全措施",
            "quality_point": "质量控制要点",
        }
        for eng_type, cn_label in type_map.items():
            entity = {"type": eng_type, "source": "rule", "confidence": 1.0}
            desc = _build_entity_description(entity)
            assert f"[{cn_label}]" in desc

    def test_unknown_type_fallback(self) -> None:
        """未知类型回退为原始类型名。"""
        entity = {"type": "unknown_type", "source": "rule", "confidence": 1.0}
        desc = _build_entity_description(entity)
        assert "[unknown_type]" in desc

    def test_aliases_truncated_at_five(self) -> None:
        """别名超过 5 个只显示前 5 个。"""
        entity = {
            "type": "process",
            "aliases": ["a1", "a2", "a3", "a4", "a5", "a6", "a7"],
            "source": "rule",
            "confidence": 1.0,
        }
        desc = _build_entity_description(entity)
        assert "a5" in desc
        assert "a6" not in desc


# ═══════════════════════════════════════════════════════════════
# converter.py — _convert_entities 测试
# ═══════════════════════════════════════════════════════════════


class TestConvertEntities:
    """测试实体转换。"""

    def test_entity_count(self, sample_entities: list[dict]) -> None:
        """转换后实体数量不变。"""
        result = _convert_entities(sample_entities)
        assert len(result) == 5

    def test_entity_format(self, sample_entities: list[dict]) -> None:
        """转换后实体包含 LightRAG 必要字段。"""
        result = _convert_entities(sample_entities)
        for entity in result:
            assert "entity_name" in entity
            assert "entity_type" in entity
            assert "description" in entity
            assert "source_id" in entity

    def test_entity_name_mapping(self, sample_entities: list[dict]) -> None:
        """实体名称正确映射。"""
        result = _convert_entities(sample_entities)
        names = [e["entity_name"] for e in result]
        assert "钢筋绑扎" in names
        assert "塔吊" in names

    def test_source_id_is_original_id(self, sample_entities: list[dict]) -> None:
        """source_id 保留原始 K21 实体 ID。"""
        result = _convert_entities(sample_entities)
        ids = [e["source_id"] for e in result]
        assert "process_001" in ids

    def test_empty_entities(self) -> None:
        """空输入返回空列表。"""
        assert _convert_entities([]) == []


# ═══════════════════════════════════════════════════════════════
# converter.py — _convert_relationships 测试
# ═══════════════════════════════════════════════════════════════


class TestConvertRelationships:
    """测试关系转换。"""

    def test_basic_conversion(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """正常关系全部转换。"""
        result, skipped = _convert_relationships(sample_relations, id_to_name)
        assert len(result) == 4
        assert skipped == 0

    def test_relationship_format(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """转换后关系包含 LightRAG 必要字段。"""
        result, _ = _convert_relationships(sample_relations, id_to_name)
        for rel in result:
            assert "src_id" in rel
            assert "tgt_id" in rel
            assert "description" in rel
            assert "keywords" in rel
            assert "weight" in rel
            assert "source_id" in rel

    def test_src_tgt_are_names(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """src_id/tgt_id 是实体名称而非 ID。"""
        result, _ = _convert_relationships(sample_relations, id_to_name)
        src_names = {r["src_id"] for r in result}
        assert "钢筋绑扎" in src_names
        assert "process_001" not in src_names

    def test_keywords_from_config(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """关系类型正确映射为中文关键词。"""
        result, _ = _convert_relationships(sample_relations, id_to_name)
        equip_rel = [
            r for r in result if r["src_id"] == "钢筋绑扎" and r["tgt_id"] == "塔吊"
        ]
        assert len(equip_rel) == 1
        assert "设备" in equip_rel[0]["keywords"]

    def test_evidence_as_description(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """有证据时使用证据作为描述。"""
        result, _ = _convert_relationships(sample_relations, id_to_name)
        assert result[0]["description"] == "钢筋绑扎施工需要使用塔吊进行钢筋吊装"

    def test_no_evidence_fallback(self, id_to_name: dict[str, str]) -> None:
        """无证据时生成默认描述。"""
        relations = [
            {
                "id": "rel_x",
                "source_entity_id": "process_001",
                "target_entity_id": "equipment_001",
                "relation_type": "requires_equipment",
                "confidence": 1.0,
                "source_doc": "doc.md",
            }
        ]
        result, _ = _convert_relationships(relations, id_to_name)
        assert "→" in result[0]["description"]

    def test_skip_unmapped_source(
        self,
        sample_relations_with_unmapped: list[dict],
        id_to_name: dict[str, str],
    ) -> None:
        """源实体无法映射时跳过。"""
        result, skipped = _convert_relationships(
            sample_relations_with_unmapped, id_to_name
        )
        assert skipped == 2
        assert len(result) == 0

    def test_weight_from_confidence(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """权重来自关系置信度。"""
        result, _ = _convert_relationships(sample_relations, id_to_name)
        hazard_rel = [r for r in result if r["tgt_id"] == "高处坠落"]
        assert hazard_rel[0]["weight"] == 0.9

    def test_empty_relations(self, id_to_name: dict[str, str]) -> None:
        """空关系列表返回空结果。"""
        result, skipped = _convert_relationships([], id_to_name)
        assert result == []
        assert skipped == 0


# ═══════════════════════════════════════════════════════════════
# converter.py — _build_chunks 测试
# ═══════════════════════════════════════════════════════════════


class TestBuildChunks:
    """测试 chunk 构建。"""

    def test_group_by_source_doc(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """按 source_doc 分组。"""
        chunks = _build_chunks(sample_relations, id_to_name)
        source_ids = {c["source_id"] for c in chunks}
        assert "doc_01.md" in source_ids
        assert "doc_02.md" in source_ids

    def test_chunk_format(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """chunk 包含 LightRAG 必要字段。"""
        chunks = _build_chunks(sample_relations, id_to_name)
        for chunk in chunks:
            assert "content" in chunk
            assert "source_id" in chunk
            assert "source_chunk_index" in chunk

    def test_chunk_content_contains_evidence(
        self, sample_relations: list[dict], id_to_name: dict[str, str]
    ) -> None:
        """chunk 内容包含证据文本。"""
        chunks = _build_chunks(sample_relations, id_to_name)
        doc01_chunk = [c for c in chunks if c["source_id"] == "doc_01.md"]
        assert len(doc01_chunk) == 1
        assert "钢筋绑扎" in doc01_chunk[0]["content"]
        assert "塔吊" in doc01_chunk[0]["content"]

    def test_skip_empty_evidence(self, id_to_name: dict[str, str]) -> None:
        """无证据的关系不产生 chunk。"""
        relations = [
            {
                "id": "rel_x",
                "source_entity_id": "process_001",
                "target_entity_id": "equipment_001",
                "relation_type": "requires_equipment",
                "source_doc": "doc.md",
            }
        ]
        chunks = _build_chunks(relations, id_to_name)
        assert chunks == []

    def test_empty_relations(self, id_to_name: dict[str, str]) -> None:
        """空关系返回空 chunk。"""
        assert _build_chunks([], id_to_name) == []


# ═══════════════════════════════════════════════════════════════
# converter.py — convert_k21_to_lightrag 集成测试
# ═══════════════════════════════════════════════════════════════


class TestConvertK21ToLightrag:
    """测试端到端转换。"""

    def test_integration(
        self, sample_entities: list[dict], sample_relations: list[dict], tmp_path: Path
    ) -> None:
        """端到端转换产生正确结构。"""
        entities_path = tmp_path / "entities.json"
        relations_path = tmp_path / "relations.json"
        entities_path.write_text(json.dumps(sample_entities), encoding="utf-8")
        relations_path.write_text(json.dumps(sample_relations), encoding="utf-8")

        result = convert_k21_to_lightrag(entities_path, relations_path)

        assert "entities" in result
        assert "relationships" in result
        assert "chunks" in result
        assert len(result["entities"]) == 5
        assert len(result["relationships"]) == 4
        assert len(result["chunks"]) >= 1

    def test_output_keys(
        self, sample_entities: list[dict], sample_relations: list[dict], tmp_path: Path
    ) -> None:
        """输出字典包含且仅包含三个键。"""
        entities_path = tmp_path / "entities.json"
        relations_path = tmp_path / "relations.json"
        entities_path.write_text(json.dumps(sample_entities), encoding="utf-8")
        relations_path.write_text(json.dumps(sample_relations), encoding="utf-8")

        result = convert_k21_to_lightrag(entities_path, relations_path)
        assert set(result.keys()) == {"entities", "relationships", "chunks"}


# ═══════════════════════════════════════════════════════════════
# builder.py — _fallback_embedding 测试
# ═══════════════════════════════════════════════════════════════


class TestFallbackEmbedding:
    """测试回退嵌入函数。"""

    def test_output_shape(self) -> None:
        """输出形状为 (N, EMBEDDING_DIM)。"""
        texts = ["hello", "world"]
        result = _fallback_embedding(texts)
        assert result.shape[0] == 2
        assert result.shape[1] > 0

    def test_normalized(self) -> None:
        """向量已归一化。"""
        result = _fallback_embedding(["test text"])
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 1e-5

    def test_deterministic(self) -> None:
        """相同文本产生相同嵌入。"""
        r1 = _fallback_embedding(["钢筋绑扎"])
        r2 = _fallback_embedding(["钢筋绑扎"])
        np.testing.assert_array_equal(r1, r2)

    def test_different_texts_different_embeddings(self) -> None:
        """不同文本产生不同嵌入。"""
        result = _fallback_embedding(["文本A", "文本B"])
        assert not np.allclose(result[0], result[1])

    def test_empty_input(self) -> None:
        """空输入返回空矩阵。"""
        result = _fallback_embedding([])
        assert result.shape[0] == 0


# ═══════════════════════════════════════════════════════════════
# builder.py — create_rag_instance 测试
# ═══════════════════════════════════════════════════════════════


class TestCreateRagInstance:
    """测试 LightRAG 实例创建。"""

    def test_creates_working_dir(self, tmp_path: Path) -> None:
        """自动创建工作目录。"""
        work_dir = tmp_path / "lightrag_test"
        rag = create_rag_instance(work_dir)
        assert work_dir.exists()
        assert rag is not None

    def test_existing_dir_ok(self, tmp_path: Path) -> None:
        """已存在的目录不报错。"""
        work_dir = tmp_path / "existing"
        work_dir.mkdir()
        rag = create_rag_instance(work_dir)
        assert rag is not None


# ═══════════════════════════════════════════════════════════════
# retriever.py — ProcessRequirements 测试
# ═══════════════════════════════════════════════════════════════


class TestProcessRequirements:
    """测试推理结果数据类。"""

    def test_default_values(self) -> None:
        """默认值为空列表/字典。"""
        pr = ProcessRequirements(process_name="测试工序")
        assert pr.equipment == []
        assert pr.hazards == []
        assert pr.safety_measures == {}
        assert pr.quality_points == []

    def test_to_dict(self) -> None:
        """转换为字典。"""
        pr = ProcessRequirements(
            process_name="钢筋绑扎",
            equipment=["塔吊"],
            hazards=["高处坠落"],
            safety_measures={"高处坠落": ["佩戴安全带"]},
            quality_points=["钢筋间距检查"],
        )
        d = pr.to_dict()
        assert d["process_name"] == "钢筋绑扎"
        assert "塔吊" in d["equipment"]
        assert d["safety_measures"]["高处坠落"] == ["佩戴安全带"]


# ═══════════════════════════════════════════════════════════════
# retriever.py — KGRetriever 图遍历测试
# ═══════════════════════════════════════════════════════════════


class TestKGRetriever:
    """测试知识图谱推理器的图遍历功能。"""

    @pytest.fixture
    def retriever(self, sample_graph: nx.Graph) -> KGRetriever:
        """创建带测试图的推理器。"""
        rag = MagicMock()
        storage = MagicMock()
        storage._graph = sample_graph
        rag.chunk_entity_relation_graph = storage

        return KGRetriever(rag)

    def test_get_neighbors_all(self, retriever: KGRetriever) -> None:
        """获取所有邻居。"""
        neighbors = retriever.get_neighbors("钢筋绑扎")
        assert len(neighbors) == 3
        assert "塔吊" in neighbors
        assert "高处坠落" in neighbors
        assert "钢筋间距检查" in neighbors

    def test_get_neighbors_filtered(self, retriever: KGRetriever) -> None:
        """按关系类型过滤邻居。"""
        neighbors = retriever.get_neighbors("钢筋绑扎", relation_type="设备")
        assert "塔吊" in neighbors
        assert "高处坠落" not in neighbors

    def test_get_neighbors_not_found(self, retriever: KGRetriever) -> None:
        """不存在的实体返回空。"""
        neighbors = retriever.get_neighbors("不存在的工序")
        assert neighbors == []

    def test_infer_process_chain(self, retriever: KGRetriever) -> None:
        """推理工序完整要求链。"""
        result = retriever.infer_process_chain("钢筋绑扎")
        assert result.process_name == "钢筋绑扎"
        assert "塔吊" in result.equipment
        assert "高处坠落" in result.hazards
        assert "佩戴安全带" in result.safety_measures.get("高处坠落", [])
        assert "钢筋间距检查" in result.quality_points

    def test_infer_process_chain_not_found(self, retriever: KGRetriever) -> None:
        """不存在的工序返回空结果。"""
        result = retriever.infer_process_chain("不存在的工序")
        assert result.equipment == []
        assert result.hazards == []
        assert result.quality_points == []

    def test_infer_hazard_measures(self, retriever: KGRetriever) -> None:
        """推理危险源安全措施。"""
        measures = retriever.infer_hazard_measures("高处坠落")
        assert "佩戴安全带" in measures

    def test_infer_hazard_measures_not_found(
        self, retriever: KGRetriever
    ) -> None:
        """不存在的危险源返回空。"""
        measures = retriever.infer_hazard_measures("不存在的危险源")
        assert measures == []

    def test_get_all_entities(self, retriever: KGRetriever) -> None:
        """获取全部实体。"""
        entities = retriever.get_all_entities()
        assert len(entities) == 5
        names = {e["name"] for e in entities}
        assert "钢筋绑扎" in names

    def test_get_all_entities_filtered(self, retriever: KGRetriever) -> None:
        """按类型过滤实体。"""
        entities = retriever.get_all_entities(entity_type="hazard")
        assert len(entities) == 1
        assert entities[0]["name"] == "高处坠落"

    def test_get_all_entities_empty_type(self, retriever: KGRetriever) -> None:
        """不存在的类型返回空。"""
        entities = retriever.get_all_entities(entity_type="nonexistent")
        assert entities == []

    def test_get_graph_stats(self, retriever: KGRetriever) -> None:
        """图谱统计信息。"""
        stats = retriever.get_graph_stats()
        assert stats["nodes"] == 5
        assert stats["edges"] == 4

    def test_find_node_exists(self, retriever: KGRetriever) -> None:
        """存在的节点直接返回。"""
        assert retriever._find_node("钢筋绑扎") == "钢筋绑扎"

    def test_find_node_not_exists(self, retriever: KGRetriever) -> None:
        """不存在的节点返回 None。"""
        assert retriever._find_node("不存在") is None


# ═══════════════════════════════════════════════════════════════
# retriever.py — 无图场景测试
# ═══════════════════════════════════════════════════════════════


class TestKGRetrieverNoGraph:
    """测试无图或空图时的降级行为。"""

    def test_no_graph_attribute(self) -> None:
        """storage 无 _graph 属性时创建空图。"""
        rag = MagicMock()
        rag.chunk_entity_relation_graph = MagicMock(spec=[])
        retriever = KGRetriever(rag)
        assert retriever.get_graph_stats() == {"nodes": 0, "edges": 0}

    def test_empty_graph(self) -> None:
        """空图返回空结果。"""
        rag = MagicMock()
        storage = MagicMock()
        storage._graph = nx.Graph()
        rag.chunk_entity_relation_graph = storage

        retriever = KGRetriever(rag)
        assert retriever.get_neighbors("任意") == []
        assert retriever.get_all_entities() == []
