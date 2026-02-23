<!-- Generated: 2026-02-20 | Files scanned: requirements.txt + config.py | Token estimate: ~350 -->

# 外部依赖与集成

## Python 包依赖（requirements.txt）

```
openai       # LLM API 客户端（兼容 DeepSeek）
requests     # HTTP 客户端（OCR API 调用）
tqdm         # 进度条（批量处理）
```

**Conda 环境**: `sca` (Python 3.10)

## 外部服务集成

### 1. MonkeyOCR API

**功能**: PDF → Markdown OCR 转换
**端点**: `http://localhost:7861/file/pdf_to_md`
**调用方式**:
```python
POST /file/pdf_to_md
Content-Type: multipart/form-data
├─ file: <PDF binary>
└─ response: {"markdown": "..."}
```

**部署方式**: Docker 容器
```bash
docker start monkeyocr-api
```

**超时配置**: 120 秒
**失败处理**: 返回空字符串 → 跳过文件

---

### 2. DeepSeek LLM API

**功能**: Markdown 语义清洗与重构
**端点**: `http://110.42.53.85:11081/v1/chat/completions`
**模型**: `deepseek-chat`
**调用方式**:
```python
client = OpenAI(
    api_key="sk-...",
    base_url="http://110.42.53.85:11081/v1"
)
client.chat.completions.create(
    model="deepseek-chat",
    temperature=0.1,
    max_tokens=4096,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": chunk}
    ]
)
```

**分块策略**: 按段落分块，每块 ≤ 2000 字（config.py:chunk_size）
**失败处理**: 抛异常 → 记录日志 → 阻断流程

---

## 未来依赖（Phase 2-4）

### 3. qmd + sqlite-vec

**用途**: 向量数据库（案例语义检索，按章节分库）
**本地部署**: 无需外部服务，已在 requirements.txt 中
**数据持久化**: sqlite 文件

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
| MonkeyOCR | `curl http://localhost:7861/health` | `200 OK` |
| DeepSeek LLM | `curl http://110.42.53.85:11081/v1/models` | 模型列表 |
| Docker | `docker ps \| grep monkeyocr` | 容器运行中 |

---

## 依赖风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| OCR 服务宕机 | 无法处理 PDF | 本地 Docker 重启 |
| LLM API 限流 | 清洗失败 | 添加重试机制（待实现） |
| API Key 泄露 | 费用损失 | 迁移至环境变量 |

---

## 网络拓扑

```
┌──────────────────┐
│  smart-construction-ai  │
│  (localhost)            │
└─────────┬───────────────┘
          │
    ┌─────┴────────┬──────────────┐
    │              │              │
    ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│ Docker  │  │ DeepSeek │  │ 文件系统 │
│ MonkeyOCR│  │ LLM API  │  │ data/    │
│ :7861   │  │ :11081   │  │ output/  │
└─────────┘  └──────────┘  └──────────┘
```
