# 增量代码审查（未提交内容）

请执行以下步骤：

## 1. 读取代码规范

先读取 `.claude/code-style-guide.md`，理解所有审查标准。

## 2. 获取未提交的变更

```bash
# 查看所有未提交的变更（staged + unstaged + untracked .py 文件）
git diff HEAD --name-only -- '*.py'
git diff --cached --name-only -- '*.py'
git ls-files --others --exclude-standard -- '*.py'
```

对上述命令输出的每个 `.py` 文件：
- 如果是已跟踪文件的修改：`git diff HEAD -- <file>` 获取差异
- 如果是新增文件：读取完整内容

## 3. 审查维度

**只审查变更部分**（新增/修改的代码），对照以下标准：
- **模块职责**：新文件是否只做一件事？模块 docstring 是否缺失？
- **类设计**：新增的类是否符合 dataclass/Pydantic 规范？
- **函数设计**：新增/修改的函数是否超过 60 行？参数是否合理？
- **类型注解**：新增代码是否有完整类型注解？
- **错误处理**：新增的 I/O 操作是否有适当的 try-except？
- **命名**：是否符合命名约定？
- **日志**：是否使用 loguru？有没有 print()？
- **反模式**：对照反模式清单检查变更部分
- **与 CLAUDE.md 的一致性**：变更是否违反 CLAUDE.md 中的规则？

## 4. 输出 implementation_plan.md

将审查结果写入项目根目录的 `implementation_plan.md`，格式如下：

```markdown
# 增量代码审查报告 — Herald

> 审查时间: YYYY-MM-DD HH:MM
> 审查范围: 未提交变更
> 审查标准: .claude/code-style-guide.md + CLAUDE.md

## 变更概览

| 文件 | 状态 | 变更行数 |
|------|------|----------|
| herald/xxx.py | 修改 | +XX / -YY |
| herald/yyy.py | 新增 | +ZZ |

## 摘要

- 变更文件数: X
- 发现问题数: Y（严重 A / 一般 B / 建议 C）
- 总体评价: （一两句话）

## 审查点 (Review Points)

### [严重] 文件路径 — 问题标题

**问题描述**: ...
**代码位置**: 行 XX-YY（diff 上下文）
**当前代码**:
\`\`\`python
# 有问题的代码片段
\`\`\`
**建议修改**:
\`\`\`python
# 建议的改法
\`\`\`
**理由**: ...

---

## 验证计划

修改完成后的验证步骤：
1. ...
2. ...
```

## 5. 重要提醒

- **不要直接修改任何代码**，只输出 implementation_plan.md
- 只关注**变更部分**，不要审查未修改的代码
- 如果没有未提交的 `.py` 变更，在 implementation_plan.md 中说明"无待审查的 Python 变更"
- 覆盖已有的 implementation_plan.md
