# Herald 代码规范 — 基于 nanobot 风格提炼

> 本规范从 nanobot (HKUDS) 源码中提炼，作为 Herald 项目代码审查的判断标准。

## 1. 模块级：一个文件只做一件事

- 每个 `.py` 文件对应一个**清晰的职责**
  - ✅ `loop.py` — agent 循环 | `context.py` — 上下文构建 | `memory.py` — 记忆读写
  - ❌ 一个文件同时处理消息路由、工具注册和会话管理
- 模块 docstring 用**一句话**说清楚这个文件干什么：
  ```python
  """Agent loop: the core processing engine."""
  ```
- 文件行数控制在 **300 行以内**（nanobot 最长的 `loop.py` 约 350 行，已经是极限）

## 2. 类设计：dataclass 优先，继承克制

### 2.1 纯数据用 dataclass，不要用普通 class

```python
# ✅ 正确
@dataclass
class InboundMessage:
    channel: str
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

# ❌ 错误：用普通 class 手写 __init__
class InboundMessage:
    def __init__(self, channel, sender_id, ...):
        self.channel = channel
        ...
```

### 2.2 配置用 Pydantic BaseModel

```python
class TelegramConfig(BaseModel):
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
```

### 2.3 抽象基类简洁明了

- ABC 只定义**接口契约**，不塞逻辑
- 公共逻辑放在 ABC 的非抽象方法里（如 `BaseChannel._handle_message`）
- nanobot 的 `Tool` 基类：4 个抽象属性/方法（`name`, `description`, `parameters`, `execute`），加一个通用的 `to_schema()`

### 2.4 继承最多一层

- `Tool → ReadFileTool` ✅
- `Tool → AdvancedTool → ReadFileTool` ❌ 不要多层继承

## 3. 函数设计：短小、单一职责

### 3.1 函数长度

- **目标**：20-40 行
- **上限**：60 行（超过就拆）
- nanobot 的 `_process_message` 约 50 行，已经是最长的方法

### 3.2 参数设计

- 必选参数不超过 **5 个**，多了用 dataclass/config 对象包装
- `**kwargs` 只用于 `Tool.execute` 这种需要动态参数的场景
- 关键参数显式传递，不用默认值掩盖：
  ```python
  # ✅ 调用者必须明确传入
  def __init__(self, provider: LLMProvider, workspace: Path, bus: MessageBus): ...

  # ❌ 用 None 默认值掩盖必要参数
  def __init__(self, provider=None, workspace=None): ...
  ```

### 3.3 返回值

- 简单场景用 `tuple`：`async def _run_agent_loop(...) -> tuple[str | None, list[str]]`
- 复杂场景用 dataclass：如 `LLMResponse`
- 避免返回 `dict`（除非是 JSON 序列化场景）

## 4. 类型注解：完整、精确

### 4.1 基本要求

- **所有**函数签名必须有类型注解（参数 + 返回值）
- 使用 Python 3.10+ 语法：`str | None` 而非 `Optional[str]`，`list[str]` 而非 `List[str]`

### 4.2 复杂类型

```python
# ✅ 类型清晰
_outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]]
_running_tasks: dict[str, asyncio.Task[None]]

# ❌ 用 Any 糊弄
_subscribers: dict[str, Any]
```

### 4.3 @property 返回类型

```python
@property
def has_tool_calls(self) -> bool:
    return len(self.tool_calls) > 0
```

## 5. 错误处理：优雅降级，不崩溃

### 5.1 Tool 执行错误返回字符串，不抛异常

```python
# ✅ nanobot 的 ToolRegistry.execute
try:
    return await tool.execute(**params)
except Exception as e:
    return f"Error executing {name}: {str(e)}"
```

### 5.2 LLM 调用错误同样返回 LLMResponse，不崩溃

```python
except Exception as e:
    return LLMResponse(content=f"Error calling LLM: {str(e)}", finish_reason="error")
```

### 5.3 文件/网络操作用 try-except 包裹

- 捕获具体异常（`PermissionError`, `json.JSONDecodeError`），不要裸 `except:`
- 日志记录用 `logger.warning` / `logger.error`

## 6. 异步编程

### 6.1 所有 I/O 操作用 async

- 网络请求、文件读写（大文件）、LLM 调用都是 `async def`
- 小文件读写（配置、JSONL）可以同步（nanobot 的 SessionManager 就是同步文件 I/O）

