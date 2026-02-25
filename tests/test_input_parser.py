"""S11 输入标准化模块单元测试。

覆盖 models.py、config.py、parser.py 的核心逻辑。
使用 Mock LLM 和 OCR 客户端，不依赖真实外部服务。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from input_parser.config import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    REQUIRED_FIELDS,
    VALID_SECTIONS,
)
from input_parser.models import (
    BasicInfo,
    ConstraintInfo,
    ParticipantInfo,
    StandardizedInput,
    TechnicalInfo,
)
from input_parser.parser import (
    InputParser,
    _dict_to_basic,
    _dict_to_constraints,
    _dict_to_participants,
    _dict_to_technical,
    _extract_json_from_response,
)


# ═══════════════════════════════════════════════════════════════
# 测试数据 Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def full_input_dict() -> dict:
    """完整的输入 JSON 字典。"""
    return {
        "basic": {
            "project_name": "220kV 某某输电线路工程",
            "project_type": "输电线路",
            "location": "广东省广州市",
            "scale": "线路全长 50km",
        },
        "technical": {
            "geology": "丘陵地形，局部岩石",
            "climate": "亚热带季风气候",
            "special_requirements": "跨越高速公路",
        },
        "participants": {
            "owner": "南方电网广东公司",
            "contractor": "某某建设集团",
            "supervisor": "某某监理公司",
            "designer": "某某设计院",
        },
        "constraints": {
            "timeline": "2026年12月完工",
            "budget": "5000万元",
            "risks": ["台风季施工", "地质复杂"],
        },
    }


@pytest.fixture
def minimal_input_dict() -> dict:
    """仅包含必填字段的最小输入。"""
    return {
        "basic": {
            "project_name": "测试工程",
            "project_type": "变电站",
        }
    }


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock OpenAI 客户端，返回预设 JSON。"""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(
        {
            "basic": {
                "project_name": "110kV 输电线路",
                "project_type": "输电线路",
                "location": "深圳",
                "scale": "10km",
            },
            "technical": {
                "geology": "平原",
                "climate": "温暖",
                "special_requirements": "",
            },
            "participants": {
                "owner": "南方电网",
                "contractor": "",
                "supervisor": "",
                "designer": "",
            },
            "constraints": {"timeline": "6个月", "budget": "", "risks": ["暴雨"]},
        },
        ensure_ascii=False,
    )
    mock.chat.completions.create.return_value = mock_response
    return mock


@pytest.fixture
def mock_ocr_client() -> MagicMock:
    """Mock MonkeyOCR 客户端。"""
    mock = MagicMock()
    mock.to_markdown.return_value = (
        "# 220kV 某某输电线路工程施工方案\n\n"
        "## 工程概况\n\n"
        "工程名称：220kV 某某输电线路工程\n"
        "工程类型：输电线路\n"
        "建设地点：广东省\n"
    )
    return mock


@pytest.fixture
def parser(mock_llm_client: MagicMock, mock_ocr_client: MagicMock) -> InputParser:
    """带 Mock 客户端的 InputParser。"""
    return InputParser(llm_client=mock_llm_client, ocr_client=mock_ocr_client)


# ═══════════════════════════════════════════════════════════════
# TestConfig — 配置常量
# ═══════════════════════════════════════════════════════════════


class TestConfig:
    """配置常量测试。"""

    def test_required_fields_contains_project_name(self) -> None:
        assert ("basic", "project_name") in REQUIRED_FIELDS

    def test_required_fields_contains_project_type(self) -> None:
        assert ("basic", "project_type") in REQUIRED_FIELDS

    def test_valid_sections(self) -> None:
        assert VALID_SECTIONS == {"basic", "technical", "participants", "constraints"}

    def test_extraction_prompts_not_empty(self) -> None:
        assert len(EXTRACTION_SYSTEM_PROMPT) > 0
        assert len(EXTRACTION_USER_TEMPLATE) > 0

    def test_extraction_user_template_has_placeholder(self) -> None:
        assert "{text}" in EXTRACTION_USER_TEMPLATE


# ═══════════════════════════════════════════════════════════════
# TestBasicInfo — 数据模型基本行为
# ═══════════════════════════════════════════════════════════════


