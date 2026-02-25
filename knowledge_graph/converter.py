"""K22 数据转换器 — 将 K21 实体/关系转为 LightRAG custom_kg 格式

LightRAG insert_custom_kg() 接受的格式：
- entities: [{entity_name, entity_type, description, source_id}]
- relationships: [{src_id, tgt_id, description, keywords, weight, source_id}]
- chunks: [{content, source_id, source_chunk_index}]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_graph.config import (
    ENTITIES_JSON,
    RELATION_KEYWORDS,
    RELATIONS_JSON,
)
from utils.logger_system import log_msg

# ---------------------------------------------------------------------------
# 实体类型中文标签
# ---------------------------------------------------------------------------
_ENTITY_TYPE_LABELS: dict[str, str] = {
    "process": "施工工序",
    "equipment": "施工设备",
    "hazard": "危险源",
    "safety_measure": "安全措施",
    "quality_point": "质量控制要点",
}


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def convert_k21_to_lightrag(
    entities_path: Path | None = None,
    relations_path: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """将 K21 输出转换为 LightRAG custom_kg 格式。

    Args:
        entities_path: K21 实体 JSON 路径
        relations_path: K21 关系 JSON 路径

    Returns:
        LightRAG custom_kg 字典，包含 entities, relationships, chunks
    """
    entities_path = entities_path or ENTITIES_JSON
    relations_path = relations_path or RELATIONS_JSON

    raw_entities = _load_json(entities_path)
    raw_relations = _load_json(relations_path)

    log_msg(
        "INFO", f"K22 转换: 加载 {len(raw_entities)} 实体, {len(raw_relations)} 关系"
    )

    # 构建 ID → 名称映射
    id_to_name = {e["id"]: e["name"] for e in raw_entities}

    # 转换实体
    lg_entities = _convert_entities(raw_entities)

    # 转换关系
    lg_relationships, skipped = _convert_relationships(raw_relations, id_to_name)

    # 从关系证据构建 chunks
    lg_chunks = _build_chunks(raw_relations, id_to_name)

    log_msg(
        "INFO",
        f"K22 转换完成: {len(lg_entities)} 实体, "
        f"{len(lg_relationships)} 关系 (跳过 {skipped}), "
        f"{len(lg_chunks)} chunks",
    )

    return {
        "entities": lg_entities,
        "relationships": lg_relationships,
        "chunks": lg_chunks,
    }


# ---------------------------------------------------------------------------
# 内部方法
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> list[dict[str, Any]]:
    """加载 JSON 文件。

    Args:
        path: JSON 文件路径

    Returns:
        解析后的列表
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _convert_entities(raw_entities: list[dict]) -> list[dict[str, Any]]:
    """将 K21 实体转换为 LightRAG 实体格式。

    Args:
        raw_entities: K21 原始实体列表

    Returns:
        LightRAG 实体列表
    """
    results: list[dict[str, Any]] = []
    for e in raw_entities:
        description = _build_entity_description(e)
        results.append(
            {
                "entity_name": e["name"],
                "entity_type": e["type"],
                "description": description,
                "source_id": e["id"],
            }
        )
    return results


def _build_entity_description(entity: dict) -> str:
    """为实体生成 LightRAG 的 description 字段。

    包含：类型标签、工程类型、属性、别名信息。

    Args:
        entity: K21 实体字典

    Returns:
        描述文本
    """
    parts: list[str] = []

    # 类型标签
    type_label = _ENTITY_TYPE_LABELS.get(entity["type"], entity["type"])
    parts.append(f"[{type_label}]")

    # 工程类型
    eng_type = entity.get("engineering_type", "通用")
    if eng_type != "通用":
        parts.append(f"工程类型: {eng_type}")

    # 属性
    attrs = entity.get("attributes", {})
    if attrs:
        attr_strs = [f"{k}={v}" for k, v in attrs.items()]
        parts.append(f"属性: {', '.join(attr_strs)}")

    # 别名
    aliases = entity.get("aliases", [])
    if aliases:
        parts.append(f"别名: {', '.join(aliases[:5])}")

    # 来源和置信度
    source = entity.get("source", "rule")
    confidence = entity.get("confidence", 1.0)
    parts.append(f"来源: {source}, 置信度: {confidence:.1f}")

    return "; ".join(parts)


def _convert_relationships(
    raw_relations: list[dict],
    id_to_name: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """将 K21 关系转换为 LightRAG 关系格式。

    LightRAG 的 src_id/tgt_id 需要匹配 entity_name。

    Args:
        raw_relations: K21 原始关系列表
        id_to_name: 实体 ID → 名称映射

    Returns:
        (LightRAG 关系列表, 跳过数)
    """
    results: list[dict[str, Any]] = []
    skipped = 0

    for r in raw_relations:
        src_name = id_to_name.get(r["source_entity_id"])
        tgt_name = id_to_name.get(r["target_entity_id"])

        if not src_name or not tgt_name:
            skipped += 1
            continue

        rel_type = r["relation_type"]
        keywords = RELATION_KEYWORDS.get(rel_type, rel_type)
        evidence = r.get("evidence", "")
        description = evidence if evidence else f"{src_name} → {rel_type} → {tgt_name}"

        results.append(
            {
                "src_id": src_name,
                "tgt_id": tgt_name,
                "description": description,
                "keywords": keywords,
                "weight": r.get("confidence", 1.0),
                "source_id": r.get("source_doc", "unknown"),
            }
        )

    return results, skipped


def _build_chunks(
    raw_relations: list[dict],
    id_to_name: dict[str, str],
) -> list[dict[str, Any]]:
    """从关系证据构建 LightRAG chunks。

    将相同来源的关系证据合并为文本块。

    Args:
        raw_relations: K21 原始关系列表
        id_to_name: 实体 ID → 名称映射

    Returns:
        LightRAG chunks 列表
    """
    # 按 source_doc 分组
    doc_evidences: dict[str, list[str]] = {}
    for r in raw_relations:
        source_doc = r.get("source_doc", "unknown")
        evidence = r.get("evidence", "")
        if not evidence:
            continue

        src_name = id_to_name.get(r["source_entity_id"], r["source_entity_id"])
        tgt_name = id_to_name.get(r["target_entity_id"], r["target_entity_id"])
        line = f"{src_name} → {tgt_name}: {evidence}"

        doc_evidences.setdefault(source_doc, []).append(line)

    # 每个文档生成一个 chunk
    chunks: list[dict[str, Any]] = []
    for idx, (doc, lines) in enumerate(doc_evidences.items()):
        content = "\n".join(lines)
        chunks.append(
            {
                "content": content,
                "source_id": doc,
                "source_chunk_index": idx,
            }
        )

    return chunks
