import re
from typing import List, Dict, Optional
from utils.logger_system import log_msg

class MarkdownVerifier:
    def __init__(self, min_length_ratio: float = 0.5, forbidden_phrases: List[str] | None = None):
        self.min_length_ratio = min_length_ratio
        self.forbidden_phrases = forbidden_phrases or []

    def verify(self, original_text: str, cleaned_text: str) -> Dict[str, bool]:
        results = {
            "length_check": self.check_length(original_text, cleaned_text),
            "hallucination_check": self.check_hallucination(cleaned_text),
            "structure_check": self.check_structure(cleaned_text)
        }
        
        all_passed = all(results.values())
        if not all_passed:
            log_msg("WARNING", f"验证未通过: {results}")
        else:
            log_msg("INFO", "结果验证通过。")
            
        return results

    def check_length(self, original: str, cleaned: str) -> bool:
        if not original:
            return True
        ratio = len(cleaned) / len(original)
        passed = ratio >= self.min_length_ratio
        if not passed:
            log_msg("WARNING", f"字数损失过大: 原始 {len(original)}, 清洗后 {len(cleaned)}, 比例 {ratio:.2f}")
        return passed

    def check_hallucination(self, text: str) -> bool:
        """检查是否有 LLM 对话性前缀（只检查行首出现的短语）。"""
        preamble_patterns = [
            r'^\s*好的[，,。！!：:\s]',
            r'^\s*以下是',
            r'^\s*当然[，,。！!：:\s]',
            r'^\s*我已为你',
            r'^\s*为您清洗',
            r'^\s*Here is the cleaned',
            r'^\s*Markdown\s*内容如下',
        ]
        for pattern in preamble_patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                matched_line = text[match.start():text.find('\n', match.start())]
                log_msg("WARNING", f"检测到幻觉短语: '{matched_line.strip()}'")
                return False
        for phrase in self.forbidden_phrases:
            pattern = r'^\s*' + re.escape(phrase)
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                matched_line = text[match.start():text.find('\n', match.start())]
                log_msg("WARNING", f"检测到禁用短语: '{matched_line.strip()}'")
                return False
        return True

    def check_structure(self, text: str) -> bool:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if '|' in line:
                if line.count('|') < 2:
                    log_msg("WARNING", f"结构检查失败：第 {i+1} 行表格管道符数量不足")
                    return False
        return True
