"""verifier.py 单元测试 — 覆盖 MarkdownVerifier 的三个 check 方法及 verify 集成。"""

import pytest
from verifier import MarkdownVerifier


# ═══════════════════════════════════════════════════════════════
# check_length()
# ═══════════════════════════════════════════════════════════════


class TestCheckLength:
    """MarkdownVerifier.check_length() 测试组。"""

    def test_pass_above_threshold(self, verifier: MarkdownVerifier) -> None:
        """清洗后保留 60%（> 50%）应通过。"""
        original = "A" * 1000
        cleaned = "A" * 600
        assert verifier.check_length(original, cleaned) is True

    def test_fail_below_threshold(self, verifier: MarkdownVerifier) -> None:
        """清洗后仅保留 30%（< 50%）应失败。"""
        original = "A" * 1000
        cleaned = "A" * 300
        assert verifier.check_length(original, cleaned) is False

    def test_empty_original_passes(self, verifier: MarkdownVerifier) -> None:
        """原文为空应直接通过（避免除零）。"""
        assert verifier.check_length("", "any") is True

    def test_boundary_exactly_at_threshold(self, verifier: MarkdownVerifier) -> None:
        """比例恰好等于 min_length_ratio 应通过（>=）。"""
        original = "A" * 100
        threshold_len = int(100 * verifier.min_length_ratio)
        cleaned = "A" * threshold_len
        assert verifier.check_length(original, cleaned) is True

    def test_cleaned_longer_than_original(self, verifier: MarkdownVerifier) -> None:
        """清洗后比原文长（ratio > 1）应通过。"""
        assert verifier.check_length("短", "比原文更长的内容") is True


# ═══════════════════════════════════════════════════════════════
# check_hallucination()
# ═══════════════════════════════════════════════════════════════


class TestCheckHallucination:
    """MarkdownVerifier.check_hallucination() 测试组。"""

    def test_clean_text_passes(self, verifier: MarkdownVerifier) -> None:
        """正常施工方案内容无幻觉短语应通过。"""
        assert verifier.check_hallucination("## 编制依据\n\n规范标准列表") is True

    def test_chinese_preamble_detected(self, verifier: MarkdownVerifier) -> None:
        """'好的，' 开头应检测为幻觉。"""
        assert verifier.check_hallucination("好的，以下是内容") is False

    def test_english_preamble_detected(self, verifier: MarkdownVerifier) -> None:
        """'Here is the cleaned' 开头应检测为幻觉。"""
        assert verifier.check_hallucination("Here is the cleaned content") is False

    def test_preamble_on_non_first_line(self, verifier: MarkdownVerifier) -> None:
        """幻觉短语出现在非首行行首也应被检测（MULTILINE 模式）。"""
        text = "## 标题\n好的，补充内容"
        assert verifier.check_hallucination(text) is False

    def test_preamble_in_middle_of_line_passes(self, verifier: MarkdownVerifier) -> None:
        """幻觉短语出现在行中间（非行首）不应误报。"""
        text = "参考资料说以下是规范内容"
        assert verifier.check_hallucination(text) is True

    def test_custom_forbidden_phrase_detected(self) -> None:
        """通过 forbidden_phrases 配置的自定义短语应在行首被检测到。"""
        v = MarkdownVerifier(forbidden_phrases=["自定义禁用词"])
        assert v.check_hallucination("自定义禁用词出现在行首") is False

    def test_custom_forbidden_phrase_not_at_line_start(self) -> None:
        """forbidden_phrases 短语出现在行中间不应误报。"""
        v = MarkdownVerifier(forbidden_phrases=["自定义禁用词"])
        assert v.check_hallucination("这里提到自定义禁用词不在行首") is True


# ═══════════════════════════════════════════════════════════════
# check_structure()
# ═══════════════════════════════════════════════════════════════


class TestCheckStructure:
    """MarkdownVerifier.check_structure() 测试组。"""

    def test_valid_table(self, verifier: MarkdownVerifier) -> None:
        """标准 GFM 表格应通过。"""
        text = "| 项目 | 内容 |\n|---|---|\n| A | 1 |"
        assert verifier.check_structure(text) is True

    def test_broken_single_pipe(self, verifier: MarkdownVerifier) -> None:
        """含 | 但数量不足 2 的行应失败。"""
        text = "| 残缺行"
        assert verifier.check_structure(text) is False

    def test_no_table_passes(self, verifier: MarkdownVerifier) -> None:
        """纯文本（无 |）应通过。"""
        text = "这是一段不含表格的纯文本。"
        assert verifier.check_structure(text) is True

    def test_pipe_in_normal_text_passes(self, verifier: MarkdownVerifier) -> None:
        """表格行中含多个 | 应通过。"""
        text = "| 列1 | 列2 | 列3 |"
        assert verifier.check_structure(text) is True


# ═══════════════════════════════════════════════════════════════
# verify() 集成测试
# ═══════════════════════════════════════════════════════════════


class TestVerifyIntegration:
    """MarkdownVerifier.verify() 集成测试组。"""

    def test_all_pass(self, verifier: MarkdownVerifier, sample_markdown: str) -> None:
        """正常内容三项检查应全部通过。"""
        result = verifier.verify(sample_markdown, sample_markdown)
        assert result == {
            "length_check": True,
            "hallucination_check": True,
            "structure_check": True,
        }

    def test_partial_fail_hallucination(self, verifier: MarkdownVerifier) -> None:
        """长度通过但含幻觉前缀时，hallucination_check 应为 False。"""
        original = "A" * 100
        cleaned = "好的，" + "A" * 100
        result = verifier.verify(original, cleaned)
        assert result["length_check"] is True
        assert result["hallucination_check"] is False

    def test_partial_fail_length(self, verifier: MarkdownVerifier) -> None:
        """长度不通过但结构和幻觉检查通过。"""
        original = "A" * 1000
        cleaned = "B" * 100
        result = verifier.verify(original, cleaned)
        assert result["length_check"] is False
        assert result["hallucination_check"] is True
        assert result["structure_check"] is True
