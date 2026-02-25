"""S11 配置 — 字段校验规则与 LLM 提取 Prompt 模板"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 必填字段（section, field_name）
# ---------------------------------------------------------------------------
REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("basic", "project_name"),
    ("basic", "project_type"),
]

# ---------------------------------------------------------------------------
# 合法顶层 section 键
# ---------------------------------------------------------------------------
VALID_SECTIONS: set[str] = {"basic", "technical", "participants", "constraints"}

# ---------------------------------------------------------------------------
# LLM 提取 Prompt — 自然语言 / OCR 文本 → 结构化 JSON
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT: str = (
    "你是一个结构化信息提取助手。从用户提供的施工方案文本中提取工程信息，"
    "以 JSON 格式返回。仅输出 JSON，不要输出任何其他文字。"
)

EXTRACTION_USER_TEMPLATE: str = (
    "从以下文本中提取施工方案的工程信息。\n\n"
    "要求的 JSON 结构：\n"
    "{{\n"
    '  "basic": {{"project_name": "", "project_type": "", "location": "", "scale": ""}},\n'
    '  "technical": {{"geology": "", "climate": "", "special_requirements": ""}},\n'
    '  "participants": {{"owner": "", "contractor": "", "supervisor": "", "designer": ""}},\n'
    '  "constraints": {{"timeline": "", "budget": "", "risks": []}}\n'
    "}}\n\n"
    "规则：\n"
    "- 如果文本中未提及某个字段，该字段填空字符串或空列表\n"
    "- risks 字段为字符串列表，每条风险单独一项\n"
    "- 仅输出 JSON，不要输出任何解释\n\n"
    "文本内容：\n{text}\n\n"
    "JSON 输出："
)

# ---------------------------------------------------------------------------
# LLM 提取重试次数
# ---------------------------------------------------------------------------
EXTRACTION_MAX_RETRIES: int = 1
