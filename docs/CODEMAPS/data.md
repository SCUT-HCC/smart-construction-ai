<!-- Generated: 2026-02-23 | Files scanned: N/A (无数据库，Phase 1) | Token estimate: ~500 | NEW: test fixtures -->

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

**质量指标**:
| 指标 | 目标 | 说明 |
|------|------|------|
| 字数保留率 | ≥ 50% | raw.md → final.md 字数损失检测 |
| 表格完整性 | 100% | Markdown 表格闭合检测 |
| LLM 幻觉率 | 0% | 禁止对话性前缀（"好的"、"以下是"） |

### 3. 标准模板（templates/）

```
templates/
├─ standard_50502.md      # GB/T 50502-2009 施工方案 10 章节标准
└─ naming_conventions.md   # 章节命名规范
```

**标准 10 章节结构**:
1. 编制依据
2. 工程概况
3. 施工组织机构及职责 ✨
4. 施工安排与进度计划
5. 施工准备
6. 施工方法及工艺要求
7. 质量管理与控制措施 ✨
8. 安全文明施工管理 ✨
9. 应急预案与处置措施
10. 绿色施工与环境保护（可选） ✨

### 4. 执行日志（task_log.json）

```json
{
  "timestamp": "2026-02-23T10:35:22",
  "file": "1.pdf",
  "status": "success",
  "output": "output/1"
}
```

**追加模式**: 每行一条 JSON 记录（便于流式处理）

### 5. 分析报告（docs/analysis/）

```
docs/analysis/
├─ chapter_analysis.py           # Python 分析脚本
├─ chapter_analysis_data.json    # 16份文档的章节结构元数据
├─ chapter_analysis_summary.md   # 章节分析总结
├─ chapter_comparison_table.md   # 章节对标表格
└─ chapter_structure_analysis.md # 结构化分析报告
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

## Python 依赖（requirements.txt）

| 包名 | 版本 | 用途 |
|------|------|------|
| openai | 2.21.0 | LLM API 客户端（兼容 DeepSeek） |
| requests | 2.32.5 | HTTP 客户端（OCR API 调用） |
| tqdm | 4.67.3 | 进度条（批量处理） |
| python-dotenv | 1.2.1 | 环境变量管理（.env 配置） |
| qmd | 0.1.0 | 向量数据库框架 |
| sqlite-vec | 0.1.6 | SQLite 向量扩展 |
| pydantic | 2.12.5 | 数据验证与序列化 |
| PyYAML | 6.0.3 | YAML 配置解析 |

**最近清理**: 移除 loguru 和 watchdog 僵尸依赖（commit d92dcf0）

## 测试数据与 Fixtures（NEW - 2026-02-23）

### conftest.py 提供的 Fixtures

```python
# 实例 fixtures
@pytest.fixture
def regex_cleaner() -> RegexCleaning:
    """使用项目配置的 RegexCleaning 实例"""

@pytest.fixture
def verifier() -> MarkdownVerifier:
    """使用项目配置的 MarkdownVerifier 实例"""

# 样本数据 fixtures
@pytest.fixture
def sample_markdown() -> str:
    """典型施工方案 Markdown"""
    return """## 编制依据\n本工程施工方案依据以下规范编制..."""

@pytest.fixture
def sample_html_table() -> str:
    """OCR 残留的 HTML 表格"""
    return "<table><tr><th>序号</th>...</tr></table>"

@pytest.fixture
def sample_latex_text() -> str:
    """包含 LaTeX 符号的文本"""
    return "钢筋间距 $\\geq$ 100mm，温度 $45^{\\circ}$..."
```

### 测试覆盖的样本数据

| Fixture | 用途 | 测试场景 |
|---------|------|---------|
| `regex_cleaner` | RegexCleaning 实例 | 水印移除、符号转换、空行压缩 |
| `verifier` | MarkdownVerifier 实例 | 长度检查、幻觉检测、结构验证 |
| `sample_markdown` | 标准施工方案文本 | 完整文档处理流程 |
| `sample_html_table` | OCR 残留 HTML | HTML 转 Markdown 处理 |
| `sample_latex_text` | LaTeX 科学计数法 | 符号转换（≥, °, →等） |

---

## 数据安全

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| API Key 泄露 | config.py 中读取 .env | 使用 python-dotenv + 环境变量 |
| 敏感信息 | PDF 中可能包含项目敏感数据 | 未脱敏（MVP 阶段不考虑） |
| 备份策略 | 无 | MVP 阶段不考虑 |
| 测试数据 | 样本数据基于真实文档 | 测试数据与生产隔离（tests/ 目录） |
