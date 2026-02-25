"""第七章 Agent — 质量管理与控制措施。

生成施工方案的质量管理章节，包含质量组织、保证措施、检验标准、工艺要求、关键工序控制。
"""

from agents.base import BaseChapterAgent


class Chapter7Agent(BaseChapterAgent):
    """第七章: 质量管理与控制措施。

    内容来源：规范库检验标准 + 案例库工艺要求。
    质量控制需覆盖第六章所有关键工序。
    """

    CHAPTER_NUMBER = 7
    CHAPTER_TITLE = "质量管理与控制措施"
    TEMPLATE_NAME = "chapter7.j2"
    DEFAULT_MAX_TOKENS = 4096
