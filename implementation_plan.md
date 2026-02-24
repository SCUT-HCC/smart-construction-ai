# K18 实施计划：规范标准结构化数据库

> **任务编号**：K18
> **优先级**：P0
> **目标**：构建 JSON 格式的规范标准结构化数据库（≥30 条），含标准编号/版本/状态/年份，直接支撑审核系统的"编制依据时效性检查"（`TimelinessChecker`）
> **日期**：2026-02-24
> **前置任务**：K11（合规标准库 82 条 ✅）、K15（Ch1 撰写指南 ✅）

---

## 摘要

将现有 `reference_standards.md` 中的 82 条 Markdown 表格数据，结合 16 份清洗后文档中的实际引用和 `ch01_编制依据.md` 的标准速查表，转化为机器可读的 JSON 结构化数据库。每条记录包含标准编号、完整名称、当前版本年份、发布状态（现行/废止/已替代）、替代关系、适用工程类型等字段。产出文件直接供 Phase 4 审核系统的 `TimelinessChecker` 消费。

---

## 审查点（需确认）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **标准版本校验深度**：是否需要逐条上网查询最新版本？还是基于已有信息 + 已知替代关系即可？ | 82 条逐一查询耗时较大 | 建议：优先覆盖 ★★/★ 高频标准（~35 条做深度校验），其余记录已知版本并标注 `"verified": false` |
| 2 | **法律法规的处理**：`reference_standards.md` 中第 1 类"通用法律法规"（9 条）没有标准编号，是否纳入数据库？ | 时效性检查通常只检查带编号的标准 | 建议：纳入但标记 `type: "法律法规"`，编号字段填 `null`，`TimelinessChecker` 跳过无编号条目 |
| 3 | **输出格式**：JSON 数组 vs JSONL？ | 影响后续代码读取方式 | 建议：JSON 对象（标准数量 <100，整体加载更方便，便于人工审阅和 diff） |
| 4 | **企业标准（Q/CSG）版本查询**：南网内部标准难以公开查询 | 企标约 8 条 | 建议：使用文档引用版本，标注 `"source": "文档引用"` |

---

## 拟议变更

### 产出文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/knowledge_base/compliance_standards/standards_database.json` | `[NEW]` | 核心产出：结构化标准数据库 |
| `docs/knowledge_base/compliance_standards/README.md` | `[NEW]` | 数据库说明文档：字段定义、维护流程、集成说明 |
| `docs/knowledge_base/compliance_standards/reference_standards.md` | `[保留]` | 原 Markdown 表格保留作为人类可读版本，不修改 |
| `docs/PROJECT_OVERVIEW.md` | `[MODIFY]` | K18 状态从 🔲 更新为 ✅ |
| `docs/CODEMAPS/INDEX.md` | `[MODIFY]` | 新增 K18 完成记录 |
| `docs/CODEMAPS/data.md` | `[MODIFY]` | 新增 standards_database 数据描述 |

### 数据库 Schema 设计

```json
{
  "version": "1.0",
  "updated_at": "2026-02-24",
  "description": "南方电网施工方案编制依据时效性检查用规范标准数据库",
  "total_count": 82,
  "verified_count": 35,
  "categories": [
    "通用法律法规与综合管理",
    "电力与电网通用安全标准",
    "质量验收通用标准",
    "土建与地基基础工程",
    "原材料标准",
    "电气安装与变压器工程",
    "起重与特种设备",
    "钢结构、防腐与防火",
    "安全、绿色施工与环境管理"
  ],
  "standards": [
    {
      "id": "GB_50300_2013",
      "standard_number": "GB 50300-2013",
      "standard_prefix": "GB",
      "number_body": "50300",
      "version_year": 2013,
      "title": "建筑工程施工质量验收统一标准",
      "type": "国家标准",
      "status": "现行",
      "replaced_by": null,
      "replaces": "GB 50300-2001",
      "category": "质量验收通用标准",
      "applicable_engineering_types": ["变电土建", "线路塔基", "通用"],
      "applicable_chapters": ["ch01", "ch06", "ch07"],
      "citation_frequency": "★★",
      "verified": true,
      "source": "国标委官网",
      "notes": null
    }
  ]
}
```

