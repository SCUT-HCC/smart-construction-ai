<!-- Generated: 2026-02-24 | Files scanned: 20 | Token estimate: ~750 -->

# 系统架构 - 南网施工方案智能辅助系统

## 项目类型

单体应用（MVP）- PDF 清洗管道 + 知识提取管道 + 单元测试框架

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

## 未来扩展（Phase 3-5）

- qmd + sqlite-vec（案例向量检索，按章节分库）
- LightRAG（知识图谱推理，工序→危险源链）
- LangGraph（多智能体系统）
  - 检测 Agent（章节完整性、依据时效性、合规性）
  - 生成 Agent（信息提取、内容生成、质量校验）
