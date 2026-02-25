"""K23 索引器 — 将知识片段和模板索引到 qmd 向量库

数据源：
1. fragments.jsonl（692 条知识片段）→ 按章节分配到 8 个 Collection
2. ch06_templates/*.md（4 大工程类型模板）→ ch06_methods
3. writing_guides/*.md（10 章撰写指南）→ templates
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import qmd
from qmd import Database, Store
from qmd.llm.base import LLMBackend

from vector_store.config import (
    ALL_COLLECTIONS,
    CH06_TEMPLATES_DIR,
    CHAPTER_TO_COLLECTION,
    DB_PATH,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
    FRAGMENTS_JSONL,
    WRITING_GUIDES_DIR,
)
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def build_vector_store(
    *,
    db_path: Path | None = None,
    force_rebuild: bool = False,
    auto_embed: bool = True,
) -> tuple[Database, Store]:
    """构建完整向量库。

    Args:
        db_path: 数据库路径
        force_rebuild: 是否强制重建（删除已有数据库）
        auto_embed: 是否自动生成嵌入向量

    Returns:
        (Database, Store) 元组
    """
    db_path = db_path or DB_PATH

    log_msg("INFO", "=" * 60)
    log_msg("INFO", "K23 向量库构建启动")
    log_msg("INFO", "=" * 60)

    # 强制重建
    if force_rebuild and db_path.exists():
        log_msg("INFO", f"强制重建: 删除 {db_path}")
        db_path.unlink()

    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: 创建 store
    log_msg("INFO", "[Step 1/4] 创建 qmd store")
    db, store = qmd.create_store(str(db_path))

    # Step 2: 索引知识片段
    log_msg("INFO", "[Step 2/4] 索引知识片段")
    _index_fragments(store)

    # Step 3: 索引补充数据
    log_msg("INFO", "[Step 3/4] 索引模板和撰写指南")
    _index_extra_sources(store)

    # Step 4: 生成嵌入
    if auto_embed:
        log_msg("INFO", "[Step 4/4] 生成嵌入向量")
        backend = _create_embedding_backend()
        embed_stats = store.embed_documents(
            backend, force=False, batch_size=EMBEDDING_BATCH_SIZE
        )
        log_msg("INFO", f"  嵌入统计: {embed_stats}")
        backend.close()
    else:
        log_msg("INFO", "[Step 4/4] 跳过嵌入（auto_embed=False）")

    # 统计
    log_msg("INFO", "=" * 60)
    total = 0
    for coll in ALL_COLLECTIONS:
        count = store.get_document_count(coll)
        total += count
        log_msg("INFO", f"  {coll}: {count} 文档")
    log_msg("INFO", f"K23 构建完成: {total} 文档, 数据库 {db_path}")
    log_msg("INFO", "=" * 60)

    return db, store


# ---------------------------------------------------------------------------
# 内部方法
# ---------------------------------------------------------------------------


def _load_fragments(path: Path) -> list[dict[str, Any]]:
    """加载 fragments.jsonl。

    Args:
        path: JSONL 文件路径

    Returns:
        片段字典列表
    """
    fragments: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                fragments.append(json.loads(line))
    return fragments


def _build_document_content(fragment: dict[str, Any]) -> str:
    """为片段构建索引内容，prepend 元数据前缀。

    在原始内容前添加结构化元数据，使 BM25 和向量检索
    能自然地按工程类型、章节等维度匹配。

    Args:
        fragment: 知识片段字典

    Returns:
        带元数据前缀的内容文本
    """
    parts: list[str] = []

    # 元数据前缀
    eng_type = fragment.get("engineering_type", "")
    if eng_type:
        parts.append(f"[工程类型: {eng_type}]")

    section = fragment.get("section", "")
    if section:
        parts.append(f"[章节: {section}]")

    tags = fragment.get("tags", [])
    if tags:
        parts.append(f"[标签: {', '.join(tags[:8])}]")

    # 正文
    content = fragment.get("content", "")
    if parts:
        prefix = " ".join(parts)
        return f"{prefix}\n{content}"
    return content


def _index_fragments(store: Store) -> dict[str, int]:
    """索引 fragments.jsonl 到各 Collection。

    Args:
        store: qmd Store 实例

    Returns:
        各 Collection 索引数量统计
    """
    fragments = _load_fragments(FRAGMENTS_JSONL)
    log_msg("INFO", f"  加载 {len(fragments)} 条片段")

    stats: dict[str, int] = {coll: 0 for coll in ALL_COLLECTIONS}
    skipped = 0

    for frag in fragments:
        chapter = frag.get("chapter", "")
        collection = CHAPTER_TO_COLLECTION.get(chapter)
        if not collection:
            skipped += 1
            continue

        frag_id = frag.get("id", f"unknown_{skipped}")
        content = _build_document_content(frag)

        store.index_document(collection, frag_id, content)
        stats[collection] = stats.get(collection, 0) + 1

    log_msg("INFO", f"  索引完成: {sum(stats.values())} 条, 跳过 {skipped}")
    for coll, count in sorted(stats.items()):
        if count > 0:
            log_msg("INFO", f"    {coll}: {count}")

    return stats


def _index_extra_sources(store: Store) -> dict[str, int]:
    """索引补充数据源（ch06 模板 + 撰写指南）。

    Args:
        store: qmd Store 实例

    Returns:
        索引数量统计
    """
    stats: dict[str, int] = {"ch06_templates": 0, "writing_guides": 0}

    # ch06 模板（4 个工程类型的施工方法模板）
    if CH06_TEMPLATES_DIR.exists():
        for md_file in sorted(CH06_TEMPLATES_DIR.glob("*.md")):
            if md_file.name == "README.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                continue
            file_id = f"template_{md_file.stem}"
            store.index_document("ch06_methods", file_id, content)
            stats["ch06_templates"] += 1
        log_msg("INFO", f"  ch06 模板: {stats['ch06_templates']} 文件")

    # 撰写指南（各章节撰写指导）
    if WRITING_GUIDES_DIR.exists():
        for md_file in sorted(WRITING_GUIDES_DIR.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                continue
            file_id = f"guide_{md_file.stem}"
            store.index_document("templates", file_id, content)
            stats["writing_guides"] += 1
        log_msg("INFO", f"  撰写指南: {stats['writing_guides']} 文件")

    return stats


def _create_embedding_backend() -> LLMBackend:
    """创建嵌入模型后端。

    Returns:
        SentenceTransformerBackend 实例
    """
    from qmd.llm.sentence_tf import SentenceTransformerBackend

    log_msg("INFO", f"  加载嵌入模型: {EMBEDDING_MODEL} (device={EMBEDDING_DEVICE})")
    backend = SentenceTransformerBackend(
        model_name=EMBEDDING_MODEL,
        device=EMBEDDING_DEVICE,
    )
    dim = backend.get_embedding_dimensions()
    log_msg("INFO", f"  嵌入维度: {dim}")
    return backend
