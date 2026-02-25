# K21 实施计划 — 实体/关系抽取

> **任务编号**: K21
> **前置依赖**: K16（692 条知识片段）、K17（235 条工序模板）、K18（84 条规范标准）
> **下游消费者**: K22（LightRAG 知识图谱构建）
> **核心关系**: 工序→设备、工序→危险源、危险源→安全措施
> **交付物**: `knowledge_graph/entities.json` + `relations.json`

---

## 摘要

从已有知识库和知识片段中抽取结构化实体与关系三元组，采用**双路抽取策略**：
1. **规则解析**（P0）— 从已结构化 Markdown 表格（`safety_knowledge/`、`quality/`、`process_references/`）中解析实体和关系，置信度高
2. **LLM 抽取**（P1）— 从 `fragments.jsonl` 中 Ch6/Ch7/Ch8 高密度片段中用 LLM 补充抽取隐式关系

预期产出：≥100 个标准化实体、≥200 条关系三元组，按 4 大工程类型分类。

---

## 审查点

| # | 问题 | 默认方案 | 需确认 |
|---|------|---------|--------|
| 1 | K21 是否包含"工序→质量要点"关系？ | 包含（`quality_control_points.md` 数据已就绪） | 是否扩展到 4 种关系 |
| 2 | 实体命名标准化策略？ | LLM 辅助归一化（同义词合并） | 是否需要人工审核种子词表 |
| 3 | LLM 抽取范围？ | 仅 Ch6/Ch7/Ch8 的 high 密度片段（约 260 条） | 是否包含 medium 密度片段 |
| 4 | 输出格式是否需要兼容 LightRAG 导入？ | JSON 格式，K22 负责适配 LightRAG API | 是否现在就定义 LightRAG schema |

---

## 拟议变更

### 新增文件

| 文件 | 说明 | 标注 |
|------|------|------|
| `entity_extraction/__init__.py` | 包初始化 | [NEW] |
| `entity_extraction/__main__.py` | 管道入口 (`python -m entity_extraction`) | [NEW] |
| `entity_extraction/schema.py` | Pydantic 数据模型（Entity, Relation, KnowledgeGraph） | [NEW] |
| `entity_extraction/rule_extractor.py` | 规则解析器：从结构化 Markdown 表格解析实体/关系 | [NEW] |
| `entity_extraction/llm_extractor.py` | LLM 抽取器：从 fragments.jsonl 非结构化文本抽取 | [NEW] |
| `entity_extraction/normalizer.py` | 实体标准化与去重（同义词合并、ID 统一） | [NEW] |
| `entity_extraction/pipeline.py` | 管道编排（规则抽取→LLM 抽取→合并→标准化→输出） | [NEW] |
| `entity_extraction/config.py` | 配置常量（LLM 参数、抽取范围、阈值） | [NEW] |
| `docs/knowledge_base/knowledge_graph/entities.json` | 输出：标准化实体库 | [NEW] |
| `docs/knowledge_base/knowledge_graph/relations.json` | 输出：关系三元组库 | [NEW] |
| `docs/knowledge_base/knowledge_graph/extraction_report.md` | 输出：抽取统计报告 | [NEW] |
| `tests/test_entity_extraction.py` | 单元测试 | [NEW] |

### 无需修改的已有文件

已有代码（`knowledge_extraction/`、`review/`）无需任何变更。K21 是独立的新模块。

---

## 详细设计

### 1. 数据模型 (`schema.py`)

```python
class Entity(BaseModel):
    """知识图谱实体"""
    id: str                          # 格式: "{type}_{eng_type_abbr}_{seq:03d}"
    type: Literal["process", "equipment", "hazard", "safety_measure", "quality_point"]
    name: str                        # 标准化名称
    aliases: list[str] = []          # 同义词列表
    engineering_type: str            # 工程类型（变电土建/变电电气/线路塔基/特殊作业）
    attributes: dict[str, str] = {}  # 附加属性（参数、等级等）
    source: str                      # 来源标识（rule/llm）
    confidence: float                # 0.0-1.0

class Relation(BaseModel):
    """知识图谱关系三元组"""
    id: str                          # 格式: "rel_{seq:04d}"
    source_entity_id: str            # 起点实体 ID
    target_entity_id: str            # 终点实体 ID
    relation_type: Literal[
        "requires_equipment",        # 工序→需要→设备
        "produces_hazard",           # 工序→产生→危险源
        "mitigated_by",              # 危险源→对应→安全措施
        "requires_quality_check",    # 工序→要求→质量要点
    ]
    confidence: float
    evidence: str                    # 原文证据片段
    source_doc: str                  # 来源文档/文件

class KnowledgeGraph(BaseModel):
    """完整知识图谱"""
    entities: list[Entity]
    relations: list[Relation]
    metadata: dict                   # 统计信息
```

