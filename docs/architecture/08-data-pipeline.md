# 数据管道（已完成）

> PDF → OCR → 正则清洗 → LLM 语义清洗 → final.md

## 状态：✅ 已完成

16 份 PDF 全部处理完毕，输出在 `output/1-16/final.md`。

## 处理流程

```
data/{n}.pdf
  → MonkeyOCR（Docker 服务）→ output/{n}/raw.md
  → RegexCleaning（正则清洗）→ output/{n}/regex.md
  → LLMCleaning（DeepSeek 语义清洗）→ output/{n}/final.md
  → MarkdownVerifier（质量检查）
```

## 各阶段说明

### OCR（MonkeyOCR）

- Docker 容器 `monkeyocr-api`，端口 7861
- 将 PDF 转为 Markdown，保留表格结构
- 主要问题：水印残留、页码、LaTeX 装饰符、表格对齐错位

### 正则清洗

`cleaning.py` 中的 `RegexCleaning`，处理规则在 `config.py` 的 `CLEANING_CONFIG`：

- 移除水印（CHINA SOUTHERN POWER GRID）
- 修复 LaTeX 圈号（`\textcircled{1}` → `1.`）
- 删除孤立页码行
- 修复换行符

### LLM 语义清洗

`cleaning.py` 中的 `LLMCleaning`，使用 DeepSeek：

- 按段落智能分块（chunk_size=2000）
- 标题层级修复
- 语义重构和段落流优化
- 去除 LLM 幻觉（forbidden_phrases 检查）

### 质量验证

`verifier.py` 中的 `MarkdownVerifier`：

- 字数损失检查（min_length_ratio=0.5）
- LLM 幻觉检查（禁止出现"好的""我已为你"等）
- Markdown 结构合法性（表格闭合等）

## 现有代码

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | 43 | CLI 入口 |
| `config.py` | 40 | 配置中心 |
| `crawler.py` | 69 | MonkeyOCR 客户端 |
| `cleaning.py` | 434 | 正则 + LLM 清洗 |
| `processor.py` | 90 | 流程编排 |
| `verifier.py` | 60 | 质量验证 |
| `utils/logger_system.py` | — | 日志系统 |

## 后续用途

数据管道在未来系统中继续作为**前置处理**：当用户提交 PDF 格式的施工方案（用于审核）时，先经过此管道转成 Markdown，再进入审核系统。
