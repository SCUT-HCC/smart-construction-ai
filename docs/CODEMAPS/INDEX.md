<!-- Generated: 2026-02-25 | Files scanned: 52 Python modules | Token estimate: ~1200 -->

# 代码地图索引 - 南网施工方案智能辅助系统

## 项目概览

**南网施工方案智能辅助系统** (smart-construction-ai) — MVP 级 Python 应用，实现 PDF 清洗、知识提取、实体关系抽取、向量库+知识图谱构建、统一检索接口。

- **技术栈**: Python 3.11 + qmd + LightRAG + LangChain/LangGraph（待集成）
- **Conda 环境**: `sca`
- **测试**: pytest 422 passed
- **当前阶段**: Phase 2 完成（知识库构建 + 统一检索）→ Phase 3（生成 demo）

---

## 代码地图导航

### 1. architecture.md - 系统架构

```
├─ 项目类型: 单体应用 MVP
├─ 数据流 1: PDF → OCR → 清洗 → Markdown
├─ 数据流 2: Markdown → 知识提取 → 692 条片段
├─ 数据流 3: 片段 → 实体/关系抽取 → 2019 实体 + 1452 关系
├─ 数据流 4: 片段/实体 → 向量库(8 Collection) + 知识图谱(1977 节点)
├─ 数据流 5: 统一检索 → KG 规范 + 向量案例 → 融合排序
└─ 外部服务: MonkeyOCR, DeepSeek LLM, Qwen3 嵌入/Reranker
```

### 2. backend.md - 后端处理流程

```
├─ 管道 1: PDF 清洗 (main.py → processor → OCR/Regex/LLM → verifier)
├─ 管道 2: 知识提取 (pipeline → split/annotate/evaluate/refine/dedup)
├─ 管道 3: 实体抽取 (pipeline → rule/llm/normalize)
├─ 管道 4: 向量库 (indexer → qmd → VectorRetriever)
├─ 管道 5: 知识图谱 (converter → builder → KGRetriever)
├─ 管道 6: 统一检索 (KnowledgeRetriever → 双引擎融合)
├─ 审核入口: ChapterMapper（三级回退映射）
└─ 测试: 10 文件, 4246 行, 422 tests passed
```

### 3. data.md - 数据结构与存储

```
├─ 文件系统: PDF → Markdown → fragments.jsonl → entities/relations
├─ 向量库: qmd.db (8 Collection, 706 文档, Qwen3-0.6B 1024 维)
├─ 知识图谱: LightRAG (1977 节点 + 1206 边)
├─ 标准模板: GB/T 50502 (10 章节)
├─ 规范数据库: 84 条结构化标准
└─ 评测数据: 100 组, E2E MRR@3=0.8683
```

### 4. dependencies.md - 外部依赖

```
├─ 核心包: openai, qmd, lightrag, networkx, sentence-transformers
├─ 外部 API: MonkeyOCR (OCR), DeepSeek (LLM)
├─ 本地模型: Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B (2.3GB)
└─ 环境: SCA_LLM_API_KEY, SCA_LLM_BASE_URL, SCA_LLM_MODEL
```

---

## 快速查询表

| 问题 | 文档 |
|------|------|
| 系统整体架构？ | architecture.md |
| 某个管道怎么工作？ | backend.md |
| 数据在哪里？什么格式？ | data.md |
| 外部依赖和配置？ | dependencies.md |
| 向量检索怎么用？ | backend.md → 管道 4/6 |
| 知识图谱怎么推理？ | backend.md → 管道 5/6 |
| 统一检索接口？ | backend.md → 管道 6 |
| 章节映射规则？ | backend.md → 审核系统 |

---

## 文件树视图

