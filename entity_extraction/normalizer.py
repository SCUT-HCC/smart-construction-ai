"""K21 实体标准化与去重

三步处理：
1. 名称归一化（去冗余修饰词、统一术语）
2. 实体去重（精确匹配 + 模糊匹配合并）
3. 关系去重 + ID 重映射
"""

from __future__ import annotations

import re
from collections import defaultdict

from entity_extraction.config import (
    ENGINEERING_TYPE_ABBR,
    FUZZY_MATCH_THRESHOLD,
    MULTI_SOURCE_CONFIDENCE_BOOST,
)
from entity_extraction.schema import Entity, Relation
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# 名称归一化
# ---------------------------------------------------------------------------

# 需要去除的后缀虚词
_SUFFIX_PATTERNS: list[str] = [
    r"作业$",
    r"工作$",
    r"工程$",
    r"施工$",
    r"的$",
    r"等$",
]

# 需要去除的前缀
_PREFIX_PATTERNS: list[str] = [
    r"^进行",
    r"^实施",
    r"^开展",
]


def normalize_name(name: str) -> str:
    """标准化实体名称。

    处理规则：
    1. strip 首尾空白
    2. 去除前缀虚词（进行、实施、开展）
    3. 去除后缀虚词（作业、工作、的、等），但保留不能去的（如"高处作业"→保留）
    4. 去除括号内的次要说明
    5. 合并连续空格

    Args:
        name: 原始实体名称

    Returns:
        标准化后的名称
    """
    name = name.strip()
    if not name:
        return name

    # 去除前缀
    for p in _PREFIX_PATTERNS:
        name = re.sub(p, "", name)

    # 去除后缀（仅当剩余部分 ≥ 2 字时）
    for p in _SUFFIX_PATTERNS:
        candidate = re.sub(p, "", name)
        if len(candidate) >= 2:
            name = candidate

    # 合并多余空格
    name = re.sub(r"\s+", "", name)

    return name


# ---------------------------------------------------------------------------
# 编辑距离（Levenshtein）
# ---------------------------------------------------------------------------


def _edit_distance(a: str, b: str) -> int:
    """计算两个字符串的编辑距离。

    Args:
        a: 字符串 A
        b: 字符串 B

    Returns:
        编辑距离值
    """
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m

    # 使用一维 DP 优化空间
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # 删除
                curr[j - 1] + 1,  # 插入
                prev[j - 1] + cost,  # 替换
            )
        prev, curr = curr, prev
    return prev[n]


# ---------------------------------------------------------------------------
# 实体去重
# ---------------------------------------------------------------------------


def deduplicate_entities(entities: list[Entity]) -> tuple[list[Entity], dict[str, str]]:
    """去重实体列表，返回去重后的实体和名称映射。

    去重规则（同 type + 同 engineering_type 内）：
    1. 精确匹配：normalized name 完全相同 → 合并
    2. 模糊匹配：编辑距离 ≤ 阈值 → 合并（保留较短名称）
    3. 多源确认：rule + llm 都抽到 → confidence += boost

    Args:
        entities: 原始实体列表

    Returns:
        (去重后的实体列表, 旧名称→新名称映射字典)
    """
    # 先归一化所有名称
    for e in entities:
        e.name = normalize_name(e.name)

    # 按 (type, engineering_type) 分组
    groups: dict[tuple[str, str], list[Entity]] = defaultdict(list)
    for e in entities:
        if not e.name:
            continue
        groups[(e.type, e.engineering_type)].append(e)

    merged: list[Entity] = []
    name_map: dict[str, str] = {}  # old_name → canonical_name

    for _key, group in groups.items():
        # 按名称聚合
        name_to_entities: dict[str, list[Entity]] = defaultdict(list)
        for e in group:
            name_to_entities[e.name].append(e)

        # 精确匹配合并
        canonical_entities: list[Entity] = []
        for name, ents in name_to_entities.items():
            base = ents[0].model_copy()
            # 合并别名
            all_aliases: set[str] = set()
            sources: set[str] = set()
            for e in ents:
                all_aliases.update(e.aliases)
                sources.add(e.source)
                # 合并 attributes
                for k, v in e.attributes.items():
                    if k not in base.attributes:
                        base.attributes[k] = v
            all_aliases.discard(name)
            base.aliases = sorted(all_aliases)
            # 多源确认提升置信度
            if len(sources) > 1:
                base.confidence = min(
                    1.0, base.confidence + MULTI_SOURCE_CONFIDENCE_BOOST
                )
            canonical_entities.append(base)

        # 模糊匹配合并（简单贪心）
        i = 0
        while i < len(canonical_entities):
            j = i + 1
            while j < len(canonical_entities):
                dist = _edit_distance(
                    canonical_entities[i].name,
                    canonical_entities[j].name,
                )
                if dist <= FUZZY_MATCH_THRESHOLD and dist > 0:
                    # 合并：保留较短名称作为主名
                    keep, drop = (
                        (i, j)
                        if len(canonical_entities[i].name)
                        <= len(canonical_entities[j].name)
                        else (j, i)
                    )
                    keeper = canonical_entities[keep]
                    dropper = canonical_entities[drop]
                    # 将被合并的名称加入别名
                    keeper.aliases = sorted(
                        set(keeper.aliases) | {dropper.name} | set(dropper.aliases)
                    )
                    keeper.confidence = min(
                        1.0, max(keeper.confidence, dropper.confidence)
                    )
                    name_map[dropper.name] = keeper.name
                    canonical_entities.pop(drop)
                    if drop < i:
                        i -= 1
                    # 不增加 j，因为列表缩短了
                else:
                    j += 1
            i += 1

        merged.extend(canonical_entities)

    # 跨工程类型的通用实体也做简单去重
    # （如"高处坠落"同时出现在变电土建和变电电气中，保持各自独立但标记为通用）

    log_msg("INFO", f"实体去重: {len(entities)} → {len(merged)}")
    return merged, name_map


