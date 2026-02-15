LLM_CONFIG = {
    "api_key": "sk-UiUarItJQtYeyT8D0f0c59D674C14439B4082677766f3bA3",
    "base_url": "http://110.42.53.85:11081/v1",
    "model": "deepseek-chat",
    "temperature": 0.1,
    "max_tokens": 4096,
    "chunk_size": 2000,
}

MONKEY_OCR_CONFIG = {
    "base_url": "http://localhost:7861",
    "timeout": 120,
}

PATHS = {
    "input_dir": "data",
    "output_dir": "output",
    "log_dir": "logs",
}

CLEANING_CONFIG = {
    "remove_watermark": True,
    "company_name": "CHINA SOUTHERN POWER GRID CO., LTD.",
    "regex_patterns": [
        (r'^\s*\$\\textcircled\{(\d+)\}\$\s*', r'\1. '),
        (r'\$\\textcircled\{(\d+)\}\$', r'(\1)'),
        (r'(?<=\S)  \n', r'\n'),
        (r'(?i)CHINA\s+SOUTHERN\s+POWER\s+GRID(?:\s+CO\.?\s*,?\s*LTD\.?)?\s*', ''),
        (r'^\s*[批★]\s*$\n', ''),
        (r'^\s*\d+\s*$\n', ''),
    ]
}

VERIFY_CONFIG = {
    "min_length_ratio": 0.5,
    "check_closed_tables": True,
    "forbidden_phrases": [
        "好的", "我已为你", "为您清洗", "Here is the cleaned", "Markdown 内容如下"
    ]
}
