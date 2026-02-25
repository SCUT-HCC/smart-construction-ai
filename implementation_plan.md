# S12: 9 个章节 Agent 实施计划

## 摘要

创建 `agents/` 和 `prompts/` 两个模块，实现 `BaseChapterAgent` 基类 + `ChapterContext` 数据结构 + 9 个章节 Agent（Chapter1Agent ~ Chapter9Agent）。每个 Agent 使用 Jinja2 模板渲染 Prompt，调用 LLM 生成章节内容，并执行命名规范化后处理。

---

## 审查点

| # | 问题 | 建议 |
|---|------|------|
| 1 | **LLM 调用方式** — 当前项目统一用 `openai.OpenAI` + `config.LLM_CONFIG` 调用 LLM（见 `input_parser/parser.py`、`cleaning.py`）。是否沿用？ | 沿用。`BaseChapterAgent.__init__` 接受可选 `llm_client: OpenAI \| None`，不传则从 `config.LLM_CONFIG` 懒加载 |
| 2 | **Jinja2 依赖** — 当前 `requirements.txt` 无 Jinja2。需要新增 | 新增 `Jinja2>=3.1.0` 到 `requirements.txt` 并 `pip install` |
| 3 | **KnowledgeRetriever 集成** — Agent 内部是否直接调用检索？ | 不调用。`ChapterContext.retrieval` 由上游（将来的 `GenerationCoordinator`）构建好传入。Agent 只消费上下文 |
| 4 | **post_process 范围** — 是做 LLM 后处理还是规则后处理？ | MVP 阶段仅做规则后处理：(1) 章节标题命名规范化 (2) 工程名称一致性替换。不调用 LLM |
| 5 | **max_tokens 配置** — 不同章节内容长度差异大（第六章可能 5000+ 字，第一章 ~1000 字）| 每个 Agent 可配置 `max_tokens`，默认值按章节类型调整。`BaseChapterAgent.__init__` 接受 `max_tokens` 参数 |
| 6 | **模板中章节结构规范** — `standard_50502.md` 的章节结构如何注入模板？ | 每个 Agent 的 `.j2` 模板中内嵌该章的子章节结构（从 `standard_50502.md` 提取）。静态内容，不需运行时读取文件 |

---

## 拟议变更

### 新增文件

| 文件 | 标注 | 说明 |
|------|------|------|
| `agents/__init__.py` | [NEW] | 模块 docstring + 导出 9 个 Agent 类 |
| `agents/base.py` | [NEW] | `BaseChapterAgent` 基类 + `ChapterContext` 数据结构 (~150 行) |
| `agents/chapter1_basis.py` | [NEW] | Chapter1Agent: 编制依据 (~60 行) |
| `agents/chapter2_overview.py` | [NEW] | Chapter2Agent: 工程概况 (~60 行) |
| `agents/chapter3_organization.py` | [NEW] | Chapter3Agent: 施工组织机构及职责 (~60 行) |
| `agents/chapter4_schedule.py` | [NEW] | Chapter4Agent: 施工安排与进度计划 (~60 行) |
| `agents/chapter5_preparation.py` | [NEW] | Chapter5Agent: 施工准备 (~60 行) |
| `agents/chapter6_methods.py` | [NEW] | Chapter6Agent: 施工方法及工艺要求 (~60 行) |
| `agents/chapter7_quality.py` | [NEW] | Chapter7Agent: 质量管理与控制措施 (~60 行) |
| `agents/chapter8_safety.py` | [NEW] | Chapter8Agent: 安全文明施工管理 (~60 行) |
| `agents/chapter9_emergency.py` | [NEW] | Chapter9Agent: 应急预案与处置措施 (~60 行) |
| `prompts/__init__.py` | [NEW] | 空模块 |
| `prompts/static/role.txt` | [NEW] | 角色定义（共享） |
| `prompts/static/output_format.txt` | [NEW] | 输出格式要求（共享） |
| `prompts/agents/chapter1.j2` | [NEW] | 第一章 Jinja2 模板 |
| `prompts/agents/chapter2.j2` | [NEW] | 第二章 Jinja2 模板 |
| `prompts/agents/chapter3.j2` | [NEW] | 第三章 Jinja2 模板 |
| `prompts/agents/chapter4.j2` | [NEW] | 第四章 Jinja2 模板 |
| `prompts/agents/chapter5.j2` | [NEW] | 第五章 Jinja2 模板 |
| `prompts/agents/chapter6.j2` | [NEW] | 第六章 Jinja2 模板 |
| `prompts/agents/chapter7.j2` | [NEW] | 第七章 Jinja2 模板 |
| `prompts/agents/chapter8.j2` | [NEW] | 第八章 Jinja2 模板 |
| `prompts/agents/chapter9.j2` | [NEW] | 第九章 Jinja2 模板 |
| `tests/test_agents.py` | [NEW] | 章节 Agent 全量测试 (~500 行) |

