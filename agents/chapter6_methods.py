"""第六章 Agent — 施工方法及工艺要求。

生成施工方案的施工方法章节，包含工艺流程、主要方法、分项技术、技术措施、验收标准。
这是最难模板化的章节，高度依赖案例检索。
"""

from agents.base import BaseChapterAgent


class Chapter6Agent(BaseChapterAgent):
    """第六章: 施工方法及工艺要求。

    内容来源：案例检索（按工程类型） + 规范库。
    这是最核心也最难生成的章节，max_tokens 设置较高。
    """

    CHAPTER_NUMBER = 6
    CHAPTER_TITLE = "施工方法及工艺要求"
    TEMPLATE_NAME = "chapter6.j2"
    DEFAULT_MAX_TOKENS = 6144
