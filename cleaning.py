import re
from typing import List, Tuple
from openai import OpenAI
from utils.logger_system import log_msg

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

    def clean(self, content: str) -> str:
        log_msg("INFO", f"正在使用模型 {self.model} 进行 LLM 语义清洗...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ],
                temperature=self.temperature
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            log_msg("ERROR", f"LLM 清洗异常: {str(e)}")
            return content
