<!-- Generated: 2026-02-23 | Files scanned: 6 core modules | Token estimate: ~500 -->

# 后端处理流程

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
