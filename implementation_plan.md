# K15 实施计划：剩余 7 章撰写指南

> **任务编号**: K15
> **目标**: 为 Ch3/5/6/7/8/9/10 编写 SKILL.md 撰写指南 + 配套参考资料
> **产出位置**: `docs/knowledge_base/writing_guides/`
> **日期**: 2026-02-23

---

## 摘要

基于已完成的 3 章撰写指南（Ch1 编制依据、Ch2 工程概况、Ch4 施工安排），为剩余 7 章编写统一格式的撰写指南。每章包含 Agent 角色定义、推理链、输出格式、工程类型速查表和 Few-Shot 示例。Ch6（施工方法）因工程类型依赖性最强、最难模板化，为本任务的核心难点。

---

## 审查点

| # | 待确认项 | 影响 | 当前处理方式 |
|---|---------|------|------------|
| 1 | Ch3 人员配置识别的具体要求（PROJECT_OVERVIEW 待决策 #4） | ch03 撰写指南中人员规模匹配规则 | 按工程规模分 3 档给出推荐值，标注"需确认" |
| 2 | Ch5 的 5.3/5.4 是否属于系统功能（PROJECT_OVERVIEW 待决策 #5） | ch05 是否包含机械设备配置和劳动力安排 | 按章节规格书保留 5.3/5.4，标注为"可选生成" |
| 3 | Ch6 分工程类型模板是否与 K17 合并 | ch06 撰写指南的粒度 | K15 仅写 ch06 的通用推理框架 + 按类型检索策略；K17 负责具体分类模板内容 |
| 4 | 现场勘查报告和地质勘查报告怎么做（PROJECT_OVERVIEW 待决策 #3） | ch02/ch05 的现场条件描述 | ch05 中标注"地勘数据从用户输入获取" |

---

## 拟议变更

### 文件级变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/knowledge_base/writing_guides/ch03_施工组织机构.md` | `[NEW]` | Ch3 撰写指南 |
| `docs/knowledge_base/writing_guides/ch05_施工准备.md` | `[NEW]` | Ch5 撰写指南 |
| `docs/knowledge_base/writing_guides/ch06_施工方法.md` | `[NEW]` | Ch6 撰写指南（通用框架） |
| `docs/knowledge_base/writing_guides/ch07_质量管理.md` | `[NEW]` | Ch7 撰写指南 |
| `docs/knowledge_base/writing_guides/ch08_安全管理.md` | `[NEW]` | Ch8 撰写指南 |
| `docs/knowledge_base/writing_guides/ch09_应急预案.md` | `[NEW]` | Ch9 撰写指南 |
| `docs/knowledge_base/writing_guides/ch10_绿色施工.md` | `[NEW]` | Ch10 撰写指南 |
| `docs/knowledge_base/safety_knowledge/hazard_sources.md` | `[NEW]` | Ch8 配套参考：危险源识别库（按工程类型） |
| `docs/knowledge_base/safety_knowledge/safety_measures.md` | `[NEW]` | Ch8 配套参考：安全技术措施库 |
| `docs/knowledge_base/emergency/emergency_procedures.md` | `[NEW]` | Ch9 配套参考：应急处置措施库（按事故类型） |
| `docs/knowledge_base/organization/role_templates.md` | `[NEW]` | Ch3 配套参考：岗位职责模板库 |
| `docs/knowledge_base/quality/quality_control_points.md` | `[NEW]` | Ch7 配套参考：关键工序质量控制点 |
| `docs/knowledge_base/README.md` | `[MODIFY]` | 更新目录结构和使用场景表 |

### 不创建新参考资料的章节

| 章节 | 原因 | 复用的现有资料 |
|------|------|--------------|
| Ch5 施工准备 | 内容高度模板化 + 已有资料足够 | `engineering_data/data_requirements.md`（设备/材料清单）、`process_references/*.md`（工艺流程→反推所需设备） |
| Ch6 施工方法 | K17 专门负责分类模板 | `process_references/*.md`（已有 4 类工艺参考） |
| Ch10 绿色施工 | 已有完整量化指标 | `targets/quantified_targets.md`（四节一环保）、DOC 5 为主模板 |

---

## 每章设计方案

### Ch3 — 施工组织机构及职责