### 修改文件

| 文件 | 标注 | 说明 |
|------|------|------|
| `requirements.txt` | [MODIFY] | 新增 `Jinja2>=3.1.0` |

### 不修改的文件

`input_parser/`、`knowledge_retriever/`、`config.py`、`cleaning.py` 等现有模块不做任何改动。

---

## 详细设计

### 1. ChapterContext — 上下文数据结构

```python
@dataclass
class ChapterContext:
    """章节生成上下文。

    由上游 GenerationCoordinator 构建，传递给 Agent.generate()。

    Attributes:
        standardized_input: 标准化工程信息
        macro_view: 前序各章的 150 字摘要列表
        key_details: 当前章节依赖的具体参数 dict
        retrieval: 知识检索结果（RetrievalResponse）
        chapter_number: 当前章节编号 (1~9)
        chapter_title: 当前章节标准标题
    """
    standardized_input: StandardizedInput
    macro_view: list[str] = field(default_factory=list)
    key_details: dict[str, Any] = field(default_factory=dict)
    retrieval: RetrievalResponse | None = None
    chapter_number: int = 0
    chapter_title: str = ""
```

### 2. BaseChapterAgent — 基类

```python
class BaseChapterAgent:
    """章节 Agent 基类。

    子类只需设置：
    - CHAPTER_NUMBER: int          # 章节编号
    - CHAPTER_TITLE: str           # 标准标题
    - TEMPLATE_NAME: str           # Jinja2 模板文件名
    - DEFAULT_MAX_TOKENS: int      # 默认 max_tokens
    """
    CHAPTER_NUMBER: int = 0
    CHAPTER_TITLE: str = ""
    TEMPLATE_NAME: str = ""
    DEFAULT_MAX_TOKENS: int = 4096

    def __init__(
        self,
        llm_client: OpenAI | None = None,
        max_tokens: int | None = None,
    ) -> None: ...

    def generate(self, context: ChapterContext) -> str:
        """基于上下文生成章节内容。

        流程：
        1. 渲染 Jinja2 模板 → prompt
        2. 调用 LLM → raw_content
        3. post_process → 规范化内容
        """

    def post_process(self, content: str, context: ChapterContext) -> str:
        """后处理：命名规范化 + 工程名称一致性替换。"""

    def _render_prompt(self, context: ChapterContext) -> str:
        """渲染 Jinja2 模板为完整 Prompt。"""

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 生成内容。"""
```

**关键实现细节：**

| 方法 | 核心逻辑 |
|------|---------|
| `_render_prompt` | 加载 `prompts/agents/{TEMPLATE_NAME}`，注入 `context` 各字段（standardized_input.to_dict()、macro_view、key_details、retrieval 的 regulations/cases）|
| `_call_llm` | 组装 system（role.txt）+ user（渲染后 prompt），调用 `client.chat.completions.create()`，提取 `choices[0].message.content` |
| `post_process` | (1) 正则修正章节标题格式 (2) 将章节标题替换为 `naming_conventions.md` 中的标准名称 (3) 用 `context.standardized_input.basic.project_name` 替换占位符 |
| `generate` | `_render_prompt → _call_llm → post_process`，串行管道 |

**Jinja2 模板加载策略：**

```python
# BaseChapterAgent 类内部
_TEMPLATE_DIR = Path(__file__).parent.parent / "prompts" / "agents"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=StrictUndefined,  # 缺变量立即报错
)
```

### 3. 9 个章节 Agent — 子类

每个子类只需覆盖类变量，无额外逻辑：

