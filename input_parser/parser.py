"""S11 输入标准化解析器 — 三种输入形式统一为 StandardizedInput"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

import config as app_config
from cleaning import RegexCleaning
from crawler import MonkeyOCRClient
from input_parser.config import (
    EXTRACTION_MAX_RETRIES,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
)
from input_parser.models import (
    BasicInfo,
    ConstraintInfo,
    ParticipantInfo,
    StandardizedInput,
    TechnicalInfo,
)
from utils.logger_system import log_msg


# ═══════════════════════════════════════════════════════════════
# 辅助函数（模块级，_ 前缀）
# ═══════════════════════════════════════════════════════════════


def _dict_to_basic(data: dict[str, Any]) -> BasicInfo:
    """dict → BasicInfo，缺失字段用默认值。"""
    return BasicInfo(
        project_name=str(data.get("project_name", "")),
        project_type=str(data.get("project_type", "")),
        location=str(data.get("location", "")),
        scale=str(data.get("scale", "")),
    )


def _dict_to_technical(data: dict[str, Any]) -> TechnicalInfo:
    """dict → TechnicalInfo，缺失字段用默认值。"""
    return TechnicalInfo(
        geology=str(data.get("geology", "")),
        climate=str(data.get("climate", "")),
        special_requirements=str(data.get("special_requirements", "")),
    )


def _dict_to_participants(data: dict[str, Any]) -> ParticipantInfo:
    """dict → ParticipantInfo，缺失字段用默认值。"""
    return ParticipantInfo(
        owner=str(data.get("owner", "")),
        contractor=str(data.get("contractor", "")),
        supervisor=str(data.get("supervisor", "")),
        designer=str(data.get("designer", "")),
    )


def _dict_to_constraints(data: dict[str, Any]) -> ConstraintInfo:
    """dict → ConstraintInfo，缺失字段用默认值。"""
    raw_risks = data.get("risks", [])
    risks = [str(r) for r in raw_risks] if isinstance(raw_risks, list) else []
    return ConstraintInfo(
        timeline=str(data.get("timeline", "")),
        budget=str(data.get("budget", "")),
        risks=risks,
    )


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """从 LLM 响应文本中提取 JSON 对象。

    支持多种格式：纯 JSON、```json 包裹、混合文本中的 JSON。

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的 dict

    Raises:
        ValueError: 无法从文本中提取合法 JSON
    """
    text = text.strip()

    # 尝试 1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 2：提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试 3：提取第一个 { ... } 块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    msg = f"无法从 LLM 响应中提取合法 JSON: {text[:200]}"
    raise ValueError(msg)


# ═══════════════════════════════════════════════════════════════
# InputParser 主类
# ═══════════════════════════════════════════════════════════════


class InputParser:
    """输入标准化解析器。

    支持三种输入形式，统一输出 StandardizedInput：
    - JSON dict → 直接映射
    - 自然语言 str → LLM 提取
    - PDF 文件路径 → OCR 清洗 → LLM 提取

    Args:
        llm_client: OpenAI 兼容客户端（自然语言/PDF 路径需要）。
                   不传则从 config.LLM_CONFIG 自动创建。
        ocr_client: MonkeyOCR 客户端（PDF 路径需要）。
                   不传则从 config.MONKEY_OCR_CONFIG 自动创建。
    """

    def __init__(
        self,
        llm_client: OpenAI | None = None,
        ocr_client: MonkeyOCRClient | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._ocr_client = ocr_client

    def _get_llm_client(self) -> OpenAI:
        """懒加载 LLM 客户端。"""
        if self._llm_client is None:
            self._llm_client = OpenAI(
                api_key=app_config.LLM_CONFIG["api_key"],
                base_url=app_config.LLM_CONFIG["base_url"],
            )
        return self._llm_client

    def _get_ocr_client(self) -> MonkeyOCRClient:
        """懒加载 OCR 客户端。"""
        if self._ocr_client is None:
            self._ocr_client = MonkeyOCRClient(
                base_url=app_config.MONKEY_OCR_CONFIG["base_url"],
                timeout=app_config.MONKEY_OCR_CONFIG["timeout"],
            )
        return self._ocr_client

    # ---------------------------------------------------------------
    # 公开接口
    # ---------------------------------------------------------------

    def parse(self, source: str | dict[str, Any]) -> StandardizedInput:
        """自动路由到对应解析方法。

        Args:
            source: JSON dict / 自然语言文本 / PDF 文件路径

        Returns:
            StandardizedInput 实例

        路由逻辑：
        - dict → parse_json()
        - str 且 .pdf 后缀 → parse_pdf()
        - 其他 str → parse_text()
        """
        if isinstance(source, dict):
            return self.parse_json(source)
        if isinstance(source, str):
            if source.lower().endswith(".pdf"):
                return self.parse_pdf(source)
            return self.parse_text(source)
        log_msg("ERROR", f"不支持的输入类型: {type(source).__name__}")
        # log_msg("ERROR", ...) 会抛异常，此处不会到达
        raise TypeError  # pragma: no cover

    def parse_json(self, data: dict[str, Any]) -> StandardizedInput:
        """JSON dict 直接映射为 StandardizedInput。

        未知字段忽略，缺失字段用默认值。

        Args:
            data: 输入字典，顶层键应为 basic/technical/participants/constraints

        Returns:
            StandardizedInput 实例
        """
        basic = _dict_to_basic(data.get("basic", {}))
        technical = _dict_to_technical(data.get("technical", {}))
        participants = _dict_to_participants(data.get("participants", {}))
        constraints = _dict_to_constraints(data.get("constraints", {}))

        result = StandardizedInput(
            basic=basic,
            technical=technical,
            participants=participants,
            constraints=constraints,
        )

        errors = result.validate()
        if errors:
            log_msg("WARNING", f"输入校验警告: {'; '.join(errors)}")

        return result

    def parse_text(self, text: str) -> StandardizedInput:
        """自然语言文本 → LLM 提取 JSON → parse_json()。

        Args:
            text: 自然语言描述或 OCR 清洗后的 Markdown 文本

        Returns:
            StandardizedInput 实例
        """
        if not text.strip():
            log_msg("WARNING", "输入文本为空，返回默认 StandardizedInput")
            return StandardizedInput()

        client = self._get_llm_client()
        prompt = EXTRACTION_USER_TEMPLATE.format(text=text)

        for attempt in range(EXTRACTION_MAX_RETRIES + 1):
            try:
                response = client.chat.completions.create(
                    model=app_config.LLM_CONFIG["model"],
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=app_config.LLM_CONFIG["temperature"],
                )
                raw_text = response.choices[0].message.content or ""
                extracted = _extract_json_from_response(raw_text)
                return self.parse_json(extracted)
            except (ValueError, json.JSONDecodeError) as e:
                if attempt < EXTRACTION_MAX_RETRIES:
                    log_msg("WARNING", f"LLM 提取第 {attempt + 1} 次失败，重试: {e}")
                    continue
                log_msg(
                    "ERROR",
                    f"LLM 提取结果解析失败（已重试 {EXTRACTION_MAX_RETRIES} 次）: {e}",
                )

        # 不可达，log_msg("ERROR") 已抛异常
        raise RuntimeError  # pragma: no cover

    def parse_pdf(self, pdf_path: str) -> StandardizedInput:
        """PDF → OCR 清洗 → Markdown → LLM 提取 → StandardizedInput。

        复用现有 OCR 管道（crawler.MonkeyOCRClient + cleaning.RegexCleaning），
        获取清洗后的 Markdown 文本，然后通过 parse_text() 的 LLM 提取流程。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            StandardizedInput 实例
        """
        if not os.path.exists(pdf_path):
            log_msg("ERROR", f"PDF 文件不存在: {pdf_path}")

        log_msg("INFO", f"开始解析 PDF: {pdf_path}")

        # OCR 识别
        ocr_client = self._get_ocr_client()
        raw_md = ocr_client.to_markdown(pdf_path)
        if not raw_md:
            log_msg("ERROR", "OCR 识别结果为空")

        # 正则清洗（跳过 LLM 清洗，后续 parse_text 会做 LLM 提取）
        regex_cleaner = RegexCleaning(app_config.CLEANING_CONFIG["regex_patterns"])
        cleaned_md = regex_cleaner.clean(raw_md)

        log_msg("INFO", f"PDF OCR 清洗完成，文本长度: {len(cleaned_md)}")
        return self.parse_text(cleaned_md)