class TestBasicInfo:
    """BasicInfo dataclass 测试。"""

    def test_default_values(self) -> None:
        info = BasicInfo()
        assert info.project_name == ""
        assert info.project_type == ""
        assert info.location == ""
        assert info.scale == ""

    def test_with_values(self) -> None:
        info = BasicInfo(project_name="测试", project_type="变电站")
        assert info.project_name == "测试"
        assert info.project_type == "变电站"

    def test_to_dict(self) -> None:
        info = BasicInfo(project_name="工程A", project_type="输电线路")
        d = info.to_dict()
        assert d["project_name"] == "工程A"
        assert d["project_type"] == "输电线路"


# ═══════════════════════════════════════════════════════════════
# TestStandardizedInput — 核心数据结构
# ═══════════════════════════════════════════════════════════════


class TestStandardizedInput:
    """StandardizedInput 测试。"""

    def test_default_construction(self) -> None:
        si = StandardizedInput()
        assert si.basic.project_name == ""
        assert isinstance(si.technical, TechnicalInfo)
        assert isinstance(si.participants, ParticipantInfo)
        assert isinstance(si.constraints, ConstraintInfo)

    def test_to_dict_structure(self, full_input_dict: dict) -> None:
        si = StandardizedInput(
            basic=BasicInfo(**full_input_dict["basic"]),
            technical=TechnicalInfo(**full_input_dict["technical"]),
            participants=ParticipantInfo(**full_input_dict["participants"]),
            constraints=ConstraintInfo(**full_input_dict["constraints"]),
        )
        d = si.to_dict()
        assert set(d.keys()) == {"basic", "technical", "participants", "constraints"}
        assert d["basic"]["project_name"] == "220kV 某某输电线路工程"
        assert d["constraints"]["risks"] == ["台风季施工", "地质复杂"]

    def test_validate_pass(self) -> None:
        si = StandardizedInput(
            basic=BasicInfo(project_name="工程", project_type="输电")
        )
        errors = si.validate()
        assert errors == []

    def test_validate_missing_project_name(self) -> None:
        si = StandardizedInput(basic=BasicInfo(project_type="输电"))
        errors = si.validate()
        assert any("project_name" in e for e in errors)

    def test_validate_missing_project_type(self) -> None:
        si = StandardizedInput(basic=BasicInfo(project_name="工程"))
        errors = si.validate()
        assert any("project_type" in e for e in errors)

    def test_validate_both_missing(self) -> None:
        si = StandardizedInput()
        errors = si.validate()
        assert len(errors) == 2

    def test_validate_whitespace_only(self) -> None:
        """空白字符串视为缺失。"""
        si = StandardizedInput(basic=BasicInfo(project_name="  ", project_type="\t"))
        errors = si.validate()
        assert len(errors) == 2

    def test_immutability_to_dict(self) -> None:
        """to_dict 返回的字典修改不影响原对象。"""
        si = StandardizedInput(
            basic=BasicInfo(project_name="原名", project_type="输电"),
            constraints=ConstraintInfo(risks=["风险1"]),
        )
        d = si.to_dict()
        d["basic"]["project_name"] = "篡改"
        d["constraints"]["risks"].append("篡改风险")
        assert si.basic.project_name == "原名"
        assert si.constraints.risks == ["风险1"]


# ═══════════════════════════════════════════════════════════════
# TestHelpers — 辅助函数
# ═══════════════════════════════════════════════════════════════


