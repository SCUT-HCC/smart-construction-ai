<!-- Generated: 2026-02-20 | Files scanned: 6 core modules | Token estimate: ~500 -->

# 后端处理流程

## 核心链路

```
main.py → PDFProcessor → [OCR → Regex → LLM] → Verifier → 文件输出
```

## 关键类与方法

### 1. 入口调度（main.py:43）

```python
parse_args() → 解析命令行参数
main() → 初始化组件链 → 触发处理
```

### 2. 处理器（processor.py:90）

```python
PDFProcessor.__init__(ocr_client, regex_cleaner, llm_cleaner, verifier)
├─ process_file(pdf_path, output_dir)
│  └─ OCR → 保存 raw.md → 正则 → 保存 regex.md → LLM → 保存 final.md → 验证
└─ process_directory(input_dir, output_dir)
   └─ 批量调用 process_file()
```

### 3. OCR 客户端（crawler.py:69）

```python
MonkeyOCRClient.to_markdown(pdf_path: str) -> str
├─ POST /file/pdf_to_md (multipart/form-data)
└─ 返回: 原始 Markdown 字符串
```

### 4. 清洗引擎（cleaning.py:434）

#### 4.1 正则清洗
```python
RegexCleaning.clean(content: str) -> str
├─ 应用 6 条正则模式（水印、LaTeX、页码等）
└─ 压缩多余空行
```

#### 4.2 LLM 清洗
```python
LLMCleaning.clean(content: str) -> str
├─ split_into_paragraphs() → 按段落分块
├─ process_chunk(chunk: str) -> str → OpenAI API 调用
│  ├─ system: SYSTEM_PROMPT（434 行中定义）
│  ├─ temperature: 0.1
│  └─ max_tokens: 4096
└─ 合并清洗结果
```

### 5. 质量验证（verifier.py:60）

```python
MarkdownVerifier.verify(original: str, cleaned: str) -> None
├─ check_length_loss() → 字数损失 > 50% → 警告
├─ check_forbidden_phrases() → 检测 LLM 对话性前缀
└─ check_markdown_validity() → 表格闭合检测
```

## 配置中心（config.py:40）

| 配置块 | 关键参数 |
|--------|---------|
| `LLM_CONFIG` | api_key, base_url, model, chunk_size=2000 |
| `MONKEY_OCR_CONFIG` | base_url=localhost:7861, timeout=120s |
| `CLEANING_CONFIG` | 6 条正则模式（水印、LaTeX、页码） |
| `VERIFY_CONFIG` | min_length_ratio=0.5, forbidden_phrases |

## 日志系统（utils/logger_system.py:48）

```python
log_msg(level: str, message: str)  # INFO/WARNING/ERROR（ERROR 自动抛异常）
log_json(data: dict)  # 结构化日志
```

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

- OCR 失败 → 跳过文件，记录 `WARNING`
- LLM API 超时 → 重试机制（待实现）
- 验证失败 → 记录 `WARNING`，不阻断流程
- 目录不存在 → 抛出 `ERROR` 异常