### 2. 规则解析器 (`rule_extractor.py`)

**数据源与解析策略**：

| 数据源 | 解析方法 | 抽取内容 | 预估产出 |
|--------|---------|---------|---------|
| `safety_knowledge/hazard_sources.md` | Markdown 表格正则解析 | 作业活动→工序；危险因素→危险源；控制措施→安全措施；三者间关系 | ~46 条危险源 + ~46 条 produces_hazard + ~46 条 mitigated_by |
| `safety_knowledge/safety_measures.md` | Markdown 表格正则解析 | 措施内容→安全措施实体（补充通用措施） | ~40 条安全措施 |
| `quality/quality_control_points.md` | Markdown 表格正则解析 | 工序→质量要点关系 | ~30 条 requires_quality_check |
| `process_references/*.md` (4 个文件) | 表格 + 标题解析 | 工序实体 + 设备/参数属性 | ~50 条工序 + ~30 条 requires_equipment |

**Markdown 表格解析算法**：

```
1. 按 "## N." 或 "### N.N" 分割章节
2. 识别表格区域（"|" 开头的连续行）
3. 解析表头确定列映射（作业活动→process, 危险因素→hazard, 控制措施→safety_measure）
4. 逐行提取实体和关系
5. 按章节归属的工程类型标注 engineering_type
```

**关键函数**：
- `parse_hazard_sources(filepath) -> tuple[list[Entity], list[Relation]]`
- `parse_safety_measures(filepath) -> list[Entity]`
- `parse_quality_points(filepath) -> tuple[list[Entity], list[Relation]]`
- `parse_process_references(dirpath) -> tuple[list[Entity], list[Relation]]`

**hazard_sources.md 表格映射关系**：

```
表格行:
| 序号 | 作业活动 | 危险因素 | 可能事故 | 等级 | 控制措施 |

映射:
  作业活动 → Entity(type="process")
  危险因素 → Entity(type="hazard", attributes={"risk_level": 等级, "accident_type": 可能事故})
  控制措施 → Entity(type="safety_measure")
  作业活动→危险因素 → Relation(type="produces_hazard")
  危险因素→控制措施 → Relation(type="mitigated_by")
```

### 3. LLM 抽取器 (`llm_extractor.py`)

**抽取范围**：fragments.jsonl 中章节为"六、施工方法"/"七、质量管理"/"八、安全管理"且 density=high 的片段（约 260 条）

**Prompt 设计**（结构化 JSON 输出）：

```
SYSTEM: 你是施工领域知识图谱抽取专家。从给定施工方案文本中抽取实体和关系。

实体类型:
- process: 施工工序/作业活动（如：钻孔、清孔、混凝土浇筑、钢筋笼下放、吊装就位）
- equipment: 施工设备/工具（如：旋转钻机、QY160起重机、振动棒、电焊机）
- hazard: 危险源/危险因素（如：坍塌、触电、高处坠落、物体打击）
- safety_measure: 安全措施/控制手段（如：系安全带、设防护栏、一机一闸一漏一箱）

关系类型:
- requires_equipment: 工序→需要→设备
- produces_hazard: 工序→产生→危险源
- mitigated_by: 危险源→对应→安全措施

要求:
1. 只抽取文本中明确提到或可直接推断的实体和关系，不要过度推测
2. 实体名称使用简洁标准化表述（去掉"的""进行"等虚词）
3. 每条关系必须附带原文证据（不超过50字）

输出严格 JSON:
{
  "entities": [{"type": "...", "name": "...", "attributes": {...}}],
  "relations": [{"source": "实体名", "target": "实体名", "type": "...", "evidence": "..."}]
}

如果文本中无可抽取的实体/关系，返回 {"entities": [], "relations": []}
```

**USER**: `[工程类型: {engineering_type}] [章节: {chapter}]\n{content[:3000]}`

**并发策略**：ThreadPoolExecutor(max_workers=8)，复用 K16 的 LLM 调用模式。每条片段独立调用，失败重试 3 次。

**JSON 解析容错**：
- 尝试 `json.loads()` 直接解析
- 失败则正则提取 `{...}` 块
- 仍失败则记录 WARNING，跳过该片段

### 4. 实体标准化与去重 (`normalizer.py`)

**标准化流程**：

