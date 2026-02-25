"""K22 推理接口 — 图遍历推理 + LLM 增强查询

提供两种查询方式：
1. 图遍历推理（毫秒级，不依赖 LLM，直接遍历 NetworkX 图）
2. LLM 增强查询（秒级，通过 LightRAG 的 aquery 接口）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
from lightrag import LightRAG, QueryParam

from knowledge_graph.builder import create_rag_instance
from knowledge_graph.config import LIGHTRAG_WORKING_DIR
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# 推理结果数据类
# ---------------------------------------------------------------------------


@dataclass
class ProcessRequirements:
    """工序的完整要求链推理结果。"""

    process_name: str
    equipment: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    safety_measures: dict[str, list[str]] = field(default_factory=dict)
    quality_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "process_name": self.process_name,
            "equipment": self.equipment,
            "hazards": self.hazards,
            "safety_measures": self.safety_measures,
            "quality_points": self.quality_points,
        }


# ---------------------------------------------------------------------------
# 推理器
# ---------------------------------------------------------------------------


class KnowledgeRetriever:
    """知识图谱推理器，封装 LightRAG 实例。

    提供图遍历推理（快速、结构化）和 LLM 查询（自然语言）两种接口。

    Args:
        rag: LightRAG 实例（已初始化并导入数据）
    """

    def __init__(self, rag: LightRAG) -> None:
        self._rag = rag
        self._graph = self._get_graph()

    @classmethod
    async def from_storage(
        cls, working_dir: Path | None = None
    ) -> "KnowledgeRetriever":
        """从已持久化的 LightRAG 存储加载。

        Args:
            working_dir: LightRAG 工作目录

        Returns:
            KnowledgeRetriever 实例
        """
        working_dir = working_dir or LIGHTRAG_WORKING_DIR
        rag = create_rag_instance(working_dir)
        await rag.initialize_storages()
        return cls(rag)

    @classmethod
    def from_storage_sync(cls, working_dir: Path | None = None) -> "KnowledgeRetriever":
        """同步版本的 from_storage。

        Args:
            working_dir: LightRAG 工作目录

        Returns:
            KnowledgeRetriever 实例
        """
        return asyncio.run(cls.from_storage(working_dir))

    # -------------------------------------------------------------------
    # 图遍历推理（不依赖 LLM，毫秒级）
    # -------------------------------------------------------------------

    def _get_graph(self) -> nx.Graph:
        """获取底层 NetworkX 图。

        Returns:
            NetworkX 图实例
        """
        storage = self._rag.chunk_entity_relation_graph
        if hasattr(storage, "_graph"):
            return storage._graph
        log_msg("WARNING", "无法获取 NetworkX 图，图遍历功能不可用")
        return nx.Graph()

    def get_neighbors(
        self,
        entity_name: str,
        relation_type: str | None = None,
    ) -> list[str]:
        """获取实体的邻居节点。

        Args:
            entity_name: 实体名称
            relation_type: 可选，过滤关系类型

        Returns:
            邻居实体名称列表
        """
        node = self._find_node(entity_name)
        if not node:
            return []

        neighbors: list[str] = []
        for neighbor in self._graph.neighbors(node):
            edge_data = self._graph.edges[node, neighbor]
            if relation_type:
                keywords = edge_data.get("keywords", "")
                if relation_type not in keywords:
                    continue
            neighbors.append(neighbor)

        return neighbors

    def infer_process_chain(self, process_name: str) -> ProcessRequirements:
        """推理工序的完整要求链。

        遍历图谱，找出工序相关的设备、危险源、安全措施和质量要点。

        Args:
            process_name: 工序名称

        Returns:
            ProcessRequirements 推理结果
        """
        result = ProcessRequirements(process_name=process_name)

        # 获取所有邻居
        entity_key = self._find_node(process_name)
        if not entity_key:
            return result

        for neighbor in self._graph.neighbors(entity_key):
            edge_data = self._graph.edges[entity_key, neighbor]
            keywords = edge_data.get("keywords", "")
            neighbor_name = neighbor.strip('"')

            if "设备" in keywords:
                result.equipment.append(neighbor_name)
            elif "危险" in keywords:
                result.hazards.append(neighbor_name)
                # 继续推理：危险源 → 安全措施
                measures = self._get_safety_measures(neighbor)
                if measures:
                    result.safety_measures[neighbor_name] = measures
            elif "质量" in keywords:
                result.quality_points.append(neighbor_name)

        return result

    def infer_hazard_measures(self, hazard_name: str) -> list[str]:
        """推理危险源对应的安全措施。

        Args:
            hazard_name: 危险源名称

        Returns:
            安全措施名称列表
        """
        node = self._find_node(hazard_name)
        if not node:
            return []
        return self._get_safety_measures(node)

    def get_all_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        """获取所有实体（可按类型过滤）。

        Args:
            entity_type: 可选实体类型过滤

        Returns:
            实体信息列表
        """
        entities: list[dict[str, Any]] = []
        for node, data in self._graph.nodes(data=True):
            node_type = data.get("entity_type", "")
            if entity_type and node_type != entity_type:
                continue
            entities.append(
                {
                    "name": node.strip('"'),
                    "type": node_type,
                    "description": data.get("description", ""),
                }
            )
        return entities

    def get_graph_stats(self) -> dict[str, int]:
        """获取图谱统计信息。

        Returns:
            统计字典
        """
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
        }

    # -------------------------------------------------------------------
    # LLM 增强查询（秒级）
    # -------------------------------------------------------------------

    async def aquery(
        self,
        question: str,
        mode: str = "hybrid",
    ) -> str:
        """通过 LightRAG 进行 LLM 增强查询。

        Args:
            question: 自然语言问题
            mode: 检索模式 (local/global/hybrid/naive/mix)

        Returns:
            LLM 生成的回答
        """
        return await self._rag.aquery(
            question,
            param=QueryParam(mode=mode),
        )

    def query(self, question: str, mode: str = "hybrid") -> str:
        """同步版本的 aquery。

        Args:
            question: 自然语言问题
            mode: 检索模式

        Returns:
            LLM 生成的回答
        """
        return asyncio.run(self.aquery(question, mode))

    # -------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------

    def _find_node(self, name: str) -> str | None:
        """在图中查找节点。

        Args:
            name: 实体名称

        Returns:
            图中的节点 key，未找到返回 None
        """
        if name in self._graph:
            return name
        return None

    def _get_safety_measures(self, hazard_node: str) -> list[str]:
        """获取危险源节点的安全措施邻居。

        Args:
            hazard_node: 危险源的图节点 key

        Returns:
            安全措施名称列表
        """
        measures: list[str] = []
        if hazard_node not in self._graph:
            return measures

        for neighbor in self._graph.neighbors(hazard_node):
            edge_data = self._graph.edges[hazard_node, neighbor]
            keywords = edge_data.get("keywords", "")
            if "措施" in keywords or "缓解" in keywords:
                measures.append(neighbor.strip('"'))

        return measures
