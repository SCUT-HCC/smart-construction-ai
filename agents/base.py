"""S12 章节 Agent 基类 — BaseChapterAgent + ChapterContext。

提供章节生成的统一流程：模板渲染 → LLM 调用 → 后处理。
子类只需设置类变量（CHAPTER_NUMBER, CHAPTER_TITLE, TEMPLATE_NAME）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from openai import OpenAI

import config as app_config
from input_parser.models import StandardizedInput
from knowledge_retriever.models import RetrievalResponse
from utils.logger_system import log_msg


# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

CHINESE_NUMBERS: tuple[str, ...] = (
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
)

STANDARD_TITLES: dict[int, str] = {
    1: "编制依据",
    2: "工程概况",
    3: "施工组织机构及职责",
    4: "施工安排与进度计划",
    5: "施工准备",
    6: "施工方法及工艺要求",
    7: "质量管理与控制措施",
    8: "安全文明施工管理",
    9: "应急预案与处置措施",
}

# Jinja2 模板目录
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)
_TEMPLATE_ENV.policies["json.dumps_kwargs"] = {"ensure_ascii": False}


# ═══════════════════════════════════════════════════════════════
# ChapterContext 数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class ChapterContext:
    """章节生成上下文。

    由上游 GenerationCoordinator 构建，传递给 Agent.generate()。

    Attributes:
        standardized_input: 标准化工程信息
        macro_view: 前序各章的 150 字摘要列表
        key_details: 当前章节依赖的具体参数
        retrieval: 知识检索结果
        chapter_number: 当前章节编号 (1~9)
        chapter_title: 当前章节标准标题
    """

    standardized_input: StandardizedInput
    macro_view: list[str] = field(default_factory=list)
    key_details: dict[str, Any] = field(default_factory=dict)
    retrieval: RetrievalResponse | None = None
    chapter_number: int = 0
    chapter_title: str = ""


# ═══════════════════════════════════════════════════════════════
# BaseChapterAgent 基类
# ═══════════════════════════════════════════════════════════════


class BaseChapterAgent:
    """章节 Agent 基类。

    子类只需覆盖以下类变量：
    - CHAPTER_NUMBER: 章节编号 (1~9)
    - CHAPTER_TITLE: 标准标题
    - TEMPLATE_NAME: Jinja2 模板文件名（相对于 prompts/agents/）
    - DEFAULT_MAX_TOKENS: 默认最大 token 数

    Args:
        llm_client: OpenAI 兼容客户端（不传则从 config.LLM_CONFIG 懒加载）
        max_tokens: 最大生成 token 数（不传则使用子类 DEFAULT_MAX_TOKENS）
    """

    CHAPTER_NUMBER: int = 0
    CHAPTER_TITLE: str = ""
    TEMPLATE_NAME: str = ""
    DEFAULT_MAX_TOKENS: int = 4096

    def __init__(
        self,
        llm_client: OpenAI | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._max_tokens = (
            max_tokens if max_tokens is not None else self.DEFAULT_MAX_TOKENS
        )

    def _get_llm_client(self) -> OpenAI:
        """懒加载 LLM 客户端。"""
        if self._llm_client is None:
            self._llm_client = OpenAI(
                api_key=app_config.LLM_CONFIG["api_key"],
                base_url=app_config.LLM_CONFIG["base_url"],
            )
        return self._llm_client

    # ---------------------------------------------------------------
    # 公开接口
    # ---------------------------------------------------------------

    def generate(self, context: ChapterContext) -> str:
        """基于上下文生成章节内容。

        流程：渲染 Prompt → 调用 LLM → 后处理。

        Args:
            context: 章节生成上下文

        Returns:
            规范化后的章节内容（Markdown 字符串）
        """
        prompt = self._render_prompt(context)
        raw_content = self._call_llm(prompt)
        return self.post_process(raw_content, context)

    def post_process(self, content: str, context: ChapterContext) -> str:
        """后处理：标题规范化 + 工程名称一致性替换。

        Args:
            content: LLM 生成的原始内容
            context: 章节上下文（用于获取工程名称）

        Returns:
            规范化后的内容
        """
        result = _normalize_chapter_title(content, self.CHAPTER_NUMBER)
        project_name = context.standardized_input.basic.project_name
        if project_name:
            result = _replace_project_name_placeholder(result, project_name)
        return result

    # ---------------------------------------------------------------
    # 内部方法
    # ---------------------------------------------------------------

    def _render_prompt(self, context: ChapterContext) -> str:
        """渲染 Jinja2 模板为完整 Prompt。

        Args:
            context: 章节上下文

        Returns:
            渲染后的 Prompt 字符串
        """
        template_path = f"agents/{self.TEMPLATE_NAME}"
        template = _TEMPLATE_ENV.get_template(template_path)

        # 准备模板变量
        regulations = []
        cases = []
        if context.retrieval is not None:
            regulations = [
                {"content": item.content} for item in context.retrieval.regulations
            ]
            cases = [{"content": item.content} for item in context.retrieval.cases]

        rendered = template.render(
            chapter_title=context.chapter_title
            or STANDARD_TITLES.get(context.chapter_number, ""),
            standardized_input=context.standardized_input.to_dict(),
            regulations=regulations,
            cases=cases,
            macro_view=list(context.macro_view),
            key_details=context.key_details,
        )
        return rendered

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 生成章节内容。

        Args:
            prompt: 渲染后的完整 Prompt

        Returns:
            LLM 返回的内容字符串
        """
        client = self._get_llm_client()
        log_msg(
            "INFO",
            f"Chapter{self.CHAPTER_NUMBER}Agent 调用 LLM，"
            f"max_tokens={self._max_tokens}",
        )

        response = client.chat.completions.create(
            model=app_config.LLM_CONFIG["model"],
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=app_config.LLM_CONFIG["temperature"],
            max_tokens=self._max_tokens,
        )

        content = response.choices[0].message.content or ""
        if not content.strip():
            log_msg("WARNING", f"Chapter{self.CHAPTER_NUMBER}Agent LLM 返回空内容")
        return content


