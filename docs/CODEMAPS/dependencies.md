<!-- Generated: 2026-02-25 | Files scanned: requirements.txt + configs | Token estimate: ~550 -->

# 外部依赖与集成

## Python 包依赖

### 核心生产依赖

```
openai==2.21.0           # LLM API 客户端（兼容 DeepSeek）
requests==2.32.5         # HTTP 客户端（OCR API）
tqdm==4.67.3             # 进度条
python-dotenv==1.2.1     # 环境变量管理
pydantic==2.12.5         # 数据验证
PyYAML==6.0.3            # YAML 配置
qmd                      # 向量数据库（sqlite-vec）
lightrag                 # 知识图谱推理（LightRAG）
networkx                 # 图遍历（KGRetriever 依赖）
sentence-transformers    # 嵌入模型框架
torch>=2.0               # PyTorch
numpy                    # 向量操作
```

### 测试依赖

```
pytest==9.0.2            # 测试框架
pytest-cov==7.0.0        # 覆盖率
ruff                     # 格式化 + lint
```

**Conda 环境**: `sca` (Python 3.11)

---

## 外部服务

### MonkeyOCR API

| 项目 | 详情 |
|------|------|
| 端点 | http://localhost:7861/parse |
| 部署 | `docker start monkeyocr-api` |
| 调用 | `crawler.py:MonkeyOCRClient.to_markdown()` |

### DeepSeek LLM API

| 项目 | 详情 |
|------|------|
| 端点 | http://110.42.53.85:11081/v1 |
| 调用 | cleaning.py, density_evaluator.py, content_refiner.py, llm_extractor.py |
| 并发 | max_workers=4 |

### 本地 GPU 模型

| 模型 | 用途 | 显存 |
|------|------|------|
| Qwen3-Embedding-0.6B | 向量嵌入 (1024 维) | 1.1GB |
| Qwen3-Reranker-0.6B | 重排序 | 1.1GB |
| **双模型合计** | E2E MRR@3=0.8683 | **2.3GB** |

**环境变量**:
```bash
SCA_LLM_API_KEY="sk-..."
SCA_LLM_BASE_URL="http://110.42.53.85:11081/v1"
SCA_LLM_MODEL="deepseek-chat"
```

---

## 模块间依赖图

```
knowledge_retriever/
├─ 依赖 → vector_store/retriever.py (VectorRetriever)
├─ 依赖 → knowledge_graph/retriever.py (KGRetriever)
└─ 依赖 → utils/logger_system.py

vector_store/
├─ 依赖 → qmd (外部包)
├─ 依赖 → vector_store/config.py (路径/模型/Collection 定义)
└─ 入口 → vector_store/__main__.py

knowledge_graph/
├─ 依赖 → lightrag (外部包)
├─ 依赖 → networkx (图遍历)
├─ 依赖 → knowledge_graph/config.py (LLM 配置)
└─ 入口 → knowledge_graph/__main__.py

entity_extraction/
├─ 依赖 → openai (LLM 抽取)
├─ 依赖 → config.py (全局 LLM 配置)
└─ 入口 → entity_extraction/__main__.py
```

---

## 健康检查

| 服务 | 命令 | 预期 |
|------|------|------|
| MonkeyOCR | `curl -X OPTIONS http://localhost:7861/parse` | HTTP 200 |
| DeepSeek | `curl http://110.42.53.85:11081/v1/models` | 模型列表 |
| Docker | `docker ps \| grep monkeyocr` | 容器运行中 |
| 向量库 | `python -m vector_store` | 构建成功 |
| 知识图谱 | `python -m knowledge_graph` | 导入成功 |

## 风险评估

| 风险 | 缓解 |
|------|------|
| OCR 宕机 | Docker 重启 |
| LLM 限流 | 调整并发数 |
| GPU 显存不足 | 双模型仅需 2.3GB |
| Key 泄露 | 环境变量隔离 |
