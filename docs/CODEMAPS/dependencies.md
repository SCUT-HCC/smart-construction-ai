<!-- Generated: 2026-02-25 | Files scanned: requirements.txt + eval scripts + model configs | Token estimate: ~550 -->

# 外部依赖与集成

## Python 包依赖

### 核心生产依赖

```
openai==2.21.0       # LLM API 客户端（兼容 DeepSeek）— 清洗 + 密度评估 + 精炼
requests==2.32.5     # HTTP 客户端（OCR API）
tqdm==4.67.3         # 进度条（批量处理 + 知识提取）
python-dotenv==1.2.1 # 环境变量管理
pydantic==2.12.5     # 数据验证与序列化
PyYAML==6.0.3        # YAML 配置解析
```

### 测试依赖

```
pytest==9.0.2        # 测试框架
pytest-cov==7.0.0    # 覆盖率报告
```

### 评测依赖（Phase 2b - K20 新增）

```
torch>=2.0           # PyTorch（模型加载）
sentence-transformers>=2.5.0  # 嵌入模型框架
numpy                # 向量操作 + 指标计算
```

### 未来依赖（Phase 3+）

```
qmd==0.1.0           # 向量数据库（案例语义检索，K20 选定 Qwen3-0.6B）
sqlite-vec==0.1.6    # SQLite 向量扩展
langchain            # LangChain 工具链
langchain-openai     # OpenAI 集成
langgraph            # 多智能体编排
lightrag             # 知识图谱推理
```

**Conda 环境**: `sca` (Python 3.10)

---

## 外部服务集成

### 1. MonkeyOCR API

| 项目 | 详情 |
|------|------|
| **功能** | PDF → Markdown OCR 转换 |
| **端点** | http://localhost:7861/parse |
| **部署** | Docker: `docker start monkeyocr-api` |
| **超时** | 120 秒 |
| **调用位置** | `crawler.py:MonkeyOCRClient.to_markdown()` |
| **失败处理** | 返回空字符串 → 跳过该文件 |

### 2. DeepSeek LLM API

| 项目 | 详情 |
|------|------|
| **功能** | 语义清洗 / 密度评估 / 内容精炼 |
| **端点** | http://110.42.53.85:11081/v1/chat/completions |
| **模型** | deepseek-chat |
| **调用位置** | `cleaning.py`, `density_evaluator.py`, `content_refiner.py` |
| **并发控制** | max_workers=4（知识提取管道） |
| **失败处理** | 清洗: 抛异常; 密度评估: 标记 low; 精炼: 保留原文 |

**环境变量**:
```bash
SCA_LLM_API_KEY="sk-..."
SCA_LLM_BASE_URL="http://110.42.53.85:11081/v1"
SCA_LLM_MODEL="deepseek-chat"
```

---

## 服务健康检查

| 服务 | 检查命令 | 预期响应 |
|------|---------|---------|
| MonkeyOCR | `curl -X OPTIONS http://localhost:7861/parse` | HTTP 200 |
| DeepSeek LLM | `curl http://110.42.53.85:11081/v1/models` | 模型列表 |
| Docker | `docker ps \| grep monkeyocr` | 容器运行中 |

---

## 依赖风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| OCR 服务宕机 | 无法处理 PDF | Docker 重启；备用本地 OCR |
| LLM API 限流 | 清洗/评估失败 | 重试机制（待实现）；调整并发数 |
| API Key 泄露 | 费用损失 + 安全 | 环境变量（已实现） |
| 网络不稳定 | 处理失败 | 重试机制（待实现） |

---

## 网络拓扑

```
┌──────────────────────────┐
│  smart-construction-ai   │
│  (localhost)             │
└────────┬─────────────────┘
         │
    ┌────┼──────────┬──────────────┐
    ▼    ▼          ▼              ▼
┌──────┐┌────────┐┌──────────┐┌──────────┐
│ 文件 ││Docker  ││DeepSeek  ││ output/  │
│ data/││MonkeyO ││LLM API   ││fragments │
│      ││CR:7861 ││:11081    ││.jsonl    │
└──────┘└────────┘└──────────┘└──────────┘
```

---

## 向量检索模型配置（K20 选型）

### Embedding 模型

| 模型 | 维度 | MRR@3 | 显存(MB) | Hit@1 | 部署状态 |
|------|------|-------|----------|-------|---------|
| Qwen3-Embedding-0.6B | 1024 | 0.8600 | 1146 | 80% | ✅ 生产选定 |
| Qwen3-Embedding-4B | 2560 | 0.8917 | 10269 | 85% | 高精度备选 |
| BGE-M3 | 1536 | — | — | — | 评估中 |

### Reranker 模型

| 模型 | 架构 | MRR@3改进 | 显存(MB) | 部署状态 |
|------|------|----------|----------|---------|
| Qwen3-Reranker-0.6B | CausalLM | +2.8% | 1100 | ✅ 生产选定 |
| Qwen3-Reranker-4B | CausalLM | +4.2% | 8200 | 高精度备选 |
| BGE-Reranker-V2-M3 | CrossEncoder | +1.5% | 2800 | 评估中 |

### E2E 联合管道（选定）

```
Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B
├─ 端到端 MRR@3: 0.8683
├─ Hit@1: 82% | Hit@3: 92%
├─ 双模型显存: 2.3GB（部署可行 ✅）
├─ 端到端延迟: 169ms
└─ 成本: 3.8GB CPU + RTX 3090 可运行
```

---

## 测试验证

```bash
# 单元测试（无需 API/模型）
conda run -n sca pytest tests/test_cleaning.py::TestRegexCleaningClean -v
conda run -n sca pytest tests/test_verifier.py -v

# 完整覆盖率
conda run -n sca pytest tests/ --cov=. --cov-report=term-missing

# 向量检索评测（需 GPU，耗时 30+ 分钟）
conda run -n sca python scripts/eval_embedding_models.py \
    --eval-dataset eval/embedding/eval_dataset.jsonl \
    --fragments docs/knowledge_base/fragments/fragments.jsonl \
    --output eval/embedding/results/

# qmd 集成验证（快速，5 分钟）
conda run -n sca python scripts/verify_qmd_integration.py \
    --fragments docs/knowledge_base/fragments/fragments.jsonl
```
