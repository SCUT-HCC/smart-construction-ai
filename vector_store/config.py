"""K23 配置 — 向量库 Collection 定义与嵌入模型参数"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "docs" / "knowledge_base"

# 数据源
FRAGMENTS_JSONL = KNOWLEDGE_BASE_DIR / "fragments" / "fragments.jsonl"
CH06_TEMPLATES_DIR = KNOWLEDGE_BASE_DIR / "writing_guides" / "ch06_templates"
WRITING_GUIDES_DIR = KNOWLEDGE_BASE_DIR / "writing_guides"

# 向量库输出
VECTOR_STORE_DIR = KNOWLEDGE_BASE_DIR / "vector_store"
DB_PATH = VECTOR_STORE_DIR / "qmd.db"

# ---------------------------------------------------------------------------
# Chapter → Collection 映射
# ---------------------------------------------------------------------------
CHAPTER_TO_COLLECTION: dict[str, str] = {
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

# 所有 Collection 名称
ALL_COLLECTIONS: list[str] = [
    "ch01_basis",
    "ch06_methods",
    "ch07_quality",
    "ch08_safety",
    "ch09_emergency",
    "ch10_green",
    "equipment",
    "templates",
]

# ---------------------------------------------------------------------------
# 嵌入模型（K20 评测选定）
# ---------------------------------------------------------------------------
EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM: int = 1024
EMBEDDING_DEVICE: str = "cuda"
EMBEDDING_BATCH_SIZE: int = 32

# ---------------------------------------------------------------------------
# 检索参数
# ---------------------------------------------------------------------------
DEFAULT_TOP_K: int = 3
DEFAULT_THRESHOLD: float = 0.6
