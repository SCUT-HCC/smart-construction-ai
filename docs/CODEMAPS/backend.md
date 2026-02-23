<!-- Generated: 2026-02-23 | Files scanned: 13 modules (7 production + 3 tests + utils + config) | Token estimate: ~650 | NEW: pytest framework -->

# 后端处理流程 - 生产代码与测试框架

## 核心链路

```
main.py → PDFProcessor → [OCR → Regex → LLM] → Verifier → 文件输出
```

## 关键类与方法

### 1. 入口调度（main.py:50）

```python
parse_args() → 解析命令行参数
main() → 初始化组件链 → 触发处理
```

**依赖注入**:
```python
components = {
    'ocr_client': MonkeyOCRClient(base_url, timeout),
    'regex_cleaner': RegexCleaning(patterns),
    'llm_cleaner': LLMCleaning(api_key, base_url, model, temperature),
    'verifier': MarkdownVerifier(min_ratio, forbidden_phrases),
}
processor = PDFProcessor(**components)
```

### 2. 处理器（processor.py:90）

```python
PDFProcessor.__init__(ocr_client, regex_cleaner, llm_cleaner, verifier)
├─ process_file(pdf_path, output_dir)
│  └─ OCR → 保存 raw.md → 正则 → 保存 regex.md → LLM → 保存 final.md → 验证
└─ process_directory(input_dir, output_dir)
   └─ 批量调用 process_file()（tqdm 进度条）
```

### 3. OCR 客户端（crawler.py:69）

```python
MonkeyOCRClient.to_markdown(pdf_path: str) -> str
├─ POST /parse (multipart/form-data)
├─ 获取 download_url
├─ GET /download_url (下载 ZIP)
└─ 解析 ZIP 获取 .md 文件
```

**错误处理**:
- 网络异常 → 返回空字符串
- ZIP 解析失败 → 返回空字符串
- 所有异常都记录 ERROR（自动抛异常）

### 4. 清洗引擎（cleaning.py:434）

#### 4.1 正则清洗
```python
RegexCleaning.clean(content: str) -> str
├─ 应用 6 条正则模式：
│  1. LaTeX 圆圈数字 → 标准序号
│  2. LaTeX 圆圈数字（内联） → 括号序号
│  3. 行末多余空格
│  4. 企业名称（CHINA SOUTHERN POWER GRID）
│  5. 批复符号（批/★）
│  6. 孤立页码
└─ 压缩多余空行（3+ → 2）
```

#### 4.2 LLM 清洗
```python
LLMCleaning.clean(content: str) -> str
├─ split_into_paragraphs() → 按段落分块（chunk_size=2000）
├─ process_chunk(chunk: str) -> str
│  ├─ OpenAI API 调用
│  ├─ system: SYSTEM_PROMPT (434 行中定义)
│  ├─ temperature: 0.1
│  └─ max_tokens: 4096
└─ 合并清洗结果

SYSTEM_PROMPT 定义（434 行）:
- 禁止对话性前缀（好的、以下是等）
- 允许的操作（标题合并、嵌套列表、段落连贯等）
- LaTeX 符号 → Unicode 映射（100+ 符号）
```

### 5. 质量验证（verifier.py:60）

```python
MarkdownVerifier.verify(original: str, cleaned: str) -> Dict[str, bool]
├─ check_length() → 字数保留率 ≥ 50%
├─ check_hallucination() → 检测 LLM 对话性前缀（正则行首匹配）
└─ check_structure() → 表格管道符数量检测
```

## 配置中心（config.py:45）

| 配置块 | 关键参数 | 说明 |
|--------|---------|------|
| `LLM_CONFIG` | api_key, base_url, model | 从 .env 读取，温度=0.1，最大4096 tokens，分块=2000 |
| `MONKEY_OCR_CONFIG` | base_url, timeout | localhost:7861，超时 120s |
| `PATHS` | input_dir, output_dir, log_dir | 输入输出路径 |
| `CLEANING_CONFIG` | remove_watermark, company_name, regex_patterns | 6 条正则模式列表 |
| `VERIFY_CONFIG` | min_length_ratio, forbidden_phrases | 保留率 ≥50%，禁止短语清单 |

## 日志系统（utils/logger_system.py:48）

```python
log_msg(level: str, msg: str)
  # INFO/WARNING/ERROR
  # ERROR 级别自动抛异常

log_json(data: dict, filename: str = "task_log.json")
  # 追加到 task_log.json
  # 自动添加 timestamp
```