### 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识，格式 `{前缀}_{编号}_{年份}`，如 `GB_50300_2013`；法律法规用 `LAW_安全生产法` |
| `standard_number` | string/null | ✅ | 完整标准编号，如 `GB 50300-2013`；法律法规填 `null` |
| `standard_prefix` | string | ✅ | 标准类别前缀：`GB`/`GB/T`/`DL`/`DL/T`/`JGJ`/`JGJ/T`/`Q/CSG`/`CECS`/`GBZ/T`/`HJ/T`/`法规`/`部门规章` |
| `number_body` | string/null | ✅ | 标准编号主体（不含前缀和年份），如 `50300`；法律法规填 `null` |
| `version_year` | int/null | ✅ | 当前版本年份；法律法规填最新修订年份或 `null` |
| `title` | string | ✅ | 标准全称 |
| `type` | enum | ✅ | `国家标准`/`推荐性国标`/`行业标准`/`推荐性行标`/`企业标准`/`法律法规`/`部门规章`/`协会标准` |
| `status` | enum | ✅ | `现行`/`废止`/`已替代`/`待查` |
| `replaced_by` | string/null | — | 如已废止/替代，填新标准完整编号 |
| `replaces` | string/null | — | 本标准替代的旧标准编号 |
| `category` | string | ✅ | 归属类别（对应 `reference_standards.md` 的 9 大分类 + 附录） |
| `applicable_engineering_types` | string[] | ✅ | 适用工程类型：`变电土建`/`变电电气`/`线路塔基`/`设备安装`/`涂装工程`/`专题方案`/`绿色施工`/`通用` |
| `applicable_chapters` | string[] | ✅ | 适用章节：`ch01`~`ch10` |
| `citation_frequency` | string | ✅ | 引用频率：`★★`(核心必引) / `★`(高频) / `—`(低频) |
| `verified` | bool | ✅ | 是否已人工核实当前版本为最新 |
| `source` | string | — | 版本信息来源：`国标委官网`/`工标网`/`文档引用`/`待查` |
| `notes` | string/null | — | 备注（废止原因、特殊说明等） |

---

## 执行步骤

### Phase 1：数据提取与初始化

**步骤 1.1**：从 `reference_standards.md` 解析 82 条记录

手工将 9 个分类表格 + 2 个附录中的所有条目转化为 JSON：
- 从表格中提取 `standard_number`、`title`、`citation_frequency`
- 自动推导 `standard_prefix`、`number_body`、`version_year`（从编号中的年份部分）
- 按表格所在分类填充 `category`
- 根据前缀推导 `type`（GB→国家标准、GB/T→推荐性国标、DL→行业标准、Q/CSG→企业标准等）
- 初始状态标记为 `"status": "待查"`, `"verified": false`

**步骤 1.2**：补充 `applicable_engineering_types` 和 `applicable_chapters`

交叉参考以下数据源：
- `ch01_编制依据.md` 第 4 节的工程类型→标准速查表（4.1 变电土建 / 4.2 变电电气 / 4.3 线路土建 / 4.4 设备安装 / 4.5 特殊专项）
- `ch06_templates/` 中各模板的验收标准章节
- `03-chapter-specification.md` 中各章的"质量判据"引用的标准

**步骤 1.3**：生成唯一 `id`

规则：
- 有标准编号：`{prefix}_{number_body}_{year}`，斜杠替换为下划线，如 `GB/T 50784-2013` → `GB_T_50784_2013`
- 法律法规：`LAW_{简称}`，如 `LAW_安全生产法`
- 企业标准：`Q_CSG_{编号}_{year}`

### Phase 2：版本校验（核心工作）

**步骤 2.1**：核心标准深度校验（目标 ≥35 条）

优先校验 `citation_frequency` 为 ★★ 的核心必引标准（约 15 条）+ ★ 高频标准（约 20 条）：

已知的重要版本更替（预填充）：

| 旧版 | 新版 | 说明 |
|------|------|------|
| GB 50300-2001 | GB 50300-2013 | 建筑工程施工质量验收统一标准 |
| GB 50204-2002 | GB 50204-2015 | 混凝土结构施工质量验收 |
| GB 175-2007 | GB 175-2020 | 通用硅酸盐水泥 |
| GB 1499.2-2007 | GB 1499.2-2018 | 热轧带肋钢筋 |
| GB 50205-2001 | GB 50205-2020 | 钢结构工程施工质量验收 |
| GB 8923-88 | GB/T 8923.1-2011 | 涂装前钢材表面处理 |
| GB 8978-1996 | GB 8978-2002 | 污水综合排放标准 |
| JGJ 52-2006 | JGJ 52-2006 | 待核实是否有新版 |
| GB 50254~50259-96 | 已拆分为多个独立标准 | 特殊情况，需备注说明 |

