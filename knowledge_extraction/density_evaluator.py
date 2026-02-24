"""知识密度评估器 — 纯 LLM 评估每个片段的信息密度。

所有片段统一由 LLM 判定 high/medium/low，不做规则预筛。
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from openai import OpenAI
from tqdm import tqdm

from utils.logger_system import log_msg
import config as app_config
from knowledge_extraction.config import LLM_MAX_WORKERS


DENSITY_SYSTEM_PROMPT = """你是一位南方电网施工方案知识工程师。请评估以下施工方案片段的知识密度等级。

## 评估标准

**high（高密度）** — 包含可直接复用的具体技术知识：
- 具体数值、参数、指标（如 "拧紧力矩不小于300N·m"、"保护层厚度25mm"）
- 标准工艺流程步骤（如 "测量定位→埋设护筒→钻孔→清孔→钢筋笼下放→混凝土灌注"）
- 标准编号引用（如 "GB 50300-2013"、"DL/T 5210-2018"）
- 设备参数表、材料规格表、风险评价表
- 具体的安全措施或质量控制要点（含操作细节）

**medium（中密度）** — 包含有用信息但混合了通用/冗余描述：
- 有价值的技术内容被套话稀释
- 结构合理但措辞冗余
- 可通过精简改写提升密度

**low（低密度）** — 应当丢弃：
- 空洞描述、套话（"加强管理"、"确保质量"、"高度重视"）
- 工程特有信息（特定项目名称如"茂名500kV电白变电站"、人名、日期、编号）
- 报审表/签字栏/行政流程残留
- OCR 噪声残留（乱码、LaTeX 符号残留）
- 内容太短无法构成完整知识点

## 重要原则
- "可复用"是核心判据：换一个工程还能用的就是有价值的
- 只有项目特有信息才归为 low，通用技术知识即使表述不完美也至少是 medium"""


DENSITY_USER_TEMPLATE = """## 待评估片段

章节: {chapter}
子章节: {section}
工程类型: {engineering_type}

---
{content}
---

请严格以 JSON 格式回复（不要包含 ```json 标记）：
{{"density": "high 或 medium 或 low", "reason": "一句话评估理由"}}"""


class DensityEvaluator:
    """通过 LLM 评估知识片段密度。

    所有片段均调用 LLM 判定，不做规则预筛。
    返回 density（high/medium/low）和 reason（评估理由）。
    """

    def __init__(self, client: Optional[OpenAI] = None):
        """初始化 LLM 客户端。

        Args:
            client: OpenAI 客户端实例，为 None 时从 app_config 创建
        """
        if client is not None:
            self._client = client
        else:
            self._client = OpenAI(
                api_key=app_config.LLM_CONFIG["api_key"],
                base_url=app_config.LLM_CONFIG["base_url"],
            )
        self._model = app_config.LLM_CONFIG["model"]

    def evaluate(self, fragments: List[Dict]) -> List[Dict]:
        """为每个片段并发评估密度。

        使用 ThreadPoolExecutor 并发调用 LLM API，线程数由 LLM_MAX_WORKERS 控制。

        Args:
            fragments: MetadataAnnotator 输出的字典列表

        Returns:
            同一列表，每个字典新增 density 和 density_reason 字段
        """
        total = len(fragments)
        counts = {"high": 0, "medium": 0, "low": 0}
        api_errors = 0
        lock = threading.Lock()

        print(f"  并发线程数: {LLM_MAX_WORKERS}")

        pbar = tqdm(
            total=total,
            desc="  密度评估",
            unit="条",
            bar_format="  {l_bar}{bar:30}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )

        def _worker(idx: int) -> None:
            nonlocal api_errors
            frag = fragments[idx]
            density, reason = self._evaluate_single(frag)
            frag["density"] = density
            frag["density_reason"] = reason

            with lock:
                counts[density] = counts.get(density, 0) + 1
                if "调用失败" in reason:
                    api_errors += 1
                pbar.set_postfix_str(
                    f"H:{counts['high']} M:{counts['medium']} L:{counts['low']} "
                    f"err:{api_errors}"
                )
                pbar.update(1)

        with ThreadPoolExecutor(max_workers=LLM_MAX_WORKERS) as executor:
            futures = [executor.submit(_worker, i) for i in range(total)]
            for future in as_completed(futures):
                # 触发异常传播（如有）
                future.result()

        pbar.close()
        print(
            f"  密度评估结果: high={counts['high']}, "
            f"medium={counts['medium']}, low={counts['low']}, "
            f"API错误={api_errors}"
        )
        return fragments

    def _evaluate_single(self, frag: Dict) -> tuple:
        """对单个片段调用 LLM 评估密度。

        Args:
            frag: 单个知识片段字典

        Returns:
            (density, reason) 元组
        """
        user_msg = DENSITY_USER_TEMPLATE.format(
            chapter=frag.get("chapter", ""),
            section=frag.get("section", ""),
            engineering_type=frag.get("engineering_type", ""),
            content=frag.get("content", "")[:3000],  # 限制长度避免超 token
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": DENSITY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=200,
            )
            text = resp.choices[0].message.content or ""
            return self._parse_response(text)
        except Exception as e:
            log_msg(
                "WARNING",
                f"LLM 密度评估失败 (DOC {frag.get('source_doc')}, "
                f"{frag.get('section')}): {e}，默认标记为 medium",
            )
            return "medium", "LLM 调用失败，默认 medium"

    def _parse_response(self, text: str) -> tuple:
        """解析 LLM 返回的 JSON。

        Args:
            text: LLM 原始返回文本

        Returns:
            (density, reason) 元组
        """
        # 清理可能的 markdown 代码块标记
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            density = data.get("density", "medium")
            reason = data.get("reason", "")
            if density not in ("high", "medium", "low"):
                density = "medium"
            return density, reason
        except (json.JSONDecodeError, KeyError):
            # 尝试从文本中提取 density
            for level in ("high", "medium", "low"):
                if level in text.lower():
                    return level, f"JSON 解析失败，从文本提取: {text[:100]}"
            return "medium", f"JSON 解析失败: {text[:100]}"