### 6.2 后台任务用 asyncio.create_task

```python
bg_task = asyncio.create_task(self._run_subagent(task_id, task, label, origin))
bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
```

### 6.3 超时控制

```python
msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
```

## 7. 命名约定

| 类别 | 风格 | 示例 |
|------|------|------|
| 类名 | PascalCase | `AgentLoop`, `ToolRegistry`, `CronService` |
| 函数/方法 | snake_case | `get_or_create`, `_process_message` |
| 常量 | UPPER_SNAKE | `DEFAULT_HEARTBEAT_INTERVAL_S`, `MAX_REDIRECTS` |
| 私有方法 | 前缀 `_` | `_guard_command`, `_resolve_model` |
| 布尔属性 | `is_`/`has_` 前缀 | `is_gateway`, `has_tool_calls`, `is_running` |
| 回调参数 | `on_` 前缀 | `on_job`, `on_heartbeat` |
| 工厂/查找函数 | `find_`/`get_` | `find_by_model`, `find_gateway` |

## 8. 模块导入

### 8.1 顺序

```python
# 1. 标准库
import asyncio
import json
from pathlib import Path
from typing import Any

# 2. 第三方库
from loguru import logger
from pydantic import BaseModel

# 3. 项目内部（使用绝对导入）
from nanobot.bus.events import InboundMessage
from nanobot.agent.tools.registry import ToolRegistry
```

### 8.2 延迟导入

- 循环依赖用**函数内 import** 解决（nanobot 在 `_consolidate_memory` 等方法中这样做）
- 可选依赖也用延迟导入：`from nanobot.channels.telegram import TelegramChannel`

## 9. 日志

- 使用 `loguru` 的 `logger`，禁用 `print()`
- 级别使用：
  - `logger.debug` — 内部细节（工具参数、缓存命中）
  - `logger.info` — 关键事件（启动、消息处理、任务完成）
  - `logger.warning` — 非致命问题（配置加载失败、文件缺失）
  - `logger.error` — 错误（LLM 调用失败、工具执行异常）

## 10. 配置与注册表模式

### 10.1 注册表模式（Registry Pattern）

nanobot 用 `ProviderSpec` + `PROVIDERS` 元组实现了**声明式注册表**：

```python
# 添加新 provider 只需要加一个 ProviderSpec，不需要改任何 if-elif
PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(name="openrouter", keywords=("openrouter",), ...),
    ProviderSpec(name="anthropic", keywords=("anthropic", "claude"), ...),
    ...
)
```

- 新增 provider 只需加一条记录，**零代码修改**
- 所有行为（env 变量、前缀、特殊参数）都由数据驱动
- Herald 的 Tool 注册也遵循此模式

### 10.2 配置 Schema

- Pydantic `BaseModel` 定义，嵌套结构清晰
- 配置加载：JSON → snake_case 转换 → Pydantic 验证
- 不要把配置散落在代码里，集中到 `config/schema.py`

## 11. 安全

- Shell 命令执行有**黑名单**（deny_patterns）和**沙箱**（restrict_to_workspace）
- 文件操作有 `allowed_dir` 限制
- URL 验证：只允许 http/https，限制重定向次数
- 敏感信息不硬编码，通过配置/环境变量传入

## 12. 反模式清单（审查时重点关注）

| 反模式 | 说明 |
|--------|------|
| **God class** | 单个类超过 300 行或承担 3 个以上职责 |
| **过度抽象** | 只有一个实现的 ABC、不必要的设计模式 |
| **裸 dict 传递** | 应该用 dataclass/Pydantic 的地方用 dict |
| **print 调试** | 任何 `print()` 调用 |
| **类型缺失** | 函数签名缺少类型注解 |
| **大函数** | 超过 60 行的函数 |
| **深层嵌套** | 超过 3 层缩进（if 套 for 套 if） |
| **硬编码配置** | URL、API key、超时时间写死在代码里 |
| **mock/stub** | MVP 中使用 mock 代替真实实现 |
| **冗余注释** | 注释复述代码（`# 返回结果` → `return result`） |
| **未使用的导入/变量** | dead code |
| **过长的导入列表** | 单个 from import 超过 5 个对象时考虑拆分 |

---

*本规范基于 nanobot (HKUDS) 源码分析，版本日期 2026-02-21。*
