# K19 实施计划：章节标题映射规则库 + ChapterMapper

> **任务编号**: K19
> **前置依赖**: K2（560 章节标题统计）、K4（10 章结构）、K16（chapter_splitter 初版映射，99.2%）
> **下游消费者**: S15（ChapterMapper）→ S16（CompletenessChecker）→ S19（ReviewCoordinator）
> **日期**: 2026-02-24

---

## 摘要

基于 K16 已验证的关键词映射规则（14 份文档 1196 片段，99.2% 准确率），构建审核系统可用的 **章节标题映射规则库**。

主要工作：
1. 对 560 个实际标题做全量映射覆盖分析，补全遗漏变体
2. 将映射规则从 `config.py` 字典升级为结构化 JSON 规则库
3. 实现独立的 `ChapterMapper` 类（三级回退：关键词 → 正则模式 → LLM 语义兜底）
4. 新增**排除规则**机制（封面、公司名、材料名等不应映射为章节）
5. 针对 16 份文档做回归测试

---

## 审查点（需确认）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | K19 是否仅产出**知识工程成果**（规则库 JSON + 文档），还是需要同步产出**可运行代码**（属于 S15）？ | 决定交付范围 | 建议：一并产出代码，规则库和 Mapper 紧密耦合，分开维护不经济 |
| 2 | LLM 语义兜底是否在本阶段实现？当前纯规则方案已达 99.2%，LLM 兜底价值在**未知文档** | 是否引入 LLM 依赖 | 建议：实现接口预留 + `NotImplementedError`，实际 LLM 调用推迟到 S15 |
| 3 | 映射是否需要支持**子章节级**（如 `7.2 质量保证措施` → Ch7）？还是仅一级标题？ | 规则库粒度 | 建议：支持，当前 ChapterSplitter 已有此逻辑（子章节继承父章节） |

---

## 现状分析

### 现有资产

| 资产 | 位置 | 内容 |
|------|------|------|
| 章节映射规则 | `knowledge_extraction/config.py:CHAPTER_MAPPING` | 10 章 × (精确 + 变体) 共 ~54 个关键词 |
| 章节分割器 | `knowledge_extraction/chapter_splitter.py` | `ChapterSplitter._map_chapter()` L1+L2 两级匹配 |
| K16 映射结果 | `extraction_report.md` | 1196 片段中 1187 成功映射（99.2%），9 个未映射 |
| 560 标题统计 | `docs/analysis/chapter_analysis_data.json` | 一级标题 560 种，出现≥2 次的仅 ~65 种 |
| 命名规范 | `templates/naming_conventions.md` | 10 章标准名称 + 禁止变体列表 |

### K16 未映射清单（9 条）

全部为**封面/公司名/文档标题**，无真实章节遗漏：

| DOC | 标题 | 原因 |
|-----|------|------|
| 9 | 广东电网能源发展有限公司 | 封面残留 |
| 9 | 500kV 电白变电站新建工程 | 封面残留 |
| 9 | 有限空间作业专项施工方案 | 文档标题 |
| 9 | 一、概述 | 宽泛标题 |
| 10 | 广东电网能源发展有限公司 | 封面残留 |
| 11 | 广东电网能源发展有限公司 | 封面残留 |
| 12 | 500kV 芝寮～回隆... | 封面残留 |
| 16 | 广东电网能源发展有限公司 | 封面残留 |
| 16 | 500kV 电白变电站新建工程 | 封面残留 |

**结论**：现有规则对**已知文档**覆盖率极高。K19 的核心价值在于：
1. 补充排除规则（封面/材料名等）
2. 为**未知文档**增强鲁棒性（更多变体关键词 + 正则 + LLM 兜底）
3. 规则库结构化（从代码字典升级为可维护的 JSON）

---

## 拟议变更

### 阶段 1：全量覆盖分析 [NEW]

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/analyze_mapping_coverage.py` | [NEW] | 分析脚本：遍历 14 份 `final.md`，逐标题运行映射，统计命中规则/未匹配/误映射 |

**交付物**：覆盖分析报告，包含：

```
覆盖分析报告
━━━━━━━━━━━━━━━
总片段数: 1196 (14 份文档)
L1 精确命中: XXX (XX.X%)
L2 变体命中: XXX (XX.X%)
未映射: 9 (0.8%)
  - 封面/公司名: 7
  - 文档标题: 1
  - 宽泛标题: 1