class TestHelpers:
    """辅助函数测试。"""

    def test_dict_to_basic_full(self) -> None:
        result = _dict_to_basic(
            {"project_name": "A", "project_type": "B", "location": "C"}
        )
        assert result.project_name == "A"
        assert result.location == "C"
        assert result.scale == ""

    def test_dict_to_basic_empty(self) -> None:
        result = _dict_to_basic({})
        assert result.project_name == ""

    def test_dict_to_technical(self) -> None:
        result = _dict_to_technical({"geology": "岩石"})
        assert result.geology == "岩石"
        assert result.climate == ""

    def test_dict_to_participants(self) -> None:
        result = _dict_to_participants({"owner": "甲方"})
        assert result.owner == "甲方"
        assert result.contractor == ""

    def test_dict_to_constraints_with_risks(self) -> None:
        result = _dict_to_constraints({"risks": ["r1", "r2"], "timeline": "3月"})
        assert result.risks == ["r1", "r2"]
        assert result.timeline == "3月"

    def test_dict_to_constraints_invalid_risks_type(self) -> None:
        """risks 非列表时返回空列表。"""
        result = _dict_to_constraints({"risks": "不是列表"})
        assert result.risks == []

    def test_dict_to_basic_non_string_value(self) -> None:
        """非字符串值会被 str() 转换。"""
        result = _dict_to_basic({"project_name": 123, "project_type": True})
        assert result.project_name == "123"
        assert result.project_type == "True"

    def test_extract_json_pure(self) -> None:
        text = '{"basic": {"project_name": "test"}}'
        result = _extract_json_from_response(text)
        assert result["basic"]["project_name"] == "test"

    def test_extract_json_code_block(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_from_response(text)
        assert result["key"] == "value"

    def test_extract_json_mixed_text(self) -> None:
        text = '以下是提取结果：\n{"key": "value"}\n以上。'
        result = _extract_json_from_response(text)
        assert result["key"] == "value"

    def test_extract_json_invalid(self) -> None:
        with pytest.raises(ValueError, match="无法从 LLM 响应中提取合法 JSON"):
            _extract_json_from_response("这不是 JSON")


# ═══════════════════════════════════════════════════════════════
# TestParseJson — JSON 路径
# ═══════════════════════════════════════════════════════════════


class TestParseJson:
    """parse_json 测试。"""

    def test_full_input(self, parser: InputParser, full_input_dict: dict) -> None:
        result = parser.parse_json(full_input_dict)
        assert result.basic.project_name == "220kV 某某输电线路工程"
        assert result.basic.project_type == "输电线路"
        assert result.technical.geology == "丘陵地形，局部岩石"
        assert result.participants.owner == "南方电网广东公司"
        assert result.constraints.risks == ["台风季施工", "地质复杂"]

    def test_minimal_input(self, parser: InputParser, minimal_input_dict: dict) -> None:
        result = parser.parse_json(minimal_input_dict)
        assert result.basic.project_name == "测试工程"
        assert result.technical.geology == ""
        assert result.participants.owner == ""

    def test_empty_dict(self, parser: InputParser) -> None:
        """空字典返回默认值并触发校验警告。"""
        result = parser.parse_json({})
        assert result.basic.project_name == ""
        errors = result.validate()
        assert len(errors) == 2

    def test_extra_fields_ignored(self, parser: InputParser) -> None:
        """多余字段被忽略。"""
        data = {
            "basic": {
                "project_name": "工程",
                "project_type": "输电",
                "unknown_field": "忽略",
            },
            "unknown_section": {"foo": "bar"},
        }
        result = parser.parse_json(data)
        assert result.basic.project_name == "工程"

    def test_partial_sections(self, parser: InputParser) -> None:
        """只提供部分 section。"""
        data = {
            "basic": {"project_name": "工程", "project_type": "变电站"},
            "constraints": {"timeline": "3个月"},
        }
        result = parser.parse_json(data)
        assert result.constraints.timeline == "3个月"
        assert result.technical.geology == ""


# ═══════════════════════════════════════════════════════════════
# TestParseText — 自然语言路径
# ═══════════════════════════════════════════════════════════════


class TestParseText:
    """parse_text 测试（LLM Mock）。"""

    def test_normal_extraction(self, parser: InputParser) -> None:
        result = parser.parse_text("110kV 输电线路工程，位于深圳，全长 10km。")
        assert result.basic.project_name == "110kV 输电线路"
        assert result.basic.location == "深圳"
        assert result.constraints.risks == ["暴雨"]

    def test_empty_text(self, parser: InputParser) -> None:
        """空文本返回默认 StandardizedInput。"""
        result = parser.parse_text("")
        assert result.basic.project_name == ""

    def test_whitespace_only(self, parser: InputParser) -> None:
        """纯空白文本同空文本。"""
        result = parser.parse_text("   \n\t  ")
        assert result.basic.project_name == ""

    def test_llm_returns_invalid_json_then_retries(
        self, mock_llm_client: MagicMock
    ) -> None:
        """LLM 第一次返回非法 JSON，重试后成功。"""
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "这不是 JSON"

        good_response = MagicMock()
        good_response.choices = [MagicMock()]
        good_response.choices[0].message.content = json.dumps(
            {"basic": {"project_name": "重试成功", "project_type": "变电站"}}
        )

        mock_llm_client.chat.completions.create.side_effect = [
            bad_response,
            good_response,
        ]
        p = InputParser(llm_client=mock_llm_client)
        result = p.parse_text("一些文本")
        assert result.basic.project_name == "重试成功"

    def test_llm_all_retries_fail(self, mock_llm_client: MagicMock) -> None:
        """LLM 所有重试都失败，抛出异常。"""
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "不是 JSON"

        mock_llm_client.chat.completions.create.return_value = bad_response
        p = InputParser(llm_client=mock_llm_client)
        with pytest.raises(Exception):
            p.parse_text("一些文本")


# ═══════════════════════════════════════════════════════════════
# TestParsePdf — PDF 路径
# ═══════════════════════════════════════════════════════════════


class TestParsePdf:
    """parse_pdf 测试（OCR + LLM Mock）。"""

    def test_normal_flow(
        self,
        parser: InputParser,
        mock_ocr_client: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """正常 PDF 解析流程。"""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        result = parser.parse_pdf(str(pdf_file))
        mock_ocr_client.to_markdown.assert_called_once_with(str(pdf_file))
        assert result.basic.project_name == "110kV 输电线路"

    def test_file_not_exists(self, parser: InputParser) -> None:
        """PDF 文件不存在时抛异常。"""
        with pytest.raises(Exception):
            parser.parse_pdf("/nonexistent/path/test.pdf")

    def test_ocr_returns_empty(
        self, mock_llm_client: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """OCR 返回空结果时抛异常。"""
        mock_ocr = MagicMock()
        mock_ocr.to_markdown.return_value = ""
        p = InputParser(llm_client=mock_llm_client, ocr_client=mock_ocr)

        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with pytest.raises(Exception):
            p.parse_pdf(str(pdf_file))


# ═══════════════════════════════════════════════════════════════
# TestParseRouter — parse() 自动路由
# ═══════════════════════════════════════════════════════════════


class TestParseRouter:
    """parse() 路由逻辑测试。"""

    def test_route_dict(self, parser: InputParser, minimal_input_dict: dict) -> None:
        result = parser.parse(minimal_input_dict)
        assert result.basic.project_name == "测试工程"

    def test_route_pdf(
        self,
        parser: InputParser,
        mock_ocr_client: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        pdf_file = tmp_path / "route.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        parser.parse(str(pdf_file))
        mock_ocr_client.to_markdown.assert_called_once()

    def test_route_text(self, parser: InputParser) -> None:
        result = parser.parse("这是一段关于某工程的描述")
        assert isinstance(result, StandardizedInput)

    def test_route_pdf_case_insensitive(
        self,
        parser: InputParser,
        mock_ocr_client: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """PDF 后缀不区分大小写。"""
        pdf_file = tmp_path / "test.PDF"
        pdf_file.write_bytes(b"%PDF-1.4")

        parser.parse(str(pdf_file))
        mock_ocr_client.to_markdown.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# TestValidation — 字段校验
# ═══════════════════════════════════════════════════════════════


class TestValidation:
    """字段校验测试。"""

    def test_valid_full_input(self, parser: InputParser, full_input_dict: dict) -> None:
        result = parser.parse_json(full_input_dict)
        assert result.validate() == []

    def test_missing_required_returns_warnings(self, parser: InputParser) -> None:
        """缺少必填字段时 parse_json 仍返回结果（不阻塞）。"""
        result = parser.parse_json({"basic": {"project_name": "工程"}})
        assert isinstance(result, StandardizedInput)
        errors = result.validate()
        assert len(errors) == 1
        assert "project_type" in errors[0]