# ---------------------------------------------------------------------------
# 关系去重 + ID 重映射
# ---------------------------------------------------------------------------


def deduplicate_relations(
    relations: list[Relation],
    name_map: dict[str, str],
) -> list[Relation]:
    """去重关系列表，并根据名称映射更新实体引用。

    去重规则：
    (source_entity_id, target_entity_id, relation_type) 三元组相同 → 合并，
    保留 confidence 较高、evidence 较长的记录。

    Args:
        relations: 原始关系列表
        name_map: 实体名称映射（旧名→新名）

    Returns:
        去重后的关系列表
    """
    before = len(relations)

    # 应用名称映射
    for r in relations:
        r.source_entity_id = name_map.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = name_map.get(r.target_entity_id, r.target_entity_id)

    # 按三元组键去重
    seen: dict[tuple[str, str, str], Relation] = {}
    for r in relations:
        key = (r.source_entity_id, r.target_entity_id, r.relation_type)
        if key in seen:
            existing = seen[key]
            # 保留 confidence 更高的
            if r.confidence > existing.confidence or (
                r.confidence == existing.confidence
                and len(r.evidence) > len(existing.evidence)
            ):
                seen[key] = r
        else:
            seen[key] = r

    result = list(seen.values())
    log_msg("INFO", f"关系去重: {before} → {len(result)}")
    return result


# ---------------------------------------------------------------------------
# 分配 ID
# ---------------------------------------------------------------------------


def assign_ids(entities: list[Entity], relations: list[Relation]) -> None:
    """为实体和关系分配唯一 ID（原地修改）。

    实体 ID 格式: {type}_{eng_abbr}_{seq:03d}
    关系 ID 格式: rel_{seq:04d}

    同时将关系的 source_entity_id/target_entity_id 从名称更新为实体 ID。

    Args:
        entities: 实体列表
        relations: 关系列表
    """
    # 按类型分组计数
    type_counters: dict[str, int] = defaultdict(int)
    name_to_id: dict[str, str] = {}

    for e in entities:
        type_counters[e.type] += 1
        eng_abbr = ENGINEERING_TYPE_ABBR.get(e.engineering_type, "unk")
        e.id = f"{e.type}_{eng_abbr}_{type_counters[e.type]:03d}"
        name_to_id[e.name] = e.id
        # 别名也映射到同一 ID
        for alias in e.aliases:
            name_to_id[alias] = e.id

    # 关系 ID + 实体引用更新
    for seq, r in enumerate(relations, start=1):
        r.id = f"rel_{seq:04d}"
        r.source_entity_id = name_to_id.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = name_to_id.get(r.target_entity_id, r.target_entity_id)