歧义标题 (命中但可能误映射):
  - "施工" → 命中 Ch5(施工准备)，但可能属于 Ch6
  - "质量" → 命中 Ch7，但语境可能是验收标准

各章命中分布:
  Ch1 编制依据: XXX 片段
  ...
  Ch10 绿色施工: XXX 片段
```

### 阶段 2：映射规则库构建 [NEW + MODIFY]

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/knowledge_base/chapter_mapping/mapping_rules.json` | [NEW] | 结构化映射规则库 |
| `docs/knowledge_base/chapter_mapping/README.md` | [NEW] | 规则库使用说明 |
| `knowledge_extraction/config.py` | [MODIFY] | `CHAPTER_MAPPING` 改为从 JSON 加载 |

**mapping_rules.json 设计**：

```json
{
  "version": "1.0",
  "updated": "2026-02-24",
  "description": "章节标题 → 标准10章 映射规则库",
  "source": "基于 16 份南网施工方案 560 个标题变体分析",
  "chapters": {
    "Ch1": {
      "standard_name": "一、编制依据",
      "required": true,
      "rules": [
        {
          "type": "exact",
          "keywords": ["编制依据"],
          "priority": 1,
          "evidence": "9/16 文档精确命中"
        },
        {
          "type": "variant",
          "keywords": ["编制说明", "编制目的", "编写依据"],
          "priority": 2,
          "evidence": "3/16 文档使用变体"
        },
        {
          "type": "regex",
          "patterns": ["^第[一二三四五六七八九十]+章\\s*编制"],
          "priority": 2,
          "evidence": "DOC 12/15 使用'第X章'格式"
        }
      ],
      "exclusions": ["编制单位", "编制人", "编制:"],
      "sub_section_indicators": ["法律法规", "行业标准", "设计文件", "合同"]
    },
    "Ch2": {
      "standard_name": "二、工程概况",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["工程概况"], "priority": 1, "evidence": "11/16"},
        {"type": "variant", "keywords": ["工程概述", "工程简介", "项目概况", "工程地质"], "priority": 2, "evidence": ""},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*工程概"], "priority": 2, "evidence": "DOC 12/15"}
      ],
      "exclusions": ["工程概况表"],
      "sub_section_indicators": ["工程简介", "工程规模", "地质", "参建单位", "气候"]
    },
    "Ch3": {
      "standard_name": "三、施工组织机构及职责",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["施工组织机构", "组织机构"], "priority": 1, "evidence": ""},
        {"type": "variant", "keywords": ["项目组织", "管理组织", "岗位职责", "管理人员", "管理机构", "施工管理及作业人员配备"], "priority": 2, "evidence": "DOC 11/12 使用变体"},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*施工管理及"], "priority": 2, "evidence": "DOC 11/12"}
      ],
      "exclusions": ["质检部：", "其它成员："],
      "sub_section_indicators": ["项目经理", "总工", "安全员", "质量员", "职责"]
    },
    "Ch4": {
      "standard_name": "四、施工安排与进度计划",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["施工安排", "进度计划"], "priority": 1, "evidence": ""},
        {"type": "variant", "keywords": ["施工计划", "施工工期", "工期规划", "施工组织及", "施工工期计划"], "priority": 2, "evidence": "DOC 1/15"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["工期", "进度", "里程碑", "关键节点"]
    },
    "Ch5": {
      "standard_name": "五、施工准备",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["施工准备"], "priority": 1, "evidence": "3/16"},
        {"type": "variant", "keywords": ["准备工作", "资源配置", "劳动力", "设备计划", "材料供应", "技术准备"], "priority": 2, "evidence": ""}
      ],
      "exclusions": [],
      "sub_section_indicators": ["三通一平", "材料", "设备", "劳动力", "技术交底"]
    },
    "Ch6": {
      "standard_name": "六、施工方法及工艺要求",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["施工方法", "施工工艺", "工艺要求"], "priority": 1, "evidence": ""},
        {"type": "variant", "keywords": ["施工技术", "施工措施", "主要工序", "施工方案概述", "施工工艺技术", "施工技术措施", "基础施工", "安装施工", "工艺流程", "操作"], "priority": 2, "evidence": ""},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*(施工工艺|灌注桩|基础)"], "priority": 2, "evidence": "DOC 12/15"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["混凝土", "钢筋", "浇筑", "吊装", "强夯", "喷涂"]
    },
    "Ch7": {
      "standard_name": "七、质量管理与控制措施",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["质量管理", "质量控制"], "priority": 1, "evidence": ""},
        {"type": "variant", "keywords": ["质量工艺", "质量保证", "质量检验", "质量通病", "成品保护", "验收标准", "施工质量控制"], "priority": 2, "evidence": "5/16"},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*验收"], "priority": 2, "evidence": "DOC 11/12"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["检验", "验收", "合格率", "质量保证体系"]
    },
    "Ch8": {
      "standard_name": "八、安全文明施工管理",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["安全管理", "安全措施", "安全技术"], "priority": 1, "evidence": "4/16"},
        {"type": "variant", "keywords": ["安全文明", "文明施工", "危险源", "安健环", "安全风险", "安全组织", "现场安全", "临时用电", "安全用电", "安全检查", "监测监控", "安全生产", "安全管理制度"], "priority": 2, "evidence": ""},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*(安全|施工保证)"], "priority": 2, "evidence": "DOC 11/12/15"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["安全带", "防护栏", "安全网", "监护", "危险源"]
    },
    "Ch9": {
      "standard_name": "九、应急预案与处置措施",
      "required": true,
      "rules": [
        {"type": "exact", "keywords": ["应急预案", "应急处置"], "priority": 1, "evidence": "4/16"},
        {"type": "variant", "keywords": ["应急措施", "应急响应", "应急救援工作程序", "应急物资准备", "事故处置", "事故应急"], "priority": 2, "evidence": ""},
        {"type": "regex", "patterns": ["^第[一二三四五六七八九十]+章\\s*应急"], "priority": 2, "evidence": "DOC 11/12/15"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["触电", "坍塌", "火灾", "高处坠落", "中毒"]
    },
    "Ch10": {
      "standard_name": "十、绿色施工与环境保护",
      "required": false,
      "rules": [
        {"type": "exact", "keywords": ["绿色施工", "环境保护"], "priority": 1, "evidence": "3/16"},
        {"type": "variant", "keywords": ["环保措施", "水土保护", "季节性施工", "环境因素", "绿色施工目标", "四节一环保", "绿色施工技术", "环境因素分析"], "priority": 2, "evidence": "DOC 5 为专题"}
      ],
      "exclusions": [],
      "sub_section_indicators": ["节水", "节材", "节地", "扬尘", "噪音"]
    }
  },
  "global_exclusions": {
    "cover_patterns": ["广东电网", "有限公司", "500kV", "新建工程", "施工方案$"],
    "admin_patterns": ["目录", "报审表", "报验表"],
    "short_generic": ["概述", "施工", "质量", "安全", "应急", "砂", "碎石", "水"]
  },
  "statistics": {
    "total_titles_tested": 1196,
    "l1_exact_hits": "待填",
    "l2_variant_hits": "待填",
    "unmapped": 9,
    "coverage_rate": "99.2%",
    "test_date": "2026-02-24"
  }
}
```