```
smart-construction-ai/
├── docs/CODEMAPS/                           # 代码地图（本目录）
│
├── 核心清洗管道 (Phase 1, 710 行)
│   ├── main.py (50)          - 入口
│   ├── processor.py (90)     - 处理协调器
│   ├── crawler.py (69)       - OCR 客户端
│   ├── cleaning.py (434)     - 正则 + LLM 清洗
│   └── verifier.py (67)      - 质量验证
│
├── 知识提取管道 (Phase 2, 1397 行)
│   └── knowledge_extraction/
│       ├── pipeline.py (308)              - 6 步管道
│       ├── chapter_splitter.py (253)      - 章节分割
│       ├── density_evaluator.py (205)     - 密度评估
│       ├── content_refiner.py (174)       - 内容精炼
│       ├── deduplicator.py (163)          - 去重
│       ├── metadata_annotator.py (113)    - 元数据标注
│       └── config.py (176)               - 配置
│
├── 实体/关系抽取 (Phase 2, 1891 行)
│   └── entity_extraction/
│       ├── pipeline.py (356)       - 双路抽取管道
│       ├── rule_extractor.py (577) - 规则抽取
│       ├── llm_extractor.py (345)  - LLM 抽取
│       ├── normalizer.py (307)     - 归一化
│       ├── config.py (155)         - 配置
│       └── schema.py (145)         - 实体/关系 Schema
│
├── 向量库 (Phase 2, 566 行)
│   └── vector_store/
│       ├── indexer.py (252)        - 索引器
│       ├── retriever.py (241)      - VectorRetriever
│       └── config.py (62)          - Collection/模型配置
│
├── 知识图谱 (Phase 2, 824 行)
│   └── knowledge_graph/
│       ├── retriever.py (296)      - KGRetriever
│       ├── converter.py (256)      - K21→LightRAG 格式转换
│       ├── builder.py (217)        - LightRAG 构建
│       └── config.py (43)          - 配置
│
├── 统一检索 (S10, 432 行)
│   └── knowledge_retriever/
│       ├── retriever.py (330)      - KnowledgeRetriever 主类
│       ├── models.py (65)          - RetrievalItem + RetrievalResponse
│       └── config.py (32)          - 融合策略参数
│
├── 审核系统 (Phase 4 预备, 426 行)
│   └── review/
│       └── chapter_mapper.py (425) - 章节标题映射（三级回退）
│
├── 基础设施
│   ├── config.py (45)              - 全局配置
│   └── utils/logger_system.py (48) - 日志系统
│
├── 测试 (4246 行, 422 tests)
│   └── tests/ (10 个测试文件)
│
├── 评测脚本 (Phase 2b)
│   └── scripts/ (4 个评测脚本)
│
├── 数据与知识库
│   ├── data/ (16 份 PDF)
│   ├── output/ (清洗产物 + fragments)
│   ├── templates/ (GB/T 50502)
│   └── docs/knowledge_base/ (向量库 + 知识图谱 + 标准)
│
└── requirements.txt + .env
```

---

## 核心组件一览

### 生产代码（6349 行, 42 文件）

| 模块 | 行数 | 核心类/函数 |
|------|------|------------|
| PDF 清洗 | 710 | PDFProcessor, RegexCleaning, LLMCleaning |
| 知识提取 | 1397 | Pipeline, ChapterSplitter, DensityEvaluator |
| 实体抽取 | 1891 | RuleExtractor, LLMExtractor, Normalizer |
| 向量库 | 566 | VectorRetriever.search(), build_vector_store() |
| 知识图谱 | 824 | KGRetriever.infer_process_chain(), convert_k21_to_lightrag() |
| 统一检索 | 432 | KnowledgeRetriever.retrieve(), _merge_and_sort() |
| 审核 | 426 | ChapterMapper.map() |
| 基础设施 | 93 | log_msg(), LLM_CONFIG |

### 测试代码（4246 行, 10 文件, 422 tests）

| 测试文件 | 行数 | 覆盖模块 |
|----------|------|---------|
| test_entity_extraction.py | 878 | K21 实体抽取 |
| test_knowledge_retriever.py | 709 | S10 统一检索 (100%) |
| test_knowledge_graph.py | 699 | K22 知识图谱 |
| test_vector_store.py | 510 | K23 向量库 |
| test_chapter_mapper.py | 502 | K19 章节映射 |
| test_cleaning.py | 369 | 清洗引擎 |
| test_knowledge_extraction.py | 368 | K16 知识提取 |
| test_verifier.py | 145 | 质量验证 |

---

## 最近更新

| 日期 | Task | 变更 |
|------|------|------|
| 2026-02-25 | S10 | 统一检索接口 KnowledgeRetriever（双引擎融合，60 测试，100% 覆盖） |
| 2026-02-25 | K23 | 向量库构建（8 Collection，706 文档，BM25+向量混合检索） |
| 2026-02-25 | K22 | LightRAG 知识图谱（1977 节点 + 1206 边，图遍历推理） |
| 2026-02-25 | K21 | 实体/关系抽取（双路抽取，2019 实体 + 1452 关系） |
| 2026-02-25 | K20 | 嵌入模型评测（Qwen3-0.6B 选型，E2E MRR@3=0.8683） |
| 2026-02-25 | K19 | 章节标题映射规则库 + ChapterMapper（三级回退） |

---

## 代码地图生成信息

- **生成时间**: 2026-02-25
- **扫描文件**: 52 个 Python 模块（42 生产 + 10 测试）
- **总代码行数**: ~10,600 行（~6,350 生产 + ~4,250 测试）
- **最后更新**: 2026-02-25（S10 统一检索接口完成）
