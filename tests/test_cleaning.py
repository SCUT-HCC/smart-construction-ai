"""cleaning.py 单元测试 — 覆盖 RegexCleaning 和 LLMCleaning 的核心方法。

classmethod / staticmethod 直接通过类调用；
LLMCleaning.clean() 通过 mock OpenAI 客户端测试，不发起真实 API 调用。
"""

from unittest.mock import patch, MagicMock

import pytest
from cleaning import RegexCleaning, LLMCleaning


# ═══════════════════════════════════════════════════════════════
# RegexCleaning.clean()
# ═══════════════════════════════════════════════════════════════


class TestRegexCleaningClean:
    """RegexCleaning.clean() 测试组。"""

    def test_removes_watermark(self, regex_cleaner: RegexCleaning) -> None:
        """水印文字 'CHINA SOUTHERN POWER GRID' 及变体应被移除。"""
        text = "施工方案\nCHINA SOUTHERN POWER GRID CO., LTD.\n第一章"
        result = regex_cleaner.clean(text)
        assert "CHINA SOUTHERN POWER GRID" not in result
        assert "施工方案" in result
        assert "第一章" in result

    def test_converts_textcircled_at_line_start(self, regex_cleaner: RegexCleaning) -> None:
        """行首 $\\textcircled{N}$ 应转为有序列表 'N. '。"""
        text = "$\\textcircled{1}$ 第一步操作"
        result = regex_cleaner.clean(text)
        assert result.startswith("1. ")
        assert "第一步操作" in result

    def test_converts_textcircled_inline(self, regex_cleaner: RegexCleaning) -> None:
        """行中 $\\textcircled{N}$ 应转为 '(N)'。"""
        text = "参见步骤 $\\textcircled{3}$ 的说明"
        result = regex_cleaner.clean(text)
        assert "(3)" in result

    def test_collapses_blank_lines(self, regex_cleaner: RegexCleaning) -> None:
        """3 个及以上连续空行应压缩为不超过 2 个换行。"""
        text = "段落一\n\n\n\n\n段落二"
        result = regex_cleaner.clean(text)
        assert "\n\n\n" not in result
        assert "段落一" in result
        assert "段落二" in result

    def test_removes_standalone_page_numbers(self, regex_cleaner: RegexCleaning) -> None:
        """独占一行的纯数字（页码）应被移除。"""
        text = "正文内容\n42\n继续内容"
        result = regex_cleaner.clean(text)
        assert "\n42\n" not in result

    def test_preserves_normal_content(self, regex_cleaner: RegexCleaning) -> None:
        """正常施工方案文本不应被误修改。"""
        text = "## 工程概况\n\n本工程位于广东省广州市。"
        result = regex_cleaner.clean(text)
        assert "## 工程概况" in result
        assert "本工程位于广东省广州市。" in result


# ═══════════════════════════════════════════════════════════════
# LLMCleaning._convert_latex_symbols()
# ═══════════════════════════════════════════════════════════════


class TestConvertLatexSymbols:
    """LLMCleaning._convert_latex_symbols() 测试组。"""

    def test_standalone_geq(self) -> None:
        """$\\geq$ 应转为 ≥。"""
        assert LLMCleaning._convert_latex_symbols("$\\geq$") == "≥"

    def test_standalone_leq(self) -> None:
        """$\\leq$ 应转为 ≤。"""
        assert LLMCleaning._convert_latex_symbols("$\\leq$") == "≤"

    def test_degree_with_number(self) -> None:
        """$45^{\\circ}$ 应转为 45°。"""
        result = LLMCleaning._convert_latex_symbols("$45^{\\circ}$")
        assert result == "45°"

    def test_degree_without_braces(self) -> None:
        """$90^\\circ$ (无花括号) 应转为 90°。"""
        result = LLMCleaning._convert_latex_symbols("$90^\\circ$")
        assert result == "90°"

    def test_comparison_with_value(self) -> None:
        """$\\leq 0.5$ 应转为 ≤0.5。"""
        result = LLMCleaning._convert_latex_symbols("$\\leq 0.5$")
        assert result == "≤0.5"

    def test_multiple_symbols_in_paragraph(self, sample_latex_text: str) -> None:
        """一段文本中多种 LaTeX 符号应全部正确转换。"""
        result = LLMCleaning._convert_latex_symbols(sample_latex_text)
        assert "$" not in result
        assert "≥" in result
        assert "45°" in result
        assert "≤0.5" in result
        assert "→" in result

    def test_no_false_positive(self) -> None:
        """不含 LaTeX 的普通文本应原样返回。"""
        text = "钢筋间距大于100mm"
        assert LLMCleaning._convert_latex_symbols(text) == text

    def test_priority_long_match_first(self) -> None:
        """$\\geqslant$ 应完整匹配为 ≥，而非部分匹配 \\geq。"""
        result = LLMCleaning._convert_latex_symbols("$\\geqslant$")
        assert result == "≥"

    def test_standalone_circ(self) -> None:
        """$\\circ$ 应转为 °。"""
        assert LLMCleaning._convert_latex_symbols("$\\circ$") == "°"


