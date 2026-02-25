"""S10 统一数据模型 — RetrievalItem 与 RetrievalResponse"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalItem:
    """统一检索结果条目。

    每个条目携带来源标识和融合优先级，供下游按策略消费。

    Attributes:
        content: 检索内容文本
        source: 来源标识 ("kg_rule" | "vector" | "template")
        priority: 融合优先级 (1=最高, 4=最低)
        score: 相关性评分 (0~1)
        metadata: 附加信息 (collection, file_id, process_name 等)
    """

    content: str
    source: str
    priority: int
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "content": self.content,
            "source": self.source,
            "priority": self.priority,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class RetrievalResponse:
    """统一检索响应。

    包含按融合策略排序的全部结果，以及按来源分类的子集视图。

    Attributes:
        items: 按优先级+评分排序的全部结果
        regulations: 强制规范子集（来自 KG，source=="kg_rule"）
        cases: 参考案例子集（来自向量检索，source=="vector"）
        query_context: 查询上下文 (chapter, engineering_type 等)
    """

    items: list[RetrievalItem] = field(default_factory=list)
    regulations: list[RetrievalItem] = field(default_factory=list)
    cases: list[RetrievalItem] = field(default_factory=list)
    query_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "items": [item.to_dict() for item in self.items],
            "regulations": [item.to_dict() for item in self.regulations],
            "cases": [item.to_dict() for item in self.cases],
            "query_context": self.query_context,
        }
