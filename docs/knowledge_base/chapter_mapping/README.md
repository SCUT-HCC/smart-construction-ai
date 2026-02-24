# 章节标题映射规则库

> K19 知识工程产出 | 2026-02-24

## 用途

将施工方案中的**实际章节标题**映射到**标准 10 章结构**（Ch1-Ch10）。

- **审核系统**：`review/chapter_mapper.py` 的 `ChapterMapper` 加载此规则库
- **知识提取**：`knowledge_extraction/config.py` 也从此文件加载，保持规则一致

## 文件说明

| 文件 | 说明 |
|------|------|
| `mapping_rules.json` | 结构化映射规则库（机器可读） |
| `README.md` | 本文件 |

## 规则结构

每个章节（Ch1-Ch10）包含：

| 字段 | 说明 |
|------|------|
| `rules[].type` | `exact`（精确匹配，confidence=1.0）/ `variant`（变体，0.8）/ `regex`（正则，0.8） |
| `rules[].keywords` | 关键词列表，标题包含任一关键词即命中 |
| `rules[].patterns` | 正则模式列表（仅 regex 类型） |
| `exclusions` | 排除关键词：命中则**不**映射到该章节 |
| `sub_section_indicators` | 子章节特征词：辅助子章节继承判断 |

## 匹配优先级

```
1. 排除规则检查（全局 + 章节级） → 命中则标记 "excluded"
2. L1 精确匹配（exact keywords）  → confidence = 1.0
3. L2 变体匹配（variant keywords）→ confidence = 0.8
4. L3 正则匹配（regex patterns） → confidence = 0.8
5. L4 子章节继承（父标题已映射）  → confidence = 父级
6. L5 (预留) LLM 语义兜底          → confidence = 0.6
7. 未映射                          → "unmapped"
```

## 统计数据

基于 14 份文档（跳过 DOC 13/14）1217 个有效片段测试：

| 指标 | 数值 |
|------|------|
| L1 精确命中 | 190 (15.6%) |
| L2 变体命中 | 147 (12.1%) |
| 直接命中合计 | 337 (27.7%) |
| 子章节继承 | 871 |
| 真正未映射 | 9 (封面残留) |
| **含继承覆盖率** | **99.3%** |

## 维护指南

### 新增关键词

1. 在对应章节的 `rules` 数组中添加
2. `type` 选择：若为标准名称的核心词用 `exact`，否则用 `variant`
3. 必须在 `tests/test_chapter_mapper.py` 中添加对应测试用例
4. 运行回归测试确认不引入误映射

### 新增排除规则

1. 在 `global_exclusions` 或对应章节的 `exclusions` 中添加
2. 全局排除用于封面/公司名等
3. 章节排除用于该章节特有的误匹配词