```python
class Chapter1Agent(BaseChapterAgent):
    """第一章: 编制依据。"""
    CHAPTER_NUMBER = 1
    CHAPTER_TITLE = "编制依据"
    TEMPLATE_NAME = "chapter1.j2"
    DEFAULT_MAX_TOKENS = 2048  # 编制依据内容较短
```

如有章节需要特殊 post_process 逻辑（如第六章的工艺流程格式化），可覆盖 `post_process` 方法。MVP 阶段暂不覆盖。

### 4. Jinja2 模板结构

每个 `.j2` 模板统一采用以下结构：

```jinja2
{# ===== 静态：角色定义 ===== #}
{% include "static/role.txt" %}

{# ===== 静态：当前章节结构规范 ===== #}
## 当前章节：{{ chapter_title }}

你需要生成以下子章节：
{{ section_spec }}

{# ===== 动态：工程信息 ===== #}
## 工程信息
{{ standardized_input | tojson(indent=2) }}

{# ===== 动态：知识检索结果 ===== #}
{% if regulations %}
## 强制规范
{% for reg in regulations %}
- {{ reg.content }}
{% endfor %}
{% endif %}

{% if cases %}
## 参考案例
{% for case in cases %}
### 案例 {{ loop.index }}
{{ case.content }}
{% endfor %}
{% endif %}

{# ===== 动态：前序章节摘要 ===== #}
{% if macro_view %}
## 前序章节摘要
{% for summary in macro_view %}
{{ summary }}
{% endfor %}
{% endif %}

{# ===== 静态：输出格式 + 生成指令 ===== #}
{% include "static/output_format.txt" %}
```

**各章的 `section_spec` 差异**（内嵌于各自模板的静态块中）：

| 章节 | 子章节 | 内容来源重点 |
|------|--------|-------------|
| Ch1 编制依据 | 1.1 法律法规 / 1.2 行业标准 / 1.3 设计文件 / 1.4 合同约定 | 知识库规范 + 用户输入 |
| Ch2 工程概况 | 2.1 工程简介 / 2.2 工程规模 / 2.3 地质地貌 / 2.4 参建单位 | 主要靠用户输入 |
| Ch3 施工组织 | 3.1 组织架构 / 3.2 管理人员职责 / 3.3 质安人员配置 | 模板 + 工程规模 |
| Ch4 施工安排 | 4.1 总体部署 / 4.2 施工顺序 / 4.3 进度计划 / 4.4 关键节点 | 案例 + 用户工期 |
| Ch5 施工准备 | 5.1 技术准备 / 5.2 材料准备 / 5.3 设备配置 / 5.4 劳动力 / 5.5 现场准备 | 模板 + 案例 |
| Ch6 施工方法 | 6.1 工艺流程 / 6.2 主要方法 / 6.3 分项技术 / 6.4 技术措施 / 6.5 验收标准 | 案例（最难模板化） |
| Ch7 质量管理 | 7.1 质量组织 / 7.2 保证措施 / 7.3 检验标准 / 7.4 工艺要求 / 7.5 关键工序控制 | 规范 + 案例 |
| Ch8 安全管理 | 8.1 安全组织 / 8.2 安全措施 / 8.3 危险点防范 / 8.4 危险源分析 / 8.5 文明施工 / 8.6 环保措施 | KG推理 + 案例 |
| Ch9 应急预案 | 9.1 应急组织 / 9.2 响应程序 / 9.3 处置措施 / 9.4 物资准备 / 9.5 演练计划 | 模板（高度模板化） |

### 5. 静态 Prompt 文件

**`prompts/static/role.txt`**（~10行）：

```
你是南方电网施工方案编制专家。你将根据提供的工程信息、规范要求和参考案例，
编写施工方案的指定章节。

要求：
- 内容必须专业、准确、符合行业规范
- 引用标准时必须包含完整编号和年份
- 工程名称必须与输入信息一致
- 使用中文编写
```

**`prompts/static/output_format.txt`**（~15行）：

```
## 输出要求

1. 使用 Markdown 格式输出
2. 章节标题使用中文数字编号（如"一、""二、"）
3. 子章节使用 X.Y 格式编号
4. 不要输出与当前章节无关的内容
5. 不要输出"好的""我来为你"等非正文内容
6. 直接输出章节正文内容
```

### 6. post_process 规则

