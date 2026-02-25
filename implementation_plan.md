# S10 — 统一检索接口 KnowledgeRetriever 实施计划

## 摘要

实现 `knowledge_retriever/` 模块，提供 `KnowledgeRetriever` 统一检索入口，协调 `VectorRetriever`（qmd 案例检索）和 KG 推理器（LightRAG 规则推理）。对外暴露 `retrieve_regulations()`、`retrieve_cases()`、`infer_rules()` 和统一 `retrieve()` 方法，按融合策略合并双引擎结果。

---

## 审查点

| # | 问题 | 建议 |
|---|------|------|
| 1 | **命名冲突** — `knowledge_graph/retriever.py` 中已有 `KnowledgeRetriever` 类，与新模块同名 | 将 KG 模块的类重命名为 `KGRetriever`，新模块使用 `KnowledgeRetriever` |
| 2 | `infer_rules()` 是否需要调用 LLM 增强查询（`aquery`）？还是仅使用图遍历？ | MVP 阶段仅使用图遍历（毫秒级），不调用 LLM；预留 `use_llm=False` 参数 |
| 3 | 融合后结果的数据结构？ | 设计统一 `RetrievalItem` dataclass，含 `source`（"kg_rule"/"vector"/"template"）、`priority` 等字段 |
| 4 | `retrieve_regulations()` 具体查询什么？ | 根据工程类型/工序，从 KG 中提取强制要求（危险源→安全措施、工序→质量要点） |

---

## 拟议变更

### 1. 重命名 KG 检索器 `[MODIFY]`

| 文件 | 变更 |
|------|------|
| `knowledge_graph/retriever.py` | 类名 `KnowledgeRetriever` → `KGRetriever` |
| `knowledge_graph/__init__.py` | 更新导出名（如有） |
| `tests/test_knowledge_graph.py` | 更新所有 `KnowledgeRetriever` 引用为 `KGRetriever` |

### 2. 新建 `knowledge_retriever/` 模块 `[NEW]`

```
knowledge_retriever/
├── __init__.py          # 模块说明 + 导出
├── config.py            # 融合策略参数（优先级权重、默认阈值）
├── models.py            # 统一数据模型（RetrievalItem, RetrievalResponse）
└── retriever.py         # KnowledgeRetriever 主类
```

#### 2.1 `models.py` — 统一数据模型

```python
@dataclass
class RetrievalItem:
    """统一检索结果条目。"""
    content: str              # 检索内容
    source: str               # 来源: "kg_rule" | "vector" | "template"
    priority: int             # 优先级: 1(最高) - 4(最低)
    score: float              # 相关性评分（0~1）
    metadata: dict[str, Any]  # 附加信息（collection, file_id, process_name 等）

@dataclass
class RetrievalResponse:
    """统一检索响应。"""
    items: list[RetrievalItem]          # 按优先级+评分排序的结果
    regulations: list[RetrievalItem]    # 强制规范子集（来自 KG）
    cases: list[RetrievalItem]          # 参考案例子集（来自 vector）
    query_context: dict[str, Any]       # 查询上下文（chapter, engineering_type 等）
```

#### 2.2 `config.py` — 融合策略配置

```python
# 优先级定义（数字越小越优先）
PRIORITY_KG_RULE = 1        # LightRAG 推理出的强制规范
PRIORITY_VECTOR_CASE = 2    # qmd 检索的相似案例
PRIORITY_TEMPLATE = 3       # 通用模板（templates collection）
PRIORITY_FREE_GEN = 4       # LLM 自由生成（不在检索阶段产生）

# 默认检索参数
DEFAULT_VECTOR_TOP_K = 3
DEFAULT_VECTOR_THRESHOLD = 0.6

# 需要 KG 推理的章节集合（安全/质量/应急相关章节）
CHAPTERS_NEED_KG: set[str] = {"ch07_quality", "ch08_safety", "ch09_emergency"}
```

#### 2.3 `retriever.py` — KnowledgeRetriever 主类

```python
class KnowledgeRetriever:
    """统一检索接口，协调 VectorRetriever + KGRetriever。

    融合策略优先级：
    1. KG 推理 → 强制规范（priority=1）
    2. 向量检索 → 参考案例（priority=2）
    3. 模板 → 通用框架（priority=3）
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        kg_retriever: KGRetriever,
    ) -> None: ...

    @classmethod
    def from_storage(cls, ...) -> "KnowledgeRetriever":
        """从已有存储加载双引擎。"""
        ...

    def retrieve(
        self,
        query: str,
        chapter: str | None = None,
        engineering_type: str | None = None,
        processes: list[str] | None = None,
    ) -> RetrievalResponse:
        """统一检索入口。内部协调双引擎，按融合策略排序合并。"""
        ...

    def retrieve_regulations(
        self,
        engineering_type: str | None = None,
        processes: list[str] | None = None,
    ) -> list[RetrievalItem]:
        """从 KG 检索强制规范。

        遍历每个工序 → 推理完整要求链（设备/危险源/安全措施/质量要点）→
        将 ProcessRequirements 转换为 RetrievalItem。
        """
        ...

    def retrieve_cases(
        self,
        query: str,
        chapter: str | None = None,
        engineering_type: str | None = None,
        limit: int = DEFAULT_VECTOR_TOP_K,
    ) -> list[RetrievalItem]:
        """从 qmd 检索案例片段。

        调用 VectorRetriever.search()，将 RetrievalResult 转换为 RetrievalItem。
        templates collection 的结果 priority 降为 3。
        """
        ...

    def infer_rules(
        self,
        context: str,
        processes: list[str] | None = None,
    ) -> list[RetrievalItem]:
        """LightRAG 推理（工序→危险源→措施链）。

        MVP 仅使用图遍历（毫秒级），不调用 LLM。
        """
        ...

    def close(self) -> None:
        """释放双引擎资源。"""
        ...
```

