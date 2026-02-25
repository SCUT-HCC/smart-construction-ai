<!-- Generated: 2026-02-25 | Files scanned: output/, templates/, docs/, eval/ | Token estimate: ~750 -->

# 数据结构与存储

## 存储架构

```
文件系统 ──→ SQLite (qmd.db) ──→ LightRAG (lightrag_storage/)
 ↓              ↓                     ↓
PDF/MD/JSON   向量库 8 Collection   知识图谱 1977 节点 + 1206 边
```

## 文件系统

### 输入数据

```
data/1.pdf ~ 16.pdf              # 16 份施工方案 PDF（178MB）
```

### 清洗输出

```
output/N/raw.md → regex.md → final.md    # 每份 PDF 三阶段产物
```

### 知识片段（K16 产出）

**路径**: `docs/knowledge_base/fragments/fragments.jsonl` (692 条)

```json
{
  "id": "doc01_ch6_s01",
  "source_doc": 1,
  "chapter": "六、施工方法及工艺要求",
  "section": "6.1 混凝土浇筑",
  "engineering_type": "变电土建",
  "density": "high",
  "tags": ["混凝土", "浇筑"],
  "content": "..."
}
```

### 实体/关系（K21 产出）

**路径**: `docs/knowledge_base/knowledge_graph/`

| 文件 | 条目 | 格式 |
|------|------|------|
| `entities.json` | 2019 实体 | `{id, type, name, engineering_type, attributes, aliases}` |
| `relations.json` | 1452 关系 | `{source_entity_id, target_entity_id, relation_type, evidence}` |

实体类型: process / equipment / hazard / safety_measure / quality_point

## 向量数据库（K23 - qmd + sqlite-vec）

**路径**: `docs/knowledge_base/vector_store/qmd.db`
**嵌入**: Qwen3-Embedding-0.6B (1024 维)
**检索**: BM25 + 向量混合, top_k=3, threshold=0.6

| Collection | 内容 | 文档数 |
|-----------|------|--------|
| ch01_basis | 编制依据标准 | 18 |
| ch06_methods | 施工方法工艺 + 模板 | 239 |
| ch07_quality | 质量管理措施 | 86 |
| ch08_safety | 安全措施与危险源 | 89 |
| ch09_emergency | 应急处置措施 | 92 |
| ch10_green | 绿色施工 | 45 |
| equipment | 设备参数表 | 65 |
| templates | 通用模板段落 | 72 |
| **合计** | | **706** |

## 知识图谱（K22 - LightRAG）

**路径**: `docs/knowledge_base/lightrag_storage/`
**统计**: 1977 节点 + 1206 边

```
工程类型 → 包含 → 施工工序 → 需要 → 设备
                    ↓
              产生 → 危险源 → 对应 → 安全措施
                    ↓
              要求 → 质量要点
```

## 标准模板与知识库

```
templates/
├─ standard_50502.md        # GB/T 50502 标准 10 章节
└─ naming_conventions.md    # 章节命名规范

docs/knowledge_base/
├─ writing_guides/          # Ch1-10 撰写指南
│  └─ ch06_templates/       # 4 大工程类型模板（235 fragments）
├─ compliance_standards/    # 84 条结构化规范标准（K18）
│  └─ standards_database.json
├─ process_references/      # 工艺参考库
├─ organization/            # 组织架构
├─ quality/                 # 质量管理
├─ safety_knowledge/        # 安全管理
└─ emergency/               # 应急管理
```

## 评测数据（K20）

**路径**: `eval/embedding/`

| 文件 | 内容 |
|------|------|
| `eval_dataset.jsonl` | 100 组 query-passage 评测对 |
| `results/combined_*.json` | E2E MRR@3=0.8683, 显存 2.3GB |

## 质量指标

| 指标 | 值 |
|------|-----|
| 字数保留率 | ≥50% |
| 知识片段 | 692 条 |
| 实体/关系 | 2019/1452 |
| 向量库文档 | 706 |
| 图谱覆盖率 | 83% |
| 向量库覆盖率 | 86% |
| E2E MRR@3 | 0.8683 |
