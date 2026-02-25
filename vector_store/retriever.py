"""K23 检索接口 — 封装 qmd 语义检索，支持按章节/工程类型过滤

提供统一的向量检索 API，供生成系统和审核系统调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import qmd
from qmd import Database, Store
from qmd.llm.base import LLMBackend

from vector_store.config import (
    ALL_COLLECTIONS,
    DB_PATH,
    DEFAULT_THRESHOLD,
    DEFAULT_TOP_K,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)


# ---------------------------------------------------------------------------
# 检索结果
# ---------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    """语义检索结果。"""

    content: str
    score: float
    collection: str
    file_id: str
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "content": self.content,
            "score": self.score,
            "collection": self.collection,
            "file_id": self.file_id,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# 检索器
# ---------------------------------------------------------------------------


class VectorRetriever:
    """向量检索器，封装 qmd 的混合检索功能。

    提供按 collection（章节）和 engineering_type（工程类型）过滤的检索接口。

    Args:
        db: qmd Database 实例
        backend: LLM 后端（用于向量检索和 rerank）
    """

    def __init__(self, db: Database, backend: LLMBackend | None = None) -> None:
        self._db = db
        self._backend = backend

    @classmethod
    def from_storage(
        cls,
        db_path: Path | None = None,
        load_model: bool = True,
    ) -> "VectorRetriever":
        """从已有向量库加载。

        Args:
            db_path: 数据库路径
            load_model: 是否加载嵌入模型（用于向量检索）

        Returns:
            VectorRetriever 实例
        """
        db_path = db_path or DB_PATH
        conn = qmd.open_database(str(db_path))
        db = Database(conn)

        backend = None
        if load_model:
            from qmd.llm.sentence_tf import SentenceTransformerBackend

            backend = SentenceTransformerBackend(
                model_name=EMBEDDING_MODEL,
                device=EMBEDDING_DEVICE,
            )

        return cls(db, backend)

    def search(
        self,
        query: str,
        collection: str | None = None,
        engineering_type: str | None = None,
        limit: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> list[RetrievalResult]:
        """语义检索。

        Args:
            query: 查询文本
            collection: 限定 Collection（章节），None 搜索所有
            engineering_type: 工程类型过滤（如"变电土建"）
            limit: 返回结果数量上限
            threshold: 相似度阈值

        Returns:
            按相关性降序排列的检索结果列表
        """
        # 构建增强查询（包含工程类型提示，提升相关性）
        enhanced_query = query
        if engineering_type:
            enhanced_query = f"[工程类型: {engineering_type}] {query}"

        # 调用 qmd 检索
        raw_results = qmd.search(
            self._db,
            enhanced_query,
            collection=collection,
            limit=limit * 2 if engineering_type else limit,
            llm_backend=self._backend,
        )

        # 转换并过滤
        results: list[RetrievalResult] = []
        for r in raw_results:
            if r.score < threshold:
                continue

            # 工程类型后过滤
            if engineering_type and not _match_engineering_type(
                r.body, engineering_type
            ):
                continue

            results.append(
                RetrievalResult(
                    content=r.body,
                    score=r.score,
                    collection=r.collection,
                    file_id=r.file,
                    context=r.context,
                )
            )

            if len(results) >= limit:
                break

        return results

    def search_multi_collection(
        self,
        query: str,
        collections: list[str],
        engineering_type: str | None = None,
        limit_per_collection: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> dict[str, list[RetrievalResult]]:
        """跨多个 Collection 检索。

        Args:
            query: 查询文本
            collections: Collection 列表
            engineering_type: 工程类型过滤
            limit_per_collection: 每个 Collection 的结果数量上限
            threshold: 相似度阈值

        Returns:
            按 Collection 分组的检索结果
        """
        results: dict[str, list[RetrievalResult]] = {}
        for coll in collections:
            if coll not in ALL_COLLECTIONS:
                continue
            coll_results = self.search(
                query,
                collection=coll,
                engineering_type=engineering_type,
                limit=limit_per_collection,
                threshold=threshold,
            )
            results[coll] = coll_results
        return results

    def get_collection_stats(self) -> dict[str, int]:
        """获取各 Collection 文档数量。

        Returns:
            Collection → 文档数量映射
        """
        store = Store(self._db)
        stats: dict[str, int] = {}
        for coll in ALL_COLLECTIONS:
            stats[coll] = store.get_document_count(coll)
        return stats

    def close(self) -> None:
        """释放资源。"""
        if self._backend:
            self._backend.close()
            self._backend = None


# ---------------------------------------------------------------------------
# 内部方法
# ---------------------------------------------------------------------------


def _match_engineering_type(content: str, engineering_type: str) -> bool:
    """检查内容是否匹配指定工程类型。

    通过检查内容中的元数据前缀来判断。

    Args:
        content: 文档内容
        engineering_type: 目标工程类型

    Returns:
        是否匹配
    """
    # 检查 prepend 的元数据前缀
    prefix_marker = f"[工程类型: {engineering_type}]"
    if prefix_marker in content:
        return True

    # 对于未标记工程类型的内容（如通用模板），也匹配
    if "[工程类型:" not in content:
        return True

    return False