**规则扩展要点**（基于 560 标题分析）：

| 章节 | 现有关键词 | 新增关键词 | 新增来源 |
|------|-----------|-----------|---------|
| Ch3 | 7 | +2: "施工管理及作业人员配备"、"安健环施工管理组织机构" | DOC 11/12/16 |
| Ch4 | 6 | +1: "施工工期计划" | DOC 1/15 |
| Ch5 | 6 | +1: "技术准备"（已在 variant 中） | — |
| Ch6 | 8 | +2: "工艺流程"、"操作" | 多文档 |
| Ch7 | 5 | +2: "验收标准"、"施工质量控制" | DOC 11/12 |
| Ch8 | 10 | +3: "安全检查"、"监测监控"、"安全生产" | DOC 3/8 |
| Ch9 | 4 | +3: "应急救援工作程序"、"应急物资准备"、"事故处置" | DOC 10/11 |
| Ch10 | 4 | +3: "绿色施工目标"、"四节一环保"、"环境因素分析" | DOC 5 |

**新增排除规则机制**（现有系统缺失）：

| 排除类型 | 示例 | 说明 |
|---------|------|------|
| 封面残留 | "广东电网能源发展有限公司" | 占未映射 9 条中的 7 条 |
| 材料名 | "砂"、"碎石"、"水" | 短标题，不是章节 |
| 签字栏 | "质检部："、"其它成员：" | 组织结构残留 |
| 宽泛标题 | "概述"、"施工" | 单独出现时信息量不足，需特殊处理 |

