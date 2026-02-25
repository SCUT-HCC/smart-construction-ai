<!-- Generated: 2026-02-25 | Files scanned: 27 Python modules + 84 standards + eval scripts | Token estimate: ~2500 -->

# 代码地图索引 - 南网施工方案智能辅助系统

## 项目概览

**南网施工方案智能辅助系统** (smart-construction-ai) 是一个 MVP 级别的 Python 应用，实现 PDF 到 Markdown 的完整清洗管道、知识提取管道，以及向量检索模型评测框架。

- **技术栈**: Python 3.10 + LangChain + LangGraph（多智能体系统）
- **核心功能**: OCR → 清洗 → 知识提取 → 向量检索评测（qmd + sqlite-vec）
- **项目周期**: 2026-01 至 2026-12（中期检查 2026-06-30）
- **Conda 环境**: `sca`
- **测试框架**: pytest + pytest-cov
- **当前阶段**: Phase 2b（向量检索评测完成 K20；Phase 3 qmd 集成待进行）

---

## 代码地图导航

### 1. architecture.md - 系统架构

**内容**: 高层系统设计与模块边界

```
├─ 项目类型: 单体应用 MVP
├─ 数据流 1: PDF → OCR → Regex → LLM → Verify → Markdown（Phase 1）
├─ 数据流 2: Markdown → 章节分割 → 密度评估 → 精炼 → 去重 → fragments.jsonl（Phase 2）
├─ 模块边界: 入口层 → 核心处理层 → 知识提取层 → 基础设施层
├─ 外部服务: MonkeyOCR (OCR), DeepSeek LLM, Docker
└─ 未来扩展: qmd + sqlite-vec, LightRAG, LangGraph
```

---

### 2. backend.md - 后端处理流程

**内容**: 代码级别的调用链、类接口、配置管理、错误处理

```
├─ PDF 清洗链路: main.py → processor.py → [crawler.py, cleaning.py, verifier.py]
├─ 知识提取链路: knowledge_extraction/__main__.py → pipeline.py → [splitter, annotator, evaluator, refiner, deduplicator]
├─ 关键类:
│  ├─ PDFProcessor: PDF 处理协调器
│  ├─ Pipeline: 知识提取 6 步管道
│  ├─ ChapterSplitter: 章节分割与标准化映射
│  ├─ DensityEvaluator: LLM 知识密度评估
│  └─ Deduplicator: 跨文档 Jaccard 去重
├─ 配置中心: config.py + knowledge_extraction/config.py
└─ 日志系统: utils/logger_system.py (log_msg, log_json)
```

---

### 3. data.md - 数据结构与存储

**内容**: 文件系统结构、数据转换流、质量指标、知识片段格式

```
├─ 输入数据: data/ (16份PDF, 178MB)
├─ 清洗输出: output/N/ (raw.md → regex.md → final.md)
├─ 知识片段: output/fragments.jsonl (692 条结构化片段)
├─ 标准模板: templates/ (GB/T 50502 10章节)
├─ 质量指标: 字数保留率 ≥50%, 表格完整性 100%, 幻觉率 0%
└─ 未来: qmd + sqlite-vec (向量库), LightRAG (知识图谱)
```

---

### 4. dependencies.md - 外部依赖与集成

**内容**: 包依赖、外部服务集成、风险评估、健康检查

```
├─ Python 包: openai, requests, tqdm, python-dotenv, pydantic, PyYAML
├─ 外部服务:
│  ├─ MonkeyOCR API (PDF → Markdown)
│  ├─ DeepSeek LLM API (语义清洗 + 密度评估 + 内容精炼)
│  └─ Docker (OCR 容器)
├─ 环境变量: SCA_LLM_API_KEY, SCA_LLM_BASE_URL, SCA_LLM_MODEL
└─ 风险评估: 服务宕机, API 限流, Key 泄露, 网络不稳定
```

---

## 快速查询表

| 问题 | 参考文档 | 相关章节 |
|------|---------|---------|
| 系统整体架构是什么？ | architecture.md | 模块边界 |
| 如何添加新的清洗步骤？ | backend.md | 清洗引擎 |
| 知识提取管道怎么运作？ | backend.md | 知识提取链路 |
| 输出数据在哪里？ | data.md | 输出数据 |
| fragments.jsonl 格式是什么？ | data.md | 知识片段 |
| 规范标准数据库怎么查询？ | data.md | 规范标准数据库 |
| 如何配置 API Key？ | dependencies.md | 环境变量配置 |
| 章节标准化映射规则？ | backend.md | ChapterSplitter |
| 密度评估的判定标准？ | backend.md | DensityEvaluator |

---

## 文件树视图

