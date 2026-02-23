<!-- Generated: 2026-02-23 | Total files in CODEMAPS: 5 | Architecture coverage: 100% -->

# 代码地图索引 - 南网施工方案智能辅助系统

## 项目概览

**南网施工方案智能辅助系统** (smart-construction-ai) 是一个 MVP 级别的 Python 应用，实现 PDF 到 Markdown 的完整清洗管道。

- **技术栈**: Python 3.10 + LangChain + LangGraph（多智能体系统）
- **核心功能**: OCR 识别 → 正则清洗 → LLM 语义清洗 → 质量验证
- **项目周期**: 2026-01 至 2026-12（中期检查 2026-06-30）
- **Conda 环境**: `sca`
- **开发规范**: CLAUDE.md + coding-style-guide.md

---

## 代码地图导航

### 1. architecture.md - 系统架构

**内容**: 高层系统设计与模块边界

```
├─ 项目类型: 单体应用 MVP
├─ 核心数据流: PDF → OCR → Regex → LLM → Verify → Markdown
├─ 模块边界: 入口层 → 核心处理层 → 基础设施层
├─ 外部服务: MonkeyOCR (OCR), DeepSeek LLM, Docker
├─ 数据资源: data/, output/, templates/, task_log.json
└─ 未来扩展: qmd + sqlite-vec, LightRAG, LangGraph
```

**目标读者**: 架构师、新开发者、项目经理

**推荐阅读**: 了解系统全貌、组件关系、扩展方向

---

### 2. backend.md - 后端处理流程

**内容**: 代码级别的调用链、类接口、配置管理、错误处理

```
├─ 核心链路: main.py → processor.py → [crawler.py, cleaning.py, verifier.py]
├─ 关键类:
│  ├─ PDFProcessor: 协调器（process_file, process_directory）
│  ├─ MonkeyOCRClient: OCR 客户端
│  ├─ RegexCleaning + LLMCleaning: 清洗引擎
│  └─ MarkdownVerifier: 质量验证
├─ 配置中心: config.py (LLM_CONFIG, MONKEY_OCR_CONFIG, etc.)
├─ 日志系统: utils/logger_system.py (log_msg, log_json)
└─ 错误处理: OCR失败 → WARNING, LLM异常 → ERROR
```

**目标读者**: 后端开发者、代码审查者

**推荐阅读**: 实现功能、调试问题、扩展处理流程

---

### 3. data.md - 数据结构与存储

**内容**: 文件系统结构、数据转换流、质量指标、未来数据库设计

```
├─ 当前阶段 (Phase 1): 无数据库，基于文件系统
├─ 输入数据: data/ (16份PDF, 178MB)
├─ 输出数据: output/N/ (raw.md → regex.md → final.md)
├─ 标准模板: templates/ (GB/T 50502 10章节)
├─ 执行日志: task_log.json (流式 JSON 日志)
├─ 分析报告: docs/analysis/ (16份文档的元数据)
├─ 质量指标: 字数保留率 ≥50%, 表格完整性 100%, 幻觉率 0%
└─ 未来: qmd + sqlite-vec (向量库), LightRAG (知识图谱)
```

**目标读者**: 数据工程师、质量管理、未来系统架构师

**推荐阅读**: 理解数据流、设计验证指标、规划数据库迁移

---

### 4. dependencies.md - 外部依赖与集成

**内容**: 包依赖、外部服务集成、风险评估、健康检查

```
├─ Python 包: openai, requests, tqdm, python-dotenv, qmd, sqlite-vec
├─ 外部服务:
│  ├─ MonkeyOCR API (PDF → Markdown)
│  ├─ DeepSeek LLM API (Markdown 语义清洗)
│  └─ Docker (OCR 容器)
├─ 环境变量: SCA_LLM_API_KEY, SCA_LLM_BASE_URL, SCA_LLM_MODEL
├─ 健康检查: curl 检查 OCR/LLM 服务状态
├─ 风险评估: 服务宕机, API 限流, Key 泄露, 网络不稳定
└─ 网络拓扑: 本地应用 → Docker/DeepSeek/文件系统
```

**目标读者**: 运维工程师、DevOps、安全审查

**推荐阅读**: 配置外部服务、监控依赖健康、处理故障

---

## 快速查询表