校验来源（按优先级）：
1. 国家标准全文公开系统 (openstd.samr.gov.cn)
2. 工标网 / 标准信息服务平台
3. 16 份文档中引用的实际版本号交叉验证

**步骤 2.2**：标注校验结果

对每条已校验标准更新：
- `status` → `现行` / `废止` / `已替代`
- `replaced_by` / `replaces` 替代关系
- `verified` → `true`
- `source` → 实际查询来源

**步骤 2.3**：其余标准基本标注

对未深度校验的标准（约 47 条）：
- 使用 `reference_standards.md` 中已有的版本年份
- 标记 `"verified": false`, `"source": "文档引用"`
- `status` 标记为 `"待查"`（除非有明确信息）

### Phase 3：数据组装与质量验证

**步骤 3.1**：组装最终 JSON 文件

- 按 `category` 分组排列，组内按 `citation_frequency` 降序
- 计算并填充顶层元数据：`total_count`、`verified_count`
- 确保 JSON 格式正确（UTF-8 编码，缩进 2 空格）

**步骤 3.2**：数据完整性检查

- [ ] 总条目数 ≥ 82（覆盖 `reference_standards.md` 全部 82 条 + 附录 2 条）
- [ ] 已校验条目数 ≥ 30（满足 K18 最低要求）
- [ ] 所有必填字段无 `undefined` 或空值
- [ ] `standard_number` 格式统一
- [ ] `id` 全局唯一
- [ ] `status` 取值仅为 `现行`/`废止`/`已替代`/`待查`
- [ ] 所有 `citation_frequency: "★★"` 的标准均已 `verified: true`
- [ ] `applicable_engineering_types` 无空数组
- [ ] `applicable_chapters` 至少包含 `ch01`

**步骤 3.3**：审核系统兼容性验证

确保数据格式满足 `07-review-system.md` 中 `TimelinessChecker` 的预期查询模式：

```python
# TimelinessChecker 预期使用方式（伪代码）
db = json.load("standards_database.json")
index = {s["number_body"]: s for s in db["standards"] if s["number_body"]}

for cited in extract_citations(document_chapter1):
    # cited = {"prefix": "GB", "number": "50204", "year": 2002}
    match = index.get(cited["number"])
    if match:
        if match["version_year"] and cited["year"] < match["version_year"]:
            report.add_warning(
                f"⚠️ {cited['prefix']} {cited['number']}-{cited['year']}"
                f" → 已替代为 {match['standard_number']}"
            )
        if match["status"] == "废止":
            report.add_error(f"🔴 {match['standard_number']} 已废止")
```

关键设计点：
- `number_body` 作为查询主键（同一标准不同版本 number_body 相同）
- `version_year` 用于版本比较
- `status` 用于废止标准告警

### Phase 4：文档编写

**步骤 4.1**：编写 `compliance_standards/README.md`

内容：
1. 数据库用途与适用范围
2. 文件说明（standards_database.json vs reference_standards.md）
3. 字段定义与取值说明
4. 数据来源与校验方法
5. 维护指南：如何新增/更新/废止标准
6. 与审核系统的集成说明（TimelinessChecker 接口）
7. 统计摘要（按类别/状态/校验状态分布）

**步骤 4.2**：更新项目文档

- `PROJECT_OVERVIEW.md`：K18 状态 🔲 → ✅
- `CODEMAPS/INDEX.md`：新增 K18 完成记录
- `CODEMAPS/data.md`：新增 standards_database.json 数据描述

---

## 验证计划

