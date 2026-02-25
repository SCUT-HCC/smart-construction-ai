<!-- Generated: 2026-02-25 | Files scanned: 27 modules + eval infrastructure | Token estimate: ~850 -->

# 系统架构 - 南网施工方案智能辅助系统

## 项目类型

单体应用（MVP）- PDF 清洗管道 + 知识提取管道 + 向量检索评测框架 + 单元测试

## 核心数据流

### 数据流 1: PDF 清洗管道（Phase 1 - 已完成）

```
PDF 输入 → OCR 识别 → 正则清洗 → LLM 语义清洗 → 质量验证 → Markdown 输出
   ↓           ↓           ↓            ↓              ↓            ↓
data/      raw.md     regex.md     final.md       日志系统    output/N/
```

### 数据流 2: 知识提取管道（Phase 2 - 已完成）

```
final.md → 章节分割 → 元数据标注 → 密度评估 → 内容精炼 → 去重 → fragments.jsonl
   ↓          ↓           ↓           ↓          ↓         ↓        ↓
output/   Section[]   +metadata   high/med/low  refined   unique   692 条片段
```

### 数据流 3: 向量检索评测（Phase 2b - K20 完成）

```
fragments.jsonl → [嵌入 + Reranker 模型评测] → 模型选型 → E2E 指标
     ↓                    ↓                        ↓         ↓
eval_dataset.jsonl  eval_embedding_models.py   Qwen3-0.6B  MRR@3=0.8683
                    eval_reranker_models.py     双模型组  Hit@1=82%
                    eval_combined_pipeline.py    合    Hit@3=92%
```

## 模块边界

```
┌─────────────────────────────────────────────────────────────┐
│                      入口层 (Entry)                          │
│  main.py (50 行) - PDF 清洗入口                              │
│  knowledge_extraction/__main__.py (5 行) - 知识提取入口       │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│  PDF 清洗层 (Phase 1)     │  │  知识提取层 (Phase 2)         │
│  processor.py (90 行)     │  │  pipeline.py (308 行)         │
│  ├─ crawler.py (69)       │  │  ├─ chapter_splitter.py (253) │
│  ├─ cleaning.py (434)     │  │  ├─ metadata_annotator.py(113)│
│  └─ verifier.py (67)      │  │  ├─ density_evaluator.py(205) │
│                           │  │  ├─ content_refiner.py (174)  │
│                           │  │  └─ deduplicator.py (163)     │
└──────────────────────────┘  └──────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   基础设施层 (Infrastructure)                │
│  config.py (45 行) - 全局配置                                │
│  knowledge_extraction/config.py (176 行) - 知识提取配置       │
│  utils/logger_system.py (48 行) - 日志系统                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   测试层 (Tests)                              │
│  tests/conftest.py (66 行) - 共享 fixtures                   │
│  tests/test_cleaning.py (369 行) - 清洗测试                  │
│  tests/test_verifier.py (145 行) - 验证测试                  │
│  tests/test_knowledge_extraction.py (368 行) - 知识提取测试   │
└─────────────────────────────────────────────────────────────┘
```

## 外部依赖

| 服务 | 用途 | 端点 |
|------|------|------|
| MonkeyOCR | PDF → Markdown 转换 | http://localhost:7861/parse |
| DeepSeek LLM | 语义清洗 / 密度评估 / 内容精炼 | http://110.42.53.85:11081/v1 |
| Docker | OCR 服务容器化 | monkeyocr-api |

## 数据资源

| 路径 | 内容 | 用途 |
|------|------|------|
| `data/` | 16 份施工方案 PDF（178MB） | 原始输入 |
| `output/1-16/` | 清洗后的 Markdown | 金标准样本 |
| `output/fragments.jsonl` | 692 条结构化知识片段 | 知识库原料 |
| `templates/` | GB/T 50502 标准模板 | 10 章节规范 |
| `docs/knowledge_base/` | 撰写指南 + 参考资料 | 生成系统素材 |
| `compliance_standards/standards_database.json` | 84 条结构化规范标准 | 时效性检查数据库 |

## 下一阶段（Phase 3-5）

### Phase 3: qmd 集成（向量检索）
- **嵌入模型**: Qwen3-Embedding-0.6B（已选型，K20 评测）
- **Reranker**: Qwen3-Reranker-0.6B（E2E MRR@3=0.8683，显存 2.3GB）
- **向量库**: qmd + sqlite-vec，按章节分 collection
- **检索参数**: top_k=3, threshold=0.6, 支持按章节/工程类型过滤

### Phase 4: LightRAG 集成（知识图谱）
- 工序 → 设备 / 危险源 / 质量要点 / 规范
- 知识推理：输入工程类型 → 输出安全/质量/设备清单

### Phase 5: LangGraph 多智能体
- 检测 Agent：章节完整性、依据时效性、合规性
- 生成 Agent：信息提取、内容生成、质量校验
