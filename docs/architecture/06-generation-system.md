# 生成系统

> 输入工程基本信息，输出完整 10 章施工方案。

## 整体流程

```
用户输入 → InputParser → StandardizedInput
                              │
                    ┌─────────▼─────────┐
                    │ GenerationCoord    │
                    │                   │
                    │  Ch1 → Validate   │
                    │  Ch2 → Validate   │
                    │  ...              │
                    │  Ch9 → Validate   │
                    │                   │
                    │  FinalCheck       │
                    │  AutoFix          │
                    └─────────┬─────────┘
                              │
                        完整施工方案
```

## 输入标准化

用户输入通过 `InputParser` 统一为 `StandardizedInput`：

```
StandardizedInput:
  basic:       {project_name, project_type, location, scale}
  technical:   {geology, climate, special_requirements}
  participants: {owner, contractor, supervisor, designer}
  constraints: {timeline, budget, risks}
```

支持三种输入形式：
- **JSON** → 直接映射
- **自然语言** → LLM 提取结构化字段
- **PDF** → OCR 清洗 → LLM 提取

## 串行生成机制

**为什么串行？** 因为章节间有依赖关系（见 03-chapter-specification 的依赖图）。后续章节需要前序章节的内容作为上下文。

每章生成流程：

```
上下文构建 → 知识检索 → LLM 生成 → 单章验证 → 通过/修复
```

### 上下文管理

每个章节 Agent 收到的上下文包含三部分：

```
ChapterContext:
  macro_view:    前序各章的 150 字摘要（控制 token）
  key_details:   当前章节依赖的具体参数（从 StandardizedInput 和前序章节提取）
  retrieval:
    regulations: LightRAG 推理结果（强制规范）
    cases:       qmd top 3（案例片段）
```

**为什么不传全文？** 施工方案动辄数万字，全部传入会超 context 限制。用摘要 + 关键参数的方式控制在可用范围内。

### 章节 Agent

9 个章节 Agent（第十章可选）共享 `BaseChapterAgent` 基类：

| 方法 | 功能 |
|------|------|
| `generate(context) → str` | 基于上下文和 Prompt 生成章节内容 |
| `post_process(content) → str` | 后处理（格式规范化、命名统一） |

每个 Agent 使用 Jinja2 模板渲染 Prompt：

```
{静态} 角色定义 + 输出格式要求
{静态} 当前章节的结构规范（来自 standard_50502.md）
{动态} StandardizedInput
{动态} 知识检索结果（规范 + 案例）
{动态} 前序章节摘要
{静态} 生成指令
```

## 验证机制

### 单章验证

每章生成后立即验证：

| 检查项 | 方法 | 失败处理 |
|--------|------|---------|
| 必需子章节是否齐全 | 正则匹配标题 | 重新生成 |
| 工程名称是否一致 | 精确匹配 | 字符串替换 |
| 内容是否空洞 | LLM 评估 | 注入更多案例重新生成 |

### 全文验证

全部章节生成后，做跨章节一致性检查：

| 检查项 | 说明 |
|--------|------|
| 事实一致性 | 工程名称、电压等级、施工工期等全文精确匹配 |
| 逻辑依赖 | 第七章的质量控制覆盖第六章的所有工序 |
| 术语一致性 | 同一概念全文使用同一名称 |
| 内容完整性 | 9 章必须存在；第十章如已生成则需满足最小内容要求 |

### 自动修复

| 问题类型 | 修复方式 | 预期成功率 |
|---------|---------|-----------|
| 术语/名称不一致 | 字符串替换 | ~100% |
| 缺失子章节 | LLM 补充生成 | ~90% |
| 事实冲突 | LLM 重写冲突段落 | ~70% |
| 逻辑矛盾 | 标记为需人工审核 | — |

## 核心类

| 类 | 职责 |
|---|------|
| `InputParser` | 输入标准化 |
| `StandardModel` | StandardizedInput 数据结构 |
| `GenerationCoordinator` | 串行编排 9 章生成 |
| `BaseChapterAgent` | 章节 Agent 基类 |
| `Chapter1Agent` ~ `Chapter9Agent` | 各章节 Agent |
| `ConsistencyValidator` | 一致性验证 |
| `Fixer` | 自动修复 |
| `KnowledgeRetriever` | 知识检索协调器：qmd + LightRAG（见 05） |

## 目录结构（规划）

```
smart-construction-ai/
├── agents/                  # 9 个章节 Agent
│   ├── base.py
│   ├── chapter1_basis.py
│   ├── ...
│   └── chapter9_emergency.py
├── prompts/
│   ├── static/              # 角色定义、输出格式
│   └── agents/              # 9 个 J2 模板
├── retrieval/               # 检索协调器
├── validation/              # 验证 + 修复
├── knowledge_base/          # qmd + LightRAG 数据
└── main_generator.py        # 生成系统主入口
```

> **与现有代码的关系**：
> - `main.py`：保留，作为 OCR 清洗管道入口（Phase 1 产物）
> - `main_generator.py`：新增，施工方案生成入口（Phase 3）
> - 现有清洗管道（cleaning.py, processor.py, verifier.py, crawler.py）保持不变，当审核系统接收 PDF 输入时作为前置处理调用
> - `agents/`, `prompts/`, `retrieval/`, `validation/` 为全新目录，与现有代码无冲突