```bash
# 1. JSON 格式校验 + 基本统计
conda run -n sca python -c "
import json
with open('docs/knowledge_base/compliance_standards/standards_database.json', encoding='utf-8') as f:
    db = json.load(f)
print(f'版本: {db[\"version\"]}')
print(f'总条目: {db[\"total_count\"]}')
print(f'已校验: {db[\"verified_count\"]}')
standards = db['standards']
assert len(standards) == db['total_count'], f'条目数不一致: {len(standards)} vs {db[\"total_count\"]}'
assert db['total_count'] >= 30, f'条目数不足 30: {db[\"total_count\"]}'
assert db['verified_count'] >= 30, f'校验数不足 30: {db[\"verified_count\"]}'
print('基本校验通过 ✅')
"

# 2. 必填字段完整性检查
conda run -n sca python -c "
import json
REQUIRED = ['id','standard_number','standard_prefix','number_body','title',
            'type','status','category','applicable_engineering_types',
            'applicable_chapters','citation_frequency','verified']
with open('docs/knowledge_base/compliance_standards/standards_database.json', encoding='utf-8') as f:
    db = json.load(f)
errors = []
for s in db['standards']:
    for field in REQUIRED:
        if field not in s:
            errors.append(f'{s.get(\"id\",\"?\")} 缺少字段 {field}')
if errors:
    for e in errors:
        print(f'❌ {e}')
else:
    print(f'所有 {len(db[\"standards\"])} 条记录必填字段完整 ✅')
"

# 3. ID 唯一性检查
conda run -n sca python -c "
import json
from collections import Counter
with open('docs/knowledge_base/compliance_standards/standards_database.json', encoding='utf-8') as f:
    db = json.load(f)
ids = [s['id'] for s in db['standards']]
dupes = [id for id, cnt in Counter(ids).items() if cnt > 1]
assert not dupes, f'重复 ID: {dupes}'
print(f'所有 {len(ids)} 个 ID 唯一 ✅')
"

# 4. 核心标准校验覆盖率
conda run -n sca python -c "
import json
with open('docs/knowledge_base/compliance_standards/standards_database.json', encoding='utf-8') as f:
    db = json.load(f)
core = [s for s in db['standards'] if s['citation_frequency'] in ('★★', '★★★')]
verified_core = [s for s in core if s['verified']]
print(f'核心标准(★★+): {len(core)} 条')
print(f'其中已校验: {len(verified_core)} 条')
not_verified = [s['id'] for s in core if not s['verified']]
if not_verified:
    print(f'⚠️ 未校验的核心标准: {not_verified}')
print('校验覆盖率检查完成')
"

# 5. 状态分布统计
conda run -n sca python -c "
import json
from collections import Counter
with open('docs/knowledge_base/compliance_standards/standards_database.json', encoding='utf-8') as f:
    db = json.load(f)
status_dist = Counter(s['status'] for s in db['standards'])
type_dist = Counter(s['type'] for s in db['standards'])
cat_dist = Counter(s['category'] for s in db['standards'])
print('=== 状态分布 ===')
for k, v in status_dist.most_common():
    print(f'  {k}: {v}')
print('=== 类型分布 ===')
for k, v in type_dist.most_common():
    print(f'  {k}: {v}')
print('=== 类别分布 ===')
for k, v in cat_dist.most_common():
    print(f'  {k}: {v}')
"

# 6. README 存在性检查
ls -la docs/knowledge_base/compliance_standards/README.md
```

---

## 依赖与风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 国标委官网查询受限/缓慢 | 中 | 版本校验效率低 | 使用已知替代关系预填充 + 多数据源交叉验证 |
| 企业标准（Q/CSG）版本无法公开查询 | 高 | 8 条企标版本不确定 | 标注 `"source": "文档引用"`, `"verified": false` |
| 部分标准存在多个平行版本（如 GB 50254~50259-96 合并拆分） | 低 | 状态标注困难 | 在 `notes` 中详细说明特殊情况 |
| 标准版本信息过时（查询时间点限制） | 低 | 数据库上线后可能已有新版 | README 中说明维护周期（建议半年更新一次） |

---

## 与后续任务的关系

| 下游任务 | 依赖方式 | 说明 |
|---------|---------|------|
| **K19** 章节标题映射规则 | 无直接依赖 | 可共享标准编号正则模式 |
| **S17** TimelinessChecker | **强依赖** | 直接消费 `standards_database.json` 做版本比对 |
| **S18** ComplianceChecker | 间接依赖 | 引用标准的有效性验证 |
| **Ch1 生成 Agent** | 间接依赖 | 标准选择时参考数据库确保引用最新版本 |

---

## 产出验收标准

| 维度 | 指标 | 阈值 |
|------|------|------|
| 数据量 | 总条目数 | ≥ 82 条（完整覆盖 `reference_standards.md`） |
| 校验覆盖 | 已校验条目数 | ≥ 30 条（所有核心标准） |
| 格式合规 | JSON 可解析 | `json.load()` 无报错 |
| 字段完整 | 必填字段覆盖率 | 100% |
| ID 唯一性 | 无重复 ID | 0 重复 |
| 审核兼容 | 支持 TimelinessChecker 查询 | 通过 number_body 索引测试 |
| 文档配套 | README 完整 | 包含字段定义 + 维护指南 + 集成说明 |

---

*计划编制：2026-02-24 | 基于 docs/ 全部文档 + reference_standards.md 82 条数据分析*
