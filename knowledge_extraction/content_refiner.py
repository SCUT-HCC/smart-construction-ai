"""内容改写器 — 对中密度片段进行 LLM 精简改写。

改写后保留原始文本（raw_content），标注 is_refined=true。
改写后字数 < REFINE_MIN_CHARS 则降级为 low。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from openai import OpenAI
from tqdm import tqdm

from utils.logger_system import log_msg
import config as app_config
from knowledge_extraction.config import REFINE_MIN_CHARS, LLM_MAX_WORKERS


REFINE_SYSTEM_PROMPT = """你是一位南方电网施工方案知识工程师。以下施工方案片段被评定为"中密度"——包含有用技术知识但混合了冗余描述。

请改写精简此片段，遵循以下原则：
1. **保留所有具体技术内容**：数值、参数、工艺步骤、标准编号、设备型号
2. **删除套话和空洞描述**：如"加强管理""严格执行""高度重视"等无信息量的表述
3. **删除工程特有信息**：具体项目名称（如"茂名500kV电白变电站"）、人名、日期、编号，替换为通用描述或直接删除
4. **保留表格结构**：如有 Markdown 表格，保持格式不变
5. **保持专业性**：措辞精准，符合施工方案技术文档风格
6. **不添加新内容**：只做精简，不补充原文没有的信息

直接输出改写后的文本，不要包含任何解释、前缀或后缀。"""


REFINE_USER_TEMPLATE = """章节: {chapter}
工程类型: {engineering_type}

---
{content}
---"""


class ContentRefiner:
    """对 density=medium 的片段进行 LLM 改写精简。

    - 仅处理 density="medium" 的片段
    - 改写后 content 更新为精简版本
    - raw_content 始终保留原始文本
    - is_refined 标记是否经过改写
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

    def refine(self, fragments: List[Dict]) -> List[Dict]:
        """对中密度片段并发改写精简。

        使用 ThreadPoolExecutor 并发调用 LLM API，线程数由 LLM_MAX_WORKERS 控制。

        Args:
            fragments: DensityEvaluator 输出的字典列表（含 density 字段）

        Returns:
            同一列表，medium 片段的 content 更新为改写版本，
            新增 is_refined 字段
        """
        medium_indices = [
            i for i, f in enumerate(fragments) if f.get("density") == "medium"
        ]
        total_medium = len(medium_indices)

        demoted_count = 0
        refined_ok = 0
        api_errors = 0
        lock = threading.Lock()

        print(f"  并发线程数: {LLM_MAX_WORKERS}")

        pbar = tqdm(
            total=total_medium,
            desc="  内容改写",
            unit="条",
            bar_format="  {l_bar}{bar:30}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )

        def _worker(frag_idx: int) -> None:
            nonlocal demoted_count, refined_ok, api_errors
            frag = fragments[frag_idx]
            refined_text = self._refine_single(frag)

            with lock:
                if refined_text and len(refined_text) >= REFINE_MIN_CHARS:
                    frag["content"] = refined_text
                    frag["is_refined"] = True
                    frag["char_count"] = len(refined_text)
                    refined_ok += 1
                elif refined_text and len(refined_text) < REFINE_MIN_CHARS:
                    frag["density"] = "low"
                    frag["density_reason"] += "；改写后字数不足，降级为 low"
                    frag["is_refined"] = True
                    frag["content"] = refined_text
                    frag["char_count"] = len(refined_text)
                    demoted_count += 1
                else:
                    frag["is_refined"] = False
                    api_errors += 1

                pbar.set_postfix_str(
                    f"ok:{refined_ok} demote:{demoted_count} err:{api_errors}"
                )
                pbar.update(1)

        with ThreadPoolExecutor(max_workers=LLM_MAX_WORKERS) as executor:
            futures = [executor.submit(_worker, idx) for idx in medium_indices]
            for future in as_completed(futures):
                future.result()

        pbar.close()

        # 对非 medium 片段设置 is_refined=false
        for frag in fragments:
            if "is_refined" not in frag:
                frag["is_refined"] = False

        print(
            f"  改写结果: 成功 {refined_ok}, "
            f"降级 {demoted_count}, 失败 {api_errors}"
        )
        return fragments

    def _refine_single(self, frag: Dict) -> Optional[str]:
        """对单个片段调用 LLM 改写。

        Args:
            frag: 单个知识片段字典

        Returns:
            改写后的文本，失败时返回 None
        """
        user_msg = REFINE_USER_TEMPLATE.format(
            chapter=frag.get("chapter", ""),
            engineering_type=frag.get("engineering_type", ""),
            content=frag.get("raw_content", frag.get("content", ""))[:3000],
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": REFINE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content or ""
            return text.strip()
        except Exception as e:
            log_msg(
                "WARNING",
                f"LLM 改写失败 (DOC {frag.get('source_doc')}, "
                f"{frag.get('section')}): {e}",
            )
            return None
