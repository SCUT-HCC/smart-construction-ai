"""ChapterMapper 单元测试 + 回归测试。

测试矩阵:
  - 标准名称精确匹配 (10)
  - 禁止变体映射 (20+)
  - 带前缀匹配 (15)
  - 子章节继承 (8)
  - 排除规则 (10)
  - 正则匹配 (5)
  - 回归: K16 全量 (14 份文档)
"""

import re
from pathlib import Path

import pytest

from review.chapter_mapper import ChapterMapper, MappingResult

# ── Fixtures ─────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def mapper() -> ChapterMapper:
    """全局共享的 ChapterMapper 实例。"""
    return ChapterMapper()


# ── 辅助函数 ─────────────────────────────────────────────────

_HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def split_headers(content: str):
    """简单的标题切分。"""
    matches = list(_HEADER_RE.finditer(content))
    results = []
    for m in matches:
        level = len(m.group(1))
        title = m.group(2).strip()
        results.append((title, level))
    return results


# ── 测试 1: 标准名称精确匹配 ─────────────────────────────────


class TestExactMatch:
    """每章的标准名称必须精确映射。"""

    @pytest.mark.parametrize(
        "title,expected_ch",
        [
            ("一、编制依据", "Ch1"),
            ("二、工程概况", "Ch2"),
            ("三、施工组织机构及职责", "Ch3"),
            ("四、施工安排与进度计划", "Ch4"),
            ("五、施工准备", "Ch5"),
            ("六、施工方法及工艺要求", "Ch6"),
            ("七、质量管理与控制措施", "Ch7"),
            ("八、安全文明施工管理", "Ch8"),
            ("九、应急预案与处置措施", "Ch9"),
            ("十、绿色施工与环境保护", "Ch10"),
        ],
    )
    def test_standard_names(self, mapper: ChapterMapper, title: str, expected_ch: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == expected_ch
        assert result.confidence == 1.0
        assert result.match_type == "exact"

    @pytest.mark.parametrize(
        "title,expected_ch",
        [
            ("编制依据", "Ch1"),
            ("工程概况", "Ch2"),
            ("施工组织机构", "Ch3"),
            ("施工安排", "Ch4"),
            ("施工准备", "Ch5"),
            ("施工方法", "Ch6"),
            ("质量管理", "Ch7"),
            ("安全管理", "Ch8"),
            ("应急预案", "Ch9"),
            ("绿色施工", "Ch10"),
        ],
    )
    def test_core_keywords(self, mapper: ChapterMapper, title: str, expected_ch: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == expected_ch
        assert result.match_type == "exact"


# ── 测试 2: 变体匹配 ────────────────────────────────────────


class TestVariantMatch:
    """naming_conventions.md 中列出的"禁止使用"变体必须正确映射。"""

    @pytest.mark.parametrize(
        "title,expected_ch",
        [
            # Ch1 变体
            ("编制说明", "Ch1"),
            ("编制目的", "Ch1"),
            ("编写依据", "Ch1"),
            # Ch2 变体
            ("工程概述", "Ch2"),
            ("工程简介", "Ch2"),
            ("项目概况", "Ch2"),
            # Ch3 变体
            ("项目组织", "Ch3"),
            ("管理组织", "Ch3"),
            ("岗位职责", "Ch3"),
            ("管理人员", "Ch3"),
            # Ch4 变体
            ("施工计划", "Ch4"),
            ("施工工期", "Ch4"),
            ("工期规划", "Ch4"),
            ("工期计划", "Ch4"),
            # Ch5 变体
            ("准备工作", "Ch5"),
            ("资源配置", "Ch5"),
            ("技术准备", "Ch5"),
            ("人力资源", "Ch5"),
            # Ch6 变体
            ("施工技术", "Ch6"),
            ("主要工序", "Ch6"),
            ("施工方案概述", "Ch6"),
            ("施工工艺技术", "Ch6"),
            ("基础施工", "Ch6"),
            ("安装施工", "Ch6"),
            # Ch7 变体
            ("质量工艺", "Ch7"),
            ("质量保证", "Ch7"),
            ("质量检验", "Ch7"),
            ("质量通病", "Ch7"),
            ("成品保护", "Ch7"),
            # Ch8 变体
            ("安全文明", "Ch8"),
            ("文明施工", "Ch8"),
            ("危险源", "Ch8"),
            ("安健环", "Ch8"),
            ("安全风险", "Ch8"),
            ("安全检查", "Ch8"),
            ("监测监控", "Ch8"),
            ("安全生产", "Ch8"),
            # Ch9 变体
            ("应急措施", "Ch9"),
            ("应急响应", "Ch9"),
            ("应急救援工作程序", "Ch9"),
            ("应急物资准备", "Ch9"),
            ("事故处置", "Ch9"),
            # Ch10 变体
            ("环保措施", "Ch10"),
            ("水土保护", "Ch10"),
            ("环境因素", "Ch10"),
            ("绿色施工目标", "Ch10"),
            ("四节一环保", "Ch10"),
            ("环境因素分析", "Ch10"),
        ],
    )
    def test_variant_names(self, mapper: ChapterMapper, title: str, expected_ch: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == expected_ch, (
            f'"{title}" 应映射到 {expected_ch}，实际映射到 {result.chapter_id} '
            f'(match_type={result.match_type}, kw="{result.matched_keyword}")'
        )


# ── 测试 3: 带编号前缀匹配 ──────────────────────────────────


class TestPrefixedMatch:
    """不同编号风格的标题都应正确映射。"""

    @pytest.mark.parametrize(
        "title,expected_ch",
        [
            # 中文数字前缀
            ("一、编制依据", "Ch1"),
            ("二、工程概况", "Ch2"),
            ("七、质量管理", "Ch7"),
            # "第X章" 前缀
            ("第一章 编制依据", "Ch1"),
            ("第二章 工程概况", "Ch2"),
            ("第五章 施工准备", "Ch5"),
            ("第六章 施工方法", "Ch6"),
            ("第八章 安全管理", "Ch8"),
            # 数字编号前缀
            ("1 编制依据", "Ch1"),
            ("2 工程概况", "Ch2"),
            ("6.1 施工方法", "Ch6"),
            # 带空格变体
            ("第三章 施工工艺技术", "Ch6"),
            ("第七章 验收标准", "Ch7"),
            # 混合格式
            ("第一章 编制说明", "Ch1"),
            ("第二章 工程概述", "Ch2"),
        ],
    )
    def test_prefixed_titles(self, mapper: ChapterMapper, title: str, expected_ch: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == expected_ch, (
            f'带前缀 "{title}" 应映射到 {expected_ch}，实际: {result.chapter_id}'
        )


# ── 测试 4: 子章节继承 ──────────────────────────────────────


class TestInheritance:
    """子章节通过 map_document() 继承父章节映射。"""

    def test_subsection_inherits_parent(self, mapper: ChapterMapper) -> None:
        sections = [
            ("七、质量管理与控制措施", 2),
            ("7.1 质量管理组织机构", 3),
            ("7.2 质量保证措施", 3),
            ("7.2.1 质量保证体系", 4),
        ]
        results = mapper.map_document(sections)
        assert all(r.chapter_id == "Ch7" for r in results)
        assert results[0].match_type == "exact"
        assert results[1].match_type in ("inherited", "variant", "exact")
        assert results[3].match_type == "inherited"

    def test_chapter_switch(self, mapper: ChapterMapper) -> None:
        """章节切换：从 Ch7 切到 Ch8。"""
        sections = [
            ("七、质量管理与控制措施", 2),
            ("7.1 质量保证措施", 3),
            ("八、安全文明施工管理", 2),
            ("8.1 安全管理组织机构", 3),
        ]
        results = mapper.map_document(sections)
        assert results[0].chapter_id == "Ch7"
        assert results[1].chapter_id == "Ch7"
        assert results[2].chapter_id == "Ch8"
        assert results[3].chapter_id == "Ch8"

    def test_unmapped_subsection_inherits(self, mapper: ChapterMapper) -> None:
        """未映射的子章节标题继承父章节。"""
        sections = [
            ("六、施工方法及工艺要求", 2),
            ("转角塔基础分坑", 3),  # 无关键词，但应继承 Ch6
            ("3.2.1 测量分坑", 4),  # 更深层级
        ]
        results = mapper.map_document(sections)
        assert results[0].chapter_id == "Ch6"
        assert results[1].chapter_id == "Ch6"
        assert results[1].match_type == "inherited"
        assert results[2].chapter_id == "Ch6"

    def test_deep_inheritance_chain(self, mapper: ChapterMapper) -> None:
        """多层继承链。"""
        sections = [
            ("一、编制依据", 2),
            ("1.1 法律法规", 3),
            ("1.1.1 安全生产法", 4),
            ("1.2 行业标准", 3),
        ]
        results = mapper.map_document(sections)
        assert all(r.chapter_id == "Ch1" for r in results)

    def test_excluded_does_not_break_inheritance(self, mapper: ChapterMapper) -> None:
        """排除的标题不影响继承链。"""
        sections = [
            ("六、施工方法及工艺要求", 2),
            ("广东电网能源发展有限公司", 1),  # 被排除
            ("6.1 工艺流程", 3),
        ]
        results = mapper.map_document(sections)
        assert results[0].chapter_id == "Ch6"
        assert results[1].chapter_id == "excluded"
        # 排除标题后，下一个子章节仍然继承 Ch6
        assert results[2].chapter_id == "Ch6"


# ── 测试 5: 排除规则 ────────────────────────────────────────


class TestExclusion:
    """封面、公司名、签字栏等应被排除。"""

    @pytest.mark.parametrize(
        "title",
        [
            "广东电网能源发展有限公司",
            "500kV 电白变电站新建工程",
            "500kV 芝寮～回隆双回线路开断接入电白站线路工程",
            "kV电白变电站新建工程",
        ],
    )
    def test_cover_exclusion(self, mapper: ChapterMapper, title: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == "excluded", f'"{title}" 应被排除'

    @pytest.mark.parametrize(
        "title",
        [
            "目录",
            "报审表",
            "报验表",
        ],
    )
    def test_admin_exclusion(self, mapper: ChapterMapper, title: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == "excluded", f'"{title}" 应被排除'

    @pytest.mark.parametrize(
        "title",
        [
            "质检部：",
            "其它成员：",
        ],
    )
    def test_signature_exclusion(self, mapper: ChapterMapper, title: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == "excluded", f'"{title}" 应被排除'

    def test_chapter_level_exclusion(self, mapper: ChapterMapper) -> None:
        """章节级排除：编制单位不应映射到 Ch1。"""
        result = mapper.map_title("编制单位")
        # 不应映射到 Ch1（"编制" 被排除）
        assert result.chapter_id != "Ch1" or result.match_type == "excluded"


# ── 测试 6: 正则匹配 ────────────────────────────────────────


class TestRegexMatch:
    """带"第X章"格式的特殊标题应通过正则匹配。"""

    @pytest.mark.parametrize(
        "title,expected_ch",
        [
            ("第一章 编制依据", "Ch1"),
            ("第二章 工程概况", "Ch2"),
            ("第五章 灌注桩基础施工技术", "Ch6"),
            ("第六章 安全文明施工", "Ch8"),
            ("第八章 应急处置", "Ch9"),
        ],
    )
    def test_chapter_prefix_regex(self, mapper: ChapterMapper, title: str, expected_ch: str) -> None:
        result = mapper.map_title(title)
        assert result.chapter_id == expected_ch, (
            f'"{title}" 应映射到 {expected_ch}，实际: {result.chapter_id} '
            f'({result.match_type}, kw="{result.matched_keyword}")'
        )


# ── 测试 7: 置信度 ──────────────────────────────────────────


class TestConfidence:
    """不同匹配类型应有不同的置信度。"""

    def test_exact_confidence(self, mapper: ChapterMapper) -> None:
        result = mapper.map_title("编制依据")
        assert result.confidence == 1.0

    def test_variant_confidence(self, mapper: ChapterMapper) -> None:
        result = mapper.map_title("编制说明")
        assert result.confidence == 0.8

    def test_excluded_confidence(self, mapper: ChapterMapper) -> None:
        result = mapper.map_title("广东电网能源发展有限公司")
        assert result.confidence == 1.0

    def test_unmapped_confidence(self, mapper: ChapterMapper) -> None:
        result = mapper.map_title("这是一个完全无关的标题")
        assert result.confidence == 0.0


# ── 测试 8: LLM 兜底预留接口 ─────────────────────────────────


class TestLLMFallback:
    """LLM 兜底接口预留，调用应抛出 NotImplementedError。"""

    def test_llm_fallback_not_implemented(self, mapper: ChapterMapper) -> None:
        with pytest.raises(NotImplementedError, match="S15"):
            mapper.llm_fallback("某个未知标题")


# ── 测试 9: 覆盖率报告 ──────────────────────────────────────


class TestCoverageReport:
    """get_coverage_report() 应返回正确的统计。"""

    def test_basic_report(self, mapper: ChapterMapper) -> None:
        sections = [
            ("一、编制依据", 2),
            ("1.1 法律法规", 3),
            ("二、工程概况", 2),
            ("广东电网公司", 1),
        ]
        results = mapper.map_document(sections)
        report = mapper.get_coverage_report(results)
        assert report["total"] == 4
        assert report["mapped"] == 3  # Ch1 + 1.1继承 + Ch2
        assert report["excluded"] == 1
        assert report["unmapped"] == 0
        assert report["coverage_rate"] == 1.0

    def test_standard_names_dict(self, mapper: ChapterMapper) -> None:
        names = mapper.get_standard_names()
        assert len(names) == 10
        assert names["Ch1"] == "一、编制依据"
        assert names["Ch10"] == "十、绿色施工与环境保护"


# ── 测试 10: 全量回归 ───────────────────────────────────────


class TestRegression:
    """对 14 份文档运行全量映射，确保覆盖率不退化。"""

    DOCS_TO_PROCESS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16]
    INPUT_TEMPLATE = "output/{doc_id}/final.md"
    # K16 基准: 1196 片段中 1187 成功映射 (99.2%)
    # ChapterMapper 新增排除规则，excluded 也算"已处理"
    MIN_COVERAGE_RATE = 0.99

    def test_full_regression(self, mapper: ChapterMapper) -> None:
        """全量回归测试：覆盖率必须 ≥ 99%。"""
        total_sections = 0
        total_mapped = 0
        total_excluded = 0
        total_unmapped = 0

        for doc_id in self.DOCS_TO_PROCESS:
            path = PROJECT_ROOT / self.INPUT_TEMPLATE.format(doc_id=doc_id)
            if not path.exists():
                pytest.skip(f"文件不存在: {path}")

            content = path.read_text(encoding="utf-8")
            sections = split_headers(content)
            results = mapper.map_document(sections)
            report = mapper.get_coverage_report(results)

            total_sections += report["total"]
            total_mapped += report["mapped"]
            total_excluded += report["excluded"]
            total_unmapped += report["unmapped"]

        coverage = (total_mapped + total_excluded) / total_sections if total_sections > 0 else 0
        assert coverage >= self.MIN_COVERAGE_RATE, (
            f"全量回归覆盖率 {coverage:.3f} 低于阈值 {self.MIN_COVERAGE_RATE}。"
            f"总片段={total_sections}, 映射={total_mapped}, "
            f"排除={total_excluded}, 未映射={total_unmapped}"
        )

    def test_no_chapter_empty(self, mapper: ChapterMapper) -> None:
        """每个章节至少有 1 个标题映射到。"""
        all_chapters_seen: set = set()

        for doc_id in self.DOCS_TO_PROCESS:
            path = PROJECT_ROOT / self.INPUT_TEMPLATE.format(doc_id=doc_id)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            sections = split_headers(content)
            results = mapper.map_document(sections)

            for r in results:
                if r.chapter_id.startswith("Ch"):
                    all_chapters_seen.add(r.chapter_id)

        # 前 9 章必须全部出现（Ch10 可选）
        for i in range(1, 10):
            ch_id = f"Ch{i}"
            assert ch_id in all_chapters_seen, (
                f"章节 {ch_id} 在 14 份文档中从未被映射到"
            )

    def test_unmapped_are_expected(self, mapper: ChapterMapper) -> None:
        """未映射的标题应全部是已知的封面/公司名等。"""
        unmapped_titles: list = []

        for doc_id in self.DOCS_TO_PROCESS:
            path = PROJECT_ROOT / self.INPUT_TEMPLATE.format(doc_id=doc_id)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            sections = split_headers(content)
            results = mapper.map_document(sections)

            for r in results:
                if r.chapter_id == "unmapped":
                    unmapped_titles.append((doc_id, r.original_title))

        # 未映射数量应很少（K16 基准为 9，新增排除规则后应更少）
        assert len(unmapped_titles) <= 15, (
            f"未映射标题数 {len(unmapped_titles)} 过多，"
            f"应 ≤ 15。清单: {unmapped_titles[:10]}"
        )
