"""章节标题映射器 — 将施工方案实际标题映射到标准 10 章结构。

审核系统的前置模块。将文档中的实际章节标题（560+ 种变体）
映射到标准 Ch1-Ch10 结构，支持三级回退和排除规则。

映射策略:
  L1 精确匹配（confidence=1.0）
  L2 变体 + 正则匹配（confidence=0.8）
  L3 (预留) LLM 语义兜底（confidence=0.6）
  + 排除规则: 封面/公司名/材料名 → "excluded"
  + 子章节继承: 深层级标题继承父章节映射
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_system import log_msg

# 默认规则库路径
_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "knowledge_base"
    / "chapter_mapping"
    / "mapping_rules.json"
)

# ── 标题清理正则 ───────────────────────────────────────────────
_CHAPTER_CN_RE = re.compile(r"第[一二三四五六七八九十百千]+章\s*")
_CN_NUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十]+、\s*")
_NUM_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")
_PAREN_NUM_RE = re.compile(r"^\(\d+\)\s*")
_CIRCLE_NUM_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*")


@dataclass(frozen=True)
class MappingResult:
    """单个标题的映射结果。

    Attributes:
        original_title: 原始标题文本
        chapter_id: "Ch1"-"Ch10" | "unmapped" | "excluded"
        chapter_name: 标准章节名称（如 "一、编制依据"），excluded/unmapped 时为空
        confidence: 映射置信度 0.0-1.0
        match_type: "exact" | "variant" | "regex" | "inherited" | "excluded" | "unmapped"
        matched_keyword: 命中的关键词/正则模式，未命中时为空
    """

    original_title: str
    chapter_id: str
    chapter_name: str
    confidence: float
    match_type: str
    matched_keyword: str


@dataclass
class _ChapterRule:
    """单个章节的编译后映射规则。"""

    standard_name: str
    required: bool
    exact_keywords: List[str]
    variant_keywords: List[str]
    regex_patterns: List[re.Pattern]  # type: ignore[type-arg]
    exclusions: List[str]
    sub_section_indicators: List[str]


class ChapterMapper:
    """章节标题映射器。

    加载结构化规则库（mapping_rules.json），将实际标题映射到标准 10 章。
    支持单标题映射和整篇文档映射（含子章节继承）。

    Args:
        rules_path: 规则库 JSON 路径，为 None 时使用默认路径
    """

    def __init__(self, rules_path: Optional[str] = None) -> None:
        """加载并编译映射规则。

        Args:
            rules_path: 规则库 JSON 路径，为 None 时使用默认路径

        Raises:
            FileNotFoundError: 规则库文件不存在
        """
        path = Path(rules_path) if rules_path else _DEFAULT_RULES_PATH
        if not path.exists():
            log_msg("ERROR", f"映射规则库不存在: {path}")

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        self._rules: Dict[str, _ChapterRule] = {}
        self._global_exclusion_patterns: List[re.Pattern] = []  # type: ignore[type-arg]
        self._standard_names: Dict[str, str] = {}

        self._compile_rules(raw)
        log_msg(
            "INFO",
            f"ChapterMapper 加载完成: {len(self._rules)} 章规则，"
            f"{len(self._global_exclusion_patterns)} 条全局排除模式",
        )

    # ── 公开接口 ───────────────────────────────────────────────

    def map_title(self, title: str) -> MappingResult:
        """映射单个标题（不含子章节继承逻辑）。

        Args:
            title: 原始标题文本

        Returns:
            映射结果
        """
        # 第 0 步：全局排除检查
        if self._is_globally_excluded(title):
            return MappingResult(
                original_title=title,
                chapter_id="excluded",
                chapter_name="",
                confidence=1.0,
                match_type="excluded",
                matched_keyword="global_exclusion",
            )

        cleaned = self._clean_title(title)

        # 第 1 步：精确匹配（L1）
        for ch_id, rule in self._rules.items():
            # 章节级排除检查
            if self._hits_exclusion(cleaned, title, rule.exclusions):
                continue
            for kw in rule.exact_keywords:
                if kw in cleaned or kw in title:
                    return MappingResult(
                        original_title=title,
                        chapter_id=ch_id,
                        chapter_name=rule.standard_name,
                        confidence=1.0,
                        match_type="exact",
                        matched_keyword=kw,
                    )

        # 第 2 步：变体匹配（L2）
        for ch_id, rule in self._rules.items():
            if self._hits_exclusion(cleaned, title, rule.exclusions):
                continue
            for kw in rule.variant_keywords:
                if kw in cleaned or kw in title:
                    return MappingResult(
                        original_title=title,
                        chapter_id=ch_id,
                        chapter_name=rule.standard_name,
                        confidence=0.8,
                        match_type="variant",
                        matched_keyword=kw,
                    )

        # 第 3 步：正则匹配（L2.5）
        for ch_id, rule in self._rules.items():
            if self._hits_exclusion(cleaned, title, rule.exclusions):
                continue
            for pat in rule.regex_patterns:
                if pat.search(title):
                    return MappingResult(
                        original_title=title,
                        chapter_id=ch_id,
                        chapter_name=rule.standard_name,
                        confidence=0.8,
                        match_type="regex",
                        matched_keyword=pat.pattern,
                    )

        # 第 4 步：LLM 语义兜底（L3，预留）
        # 未来在 S15 中实现，当前抛出异常提醒调用者
        # result = self._llm_fallback(title)
        # if result is not None:
        #     return result

        return MappingResult(
            original_title=title,
            chapter_id="unmapped",
            chapter_name="",
            confidence=0.0,
            match_type="unmapped",
            matched_keyword="",
        )

    def map_document(
        self, sections: List[Tuple[str, int]]
    ) -> List[MappingResult]:
        """映射整篇文档的标题列表，含子章节继承逻辑。

        子章节继承规则:
          - 当前标题层级 > 父章节层级 → 继承父章节映射
          - 当前标题有直接映射 + 层级 ≤ 父章节层级 → 更新当前章节
          - 当前标题无直接映射 + 层级 ≤ 父章节层级 → 仍继承父章节

        Args:
            sections: [(标题, 层级), ...]，层级为 Markdown 标题层级（1-4）

        Returns:
            逐标题的映射结果列表，长度与输入相同
        """
        results: List[MappingResult] = []
        current_chapter_id = "unmapped"
        current_chapter_name = ""
        current_chapter_confidence = 0.0
        current_chapter_level = 99

        for title, level in sections:
            direct_result = self.map_title(title)

            # 排除的标题不参与继承
            if direct_result.match_type == "excluded":
                results.append(direct_result)
                continue

            # 判断是否为新章节还是子章节
            if direct_result.chapter_id not in ("unmapped",) and level <= current_chapter_level:
                # 新章节：更新当前章节上下文
                current_chapter_id = direct_result.chapter_id
                current_chapter_name = direct_result.chapter_name
                current_chapter_confidence = direct_result.confidence
                current_chapter_level = level
                results.append(direct_result)
            elif level > current_chapter_level and current_chapter_id != "unmapped":
                # 子章节：继承父章节
                results.append(
                    MappingResult(
                        original_title=title,
                        chapter_id=current_chapter_id,
                        chapter_name=current_chapter_name,
                        confidence=current_chapter_confidence,
                        match_type="inherited",
                        matched_keyword=f"继承自 {current_chapter_name}",
                    )
                )
            elif direct_result.chapter_id not in ("unmapped",):
                # 有映射但层级不更新上下文（同级别）
                results.append(direct_result)
            else:
                # 无映射，尝试继承
                if current_chapter_id != "unmapped":
                    results.append(
                        MappingResult(
                            original_title=title,
                            chapter_id=current_chapter_id,
                            chapter_name=current_chapter_name,
                            confidence=current_chapter_confidence * 0.7,
                            match_type="inherited",
                            matched_keyword=f"继承自 {current_chapter_name}",
                        )
                    )
                else:
                    results.append(direct_result)

        return results

    def get_coverage_report(
        self, results: List[MappingResult]
    ) -> Dict[str, Any]:
        """生成覆盖率统计报告。

        Args:
            results: map_document() 的输出

        Returns:
            统计字典，包含各章命中数、覆盖率、未映射清单等
        """
        total = len(results)
        if total == 0:
            return {"total": 0, "coverage_rate": 0.0}

        chapter_counts: Dict[str, int] = {}
        match_type_counts: Dict[str, int] = {}
        unmapped_titles: List[str] = []
        excluded_titles: List[str] = []

        for r in results:
            match_type_counts[r.match_type] = match_type_counts.get(r.match_type, 0) + 1

            if r.chapter_id == "unmapped":
                unmapped_titles.append(r.original_title)
            elif r.chapter_id == "excluded":
                excluded_titles.append(r.original_title)
            else:
                chapter_counts[r.chapter_id] = chapter_counts.get(r.chapter_id, 0) + 1

        mapped = sum(chapter_counts.values())
        excluded = len(excluded_titles)

        return {
            "total": total,
            "mapped": mapped,
            "excluded": excluded,
            "unmapped": len(unmapped_titles),
            "coverage_rate": (mapped + excluded) / total if total > 0 else 0.0,
            "chapter_distribution": chapter_counts,
            "match_type_distribution": match_type_counts,
            "unmapped_titles": unmapped_titles,
            "excluded_titles": excluded_titles,
        }

    def get_standard_names(self) -> Dict[str, str]:
        """返回标准章节 ID → 名称的映射。

        Returns:
            {"Ch1": "一、编制依据", ...}
        """
        return dict(self._standard_names)

    def llm_fallback(self, title: str) -> MappingResult:
        """LLM 语义兜底映射（预留接口）。

        在 S15 阶段实现。当关键词和正则都无法匹配时，
        调用 LLM 判断标题应属于哪个标准章节。

        Args:
            title: 清理后的标题文本

        Returns:
            映射结果（confidence=0.6）

        Raises:
            NotImplementedError: 当前阶段未实现
        """
        raise NotImplementedError(
            "LLM 语义兜底将在 S15 阶段实现。"
            "预期行为：调用 LLM 判断标题应属于哪个标准章节，"
            "返回 MappingResult(confidence=0.6, match_type='llm')。"
        )

    # ── 内部方法 ───────────────────────────────────────────────

    def _compile_rules(self, raw: Dict[str, Any]) -> None:
        """编译 JSON 规则为内部数据结构。

        Args:
            raw: mapping_rules.json 的解析结果
        """
        for ch_id, ch_data in raw["chapters"].items():
            exact: List[str] = []
            variant: List[str] = []
            patterns: List[re.Pattern] = []  # type: ignore[type-arg]

            for rule in ch_data["rules"]:
                if rule["type"] == "exact":
                    exact.extend(rule["keywords"])
                elif rule["type"] == "variant":
                    variant.extend(rule["keywords"])
                elif rule["type"] == "regex":
                    for p in rule["patterns"]:
                        patterns.append(re.compile(p))

            self._rules[ch_id] = _ChapterRule(
                standard_name=ch_data["standard_name"],
                required=ch_data["required"],
                exact_keywords=exact,
                variant_keywords=variant,
                regex_patterns=patterns,
                exclusions=ch_data.get("exclusions", []),
                sub_section_indicators=ch_data.get("sub_section_indicators", []),
            )
            self._standard_names[ch_id] = ch_data["standard_name"]

        # 编译全局排除模式
        global_exc = raw.get("global_exclusions", {})
        for category in ("cover_patterns", "admin_patterns", "signature_patterns"):
            for pattern_str in global_exc.get(category, []):
                self._global_exclusion_patterns.append(re.compile(pattern_str))

    def _clean_title(self, title: str) -> str:
        """去掉编号前缀，返回清理后的标题核心文本。

        Args:
            title: 原始标题

        Returns:
            清理后的标题
        """
        cleaned = _CHAPTER_CN_RE.sub("", title)
        cleaned = _CN_NUM_PREFIX_RE.sub("", cleaned)
        cleaned = _NUM_SECTION_RE.sub("", cleaned)
        cleaned = _PAREN_NUM_RE.sub("", cleaned)
        cleaned = _CIRCLE_NUM_RE.sub("", cleaned)
        return cleaned.strip()

    def _is_globally_excluded(self, title: str) -> bool:
        """检查标题是否匹配全局排除规则。

        Args:
            title: 原始标题

        Returns:
            True 表示应排除
        """
        for pat in self._global_exclusion_patterns:
            if pat.search(title):
                return True
        return False

    def _hits_exclusion(
        self, cleaned: str, original: str, exclusions: List[str]
    ) -> bool:
        """检查标题是否匹配章节级排除规则。

        Args:
            cleaned: 清理后的标题
            original: 原始标题
            exclusions: 该章节的排除关键词列表

        Returns:
            True 表示应排除（不映射到该章节）
        """
        for exc in exclusions:
            if exc in cleaned or exc in original:
                return True
        return False
