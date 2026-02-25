"""K21 规则解析器 — 从结构化 Markdown 表格中抽取实体和关系

解析 4 类数据源：
1. hazard_sources.md → 工序/危险源/安全措施 + produces_hazard/mitigated_by
2. safety_measures.md → 补充安全措施实体
3. quality_control_points.md → 工序/质量要点 + requires_quality_check
4. process_references/*.md → 工序/设备 + requires_equipment
"""

from __future__ import annotations

import re
from pathlib import Path

from entity_extraction.config import (
    HAZARD_SECTION_ENGINEERING_TYPE,
    HAZARD_SOURCES_PATH,
    PROCESS_REFS_DIR,
    QUALITY_POINTS_PATH,
    SAFETY_MEASURES_PATH,
)
from entity_extraction.schema import Entity, Relation
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# 通用 Markdown 表格解析工具
# ---------------------------------------------------------------------------


def _parse_table_rows(text: str) -> list[list[str]]:
    """解析 Markdown 表格，返回数据行（跳过表头和分隔行）。

    Args:
        text: 包含 Markdown 表格的文本块

    Returns:
        每行为一个列表，元素为各列文本（已 strip）
    """
    rows: list[list[str]] = []
    lines = text.strip().splitlines()
    header_seen = False
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            # 非表格行：重置状态以支持同一 section 内的多个表格
            header_seen = False
            continue
        # 跳过分隔行（|---|---|）
        if re.match(r"^\|[\s\-:]+\|", line):
            header_seen = True
            continue
        if not header_seen:
            # 表头行（分隔行之前的第一行），跳过
            continue
        # 解析数据行
        cells = [c.strip() for c in line.split("|")]
        # 去掉首尾空串（因为 "|a|b|" split 后首尾为 ""）
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if cells:
            rows.append(cells)
    return rows