### 阶段 3：ChapterMapper 实现 [NEW]

| 文件 | 操作 | 说明 |
|------|------|------|
| `review/__init__.py` | [NEW] | 审核系统模块初始化 |
| `review/chapter_mapper.py` | [NEW] | ChapterMapper 类 |

**类设计**：

```python
@dataclass
class MappingResult:
    """单个标题的映射结果。"""
    original_title: str          # 原始标题
    chapter_id: str              # "Ch1"-"Ch10" | "unmapped" | "excluded"
    chapter_name: str            # "一、编制依据" 等
    confidence: float            # 0.0-1.0
    match_type: str              # "exact" | "variant" | "regex" | "inherited" | "excluded"
    matched_keyword: str         # 命中的关键词/模式

class ChapterMapper:
    """章节标题映射器 — 将实际标题映射到标准10章结构。

    三级回退策略：
      L1 精确匹配（confidence=1.0）
      L2 变体 + 正则匹配（confidence=0.8）
      L3 (预留) LLM 语义兜底（confidence=0.6）

    + 排除规则：封面/公司名/材料名 → "excluded"
    + 子章节继承：深层级标题继承父章节
    """

    def __init__(self, rules_path: str = None):
        """加载映射规则库。"""

    def map_title(self, title: str) -> MappingResult:
        """映射单个标题。"""

    def map_document(
        self, sections: List[Tuple[str, int]]
    ) -> List[MappingResult]:
        """映射整篇文档的标题列表（含子章节继承逻辑）。

        Args:
            sections: [(标题, 层级), ...]

        Returns:
            逐标题的映射结果列表
        """

    def get_coverage_report(
        self, results: List[MappingResult]
    ) -> Dict[str, Any]:
        """生成覆盖率统计报告。"""
```

**与现有 ChapterSplitter 的关系**：

```
knowledge_extraction/chapter_splitter.py (K16, 已完成)
  └── ChapterSplitter._map_chapter()     ← 内联映射，切分+映射一体
      └── 引用 config.py:CHAPTER_MAPPING  ← 关键词字典

review/chapter_mapper.py (K19, 本次新增)
  └── ChapterMapper                       ← 独立映射模块
      └── 加载 mapping_rules.json         ← 结构化规则库
      └── 新增排除规则、置信度、正则匹配
      └── 新增 LLM 兜底接口（预留）
```

- 两者**共用同一份规则数据**（JSON），但 `ChapterMapper` 功能更丰富
- `config.py:CHAPTER_MAPPING` 改为从 JSON 加载，保持 `ChapterSplitter` 向后兼容
- 长期看，`ChapterSplitter._map_chapter()` 可逐步迁移到调用 `ChapterMapper`

### 阶段 4：测试 [NEW]

| 文件 | 操作 | 说明 |
|------|------|------|
| `tests/test_chapter_mapper.py` | [NEW] | ChapterMapper 单元测试 + 回归测试 |

**测试用例矩阵**：

| 类别 | 用例数 | 说明 |
|------|--------|------|
| 标准名称精确匹配 | 10 | 每章一个标准名称，confidence=1.0 |
| 禁止变体映射 | 20+ | `naming_conventions.md` 中列出的所有"禁止使用"变体 |
| 带前缀匹配 | 15 | "第X章"、"一、"、"1." 三种编号风格 |
| 子章节继承 | 8 | "7.2 质量保证措施" → Ch7, "8.3 危险源" → Ch8 |
| 排除规则 | 10 | 封面、公司名、材料名、签字栏 → "excluded" |
| 宽泛标题 | 5 | "概述"、"施工" 单独出现 → unmapped 或 inherited |
| 正则匹配 | 5 | "第五章 灌注桩基础施工技术" → Ch6 |
| 回归：K16 全量 | 1196 | 与 K16 结果对比，无退化 |
| **合计** | **~75** | |

**目标指标**：

| 指标 | 阈值 |
|------|------|
| 已知文档覆盖率 | ≥ 99.2%（与 K16 持平） |
| 误映射率 | < 1% |
| 排除规则正确率 | 100%（封面等全部排除） |
| 测试通过率 | 100% |

---

## 文件变更总结

