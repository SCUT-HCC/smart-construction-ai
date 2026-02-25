"""第五章 Agent — 施工准备。

生成施工方案的施工准备章节，包含技术准备、材料准备、设备配置、劳动力、现场准备。
"""

from agents.base import BaseChapterAgent


class Chapter5Agent(BaseChapterAgent):
    """第五章: 施工准备。

    内容来源：通用模板 + 按工程类型从案例库检索设备/材料清单。
    """

    CHAPTER_NUMBER = 5
    CHAPTER_TITLE = "施工准备"
    TEMPLATE_NAME = "chapter5.j2"
    DEFAULT_MAX_TOKENS = 3072