# ═══════════════════════════════════════════════════════════════
# LLMCleaning._fix_table_separators()
# ═══════════════════════════════════════════════════════════════


class TestFixTableSeparators:
    """LLMCleaning._fix_table_separators() 测试组。"""

    def test_compresses_long_pipe_separator(self) -> None:
        """超长管道分隔行（>500字符）应压缩为 ---。"""
        long_sep = "|" + "-" * 300 + "|" + "-" * 300 + "|"
        result = LLMCleaning._fix_table_separators(long_sep)
        assert len(result) < 100
        assert "---" in result

    def test_compresses_pure_dash_line(self) -> None:
        """50+ 个纯 '-' 独占一行应压缩为 '---'。"""
        result = LLMCleaning._fix_table_separators("-" * 100)
        assert result.strip() == "---"

    def test_preserves_normal_separator(self) -> None:
        """正常长度的表格分隔行不应被修改。"""
        normal = "| --- | --- | --- |"
        assert LLMCleaning._fix_table_separators(normal) == normal

    def test_broken_separator_adds_trailing_pipe(self) -> None:
        """以 | 开头但未以 | 结尾的超长分隔行应补齐末尾 |。"""
        broken = "|" + "-" * 250
        result = LLMCleaning._fix_table_separators(broken)
        assert result.strip().endswith("|")

    def test_mixed_content_only_fixes_separators(self) -> None:
        """混合内容中只修复异常分隔行，其余行不变。"""
        text = "| 标题 | 内容 |\n" + "|" + "-" * 300 + "|" + "-" * 300 + "|\n| 数据 | 值 |"
        result = LLMCleaning._fix_table_separators(text)
        lines = result.split("\n")
        assert lines[0] == "| 标题 | 内容 |"
        assert len(lines[1]) < 100
        assert lines[2] == "| 数据 | 值 |"


# ═══════════════════════════════════════════════════════════════
# LLMCleaning._clean_html_tags()
# ═══════════════════════════════════════════════════════════════


class TestCleanHtmlTags:
    """LLMCleaning._clean_html_tags() 测试组。"""

    def test_html_table_to_markdown(self, sample_html_table: str) -> None:
        """HTML <table> 应转为 GFM Markdown 表格。"""
        result = LLMCleaning._clean_html_tags(sample_html_table)
        assert "<table>" not in result
        assert "<tr>" not in result
        assert "| 序号 | 名称 | 数量 |" in result
        assert "| --- | --- | --- |" in result
        assert "| 1 | 挖掘机 | 2台 |" in result

    def test_br_to_newline(self) -> None:
        """<br> 应转为换行符。"""
        result = LLMCleaning._clean_html_tags("第一行<br>第二行")
        assert result == "第一行\n第二行"

    def test_br_self_closing(self) -> None:
        """<br/> 自闭合标签应转为换行符。"""
        result = LLMCleaning._clean_html_tags("第一行<br/>第二行")
        assert result == "第一行\n第二行"

    def test_removes_span_preserves_text(self) -> None:
        """<span> 标签应移除但保留内部文本。"""
        result = LLMCleaning._clean_html_tags('<span style="color:red">重要文本</span>')
        assert result == "重要文本"

    def test_removes_sup_sub(self) -> None:
        """<sub>/<sup> 标签应移除但保留内部文本。"""
        result = LLMCleaning._clean_html_tags("H<sub>2</sub>O 和 10<sup>3</sup>")
        assert result == "H2O 和 103"

    def test_preserves_plain_text(self) -> None:
        """无 HTML 标签的纯文本应原样返回。"""
        text = "普通施工方案文本，无 HTML 标签。"
        assert LLMCleaning._clean_html_tags(text) == text

    def test_hr_to_markdown(self) -> None:
        """<hr> 应转为 Markdown 分隔线 ---。"""
        result = LLMCleaning._clean_html_tags("段落一<hr>段落二")
        assert "---" in result


# ═══════════════════════════════════════════════════════════════
# LLMCleaning._post_process()
# ═══════════════════════════════════════════════════════════════


