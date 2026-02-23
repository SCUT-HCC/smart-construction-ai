# 生产代码缺陷修复计划 — cleaning.py 异常处理 + verifier.py forbidden_phrases

## 摘要

修复两个在任务 1.1 代码审查中发现的生产代码缺陷：(1) `LLMCleaning.clean()` 异常回退为死代码；(2) `MarkdownVerifier.check_hallucination()` 忽略构造参数 `forbidden_phrases`。同步更新测试用例覆盖修复后的行为。

---

## 缺陷分析

### 缺陷 1：`cleaning.py:430-432` — 降级机制失效

**现状**：

```python
# cleaning.py:430-432
except Exception as e:
    log_msg("ERROR", f"LLM 清洗块 {i+1} 异常: {str(e)}")  # ← 抛出异常
    cleaned_chunks.append(chunk)                              # ← 永远不执行（死代码）
```

**根因**：`log_msg("ERROR", ...)` 内部先 `logger.error(msg)` 再 `raise Exception(msg)`（见 `utils/logger_system.py:27-28`），导致后续的降级逻辑 `cleaned_chunks.append(chunk)` 不可达。

**设计意图**：单个块的 LLM 调用失败时，应降级保留原始块继续处理，而非中断整个管道。这是合理的容错策略——16 份 PDF 各有数十个块，因一个块的 API 超时而丢弃整份文档是不可接受的。

**修复方案**：将 `log_msg("ERROR", ...)` 改为 `log_msg("WARNING", ...)`，使异常被记录但不抛出，降级逻辑正常执行。

---

### 缺陷 2：`verifier.py:34-51` — `forbidden_phrases` 参数被忽略

**现状**：

```python
# verifier.py:6-8 — 接收并存储了参数
def __init__(self, min_length_ratio=0.5, forbidden_phrases=None):
    self.forbidden_phrases = forbidden_phrases or []

# verifier.py:34-51 — 完全不读取 self.forbidden_phrases，使用硬编码模式
def check_hallucination(self, text):
    preamble_patterns = [          # ← 硬编码，与 __init__ 参数割裂
        r'^\s*好的[，,。！!：:\s]',
        ...
    ]
```

**调用方**：`main.py:37` 和 `tests/conftest.py:23` 均从 `config.VERIFY_CONFIG["forbidden_phrases"]` 传入值 `["好的", "我已为你", "为您清洗", "Here is the cleaned", "Markdown 内容如下"]`，但这些值从未生效。

**修复方案**：在 `check_hallucination()` 末尾追加对 `self.forbidden_phrases` 的行首子串匹配检查。保留硬编码正则模式不变（它们更精确，含标点约束），`forbidden_phrases` 作为可配置的补充检测机制。

---

## 审查点

| # | 问题 | 判断 | 需确认？ |
|---|------|------|---------|
| 1 | 是否应修改 `log_msg` 本身而非调用方？ | 否。`log_msg("ERROR")` 抛异常是全局约定（12 处调用均依赖此行为），不应改变。只需将此处降级为 WARNING | 否 |
| 2 | `forbidden_phrases` 匹配策略：全文子串 vs 行首匹配？ | 行首匹配（`^\s*{phrase}`），与现有硬编码模式的检测逻辑一致 | 否 |
| 3 | 硬编码模式和 `forbidden_phrases` 有重叠（如 "好的"），是否需要去重？ | 否。重叠不影响正确性，保持两层检测独立性更易维护 | 否 |

---

## 拟议变更

| 文件 | 变更 | 标注 |
|------|------|------|
| `cleaning.py:431` | `log_msg("ERROR", ...)` → `log_msg("WARNING", ...)` | `[MODIFY]` |
| `verifier.py:34-51` | `check_hallucination()` 末尾追加 `self.forbidden_phrases` 行首匹配逻辑 | `[MODIFY]` |
| `tests/test_cleaning.py` | 新增 `test_clean_api_error_falls_back_to_original_chunk` | `[MODIFY]` |
| `tests/test_verifier.py` | 新增 `test_custom_forbidden_phrase_detected` | `[MODIFY]` |

---

## 详细设计

