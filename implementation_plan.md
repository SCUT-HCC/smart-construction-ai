# K23 实施计划 — 向量库构建（qmd + sqlite-vec）

> **任务编号**: K23
> **前置依赖**: K16（692 条片段）、K17（235 条模板）、K20（Qwen3-Embedding-0.6B 选型）
> **下游消费者**: 生成系统（案例检索）、审核系统（合规匹配）
> **核心交付物**: 8 个 Collection 向量库 + 统一检索接口
> **技术栈**: qmd + sqlite-vec + Qwen3-Embedding-0.6B

---

## 摘要

将 K16 的 692 条知识片段 + K17 模板 + 撰写指南索引到 qmd 向量库中，
按章节分为 8 个 Collection，提供按章节/工程类型语义检索能力。
使用 qmd 的 SentenceTransformerBackend 加载 Qwen3-Embedding-0.6B（1024 维）生成嵌入。

---

## 8 个 Collection 数据映射

| Collection | 数据来源 | 预估数量 |
|-----------|---------|---------|
| ch01_basis | fragments 一、编制依据 | 18 |
| ch06_methods | fragments 六、施工方法 + ch06_templates/ | 235 + 4 |
| ch07_quality | fragments 七、质量管理 | 86 |
| ch08_safety | fragments 八、安全文明施工 | 89 |
| ch09_emergency | fragments 九、应急预案 | 92 |
| ch10_green | fragments 十、绿色施工 | 45 |
| equipment | fragments 五、施工准备（含设备/材料清单） | 65 |
| templates | fragments 二/三/四 + writing_guides/*.md | 62 + 10 |

**总计**: 692 片段 + ~14 撰写指南/模板 ≈ 706 文档

---

## 拟议变更

| 文件 | 说明 | 标注 |
|------|------|------|
| `vector_store/__init__.py` | 包初始化 | [NEW] |
| `vector_store/__main__.py` | 入口 (`python -m vector_store`) | [NEW] |
| `vector_store/config.py` | Collection 定义、路径、模型配置 | [NEW] |
| `vector_store/indexer.py` | 索引器：加载数据→索引→嵌入 | [NEW] |
| `vector_store/retriever.py` | 检索接口：按章节/工程类型语义检索 | [NEW] |
| `tests/test_vector_store.py` | 单元测试 | [NEW] |

---

## 详细设计

### 1. 配置 (`config.py`)

```python
CHAPTER_TO_COLLECTION = {
    "一、编制依据": "ch01_basis",
    "六、施工方法及工艺要求": "ch06_methods",
    "七、质量管理与控制措施": "ch07_quality",
    "八、安全文明施工管理": "ch08_safety",
    "九、应急预案与处置措施": "ch09_emergency",
    "十、绿色施工与环境保护": "ch10_green",
    "五、施工准备": "equipment",
    "二、工程概况": "templates",
    "三、施工组织机构及职责": "templates",
    "四、施工安排与进度计划": "templates",
}
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DB_PATH = "docs/knowledge_base/vector_store/qmd.db"
```

### 2. 索引器 (`indexer.py`)

```
Step 1: 加载 fragments.jsonl → 按 CHAPTER_TO_COLLECTION 分配 collection
Step 2: 为每条片段构建内容（prepend 元数据前缀：工程类型、章节、标签）
Step 3: 加载 ch06_templates/*.md → 索引到 ch06_methods
Step 4: 加载 writing_guides/*.md（非模板文件）→ 索引到 templates
Step 5: 调用 store.index_document() 逐条索引
Step 6: 使用 SentenceTransformerBackend 生成嵌入
```

### 3. 检索接口 (`retriever.py`)

```python
class VectorRetriever:
    def search(
        self,
        query: str,
        collection: str | None = None,
        engineering_type: str | None = None,
        limit: int = 3,
    ) -> list[SearchResult]: ...
```

---

## 实施步骤

| 步骤 | 内容 | 前置依赖 |
|------|------|---------|
| 1 | 创建 `vector_store/` 模块骨架 + config.py | 无 |
| 2 | 实现 indexer.py（数据加载 + 索引 + 嵌入） | Step 1 |
| 3 | 实现 retriever.py（检索接口） | Step 2 |
| 4 | 端到端构建 + 检索测试 | Step 3 |
| 5 | 编写单元测试，覆盖率 ≥80% | Step 4 |

---

## 验证计划

| 指标 | 目标值 | 验证方式 |
|------|--------|---------|
| 索引文档总数 | ≥692（全部片段） | 自动统计 |
| 8 个 Collection 均有文档 | 每个 ≥1 | 计数验证 |
| 嵌入维度 | 1024 | SentenceTransformerBackend 验证 |
| 检索召回 | top-3 中包含相关结果 | 5 个测试查询 |
| 测试覆盖率 | ≥80% | pytest --cov |
