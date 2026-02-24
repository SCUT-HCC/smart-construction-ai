<!-- Generated: 2026-02-24 | Files scanned: requirements.txt + config.py + ke/config.py | Token estimate: ~450 -->

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

### 未来依赖（Phase 3+）

```
qmd==0.1.0           # 向量数据库（案例语义检索）
sqlite-vec==0.1.6    # SQLite 向量扩展
langchain            # LangChain 工具链
langchain-openai     # OpenAI 集成
langgraph            # 多智能体编排
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

## 测试验证

```bash
# 快速验证（无需 API）
conda run -n sca pytest tests/test_cleaning.py::TestRegexCleaningClean -v
conda run -n sca pytest tests/test_verifier.py -v

# 完整覆盖率
conda run -n sca pytest tests/ --cov=. --cov-report=term-missing
```
