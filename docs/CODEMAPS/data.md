<!-- Generated: 2026-02-25 | Files scanned: output/, templates/, docs/, eval/ | Token estimate: ~750 -->

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
├─ compliance_standards/    # 合规标准库（K11 + K18）
│  ├─ standards_database.json  # K18: 结构化标准数据库（84 条，供 TimelinessChecker）
│  ├─ reference_standards.md   # K11: 人类可读标准清单（82 条 Markdown 表格）
│  └─ README.md                # 字段定义 + 集成说明 + 维护指南
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

## 规范标准数据库（K18 产出）

**路径**: `docs/knowledge_base/compliance_standards/standards_database.json`
**用途**: 审核系统 `TimelinessChecker` 的核心数据源

```json
{
  "total_count": 84,
  "verified_count": 42,
  "standards": [{
    "id": "GB_50300_2013",
    "standard_number": "GB 50300-2013",
    "number_body": "50300",        // ← TimelinessChecker 查询主键
    "version_year": 2013,          // ← 与文档引用年份比对
    "status": "现行|废止|已替代|待查",
    "replaces": "GB 50300-2001",   // ← 版本替代关系
    "applicable_engineering_types": ["变电土建", ...],
    "citation_frequency": "★★"
  }]
}
```

**统计**: 现行 73 | 待查 10 | 已替代 1 | 替代关系 8 组

---

## 评测数据（K20 - Phase 2b）

### 评测数据集

**路径**: `eval/embedding/eval_dataset.jsonl`
**内容**: 100 组 query-passage 对（原始 chunks）

```json
{
  "query": "混凝土强度等级C30如何浇筑？",
  "passages": [
    {
      "id": "ch06_s001",
      "content": "混凝土浇筑施工工艺：采用商品混凝土，强度等级C30...",
      "chapter": "Ch6_施工方法及工艺要求"
    }
  ],
  "positive_ids": ["ch06_s001"]
}
```

### 评测结果（K20 选型）

**路径**: `eval/embedding/results/`

| 文件 | 内容 | 关键指标 |
|------|------|---------|
| `result_qwen3-0.6b.json` | Qwen3-Embedding-0.6B | MRR@3=0.8600, Hit@3=92%, 显存1146MB |
| `result_qwen3-4b.json` | Qwen3-Embedding-4B | MRR@3=0.8917, Hit@3=94%, 显存10269MB |
| `reranker_qwen3-reranker-0.6b.json` | Qwen3-Reranker-0.6B | MRR@3改进 +2.8%, 显存1.1GB |
| `combined_qwen3-0.6b_qwen3-reranker-0.6b.json` | **选型组合** | E2E MRR@3=0.8683, 显存2.3GB ✅ |
| `embedding_report.md` | 详细分析报告 | 按章节/文本长度分层 |
| `reranker_report.md` | Reranker 对标 | 性能 vs 显存权衡 |
| `eval_report.md` | 综合评测总结 | 部署建议 + 成本分析 |

---

## 未来数据架构（Phase 3-4）

### 向量数据库（qmd + sqlite-vec）

```
collection: construction_plans
├─ ch01_basis: 编制依据引用标准
├─ ch06_methods: 施工方法与工艺
├─ ch07_quality: 质量管理措施
├─ ch08_safety: 安全措施与危险源
├─ ch09_emergency: 应急处置措施
├─ ch10_green: 绿色施工
├─ equipment: 设备参数表
└─ templates: 通用模板段落
───────────────────────────────────
嵌入模型: Qwen3-Embedding-0.6B (1024-dim, K20 选定)
Reranker: Qwen3-Reranker-0.6B (K20 选定, E2E MRR@3=0.8683)
top_k: 3 | threshold: 0.6 | 按章节/工程类型过滤
```

### 知识图谱（LightRAG）

```
工程实体 → 施工工序 → 设备需求
    ↓           ↓            ↓
灌注桩    钻孔/清孔/浇筑    旋转钻机

工序 → 危险源 → 安全措施
    ↓      ↓         ↓
浇筑   坍塌   安全围挡+监测
```

---

## 数据安全

| 风险 | 缓解措施 |
|------|---------|
| API Key 泄露 | 使用 python-dotenv + 环境变量 |
| 敏感信息 | MVP 阶段不考虑脱敏 |
| 测试数据 | tests/ 目录与生产隔离 |
