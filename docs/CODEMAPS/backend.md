<!-- Generated: 2026-02-25 | Files scanned: 42 production modules | Token estimate: ~950 -->

# 后端处理流程

## 管道总览

```
管道 1 (Phase 1): main.py → PDFProcessor → [OCR → Regex → LLM] → Verifier → final.md
管道 2 (Phase 2): knowledge_extraction → Pipeline.run() → [Split→Annotate→Evaluate→Refine→Dedup] → fragments.jsonl
管道 3 (Phase 2): entity_extraction → Pipeline.run() → [Rule→LLM→Normalize] → entities.json + relations.json
管道 4 (Phase 2): vector_store → build_vector_store() → 8 Collection qmd.db → VectorRetriever.search()
管道 5 (Phase 2): knowledge_graph → build → LightRAG → KGRetriever.infer_process_chain()
管道 6 (S10):     knowledge_retriever → KnowledgeRetriever.retrieve() → 融合双引擎 → RetrievalResponse
```

---

## 管道 1: PDF 清洗（Phase 1）

```python
main.py:parse_args() → processor.py:PDFProcessor.process_file()
├─ crawler.py:MonkeyOCRClient.to_markdown()     # POST /parse → ZIP → .md
├─ cleaning.py:RegexCleaning.clean()             # 6 条正则
├─ cleaning.py:LLMCleaning.clean()               # DeepSeek API, chunk_size=2000
└─ verifier.py:MarkdownVerifier.verify()         # 字数保留率≥50%, 幻觉检测
```

## 管道 2: 知识提取（Phase 2 - K16）

```python
knowledge_extraction/__main__.py → Pipeline.run()
├─ ChapterSplitter.split()         # 正则匹配标题 → 标准 10 章节
├─ MetadataAnnotator.annotate()    # 添加 source_doc, chapter, tags
├─ DensityEvaluator.evaluate()     # 并行 LLM (max_workers=4), high/medium/low
├─ ContentRefiner.refine()         # 仅精炼 medium 密度
├─ Deduplicator.deduplicate()      # 按章节 Jaccard>0.8 去重
└─ 序列化 → fragments.jsonl (692 条)
```

## 管道 3: 实体/关系抽取（Phase 2 - K21）

```python
entity_extraction/__main__.py → Pipeline.run()
├─ RuleExtractor.extract()        # 正则规则抽取 (577 行)
├─ LLMExtractor.extract()         # LLM 结构化抽取 (345 行)
├─ Normalizer.normalize()         # 实体归一化、去重、合并 (307 行)
└─ 输出 entities.json (2019) + relations.json (1452)
```

**Schema** (entity_extraction/schema.py:145):
- 实体类型: process, equipment, hazard, safety_measure, quality_point
- 关系类型: requires_equipment, produces_hazard, mitigated_by, requires_quality_check

## 管道 4: 向量库构建（Phase 2 - K23）

```python
vector_store/__main__.py → build_vector_store()
├─ indexer.py:_load_fragments()              # 加载 fragments.jsonl
├─ indexer.py:_index_fragments()             # 按 CHAPTER_TO_COLLECTION 分配
├─ indexer.py:_index_extra_sources()         # ch06_templates + writing_guides
└─ SentenceTransformerBackend.embed()        # Qwen3-Embedding-0.6B, 1024 维

retriever.py:VectorRetriever
├─ .search(query, collection, engineering_type) → list[RetrievalResult]
├─ .search_multi_collection(query, collections) → dict[str, list]
└─ .get_collection_stats() → dict[str, int]
```

**8 Collections**: ch01_basis, ch06_methods, ch07_quality, ch08_safety, ch09_emergency, ch10_green, equipment, templates

## 管道 5: 知识图谱构建（Phase 2 - K22）

```python
knowledge_graph/__main__.py → build
├─ converter.py:convert_k21_to_lightrag()    # K21 → LightRAG 格式
├─ builder.py:create_rag_instance()          # 初始化 LightRAG
└─ builder.py:import + initialize_storages() # 导入实体/关系/chunks

retriever.py:KGRetriever
├─ .infer_process_chain(process) → ProcessRequirements   # 图遍历，毫秒级
├─ .infer_hazard_measures(hazard) → list[str]
├─ .get_neighbors(entity, relation_type) → list[str]
├─ .aquery(question, mode) → str                         # LLM 查询，秒级
└─ .get_all_entities(entity_type) → list[dict]
```

## 管道 6: 统一检索（S10）

```python
knowledge_retriever/retriever.py:KnowledgeRetriever
├─ .retrieve(query, chapter, engineering_type, processes) → RetrievalResponse
│   ├─ _chapter_needs_kg(chapter)           # ch07/ch08/ch09 需要 KG
│   ├─ retrieve_regulations(processes)      # KG → RetrievalItem (priority=1)
│   ├─ retrieve_cases(query, chapter)       # Vector → RetrievalItem (priority=2/3)
│   └─ _merge_and_sort(items)              # priority ASC, score DESC
├─ .retrieve_regulations(processes) → list[RetrievalItem]
├─ .retrieve_cases(query, chapter) → list[RetrievalItem]
├─ .infer_rules(context, processes) → list[RetrievalItem]
└─ .close()
```

**融合优先级**: KG 规范(1) > 向量案例(2) > 模板(3) > LLM 自由生成(4)

## 审核系统入口（K19）

```python
review/chapter_mapper.py:ChapterMapper
├─ .map(title) → ChapterID          # 三级回退：精确→关键词→模糊
└─ 113 测试通过
```

---

## 配置中心

| 配置文件 | 关键参数 |
|----------|---------|
| `config.py` (45) | LLM_CONFIG, MONKEY_OCR_CONFIG, CLEANING_CONFIG |
| `knowledge_extraction/config.py` (176) | CHAPTER_MAPPING, DOC_QUALITY, DEDUP_THRESHOLD |
| `entity_extraction/config.py` (155) | 实体类型定义, 规则模式, LLM prompt |
| `vector_store/config.py` (62) | CHAPTER_TO_COLLECTION, EMBEDDING_MODEL, TOP_K |
| `knowledge_graph/config.py` (43) | LIGHTRAG_WORKING_DIR, RELATION_KEYWORDS |
| `knowledge_retriever/config.py` (32) | PRIORITY_*, CHAPTERS_NEED_KG |

## 日志系统

```python
utils/logger_system.py:log_msg(level, msg)   # INFO/WARNING/ERROR，ERROR 自动抛异常
utils/logger_system.py:log_json(data, file)   # 追加 JSON + timestamp
```

---

## 测试框架

```
tests/ (10 文件, 4246 行)
├── conftest.py (66)                    - 共享 fixtures
├── test_cleaning.py (369)              - RegexCleaning + LLMCleaning
├── test_verifier.py (145)              - MarkdownVerifier
├── test_knowledge_extraction.py (368)  - 知识提取管道
├── test_entity_extraction.py (878)     - 实体/关系抽取（K21）
├── test_chapter_mapper.py (502)        - 章节映射（K19）
├── test_vector_store.py (510)          - 向量库（K23）
├── test_knowledge_graph.py (699)       - 知识图谱（K22）
└── test_knowledge_retriever.py (709)   - 统一检索（S10）
```

运行: `conda run -n sca pytest tests/ -v` → 422 passed
