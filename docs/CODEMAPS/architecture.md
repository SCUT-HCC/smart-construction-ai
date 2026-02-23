<!-- Generated: 2026-02-23 | Files scanned: 13 | Token estimate: ~700 | NEW: pytest framework -->

# 系统架构 - 南网施工方案智能辅助系统

## 项目类型

单体应用（MVP）- PDF 处理与清洗管道 + 单元测试框架

## 核心数据流

```
PDF 输入 → OCR 识别 → 正则清洗 → LLM 语义清洗 → 质量验证 → Markdown 输出
   ↓           ↓           ↓            ↓              ↓            ↓
data/      raw.md     regex.md     final.md       日志系统    output/N/
```

## 模块边界

### 生产代码流（Production）

```
┌─────────────────────────────────────────────────────────────┐
│                      入口层 (Entry)                          │
│  main.py (50 行)                                             │
│  └─ 参数解析 → 组件初始化 → 调度执行                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    核心处理层 (Core)                         │
│  processor.py (91 行)                                        │
│  ├─ PDFProcessor.process_file()                             │
│  └─ PDFProcessor.process_directory()                        │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│   OCR 识别       │ │   清洗引擎   │ │   质量验证   │
│  crawler.py      │ │ cleaning.py  │ │ verifier.py  │
│   (69 行)        │ │  (434 行)    │ │  (67 行)     │
└──────────────────┘ └──────────────┘ └──────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   基础设施层 (Infrastructure)                │
│  config.py (45 行) - 全局配置                                │
│  utils/logger_system.py (48 行) - 日志系统（标准库 logging）│
└─────────────────────────────────────────────────────────────┘
```

### 测试框架（NEW - 2026-02-23）

```
┌─────────────────────────────────────────────────────────────┐
│                    pytest 测试框架 (Tests)                   │
├─────────────────────────────────────────────────────────────┤
│  conftest.py (66 行) - 共享 fixtures                        │
│  ├─ regex_cleaner fixture                                   │
│  ├─ verifier fixture                                        │
│  └─ sample_markdown, sample_latex_text fixtures             │
│                                                              │
│  test_cleaning.py (369 行) - RegexCleaning 单元测试          │
│  ├─ TestRegexCleaningClean (10+ 个测试)                     │
│  └─ TestLLMCleaningClean (mocked OpenAI)                    │
│                                                              │
│  test_verifier.py (145 行) - MarkdownVerifier 单元测试       │
│  └─ TestMarkdownVerifier (5+ 个测试)                        │
└─────────────────────────────────────────────────────────────┘
         │
         └─ 验证生产代码的正确性、边界情况、错误处理
```

## 外部依赖

| 服务 | 用途 | 端点 |
|------|------|------|
| MonkeyOCR | PDF → Markdown 转换 | http://localhost:7861/parse |
| DeepSeek LLM | 语义清洗与重构 | http://110.42.53.85:11081/v1/chat/completions |
| Docker | OCR 服务容器化 | monkeyocr-api |

## 数据资源

| 路径 | 内容 | 用途 |
|------|------|------|
| `data/` | 16 份施工方案 PDF（178MB） | 原始输入 |
| `output/1-16/` | 清洗后的 Markdown | 金标准样本 |
| `templates/standard_50502.md` | GB/T 50502-2009 标准 | 施工方案 7 大章节规范 |
| `task_log.json` | 执行日志 | 调试与追溯 |

## 核心功能

1. **OCR 转换**: PDF → Markdown（MonkeyOCR API）
2. **正则清洗**: 移除水印、页码、LaTeX 装饰符
3. **LLM 清洗**: 标题合并、段落流优化、表格修复
4. **质量验证**: 字数损失检测、LLM 幻觉检测、Markdown 合法性

## 未来扩展（Phase 2-4）

- qmd + sqlite-vec（案例向量检索）
- LightRAG（知识图谱推理）
- LangGraph（多智能体系统）
  - 检测 Agent（章节完整性、依据时效性、合规性）
  - 生成 Agent（信息提取、内容生成、质量校验）
