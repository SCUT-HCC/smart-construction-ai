# 施工方案知识库 (Knowledge Base)

> 本知识库基于 16 份南方电网实际施工方案（重点参考 DOC 4/6/7/10/11/12 等高质量样本）系统梳理而成，
> 供施工方案生成系统 (Generation Agent) 和审核系统 (Review Agent) 调用。

---

## 目录结构

```
docs/knowledge_base/
├── README.md                          ← 本文件（索引与导航）
│
├── writing_guides/                    # 撰写指南（10 章全覆盖）
│   ├── ch01_编制依据.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch02_工程概况.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch03_施工组织机构.md          # Agent 角色 + 推理链 + 输出模板
│   ├── ch04_施工安排.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch05_施工准备.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch06_施工方法.md              # Agent 角色 + 推理链 + 检索路由框架
│   ├── ch06_templates/               # Ch6 分工程类型模板（K17 产出）
│   │   ├── README.md                 # 导航索引 + 子类型映射 + 格式规范
│   │   ├── civil_works_template.md   # 变电土建（混凝土+钢筋+模板+强夯+防水+砌体+给排水）
│   │   ├── electrical_install_template.md  # 变电电气（主变+建筑电气+防雷接地+吊装）
│   │   ├── line_tower_template.md    # 线路塔基（挖孔桩+灌注桩+钢结构屋面）
│   │   └── special_general_template.md     # 特殊/通用（防腐防火+雨季+有限空间+起重）
│   ├── ch07_质量管理.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch08_安全管理.md              # Agent 角色 + 推理链 + 输出模板
│   ├── ch09_应急预案.md              # Agent 角色 + 推理链 + 输出模板
│   └── ch10_绿色施工.md              # Agent 角色 + 推理链 + 输出模板（可选章节）
│
├── compliance_standards/              # 合规标准库
│   └── reference_standards.md         # 9 大类 80+ 条国标/行标/企标
│
├── engineering_data/                  # 工程数据需求清单
│   └── data_requirements.md           # 6 类工程 × 必需数据字段 + 真实参数范围
│
├── targets/                           # 目标量化指标
│   └── quantified_targets.md          # 质量 / 安全 / 绿色施工 / 文明施工
│
├── process_references/                # 工程工艺参考（4 类）
│   ├── civil_works.md                 # 变电土建（混凝土、钢筋、模板、强夯、防水）
│   ├── electrical_install.md          # 变电电气（主变安装、建筑电气、防雷接地）
│   ├── line_tower.md                  # 线路塔基（挖孔桩、灌注桩、钢结构屋面）
│   └── special_general.md             # 特殊/通用（雨季、有限空间、防腐防火、起重吊装）
│
├── organization/                      # 组织架构与岗位职责
│   └── role_templates.md              # 标准组织架构 + 10 个关键岗位职责模板
│
├── quality/                           # 质量管理参考
│   └── quality_control_points.md      # 质量控制点 + 通病防治 + 成品保护
│
├── safety_knowledge/                  # 安全管理参考
│   ├── hazard_sources.md              # 危险源辨识与风险评估（按工程类型分类）
│   └── safety_measures.md             # 安全保证措施 + 文明施工 + 环保措施
│
└── emergency/                         # 应急管理参考
    └── emergency_procedures.md        # 8 类事故处置程序 + 物资清单 + 演练要求
```

---

## 使用场景