| # | 文件路径 | 操作 | 行数估计 |
|---|---------|------|---------|
| 1 | `scripts/analyze_mapping_coverage.py` | [NEW] | ~120 |
| 2 | `docs/knowledge_base/chapter_mapping/mapping_rules.json` | [NEW] | ~280 |
| 3 | `docs/knowledge_base/chapter_mapping/README.md` | [NEW] | ~80 |
| 4 | `knowledge_extraction/config.py` | [MODIFY] | ~15 行变更（加载 JSON） |
| 5 | `review/__init__.py` | [NEW] | ~5 |
| 6 | `review/chapter_mapper.py` | [NEW] | ~220 |
| 7 | `tests/test_chapter_mapper.py` | [NEW] | ~280 |

**总新增**: ~1000 行（含测试 280 + JSON 280 + 代码 220 + 脚本 120 + 文档 80）

---

## 验证计划

```bash
# 1. 运行覆盖分析脚本
conda run -n sca python scripts/analyze_mapping_coverage.py

# 2. 运行 ChapterMapper 单元测试
conda run -n sca pytest tests/test_chapter_mapper.py -v

# 3. 全量回归：16 份文档
conda run -n sca python -c "
from review.chapter_mapper import ChapterMapper
from knowledge_extraction.chapter_splitter import ChapterSplitter
from knowledge_extraction.config import DOCS_TO_PROCESS, INPUT_PATH_TEMPLATE

mapper = ChapterMapper()
splitter = ChapterSplitter()
total, matched = 0, 0
for doc_id in DOCS_TO_PROCESS:
    path = INPUT_PATH_TEMPLATE.format(doc_id=doc_id)
    with open(path) as f:
        content = f.read()
    sections = splitter._split_by_headers(content)
    titles = [(t, l) for t, _, l in sections]
    results = mapper.map_document(titles)
    for r in results:
        total += 1
        if r.chapter_id not in ('unmapped',):
            matched += 1
print(f'总片段: {total}, 映射成功+排除: {matched}, 覆盖率: {matched/total*100:.1f}%')
"

# 4. 代码质量
conda run -n sca ruff check review/ scripts/analyze_mapping_coverage.py tests/test_chapter_mapper.py
conda run -n sca ruff format --check review/ scripts/ tests/test_chapter_mapper.py
```

**预期输出**：

| 检查项 | 预期 |
|--------|------|
| 覆盖分析 | L1+L2 命中率 ≥ 99%，未映射仅剩封面/宽泛标题 |
| 单元测试 | 全部通过，≥ 75 个用例 |
| 全量回归 | 覆盖率 ≥ 99.2%（不退化） |
| ruff | 0 errors, 0 warnings |

---

## 执行顺序

```
阶段 1（覆盖分析）→ 阶段 2（规则库 JSON）→ 阶段 3（ChapterMapper 代码）→ 阶段 4（测试）
     ↓                    ↓                        ↓
 发现遗漏变体        补全规则+排除列表         加载 JSON + 三级回退
```

阶段 1 的分析结果直接决定阶段 2 需要补充哪些规则；阶段 3 依赖阶段 2 的 JSON；阶段 4 覆盖所有。

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| "操作"、"工艺流程" 等宽泛关键词引入误映射 | 精确率下降 | 每条新规则必须附带排除条件 + 测试用例 |
| 新增正则模式匹配到非目标标题 | 覆盖率虚高 | 正则必须有锚定（`^第X章`），不做模糊全文匹配 |
| `config.py` 改为 JSON 加载后影响 K16 管道 | 回归风险 | 保持 `CHAPTER_MAPPING` 变量名和结构不变，仅改数据来源 |
| LLM 兜底接口预留但未实现 | S15 阶段需补充 | 接口文档清晰，抛 `NotImplementedError` 并注释预期行为 |

---

## 与后续任务的关系

| 下游任务 | 依赖方式 |
|---------|---------|
| **S15** ChapterMapper 集成 | 直接复用 `review/chapter_mapper.py`，补充 LLM 兜底实现 |
| **S16** CompletenessChecker | 消费 `ChapterMapper.map_document()` 的输出判断覆盖率 |
| **S7** ChapterSplitter 升级 | `config.py` 改为加载 JSON 后，知识提取管道自动受益 |
| **K20** 嵌入模型评估 | 无直接依赖 |

---

*计划编写：2026-02-24 | 基于 docs/ 全部文档 + K16 提取报告 + 560 标题统计分析*