```python
# BaseChapterAgent.post_process() 内部逻辑

# 1. 标题规范化 — 按 naming_conventions.md 的标准名称
STANDARD_TITLES = {
    1: "编制依据",
    2: "工程概况",
    3: "施工组织机构及职责",
    4: "施工安排与进度计划",
    5: "施工准备",
    6: "施工方法及工艺要求",
    7: "质量管理与控制措施",
    8: "安全文明施工管理",
    9: "应急预案与处置措施",
}

CHINESE_NUMBERS = "一二三四五六七八九十"

# 2. 正则替换非标准标题格式
#    "第X章 XXX" → "X、标准标题"
#    "1. XXX" → "一、标准标题"

# 3. 工程名称一致性
#    替换 {{工程名称}} / 占位符 → 实际工程名称
```

---

## 目录结构

```
agents/
├── __init__.py                 # 模块导出 (~20 行)
├── base.py                     # BaseChapterAgent + ChapterContext (~150 行)
├── chapter1_basis.py           # Chapter1Agent (~30 行)
├── chapter2_overview.py        # Chapter2Agent (~30 行)
├── chapter3_organization.py    # Chapter3Agent (~30 行)
├── chapter4_schedule.py        # Chapter4Agent (~30 行)
├── chapter5_preparation.py     # Chapter5Agent (~30 行)
├── chapter6_methods.py         # Chapter6Agent (~30 行)
├── chapter7_quality.py         # Chapter7Agent (~30 行)
├── chapter8_safety.py          # Chapter8Agent (~30 行)
└── chapter9_emergency.py       # Chapter9Agent (~30 行)

prompts/
├── __init__.py                 # 空
├── static/
│   ├── role.txt                # 角色定义 (~10 行)
│   └── output_format.txt       # 输出格式要求 (~15 行)
└── agents/
    ├── chapter1.j2             # 第一章模板
    ├── chapter2.j2             # ...
    ├── chapter3.j2
    ├── chapter4.j2
    ├── chapter5.j2
    ├── chapter6.j2
    ├── chapter7.j2
    ├── chapter8.j2
    └── chapter9.j2

tests/
└── test_agents.py              # 全量测试 (~500 行)
```

---

## 测试设计

```python
# tests/test_agents.py 测试类组织

# ═══════════════════════════════════════════════════════════════
# Fixture
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock OpenAI 客户端，返回预设章节内容。"""

@pytest.fixture
def sample_input() -> StandardizedInput:
    """示例 StandardizedInput。"""

@pytest.fixture
def sample_retrieval() -> RetrievalResponse:
    """示例 RetrievalResponse（含 regulations + cases）。"""

@pytest.fixture
def sample_context(sample_input, sample_retrieval) -> ChapterContext:
    """完整的 ChapterContext 示例。"""

# ═══════════════════════════════════════════════════════════════
# 数据结构测试
# ═══════════════════════════════════════════════════════════════

class TestChapterContext:
    """ChapterContext 数据结构测试。"""
    # - 默认值测试
    # - 属性赋值测试
    # - macro_view 列表不可变性

# ═══════════════════════════════════════════════════════════════
# 基类测试
# ═══════════════════════════════════════════════════════════════

class TestBaseChapterAgent:
    """BaseChapterAgent 基类测试。"""
    # - __init__ 默认参数
    # - __init__ 自定义 llm_client / max_tokens
    # - _render_prompt 渲染正确
    # - _render_prompt 缺字段 → StrictUndefined 报错
    # - _call_llm 正常返回
    # - _call_llm 空响应处理
    # - generate 完整管道（render → call → post_process）
    # - post_process 标题规范化
    # - post_process 工程名称替换

# ═══════════════════════════════════════════════════════════════
# 模板渲染测试
# ═══════════════════════════════════════════════════════════════

class TestJinja2Templates:
    """Jinja2 模板渲染测试（不调用 LLM）。"""
    # - 每个模板文件存在且可加载
    # - 模板渲染包含 role.txt 内容
    # - 模板渲染包含 output_format.txt 内容
    # - 模板渲染包含 standardized_input
    # - 模板渲染包含 regulations
    # - 模板渲染包含 cases
    # - 模板渲染包含 macro_view
    # - 空 retrieval 不报错

# ═══════════════════════════════════════════════════════════════
# 9 个子类测试
# ═══════════════════════════════════════════════════════════════

class TestChapter1Agent:
    """Chapter1Agent 编制依据。"""
    # - 类变量正确
    # - generate 正常流程（Mock LLM）
    # - post_process 标题规范化

class TestChapter2Agent: ...  # 同上模式
class TestChapter3Agent: ...
class TestChapter4Agent: ...
class TestChapter5Agent: ...
class TestChapter6Agent: ...
class TestChapter7Agent: ...
class TestChapter8Agent: ...
class TestChapter9Agent: ...

# ═══════════════════════════════════════════════════════════════
# 后处理测试
# ═══════════════════════════════════════════════════════════════

class TestPostProcess:
    """post_process 规则测试。"""
    # - "第一章 编制依据" → "一、编制依据"
    # - "1. 编制依据" → "一、编制依据"
    # - 非标准名称替换为标准名称
    # - {{工程名称}} 替换为实际名称
    # - 无需替换的内容保持不变
```

