# 部署与依赖

## 部署环境

单机部署，所有组件跑在 pci-3 上：

```
pci-3 (RTX 4090 / i9-13900K / 64GB / Ubuntu 20.04)
├── Python 3.10 (conda: sca)
├── MonkeyOCR (Docker)
├── qmd + sqlite-vec (本地)
├── LightRAG (本地)
└── LLM API (远程)
```

## 安装

```bash
conda activate sca
pip install -r requirements.txt
```

## 核心依赖

| 类别 | 包 | 用途 |
|------|---|------|
| LLM | openai (httpx) | DeepSeek / 其他 OpenAI 兼容 API |
| 验证 | pydantic | 数据结构校验 |
| 日志 | logging (stdlib) | 日志（通过 utils/logger_system.py 封装） |
| OCR | requests | MonkeyOCR HTTP 客户端 |
| 进度 | tqdm | 批量处理进度条 |
| 向量检索 | qmd + sqlite-vec | 章节级案例语义检索（替代 ChromaDB） |

### 待新增依赖（Phase 2+）

| 包 | 用途 |
|----|------|
| langchain | Agent 编排框架 |
| langgraph | 多 Agent 状态图 |
| lightrag | 知识图谱推理 |
| jinja2 | Prompt 模板渲染 |

## 外部服务

| 服务 | 用途 | 必需 |
|------|------|------|
| MonkeyOCR (Docker) | PDF → Markdown | 仅 PDF 输入时 |
| DeepSeek API | LLM 清洗 | ✅ |
| 生成/审核 LLM API | 章节生成、合规检查 | ✅（待定模型） |

## LLM 配置

当前使用 DeepSeek（清洗阶段）：

```python
api_key = "sk-..."
base_url = "http://110.42.53.85:11081/v1"
model = "deepseek-chat"
```

生成和审核阶段的 LLM 待定，可能需要更强的模型（Claude / GPT-4）。

> **选型因素**：中文长文本生成质量、context window（施工方案单章可达数千字）、API 成本、延迟（交互式生成需 <30s/章）

## Docker

```bash
# MonkeyOCR
docker start monkeyocr-api    # 启动
docker ps | grep monkeyocr     # 检查状态
```