```
1. 名称归一化
   - 去除冗余修饰词（"进行""相关""的""作业"等后缀）
   - 统一术语（"混凝土灌注" = "混凝土浇筑" = "浇筑混凝土"）
   - 对齐表述风格（动词+宾语 格式，如"钻孔""浇筑""吊装"）

2. 实体去重（同类型 + 同工程类型内）
   - 精确匹配：name 完全相同 → 合并（aliases 取并集）
   - 模糊匹配：编辑距离 ≤ 2 且同 engineering_type → 候选合并
   - 多源确认：规则+LLM 都抽取到的实体，confidence += 0.1

3. 关系去重
   - (source_id, target_id, relation_type) 三元组相同 → 合并
   - 保留 confidence 较高、evidence 更具体的记录
```

**种子词表**（内置于 config.py，基于已有知识库数据）：

| 类型 | 种子词 | 用途 |
|------|--------|------|
| process | 钻孔、清孔、浇筑、吊装、焊接、绑扎、养护、振捣、抹灰、涂装、开挖、支护 | 工序实体识别锚点 |
| equipment | 钻机、起重机、振动棒、电焊机、搅拌机、泵车、经纬仪、脚手架、模板 | 设备实体识别锚点 |
| hazard | 坍塌、高处坠落、触电、物体打击、机械伤害、中毒窒息、火灾、倾覆 | 危险源识别锚点 |
| safety_measure | 安全带、防护栏、安全网、漏电保护器、警戒区、通风检测、安全帽 | 措施识别锚点 |

### 5. 管道编排 (`pipeline.py`)

```
Step 1: 规则抽取（~秒级）
  ├─ parse_hazard_sources()     → entities_1, relations_1   [hazard_sources.md]
  ├─ parse_safety_measures()    → entities_2                [safety_measures.md]
  ├─ parse_quality_points()     → entities_3, relations_3   [quality_control_points.md]
  └─ parse_process_references() → entities_4, relations_4   [process_references/*.md]
  日志: "规则抽取完成: {N} 实体, {M} 关系"

Step 2: LLM 抽取（~分钟级，并发 8 线程）
  ├─ 加载 fragments.jsonl
  ├─ 过滤: chapter ∈ {六/七/八} AND density = "high"
  └─ 并发 LLM 调用 → entities_5, relations_5
  日志: "LLM 抽取完成: {N} 实体, {M} 关系, {F} 失败"

Step 3: 合并
  └─ all_entities = Σ(entities_1~5), all_relations = Σ(relations_1~5)

Step 4: 标准化与去重
  ├─ normalize_entities(all_entities)  → 去重后实体列表
  └─ normalize_relations(all_relations, entity_id_map)  → 更新 ID 引用
  日志: "标准化: {去重前}→{去重后} 实体, {去重前}→{去重后} 关系"

Step 5: 分配 ID + 序列化
  ├─ knowledge_graph/entities.json
  ├─ knowledge_graph/relations.json
  └─ knowledge_graph/extraction_report.md
  日志: "输出完成: entities.json ({N}), relations.json ({M})"
```

### 6. 配置 (`config.py`)

```python
# --- 抽取范围 ---
EXTRACT_CHAPTERS = ["六、施工方法及工艺要求", "七、质量管理与控制措施", "八、安全文明施工管理"]
EXTRACT_DENSITY = ["high"]
FRAGMENTS_PATH = "docs/knowledge_base/fragments/fragments.jsonl"

# --- 结构化数据源 ---
HAZARD_SOURCES_PATH = "docs/knowledge_base/safety_knowledge/hazard_sources.md"
SAFETY_MEASURES_PATH = "docs/knowledge_base/safety_knowledge/safety_measures.md"
QUALITY_POINTS_PATH = "docs/knowledge_base/quality/quality_control_points.md"
PROCESS_REFS_DIR = "docs/knowledge_base/process_references/"

# --- LLM 配置 ---
LLM_MAX_WORKERS = 8
LLM_TEMPERATURE = 0.1
LLM_MAX_RETRIES = 3
LLM_CONTENT_MAX_CHARS = 3000  # 片段截断长度

# --- 标准化 ---
FUZZY_MATCH_THRESHOLD = 2           # 编辑距离阈值
MULTI_SOURCE_CONFIDENCE_BOOST = 0.1 # 多源确认置信度提升

# --- 输出 ---
OUTPUT_DIR = "docs/knowledge_base/knowledge_graph/"
```

---

## 验证计划

### 自动化测试

```bash
# 单元测试（schema 验证 + 规则解析 + 标准化逻辑）
conda run -n sca pytest tests/test_entity_extraction.py -v

# 端到端管道运行
conda run -n sca python -m entity_extraction

# 验证输出
conda run -n sca python -c "
import json
entities = json.load(open('docs/knowledge_base/knowledge_graph/entities.json'))
relations = json.load(open('docs/knowledge_base/knowledge_graph/relations.json'))
print(f'实体数: {len(entities)}')
print(f'关系数: {len(relations)}')
assert len(entities) >= 100, f'实体数不足: {len(entities)}'
assert len(relations) >= 200, f'关系数不足: {len(relations)}'
"

# 代码质量
conda run -n sca ruff check entity_extraction/
conda run -n sca ruff format --check entity_extraction/
```