**难度**: ★★☆（中等模板化，需工程规模匹配）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网项目管理专家，熟悉项目组织架构设计 |
| 推理链 | ①识别工程规模（大/中/小型）→ ②确定组织层级（三级/二级）→ ③匹配岗位配置标准 → ④生成架构图 + 职责表 |
| 输出结构 | 3.1 项目组织架构（含 Mermaid 图）、3.2 管理人员职责（表格）、3.3 质量安全人员配置（表格） |
| 参考资料 | `[NEW] organization/role_templates.md` — 从 DOC 6/7/10 提取岗位职责模板 |
| Few-Shot | 500kV 变电站新建工程（大型）→ 含项目经理/总工/安监部/质管部/工程部 |
| 关键约束 | 组织架构图必须包含：项目经理、总工、安全/质量/技术负责人；人员配置与工程规模匹配 |

**`organization/role_templates.md` 内容规划**：

从 DOC 6（主控通信楼）和 DOC 7（主变安装）提取：
- 项目经理、副经理、总工职责（通用）
- 工程部、质管部、安监部、综合部职责（通用）
- 质检员、安全员职责（通用）
- 施工队组长职责（通用）
- 按工程规模的人员配置推荐表

---

### Ch5 — 施工准备

**难度**: ★★☆（模板化程度高）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网项目筹备专家，擅长施工前准备策划 |
| 推理链 | ①工程类型识别 → ②从 Ch6（施工方法）反推所需设备/材料 → ③匹配技术准备内容 → ④现场条件分析 |
| 输出结构 | 5.1 技术准备、5.2 材料准备（表格）、5.3 机械设备配置（表格）、5.4 劳动力安排（表格）、5.5 现场准备 |
| 参考资料 | 复用 `engineering_data/data_requirements.md` + `process_references/*.md` |
| Few-Shot | 500kV 变电站主变安装准备 → 设备清单（吊车/滤油机/真空泵）+ 材料清单（变压器油/密封垫） |
| 关键约束 | 设备清单必须与 Ch6 施工方法一致；5.3/5.4 标注为"可选生成" |
| 依赖关系 | 依赖 Ch2（工程规模）→ 推断设备/材料需求量 |

---

### Ch6 — 施工方法及工艺要求

**难度**: ★★★★（最难，强工程类型依赖）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网施工工艺专家，精通多类工程施工方法 |
| 推理链 | ①工程类型精确分类（变电土建/电气/线路塔基/设备安装/特殊作业）→ ②检索对应 `process_references/*.md` → ③组装工艺流程 → ④填充分项工程施工技术 → ⑤匹配验收标准 |
| 输出结构 | 6.1 施工工艺流程（流程图）、6.2 主要施工方法（按工程类型）、6.3 分项工程施工技术、6.4 技术措施、6.5 验收标准 |
| 参考资料 | 复用 `process_references/civil_works.md`、`electrical_install.md`、`line_tower.md`、`special_general.md` |
| Few-Shot | 变电土建（主控通信楼混凝土+钢筋+模板）→ 从 DOC 6 提取典型工艺流程 |
| 关键约束 | **工艺流程的步骤描述必须引用参考文件中的原文**（基于规范的定式）；本章仅写通用推理框架，K17 负责分工程类型的具体模板 |
| 依赖关系 | 依赖 Ch2（地质条件）→ 选择工艺方法 |

**设计说明**：
- Ch6 的 SKILL.md 定义**检索策略**而非具体内容：根据工程类型 → 路由到对应的 process_reference → 组装输出
- 4 类工程的工艺参考已在 `process_references/` 中，直接复用
- 验收标准引用 `compliance_standards/reference_standards.md` 中的对应标准

---

### Ch7 — 质量管理与控制措施

**难度**: ★★★☆（中高，需工序-质量控制点映射）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网质量管理工程师，精通质量管理体系和关键工序质量控制 |
| 推理链 | ①从 Ch6 提取关键工序清单 → ②为每个工序匹配质量控制点 → ③生成质量管理组织机构 → ④编写事前/事中/事后三阶段保证措施 |
| 输出结构 | 7.1 质量管理组织机构（含体系图）、7.2 质量保证措施（事前/事中/事后）、7.3 质量检验标准（表格）、7.4 质量工艺要求（按工程类型）、7.5 关键工序质量控制（含质量通病对策表） |
| 参考资料 | `[NEW] quality/quality_control_points.md` — 从 DOC 6/7/11 提取关键工序质量控制点和质量通病对策 |
| Few-Shot | 混凝土工程质量控制（浇筑→振捣→养护→拆模→检验）→ 质量通病对策表 |
| 关键约束 | 质量控制必须覆盖 Ch6 中所有关键工序；检验标准引用正确规范 |
| 依赖关系 | 强依赖 Ch6（施工方法）→ 质量控制点对应工序 |