**依赖**: 标准库 `logging`（已移除 loguru/watchdog 僵尸依赖）

## 文件输出结构

```
output/
├─ 1/
│  ├─ raw.md      # OCR 原始输出
│  ├─ regex.md    # 正则清洗后
│  └─ final.md    # LLM 清洗后（最终产物）
├─ 2/
└─ ...16/
```

## 错误处理策略

| 场景 | 处理 | 结果 |
|------|------|------|
| OCR 失败（网络/格式） | 返回空字符串 | 跳过该文件 → WARNING |
| LLM API 超时 | 抛出异常 | 文件标记失败 → WARNING |
| 验证失败 | 记录 WARNING | 不阻断流程（已生成 final.md） |
| 目录不存在 | 抛出异常 | 任务停止 → ERROR |

---

## 测试框架（NEW - 2026-02-23）

### 测试结构

```
tests/
├── conftest.py (66 行) - pytest fixtures 配置
├── test_cleaning.py (369 行) - RegexCleaning + LLMCleaning 单元测试
└── test_verifier.py (145 行) - MarkdownVerifier 单元测试
```

### pytest 配置

**Fixtures** (conftest.py):
```python
@pytest.fixture
def regex_cleaner() -> RegexCleaning:
    """使用项目配置的 RegexCleaning 实例"""
    return RegexCleaning(config.CLEANING_CONFIG["regex_patterns"])

@pytest.fixture
def verifier() -> MarkdownVerifier:
    """使用项目配置的 MarkdownVerifier 实例"""
    return MarkdownVerifier(
        min_length_ratio=config.VERIFY_CONFIG["min_length_ratio"],
        forbidden_phrases=config.VERIFY_CONFIG["forbidden_phrases"]
    )

@pytest.fixture
def sample_markdown() -> str:
    """典型施工方案 Markdown 片段"""
    # 包含标题、表格、列表的样本数据

@pytest.fixture
def sample_latex_text() -> str:
    """包含 LaTeX 符号的文本片段"""
```

### RegexCleaning 单元测试 (test_cleaning.py)

覆盖场景:
```
✓ test_removes_watermark - CHINA SOUTHERN POWER GRID 水印移除
✓ test_converts_textcircled_at_line_start - 行首 \textcircled{N} → "N. "
✓ test_converts_textcircled_inline - 行中 \textcircled{N} → "(N)"
✓ test_collapses_blank_lines - 多余空行压缩
✓ test_removes_standalone_page_numbers - 独占一行的页码移除
✓ test_preserves_normal_content - 正常文本保护
... (6+ 个测试，覆盖正则清洗的主要场景)
```

### LLMCleaning 单元测试 (test_cleaning.py)

使用 `@patch` mock OpenAI 客户端，避免真实 API 调用:
```python
with patch('openai.OpenAI') as mock_openai:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "cleaned content"

    llm_cleaner = LLMCleaning(api_key, base_url, model, temperature=0.1)
    result = llm_cleaner.clean(text)
    # 验证 OpenAI 调用及返回结果
```

### MarkdownVerifier 单元测试 (test_verifier.py)

覆盖场景:
```
✓ test_verify_all_checks_pass - 所有验证通过
✓ test_verify_length_check_fails - 字数保留率不足
✓ test_check_hallucination_preamble - 检测对话性前缀
✓ test_check_hallucination_forbidden_phrase - 检测禁用短语
✓ test_check_structure_valid_table - 有效 Markdown 表格
... (5+ 个测试，覆盖验证逻辑)
```

### 运行测试

```bash
# 激活 Conda 环境
conda activate sca

# 运行所有测试
conda run -n sca pytest tests/ -v

# 运行特定测试文件
conda run -n sca pytest tests/test_cleaning.py -v

# 运行带覆盖率报告
conda run -n sca pytest tests/ --cov=. --cov-report=term-missing

# 运行特定测试类
conda run -n sca pytest tests/test_cleaning.py::TestRegexCleaningClean -v
```

### 依赖

| 包 | 版本 | 用途 |
|------|------|------|
| pytest | 9.0.2 | 测试框架 |
| pytest-cov | 7.0.0 | 覆盖率报告 |
| unittest.mock | 标准库 | Mock OpenAI 客户端 |
