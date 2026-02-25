"""S12 章节 Agent 单元测试。

覆盖 ChapterContext、BaseChapterAgent、Jinja2 模板渲染、
9 个子类、post_process 后处理。
LLM 调用全部 Mock，不依赖真实 LLM。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.base import (
    CHINESE_NUMBERS,
    STANDARD_TITLES,
    BaseChapterAgent,
    ChapterContext,
    _normalize_chapter_title,
    _replace_project_name_placeholder,
)
from agents.chapter1_basis import Chapter1Agent
from agents.chapter2_overview import Chapter2Agent
from agents.chapter3_organization import Chapter3Agent
from agents.chapter4_schedule import Chapter4Agent
from agents.chapter5_preparation import Chapter5Agent
from agents.chapter6_methods import Chapter6Agent
from agents.chapter7_quality import Chapter7Agent
from agents.chapter8_safety import Chapter8Agent
from agents.chapter9_emergency import Chapter9Agent
from input_parser.models import (
    BasicInfo,
    ConstraintInfo,
    ParticipantInfo,
    StandardizedInput,
    TechnicalInfo,
)
from knowledge_retriever.models import RetrievalItem, RetrievalResponse


# ═══════════════════════════════════════════════════════════════
# Fixture
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_input() -> StandardizedInput:
    """示例 StandardizedInput。"""
    return StandardizedInput(
        basic=BasicInfo(
            project_name="220kV 凤凰变电站新建工程",
            project_type="变电站土建",
            location="广东省广州市天河区",
            scale="220kV 变电站 1 座",
        ),
        technical=TechnicalInfo(
            geology="场地为第四系冲积层，地基承载力 150kPa",
            climate="亚热带季风气候，年均降雨量 1800mm",
            special_requirements="场地紧邻居民区，需控制噪音和扬尘",
        ),
        participants=ParticipantInfo(
            owner="南方电网广州供电局",
            contractor="广东省送变电工程有限公司",
            supervisor="广东省电力设计研究院",
            designer="中国能源建设集团广东省电力设计研究院",
        ),
        constraints=ConstraintInfo(
            timeline="2026-03 至 2026-12，总工期 10 个月",
            budget="3500 万元",
            risks=["雨季施工风险", "地下管线干扰"],
        ),
    )


@pytest.fixture
def sample_retrieval() -> RetrievalResponse:
    """示例 RetrievalResponse（含 regulations + cases）。"""
    return RetrievalResponse(
        items=[
            RetrievalItem(
                content="GB 50300-2013 建筑工程施工质量验收统一标准",
                source="kg_rule",
                priority=1,
                score=1.0,
            ),
            RetrievalItem(
                content="混凝土浇筑应分层进行，每层厚度不超过 300mm",
                source="vector",
                priority=2,
                score=0.92,
            ),
        ],
        regulations=[
            RetrievalItem(
                content="GB 50300-2013 建筑工程施工质量验收统一标准",
                source="kg_rule",
                priority=1,
                score=1.0,
            ),
        ],
        cases=[
            RetrievalItem(
                content="混凝土浇筑应分层进行，每层厚度不超过 300mm",
                source="vector",
                priority=2,
                score=0.92,
            ),
        ],
    )


@pytest.fixture
def sample_context(
    sample_input: StandardizedInput,
    sample_retrieval: RetrievalResponse,
) -> ChapterContext:
    """完整的 ChapterContext。"""
    return ChapterContext(
        standardized_input=sample_input,
        macro_view=["第一章摘要：本工程依据 GB 50300 等标准编制。"],
        key_details={"voltage_level": "220kV", "foundation_type": "桩基础"},
        retrieval=sample_retrieval,
        chapter_number=2,
        chapter_title="工程概况",
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock OpenAI 客户端，返回预设章节内容。"""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "## 一、编制依据\n\n"
        "### 1.1 法律法规\n\n"
        "《中华人民共和国建筑法》\n\n"
        "### 1.2 行业标准\n\n"
        "GB 50300-2013 建筑工程施工质量验收统一标准\n"
    )
    mock.chat.completions.create.return_value = mock_response
    return mock