# ═══════════════════════════════════════════════════════════════
# 后处理辅助函数
# ═══════════════════════════════════════════════════════════════


def _normalize_chapter_title(content: str, chapter_number: int) -> str:
    """规范化一级章节标题。

    将各种非标准格式替换为 "X、标准标题" 格式：
    - "第X章 XXX" → "X、标准标题"
    - "N. XXX" → "X、标准标题"
    - "第N章XXX" → "X、标准标题"

    Args:
        content: 原始内容
        chapter_number: 章节编号 (1~9)

    Returns:
        标题规范化后的内容
    """
    if chapter_number not in STANDARD_TITLES:
        return content

    standard_title = STANDARD_TITLES[chapter_number]
    cn_num = CHINESE_NUMBERS[chapter_number - 1]
    canonical = f"{cn_num}、{standard_title}"

    # 模式 1: "第X章 XXX" 或 "第X章XXX"
    content = re.sub(
        rf"第[{cn_num}{chapter_number}]章\s*\S+",
        canonical,
        content,
        count=1,
    )

    # 模式 2: "N. XXX" 或 "N、XXX"（阿拉伯数字开头）
    content = re.sub(
        rf"(?m)^(#{1, 3}\s*)?{chapter_number}[\\.、]\s*\S+",
        rf"\g<1>{canonical}" if re.search(r"^#", content, re.MULTILINE) else canonical,
        content,
        count=1,
    )

    return content


def _replace_project_name_placeholder(content: str, project_name: str) -> str:
    """将占位符替换为实际工程名称。

    替换模式：
    - {{工程名称}}
    - 【工程名称】
    - {工程名称}

    Args:
        content: 原始内容
        project_name: 实际工程名称

    Returns:
        替换后的内容
    """
    patterns = [
        r"\{\{工程名称\}\}",
        r"【工程名称】",
        r"\{工程名称\}",
    ]
    for pattern in patterns:
        content = re.sub(pattern, project_name, content)
    return content