**Mock 策略**：

| 依赖 | Mock 方式 |
|------|----------|
| LLM | `MagicMock(spec=OpenAI)` → mock `client.chat.completions.create` 返回预设 Markdown |
| KnowledgeRetriever | 不 Mock（Agent 不直接调用检索，只消费 ChapterContext） |
| 模板文件 | 使用真实模板文件（测试模板渲染正确性） |

**预计测试用例**：~50 个（覆盖率目标 ≥85%）

---

## 验证计划

```bash
# 0. 安装 Jinja2
conda run -n sca pip install "Jinja2>=3.1.0"

# 1. 代码格式化 + 检查
conda run -n sca ruff format agents/ prompts/ tests/test_agents.py
conda run -n sca ruff check agents/ prompts/ tests/test_agents.py

# 2. 运行模块测试
conda run -n sca pytest tests/test_agents.py -v

# 3. 覆盖率（目标 ≥85%）
conda run -n sca pytest tests/test_agents.py --cov=agents --cov-report=term-missing

# 4. 全量测试不回归
conda run -n sca pytest tests/ -v

# 5. 快速集成验证（Mock LLM，仅测试模板渲染）
conda run -n sca python -c "
from agents.base import BaseChapterAgent, ChapterContext
from agents.chapter1_basis import Chapter1Agent
from input_parser.models import StandardizedInput, BasicInfo
from knowledge_retriever.models import RetrievalResponse

ctx = ChapterContext(
    standardized_input=StandardizedInput(
        basic=BasicInfo(project_name='测试工程', project_type='输电线路')
    ),
    chapter_number=1,
    chapter_title='编制依据',
)
agent = Chapter1Agent()
prompt = agent._render_prompt(ctx)
print(prompt[:500])
print('--- 模板渲染成功 ---')
"
```

---

## 实施步骤

| 步骤 | 内容 | 前置 |
|------|------|------|
| 1 | `pip install Jinja2` + 更新 `requirements.txt` | 无 |
| 2 | 创建 `prompts/static/role.txt` + `output_format.txt` | 无 |
| 3 | 创建 9 个 `prompts/agents/chapterN.j2` 模板 | Step 2 |
| 4 | 创建 `agents/__init__.py` | 无 |
| 5 | 创建 `agents/base.py`（ChapterContext + BaseChapterAgent） | Step 3 |
| 6 | 创建 9 个 `agents/chapterN_xxx.py` 子类 | Step 5 |
| 7 | 创建 `tests/test_agents.py`（~50 用例） | Step 6 |
| 8 | `ruff format` + `ruff check` | Step 7 |
| 9 | `pytest tests/test_agents.py -v --cov` | Step 8 |
| 10 | `pytest tests/ -v` 全量回归 | Step 9 |

---

## 依赖说明

| 依赖 | 类型 | 说明 |
|------|------|------|
| `Jinja2>=3.1.0` | **新增** | 模板渲染引擎 |
| `openai` | 已有 | LLM 调用 |
| `input_parser.models.StandardizedInput` | 已有 (S11) | 标准化输入 |
| `knowledge_retriever.models.RetrievalResponse` | 已有 (S10) | 检索结果 |
| `utils.logger_system.log_msg` | 已有 | 日志 |
| `config.LLM_CONFIG` | 已有 | LLM 配置 |
