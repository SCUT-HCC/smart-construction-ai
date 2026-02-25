"""S10 统一检索接口 — 协调 VectorRetriever + KGRetriever

融合策略优先级：
1. KG 推理 → 强制规范 (priority=1)
2. 向量检索 → 参考案例 (priority=2)
3. 模板 → 通用框架 (priority=3)
"""

from __future__ import annotations

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
from utils.logger_system import log_msg
from vector_store.retriever import VectorRetriever


class KnowledgeRetriever:
    """统一检索接口，协调 VectorRetriever + KGRetriever。

    对外暴露三个专用方法和一个统一入口：
    - retrieve_regulations(): 从 KG 检索强制规范
    - retrieve_cases(): 从 qmd 检索案例片段
    - infer_rules(): KG 推理（工序→危险源→措施链）
    - retrieve(): 统一检索入口，内部协调双引擎

    Args:
        vector_retriever: 向量检索器（qmd 案例检索）
        kg_retriever: 知识图谱推理器（LightRAG 规则推理）
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        kg_retriever: KGRetriever | None = None,
    ) -> None:
        self._vector = vector_retriever
        self._kg = kg_retriever

    def retrieve(
        self,
        query: str,
        chapter: str | None = None,
        engineering_type: str | None = None,
        processes: list[str] | None = None,
    ) -> RetrievalResponse:
        """统一检索入口，内部协调双引擎，按融合策略排序合并。

        流程：
        1. 判断章节是否需要 KG 推理 → 提取强制规范
        2. 向量检索案例片段
        3. 按 (priority ASC, score DESC) 合并排序
        4. 封装 RetrievalResponse 返回

        Args:
            query: 查询文本
            chapter: 目标章节 collection 名称（如 "ch07_quality"）
            engineering_type: 工程类型过滤（如 "变电土建"）
            processes: 工序名称列表（用于 KG 推理）

        Returns:
            RetrievalResponse 统一检索响应
        """
        regulations: list[RetrievalItem] = []
        cases: list[RetrievalItem] = []

        # 1. KG 推理：需要 KG 的章节且有 KG 引擎
        if self._kg and _chapter_needs_kg(chapter):
            regulations = self.retrieve_regulations(
                engineering_type=engineering_type,
                processes=processes,
            )

        # 2. 向量检索
        if self._vector:
            cases = self.retrieve_cases(
                query=query,
                chapter=chapter,
                engineering_type=engineering_type,
            )

        # 3. 合并排序
        all_items = _merge_and_sort(regulations + cases)

        # 4. 封装响应
        return RetrievalResponse(
            items=all_items,
            regulations=[i for i in all_items if i.source == "kg_rule"],
            cases=[i for i in all_items if i.source in ("vector", "template")],
            query_context={
                "query": query,
                "chapter": chapter,
                "engineering_type": engineering_type,
                "processes": processes,
            },
        )

    def retrieve_regulations(
        self,
        engineering_type: str | None = None,
        processes: list[str] | None = None,
    ) -> list[RetrievalItem]:
        """从 KG 检索强制规范。

        遍历每个工序，推理完整要求链（设备/危险源/安全措施/质量要点），
        将 ProcessRequirements 转换为 RetrievalItem。

        Args:
            engineering_type: 工程类型（预留，当前未使用）
            processes: 工序名称列表

        Returns:
            强制规范 RetrievalItem 列表 (priority=1)
        """
        if not self._kg:
            log_msg("WARNING", "KG 引擎未初始化，跳过规范检索")
            return []

        if not processes:
            return []

        items: list[RetrievalItem] = []
        for process_name in processes:
            req = self._kg.infer_process_chain(process_name)
            items.extend(_process_requirements_to_items(req))

        return items

    def retrieve_cases(
        self,
        query: str,
        chapter: str | None = None,
        engineering_type: str | None = None,
        limit: int = DEFAULT_VECTOR_TOP_K,
        threshold: float = DEFAULT_VECTOR_THRESHOLD,
    ) -> list[RetrievalItem]:
        """从 qmd 检索案例片段。

        调用 VectorRetriever.search()，将 RetrievalResult 转换为 RetrievalItem。
        templates collection 的结果优先级降为 PRIORITY_TEMPLATE。

        Args:
            query: 查询文本
            chapter: 目标章节 collection
            engineering_type: 工程类型过滤
            limit: 返回结果数量上限
            threshold: 相似度阈值

        Returns:
            案例片段 RetrievalItem 列表
        """
        if not self._vector:
            log_msg("WARNING", "向量引擎未初始化，跳过案例检索")
            return []

        raw_results = self._vector.search(
            query=query,
            collection=chapter,
            engineering_type=engineering_type,
            limit=limit,
            threshold=threshold,
        )

        items: list[RetrievalItem] = []
        for r in raw_results:
            is_template = r.collection == TEMPLATE_COLLECTION
            items.append(
                RetrievalItem(
                    content=r.content,
                    source="template" if is_template else "vector",
                    priority=PRIORITY_TEMPLATE if is_template else PRIORITY_VECTOR_CASE,
                    score=r.score,
                    metadata={
                        "collection": r.collection,
                        "file_id": r.file_id,
                        "context": r.context,
                    },
                )
            )

        return items

    def infer_rules(
        self,
        context: str,
        processes: list[str] | None = None,
    ) -> list[RetrievalItem]:
        """LightRAG 推理（工序→危险源→措施链）。

        MVP 阶段仅使用图遍历（毫秒级），不调用 LLM。

        Args:
            context: 上下文描述（预留，当前未使用）
            processes: 工序名称列表

        Returns:
            推理结果 RetrievalItem 列表 (priority=1)
        """
        if not self._kg:
            log_msg("WARNING", "KG 引擎未初始化，跳过规则推理")
            return []

        if not processes:
            return []

        items: list[RetrievalItem] = []
        for process_name in processes:
            req = self._kg.infer_process_chain(process_name)
            items.extend(_process_requirements_to_items(req))

        return items

    def close(self) -> None:
        """释放双引擎资源。"""
        if self._vector:
            self._vector.close()
            self._vector = None
        # KGRetriever 无需显式关闭
        self._kg = None


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _chapter_needs_kg(chapter: str | None) -> bool:
    """判断章节是否需要 KG 推理。

    Args:
        chapter: 章节 collection 名称

    Returns:
        是否需要 KG 推理
    """
    if chapter is None:
        return True  # 未指定章节时默认启用 KG
    return chapter in CHAPTERS_NEED_KG


def _merge_and_sort(items: list[RetrievalItem]) -> list[RetrievalItem]:
    """按融合策略排序：priority ASC → score DESC。

    Args:
        items: 待排序的检索结果

    Returns:
        排序后的结果列表（新列表，不修改原列表）
    """
    return sorted(items, key=lambda x: (x.priority, -x.score))


def _process_requirements_to_items(
    req: ProcessRequirements,
) -> list[RetrievalItem]:
    """将 ProcessRequirements 转换为 RetrievalItem 列表。

    为每种要求（设备、危险源+措施、质量要点）生成独立的检索条目。

    Args:
        req: 工序要求链推理结果

    Returns:
        RetrievalItem 列表 (source="kg_rule", priority=1)
    """
    items: list[RetrievalItem] = []
    process = req.process_name

    # 设备要求
    if req.equipment:
        items.append(
            RetrievalItem(
                content=f"工序「{process}」需要设备：{'、'.join(req.equipment)}",
                source="kg_rule",
                priority=PRIORITY_KG_RULE,
                score=1.0,
                metadata={
                    "process_name": process,
                    "rule_type": "equipment",
                    "equipment": req.equipment,
                },
            )
        )

    # 危险源 + 安全措施
    for hazard in req.hazards:
        measures = req.safety_measures.get(hazard, [])
        content_parts = [f"工序「{process}」存在危险源：{hazard}"]
        if measures:
            content_parts.append(f"安全措施：{'、'.join(measures)}")
        items.append(
            RetrievalItem(
                content="。".join(content_parts),
                source="kg_rule",
                priority=PRIORITY_KG_RULE,
                score=1.0,
                metadata={
                    "process_name": process,
                    "rule_type": "hazard_measure",
                    "hazard": hazard,
                    "measures": measures,
                },
            )
        )

    # 质量要点
    if req.quality_points:
        items.append(
            RetrievalItem(
                content=f"工序「{process}」质量要点：{'、'.join(req.quality_points)}",
                source="kg_rule",
                priority=PRIORITY_KG_RULE,
                score=1.0,
                metadata={
                    "process_name": process,
                    "rule_type": "quality",
                    "quality_points": req.quality_points,
                },
            )
        )

    return items
