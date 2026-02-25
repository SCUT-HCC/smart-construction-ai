"""第四章 Agent — 施工安排与进度计划。

生成施工方案的施工安排章节，包含总体部署、施工顺序、进度计划、关键节点。
"""

from agents.base import BaseChapterAgent


class Chapter4Agent(BaseChapterAgent):
    """第四章: 施工安排与进度计划。

    内容来源：案例检索框架 + 用户输入工期 + LLM 排布。
    """

    CHAPTER_NUMBER = 4
    CHAPTER_TITLE = "施工安排与进度计划"
    TEMPLATE_NAME = "chapter4.j2"
    DEFAULT_MAX_TOKENS = 3072
