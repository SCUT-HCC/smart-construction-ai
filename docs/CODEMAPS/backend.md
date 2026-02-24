<!-- Generated: 2026-02-24 | Files scanned: 20 modules | Token estimate: ~900 -->

# 后端处理流程 - PDF 清洗 + 知识提取

## 管道总览

```
管道 1 (Phase 1): main.py → PDFProcessor → [OCR → Regex → LLM] → Verifier → output/N/final.md
管道 2 (Phase 2): __main__.py → Pipeline.run() → [Split → Annotate → Evaluate → Refine → Dedup] → fragments.jsonl
```

---

## 管道 1: PDF 清洗

### 1. 入口调度（main.py:50）

```python
parse_args() → 解析 --input, --output
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
PDFProcessor.process_file(pdf_path, output_dir)
├─ OCR → 保存 raw.md → 正则 → 保存 regex.md → LLM → 保存 final.md → 验证
PDFProcessor.process_directory(input_dir, output_dir)
└─ 批量调用 process_file()（tqdm 进度条）
```

### 3. OCR 客户端（crawler.py:69）

```python
MonkeyOCRClient.to_markdown(pdf_path: str) -> str
├─ POST /parse (multipart/form-data) → download_url
└─ GET /download_url → ZIP → 解析 .md
```

### 4. 清洗引擎（cleaning.py:434）

```python
RegexCleaning.clean(content: str) -> str
├─ 6 条正则: LaTeX 序号、行末空格、企业名、批复符、孤立页码
└─ 压缩多余空行（3+ → 2）

LLMCleaning.clean(content: str) -> str
├─ split_into_paragraphs() → 按段落分块（chunk_size=2000）
├─ process_chunk() → DeepSeek API（temperature=0.1, max_tokens=4096）
└─ SYSTEM_PROMPT: 禁对话前缀、标题合并、段落连贯、LaTeX→Unicode
```

### 5. 质量验证（verifier.py:67）

```python
MarkdownVerifier.verify(original, cleaned) -> Dict[str, bool]
├─ check_length() → 字数保留率 ≥ 50%
├─ check_hallucination() → 检测 LLM 对话性前缀
└─ check_structure() → 表格管道符数量检测
```

---

## 管道 2: 知识提取

### 入口（knowledge_extraction/__main__.py:5）

```bash
python -u -m knowledge_extraction
```

### 6 步管道编排（pipeline.py:308）

```python
Pipeline.run() → 6 步顺序执行:
│
├─ Step 1: ChapterSplitter.split(doc_path) → List[Section]
│  └─ 正则匹配 Markdown 标题 → 映射到标准 10 章节
│
├─ Step 2: MetadataAnnotator.annotate(sections) → List[Section]
│  └─ 添加 source_doc, chapter, engineering_type, tags
│
├─ Step 3: DensityEvaluator.evaluate(sections) → List[Section]
│  └─ 并行 LLM 调用（max_workers=4），评估 high/medium/low
│
├─ Step 4: ContentRefiner.refine(sections) → List[Section]
│  └─ 仅精炼 medium 密度片段，LLM 摘要简化
│
├─ Step 5: Deduplicator.deduplicate(sections) → List[Section]
│  └─ 按章节分组 → Jaccard 相似度 > 0.8 → 保留最高质量
│
└─ Step 6: 过滤 + 序列化 → output/fragments.jsonl
   └─ 仅保留 high + medium 密度片段（692 条）
```

### 章节分割器（chapter_splitter.py:253）

```python
ChapterSplitter.split(doc_path: str) -> List[Section]
├─ _extract_sections() → 正则解析 Markdown 标题层级
├─ _map_chapter(title) → 匹配标准 10 章节（精确 + 变体关键词）
└─ _is_admin_content(title) → 过滤行政性内容（审批页、签章等）
```

**标准章节映射** (knowledge_extraction/config.py):
```
Ch1 编制依据 ← "编制依据", "编制说明", "依据"
Ch2 工程概况 ← "工程概况", "项目概况", "工程简介"
... (10 章节，每章 2-5 个变体关键词)
```

### 密度评估器（density_evaluator.py:205）

```python
DensityEvaluator.evaluate(sections) -> List[Section]
├─ ThreadPoolExecutor(max_workers=4) → 并行 LLM 调用
├─ 每片段独立评估 → 返回 {"density": "high|medium|low", "reason": "..."}
└─ 评估标准: 技术具体性、数据丰富度、可复用性
```

### 去重器（deduplicator.py:163）

```python
Deduplicator.deduplicate(sections) -> List[Section]
├─ 按 chapter 分组
├─ _dedup_group() → 两两 Jaccard 比较
│  └─ 相似度 > 0.8 → 保留 quality_score 更高的
└─ 合并所有分组结果
```

---

## 配置中心

### 全局配置（config.py:45）

| 配置块 | 关键参数 |
|--------|---------|
| `LLM_CONFIG` | api_key, base_url, model, temperature=0.1, max_tokens=4096, chunk_size=2000 |
| `MONKEY_OCR_CONFIG` | base_url=localhost:7861, timeout=120s |
| `CLEANING_CONFIG` | 6 条正则模式 |
| `VERIFY_CONFIG` | min_length_ratio=0.5, forbidden_phrases |

### 知识提取配置（knowledge_extraction/config.py:176）

| 配置块 | 关键参数 |
|--------|---------|
| `DOCS_TO_PROCESS` | [1..16] 文档列表 |
| `DOC_QUALITY` | 每文档质量评分 1-3 |
| `STANDARD_CHAPTERS` | Ch1-Ch10 标准章节定义 |
| `CHAPTER_MAPPING` | 精确 + 变体关键词映射 |
| `LLM_MAX_WORKERS` | 并发 API 调用数（默认 4） |
| `DEDUP_THRESHOLD` | Jaccard 阈值 0.8 |

---

## 日志系统（utils/logger_system.py:48）

```python
log_msg(level: str, msg: str)   # INFO/WARNING/ERROR，ERROR 自动抛异常
log_json(data: dict, filename)  # 追加到 task_log.json，自动加 timestamp
```

## 错误处理策略

| 场景 | 处理 | 结果 |
|------|------|------|
| OCR 失败 | 返回空字符串 | 跳过该文件 → WARNING |
| LLM API 超时 | 抛出异常 | 文件标记失败 → WARNING |
| 验证失败 | 记录 WARNING | 不阻断（已生成 final.md） |
| 密度评估异常 | 标记为 low | 该片段被过滤 |
| 章节映射失败 | 归入 "未分类" | 保留但不参与去重分组 |

---

## 测试框架

```
tests/
├── conftest.py (66 行) - 共享 fixtures
├── test_cleaning.py (369 行) - RegexCleaning + LLMCleaning
├── test_verifier.py (145 行) - MarkdownVerifier
└── test_knowledge_extraction.py (368 行) - 知识提取管道各模块
```

运行命令:
```bash
conda run -n sca pytest tests/ -v
conda run -n sca pytest tests/ --cov=. --cov-report=term-missing
```
