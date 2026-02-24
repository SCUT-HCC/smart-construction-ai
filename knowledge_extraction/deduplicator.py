"""跨文档去重器 — 同章节内基于 Jaccard 相似度去重。

使用 jieba 分词后比较词集合，阈值 > 0.8 视为重复，
保留 quality_rating 更高者。
"""

from typing import Dict, List, Set, Tuple

from utils.logger_system import log_msg
from knowledge_extraction.config import DEDUP_THRESHOLD

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


class Deduplicator:
    """同章节内跨文档去重。

    比较范围：同一 chapter_id 内的片段两两比较（不跨章节）。
    算法：Jaccard 相似度（基于 jieba 分词后的词集合）。
    保留规则：quality_rating 高者优先；相同则保留 source_doc 编号更小者。
    """

    def __init__(self, threshold: float = DEDUP_THRESHOLD):
        """初始化。

        Args:
            threshold: Jaccard 相似度阈值，超过则视为重复
        """
        self._threshold = threshold
        if not _HAS_JIEBA:
            log_msg("WARNING", "jieba 未安装，将使用字符级分词（精度较低）")

    def deduplicate(self, fragments: List[Dict]) -> List[Dict]:
        """对片段列表去重，返回去重后的列表。

        Args:
            fragments: 含 density 字段的片段列表（仅对 high/medium 去重）

        Returns:
            去重后的片段列表
        """
        # 仅对入库片段（high/medium）去重
        to_dedup = [f for f in fragments if f.get("density") in ("high", "medium")]
        excluded = [f for f in fragments if f.get("density") not in ("high", "medium")]

        # 按章节分组
        chapter_groups: Dict[str, List[Dict]] = {}
        for frag in to_dedup:
            ch_id = frag.get("chapter_id", "unmapped")
            chapter_groups.setdefault(ch_id, []).append(frag)

        kept: List[Dict] = []
        removed_count = 0

        for ch_id, group in chapter_groups.items():
            group_kept, group_removed = self._dedup_group(group)
            kept.extend(group_kept)
            removed_count += group_removed

        log_msg(
            "INFO",
            f"去重完成: 输入 {len(to_dedup)} 条，"
            f"移除 {removed_count} 条，保留 {len(kept)} 条",
        )
        return kept + excluded

    def _dedup_group(self, group: List[Dict]) -> Tuple[List[Dict], int]:
        """对同一章节内的片段去重。

        Args:
            group: 同一 chapter_id 下的片段列表

        Returns:
            (保留的片段列表, 移除数量)
        """
        if len(group) <= 1:
            return group, 0

        # 预计算词集合
        token_sets: List[Set[str]] = [
            self._tokenize(f.get("content", "")) for f in group
        ]

        # 标记要移除的索引
        to_remove: Set[int] = set()

        for i in range(len(group)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(group)):
                if j in to_remove:
                    continue
                sim = self._jaccard(token_sets[i], token_sets[j])
                if sim > self._threshold:
                    # 移除质量较低的那个
                    loser = self._pick_loser(group[i], group[j], i, j)
                    to_remove.add(loser)

        kept = [f for idx, f in enumerate(group) if idx not in to_remove]
        return kept, len(to_remove)

    def _tokenize(self, text: str) -> Set[str]:
        """将文本分词为词集合。

        Args:
            text: 输入文本

        Returns:
            词集合（去除长度 < 2 的词）
        """
        if _HAS_JIEBA:
            words = jieba.lcut(text)
        else:
            # 简单的字符级分词（bigram）
            words = [text[i : i + 2] for i in range(len(text) - 1)]
        return {w for w in words if len(w) >= 2}

    def _jaccard(self, set_a: Set[str], set_b: Set[str]) -> float:
        """计算 Jaccard 相似度。

        Args:
            set_a: 词集合 A
            set_b: 词集合 B

        Returns:
            Jaccard 相似度 [0, 1]
        """
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union

    def _pick_loser(
        self, frag_a: Dict, frag_b: Dict, idx_a: int, idx_b: int
    ) -> int:
        """在两个重复片段中选择要移除的那个。

        规则：quality_rating 低者移除；相同则 source_doc 编号大者移除。

        Args:
            frag_a: 片段 A
            frag_b: 片段 B
            idx_a: 片段 A 在 group 中的索引
            idx_b: 片段 B 在 group 中的索引

        Returns:
            要移除的片段索引
        """
        qa = frag_a.get("quality_rating", 2)
        qb = frag_b.get("quality_rating", 2)
        if qa != qb:
            return idx_b if qa > qb else idx_a

        da = frag_a.get("source_doc", 999)
        db = frag_b.get("source_doc", 999)
        return idx_b if da <= db else idx_a