### 1. `cleaning.py` — 修复异常处理

**修改前**（`cleaning.py:430-432`）：
```python
except Exception as e:
    log_msg("ERROR", f"LLM 清洗块 {i+1} 异常: {str(e)}")
    cleaned_chunks.append(chunk)
```

**修改后**：
```python
except Exception as e:
    log_msg("WARNING", f"LLM 清洗块 {i+1} 异常，降级保留原文: {str(e)}")
    cleaned_chunks.append(chunk)
```

变更：1 行，仅改日志级别和消息文本。

---

### 2. `verifier.py` — 修复 `forbidden_phrases` 检测

**修改前**（`verifier.py:34-51`）：
```python
def check_hallucination(self, text: str) -> bool:
    preamble_patterns = [...]
    for pattern in preamble_patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            ...
            return False
    return True
```

**修改后**：
```python
def check_hallucination(self, text: str) -> bool:
    preamble_patterns = [...]               # 保留不变
    for pattern in preamble_patterns:       # 保留不变
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            ...
            return False

    # 补充：检查配置的 forbidden_phrases（行首子串匹配）
    for phrase in self.forbidden_phrases:
        pattern = r'^\s*' + re.escape(phrase)
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            matched_line = text[match.start():text.find('\n', match.start())]
            log_msg("WARNING", f"检测到禁用短语: '{matched_line.strip()}'")
            return False
    return True
```

变更：追加 6 行。不修改现有逻辑。

---

### 3. 测试更新

#### `tests/test_cleaning.py` — 新增 1 个用例

```python
class TestLLMCleaningClean:
    ...
    def test_clean_api_error_falls_back_to_original_chunk(self) -> None:
        """API 调用异常时，应降级保留原始块而非抛出异常。"""
        # mock API 抛出异常
        # 断言：不抛异常，返回值包含原始内容
```

#### `tests/test_verifier.py` — 新增 1 个用例

```python
class TestCheckHallucination:
    ...
    def test_custom_forbidden_phrase_detected(self) -> None:
        """通过 forbidden_phrases 配置的自定义短语应被检测到。"""
        v = MarkdownVerifier(forbidden_phrases=["自定义禁用词"])
        assert v.check_hallucination("自定义禁用词出现在文本中") is False
        # 同时验证行中间出现不误报
        assert v.check_hallucination("这里提到自定义禁用词不在行首") is True
```

---

## 实施步骤

| 步骤 | 操作 | 涉及文件 |
|------|------|---------|
| 1 | 修改 `cleaning.py:431`：`"ERROR"` → `"WARNING"` + 更新消息 | `cleaning.py` |
| 2 | 修改 `verifier.py:check_hallucination()`：追加 `forbidden_phrases` 检查 | `verifier.py` |
| 3 | 新增测试用例 `test_clean_api_error_falls_back_to_original_chunk` | `tests/test_cleaning.py` |
| 4 | 新增测试用例 `test_custom_forbidden_phrase_detected` | `tests/test_verifier.py` |
| 5 | 运行全部测试确认通过 + 覆盖率不下降 | — |

---

## 验证计划

```bash
# 1. 运行全部测试
conda run -n sca pytest tests/ -v

# 2. 覆盖率报告（应 ≥ 95%，修复后 cleaning.py:430-432 不再为 Miss）
conda run -n sca pytest tests/ --cov=cleaning --cov=verifier --cov-report=term-missing

# 3. 预期结果
# - 59 passed（原 57 + 新增 2）
# - cleaning.py 覆盖率从 94% → 96%+（430-432 行被覆盖）
# - verifier.py 保持 100%
```

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 降级为 WARNING 后，单块失败可能被忽略 | WARNING 级别仍会打印日志，运维可通过日志监控发现；且 `log_json` 已记录了失败信息 |
| `forbidden_phrases` 新逻辑与硬编码模式重叠匹配 | 无副作用：两层检测命中任一即返回 False，重复命中不影响结果 |
| `re.escape(phrase)` 对含正则元字符的短语可能过度转义 | 预期 `forbidden_phrases` 均为纯中/英文短语，无元字符；且 `re.escape` 本身就是安全做法 |
