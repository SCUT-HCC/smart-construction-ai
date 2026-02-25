"""第二章 Agent — 工程概况。

生成施工方案的工程概况章节，包含工程简介、规模、地质地貌、参建单位。
"""

from agents.base import BaseChapterAgent


class Chapter2Agent(BaseChapterAgent):
    """第二章: 工程概况。

    内容来源：主要依赖用户输入（StandardizedInput），LLM 负责组织语言。
    """

    CHAPTER_NUMBER = 2
    CHAPTER_TITLE = "工程概况"
    TEMPLATE_NAME = "chapter2.j2"
    DEFAULT_MAX_TOKENS = 2048
