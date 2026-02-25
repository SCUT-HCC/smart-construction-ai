"""K21 管道编排 — 端到端实体/关系抽取

五步流程：
1. 规则抽取（4 个结构化 Markdown 数据源）
2. LLM 抽取（fragments.jsonl 高密度片段，可选）
3. 合并实体和关系
4. 标准化 + 去重
5. 分配 ID → 序列化 JSON + 生成报告
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from entity_extraction.config import OUTPUT_DIR
from entity_extraction.llm_extractor import LLMExtractor
from entity_extraction.normalizer import (
    assign_ids,
    deduplicate_entities,
    deduplicate_relations,
)
from entity_extraction.rule_extractor import run_rule_extraction
from entity_extraction.schema import (
    RELATION_TYPE_LABELS,
    Entity,
    KnowledgeGraph,
    Relation,
)
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# 管道主函数
# ---------------------------------------------------------------------------


def run_pipeline(
    *,
    skip_llm: bool = False,
    output_dir: Path | None = None,
) -> KnowledgeGraph:
    """执行端到端实体/关系抽取管道。

    Args:
        skip_llm: 是否跳过 LLM 抽取（仅使用规则抽取）
        output_dir: 输出目录，默认使用配置中的 OUTPUT_DIR

    Returns:
        构建完成的 KnowledgeGraph
    """
    output_dir = output_dir or OUTPUT_DIR
    log_msg("INFO", "=" * 60)
    log_msg("INFO", "K21 实体/关系抽取管道启动")
    log_msg("INFO", "=" * 60)

    # ------------------------------------------------------------------
    # Step 1: 规则抽取
    # ------------------------------------------------------------------
    log_msg("INFO", "[Step 1/5] 规则抽取（结构化 Markdown 数据源）")
    rule_entities, rule_relations = run_rule_extraction()

    # ------------------------------------------------------------------
    # Step 2: LLM 抽取（可选）
    # ------------------------------------------------------------------
    llm_entities: list[Entity] = []
    llm_relations: list[Relation] = []
    if skip_llm:
        log_msg("INFO", "[Step 2/5] LLM 抽取 — 已跳过 (skip_llm=True)")
    else:
        log_msg("INFO", "[Step 2/5] LLM 抽取（fragments.jsonl 高密度片段）")
        extractor = LLMExtractor()
        llm_entities, llm_relations = extractor.extract_from_fragments()

    # ------------------------------------------------------------------
    # Step 3: 合并
    # ------------------------------------------------------------------
    log_msg("INFO", "[Step 3/5] 合并规则 + LLM 结果")
    all_entities = rule_entities + llm_entities
    all_relations = rule_relations + llm_relations
    log_msg("INFO", f"  合并后: {len(all_entities)} 实体, {len(all_relations)} 关系")

    # ------------------------------------------------------------------
    # Step 4: 标准化 + 去重
    # ------------------------------------------------------------------
    log_msg("INFO", "[Step 4/5] 实体标准化 + 去重")
    deduped_entities, name_map = deduplicate_entities(all_entities)
    deduped_relations = deduplicate_relations(all_relations, name_map)

    # ------------------------------------------------------------------
    # Step 5: 分配 ID + 构建图谱
    # ------------------------------------------------------------------
    log_msg("INFO", "[Step 5/5] 分配 ID + 序列化输出")
    assign_ids(deduped_entities, deduped_relations)

    metadata = _build_metadata(
        rule_entities=rule_entities,
        llm_entities=llm_entities,
        deduped_entities=deduped_entities,
        rule_relations=rule_relations,
        llm_relations=llm_relations,
        deduped_relations=deduped_relations,
        skip_llm=skip_llm,
    )

    graph = KnowledgeGraph(
        entities=deduped_entities,
        relations=deduped_relations,
        metadata=metadata,
    )

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------
    _save_outputs(graph, output_dir)

    log_msg("INFO", "=" * 60)
    log_msg(
        "INFO", f"K21 管道完成: {len(graph.entities)} 实体, {len(graph.relations)} 关系"
    )
    log_msg("INFO", f"输出目录: {output_dir}")
    log_msg("INFO", "=" * 60)

    return graph


# ---------------------------------------------------------------------------
# 统计元信息
# ---------------------------------------------------------------------------


def _build_metadata(
    *,
    rule_entities: list[Entity],
    llm_entities: list[Entity],
    deduped_entities: list[Entity],
    rule_relations: list[Relation],
    llm_relations: list[Relation],
    deduped_relations: list[Relation],
    skip_llm: bool,
) -> dict:
    """构建管道统计元信息。

    Args:
        rule_entities: 规则抽取的实体
        llm_entities: LLM 抽取的实体
        deduped_entities: 去重后的实体
        rule_relations: 规则抽取的关系
        llm_relations: LLM 抽取的关系
        deduped_relations: 去重后的关系
        skip_llm: 是否跳过了 LLM 抽取

    Returns:
        元信息字典
    """
    entity_type_counts = Counter(e.type for e in deduped_entities)
    eng_type_counts = Counter(e.engineering_type for e in deduped_entities)
    rel_type_counts = Counter(r.relation_type for r in deduped_relations)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "skip_llm": skip_llm,
        "raw_counts": {
            "rule_entities": len(rule_entities),
            "rule_relations": len(rule_relations),
            "llm_entities": len(llm_entities),
            "llm_relations": len(llm_relations),
            "total_entities_before_dedup": len(rule_entities) + len(llm_entities),
            "total_relations_before_dedup": len(rule_relations) + len(llm_relations),
        },
        "final_counts": {
            "entities": len(deduped_entities),
            "relations": len(deduped_relations),
        },
        "entity_type_distribution": dict(entity_type_counts.most_common()),
        "engineering_type_distribution": dict(eng_type_counts.most_common()),
        "relation_type_distribution": dict(rel_type_counts.most_common()),
    }


# ---------------------------------------------------------------------------
# 序列化输出
# ---------------------------------------------------------------------------


def _save_outputs(graph: KnowledgeGraph, output_dir: Path) -> None:
    """将知识图谱序列化为 JSON 并生成报告。

    输出文件：
    - entities.json: 实体列表
    - relations.json: 关系列表
    - knowledge_graph.json: 完整图谱（含元信息）
    - extraction_report.md: 可读报告

    Args:
        graph: 知识图谱
        output_dir: 输出目录
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 实体 JSON
    entities_path = output_dir / "entities.json"
    entities_data = [e.model_dump() for e in graph.entities]
    entities_path.write_text(
        json.dumps(entities_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_msg("INFO", f"  已写入: {entities_path} ({len(entities_data)} 条)")

    # 关系 JSON
    relations_path = output_dir / "relations.json"
    relations_data = [r.model_dump() for r in graph.relations]
    relations_path.write_text(
        json.dumps(relations_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_msg("INFO", f"  已写入: {relations_path} ({len(relations_data)} 条)")

    # 完整图谱 JSON
    graph_path = output_dir / "knowledge_graph.json"
    graph_path.write_text(
        graph.model_dump_json(indent=2),
        encoding="utf-8",
    )
    log_msg("INFO", f"  已写入: {graph_path}")

    # 报告
    report_path = output_dir / "extraction_report.md"
    report_path.write_text(
        _generate_report(graph),
        encoding="utf-8",
    )
    log_msg("INFO", f"  已写入: {report_path}")


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------


def _generate_report(graph: KnowledgeGraph) -> str:
    """生成 Markdown 格式的抽取报告。

    Args:
        graph: 知识图谱

    Returns:
        Markdown 报告文本
    """
    meta = graph.metadata
    raw = meta.get("raw_counts", {})
    final = meta.get("final_counts", {})
    etype_dist = meta.get("entity_type_distribution", {})
    eng_dist = meta.get("engineering_type_distribution", {})
    rel_dist = meta.get("relation_type_distribution", {})

    lines: list[str] = []
    lines.append("# K21 实体/关系抽取报告")
    lines.append("")
    lines.append(f"> 生成时间: {meta.get('generated_at', 'N/A')}")
    lines.append(f"> LLM 抽取: {'跳过' if meta.get('skip_llm') else '已执行'}")
    lines.append("")

    # 总览
    lines.append("## 1. 总览")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 规则抽取实体 | {raw.get('rule_entities', 0)} |")
    lines.append(f"| 规则抽取关系 | {raw.get('rule_relations', 0)} |")
    lines.append(f"| LLM 抽取实体 | {raw.get('llm_entities', 0)} |")
    lines.append(f"| LLM 抽取关系 | {raw.get('llm_relations', 0)} |")
    lines.append(f"| 去重前实体总数 | {raw.get('total_entities_before_dedup', 0)} |")
    lines.append(f"| 去重前关系总数 | {raw.get('total_relations_before_dedup', 0)} |")
    lines.append(f"| **最终实体数** | **{final.get('entities', 0)}** |")
    lines.append(f"| **最终关系数** | **{final.get('relations', 0)}** |")
    lines.append("")

    # 实体类型分布
    lines.append("## 2. 实体类型分布")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("|------|------|")
    type_labels = {
        "process": "工序 (process)",
        "equipment": "设备 (equipment)",
        "hazard": "危险源 (hazard)",
        "safety_measure": "安全措施 (safety_measure)",
        "quality_point": "质量要点 (quality_point)",
    }
    for etype, count in etype_dist.items():
        label = type_labels.get(etype, etype)
        lines.append(f"| {label} | {count} |")
    lines.append("")

    # 工程类型分布
    lines.append("## 3. 工程类型分布")
    lines.append("")
    lines.append("| 工程类型 | 实体数 |")
    lines.append("|----------|--------|")
    for eng, count in eng_dist.items():
        lines.append(f"| {eng} | {count} |")
    lines.append("")

    # 关系类型分布
    lines.append("## 4. 关系类型分布")
    lines.append("")
    lines.append("| 关系类型 | 中文 | 数量 |")
    lines.append("|----------|------|------|")
    for rtype, count in rel_dist.items():
        label = RELATION_TYPE_LABELS.get(rtype, rtype)
        lines.append(f"| {rtype} | {label} | {count} |")
    lines.append("")

    # 实体采样
    lines.append("## 5. 实体采样（每类型前 5 条）")
    lines.append("")
    type_groups: dict[str, list[Entity]] = {}
    for e in graph.entities:
        type_groups.setdefault(e.type, []).append(e)

    for etype in ("process", "equipment", "hazard", "safety_measure", "quality_point"):
        group = type_groups.get(etype, [])
        if not group:
            continue
        label = type_labels.get(etype, etype)
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| ID | 名称 | 工程类型 | 来源 | 置信度 |")
        lines.append("|----|------|----------|------|--------|")
        for e in group[:5]:
            lines.append(
                f"| {e.id} | {e.name} | {e.engineering_type} | {e.source} | {e.confidence:.2f} |"
            )
        if len(group) > 5:
            lines.append(f"| ... | _(共 {len(group)} 条)_ | | | |")
        lines.append("")

    # 关系采样
    lines.append("## 6. 关系采样（前 10 条）")
    lines.append("")
    lines.append("| ID | 起点 | 关系 | 终点 | 证据 |")
    lines.append("|----|------|------|------|------|")
    for r in graph.relations[:10]:
        evidence_short = r.evidence[:30] + "..." if len(r.evidence) > 30 else r.evidence
        label = RELATION_TYPE_LABELS.get(r.relation_type, r.relation_type)
        lines.append(
            f"| {r.id} | {r.source_entity_id} | {label} | {r.target_entity_id} | {evidence_short} |"
        )
    if len(graph.relations) > 10:
        lines.append(f"| ... | _(共 {len(graph.relations)} 条)_ | | | |")
    lines.append("")

    return "\n".join(lines)
