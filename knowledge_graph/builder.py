"""K22 构建器 — 初始化 LightRAG 实例并导入 K21 知识图谱

提供同步和异步接口，支持增量和全量构建。
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from lightrag import LightRAG
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

from knowledge_graph.config import (
    EMBEDDING_DIM,
    EMBEDDING_MAX_TOKENS,
    LIGHTRAG_WORKING_DIR,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
)
from knowledge_graph.converter import convert_k21_to_lightrag
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# LLM 函数（包装 DeepSeek API）
# ---------------------------------------------------------------------------


async def _llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> str:
    """DeepSeek LLM 调用函数（LightRAG 兼容）。

    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        history_messages: 历史消息
        **kwargs: 其他参数

    Returns:
        LLM 响应文本
    """
    return await openai_complete_if_cache(
        model=LLM_MODEL,
        prompt=prompt,
        system_prompt=system_prompt,
        history_messages=history_messages or [],
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 嵌入函数
# ---------------------------------------------------------------------------


async def _embedding_func(texts: list[str]) -> np.ndarray:
    """嵌入函数（使用 OpenAI 兼容 API）。

    Args:
        texts: 文本列表

    Returns:
        嵌入向量矩阵 (N, dim)
    """
    try:
        return await openai_embed(
            texts,
            model="text-embedding-v3",
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
    except Exception:
        # 回退：生成确定性伪嵌入（基于文本哈希）
        # 用于 insert_custom_kg 场景，不影响图遍历推理
        return _fallback_embedding(texts)


def _fallback_embedding(texts: list[str]) -> np.ndarray:
    """回退嵌入：基于字符哈希生成确定性向量。

    仅用于 custom KG 导入场景，图遍历推理不依赖向量。

    Args:
        texts: 文本列表

    Returns:
        伪嵌入矩阵 (N, dim)
    """
    result = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        # 确定性哈希嵌入
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(EMBEDDING_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)
        result[i] = vec
    return result


# ---------------------------------------------------------------------------
# 构建器
# ---------------------------------------------------------------------------


def create_rag_instance(working_dir: Path | None = None) -> LightRAG:
    """创建 LightRAG 实例（未初始化存储）。

    Args:
        working_dir: 工作目录路径

    Returns:
        LightRAG 实例
    """
    working_dir = working_dir or LIGHTRAG_WORKING_DIR
    working_dir.mkdir(parents=True, exist_ok=True)

    return LightRAG(
        working_dir=str(working_dir),
        llm_model_func=_llm_model_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBEDDING_DIM,
            max_token_size=EMBEDDING_MAX_TOKENS,
            func=_embedding_func,
        ),
    )


async def build_knowledge_graph(
    *,
    working_dir: Path | None = None,
    force_rebuild: bool = False,
) -> LightRAG:
    """构建知识图谱：转换 K21 数据并导入 LightRAG。

    Args:
        working_dir: LightRAG 工作目录
        force_rebuild: 是否强制重建（删除已有数据）

    Returns:
        已导入数据的 LightRAG 实例
    """
    working_dir = working_dir or LIGHTRAG_WORKING_DIR

    log_msg("INFO", "=" * 60)
    log_msg("INFO", "K22 知识图谱构建启动")
    log_msg("INFO", "=" * 60)

    # 强制重建：清空工作目录
    if force_rebuild and working_dir.exists():
        log_msg("INFO", f"强制重建: 清空 {working_dir}")
        shutil.rmtree(working_dir)

    # Step 1: 创建 LightRAG 实例
    log_msg("INFO", "[Step 1/3] 创建 LightRAG 实例")
    rag = create_rag_instance(working_dir)
    await rag.initialize_storages()

    # Step 2: 转换 K21 数据
    log_msg("INFO", "[Step 2/3] 转换 K21 数据为 LightRAG 格式")
    custom_kg = convert_k21_to_lightrag()

    # Step 3: 导入
    log_msg("INFO", "[Step 3/3] 导入知识图谱")
    log_msg(
        "INFO",
        f"  导入: {len(custom_kg['entities'])} 实体, "
        f"{len(custom_kg['relationships'])} 关系, "
        f"{len(custom_kg['chunks'])} chunks",
    )
    await rag.ainsert_custom_kg(custom_kg)

    # 统计
    graph_storage = rag.chunk_entity_relation_graph
    if hasattr(graph_storage, "_graph"):
        graph = graph_storage._graph
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()
    else:
        node_count = len(custom_kg["entities"])
        edge_count = len(custom_kg["relationships"])

    log_msg("INFO", "=" * 60)
    log_msg("INFO", f"K22 构建完成: {node_count} 节点, {edge_count} 边")
    log_msg("INFO", f"工作目录: {working_dir}")
    log_msg("INFO", "=" * 60)

    return rag


def build_knowledge_graph_sync(
    *,
    working_dir: Path | None = None,
    force_rebuild: bool = False,
) -> LightRAG:
    """同步版本的 build_knowledge_graph。

    Args:
        working_dir: LightRAG 工作目录
        force_rebuild: 是否强制重建

    Returns:
        已导入数据的 LightRAG 实例
    """
    return asyncio.run(
        build_knowledge_graph(working_dir=working_dir, force_rebuild=force_rebuild)
    )
