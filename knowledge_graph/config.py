"""K22 配置 — LightRAG 知识图谱构建参数"""

from __future__ import annotations

from pathlib import Path

import config as app_config

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "docs" / "knowledge_base"

# K21 输出（输入）
ENTITIES_JSON = KNOWLEDGE_BASE_DIR / "knowledge_graph" / "entities.json"
RELATIONS_JSON = KNOWLEDGE_BASE_DIR / "knowledge_graph" / "relations.json"

# LightRAG 工作目录（持久化存储）
LIGHTRAG_WORKING_DIR = KNOWLEDGE_BASE_DIR / "lightrag_storage"

# ---------------------------------------------------------------------------
# LLM 配置（复用项目全局配置）
# ---------------------------------------------------------------------------
LLM_API_KEY: str = app_config.LLM_CONFIG["api_key"]
LLM_BASE_URL: str = app_config.LLM_CONFIG["base_url"]
LLM_MODEL: str = app_config.LLM_CONFIG["model"]

# ---------------------------------------------------------------------------
# 嵌入配置
# ---------------------------------------------------------------------------
EMBEDDING_DIM: int = 1024
EMBEDDING_MAX_TOKENS: int = 8192

# ---------------------------------------------------------------------------
# 关系类型中文标签（用于 LightRAG 的 keywords 字段）
# ---------------------------------------------------------------------------
RELATION_KEYWORDS: dict[str, str] = {
    "requires_equipment": "需要设备,工序设备",
    "produces_hazard": "产生危险源,工序危险",
    "mitigated_by": "安全措施,控制措施,风险缓解",
    "requires_quality_check": "质量控制,质量要点,质量检查",
}
