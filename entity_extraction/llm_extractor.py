"""K21 LLM 抽取器 — 从 fragments.jsonl 非结构化文本中抽取实体和关系

使用 DeepSeek API 从 Ch6/Ch7/Ch8 高密度片段中补充抽取
规则解析器无法触及的隐式实体和关系。
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI
from tqdm import tqdm

import config as app_config
from entity_extraction.config import (
    EXTRACT_CHAPTERS,
    EXTRACT_DENSITY,
    FRAGMENTS_PATH,
    LLM_CONTENT_MAX_CHARS,
    LLM_MAX_RETRIES,
    LLM_MAX_WORKERS,
    LLM_TEMPERATURE,
)
from entity_extraction.schema import Entity, Relation
from utils.logger_system import log_msg


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """你是施工领域知识图谱抽取专家。从给定施工方案文本中抽取实体和关系。

## 实体类型

- process: 施工工序/作业活动（如：钻孔、清孔、混凝土浇筑、钢筋笼下放、吊装就位）
- equipment: 施工设备/工具（如：旋转钻机、QY160起重机、振动棒、电焊机）
- hazard: 危险源/危险因素（如：坍塌、触电、高处坠落、物体打击）
- safety_measure: 安全措施/控制手段（如：系安全带、设防护栏、一机一闸一漏一箱）
- quality_point: 质量控制要点（如：保护层厚度≥25mm、振捣密实不漏振）

## 关系类型

- requires_equipment: 工序 → 需要 → 设备
- produces_hazard: 工序 → 产生 → 危险源
- mitigated_by: 危险源 → 对应 → 安全措施
- requires_quality_check: 工序 → 要求 → 质量要点

## 要求

1. 只抽取文本中明确提到或可直接推断的实体和关系，不要过度推测
2. 实体名称使用简洁标准化表述（去掉"的""进行""工作"等虚词）
3. 每条关系必须附带原文证据（不超过50字）
4. 工序名称用动词+宾语格式（如"混凝土浇筑""钢筋绑扎"）
5. 如果文本中无可抽取的实体/关系，返回 {"entities": [], "relations": []}

## 输出格式

