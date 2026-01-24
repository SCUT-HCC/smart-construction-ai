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
        for phrase in self.forbidden_phrases:
            if phrase in text:
                log_msg("WARNING", f"检测到幻觉短语: '{phrase}'")
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
