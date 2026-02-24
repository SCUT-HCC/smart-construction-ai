<!-- Generated: 2026-02-24 | Files scanned: output/, templates/, docs/ | Token estimate: ~550 -->

# 数据结构与存储

## 当前阶段（Phase 1-2）

**无数据库**，基于文件系统的管道式处理。

## 文件系统结构

### 1. 输入数据（data/）

```
data/
├─ 1.pdf ~ 16.pdf   # 南方电网施工方案（16 份，178MB）
```

### 2. 清洗输出（output/N/）

```
output/1/
├─ raw.md      # OCR 直接输出
├─ regex.md    # 正则清洗后
└─ final.md    # LLM 语义清洗后（金标准）
```

**数据转换链**:
```
PDF (binary) → raw.md (~50KB) → regex.md (~48KB) → final.md (~45KB)
```

### 3. 知识片段（output/fragments.jsonl）

**来源**: 知识提取管道（K16）处理 16 份 final.md
**产出**: 692 条结构化知识片段

**单条片段格式**:
```json
{
  "source_doc": "output/3/final.md",
  "chapter": "Ch6_施工方法及工艺要求",
  "title": "钢筋绑扎工艺",
  "content": "...(精炼后文本)...",
  "density": "high",
  "engineering_type": "输电线路",
  "tags": ["钢筋", "绑扎", "工艺"],
  "quality_score": 3
}
```

**密度分布**:
| 密度 | 含义 | 处理方式 |
|------|------|---------|
| high | 技术细节丰富、可直接复用 | 保留原文 |
| medium | 有价值但需精炼 | LLM 摘要后保留 |
| low | 行政性/重复性内容 | 过滤丢弃 |

### 4. 标准模板（templates/）

```
templates/
├─ standard_50502.md      # GB/T 50502-2009 标准 10 章节模板
└─ naming_conventions.md   # 章节命名规范
```

**标准 10 章节**:
1. 编制依据 → 2. 工程概况 → 3. 施工组织机构及职责 → 4. 施工安排与进度计划
5. 施工准备 → 6. 施工方法及工艺要求 → 7. 质量管理与控制措施
8. 安全文明施工管理 → 9. 应急预案与处置措施 → 10. 绿色施工与环境保护（可选）

### 5. 知识库资料（docs/knowledge_base/）

**内容**: 基于 16 份实际方案系统梳理的撰写指南与参考资料

```
docs/knowledge_base/
├─ writing_guides/          # 各章节撰写指南（Ch1-Ch10）
│  └─ ch06_templates/       # K17: 第六章分工程类型模板（4 大类）
│     ├─ README.md                      # 导航索引 + 子类型映射 + 格式规范
│     ├─ civil_works_template.md        # 变电土建（116 fragments）
│     ├─ electrical_install_template.md # 变电电气（53 fragments）
│     ├─ line_tower_template.md         # 线路塔基（49 fragments）
│     └─ special_general_template.md    # 特殊/通用（17 fragments）
├─ process_references/      # 工艺参考库（4 类）
├─ compliance_standards/    # 合规标准库
├─ engineering_data/        # 工程数据需求清单
├─ targets/                 # 目标量化指标
├─ organization/            # 组织架构与岗位职责
├─ quality/                 # 质量管理参考
├─ safety_knowledge/        # 安全管理参考
└─ emergency/               # 应急管理参考
```

### 6. 分析报告（docs/analysis/）

```
docs/analysis/
├─ chapter_analysis_data.json    # 16份文档章节结构元数据
├─ chapter_comparison_table.md   # 章节对标表格
└─ chapter_structure_analysis.md # 结构化分析报告
```

### 7. 执行日志（task_log.json）

```json
{"timestamp": "2026-02-23T10:35:22", "file": "1.pdf", "status": "success", "output": "output/1"}
```

追加模式，每行一条 JSON 记录。

---

## 质量指标

| 指标 | 目标 | 说明 |
|------|------|------|
| 字数保留率 | ≥ 50% | raw.md → final.md 字数损失检测 |
| 表格完整性 | 100% | Markdown 表格闭合检测 |
| LLM 幻觉率 | 0% | 禁止对话性前缀 |
| 知识片段产出 | 692 条 | 16 份文档提取的有效片段 |
| 去重阈值 | Jaccard > 0.8 | 跨文档相似片段合并 |

---

## 未来数据架构（Phase 3-4）

### 向量数据库（qmd + sqlite-vec）

```
collection: construction_plans
├─ 按章节分库存储 fragments.jsonl 中的片段
├─ embedding: 1536-dim (OpenAI text-embedding-3-small)
└─ metadata: {chapter, engineering_type, quality_score}
```

### 知识图谱（LightRAG）

```
工程实体 → 施工方法 → 规范引用
    ↓           ↓            ↓
工期要求    机械配置     版本时效性
```

---

## 数据安全

| 风险 | 缓解措施 |
|------|---------|
| API Key 泄露 | 使用 python-dotenv + 环境变量 |
| 敏感信息 | MVP 阶段不考虑脱敏 |
| 测试数据 | tests/ 目录与生产隔离 |