严格 JSON，不要包含 ```json 标记：
{"entities": [{"type": "...", "name": "...", "attributes": {}}], "relations": [{"source": "实体名", "target": "实体名", "type": "...", "evidence": "..."}]}"""

EXTRACTION_USER_TEMPLATE = """[工程类型: {engineering_type}] [章节: {chapter}]

{content}"""


# ---------------------------------------------------------------------------
# LLM 抽取器
# ---------------------------------------------------------------------------


class LLMExtractor:
    """通过 LLM 从非结构化施工方案片段中抽取实体和关系。

    Args:
        client: OpenAI 兼容客户端，为 None 时从全局配置创建
    """

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = OpenAI(
                api_key=app_config.LLM_CONFIG["api_key"],
                base_url=app_config.LLM_CONFIG["base_url"],
            )
        self._model = app_config.LLM_CONFIG["model"]

    # -------------------------------------------------------------------
    # 公开接口
    # -------------------------------------------------------------------

    def extract_from_fragments(
        self,
        fragments_path: Path | None = None,
    ) -> tuple[list[Entity], list[Relation]]:
        """从 fragments.jsonl 中抽取实体和关系。

        过滤条件：chapter ∈ EXTRACT_CHAPTERS 且 density ∈ EXTRACT_DENSITY。

        Args:
            fragments_path: JSONL 文件路径，默认使用配置路径

        Returns:
            (实体列表, 关系列表)
        """
        fragments_path = fragments_path or FRAGMENTS_PATH
        fragments = self._load_and_filter(fragments_path)
        log_msg("INFO", f"LLM 抽取: 共 {len(fragments)} 条待处理片段")

        if not fragments:
            return [], []

        all_entities: list[Entity] = []
        all_relations: list[Relation] = []
        errors = 0
        lock = threading.Lock()

        pbar = tqdm(
            total=len(fragments),
            desc="  LLM 抽取",
            unit="条",
            bar_format="  {l_bar}{bar:30}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )

        def _worker(frag: dict[str, Any]) -> None:
            nonlocal errors
            entities, relations = self._extract_single(frag)
            with lock:
                all_entities.extend(entities)
                all_relations.extend(relations)
                if not entities and not relations:
                    pass  # 空结果不算错误
                pbar.set_postfix_str(
                    f"E:{len(all_entities)} R:{len(all_relations)} err:{errors}"
                )
                pbar.update(1)

        with ThreadPoolExecutor(max_workers=LLM_MAX_WORKERS) as executor:
            futures = {executor.submit(_worker, f): f for f in fragments}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    with lock:
                        errors += 1
                        pbar.update(1)
                    log_msg("WARNING", f"LLM 抽取异常: {exc}")

        pbar.close()
        log_msg(
            "INFO",
            f"LLM 抽取完成: {len(all_entities)} 实体, {len(all_relations)} 关系, {errors} 失败",
        )
        return all_entities, all_relations

    # -------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------

    def _load_and_filter(self, path: Path) -> list[dict[str, Any]]:
        """加载 JSONL 并按章节和密度过滤。

        Args:
            path: fragments.jsonl 路径

        Returns:
            过滤后的片段列表
        """
        results: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                frag = json.loads(line)
                chapter = frag.get("chapter", "")
                density = frag.get("density", "")
                if chapter in EXTRACT_CHAPTERS and density in EXTRACT_DENSITY:
                    results.append(frag)
        return results

    def _extract_single(
        self, frag: dict[str, Any]
    ) -> tuple[list[Entity], list[Relation]]:
        """对单个片段调用 LLM 抽取。

        Args:
            frag: 知识片段字典

        Returns:
            (实体列表, 关系列表)
        """
        content = frag.get("content", "")[:LLM_CONTENT_MAX_CHARS]
        engineering_type = frag.get("engineering_type", "通用")
        chapter = frag.get("chapter", "")
        source_doc = frag.get("id", "unknown")

        user_msg = EXTRACTION_USER_TEMPLATE.format(
            engineering_type=engineering_type,
            chapter=chapter,
            content=content,
        )

        # 带重试的 LLM 调用
        for attempt in range(LLM_MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=LLM_TEMPERATURE,
                    max_tokens=2048,
                )
                text = response.choices[0].message.content or ""
                return self._parse_response(text, engineering_type, source_doc)
            except Exception:
                if attempt < LLM_MAX_RETRIES - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                raise

        return [], []

    def _parse_response(
        self,
        text: str,
        engineering_type: str,
        source_doc: str,
    ) -> tuple[list[Entity], list[Relation]]:
        """解析 LLM JSON 响应为实体和关系。

        容错策略：
        1. 直接 json.loads
        2. 正则提取 {...} 块
        3. 失败则返回空

        Args:
            text: LLM 原始响应文本
            engineering_type: 工程类型
            source_doc: 来源片段 ID

        Returns:
            (实体列表, 关系列表)
        """
        data = self._try_parse_json(text)
        if data is None:
            return [], []

        entities: list[Entity] = []
        relations: list[Relation] = []

        # 解析实体
        for item in data.get("entities", []):
            entity_type = item.get("type", "")
            name = item.get("name", "").strip()
            if not name or entity_type not in (
                "process",
                "equipment",
                "hazard",
                "safety_measure",
                "quality_point",
            ):
                continue
            entities.append(
                Entity(
                    type=entity_type,
                    name=name,
                    engineering_type=engineering_type,
                    attributes=item.get("attributes", {}),
                    source="llm",
                    confidence=0.8,
                )
            )

        # 解析关系
        for item in data.get("relations", []):
            rel_type = item.get("type", "")
            source_name = item.get("source", "").strip()
            target_name = item.get("target", "").strip()
            evidence = item.get("evidence", "").strip()
            if (
                not source_name
                or not target_name
                or rel_type
                not in (
                    "requires_equipment",
                    "produces_hazard",
                    "mitigated_by",
                    "requires_quality_check",
                )
            ):
                continue
            relations.append(
                Relation(
                    source_entity_id=source_name,
                    target_entity_id=target_name,
                    relation_type=rel_type,
                    confidence=0.8,
                    evidence=evidence[:80],
                    source_doc=source_doc,
                )
            )

        return entities, relations

    @staticmethod
    def _try_parse_json(text: str) -> dict[str, Any] | None:
        """尝试从文本中解析 JSON。

        Args:
            text: LLM 响应文本

        Returns:
            解析后的字典，失败返回 None
        """
        # 去除可能的 markdown 代码块标记
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 {...} 块
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None