def _make_context_for_chapter(
    sample_input: StandardizedInput,
    chapter_number: int,
    chapter_title: str,
) -> ChapterContext:
    """为指定章节构建最小 ChapterContext。"""
    return ChapterContext(
        standardized_input=sample_input,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
    )


# ═══════════════════════════════════════════════════════════════
# TestChapterContext — 数据结构测试
# ═══════════════════════════════════════════════════════════════


class TestChapterContext:
    """ChapterContext 数据结构测试。"""

    def test_default_values(self, sample_input: StandardizedInput) -> None:
        """默认值初始化。"""
        ctx = ChapterContext(standardized_input=sample_input)
        assert ctx.macro_view == []
        assert ctx.key_details == {}
        assert ctx.retrieval is None
        assert ctx.chapter_number == 0
        assert ctx.chapter_title == ""

    def test_full_initialization(self, sample_context: ChapterContext) -> None:
        """完整初始化。"""
        assert sample_context.chapter_number == 2
        assert sample_context.chapter_title == "工程概况"
        assert len(sample_context.macro_view) == 1
        assert "voltage_level" in sample_context.key_details
        assert sample_context.retrieval is not None

    def test_macro_view_is_independent_list(
        self, sample_input: StandardizedInput
    ) -> None:
        """macro_view 默认列表不会跨实例共享。"""
        ctx1 = ChapterContext(standardized_input=sample_input)
        ctx2 = ChapterContext(standardized_input=sample_input)
        ctx1.macro_view.append("test")
        assert ctx2.macro_view == []


# ═══════════════════════════════════════════════════════════════
# TestBaseChapterAgent — 基类测试
# ═══════════════════════════════════════════════════════════════


