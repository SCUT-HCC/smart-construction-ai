"""构造嵌入模型评测数据集。

从 692 条知识片段中按章节×工程类型分层抽样，用 LLM 生成检索查询，
构造 hard negatives，输出 query-passage 评测对。

用法：
    conda run -n sca python scripts/build_eval_dataset.py \
        --fragments docs/knowledge_base/fragments/fragments.jsonl \
        --output eval/embedding/eval_dataset.jsonl \
        --sample-size 100
"""

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from openai import OpenAI

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import LLM_CONFIG

# ── 章节抽样配额 ──────────────────────────────────────────────────────────
CHAPTER_QUOTAS: dict[str, int] = {
    "一、编制依据": 5,
    "二、工程概况": 3,
    "三、施工组织机构及职责": 3,
    "四、施工安排与进度计划": 4,
    "五、施工准备": 8,
    "六、施工方法及工艺要求": 30,
    "七、质量管理与控制措施": 15,
    "八、安全文明施工管理": 15,
    "九、应急预案与处置措施": 12,
    "十、绿色施工与环境保护": 5,
}

# 长文本保障配额
LONG_TEXT_MIN_512 = 15   # ≥15 条 >512 字
LONG_TEXT_MIN_1024 = 5   # ≥5 条 >1024 字

# LLM 查询生成 Prompt
QUERY_GEN_PROMPT = """你是一位电力工程施工方案编制专家。给定一段施工知识片段，请生成一个自然语言检索查询，
使得该查询在知识库中能精准命中这段内容。

要求：
- 查询应模拟实际工程师在编写施工方案时的检索意图
- 使用专业术语但保持口语化
- 长度 15-40 字
- 不要使用引号

片段内容：
{content}

章节：{chapter}
工程类型：{engineering_type}
标签：{tags}

请直接输出查询语句，不要解释。"""


def load_fragments(path: str) -> list[dict[str, Any]]:
    """加载知识片段 JSONL 文件。"""
    fragments = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                fragments.append(json.loads(line))
    return fragments


