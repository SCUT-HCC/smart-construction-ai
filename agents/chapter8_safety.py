"""第八章 Agent — 安全文明施工管理。

生成施工方案的安全管理章节，包含安全组织、安全措施、危险点防范、
危险源分析、文明施工、环保措施。
"""

from agents.base import BaseChapterAgent


class Chapter8Agent(BaseChapterAgent):
    """第八章: 安全文明施工管理。

    内容来源：KG 推理（工序→危险源→措施链） + 案例库。
    危险源需覆盖第六章所有施工工序。
    """

    CHAPTER_NUMBER = 8
    CHAPTER_TITLE = "安全文明施工管理"
    TEMPLATE_NAME = "chapter8.j2"
    DEFAULT_MAX_TOKENS = 5120
