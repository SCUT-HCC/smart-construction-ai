# K22 实施计划 — LightRAG 知识图谱构建

> **任务编号**: K22
> **前置依赖**: K21（2019 实体 + 1452 关系，已完成）
> **下游消费者**: 生成系统（KnowledgeRetriever）、审核系统（ComplianceChecker）
> **核心交付物**: 可查询的 LightRAG 知识图谱实例 + 推理接口
> **技术栈**: lightrag-hku + DeepSeek API + NetworkX

---

## 摘要

将 K21 的结构化实体/关系导入 LightRAG，构建施工领域知识图谱推理引擎。
采用 LightRAG 的 `insert_custom_kg()` API 直接导入预构建的知识图谱，
提供图遍历推理接口和 LLM 增强的自然语言查询能力。

**核心推理场景**：
```
输入: "灌注桩基础" + "变电土建"
推理: 灌注桩 → 包含工序 [钻孔, 清孔, 钢筋笼下放, 混凝土灌注]
     → 每个工序的危险源 + 安全措施 + 质量要点
输出: 结构化的安全/质量要求清单
```

---

## 审查点

| # | 问题 | 默认方案 |
|---|------|---------|
| 1 | 图存储后端？ | NetworkX（轻量级，无需额外服务） |
| 2 | 向量存储？ | NanoVectorDB（LightRAG 默认，零配置） |
| 3 | 嵌入模型？ | 使用 DeepSeek API 的 embedding 端点，若不支持则用 sentence-transformers |
| 4 | 是否导入 chunks？ | 是，将关系证据文本作为 chunks 导入，支持混合检索 |

---

## 拟议变更

### 新增文件

| 文件 | 说明 | 标注 |
|------|------|------|
| `knowledge_graph/__init__.py` | 包初始化 | [NEW] |
| `knowledge_graph/__main__.py` | 入口 (`python -m knowledge_graph`) | [NEW] |
| `knowledge_graph/config.py` | LightRAG 配置（路径、LLM、嵌入） | [NEW] |
| `knowledge_graph/converter.py` | K21 数据 → LightRAG custom_kg 格式转换 | [NEW] |
| `knowledge_graph/builder.py` | 初始化 LightRAG 实例 + 导入知识图谱 | [NEW] |
| `knowledge_graph/retriever.py` | 推理查询接口（图遍历 + LLM 查询） | [NEW] |
| `tests/test_knowledge_graph.py` | 单元测试 | [NEW] |

### 修改文件

| 文件 | 说明 | 标注 |
|------|------|------|
| `requirements.txt` | 添加 lightrag-hku | [MODIFY] |

---

## 详细设计

### 1. 数据转换 (`converter.py`)

将 K21 的 `entities.json` + `relations.json` 转换为 LightRAG 的 custom_kg 格式：

```python
# K21 Entity → LightRAG entity
{
    "entity_name": entity.name,           # "混凝土浇筑"
    "entity_type": entity.type,           # "process"
    "description": build_description(entity),  # 含工程类型、属性、别名
    "source_id": entity.id,              # "process_civil_001"
}

# K21 Relation → LightRAG relationship
{
    "src_id": relation.source_entity_id,   # 实体名称（非ID，LightRAG 用名称关联）
    "tgt_id": relation.target_entity_id,
    "description": relation.evidence,
    "keywords": RELATION_TYPE_LABELS[relation.relation_type],
    "weight": relation.confidence,
    "source_id": relation.source_doc,
}
```

### 2. 构建器 (`builder.py`)

```
Step 1: 加载 K21 输出（entities.json + relations.json）
Step 2: 转换为 LightRAG custom_kg 格式
Step 3: 初始化 LightRAG（配置 LLM + 嵌入 + 存储目录）
Step 4: 调用 insert_custom_kg() 导入
Step 5: 持久化（LightRAG 自动持久化到 working_dir）
```

### 3. 推理接口 (`retriever.py`)

**图遍历推理**（不依赖 LLM，毫秒级响应）：
```python
def infer_process_chain(process_name, engineering_type) -> dict:
    """推理工序的完整要求链"""
    return {
        "equipment": [...],       # requires_equipment
        "hazards": [...],         # produces_hazard
        "safety_measures": {...}, # hazard → mitigated_by
        "quality_points": [...],  # requires_quality_check
    }
```

**LLM 增强查询**（自然语言，秒级响应）：
```python
async def query(question, mode="hybrid") -> str:
    """LightRAG 混合检索+LLM生成"""
    return await rag.aquery(question, param=QueryParam(mode=mode))
```

### 4. LLM 配置

复用项目全局 DeepSeek API 配置：
```python
async def llm_complete(prompt, system_prompt=None, **kwargs):
    return await openai_complete_if_cache(
        model="deepseek-chat",
        prompt=prompt,
        system_prompt=system_prompt,
        api_key=app_config.LLM_CONFIG["api_key"],
        base_url=app_config.LLM_CONFIG["base_url"],
    )
```

---

## 实施步骤

| 步骤 | 内容 | 前置依赖 |
|------|------|---------|
| 1 | 安装 lightrag-hku + 创建模块骨架 | 无 |
| 2 | 实现 config.py + converter.py（数据转换） | Step 1 |
| 3 | 实现 builder.py（LightRAG 初始化 + 导入） | Step 2 |
| 4 | 实现 retriever.py（图遍历 + 查询接口） | Step 3 |
| 5 | 端到端构建 + 推理测试 | Step 4 |
| 6 | 编写测试，确保覆盖率 ≥80% | Step 5 |

---

## 验证计划

### 质量验收标准

| 指标 | 目标值 | 验证方式 |
|------|--------|---------|
| KG 节点数 | ≥2000（匹配 K21 实体数） | 自动统计 |
| KG 边数 | ≥1400（匹配 K21 关系数） | 自动统计 |
| 图遍历推理 | 输入工序名→返回相关危险源和措施 | 测试用例验证 |
| LLM 查询 | 自然语言问答正确率 ≥80% | 抽样验证 5 个推理场景 |
| 测试覆盖率 | ≥80% | pytest --cov |

### 推理场景测试

1. "灌注桩施工需要哪些设备？" → 应返回 equipment 列表
2. "基坑开挖有哪些危险源？" → 应返回 hazard 列表
3. "高处坠落的安全措施有哪些？" → 应返回 safety_measure 列表
4. "混凝土浇筑的质量控制要点？" → 应返回 quality_point 列表
5. "变电土建工程的完整安全要求？" → 应返回结构化清单