def stratified_sample(
    fragments: list[dict[str, Any]],
    quotas: dict[str, int],
    long_512_min: int = LONG_TEXT_MIN_512,
    long_1024_min: int = LONG_TEXT_MIN_1024,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """按章节配额 + 长文本保障分层抽样。

    Args:
        fragments: 全量知识片段
        quotas: 章节 → 抽样数
        long_512_min: >512字片段的最少数量
        long_1024_min: >1024字片段的最少数量
        seed: 随机种子

    Returns:
        抽样后的片段列表
    """
    rng = random.Random(seed)

    # 按章节分组
    by_chapter: dict[str, list[dict]] = defaultdict(list)
    for frag in fragments:
        ch = frag.get("chapter", "")
        if ch and frag.get("char_count", 0) > 10:  # 排除空片段
            by_chapter[ch].append(frag)

    sampled: list[dict[str, Any]] = []
    sampled_ids: set[str] = set()

    # 阶段 1：按章节配额抽样
    for chapter, quota in quotas.items():
        pool = by_chapter.get(chapter, [])
        if not pool:
            continue

        # 优先包含长文本
        long_pool = [f for f in pool if f.get("char_count", 0) > 512]
        short_pool = [f for f in pool if f.get("char_count", 0) <= 512]

        # 至少 1/3 来自长文本（如果有）
        long_quota = min(max(quota // 3, 1), len(long_pool))
        short_quota = quota - long_quota

        rng.shuffle(long_pool)
        rng.shuffle(short_pool)

        for frag in long_pool[:long_quota]:
            if frag["id"] not in sampled_ids:
                sampled.append(frag)
                sampled_ids.add(frag["id"])

        for frag in short_pool[:short_quota]:
            if frag["id"] not in sampled_ids:
                sampled.append(frag)
                sampled_ids.add(frag["id"])

    # 阶段 2：补充长文本保障
    long_512_count = sum(1 for s in sampled if s.get("char_count", 0) > 512)
    long_1024_count = sum(1 for s in sampled if s.get("char_count", 0) > 1024)

    if long_512_count < long_512_min:
        extra_pool = [
            f for f in fragments
            if f.get("char_count", 0) > 512 and f["id"] not in sampled_ids
        ]
        rng.shuffle(extra_pool)
        for frag in extra_pool[: long_512_min - long_512_count]:
            sampled.append(frag)
            sampled_ids.add(frag["id"])

    if long_1024_count < long_1024_min:
        extra_pool = [
            f for f in fragments
            if f.get("char_count", 0) > 1024 and f["id"] not in sampled_ids
        ]
        rng.shuffle(extra_pool)
        for frag in extra_pool[: long_1024_min - long_1024_count]:
            sampled.append(frag)
            sampled_ids.add(frag["id"])

    return sampled


def generate_query(
    fragment: dict[str, Any],
    client: OpenAI,
    model: str,
) -> str:
    """调用 LLM 为片段生成检索查询。

    Args:
        fragment: 知识片段
        client: OpenAI 兼容客户端
        model: 模型名

    Returns:
        生成的查询字符串
    """
    content = fragment.get("content", "")
    # 截断过长内容，避免 token 超限
    if len(content) > 2000:
        content = content[:2000] + "..."

    prompt = QUERY_GEN_PROMPT.format(
        content=content,
        chapter=fragment.get("chapter", ""),
        engineering_type=fragment.get("engineering_type", ""),
        tags=", ".join(fragment.get("tags", [])),
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=100,
    )

    query = response.choices[0].message.content.strip()
    # 去掉可能的引号
    query = query.strip('"').strip("'").strip(""").strip(""")
    return query


def build_hard_negatives(
    positive: dict[str, Any],
    all_fragments: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, str]]:
    """为正例构造 4 个 hard negatives。

    策略：
      1. same_chapter_diff_eng: 同章节不同工程类型
      2. diff_chapter_same_eng: 不同章节相同工程类型
      3. same_chapter_same_eng: 同章节同工程类型不同内容
      4. random: 随机负例

    Args:
        positive: 正例片段
        all_fragments: 全量片段
        rng: 随机数生成器

    Returns:
        hard negatives 列表
    """
    pos_id = positive["id"]
    pos_chapter = positive.get("chapter", "")
    pos_eng = positive.get("engineering_type", "")

    negatives: list[dict[str, str]] = []

    # 类型 1: 同章节不同工程类型
    pool1 = [
        f for f in all_fragments
        if f["id"] != pos_id
        and f.get("chapter") == pos_chapter
        and f.get("engineering_type") != pos_eng
        and f.get("char_count", 0) > 10
    ]
    if pool1:
        neg = rng.choice(pool1)
        negatives.append({"id": neg["id"], "type": "same_chapter_diff_eng"})

    # 类型 2: 不同章节相同工程类型
    pool2 = [
        f for f in all_fragments
        if f["id"] != pos_id
        and f.get("chapter") != pos_chapter
        and f.get("engineering_type") == pos_eng
        and f.get("char_count", 0) > 10
    ]
    if pool2:
        neg = rng.choice(pool2)
        negatives.append({"id": neg["id"], "type": "diff_chapter_same_eng"})

    # 类型 3: 同章节同工程类型不同内容
    pool3 = [
        f for f in all_fragments
        if f["id"] != pos_id
        and f.get("chapter") == pos_chapter
        and f.get("engineering_type") == pos_eng
        and f.get("char_count", 0) > 10
    ]
    if pool3:
        neg = rng.choice(pool3)
        negatives.append({"id": neg["id"], "type": "same_chapter_same_eng"})

    # 类型 4: 随机负例（不同章节不同工程类型）
    used_ids = {pos_id} | {n["id"] for n in negatives}
    pool4 = [
        f for f in all_fragments
        if f["id"] not in used_ids
        and f.get("chapter") != pos_chapter
        and f.get("char_count", 0) > 10
    ]
    if pool4:
        neg = rng.choice(pool4)
        negatives.append({"id": neg["id"], "type": "random"})

    # 如果某类型池为空，用随机填充到 4 个
    used_ids = {pos_id} | {n["id"] for n in negatives}
    fallback_pool = [
        f for f in all_fragments
        if f["id"] not in used_ids and f.get("char_count", 0) > 10
    ]
    rng.shuffle(fallback_pool)
    while len(negatives) < 4 and fallback_pool:
        neg = fallback_pool.pop()
        negatives.append({"id": neg["id"], "type": "fallback"})

    return negatives


def build_eval_dataset(
    fragments_path: str,
    output_path: str,
    sample_size: int = 100,
) -> None:
    """构造嵌入模型评测数据集。

    Args:
        fragments_path: 知识片段 JSONL 路径
        output_path: 输出评测数据集 JSONL 路径
        sample_size: 目标抽样数量（实际可能略有偏差）
    """
    print(f"加载片段: {fragments_path}")
    fragments = load_fragments(fragments_path)
    print(f"  总片段数: {len(fragments)}")

    # 分层抽样
    print(f"分层抽样 (目标 {sample_size} 条)...")
    sampled = stratified_sample(fragments, CHAPTER_QUOTAS)
    print(f"  抽样结果: {len(sampled)} 条")

    # 统计
    long_512 = sum(1 for s in sampled if s.get("char_count", 0) > 512)
    long_1024 = sum(1 for s in sampled if s.get("char_count", 0) > 1024)
    print(f"  >512字: {long_512} 条, >1024字: {long_1024} 条")

    by_ch: dict[str, int] = defaultdict(int)
    for s in sampled:
        by_ch[s.get("chapter", "未知")] += 1
    print("  按章节分布:")
    for ch, cnt in sorted(by_ch.items()):
        print(f"    {ch}: {cnt}")

    # 初始化 LLM 客户端
    client = OpenAI(
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
    )
    model = LLM_CONFIG["model"]
    print(f"\nLLM: {model} @ {LLM_CONFIG['base_url']}")

    # 生成查询 + 构造 hard negatives
    rng = random.Random(42)
    eval_items: list[dict[str, Any]] = []
    failed = 0

    for i, frag in enumerate(sampled):
        query_id = f"q{i+1:03d}"
        print(f"  [{i+1}/{len(sampled)}] {query_id}: {frag['id']} ({frag.get('chapter', '')[:8]}...) ", end="")

        try:
            query = generate_query(frag, client, model)
            hard_negs = build_hard_negatives(frag, fragments, rng)

            item = {
                "query_id": query_id,
                "query": query,
                "positive_id": frag["id"],
                "positive_chapter": frag.get("chapter", ""),
                "positive_engineering_type": frag.get("engineering_type", ""),
                "positive_char_count": frag.get("char_count", 0),
                "hard_negatives": hard_negs,
                "human_verified": False,
            }
            eval_items.append(item)
            print(f"→ {query[:40]}...")

        except Exception as e:
            failed += 1
            print(f"[FAILED] {e}")

        # 避免 API 限流
        time.sleep(0.3)

    # 输出
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in eval_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n评测数据集构造完成:")
    print(f"  成功: {len(eval_items)} 组")
    print(f"  失败: {failed} 组")
    print(f"  输出: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="构造嵌入模型评测数据集")
    parser.add_argument(
        "--fragments",
        default="docs/knowledge_base/fragments/fragments.jsonl",
        help="知识片段 JSONL 路径",
    )
    parser.add_argument(
        "--output",
        default="eval/embedding/eval_dataset.jsonl",
        help="输出评测数据集路径",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="抽样数量",
    )
    args = parser.parse_args()
    build_eval_dataset(args.fragments, args.output, args.sample_size)


if __name__ == "__main__":
    main()