**`quality/quality_control_points.md` 内容规划**：

从 DOC 6 提取：
- 质量管理组织机构主要职责表（通用模板）
- 事前/事中/事后三阶段质量保证措施（通用）
- 质量通病预测分析与对策表（按工程类型）
  - 土建类：地基承载力、混凝土蜂窝麻面、屋面渗漏、预埋件偏差
  - 电气类：接触电阻、绝缘、密封
- 质量目标量化指标（复用 `targets/quantified_targets.md`）

---

### Ch8 — 安全文明施工管理

**难度**: ★★★☆（中高，需工序-危险源映射）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网安全总监，精通危险源辨识和安全防范 |
| 推理链 | ①从 Ch6 提取施工工序 → ②为每个工序识别危险源 → ③按风险矩阵评价 → ④匹配安全技术措施 → ⑤生成文明施工+环保措施 |
| 输出结构 | 8.1 安全管理组织机构、8.2 安全技术措施、8.3 施工危险点及防范（表格）、8.4 危险源分析与风险评价（风险矩阵）、8.5 文明施工措施、8.6 环境保护措施 |
| 参考资料 | `[NEW] safety_knowledge/hazard_sources.md` + `[NEW] safety_knowledge/safety_measures.md` |
| Few-Shot | 变电土建施工危险点分析（高处坠落/物体打击/触电/坍塌/机械伤害）→ 防范措施表 |
| 关键约束 | 每个危险源必须有对应防范措施；危险源必须覆盖 Ch6 所有工序；文明施工按 7S 标准 |
| 依赖关系 | 强依赖 Ch6（施工方法）→ 危险源对应工序 |

**`safety_knowledge/hazard_sources.md` 内容规划**：

从 DOC 6/7/10 及其他样本提取：
- 通用危险源（适用所有工程）：高处坠落、物体打击、触电、机械伤害、火灾
- 变电土建特有：坍塌（基坑/模板）、混凝土浇筑烫伤
- 变电电气特有：带电作业触电、油务操作防火防爆、设备吊装
- 线路塔基特有：孔内缺氧、桩基坍孔、高空落物
- 特殊作业：有限空间中毒窒息、雨季施工滑倒/触电

**`safety_knowledge/safety_measures.md` 内容规划**：

- 安全管理组织机构职责模板（从 DOC 6 提取）
- 各类危险源的标准防范措施（对应 hazard_sources）
- 文明施工措施（复用 `targets/quantified_targets.md` 4.1-4.4 节）
- 即时环保措施（噪音/扬尘/废弃物 — 注意与 Ch10 区分）

---

### Ch9 — 应急预案与处置措施

**难度**: ★★☆（高度模板化）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网应急管理专家，负责编制各类事故应急预案 |
| 推理链 | ①从 Ch8 提取危险源/事故类型 → ②为每类事故匹配应急处置流程 → ③生成应急组织机构 → ④编写物资清单和演练计划 |
| 输出结构 | 9.1 应急组织机构与职责、9.2 应急响应程序（含流程图）、9.3 应急处置措施（按事故类型分节）、9.4 应急物资准备（表格）、9.5 应急演练计划 |
| 参考资料 | `[NEW] emergency/emergency_procedures.md` |
| Few-Shot | 触电事故应急处置（发现→断电→CPR→报告→送医）+ 物资清单（AED、急救箱、灭火器） |
| 关键约束 | 应急类型必须覆盖 Ch8 所有危险源；处置措施必须具体可操作（不能只写"立即报告"） |
| 依赖关系 | 强依赖 Ch8（危险源）→ 应急类型对应风险 |

**`emergency/emergency_procedures.md` 内容规划**：

按事故类型组织（从 DOC 6/7/10 及行业通用知识提取）：
- 触电事故处置流程
- 高处坠落事故处置流程
- 物体打击事故处置流程
- 坍塌事故处置流程
- 火灾/爆炸事故处置流程
- 中毒窒息事故处置流程（有限空间）
- 机械伤害事故处置流程
- 通用应急物资清单模板
- 应急演练计划模板（频次/内容/记录）

---

### Ch10 — 绿色施工与环境保护（可选）

**难度**: ★☆☆（高度模板化，DOC 5 为主模板）

