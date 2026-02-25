<!-- Generated: 2026-02-25 | Files scanned: 52 Python modules | Token estimate: ~900 -->

# 系统架构 - 南网施工方案智能辅助系统

## 项目类型

单体应用（MVP）- PDF 清洗 + 知识提取 + 实体关系抽取 + 向量库 + 知识图谱 + 统一检索

## 核心数据流

### 数据流 1: PDF 清洗管道（Phase 1 - 已完成）

```
PDF → OCR → 正则清洗 → LLM 语义清洗 → 质量验证 → Markdown
 ↓       ↓          ↓            ↓           ↓          ↓
data/  raw.md    regex.md     final.md    日志系统   output/N/
```

### 数据流 2: 知识提取管道（Phase 2 - 已完成）

```
final.md → 章节分割 → 元数据标注 → 密度评估 → 精炼 → 去重 → fragments.jsonl
                                                                   692 条
```

### 数据流 3: 实体/关系抽取（Phase 2 - K21 完成）

```
fragments.jsonl → 规则抽取 + LLM 抽取 → 归一化 → entities.json + relations.json
                                                   2019 实体      1452 关系
```

### 数据流 4: 知识库构建（Phase 2 - K22/K23 完成）

```
entities.json ──→ LightRAG 导入 ──→ 知识图谱（1977 节点 + 1206 边）
relations.json ┘                     ↓
                                KGRetriever（图遍历推理 + LLM 查询）

fragments.jsonl ──→ qmd 索引 ──→ 8 Collection 向量库（706 文档，741 chunks）
                                  ↓
                              VectorRetriever（BM25 + 向量混合检索）
```

### 数据流 5: 统一检索（S10 完成）

```
查询请求 → KnowledgeRetriever.retrieve()
              ├─ KGRetriever → 强制规范 (priority=1)
              ├─ VectorRetriever → 参考案例 (priority=2) / 模板 (priority=3)
              └─ 融合排序 → RetrievalResponse
```

## 模块边界

```
┌─────────────────────────────────────────────────────────────┐
│                      入口层 (Entry)                          │
│  main.py (50)              - PDF 清洗入口                   │
│  knowledge_extraction/     - 知识提取入口                    │
│  entity_extraction/        - 实体抽取入口                    │
│  vector_store/             - 向量库构建入口                  │
│  knowledge_graph/          - 知识图谱构建入口                │
└─────────────────────────────────────────────────────────────┘
               │
    ┌──────────┼──────────┬───────────────┐
    ▼          ▼          ▼               ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────────┐
│Phase 1 │ │Phase 2 │ │Phase 2   │ │  知识库层     │
│PDF清洗 │ │知识提取│ │实体抽取  │ │              │
│5 files │ │7 files │ │6 files   │ │vector_store/ │
│(710行) │ │(1397行)│ │(1891行)  │ │knowledge_graph│
└────────┘ └────────┘ └──────────┘ │knowledge_    │
                                    │  retriever/  │
                                    │review/       │
                                    └──────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                   基础设施层 (Infrastructure)                │
│  config.py (45) - 全局配置（LLM/OCR/清洗）                 │
│  utils/logger_system.py (48) - log_msg() / log_json()      │
└─────────────────────────────────────────────────────────────┘
```

## 外部依赖

| 服务 | 用途 | 端点 |
|------|------|------|
| MonkeyOCR | PDF → Markdown | localhost:7861/parse |
| DeepSeek LLM | 清洗/评估/精炼/抽取 | 110.42.53.85:11081/v1 |
| Docker | OCR 容器 | monkeyocr-api |
| Qwen3-Embedding-0.6B | 向量嵌入 (1024 维) | 本地 GPU |
| Qwen3-Reranker-0.6B | 重排序 | 本地 GPU |

## 数据资源

| 路径 | 内容 | 状态 |
|------|------|------|
| `data/` | 16 份 PDF（178MB） | 原始输入 |
| `output/1-16/` | 清洗后 Markdown | 金标准 |
| `docs/knowledge_base/fragments/` | 692 条知识片段 | K16 产出 |
| `docs/knowledge_base/knowledge_graph/` | 2019 实体 + 1452 关系 | K21 产出 |
| `docs/knowledge_base/vector_store/qmd.db` | 8 Collection 向量库 | K23 产出 |
| `docs/knowledge_base/lightrag_storage/` | LightRAG 持久化 | K22 产出 |
| `templates/` | GB/T 50502 标准模板 | 10 章节 |
| `docs/knowledge_base/compliance_standards/` | 84 条规范标准 | K18 产出 |

## 下一阶段

| Phase | 目标 |
|-------|------|
| Phase 3 | 施工方案生成 demo（LangGraph 多智能体） |
| Phase 4 | 施工方案审核系统 |
| Phase 5 | 中期检查（2026-06-30） |