#### 核心逻辑 — `retrieve()` 方法流程

```
retrieve(query, chapter, engineering_type, processes)
│
├── 1. 判断章节是否需要 KG 推理（chapter in CHAPTERS_NEED_KG）
│   └── 是 → retrieve_regulations(engineering_type, processes)
│         → 将 ProcessRequirements 转换为 RetrievalItem (priority=1)
│
├── 2. 向量检索案例
│   └── retrieve_cases(query, chapter, engineering_type)
│       → 非 templates → RetrievalItem (priority=2)
│       → templates    → RetrievalItem (priority=3)
│
├── 3. 合并去重
│   └── 按 (priority ASC, score DESC) 排序
│
└── 4. 封装 RetrievalResponse 返回
        ├── items: 全部结果（已排序）
        ├── regulations: 筛选 source=="kg_rule" 的子集
        ├── cases: 筛选 source=="vector" 的子集
        └── query_context: {chapter, engineering_type, processes}
```

### 3. 新建测试 `[NEW]`

| 文件 | 说明 |
|------|------|
| `tests/test_knowledge_retriever.py` | 统一检索接口单元测试 |

**测试策略**：Mock `VectorRetriever` 和 `KGRetriever`，不依赖真实数据库/模型。

**测试覆盖项**：

| 测试类 | 测试点 |
|--------|--------|
| `TestRetrievalItem` | `to_dict()`、默认值、字段验证 |
| `TestRetrievalResponse` | 结果分类（regulations/cases）、排序 |
| `TestKnowledgeRetriever` | `retrieve()` 双引擎协调 |
| | `retrieve_regulations()` — KG 推理 → RetrievalItem 转换 |
| | `retrieve_cases()` — 向量检索 → RetrievalItem 转换 |
| | `retrieve_cases()` — templates 结果 priority=3 |
| | `infer_rules()` — 工序链推理 |
| | 按 chapter 过滤（需要 KG vs 不需要 KG） |
| | 按 engineering_type 过滤透传 |
| | 空结果降级（KG 无结果仍返回 vector 结果） |
| | 融合排序正确性（priority ASC → score DESC） |
| | `close()` 资源释放 |
| | 单引擎模式（仅 vector / 仅 KG） |

---

## 验证计划

```bash
# 1. 重命名后回归 — KG 模块测试全部通过
conda run -n sca pytest tests/test_knowledge_graph.py -v

# 2. 向量库模块测试不受影响
conda run -n sca pytest tests/test_vector_store.py -v

# 3. 新模块测试
conda run -n sca pytest tests/test_knowledge_retriever.py -v

# 4. 覆盖率检查（目标 ≥80%）
conda run -n sca pytest tests/test_knowledge_retriever.py --cov=knowledge_retriever --cov-report=term-missing

# 5. 全量测试不回归
conda run -n sca pytest tests/ -v

# 6. 代码检查
conda run -n sca ruff check knowledge_retriever/ tests/test_knowledge_retriever.py
conda run -n sca ruff format --check knowledge_retriever/ tests/test_knowledge_retriever.py
```

---

## 实施步骤

| 步骤 | 内容 | 前置 |
|------|------|------|
| 1 | 重命名 `KnowledgeRetriever` → `KGRetriever`（3 个文件） | 无 |
| 2 | 运行 `test_knowledge_graph.py` 验证回归 | Step 1 |
| 3 | 创建 `knowledge_retriever/__init__.py` | Step 2 |
| 4 | 创建 `knowledge_retriever/config.py`（融合策略参数） | Step 3 |
| 5 | 创建 `knowledge_retriever/models.py`（RetrievalItem, RetrievalResponse） | Step 4 |
| 6 | 创建 `knowledge_retriever/retriever.py`（KnowledgeRetriever 主类） | Step 5 |
| 7 | 创建 `tests/test_knowledge_retriever.py`（Mock 双引擎） | Step 6 |
| 8 | 运行全量测试 + 覆盖率，确认无回归 | Step 7 |
| 9 | `ruff format` + `ruff check` | Step 8 |
