"""第三章 Agent — 施工组织机构及职责。

生成施工方案的组织机构章节，包含组织架构、管理人员职责、质安人员配置。
"""

from agents.base import BaseChapterAgent


class Chapter3Agent(BaseChapterAgent):
    """第三章: 施工组织机构及职责。

    内容来源：通用职责模板（知识库） + 工程规模匹配人员配置。
    """

    CHAPTER_NUMBER = 3
    CHAPTER_TITLE = "施工组织机构及职责"
    TEMPLATE_NAME = "chapter3.j2"
    DEFAULT_MAX_TOKENS = 3072
