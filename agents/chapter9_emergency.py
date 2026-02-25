"""第九章 Agent — 应急预案与处置措施。

生成施工方案的应急预案章节，包含应急组织、响应程序、处置措施、物资准备、演练计划。
"""

from agents.base import BaseChapterAgent


class Chapter9Agent(BaseChapterAgent):
    """第九章: 应急预案与处置措施。

    内容来源：高度模板化。应急处置按事故类型有标准写法，从知识库检索。
    应急类型需覆盖第八章的所有风险。
    """

    CHAPTER_NUMBER = 9
    CHAPTER_TITLE = "应急预案与处置措施"
    TEMPLATE_NAME = "chapter9.j2"
    DEFAULT_MAX_TOKENS = 4096