| 维度 | 设计 |
|------|------|
| Agent 角色 | 南方电网绿色施工管理专家 |
| 推理链 | ①确认是否需要独立绿色施工章节（大型工程或有环保要求时生成）→ ②加载"四节一环保"框架 → ③从 `targets/quantified_targets.md` 提取量化指标 → ④生成各节内容 |
| 输出结构 | 10.1 绿色施工总体框架、10.2 节地与土地资源、10.3 节水与水资源、10.4 节材与材料资源、10.5 环境保护与减排、10.6 水土污染控制 |
| 参考资料 | 复用 `targets/quantified_targets.md` 第 3 节（绿色施工目标） |
| Few-Shot | 500kV 变电站绿色施工方案 → 四节一环保量化指标表 |
| 关键约束 | 本章为可选；与 Ch8.6（即时环保措施）明确区分——Ch10 是系统性绿色管理，Ch8.6 是施工过程即时措施 |

---

## 执行顺序与依赖

```
Phase A — 无前置依赖，可并行
├── ch03_施工组织机构.md  + organization/role_templates.md
├── ch05_施工准备.md      （复用已有资料）
└── ch10_绿色施工.md      （复用已有资料）

Phase B — 依赖 process_references/（已有）
└── ch06_施工方法.md      （通用推理框架，不含分类模板）

Phase C — 依赖 ch06
├── ch07_质量管理.md      + quality/quality_control_points.md
└── ch08_安全管理.md      + safety_knowledge/hazard_sources.md
                          + safety_knowledge/safety_measures.md

Phase D — 依赖 ch08
└── ch09_应急预案.md      + emergency/emergency_procedures.md
```

**建议执行方式**：Phase A 的 3 个章节并行编写 → Phase B → Phase C 的 2 个章节并行 → Phase D

---

## 统一格式规范

每个 `chXX_*.md` 撰写指南必须包含以下 6 个部分（与 ch01/ch02/ch04 对齐）：

```markdown
# ChX <章节名称> — 撰写指南

> **适用章节**：X、<标准章节名>（含子章节列表）
> **数据来源**：DOC X/Y/Z 的相关章节

---

## 1. Agent 角色定义
## 2. 推理链（必须遵循）
### Step 1: ...
### Step 2: ...
...
## 3. 输出格式（严格限制）
## 4. 工程类型 → 内容速查表（如适用）
## 5. 示例（输入 → 推理 → 输出）
## 6. 约束与注意事项
```

---

## 验证计划

### 格式验证
```bash
# 检查所有 writing_guides 文件是否存在
ls docs/knowledge_base/writing_guides/ch*.md

# 检查新建参考资料目录
ls docs/knowledge_base/safety_knowledge/
ls docs/knowledge_base/emergency/
ls docs/knowledge_base/organization/
ls docs/knowledge_base/quality/
```

### 内容验证（人工）
- [ ] 每章的子章节与 `templates/standard_50502.md` 一致
- [ ] 章节名称与 `templates/naming_conventions.md` 一致
- [ ] 每章的推理链覆盖了 `03-chapter-specification.md` 中的所有质量判据
- [ ] 依赖关系正确（Ch7 引用 Ch6 工序、Ch8 引用 Ch6 工序、Ch9 引用 Ch8 危险源）
- [ ] 参考资料数据来源标注清晰（DOC 编号 + 章节）

### 一致性检查
- [ ] 7 个撰写指南格式与已有的 ch01/ch02/ch04 一致
- [ ] `README.md` 使用场景表覆盖所有 10 章
- [ ] 无遗漏的参考资料文件

---

## 产出交付清单

| # | 产出 | 文件数 |
|---|------|-------|
| 1 | 7 个撰写指南 (`writing_guides/ch03~ch10`) | 7 |
| 2 | 岗位职责模板库 (`organization/role_templates.md`) | 1 |
| 3 | 质量控制点库 (`quality/quality_control_points.md`) | 1 |
| 4 | 危险源识别库 (`safety_knowledge/hazard_sources.md`) | 1 |
| 5 | 安全技术措施库 (`safety_knowledge/safety_measures.md`) | 1 |
| 6 | 应急处置措施库 (`emergency/emergency_procedures.md`) | 1 |
| 7 | 更新 README.md | 1 |
| **合计** | | **13 个文件** |

---

*计划编制：2026-02-23 | 基于 docs/ 全部文档分析*
