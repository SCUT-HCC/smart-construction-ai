"""K21 数据模型 — 实体、关系、知识图谱

定义知识图谱的核心数据结构，用于规则解析和 LLM 抽取的统一输出。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 实体类型常量
# ---------------------------------------------------------------------------
EntityType = Literal[
    "process",  # 施工工序/作业活动
    "equipment",  # 施工设备/工具
    "hazard",  # 危险源/危险因素
    "safety_measure",  # 安全措施/控制手段
    "quality_point",  # 质量控制要点
]

# ---------------------------------------------------------------------------
# 关系类型常量
# ---------------------------------------------------------------------------
RelationType = Literal[
    "requires_equipment",  # 工序 → 需要 → 设备
    "produces_hazard",  # 工序 → 产生 → 危险源
    "mitigated_by",  # 危险源 → 对应 → 安全措施
    "requires_quality_check",  # 工序 → 要求 → 质量要点
]

# 关系类型的中文描述（用于报告）
RELATION_TYPE_LABELS: dict[str, str] = {
    "requires_equipment": "工序→设备",
    "produces_hazard": "工序→危险源",
    "mitigated_by": "危险源→安全措施",
    "requires_quality_check": "工序→质量要点",
}


class Entity(BaseModel):
    """知识图谱实体。

    Args:
        id: 唯一标识，格式 "{type}_{eng_abbr}_{seq:03d}"
        type: 实体类型
        name: 标准化名称
        aliases: 同义词列表
        engineering_type: 工程类型（变电土建/变电电气/线路塔基/特殊作业/通用）
        attributes: 附加属性（参数、等级等）
        source: 来源标识（rule / llm）
        confidence: 置信度 0.0-1.0
    """

    id: str = ""
    type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)
    engineering_type: str = "通用"
    attributes: dict[str, str] = Field(default_factory=dict)
    source: str = "rule"
    confidence: float = 1.0


class Relation(BaseModel):
    """知识图谱关系三元组。

    Args:
        id: 唯一标识，格式 "rel_{seq:04d}"
        source_entity_id: 起点实体 ID
        target_entity_id: 终点实体 ID
        relation_type: 关系类型
        confidence: 置信度 0.0-1.0
        evidence: 原文证据片段
        source_doc: 来源文档/文件路径
    """

    id: str = ""
    source_entity_id: str
    target_entity_id: str
    relation_type: RelationType
    confidence: float = 1.0
    evidence: str = ""
    source_doc: str = ""


class KnowledgeGraph(BaseModel):
    """完整知识图谱，包含所有实体和关系。

    Args:
        entities: 实体列表
        relations: 关系三元组列表
        metadata: 统计元信息
    """

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def entity_by_name(
        self, name: str, entity_type: EntityType | None = None
    ) -> Entity | None:
        """按名称查找实体（精确匹配）。

        Args:
            name: 实体名称
            entity_type: 可选类型过滤

        Returns:
            匹配的实体，未找到返回 None
        """
        for e in self.entities:
            if e.name == name and (entity_type is None or e.type == entity_type):
                return e
        return None

    def find_entity(
        self,
        name: str,
        entity_type: EntityType | None = None,
        engineering_type: str | None = None,
    ) -> Entity | None:
        """按名称查找实体，支持别名匹配。

        Args:
            name: 实体名称或别名
            entity_type: 可选类型过滤
            engineering_type: 可选工程类型过滤

        Returns:
            匹配的实体，未找到返回 None
        """
        for e in self.entities:
            if entity_type and e.type != entity_type:
                continue
            if engineering_type and e.engineering_type not in (
                engineering_type,
                "通用",
            ):
                continue
            if e.name == name or name in e.aliases:
                return e
        return None