```
smart-construction-ai/
├── docs/CODEMAPS/
│   ├── INDEX.md (本文件) - 导航与索引
│   ├── architecture.md - 系统架构 (~750 tokens)
│   ├── backend.md - 后端流程 (~950 tokens)
│   ├── data.md - 数据结构 (~600 tokens)
│   └── dependencies.md - 外部依赖 (~500 tokens)
├── 核心清洗管道（Phase 1）
│   ├── main.py - 入口与参数解析 (50 行)
│   ├── processor.py - PDF 处理协调器 (90 行)
│   ├── crawler.py - OCR 客户端 (69 行)
│   ├── cleaning.py - 清洗引擎 (434 行)
│   └── verifier.py - 质量验证 (67 行)
├── 知识提取管道（Phase 2）
│   ├── knowledge_extraction/__main__.py (5 行)
│   ├── knowledge_extraction/pipeline.py (308 行)
│   ├── knowledge_extraction/chapter_splitter.py (253 行)
│   ├── knowledge_extraction/metadata_annotator.py (113 行)
│   ├── knowledge_extraction/density_evaluator.py (205 行)
│   ├── knowledge_extraction/content_refiner.py (174 行)
│   ├── knowledge_extraction/deduplicator.py (163 行)
│   └── knowledge_extraction/config.py (176 行)
├── 向量检索评测（Phase 2b - K20）
│   ├── scripts/eval_embedding_models.py - 嵌入模型评测
│   ├── scripts/eval_reranker_models.py - Reranker 评测
│   ├── scripts/eval_combined_pipeline.py - E2E 联合管道
│   ├── scripts/verify_qmd_integration.py - qmd 集成验证
│   └── eval/embedding/results/ - 评测报告 + 模型指标
├── 基础设施
│   ├── config.py (45 行) + utils/logger_system.py (48 行)
│   ├── tests/ - pytest fixtures + 测试 (~1000 行)
│   ├── templates/ - GB/T 50502 标准 10 章节
│   ├── data/ - 16份原始 PDF
│   └── output/ - fragments.jsonl (692 条) + 清洗后 MD
├── 知识库资料（docs/knowledge_base/ + docs/analysis/）
│   ├── writing_guides/ - Ch1-10 撰写指南
│   ├── ch06_templates/ - 4 大工程类型模板（K17）
│   ├── compliance_standards/ - 结构化标准 JSON（K18）
│   ├── process_references/ - 工艺参考库
│   └── 其他资源 (organization, quality, safety, emergency)
├── requirements.txt - Python 依赖
└── .env - 环境变量（SCA_LLM_API_KEY 等）
```

---

## 核心组件职责一览

### 生产代码 — PDF 清洗管道

| 组件 | 行数 | 职责 | 主要方法 |
|------|------|------|---------|
| **main.py** | 50 | 入口与参数解析 | `parse_args()`, `main()` |
| **processor.py** | 90 | 处理流程协调 | `process_file()`, `process_directory()` |
| **crawler.py** | 69 | OCR API 调用 | `MonkeyOCRClient.to_markdown()` |
| **cleaning.py** | 434 | 正则 + LLM 清洗 | `RegexCleaning.clean()`, `LLMCleaning.clean()` |
| **verifier.py** | 67 | 质量验证 | `MarkdownVerifier.verify()` |
| **config.py** | 45 | 全局配置 | `LLM_CONFIG`, `CLEANING_CONFIG` 等 |
| **logger_system.py** | 48 | 日志与追踪 | `log_msg()`, `log_json()` |

### 生产代码 — 知识提取管道

| 组件 | 行数 | 职责 | 主要方法 |
|------|------|------|---------|
| **pipeline.py** | 308 | 6 步管道编排 | `Pipeline.run()` |
| **chapter_splitter.py** | 253 | 章节分割与标准映射 | `ChapterSplitter.split()`, `_map_chapter()` |
| **metadata_annotator.py** | 113 | 元数据标注 | `MetadataAnnotator.annotate()` |
| **density_evaluator.py** | 205 | LLM 密度评估 | `DensityEvaluator.evaluate()` |
| **content_refiner.py** | 174 | LLM 内容精炼 | `ContentRefiner.refine()` |
| **deduplicator.py** | 163 | 跨文档去重 | `Deduplicator.deduplicate()` |
| **ke/config.py** | 176 | 知识提取配置 | 章节映射、质量评分、工程类型 |

### 测试代码

| 组件 | 行数 | 覆盖目标 |
|------|------|---------|
| **conftest.py** | 66 | 共享 fixtures |
| **test_cleaning.py** | 369 | RegexCleaning + LLMCleaning |
| **test_verifier.py** | 145 | MarkdownVerifier |
| **test_knowledge_extraction.py** | 368 | 知识提取管道各模块 |

---

## 最近更新

| 日期 | Task | 变更 |
|------|------|------|
| 2026-02-25 | K20 | 向量检索评测完成：Qwen3-0.6B Embedding + Qwen3-0.6B Reranker 选定，E2E MRR@3=0.8683 |
| 2026-02-25 | K20 | 新增 4 个评测脚本：嵌入模型 / Reranker / 联合管道 / qmd 集成验证 |
| 2026-02-25 | K20 | 评测数据：eval/embedding/ 包含 100 组测试数据 + 6 个模型的对标结果 |
| 2026-02-24 | K18 | 完成规范标准结构化数据库（84 条 JSON，42 条已校验，8 组替代关系） |
| 2026-02-24 | K17 | 完成第六章分工程类型模板（4 大类 235 条片段） |
| 2026-02-24 | K16 | 完成知识提取管道，产出 692 条结构化知识片段 |

---

## 代码地图生成信息

- **生成时间**: 2026-02-25
- **扫描文件**: 27 个 Python 模块（核心 7 + 知识提取 7 + 评测 4 + 测试 4 + 配置 + utils）
- **总代码行数**: ~3200 行（~2200 生产 + ~1000 测试）
- **最后更新**: 2026-02-25（与代码同步，K20 完成）
- **重大变更**: 新增 4 个评测脚本（embedding/reranker/combined/qmd-verify）；完成向量检索模型选型（Qwen3 系列）