| 问题 | 参考文档 | 相关章节 |
|------|---------|---------|
| 系统整体架构是什么？ | architecture.md | 模块边界 |
| 如何添加新的清洗步骤？ | backend.md | 清洗引擎 (4.2) |
| 输出数据在哪里？ | data.md | 输出数据 (output/N/) |
| 如何配置 API Key？ | dependencies.md | 环境变量配置 |
| 处理流程有哪些错误处理？ | backend.md | 错误处理策略 |
| OCR 服务故障怎么办？ | dependencies.md | 依赖风险评估 |
| 质量指标有哪些？ | data.md | 质量指标 |
| 未来如何支持向量检索？ | data.md, dependencies.md | 未来数据架构, 未来依赖 |

---

## 文件树视图

```
smart-construction-ai/
├── docs/CODEMAPS/
│   ├── INDEX.md (本文件) - 导航与索引
│   ├── architecture.md - 系统架构 (~650 tokens)
│   ├── backend.md - 后端流程 (~500 tokens)
│   ├── data.md - 数据结构 (~400 tokens)
│   └── dependencies.md - 外部依赖 (~350 tokens)
├── docs/architecture/ (系统设计文档 09份)
├── docs/analysis/ (16份文档的章节分析)
├── main.py - 入口与参数解析
├── processor.py - PDF 处理协调器
├── crawler.py - OCR 客户端
├── cleaning.py - 清洗引擎 (正则 + LLM)
├── verifier.py - 质量验证
├── config.py - 全局配置
├── utils/logger_system.py - 日志系统
├── templates/ - GB/T 50502 标准模板
├── data/ - 16份原始 PDF
├── output/ - 清洗后的 Markdown (16份)
├── requirements.txt - Python 依赖
└── .env / .env.example - 环境变量
```

---

## 核心组件职责一览

| 组件 | 行数 | 职责 | 主要方法 |
|------|------|------|---------|
| **main.py** | 50 | 入口与参数解析 | `parse_args()`, `main()` |
| **processor.py** | 90 | 处理流程协调 | `process_file()`, `process_directory()` |
| **crawler.py** | 69 | OCR API 调用 | `MonkeyOCRClient.to_markdown()` |
| **cleaning.py** | 434 | 正则 + LLM 清洗 | `RegexCleaning.clean()`, `LLMCleaning.clean()` |
| **verifier.py** | 60 | 质量验证 | `MarkdownVerifier.verify()` |
| **config.py** | 45 | 全局配置 | `LLM_CONFIG`, `CLEANING_CONFIG` 等 |
| **logger_system.py** | 48 | 日志与追踪 | `log_msg()`, `log_json()` |

---

## 最近更新

| 日期 | Commit | 变更 |
|------|--------|------|
| 2026-02-23 | (当前) | 生成完整代码地图（architecture, backend, data, dependencies）|
| 2026-02-23 | d92dcf0 | 移除 loguru/watchdog 僵尸依赖，统一日志方案 |
| 2026-02-15 | 63a0940 | 清理 .gitignore 中已无用的忽略条目 |
| 2026-02-13 | 19b4b24 | 清理孤立实验目录，归档参考文档 |
| 2026-02-10 | acdfa73 | 添加项目鸟瞰文档 - 规划与代码一致性比对报告 |

---

## 如何使用本代码地图

### 场景 1: 新开发者快速上手
1. 读 **architecture.md** 了解系统架构（5 分钟）
2. 读 **backend.md** 了解代码流程（10 分钟）
3. 根据任务选择相关文档深入

### 场景 2: 实现新功能
1. 在 **backend.md** 中找到相关处理流程
2. 查阅 **dependencies.md** 确认外部依赖
3. 修改对应模块，参考 config.py 的配置示例

### 场景 3: 调试问题
1. 根据错误信息在 **backend.md** 的错误处理策略中找到对应场景
2. 检查 **dependencies.md** 的服务健康状态
3. 查看 task_log.json 追踪执行过程

### 场景 4: 性能优化 / 扩展
1. 读 **data.md** 的未来数据架构
2. 读 **dependencies.md** 的未来依赖规划
3. 参考 CLAUDE.md 中的 Phase 2-4 路线图

---

## 代码地图生成信息

- **生成时间**: 2026-02-23
- **扫描文件**: 9 个 Python 核心模块 + 配置 + 日志
- **总代码行数**: ~796 行（不含 __pycache__ 和 .git）
- **代码地图总行数**: ~1800 行（4份文档）
- **预期阅读时间**: 30-45 分钟（完整阅读）; 5-10 分钟（快速查询）
- **最后更新**: 2026-02-23（与代码同步）

---

**维护者**: Claude Code (Documentation Specialist)
**反馈**: 发现文档与代码不一致时，请创建新的代码地图更新任务。
