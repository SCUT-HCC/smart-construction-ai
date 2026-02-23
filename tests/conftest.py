"""pytest 共享 fixture — 为 cleaning / verifier 模块测试提供可复用的实例和样本数据。"""

import pytest
import config
from cleaning import RegexCleaning
from verifier import MarkdownVerifier


# ── 实例 fixture ──────────────────────────────────────────────


@pytest.fixture
def regex_cleaner() -> RegexCleaning:
    """使用项目配置中的正则模式创建 RegexCleaning 实例。"""
    return RegexCleaning(config.CLEANING_CONFIG["regex_patterns"])


@pytest.fixture
def verifier() -> MarkdownVerifier:
    """使用项目配置创建 MarkdownVerifier 实例。"""
    return MarkdownVerifier(
        min_length_ratio=config.VERIFY_CONFIG["min_length_ratio"],
        forbidden_phrases=config.VERIFY_CONFIG["forbidden_phrases"],
    )


# ── 样本数据 fixture ──────────────────────────────────────────


@pytest.fixture
def sample_markdown() -> str:
    """包含标题、表格、列表的典型施工方案 Markdown 片段。"""
    return (
        "## 编制依据\n\n"
        "本工程施工方案依据以下规范编制：\n\n"
        "1. GB 50300-2013 建筑工程施工质量验收统一标准\n"
        "2. DL/T 5210.1-2012 电力建设施工质量验收规程\n\n"
        "## 工程概况\n\n"
        "| 项目 | 内容 |\n"
        "|---|---|\n"
        "| 工程名称 | 某 110kV 变电站新建工程 |\n"
        "| 建设单位 | 南方电网 |\n\n"
        "### 工程特点\n\n"
        "本工程位于广东省，地形以丘陵为主。\n"
    )


@pytest.fixture
def sample_html_table() -> str:
    """包含 HTML <table> 的 OCR 残留内容。"""
    return (
        "<table>"
        "<tr><th>序号</th><th>名称</th><th>数量</th></tr>"
        "<tr><td>1</td><td>挖掘机</td><td>2台</td></tr>"
        "<tr><td>2</td><td>吊车</td><td>1台</td></tr>"
        "</table>"
    )


@pytest.fixture
def sample_latex_text() -> str:
    """包含多种 LaTeX 符号的文本片段。"""
    return (
        "钢筋间距 $\\geq$ 100mm，温度 $45^{\\circ}$，"
        "误差 $\\leq 0.5$ mm，方向 $\\rightarrow$ 东。"
    )
