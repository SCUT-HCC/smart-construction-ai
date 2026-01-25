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
    SYSTEM_PROMPT = """
# System Prompt: Markdown Structural Optimizer

## Context
You are receiving a raw Markdown file generated from an OCR process. The text contains fragmented headers, flattened tables of contents, and broken paragraph flows.

## Core Directives
1. **Merge Headers**: If a header level (e.g., # or ##) is split across multiple lines, merge them into a single coherent line.
2. **Reconstruct TOC**: Convert long, single-paragraph Table of Contents into a nested Markdown list.
3. **Reflow Text**: Remove unnecessary line breaks within paragraphs. Ensure sentences flow naturally.
4. **Standardize Lists**: Ensure all list markers are consistent. One space after the marker.
5. **Preserve Content**: DO NOT summarize. DO NOT delete technical data, numbers, or tables.
6. **GFM Compliance**: Output must be valid GitHub Flavored Markdown.

## Handling Symbols
- Convert parenthetical numbers (1) or circled numbers at the start of lines to standard Markdown lists 1.
- Remove stray decoration symbols like math environments used for bullets.

## Output Format
- Return ONLY the cleaned Markdown content.
- NO conversational preambles like "Here is the cleaned content" or "I have processed the file".
- NO closing remarks.
"""

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
            
            # 检查是否为标题（简单启发式：以 # 开头）
            is_header = para.strip().startswith('#')
            
            # 截断条件：
            # 1. 加上当前段落会显著超过 chunk_size
            # 2. 当前段落是标题，且当前块已经有一定内容（比如超过 chunk_size 的 50%），则提前切分，让标题作为新块的开始
            if (current_length + para_len > self.chunk_size) or \
               (is_header and current_length > self.chunk_size * 0.5):
                
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(para)
            current_length += para_len + 2  # +2 for \n\n

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks

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
                cleaned_chunks.append(cleaned_text)
            except Exception as e:
                log_msg("ERROR", f"LLM 清洗块 {i+1} 异常: {str(e)}")
                # 发生错误时保留原始内容，避免数据丢失
                cleaned_chunks.append(chunk)
        
        return '\n\n'.join(cleaned_chunks)