class TestBaseChapterAgent:
    """BaseChapterAgent 基类测试。"""

    def test_init_defaults(self) -> None:
        """默认初始化。"""
        agent = Chapter1Agent()
        assert agent._llm_client is None
        assert agent._max_tokens == Chapter1Agent.DEFAULT_MAX_TOKENS

    def test_init_custom_client(self, mock_llm_client: MagicMock) -> None:
        """自定义 LLM 客户端。"""
        agent = Chapter1Agent(llm_client=mock_llm_client, max_tokens=1024)
        assert agent._llm_client is mock_llm_client
        assert agent._max_tokens == 1024

    def test_render_prompt_basic(self, sample_input: StandardizedInput) -> None:
        """模板渲染 — 最小上下文。"""
        agent = Chapter1Agent()
        ctx = _make_context_for_chapter(sample_input, 1, "编制依据")
        prompt = agent._render_prompt(ctx)
        assert "编制依据" in prompt
        assert "220kV 凤凰变电站新建工程" in prompt

    def test_render_prompt_with_retrieval(self, sample_context: ChapterContext) -> None:
        """模板渲染 — 包含检索结果。"""
        agent = Chapter2Agent()
        prompt = agent._render_prompt(sample_context)
        assert "GB 50300-2013" in prompt
        assert "混凝土浇筑" in prompt

    def test_render_prompt_with_macro_view(
        self, sample_context: ChapterContext
    ) -> None:
        """模板渲染 — 包含前序章节摘要。"""
        agent = Chapter2Agent()
        prompt = agent._render_prompt(sample_context)
        assert "第一章摘要" in prompt

    def test_render_prompt_empty_retrieval(
        self, sample_input: StandardizedInput
    ) -> None:
        """模板渲染 — retrieval 为 None 不报错。"""
        agent = Chapter1Agent()
        ctx = ChapterContext(
            standardized_input=sample_input,
            chapter_number=1,
            chapter_title="编制依据",
            retrieval=None,
        )
        prompt = agent._render_prompt(ctx)
        assert "编制依据" in prompt
        # 无规范/案例块（用 Markdown 标题标识，区分 role.txt 中的描述文字）
        assert "## 强制规范" not in prompt
        assert "## 参考案例" not in prompt

    def test_call_llm(self, mock_llm_client: MagicMock) -> None:
        """LLM 调用 — 正常返回。"""
        agent = Chapter1Agent(llm_client=mock_llm_client)
        result = agent._call_llm("测试 prompt")
        assert "编制依据" in result
        mock_llm_client.chat.completions.create.assert_called_once()

    def test_call_llm_empty_response(self) -> None:
        """LLM 调用 — 返回空内容，应有 WARNING 日志。"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_client.chat.completions.create.return_value = mock_response

        agent = Chapter1Agent(llm_client=mock_client)
        result = agent._call_llm("测试 prompt")
        assert result == ""

    def test_generate_full_pipeline(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        """generate 完整管道 — render → call → post_process。"""
        agent = Chapter1Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 1, "编制依据")
        result = agent.generate(ctx)
        assert isinstance(result, str)
        assert len(result) > 0
        mock_llm_client.chat.completions.create.assert_called_once()

    def test_lazy_load_llm_client(self, sample_input: StandardizedInput) -> None:
        """懒加载 LLM 客户端 — 验证 _get_llm_client 创建实例。"""
        agent = Chapter1Agent()
        assert agent._llm_client is None
        with patch("agents.base.OpenAI") as mock_openai:
            client = agent._get_llm_client()
            mock_openai.assert_called_once()
            assert agent._llm_client is client


# ═══════════════════════════════════════════════════════════════
# TestJinja2Templates — 模板渲染测试
# ═══════════════════════════════════════════════════════════════


class TestJinja2Templates:
    """Jinja2 模板渲染测试（不调用 LLM）。"""

    ALL_AGENTS: list[type[BaseChapterAgent]] = [
        Chapter1Agent,
        Chapter2Agent,
        Chapter3Agent,
        Chapter4Agent,
        Chapter5Agent,
        Chapter6Agent,
        Chapter7Agent,
        Chapter8Agent,
        Chapter9Agent,
    ]

    def test_all_templates_render(self, sample_input: StandardizedInput) -> None:
        """所有 9 个模板都能正常渲染。"""
        for agent_cls in self.ALL_AGENTS:
            agent = agent_cls()
            ctx = _make_context_for_chapter(
                sample_input,
                agent.CHAPTER_NUMBER,
                agent.CHAPTER_TITLE,
            )
            prompt = agent._render_prompt(ctx)
            assert len(prompt) > 100, f"{agent_cls.__name__} 模板渲染内容过短"

    def test_templates_contain_role(self, sample_input: StandardizedInput) -> None:
        """所有模板包含角色定义。"""
        for agent_cls in self.ALL_AGENTS:
            agent = agent_cls()
            ctx = _make_context_for_chapter(
                sample_input,
                agent.CHAPTER_NUMBER,
                agent.CHAPTER_TITLE,
            )
            prompt = agent._render_prompt(ctx)
            assert "施工方案编制专家" in prompt, (
                f"{agent_cls.__name__} 模板缺少角色定义"
            )

    def test_templates_contain_output_format(
        self, sample_input: StandardizedInput
    ) -> None:
        """所有模板包含输出格式要求。"""
        for agent_cls in self.ALL_AGENTS:
            agent = agent_cls()
            ctx = _make_context_for_chapter(
                sample_input,
                agent.CHAPTER_NUMBER,
                agent.CHAPTER_TITLE,
            )
            prompt = agent._render_prompt(ctx)
            assert "输出要求" in prompt, f"{agent_cls.__name__} 模板缺少输出格式"

    def test_templates_contain_engineering_info(
        self, sample_input: StandardizedInput
    ) -> None:
        """所有模板包含工程信息。"""
        for agent_cls in self.ALL_AGENTS:
            agent = agent_cls()
            ctx = _make_context_for_chapter(
                sample_input,
                agent.CHAPTER_NUMBER,
                agent.CHAPTER_TITLE,
            )
            prompt = agent._render_prompt(ctx)
            assert "220kV" in prompt, f"{agent_cls.__name__} 模板缺少工程信息"

    def test_template_with_retrieval(self, sample_context: ChapterContext) -> None:
        """模板渲染包含检索结果（regulations + cases）。"""
        agent = Chapter2Agent()
        prompt = agent._render_prompt(sample_context)
        assert "强制规范" in prompt
        assert "参考案例" in prompt

    def test_template_without_retrieval(self, sample_input: StandardizedInput) -> None:
        """无检索结果时不输出规范/案例块。"""
        agent = Chapter1Agent()
        ctx = ChapterContext(
            standardized_input=sample_input,
            chapter_number=1,
            chapter_title="编制依据",
        )
        prompt = agent._render_prompt(ctx)
        assert "## 强制规范" not in prompt
        assert "## 参考案例" not in prompt


# ═══════════════════════════════════════════════════════════════
# TestChapterAgents — 9 个子类测试
# ═══════════════════════════════════════════════════════════════


class TestChapter1Agent:
    """Chapter1Agent 编制依据。"""

    def test_class_variables(self) -> None:
        """类变量正确。"""
        assert Chapter1Agent.CHAPTER_NUMBER == 1
        assert Chapter1Agent.CHAPTER_TITLE == "编制依据"
        assert Chapter1Agent.TEMPLATE_NAME == "chapter1.j2"
        assert Chapter1Agent.DEFAULT_MAX_TOKENS == 2048

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        """正常生成流程。"""
        agent = Chapter1Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 1, "编制依据")
        result = agent.generate(ctx)
        assert isinstance(result, str)
        assert len(result) > 0


class TestChapter2Agent:
    """Chapter2Agent 工程概况。"""

    def test_class_variables(self) -> None:
        assert Chapter2Agent.CHAPTER_NUMBER == 2
        assert Chapter2Agent.CHAPTER_TITLE == "工程概况"
        assert Chapter2Agent.TEMPLATE_NAME == "chapter2.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 二、工程概况\n\n### 2.1 工程简介\n"
        agent = Chapter2Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 2, "工程概况")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter3Agent:
    """Chapter3Agent 施工组织机构及职责。"""

    def test_class_variables(self) -> None:
        assert Chapter3Agent.CHAPTER_NUMBER == 3
        assert Chapter3Agent.CHAPTER_TITLE == "施工组织机构及职责"
        assert Chapter3Agent.TEMPLATE_NAME == "chapter3.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 三、施工组织机构及职责\n\n### 3.1 组织架构\n"
        agent = Chapter3Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 3, "施工组织机构及职责")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter4Agent:
    """Chapter4Agent 施工安排与进度计划。"""

    def test_class_variables(self) -> None:
        assert Chapter4Agent.CHAPTER_NUMBER == 4
        assert Chapter4Agent.CHAPTER_TITLE == "施工安排与进度计划"
        assert Chapter4Agent.TEMPLATE_NAME == "chapter4.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 四、施工安排与进度计划\n\n### 4.1 施工总体部署\n"
        agent = Chapter4Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 4, "施工安排与进度计划")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter5Agent:
    """Chapter5Agent 施工准备。"""

    def test_class_variables(self) -> None:
        assert Chapter5Agent.CHAPTER_NUMBER == 5
        assert Chapter5Agent.CHAPTER_TITLE == "施工准备"
        assert Chapter5Agent.TEMPLATE_NAME == "chapter5.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 五、施工准备\n\n### 5.1 技术准备\n"
        agent = Chapter5Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 5, "施工准备")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter6Agent:
    """Chapter6Agent 施工方法及工艺要求。"""

    def test_class_variables(self) -> None:
        assert Chapter6Agent.CHAPTER_NUMBER == 6
        assert Chapter6Agent.CHAPTER_TITLE == "施工方法及工艺要求"
        assert Chapter6Agent.TEMPLATE_NAME == "chapter6.j2"
        assert Chapter6Agent.DEFAULT_MAX_TOKENS == 6144

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 六、施工方法及工艺要求\n\n### 6.1 施工工艺流程\n"
        agent = Chapter6Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 6, "施工方法及工艺要求")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter7Agent:
    """Chapter7Agent 质量管理与控制措施。"""

    def test_class_variables(self) -> None:
        assert Chapter7Agent.CHAPTER_NUMBER == 7
        assert Chapter7Agent.CHAPTER_TITLE == "质量管理与控制措施"
        assert Chapter7Agent.TEMPLATE_NAME == "chapter7.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 七、质量管理与控制措施\n\n### 7.1 质量管理组织\n"
        agent = Chapter7Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 7, "质量管理与控制措施")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter8Agent:
    """Chapter8Agent 安全文明施工管理。"""

    def test_class_variables(self) -> None:
        assert Chapter8Agent.CHAPTER_NUMBER == 8
        assert Chapter8Agent.CHAPTER_TITLE == "安全文明施工管理"
        assert Chapter8Agent.TEMPLATE_NAME == "chapter8.j2"
        assert Chapter8Agent.DEFAULT_MAX_TOKENS == 5120

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 八、安全文明施工管理\n\n### 8.1 安全管理组织\n"
        agent = Chapter8Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 8, "安全文明施工管理")
        result = agent.generate(ctx)
        assert isinstance(result, str)


class TestChapter9Agent:
    """Chapter9Agent 应急预案与处置措施。"""

    def test_class_variables(self) -> None:
        assert Chapter9Agent.CHAPTER_NUMBER == 9
        assert Chapter9Agent.CHAPTER_TITLE == "应急预案与处置措施"
        assert Chapter9Agent.TEMPLATE_NAME == "chapter9.j2"

    def test_generate(
        self,
        mock_llm_client: MagicMock,
        sample_input: StandardizedInput,
    ) -> None:
        mock_llm_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "## 九、应急预案与处置措施\n\n### 9.1 应急组织\n"
        agent = Chapter9Agent(llm_client=mock_llm_client)
        ctx = _make_context_for_chapter(sample_input, 9, "应急预案与处置措施")
        result = agent.generate(ctx)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# TestPostProcess — 后处理规则测试
# ═══════════════════════════════════════════════════════════════


class TestPostProcess:
    """post_process 规则测试。"""

    def test_normalize_title_from_numbered_format(self) -> None:
        """'第一章 编制依据' → '一、编制依据'。"""
        content = "## 第一章 编制依据\n\n内容"
        result = _normalize_chapter_title(content, 1)
        assert "一、编制依据" in result

    def test_normalize_title_from_digit_format(self) -> None:
        """'1. 编制依据' → '一、编制依据'。"""
        content = "1. 编制依据\n\n内容"
        result = _normalize_chapter_title(content, 1)
        assert "一、编制依据" in result

    def test_normalize_title_already_correct(self) -> None:
        """已经是标准格式不改变。"""
        content = "## 一、编制依据\n\n内容"
        result = _normalize_chapter_title(content, 1)
        assert "一、编制依据" in result

    def test_normalize_invalid_chapter_number(self) -> None:
        """无效章节号不处理。"""
        content = "some content"
        result = _normalize_chapter_title(content, 99)
        assert result == content

    def test_replace_placeholder_double_braces(self) -> None:
        """'{{工程名称}}' 替换。"""
        content = "本工程名称为{{工程名称}}，位于广州。"
        result = _replace_project_name_placeholder(content, "测试工程")
        assert result == "本工程名称为测试工程，位于广州。"

    def test_replace_placeholder_brackets(self) -> None:
        """'【工程名称】' 替换。"""
        content = "本工程为【工程名称】配电工程。"
        result = _replace_project_name_placeholder(content, "测试工程")
        assert result == "本工程为测试工程配电工程。"

    def test_replace_placeholder_single_braces(self) -> None:
        """'{工程名称}' 替换。"""
        content = "项目名称：{工程名称}"
        result = _replace_project_name_placeholder(content, "测试工程")
        assert result == "项目名称：测试工程"

    def test_replace_no_placeholder(self) -> None:
        """无占位符时不改变。"""
        content = "这里没有任何占位符。"
        result = _replace_project_name_placeholder(content, "测试工程")
        assert result == content

    def test_post_process_integration(self, sample_input: StandardizedInput) -> None:
        """post_process 集成测试 — 标题 + 名称替换。"""
        agent = Chapter1Agent()
        ctx = _make_context_for_chapter(sample_input, 1, "编制依据")
        content = "## 第一章 编制依据\n\n{{工程名称}}施工方案编制依据如下："
        result = agent.post_process(content, ctx)
        assert "一、编制依据" in result
        assert "220kV 凤凰变电站新建工程" in result
        assert "{{工程名称}}" not in result

    def test_post_process_empty_project_name(self) -> None:
        """工程名称为空时不替换。"""
        agent = Chapter1Agent()
        ctx = ChapterContext(
            standardized_input=StandardizedInput(
                basic=BasicInfo(project_name="", project_type="输电线路")
            ),
            chapter_number=1,
            chapter_title="编制依据",
        )
        content = "{{工程名称}}施工方案"
        result = agent.post_process(content, ctx)
        assert "{{工程名称}}" in result


# ═══════════════════════════════════════════════════════════════
# TestConstants — 常量测试
# ═══════════════════════════════════════════════════════════════


class TestConstants:
    """常量正确性验证。"""

    def test_standard_titles_complete(self) -> None:
        """9 个标准标题完整。"""
        assert len(STANDARD_TITLES) == 9
        for i in range(1, 10):
            assert i in STANDARD_TITLES

    def test_chinese_numbers_length(self) -> None:
        """中文数字元组长度。"""
        assert len(CHINESE_NUMBERS) == 10

    def test_all_agents_have_correct_numbers(self) -> None:
        """所有 Agent 子类的 CHAPTER_NUMBER 正确。"""
        agents = [
            Chapter1Agent,
            Chapter2Agent,
            Chapter3Agent,
            Chapter4Agent,
            Chapter5Agent,
            Chapter6Agent,
            Chapter7Agent,
            Chapter8Agent,
            Chapter9Agent,
        ]
        for i, agent_cls in enumerate(agents, start=1):
            assert agent_cls.CHAPTER_NUMBER == i, (
                f"{agent_cls.__name__}.CHAPTER_NUMBER should be {i}"
            )

    def test_all_agents_have_standard_titles(self) -> None:
        """所有 Agent 子类的 CHAPTER_TITLE 与 STANDARD_TITLES 一致。"""
        agents = [
            Chapter1Agent,
            Chapter2Agent,
            Chapter3Agent,
            Chapter4Agent,
            Chapter5Agent,
            Chapter6Agent,
            Chapter7Agent,
            Chapter8Agent,
            Chapter9Agent,
        ]
        for agent_cls in agents:
            expected = STANDARD_TITLES[agent_cls.CHAPTER_NUMBER]
            assert agent_cls.CHAPTER_TITLE == expected, (
                f"{agent_cls.__name__}.CHAPTER_TITLE mismatch"
            )

    def test_all_agents_have_template_names(self) -> None:
        """所有 Agent 子类都有非空 TEMPLATE_NAME。"""
        agents = [
            Chapter1Agent,
            Chapter2Agent,
            Chapter3Agent,
            Chapter4Agent,
            Chapter5Agent,
            Chapter6Agent,
            Chapter7Agent,
            Chapter8Agent,
            Chapter9Agent,
        ]
        for agent_cls in agents:
            assert agent_cls.TEMPLATE_NAME, (
                f"{agent_cls.__name__}.TEMPLATE_NAME is empty"
            )
            assert agent_cls.TEMPLATE_NAME.endswith(".j2")