class TestPostProcess:
    """LLMCleaning._post_process() 测试组。"""

    def test_removes_chinese_preamble(self) -> None:
        """中文对话前缀 '好的，' 应被移除。"""
        text = "好的，\n## 编制依据"
        result = LLMCleaning._post_process(text)
        assert result.startswith("## 编制依据")

    def test_removes_english_preamble(self) -> None:
        """英文对话前缀 'Sure,' 应被移除。"""
        text = "Sure,\n## Title"
        result = LLMCleaning._post_process(text)
        assert result.startswith("## Title")

    def test_removes_suffix(self) -> None:
        """对话后缀 '以上是...' 应被移除。"""
        text = "正文内容\n以上是处理结果"
        result = LLMCleaning._post_process(text)
        assert "以上是" not in result
        assert "正文内容" in result

    def test_removes_code_fence(self) -> None:
        """```markdown 代码块包裹应被移除。"""
        text = "```markdown\n## 标题\n内容\n```"
        result = LLMCleaning._post_process(text)
        assert "```" not in result
        assert "## 标题" in result

    def test_removes_watermark(self) -> None:
        """残留水印 'CHINA SOUTHERN POWER GRID' 应被移除。"""
        text = "## 标题\nCHINA SOUTHERN POWER GRID CO., LTD.\n正文"
        result = LLMCleaning._post_process(text)
        assert "CHINA SOUTHERN POWER GRID" not in result

    def test_chains_all_steps(self) -> None:
        """同时包含前缀 + LaTeX + HTML + 长分隔行，应全部清理。"""
        text = (
            "好的，以下是处理后的内容：\n"
            "## 工程概况\n\n"
            "温度 $45^{\\circ}$，间距 $\\geq$ 100mm\n\n"
            "| 项目 | 值 |\n"
            + "|" + "-" * 300 + "|" + "-" * 300 + "|\n"
            "| A | 1 |\n\n"
            "<span>保留文本</span>\n"
            "以上是处理结果"
        )
        result = LLMCleaning._post_process(text)
        assert not result.startswith("好的")
        assert "45°" in result
        assert "≥" in result
        assert "-" * 50 not in result
        assert "<span>" not in result
        assert "保留文本" in result
        assert "以上是" not in result

    def test_empty_input(self) -> None:
        """空字符串输入应返回空字符串。"""
        assert LLMCleaning._post_process("") == ""


# ═══════════════════════════════════════════════════════════════
# LLMCleaning._chunk_text()
# ═══════════════════════════════════════════════════════════════


class TestChunkText:
    """LLMCleaning._chunk_text() 测试组 — 通过 mock OpenAI 客户端避免真实连接。"""

    @staticmethod
    def _make_instance(chunk_size: int = 500) -> LLMCleaning:
        """构造一个 mock OpenAI 客户端的 LLMCleaning 实例。"""
        with patch("cleaning.OpenAI"):
            inst = LLMCleaning(api_key="test", base_url="http://test", model="test")
            inst.chunk_size = chunk_size
            return inst

    def test_short_text_single_chunk(self) -> None:
        """短于 chunk_size 的文本应返回单个块。"""
        inst = self._make_instance(chunk_size=2000)
        chunks = inst._chunk_text("短段落")
        assert len(chunks) == 1

    def test_splits_by_paragraph(self) -> None:
        """超过 chunk_size 的多段文本应按段落边界分块。"""
        inst = self._make_instance(chunk_size=100)
        paragraphs = ["段落" + str(i) + "内容" * 20 for i in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = inst._chunk_text(text)
        assert len(chunks) > 1
        joined = "\n\n".join(chunks)
        for p in paragraphs:
            assert p in joined

    def test_header_triggers_early_split(self) -> None:
        """标题段落在块已超过 50% chunk_size 时应触发提前截断。"""
        inst = self._make_instance(chunk_size=200)
        text = "A" * 150 + "\n\n## 新章节标题\n\n后续内容"
        chunks = inst._chunk_text(text)
        found = any(c.strip().startswith("## 新章节标题") for c in chunks)
        assert found, "标题应成为新块的开头"

    def test_empty_input(self) -> None:
        """空字符串应返回包含空串的单元素列表。"""
        inst = self._make_instance(chunk_size=500)
        chunks = inst._chunk_text("")
        assert len(chunks) == 1


# ═══════════════════════════════════════════════════════════════
# LLMCleaning.clean() — mock API 调用
# ═══════════════════════════════════════════════════════════════


class TestLLMCleaningClean:
    """LLMCleaning.clean() 测试组 — 通过 mock OpenAI 验证编排逻辑。"""

    @staticmethod
    def _make_instance_with_mock_api(api_return: str) -> LLMCleaning:
        """构造 mock API 返回固定内容的 LLMCleaning 实例。"""
        with patch("cleaning.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = api_return
            mock_client.chat.completions.create.return_value = mock_response
            inst = LLMCleaning(api_key="test", base_url="http://test", model="test")
            return inst

    def test_clean_calls_api_and_post_processes(self) -> None:
        """clean() 应调用 API 并对结果执行 _post_process。"""
        inst = self._make_instance_with_mock_api("好的，\n## 清洗后内容")
        result = inst.clean("原始文本段落")
        # _post_process 应移除 "好的，" 前缀
        assert "好的" not in result
        assert "## 清洗后内容" in result

    def test_clean_joins_multiple_chunks(self) -> None:
        """多块文本应分别调用 API 后用双换行拼接。"""
        inst = self._make_instance_with_mock_api("处理后的块")
        inst.chunk_size = 50
        # 构造超过 chunk_size 的多段文本
        text = "\n\n".join(["段落" + str(i) + "内容" * 20 for i in range(3)])
        result = inst.clean(text)
        # 多个块的结果应被拼接
        assert result.count("处理后的块") >= 2

    def test_clean_api_error_falls_back_to_original_chunk(self) -> None:
        """API 调用异常时，应降级保留原始块而非抛出异常。"""
        with patch("cleaning.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = ConnectionError("API 超时")
            inst = LLMCleaning(api_key="test", base_url="http://test", model="test")
        result = inst.clean("原始内容应保留")
        assert "原始内容应保留" in result
