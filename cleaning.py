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
        "8. 删除 OCR 残留的水印文字，如 'CHINA SOUTHERN POWER GRID' 及其变体（可能跨行出现）\n"
        "\n"
        "## 标题层级规范\n"
        "根据原文的层级结构合理分配标题级别：\n"
        "- 文档标题（封面标题、总标题）使用 `#`（H1），整篇文档最多 1-2 个 H1\n"
        "- 章节标题（如 '第一章'、'一、'、'1.'）使用 `##`（H2）\n"
        "- 子节标题（如 '1.1'、'（一）'）使用 `###`（H3）\n"
        "- 更细的小节使用 `####`（H4）\n"
        "- 不要将所有标题都设为同一级别\n"
        "\n"
        "## 输出格式\n"
        "直接输出 GitHub Flavored Markdown。第一个字符必须是原文内容的一部分。"
    )

    # --- LaTeX symbol → Unicode mapping ---
    # Only simple symbol-level LaTeX; complex math formulas are preserved.
    LATEX_SYMBOL_MAP = {
        r'\star': '★',
        r'\bigstar': '★',
        r'\geqslant': '≥',
        r'\leqslant': '≤',
        r'\geq': '≥',
        r'\leq': '≤',
        r'\ge': '≥',
        r'\le': '≤',
        r'\times': '×',
        r'\pm': '±',
        r'\mp': '∓',
        r'\approx': '≈',
        r'\neq': '≠',
        r'\ne': '≠',
        r'\rightarrow': '→',
        r'\leftarrow': '←',
        r'\leftrightarrow': '↔',
        r'\Rightarrow': '⇒',
        r'\Leftarrow': '⇐',
        r'\uparrow': '↑',
        r'\downarrow': '↓',
        r'\infty': '∞',
        r'\degree': '°',
        r'\circ': '°',
        r'\alpha': 'α',
        r'\beta': 'β',
        r'\gamma': 'γ',
        r'\delta': 'δ',
        r'\epsilon': 'ε',
        r'\theta': 'θ',
        r'\lambda': 'λ',
        r'\mu': 'μ',
        r'\pi': 'π',
        r'\sigma': 'σ',
        r'\omega': 'ω',
        r'\phi': 'φ',
        r'\psi': 'ψ',
        r'\rho': 'ρ',
        r'\tau': 'τ',
        r'\chi': 'χ',
        r'\Delta': 'Δ',
        r'\Sigma': 'Σ',
        r'\Omega': 'Ω',
        r'\Pi': 'Π',
        r'\Phi': 'Φ',
        r'\sqrt': '√',
        r'\cdot': '·',
        r'\bullet': '•',
        r'\div': '÷',
        r'\sim': '~',
        r'\propto': '∝',
        r'\perp': '⊥',
        r'\parallel': '∥',
        r'\subset': '⊂',
        r'\supset': '⊃',
        r'\subseteq': '⊆',
        r'\supseteq': '⊇',
        r'\in': '∈',
        r'\notin': '∉',
        r'\cup': '∪',
        r'\cap': '∩',
        r'\emptyset': '∅',
        r'\forall': '∀',
        r'\exists': '∃',
        r'\neg': '¬',
        r'\land': '∧',
        r'\lor': '∨',
        r'\triangle': '△',
        r'\square': '□',
        r'\boxdot': '☑',
        r'\checkmark': '✓',
    }

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

    @classmethod
    def _convert_latex_symbols(cls, text: str) -> str:
        """Convert simple LaTeX symbol expressions to Unicode characters.
        
        Handles patterns like:
        - $\symbol$ → unicode
        - $\symbol$ with surrounding text preserved
        - Degree patterns like $45^{\circ}$ → 45°
        """
        # Handle degree patterns first: $45^{\circ}$, $90^{\circ}$, etc.
        text = re.sub(
            r'\$\s*(\d+)\s*\^\s*\{?\s*\\circ\s*\}?\s*\$',
            r'\1°',
            text
        )
        # Handle standalone $\circ$ → °
        text = re.sub(r'\$\s*\\circ\s*\$', '°', text)
        
        # Handle $^\circ$ pattern (degree without number)
        text = re.sub(r'\$\s*\^\s*\{?\s*\\circ\s*\}?\s*\$', '°', text)
        
        # Sort by length (longest first) to avoid partial matches
        # e.g., \geqslant before \geq
        sorted_symbols = sorted(cls.LATEX_SYMBOL_MAP.keys(), key=len, reverse=True)
        
        for latex_cmd in sorted_symbols:
            unicode_char = cls.LATEX_SYMBOL_MAP[latex_cmd]
            # Escape the backslash for regex
            escaped = re.escape(latex_cmd)
            # Match $\cmd$ with optional surrounding whitespace inside $...$
            # This pattern matches the symbol wrapped in $ delimiters
            pattern = r'\$\s*' + escaped + r'\s*\$'
            text = re.sub(pattern, unicode_char, text)
        
        # Handle $\symbol VALUE$ patterns (e.g. $\leq 0.5$ → ≤0.5, $\geq 40$ → ≥40)
        # Only for comparison/relation symbols followed by simple values
        comparison_symbols = {
            r'\geqslant': '≥', r'\leqslant': '≤',
            r'\geq': '≥', r'\leq': '≤',
            r'\ge': '≥', r'\le': '≤',
            r'\approx': '≈', r'\neq': '≠', r'\ne': '≠',
        }
        sorted_comp = sorted(comparison_symbols.keys(), key=len, reverse=True)
        for latex_cmd in sorted_comp:
            unicode_char = comparison_symbols[latex_cmd]
            escaped = re.escape(latex_cmd)
            # Match $\cmd VALUE$ where VALUE is simple (numbers, dots, %, letters)
            pattern = r'\$\s*' + escaped + r'\s*([0-9][0-9a-zA-Z.,%]*)\s*\$'
            text = re.sub(pattern, unicode_char + r'\1', text)
        
        return text

    @staticmethod
    def _fix_table_separators(text: str) -> str:
        """Fix abnormally long table separator lines.
        
        Handles:
        1. Lines like |---|---|...| where dashes are excessively long
        2. Lines starting with | but not ending with | (broken separators)
        3. Pure dash lines (---...---) without pipes
        """
        lines = text.split('\n')
        fixed_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Case 1: Line with pipes that looks like a table separator
            # Match lines that are mostly dashes, pipes, colons, and spaces
            if '|' in stripped and len(stripped) > 500:
                # Check if it's a separator line (mostly -|: characters)
                non_sep_chars = re.sub(r'[\s\-|:]', '', stripped)
                if len(non_sep_chars) < len(stripped) * 0.05:  # >95% separator chars
                    # Compress each cell's dashes to exactly ---
                    fixed = re.sub(r'-{3,}', '---', stripped)
                    fixed_lines.append(fixed)
                    continue
            
            # Case 2: Pipe-delimited separator line (normal length check too)
            if re.match(r'^\|[\s\-:|]+\|?$', stripped) and len(stripped) > 200:
                fixed = re.sub(r'-{3,}', '---', stripped)
                # Ensure it ends with |
                if not fixed.endswith('|'):
                    fixed += '|'
                fixed_lines.append(fixed)
                continue
            
            # Case 3: Pure dash lines (no pipes) that are excessively long
            if re.match(r'^-{50,}$', stripped):
                fixed_lines.append('---')
                continue
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    @staticmethod
    def _clean_html_tags(text: str) -> str:
        """Clean residual HTML tags from OCR output.
        
        - Convert simple HTML tables to GFM Markdown tables
        - Remove other HTML tags while preserving inner text
        """
        # --- Convert HTML tables to Markdown ---
        def _html_table_to_markdown(match: re.Match) -> str:
            """Convert a simple HTML <table>...</table> to GFM markdown."""
            table_html = match.group(0)
            
            try:
                # Extract rows
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
                if not rows:
                    return table_html  # Can't parse, return as-is
                
                md_rows = []
                max_cols = 0
                
                for row in rows:
                    # Extract cells (td or th)
                    cells = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', row, re.DOTALL)
                    if not cells:
                        continue
                    
                    # Clean cell content: remove inner HTML tags, normalize whitespace
                    cleaned_cells = []
                    for cell in cells:
                        # Remove <br> tags → space
                        cell = re.sub(r'<br\s*/?>', ' ', cell)
                        # Remove <sup>, <sub> etc. but keep text
                        cell = re.sub(r'<[^>]+>', '', cell)
                        # Normalize whitespace
                        cell = ' '.join(cell.split())
                        cleaned_cells.append(cell.strip())
                    
                    if cleaned_cells:
                        max_cols = max(max_cols, len(cleaned_cells))
                        md_rows.append(cleaned_cells)
                
                if not md_rows:
                    return ''
                
                # Pad rows to max_cols
                for i in range(len(md_rows)):
                    while len(md_rows[i]) < max_cols:
                        md_rows[i].append('')
                
                # Build markdown table
                result_lines = []
                # First row as header
                result_lines.append('| ' + ' | '.join(md_rows[0]) + ' |')
                # Separator
                result_lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')
                # Data rows
                for row in md_rows[1:]:
                    result_lines.append('| ' + ' | '.join(row) + ' |')
                
                return '\n'.join(result_lines)
            
            except Exception:
                # If parsing fails, just strip the tags
                cleaned = re.sub(r'<[^>]+>', ' ', table_html)
                return ' '.join(cleaned.split())
        
        # Convert HTML tables to Markdown
        text = re.sub(
            r'<table[^>]*>.*?</table>',
            _html_table_to_markdown,
            text,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # Remove any remaining HTML tags (preserve inner text)
        # Common self-closing tags
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<hr\s*/?>', '\n---\n', text, flags=re.IGNORECASE)
        # Remove <sup>text</sup> → text (keep text)
        text = re.sub(r'</?(?:sup|sub|em|strong|b|i|u|s|span|div|p|font)[^>]*>', '', text, flags=re.IGNORECASE)
        # Remove any other remaining HTML tags
        text = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*[^>]*>', '', text, flags=re.IGNORECASE)
        
        return text

    @classmethod
    def _post_process(cls, text: str) -> str:
        """对 LLM 输出进行后处理：移除对话前缀/后缀、修复异常表格行、转换LaTeX符号、清理HTML。"""
        
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
        
        # --- 3. 移除残留水印 ---
        text = re.sub(
            r'(?i)CHINA\s+SOUTHERN\s+POWER\s+GRID(?:\s+CO\.?\s*,?\s*LTD\.?)?\s*',
            '', text
        )
        
        # --- 4. 移除代码块包裹 ---
        text = re.sub(r'^\s*```(?:markdown)?\s*\n', '', text)
        text = re.sub(r'\n\s*```\s*$', '', text)
        
        # --- 5. 修复异常长的表格分隔行 ---
        text = cls._fix_table_separators(text)
        
        # --- 6. LaTeX 符号 → Unicode 转换 ---
        text = cls._convert_latex_symbols(text)
        
        # --- 7. 清理残留 HTML 标签 ---
        text = cls._clean_html_tags(text)
        
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
                log_msg("WARNING", f"LLM 清洗块 {i+1} 异常，降级保留原文: {str(e)}")
                cleaned_chunks.append(chunk)
        
        return '\n\n'.join(cleaned_chunks)
