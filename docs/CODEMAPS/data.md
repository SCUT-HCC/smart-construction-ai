<!-- Generated: 2026-02-20 | Files scanned: N/A (未使用数据库) | Token estimate: ~400 -->

# 数据结构与存储

## 当前阶段（Phase 1）

**无数据库**，基于文件系统的管道式处理。

## 文件系统结构

### 1. 输入数据（data/）

```
data/
├─ 1.pdf  # 南方电网施工方案样本 1
├─ 2.pdf
└─ ...16.pdf
```

**特征**:
- 总计 16 份 PDF（178MB）
- 格式: 扫描件 + 结构化文档混合
- 内容: 施工方案（7 大章节）

### 2. 输出数据（output/N/）

```
output/1/
├─ raw.md      # OCR 直接输出（未清洗）
├─ regex.md    # 正则清洗后
└─ final.md    # LLM 语义清洗后（金标准）
```

**数据转换链**:
```
PDF (binary) → raw.md (~50KB) → regex.md (~48KB) → final.md (~45KB)
```

### 3. 标准模板（templates/）

```
templates/
└─ standard_50502.md  # GB/T 50502-2009 施工方案 7 大章节标准
```

**内容结构**:
1. 编制依据
2. 工程概况
3. 施工安排
4. 施工准备
5. 施工方法及工艺要求
6. 施工保证措施
7. 应急预案

### 4. 执行日志（task_log.json）

```json
{
  "file": "1.pdf",
  "status": "success",
  "output": "output/1",
  "timestamp": "2026-02-15T10:35:22"
}
```

## 未来数据架构（Phase 2-4）

### 向量数据库（qmd + sqlite-vec）

**集合 1: 编制依据库**
```
collection: construction_standards
├─ document: 国标 GB/T 50502-2009
├─ document: 行标 DL/T 5190.1-2012
└─ metadata: {type: "standard", version: "2009", status: "active"}
```

**集合 2: 优质方案片段**
```
collection: construction_plans
├─ document: output/1/final.md (按章节分块)
├─ metadata: {project_id: "1", chapter: "工程概况", quality_score: 0.95}
└─ embedding: 1536-dim vector (OpenAI text-embedding-3-small)
```

### 语义检索（LightRAG）

**知识图谱**:
```
工程实体 → 施工方法 → 规范引用
    ↓           ↓            ↓
工期要求    机械配置     版本时效性
```

## 数据质量指标

| 指标 | 阈值 | 说明 |
|------|------|------|
| 字数保留率 | ≥ 50% | raw.md → final.md 字数损失 |
| 表格完整性 | 100% | Markdown 表格闭合检测 |
| LLM 幻觉率 | 0% | 禁止对话性前缀（"好的"、"以下是"） |

## 数据安全

- **API Key 泄露风险**: config.py 中硬编码（待迁移至环境变量）
- **敏感信息**: PDF 中可能包含项目敏感数据（未脱敏）
- **备份策略**: 无（MVP 阶段不考虑）
