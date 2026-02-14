import re
from typing import List, Tuple
from openai import OpenAI
from utils.logger_system import log_msg
import config

class RegexCleaning:
    def __init__(self, patterns: List[Tuple[str, str]]):
        self.patterns = patterns

    def clean(self, content: str) -> str:
        log_msg("INFO", "开始执行正则清洗...")
        for pattern, replacement in self.patterns:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

class LLMCleaning:
    SYSTEM_PROMPT = (
        "你是一个纯文本处理管道。输入是 OCR 生成的 Markdown 片段，输出是格式优化后的 Markdown。\n"
        "\n"
        "## 绝对禁止\n"
        "- 禁止输出任何对话性语言，包括但不限于：好的、以下是、当然、我来、为您、没问题、"
        "收到、明白、可以的、让我、下面是、请看、处理完成、优化如下\n"
        "- 禁止输出任何前缀说明或后缀总结\n"
        "- 禁止添加、删除或改写任何实质性内容\n"
        "- 禁止用 ```markdown``` 代码块包裹输出\n"
        "\n"
        "## 允许的操作（仅限以下）\n"
        "1. 合并被 OCR 拆分到多行的标题\n"
        "2. 将扁平目录重构为嵌套 Markdown 列表\n"
        "3. 移除段落内不必要的换行，使句子连贯\n"
        "4. 统一列表标记格式\n"
        "5. 将行首带圆圈数字或括号数字转为标准有序列表\n"
        "6. 移除装饰性符号\n"
        "7. 修复明显的 Markdown 表格格式问题（表头分隔行每列只需 3 个短横线）\n"
        "\n"
        "## 输出格式\n"
        "直接输出 GitHub Flavored Markdown。第一个字符必须是原文内容的一部分。"
    )

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.1):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.chunk_size = config.LLM_CONFIG.get("chunk_size", 2000)

    def _chunk_text(self, content: str) -> List[str]:
        """
        基于段落的智能分块策略。
        1. 按双换行(\n\n)分割段落。
        2. 累积段落直到达到 chunk_size。
        3. 若检测到 Markdown 标题且当前块已有内容，提前截断以保持结构完整。
        """
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)
            
            is_header = para.strip().startswith('#')
            
            if (current_length + para_len > self.chunk_size) or \
               (is_header and current_length > self.chunk_size * 0.5):
                
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(para)
            current_length += para_len + 2

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks

    @staticmethod
    def _post_process(text: str) -> str:
        """对 LLM 输出进行后处理：移除对话前缀/后缀、修复异常表格行。"""
        
        # --- 1. 移除 LLM 对话性前缀 ---
        preamble_patterns = [
            r'^\s*好的[，,。！!：:\s]*',
            r'^\s*以下是[^\n]*[：:\n]',
            r'^\s*当然[，,。！!：:\s]*',
            r'^\s*我来[^\n]*[：:\n]',
            r'^\s*为[您你][^\n]*[：:\n]',
            r'^\s*没问题[，,。！!：:\s]*',
            r'^\s*收到[，,。！!：:\s]*',
            r'^\s*明白[，,。！!：:\s]*',
            r'^\s*可以的?[，,。！!：:\s]*',
            r'^\s*让我[^\n]*[：:\n]',
            r'^\s*下面是[^\n]*[：:\n]',
            r'^\s*请看[^\n]*[：:\n]',
            r'^\s*处理完成[^\n]*[：:\n]',
            r'^\s*优化如下[^\n]*[：:\n]',
            r'^\s*Here is[^\n]*[:\n]',
            r'^\s*Sure[,!.:\s]*',
            r'^\s*I have[^\n]*[:\n]',
            r'^\s*The following[^\n]*[:\n]',
            r'^\s*Markdown\s*内容如下[：:\s]*',
        ]
        for pattern in preamble_patterns:
            text = re.sub(pattern, '', text, count=1)
        
        # --- 2. 移除 LLM 对话性后缀 ---
        suffix_patterns = [
            r'\n\s*以上是[^\n]*$',
            r'\n\s*希望[^\n]*$',
            r'\n\s*如[有需][^\n]*$',
            r'\n\s*处理完成[^\n]*$',
        ]
        for pattern in suffix_patterns:
            text = re.sub(pattern, '', text)
        
        # --- 3. 移除代码块包裹 ---
        text = re.sub(r'^\s*```(?:markdown)?\s*\n', '', text)
        text = re.sub(r'\n\s*```\s*$', '', text)
        
        # --- 4. 修复异常长的表格分隔行 ---
        # 正常的 GFM 表格分隔行每个单元格只需 3 个短横线
        # 如果某行是纯表格分隔行且超过 500 字符，则压缩之
        def _fix_table_separator(match: re.Match) -> str:
            line = match.group(0)
            # 将每个单元格中过长的 ----- 压缩为 ---
            fixed = re.sub(r'-{3,}', '---', line)
            return fixed
        
        text = re.sub(r'^\|[\s\-:|]+\|$', _fix_table_separator, text, flags=re.MULTILINE)
        
        return text.strip()

    def clean(self, content: str) -> str:
        log_msg("INFO", f"正在使用模型 {self.model} 进行 LLM 语义清洗...")
        
        chunks = self._chunk_text(content)
        log_msg("INFO", f"分块逻辑启动: 共 {len(chunks)} 个块 (Chunk Size: {self.chunk_size})")
        
        cleaned_chunks = []
        for i, chunk in enumerate(chunks):
            log_msg("INFO", f"正在处理第 {i+1}/{len(chunks)} 个块 (长度: {len(chunk)})...")
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": chunk}
                    ],
                    temperature=self.temperature
                )
                cleaned_text = response.choices[0].message.content or ""
                cleaned_text = self._post_process(cleaned_text)
                cleaned_chunks.append(cleaned_text)
            except Exception as e:
                log_msg("ERROR", f"LLM 清洗块 {i+1} 异常: {str(e)}")
                cleaned_chunks.append(chunk)
        
        return '\n\n'.join(cleaned_chunks)