| 场景 | 入口文件 | 说明 |
|------|---------|------|
| 生成 Ch1 编制依据 | `writing_guides/ch01_编制依据.md` → `compliance_standards/reference_standards.md` | 先读指南确定推理链，再从标准库检索匹配标准 |
| 生成 Ch2 工程概况 | `writing_guides/ch02_工程概况.md` → `engineering_data/data_requirements.md` | 先读指南确定数据结构，再按工程类型填充参数表 |
| 生成 Ch3 施工组织 | `writing_guides/ch03_施工组织机构.md` → `organization/role_templates.md` | 按工程规模选择架构模板，检索岗位职责 |
| 生成 Ch4 施工安排 | `writing_guides/ch04_施工安排.md` → `targets/quantified_targets.md` + `process_references/*.md` | 先读指南确定框架，从目标库取指标，从工艺库取流程 |
| 生成 Ch5 施工准备 | `writing_guides/ch05_施工准备.md` → `process_references/*.md` | 从 Ch6 反推设备/材料需求，按工程类型检索清单 |
| 生成 Ch6 施工方法 | `writing_guides/ch06_施工方法.md` → `ch06_templates/*.md` → `process_references/*.md` | 先读通用框架分类，再加载对应模板确定子章节，最后检索参数 |
| 生成 Ch7 质量管理 | `writing_guides/ch07_质量管理.md` → `quality/quality_control_points.md` + `targets/quantified_targets.md` | 从 Ch6 反推质量控制点，加载量化目标 |
| 生成 Ch8 安全管理 | `writing_guides/ch08_安全管理.md` → `safety_knowledge/hazard_sources.md` + `safety_knowledge/safety_measures.md` | 从 Ch6 反推危险源，匹配安全措施 |
| 生成 Ch9 应急预案 | `writing_guides/ch09_应急预案.md` → `emergency/emergency_procedures.md` | 从 Ch8 反推事故类型，检索处置程序 |
| 生成 Ch10 绿色施工 | `writing_guides/ch10_绿色施工.md` → `targets/quantified_targets.md` | 判断是否需要本章，加载"四节一环保"框架 |
| 审核依据时效性 | `compliance_standards/reference_standards.md` | 比对方案引用的标准与最新标准库 |
| 审核章节完整性 | `engineering_data/data_requirements.md` | 检查工程概况章节数据字段是否完整 |
| 审核质量/安全指标 | `targets/quantified_targets.md` | 比对方案中的目标值是否达到最低标准 |

---

## 章节间依赖关系

```
Ch2（工程概况）──→ Ch3（组织架构：基于工程规模定人员配置）
               ──→ Ch4（施工安排：基于工程量排工期）
               ──→ Ch5（施工准备：基于工程量定设备/材料）
               ──→ Ch6（施工方法：基于工程类型选工艺）

Ch6（施工方法）──→ Ch5（设备/材料与工法一致）
               ──→ Ch7（质量控制点对应施工工序）
               ──→ Ch8（危险源对应施工工序）

Ch8（安全管理）──→ Ch9（应急类型对应风险类型）
```

> **生成顺序**：Ch1 → Ch2 → Ch3 → Ch4 → Ch5 ↔ Ch6 → Ch7 → Ch8 → Ch9 → Ch10（可选）

---

## 数据来源与质量

### 高质量参考方案（优先引用）

| 编号 | 方案类型 | 工程类别 | 特点 |
|-----|---------|---------|------|
| DOC 4 | GIS 室钢屋面楼承板 | 变电土建 | 结构清晰，工艺参数详尽 |
| DOC 6 | 主控通信楼施工方案 | 变电土建（综合） | 覆盖全面，含完整质量/安全目标 |
| DOC 7 | 主变压器安装方案 | 变电电气 | 专业深度好，油务指标完整 |
| DOC 10 | 起重机安装专项方案 | 设备安装 | 含计算书与施工风险分析 |
| DOC 11 | 填土地基强夯方案 | 地基处理 | 工艺参数量化完整 |
| DOC 12 | 灌注桩基础施工方案 | 线路土建 | 桩基参数详尽，含配合比设计 |

### 补充参考方案

| 编号 | 方案类型 | 用途 |
|-----|---------|------|
| DOC 1 | 人工挖孔桩方案 | 线路塔基工艺补充 |
| DOC 5 | 绿色施工方案 | 四节一环保量化指标 |
| DOC 8 | 雨季施工方案 | 季节性施工措施 |
| DOC 9 | 事故油池方案 | 有限空间作业补充 |
| DOC 16 | 安健环施工方案 | 7S 管理与文明施工 |

---

## 与其他文档的关系

| 文档 | 路径 | 关系 |
|------|------|------|
| 10 章节标准模板 | `templates/standard_50502.md` | 知识库的**章节框架骨架**，撰写指南据此展开 |
| 命名规范 | `templates/naming_conventions.md` | 知识库输出必须遵守的**标题命名规则** |
| 章节规格书 | `docs/architecture/03-chapter-specification.md` | 知识库的**上层设计文件**，定义每章必写内容 |
| 语料分析 | `docs/analysis/chapter_comparison_table.md` | 知识库建设的**数据基础**，16 份方案的统计分析 |
| 旧版撰写指南 | `docs/drafts/opencode_skills/` | 本知识库的**前身**，已被重写替代 |

---

*最后更新：2026-02-23 | 数据来源：16 份南方电网 500kV 电白变电站施工方案*