### 质量验收标准

| 指标 | 目标值 | 验证方式 |
|------|--------|---------|
| 实体总数 | ≥100 | 自动统计 |
| 关系总数 | ≥200 | 自动统计 |
| hazard_sources.md 解析覆盖率 | 100% 表格行 | 行数对比（46 行→46 组三元组） |
| LLM 抽取成功率 | ≥90% 片段成功解析 JSON | 失败计数 |
| 实体去重率 | 去重后 < 合并前 80% | 前后对比 |
| 4 大工程类型均有覆盖 | 每种 ≥10 个实体 | 分类统计 |
| 3 种核心关系均有覆盖 | 每种 ≥30 条 | 分类统计 |
| 测试覆盖率 | ≥80% | pytest --cov |

### 抽样验证

从输出中随机抽取 20 条关系，对照原文验证：
- 实体名称是否准确
- 关系类型是否正确
- evidence 是否匹配原文

---

## 实施步骤

| 步骤 | 内容 | 前置依赖 |
|------|------|---------|
| 1 | 创建 `entity_extraction/` 模块骨架 + `schema.py` + `config.py` | 无 |
| 2 | 实现 `rule_extractor.py`（4 个数据源的 Markdown 表格解析） | Step 1 |
| 3 | 编写 `tests/test_entity_extraction.py` 规则解析测试（TDD） | Step 2 |
| 4 | 实现 `llm_extractor.py`（Prompt + 并发 + JSON 解析容错） | Step 1 |
| 5 | 实现 `normalizer.py`（名称归一化 + 实体去重 + 关系去重） | Step 2, 4 |
| 6 | 实现 `pipeline.py` + `__main__.py`（管道编排 5 步） | Step 2, 4, 5 |
| 7 | 端到端运行，生成 `knowledge_graph/*.json` | Step 6 |
| 8 | 编写 `extraction_report.md` 统计报告，验证质量指标 | Step 7 |
| 9 | 补充测试用例，确保覆盖率 ≥80% | Step 7 |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 输出 JSON 格式不稳定 | 解析失败率高 | 正则提取 JSON 块 + 重试 3 次 + 跳过并记录 |
| 实体命名不一致（"混凝土浇筑"vs"浇筑混凝土"） | 同一实体多条记录 | 种子词表锚定 + 编辑距离合并 + LLM 确认 |
| Markdown 表格格式不完全统一 | 规则解析遗漏行 | 为每个数据源编写定制解析器，测试覆盖每个文件 |
| LLM API 调用量（~260 次） | 耗时和成本 | 仅 high 密度片段；8 线程并发；预估 10-15 分钟 |
| 跨工程类型实体重复（如"高处坠落"出现在所有类型） | 去重逻辑复杂 | 跨工程类型的通用实体标记为 engineering_type="通用" |

---

## 上游数据资产清单

| 数据源 | 路径 | 内容 | 记录数 | K21 用途 |
|--------|------|------|--------|---------|
| 知识片段 | `fragments/fragments.jsonl` | 692 条结构化片段 | 692 | LLM 抽取原料 |
| 危险源清单 | `safety_knowledge/hazard_sources.md` | 4 类工程 × 危险因素表 | 46 行 | 规则抽取：工序→危险源→安全措施 |
| 安全措施库 | `safety_knowledge/safety_measures.md` | 6 类安全措施表 | ~40 行 | 规则抽取：补充安全措施实体 |
| 质量控制点 | `quality/quality_control_points.md` | 4 类工程质量要点表 | ~30 行 | 规则抽取：工序→质量要点 |
| 工艺参考 | `process_references/*.md` (4 文件) | 工艺参数表 | ~80 行 | 规则抽取：工序+设备实体 |

---

## 与后续任务的关系

| 下游任务 | 依赖方式 |
|---------|---------|
| **K22** LightRAG 知识图谱构建 | 导入 entities.json + relations.json 为 LightRAG 节点和边 |
| **S10** KnowledgeRetriever.infer_rules() | 基于知识图谱实现"输入工程类型→输出安全/质量清单"推理 |
| **审核系统** 合规性检查 | 匹配施工方案中的工序→验证是否覆盖对应危险源和安全措施 |

---

*计划创建：2026-02-25 | 基于 K16 知识片段 + safety_knowledge/ + quality/ + process_references/ + 05-knowledge-base.md 架构设计*
