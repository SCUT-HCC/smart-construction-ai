<!-- Generated: 2026-02-23 | Files scanned: requirements.txt + config.py | Token estimate: ~350 -->

# 外部依赖与集成

## Python 包依赖（requirements.txt）

**核心包**:
```
openai==2.21.0       # LLM API 客户端（兼容 DeepSeek）
requests==2.32.5     # HTTP 客户端（OCR API 调用）
tqdm==4.67.3         # 进度条（批量处理）
python-dotenv==1.2.1 # 环境变量管理
```

**未来依赖**:
```
qmd==0.1.0           # 向量数据库（Phase 2+）
sqlite-vec==0.1.6    # SQLite 向量扩展（Phase 2+）
```

**其他依赖**:
- pydantic, PyYAML, typing-extensions（数据验证与配置）
- httpx, httpcore（HTTP 基础库）
- 标准库 logging（日志，已移除 loguru）

**Conda 环境**: `sca` (Python 3.10)

**最近变更**:
- 移除 loguru 和 watchdog 僵尸依赖（commit d92dcf0）
- 添加 python-dotenv 用于 .env 配置（commit 49f1379）

---

## 外部服务集成

### 1. MonkeyOCR API

**功能**: PDF → Markdown OCR 转换

**端点**: `http://localhost:7861/parse`

**调用方式**:
```python
POST /parse
Content-Type: multipart/form-data
├─ file: <PDF binary>
└─ response: {
    "success": true,
    "download_url": "/download/task_id.zip"
   }

GET /download/task_id.zip → 返回 ZIP 文件
└─ 包含: document.md（Markdown 文本）
```

**部署方式**: Docker 容器
```bash
docker start monkeyocr-api
```

**超时配置**: 120 秒（config.py:17）

**失败处理**:
- 网络异常 → 返回空字符串 → 跳过该文件
- ZIP 解析失败 → 返回空字符串 → 跳过该文件

**调用位置**: `crawler.py:MonkeyOCRClient.to_markdown()`

---

### 2. DeepSeek LLM API

**功能**: Markdown 语义清洗与重构

**端点**: `http://110.42.53.85:11081/v1/chat/completions`

**模型**: `deepseek-chat`（config.py:9）

**调用方式**:
```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-...",
    base_url="http://110.42.53.85:11081/v1"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    temperature=0.1,
    max_tokens=4096,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": chunk}
    ]
)
```

**分块策略**: 按段落分块，每块 ≤ 2000 字（config.py:12）

**失败处理**: 抛异常 → 记录 ERROR → 阻断流程

**调用位置**: `cleaning.py:LLMCleaning.clean()`

**环境变量配置**:
```bash
export SCA_LLM_API_KEY="sk-..."
export SCA_LLM_BASE_URL="http://110.42.53.85:11081/v1"
export SCA_LLM_MODEL="deepseek-chat"  # 可选，默认 deepseek-chat
```

---

## 未来依赖（Phase 2-4）

### 3. qmd + sqlite-vec

**用途**: 向量数据库（案例语义检索，按章节分库）

**特点**:
- 本地部署：无需外部服务
- 数据持久化：SQLite 文件
- 向量维度：1536-dim（OpenAI text-embedding-3-small）

---

### 4. LangChain + LangGraph

**LangChain**: 工具链封装（Prompt、Chain、Memory）

**LangGraph**: 多智能体编排（检测 Agent + 生成 Agent）

**依赖**:
```
langchain
langchain-openai
langgraph
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
| OCR 服务宕机 | 无法处理 PDF | 本地 Docker 重启；实现本地 OCR 备方案 |
| LLM API 限流 | 清洗失败 | 添加重试机制（待实现）；调整分块策略 |
| API Key 泄露 | 费用损失 + 安全风险 | 使用环境变量而非硬编码（已实现） |
| 网络不稳定 | 处理失败 | 重试机制待实现 |
| 模型版本变更 | 输出质量下降 | 监控模型性能；定期更新 system prompt |

---

## 网络拓扑

```
┌──────────────────────────────────┐
│  smart-construction-ai           │
│  (localhost)                      │
└─────────────┬──────────────────────┘
              │
       ┌──────┼──────────────┬──────────────┐
       │      │              │              │
       ▼      ▼              ▼              ▼
    ┌─────┐ ┌────────┐  ┌──────────┐  ┌──────────────┐
    │文件 │ │Docker  │  │ DeepSeek │  │文件系统      │
    │系统 │ │MonkeyO │  │ LLM API  │  │(output/     │
    │data/│ │CR API  │  │ :11081   │  │task_log.json)│
    │     │ │:7861   │  │          │  │              │
    └─────┘ └────────┘  └──────────┘  └──────────────┘
```

---

## 依赖版本管理

**更新策略**:
- openai: 跟踪官方更新（目前 2.21.0 支持 API 兼容模式）
- requests: 保持稳定版本（2.32.5）
- 其他: 仅在必要时更新

**测试流程**:
```bash
# 1. 更新依赖版本
pip install --upgrade <package>

# 2. 运行单文件快速测试
conda run -n sca python main.py --input data/7.pdf --output test_tmp

# 3. 清理
rm -rf test_tmp
```
