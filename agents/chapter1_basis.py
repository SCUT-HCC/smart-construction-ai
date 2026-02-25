"""第一章 Agent — 编制依据。

生成施工方案的编制依据章节，包含法律法规、行业标准、设计文件、合同约定。
"""

from agents.base import BaseChapterAgent


class Chapter1Agent(BaseChapterAgent):
    """第一章: 编制依据。

    内容来源：知识库规范检索 + 用户输入的设计文件/合同信息。
    """

    CHAPTER_NUMBER = 1
    CHAPTER_TITLE = "编制依据"
    TEMPLATE_NAME = "chapter1.j2"
    DEFAULT_MAX_TOKENS = 2048
