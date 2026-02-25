"""K23 向量库模块单元测试。

覆盖 config.py、indexer.py、retriever.py 的核心逻辑。
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vector_store.config import (
    ALL_COLLECTIONS,
    CHAPTER_TO_COLLECTION,
)
from vector_store.indexer import (
    _build_document_content,
    _index_extra_sources,
    _index_fragments,
    _load_fragments,
    build_vector_store,
)
from vector_store.retriever import (
    RetrievalResult,
    VectorRetriever,
    _match_engineering_type,
)


# ═══════════════════════════════════════════════════════════════
# 测试 Fixture
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_fragments() -> list[dict]:
    """知识片段样本。"""
    return [
        {
            "id": "doc01_ch6_s01",
            "source_doc": 1,
            "chapter": "六、施工方法及工艺要求",
            "section": "6.1 混凝土浇筑",
            "engineering_type": "变电土建",
            "density": "high",
            "tags": ["混凝土", "浇筑", "振捣"],
            "content": "混凝土浇筑施工应分层进行，每层厚度不超过500mm。",
        },
        {
            "id": "doc01_ch7_s01",
            "chapter": "七、质量管理与控制措施",
            "section": "7.1 质量控制",
            "engineering_type": "变电土建",
            "density": "high",
            "tags": ["质量", "检查"],
            "content": "每100m³取样一组标准养护试件。",
        },
        {
            "id": "doc01_ch8_s01",
            "chapter": "八、安全文明施工管理",
            "section": "8.1 安全措施",
            "engineering_type": "变电电气",
            "density": "high",
            "tags": ["安全", "高处"],
            "content": "高处作业必须佩戴安全带。",
        },
        {
            "id": "doc01_ch1_s01",
            "chapter": "一、编制依据",
            "section": "1.1 编制依据",
            "engineering_type": "变电土建",
            "density": "high",
            "tags": ["标准", "规范"],
            "content": "GB 50300-2013 建筑工程施工质量验收统一标准。",
        },
        {
            "id": "doc01_ch5_s01",
            "chapter": "五、施工准备",
            "section": "5.1 设备",
            "engineering_type": "变电土建",
            "density": "medium",
            "tags": ["设备", "准备"],
            "content": "主要施工设备：塔吊1台，搅拌车2辆。",
        },
        {
            "id": "doc01_ch3_s01",
            "chapter": "三、施工组织机构及职责",
            "section": "3.1 组织机构",
            "engineering_type": "变电土建",
            "density": "medium",
            "tags": ["组织", "职责"],
            "content": "项目经理负责全面管理，安全员负责安全监督。",
        },
    ]


@pytest.fixture
def fragments_jsonl(sample_fragments: list[dict], tmp_path: Path) -> Path:
    """创建临时 fragments.jsonl 文件。"""
    path = tmp_path / "fragments.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for frag in sample_fragments:
            f.write(json.dumps(frag, ensure_ascii=False) + "\n")
    return path


# ═══════════════════════════════════════════════════════════════
# config.py 测试
# ═══════════════════════════════════════════════════════════════


class TestConfig:
    """测试配置定义。"""

    def test_all_chapters_mapped(self) -> None:
        """所有 10 个章节都有映射。"""
        assert len(CHAPTER_TO_COLLECTION) == 10

    def test_all_collections_defined(self) -> None:
        """8 个 Collection 都已定义。"""
        assert len(ALL_COLLECTIONS) == 8

    def test_collections_match_mapping(self) -> None:
        """映射值都在 Collection 列表中。"""
        for collection in CHAPTER_TO_COLLECTION.values():
            assert collection in ALL_COLLECTIONS

    def test_chapter_mapping_targets(self) -> None:
        """关键章节映射正确。"""
        assert CHAPTER_TO_COLLECTION["一、编制依据"] == "ch01_basis"
        assert CHAPTER_TO_COLLECTION["六、施工方法及工艺要求"] == "ch06_methods"
        assert CHAPTER_TO_COLLECTION["七、质量管理与控制措施"] == "ch07_quality"
        assert CHAPTER_TO_COLLECTION["八、安全文明施工管理"] == "ch08_safety"
        assert CHAPTER_TO_COLLECTION["五、施工准备"] == "equipment"
        assert CHAPTER_TO_COLLECTION["三、施工组织机构及职责"] == "templates"


# ═══════════════════════════════════════════════════════════════
# indexer.py — _load_fragments 测试
# ═══════════════════════════════════════════════════════════════


class TestLoadFragments:
    """测试片段加载。"""

    def test_load_count(self, fragments_jsonl: Path) -> None:
        """加载正确数量的片段。"""
        fragments = _load_fragments(fragments_jsonl)
        assert len(fragments) == 6

    def test_load_content(self, fragments_jsonl: Path) -> None:
        """片段内容正确。"""
        fragments = _load_fragments(fragments_jsonl)
        assert fragments[0]["id"] == "doc01_ch6_s01"
        assert "混凝土" in fragments[0]["content"]

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """空文件返回空列表。"""
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        assert _load_fragments(path) == []


# ═══════════════════════════════════════════════════════════════
# indexer.py — _build_document_content 测试
# ═══════════════════════════════════════════════════════════════


class TestBuildDocumentContent:
    """测试文档内容构建。"""

    def test_full_metadata(self, sample_fragments: list[dict]) -> None:
        """包含所有元数据前缀。"""
        content = _build_document_content(sample_fragments[0])
        assert "[工程类型: 变电土建]" in content
        assert "[章节: 6.1 混凝土浇筑]" in content
        assert "[标签: 混凝土, 浇筑, 振捣]" in content
        assert "混凝土浇筑施工应分层进行" in content

    def test_no_engineering_type(self) -> None:
        """无工程类型时不添加前缀。"""
        frag = {"content": "测试内容", "tags": ["a"]}
        content = _build_document_content(frag)
        assert "[工程类型:" not in content
        assert "测试内容" in content

    def test_no_tags(self) -> None:
        """无标签时不添加标签前缀。"""
        frag = {"content": "测试内容", "engineering_type": "变电土建"}
        content = _build_document_content(frag)
        assert "[标签:" not in content

    def test_tags_truncated_at_eight(self) -> None:
        """标签超过 8 个只显示前 8 个。"""
        frag = {
            "content": "测试",
            "tags": ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10"],
        }
        content = _build_document_content(frag)
        assert "t8" in content
        assert "t9" not in content

    def test_empty_content(self) -> None:
        """空内容返回空字符串。"""
        frag = {"content": ""}
        content = _build_document_content(frag)
        assert content == ""

    def test_metadata_prefix_format(self, sample_fragments: list[dict]) -> None:
        """元数据前缀在正文之前，用换行分隔。"""
        content = _build_document_content(sample_fragments[0])
        lines = content.split("\n")
        assert len(lines) >= 2
        assert "[工程类型:" in lines[0]
        assert "混凝土" in lines[1]


# ═══════════════════════════════════════════════════════════════
# indexer.py — _index_fragments 测试
# ═══════════════════════════════════════════════════════════════


class TestIndexFragments:
    """测试片段索引。"""

    def test_index_to_correct_collections(
        self, sample_fragments: list[dict], fragments_jsonl: Path, tmp_path: Path
    ) -> None:
        """片段按章节分配到正确的 Collection。"""
        import qmd

        db_path = tmp_path / "test.db"
        db, store = qmd.create_store(str(db_path))

        with patch("vector_store.indexer.FRAGMENTS_JSONL", fragments_jsonl):
            stats = _index_fragments(store)

        assert stats["ch06_methods"] == 1
        assert stats["ch07_quality"] == 1
        assert stats["ch08_safety"] == 1
        assert stats["ch01_basis"] == 1
        assert stats["equipment"] == 1
        assert stats["templates"] == 1

    def test_total_indexed(self, fragments_jsonl: Path, tmp_path: Path) -> None:
        """所有片段均被索引。"""
        import qmd

        db_path = tmp_path / "test.db"
        db, store = qmd.create_store(str(db_path))

        with patch("vector_store.indexer.FRAGMENTS_JSONL", fragments_jsonl):
            stats = _index_fragments(store)

        assert sum(stats.values()) == 6

    def test_skip_unknown_chapter(self, tmp_path: Path) -> None:
        """未知章节跳过。"""
        import qmd

        jsonl_path = tmp_path / "frags.jsonl"
        frag = {"id": "x", "chapter": "未知章节", "content": "test"}
        jsonl_path.write_text(json.dumps(frag, ensure_ascii=False), encoding="utf-8")

        db_path = tmp_path / "test.db"
        db, store = qmd.create_store(str(db_path))

        with patch("vector_store.indexer.FRAGMENTS_JSONL", jsonl_path):
            stats = _index_fragments(store)

        assert sum(stats.values()) == 0


# ═══════════════════════════════════════════════════════════════
# indexer.py — _index_extra_sources 测试
# ═══════════════════════════════════════════════════════════════


class TestIndexExtraSources:
    """测试补充数据源索引。"""

    def test_templates_indexed(self, tmp_path: Path) -> None:
        """ch06 模板文件被正确索引。"""
        import qmd

        # 创建临时模板目录
        templates_dir = tmp_path / "ch06_templates"
        templates_dir.mkdir()
        (templates_dir / "civil.md").write_text("# 土建模板\n内容", encoding="utf-8")
        (templates_dir / "README.md").write_text("# 说明", encoding="utf-8")

        guides_dir = tmp_path / "writing_guides"
        guides_dir.mkdir()
        (guides_dir / "ch01.md").write_text("# 编制依据指南", encoding="utf-8")

        db_path = tmp_path / "test.db"
        db, store = qmd.create_store(str(db_path))

        with (
            patch("vector_store.indexer.CH06_TEMPLATES_DIR", templates_dir),
            patch("vector_store.indexer.WRITING_GUIDES_DIR", guides_dir),
        ):
            stats = _index_extra_sources(store)

        assert stats["ch06_templates"] == 1  # README.md 跳过
        assert stats["writing_guides"] == 1

    def test_empty_dirs(self, tmp_path: Path) -> None:
        """不存在的目录不报错。"""
        import qmd

        db_path = tmp_path / "test.db"
        db, store = qmd.create_store(str(db_path))

        with (
            patch("vector_store.indexer.CH06_TEMPLATES_DIR", tmp_path / "nonexistent1"),
            patch("vector_store.indexer.WRITING_GUIDES_DIR", tmp_path / "nonexistent2"),
        ):
            stats = _index_extra_sources(store)

        assert stats["ch06_templates"] == 0
        assert stats["writing_guides"] == 0


# ═══════════════════════════════════════════════════════════════
# indexer.py — build_vector_store 集成测试
# ═══════════════════════════════════════════════════════════════


class TestBuildVectorStore:
    """测试端到端构建（无嵌入）。"""

    def test_build_creates_db(self, fragments_jsonl: Path, tmp_path: Path) -> None:
        """构建创建数据库文件。"""
        db_path = tmp_path / "vs" / "test.db"

        with (
            patch("vector_store.indexer.FRAGMENTS_JSONL", fragments_jsonl),
            patch("vector_store.indexer.CH06_TEMPLATES_DIR", tmp_path / "no1"),
            patch("vector_store.indexer.WRITING_GUIDES_DIR", tmp_path / "no2"),
        ):
            db, store = build_vector_store(db_path=db_path, auto_embed=False)

        assert db_path.exists()

    def test_build_force_rebuild(self, fragments_jsonl: Path, tmp_path: Path) -> None:
        """强制重建删除已有数据库。"""
        db_path = tmp_path / "test.db"
        db_path.write_text("old data", encoding="utf-8")

        with (
            patch("vector_store.indexer.FRAGMENTS_JSONL", fragments_jsonl),
            patch("vector_store.indexer.CH06_TEMPLATES_DIR", tmp_path / "no1"),
            patch("vector_store.indexer.WRITING_GUIDES_DIR", tmp_path / "no2"),
        ):
            db, store = build_vector_store(
                db_path=db_path, force_rebuild=True, auto_embed=False
            )

        # 新数据库应该有文档
        total = sum(store.get_document_count(c) for c in ALL_COLLECTIONS)
        assert total == 6


# ═══════════════════════════════════════════════════════════════
# retriever.py — _match_engineering_type 测试
# ═══════════════════════════════════════════════════════════════


class TestMatchEngineeringType:
    """测试工程类型匹配。"""

    def test_exact_match(self) -> None:
        """精确匹配工程类型。"""
        content = "[工程类型: 变电土建] [章节: 6.1] 内容"
        assert _match_engineering_type(content, "变电土建") is True

    def test_mismatch(self) -> None:
        """不匹配的工程类型。"""
        content = "[工程类型: 变电电气] [章节: 6.1] 内容"
        assert _match_engineering_type(content, "变电土建") is False

    def test_no_type_marker(self) -> None:
        """无工程类型标记的内容匹配任何类型。"""
        content = "没有工程类型标记的通用内容"
        assert _match_engineering_type(content, "变电土建") is True

    def test_empty_content(self) -> None:
        """空内容匹配任何类型。"""
        assert _match_engineering_type("", "变电土建") is True


# ═══════════════════════════════════════════════════════════════
# retriever.py — RetrievalResult 测试
# ═══════════════════════════════════════════════════════════════


class TestRetrievalResult:
    """测试检索结果数据类。"""

    def test_to_dict(self) -> None:
        """转换为字典。"""
        result = RetrievalResult(
            content="test",
            score=0.95,
            collection="ch06_methods",
            file_id="doc01",
            context=None,
        )
        d = result.to_dict()
        assert d["content"] == "test"
        assert d["score"] == 0.95
        assert d["collection"] == "ch06_methods"

    def test_default_context(self) -> None:
        """context 默认为 None。"""
        result = RetrievalResult(content="test", score=0.5, collection="c", file_id="f")
        assert result.context is None


# ═══════════════════════════════════════════════════════════════
# retriever.py — VectorRetriever 测试
# ═══════════════════════════════════════════════════════════════


class TestVectorRetriever:
    """测试向量检索器。"""

    @pytest.fixture
    def retriever_with_data(
        self, fragments_jsonl: Path, tmp_path: Path
    ) -> VectorRetriever:
        """创建已索引数据的检索器（无嵌入模型）。"""
        db_path = tmp_path / "test_retriever.db"

        with (
            patch("vector_store.indexer.FRAGMENTS_JSONL", fragments_jsonl),
            patch("vector_store.indexer.CH06_TEMPLATES_DIR", tmp_path / "no1"),
            patch("vector_store.indexer.WRITING_GUIDES_DIR", tmp_path / "no2"),
        ):
            db, store = build_vector_store(db_path=db_path, auto_embed=False)

        return VectorRetriever(db, backend=None)

    def test_get_collection_stats(self, retriever_with_data: VectorRetriever) -> None:
        """获取各 Collection 文档数量。"""
        stats = retriever_with_data.get_collection_stats()
        assert stats["ch06_methods"] == 1
        assert stats["ch07_quality"] == 1
        assert stats["ch08_safety"] == 1
        assert stats["ch01_basis"] == 1
        assert stats["equipment"] == 1
        assert stats["templates"] == 1

    def test_search_without_backend(self, retriever_with_data: VectorRetriever) -> None:
        """无嵌入模型时 BM25 检索仍可用。"""
        results = retriever_with_data.search(
            "混凝土", collection="ch06_methods", limit=3, threshold=0.0
        )
        # BM25 检索应返回结果
        assert len(results) >= 1
        assert "混凝土" in results[0].content

    def test_search_specific_collection(
        self, retriever_with_data: VectorRetriever
    ) -> None:
        """指定 Collection 只返回该 Collection 结果。"""
        results = retriever_with_data.search(
            "安全", collection="ch08_safety", limit=10, threshold=0.0
        )
        for r in results:
            assert r.collection == "ch08_safety"

    def test_search_with_threshold(self, retriever_with_data: VectorRetriever) -> None:
        """阈值过滤低分结果。"""
        results = retriever_with_data.search(
            "混凝土", collection="ch06_methods", limit=10, threshold=999.0
        )
        assert len(results) == 0

    def test_close(self, retriever_with_data: VectorRetriever) -> None:
        """关闭检索器。"""
        retriever_with_data.close()
        assert retriever_with_data._backend is None

    def test_search_multi_collection(
        self, retriever_with_data: VectorRetriever
    ) -> None:
        """跨多个 Collection 检索。"""
        results = retriever_with_data.search_multi_collection(
            "施工",
            collections=["ch06_methods", "ch08_safety"],
            limit_per_collection=3,
            threshold=0.0,
        )
        assert "ch06_methods" in results
        assert "ch08_safety" in results

    def test_search_multi_collection_invalid(
        self, retriever_with_data: VectorRetriever
    ) -> None:
        """无效 Collection 被忽略。"""
        results = retriever_with_data.search_multi_collection(
            "施工",
            collections=["nonexistent", "ch06_methods"],
            limit_per_collection=3,
            threshold=0.0,
        )
        assert "nonexistent" not in results
        assert "ch06_methods" in results