def _split_sections(text: str) -> dict[str, str]:
    """按 ## N. 标题分割 Markdown 文档为章节。

    Args:
        text: 完整 Markdown 文本

    Returns:
        字典 {章节编号: 章节内容}，编号如 "2", "3", "5.1"
    """
    sections: dict[str, str] = {}
    # 匹配 ## N. 或 ### N.N 格式标题（句号/顿号可选，兼容 "### 5.1 有限空间" 格式）
    pattern = re.compile(r"^(#{2,3})\s+(\d+(?:\.\d+)?)[.、]?\s+(.*)", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        section_id = m.group(2)
        # 内容包含标题行本身（供子函数提取标题文本）
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[section_id] = text[start:end]
    return sections


# ---------------------------------------------------------------------------
# 1. hazard_sources.md 解析
# ---------------------------------------------------------------------------


def parse_hazard_sources(
    filepath: Path | None = None,
) -> tuple[list[Entity], list[Relation]]:
    """从危险源辨识表中抽取工序、危险源、安全措施实体及其关系。

    表格格式（章节 2-4）:
        | 序号 | 作业活动 | 危险因素 | 可能事故 | 等级 | 控制措施 |

    表格格式（章节 5.x，无"作业活动"列）:
        | 序号 | 危险因素 | 可能事故 | 等级 | 控制措施 |

    Args:
        filepath: Markdown 文件路径，默认使用配置路径

    Returns:
        (实体列表, 关系列表)
    """
    filepath = filepath or HAZARD_SOURCES_PATH
    text = filepath.read_text(encoding="utf-8")
    sections = _split_sections(text)

    entities: list[Entity] = []
    relations: list[Relation] = []

    for section_id, content in sections.items():
        # 跳过非危险源清单章节（如 "1" 风险等级定义、"6" 事故类型统计）
        top_section = section_id.split(".")[0]
        if top_section not in HAZARD_SECTION_ENGINEERING_TYPE:
            continue

        eng_type = HAZARD_SECTION_ENGINEERING_TYPE[top_section]
        rows = _parse_table_rows(content)

        for row in rows:
            if len(row) >= 6:
                # 标准 6 列格式：序号 | 作业活动 | 危险因素 | 可能事故 | 等级 | 控制措施
                process_name = row[1].strip()
                hazard_desc = row[2].strip()
                accident_type = row[3].strip()
                risk_level = row[4].strip()
                measure_desc = row[5].strip()
            elif len(row) >= 5:
                # 5 列格式（章节 5.x）：序号 | 危险因素 | 可能事故 | 等级 | 控制措施
                # 用子章节标题作为作业活动
                sub_title_match = re.search(r"###?\s+[\d.]+\s+(.+)", content[:200])
                process_name = (
                    sub_title_match.group(1).strip() if sub_title_match else "特殊作业"
                )
                hazard_desc = row[1].strip()
                accident_type = row[2].strip()
                risk_level = row[3].strip()
                measure_desc = row[4].strip()
            else:
                continue

            if not hazard_desc or not measure_desc:
                continue

            # --- 创建工序实体 ---
            process_entity = Entity(
                type="process",
                name=process_name,
                engineering_type=eng_type,
                source="rule",
                confidence=1.0,
            )

            # --- 创建危险源实体 ---
            hazard_entity = Entity(
                type="hazard",
                name=hazard_desc,
                engineering_type=eng_type,
                attributes={
                    "accident_type": accident_type,
                    "risk_level": risk_level,
                },
                source="rule",
                confidence=1.0,
            )

            # --- 创建安全措施实体 ---
            measure_entity = Entity(
                type="safety_measure",
                name=measure_desc,
                engineering_type=eng_type,
                source="rule",
                confidence=1.0,
            )

            entities.extend([process_entity, hazard_entity, measure_entity])

            # --- 关系：工序→产生→危险源 ---
            relations.append(
                Relation(
                    source_entity_id=process_entity.name,  # 临时用 name，后续标准化分配 ID
                    target_entity_id=hazard_entity.name,
                    relation_type="produces_hazard",
                    confidence=1.0,
                    evidence=f"{process_name} → {hazard_desc} → {accident_type}",
                    source_doc="hazard_sources.md",
                )
            )

            # --- 关系：危险源→对应→安全措施 ---
            relations.append(
                Relation(
                    source_entity_id=hazard_entity.name,
                    target_entity_id=measure_entity.name,
                    relation_type="mitigated_by",
                    confidence=1.0,
                    evidence=f"{hazard_desc}({accident_type}) → {measure_desc[:50]}",
                    source_doc="hazard_sources.md",
                )
            )

    log_msg(
        "INFO", f"hazard_sources 解析完成: {len(entities)} 实体, {len(relations)} 关系"
    )
    return entities, relations


# ---------------------------------------------------------------------------
# 2. safety_measures.md 解析
# ---------------------------------------------------------------------------


def parse_safety_measures(filepath: Path | None = None) -> list[Entity]:
    """从安全保证措施库中抽取补充安全措施实体。

    表格格式:
        | 序号 | 措施内容 |

    Args:
        filepath: Markdown 文件路径

    Returns:
        安全措施实体列表
    """
    filepath = filepath or SAFETY_MEASURES_PATH
    text = filepath.read_text(encoding="utf-8")
    sections = _split_sections(text)

    entities: list[Entity] = []

    # 遍历 1.x 章节（安全保证措施各场景）
    for section_id, content in sections.items():
        # 跳过 2.x（安全管理制度）、3.x（文明施工）、4.x（环保）—— 这些是管理措施非技术措施
        top_section = section_id.split(".")[0]
        if top_section not in ("1",):
            continue

        # 获取子章节标题作为场景标签
        sub_title_match = re.search(r"###?\s+[\d.]+\s+(.+)", content[:200])
        scene = sub_title_match.group(1).strip() if sub_title_match else ""

        rows = _parse_table_rows(content)
        for row in rows:
            if len(row) >= 2:
                measure_text = row[1].strip()
                if not measure_text:
                    continue
                entities.append(
                    Entity(
                        type="safety_measure",
                        name=measure_text,
                        engineering_type="通用",
                        attributes={"scene": scene} if scene else {},
                        source="rule",
                        confidence=0.9,
                    )
                )

    log_msg("INFO", f"safety_measures 解析完成: {len(entities)} 实体")
    return entities


# ---------------------------------------------------------------------------
# 3. quality_control_points.md 解析
# ---------------------------------------------------------------------------


def parse_quality_points(
    filepath: Path | None = None,
) -> tuple[list[Entity], list[Relation]]:
    """从质量控制点表中抽取工序和质量要点实体及关系。

    表格格式 A（章节 4.1 主变安装）:
        | 工序 | W/H/S 点 | 质量控制要点 |

    表格格式 B（章节 4.2, 5, 6）:
        | 工序 | 质量控制要点 |

    Args:
        filepath: Markdown 文件路径

    Returns:
        (实体列表, 关系列表)
    """
    filepath = filepath or QUALITY_POINTS_PATH
    text = filepath.read_text(encoding="utf-8")
    sections = _split_sections(text)

    entities: list[Entity] = []
    relations: list[Relation] = []

    # 章节→工程类型映射
    section_eng_type: dict[str, str] = {
        "2": "变电土建",  # 质量通病
        "3": "变电土建",  # 成品保护
        "4": "变电电气",  # 电气质量
        "4.1": "变电电气",
        "4.2": "变电电气",
        "5": "线路塔基",
        "6": "特殊作业",
        "6.1": "特殊作业",
        "6.2": "特殊作业",
    }

    for section_id, content in sections.items():
        top = section_id.split(".")[0]
        # 跳过第 1 章（通用三阶段管理措施）和第 3 章（成品保护）
        if top in ("1", "3"):
            continue

        eng_type = section_eng_type.get(section_id, section_eng_type.get(top, "通用"))
        rows = _parse_table_rows(content)

        for row in rows:
            process_name = ""
            quality_desc = ""
            attributes: dict[str, str] = {}

            if len(row) >= 3 and "W/H/S" in content[:500]:
                # 格式 A：工序 | W/H/S 点 | 质量控制要点
                process_name = row[0].strip()
                attributes["whs_point"] = row[1].strip()
                quality_desc = row[2].strip()
            elif len(row) >= 2:
                # 格式 B：工序 | 质量控制要点
                # 或者 序号 | 质量薄弱环节 | 预防技术措施（章节 2）
                if top == "2" and len(row) >= 3:
                    # 质量通病：薄弱环节→质量要点（预防措施）
                    process_name = row[1].strip()  # 质量薄弱环节当作工序关联
                    quality_desc = row[2].strip()
                else:
                    process_name = row[0].strip()
                    quality_desc = row[1].strip()

            if not process_name or not quality_desc:
                continue

            # --- 创建工序实体 ---
            process_entity = Entity(
                type="process",
                name=process_name,
                engineering_type=eng_type,
                source="rule",
                confidence=1.0,
            )

            # --- 创建质量要点实体 ---
            quality_entity = Entity(
                type="quality_point",
                name=quality_desc[:80],  # 截断过长描述作为名称
                engineering_type=eng_type,
                attributes=attributes,
                source="rule",
                confidence=1.0,
            )

            entities.extend([process_entity, quality_entity])

            # --- 关系：工序→要求→质量要点 ---
            relations.append(
                Relation(
                    source_entity_id=process_entity.name,
                    target_entity_id=quality_entity.name,
                    relation_type="requires_quality_check",
                    confidence=1.0,
                    evidence=f"{process_name} → {quality_desc[:50]}",
                    source_doc="quality_control_points.md",
                )
            )

    log_msg(
        "INFO", f"quality_points 解析完成: {len(entities)} 实体, {len(relations)} 关系"
    )
    return entities, relations


# ---------------------------------------------------------------------------
# 4. process_references/*.md 解析
# ---------------------------------------------------------------------------

# 文件名→工程类型映射
_PROCESS_REF_ENG_TYPE: dict[str, str] = {
    "civil_works.md": "变电土建",
    "electrical_install.md": "变电电气",
    "line_tower.md": "线路塔基",
    "special_general.md": "特殊作业",
}

# 设备关键词（用于从参数表和工艺流程中识别设备实体）
_EQUIPMENT_KEYWORDS: list[str] = [
    "机",
    "器",
    "锤",
    "棒",
    "泵",
    "仪",
    "架",
    "管",
    "锯",
    "车",
    "模板",
    "串筒",
    "溜槽",
    "卷扬",
    "钢丝绳",
    "吊具",
    "脚手架",
]


def parse_process_references(
    dirpath: Path | None = None,
) -> tuple[list[Entity], list[Relation]]:
    """从工艺参考文件中抽取工序和设备实体。

    从 ## 标题中提取工序名称，从参数表中识别设备实体。

    Args:
        dirpath: 工艺参考目录路径

    Returns:
        (实体列表, 关系列表)
    """
    dirpath = dirpath or PROCESS_REFS_DIR
    entities: list[Entity] = []
    relations: list[Relation] = []

    for md_file in sorted(dirpath.glob("*.md")):
        eng_type = _PROCESS_REF_ENG_TYPE.get(md_file.name, "通用")
        text = md_file.read_text(encoding="utf-8")

        # --- 从 ## 标题抽取工序 ---
        section_pattern = re.compile(r"^##\s+\d+[.、]\s*(.+)", re.MULTILINE)
        for m in section_pattern.finditer(text):
            process_name = m.group(1).strip()
            # 过滤非工序标题（如"关键参数""质量控制标准"）
            if any(
                kw in process_name
                for kw in ("参数", "标准", "指标", "要求", "措施", "规格")
            ):
                continue
            entities.append(
                Entity(
                    type="process",
                    name=process_name,
                    engineering_type=eng_type,
                    source="rule",
                    confidence=0.9,
                )
            )

        # --- 从工艺流程代码块中抽取工序 ---
        flow_pattern = re.compile(r"```\n(.+?)\n```", re.DOTALL)
        for m in flow_pattern.finditer(text):
            flow_text = m.group(1)
            # 按 → 分割工序
            steps = re.split(r"[→\n]", flow_text)
            for step in steps:
                step = step.strip().strip("→ \n")
                if not step or len(step) < 2:
                    continue
                # 去除前缀编号
                step = re.sub(r"^\d+[.、)\s]+", "", step).strip()
                if not step:
                    continue
                step_entity = Entity(
                    type="process",
                    name=step,
                    engineering_type=eng_type,
                    source="rule",
                    confidence=0.8,
                )
                entities.append(step_entity)

                # 如果流程中提到设备关键词，抽取设备实体
                for kw in _EQUIPMENT_KEYWORDS:
                    if kw in step:
                        # 设备名通常是"XX机""XX器"等
                        equip_match = re.search(
                            rf"[\u4e00-\u9fff]{{1,6}}{re.escape(kw)}", step
                        )
                        if equip_match:
                            equip_name = equip_match.group(0)
                            equip_entity = Entity(
                                type="equipment",
                                name=equip_name,
                                engineering_type=eng_type,
                                source="rule",
                                confidence=0.7,
                            )
                            entities.append(equip_entity)
                            relations.append(
                                Relation(
                                    source_entity_id=step,
                                    target_entity_id=equip_name,
                                    relation_type="requires_equipment",
                                    confidence=0.7,
                                    evidence=f"工艺流程: {step}",
                                    source_doc=md_file.name,
                                )
                            )

        # --- 从参数表中识别设备 ---
        rows = _parse_table_rows(text)
        for row in rows:
            for cell in row:
                for kw in _EQUIPMENT_KEYWORDS:
                    if kw in cell:
                        equip_match = re.search(
                            r"[A-Z]*[\u4e00-\u9fff]{1,8}" + re.escape(kw),
                            cell,
                        )
                        if equip_match:
                            equip_name = equip_match.group(0)
                            if len(equip_name) >= 3:  # 过滤太短的匹配
                                entities.append(
                                    Entity(
                                        type="equipment",
                                        name=equip_name,
                                        engineering_type=eng_type,
                                        source="rule",
                                        confidence=0.7,
                                    )
                                )

    log_msg(
        "INFO",
        f"process_references 解析完成: {len(entities)} 实体, {len(relations)} 关系",
    )
    return entities, relations


# ---------------------------------------------------------------------------
# 汇总入口
# ---------------------------------------------------------------------------


def run_rule_extraction() -> tuple[list[Entity], list[Relation]]:
    """运行全部规则抽取，汇总所有数据源的结果。

    Returns:
        (合并后的实体列表, 合并后的关系列表)
    """
    all_entities: list[Entity] = []
    all_relations: list[Relation] = []

    # 1. 危险源清单
    e1, r1 = parse_hazard_sources()
    all_entities.extend(e1)
    all_relations.extend(r1)

    # 2. 安全措施库（补充实体，无新关系）
    e2 = parse_safety_measures()
    all_entities.extend(e2)

    # 3. 质量控制点
    e3, r3 = parse_quality_points()
    all_entities.extend(e3)
    all_relations.extend(r3)

    # 4. 工艺参考
    e4, r4 = parse_process_references()
    all_entities.extend(e4)
    all_relations.extend(r4)

    log_msg(
        "INFO", f"规则抽取汇总: {len(all_entities)} 实体, {len(all_relations)} 关系"
    )
    return all_entities, all_relations
