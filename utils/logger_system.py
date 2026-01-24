import json
import logging
import os
from datetime import datetime

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nanwang")

def log_msg(level: str, msg: str):
    """
    记录文本日志。如果级别为 ERROR，则抛出异常。
    
    Args:
        level: 日志级别 (INFO, WARNING, ERROR)
        msg: 日志内容
    """
    level = level.upper()
    if level == "INFO":
        logger.info(msg)
    elif level == "WARNING":
        logger.warning(msg)
    elif level == "ERROR":
        logger.error(msg)
        raise Exception(msg)
    else:
        logger.info(f"[{level}] {msg}")

def log_json(data: dict, filename: str = "task_log.json"):
    """
    将结构化数据记录到 JSON 文件中。
    
    Args:
        data: 要记录的字典数据
        filename: 保存的 JSON 文件名
    """
    data_with_time = {
        "timestamp": datetime.now().isoformat(),
        **data
    }
    
    # 简单的追加逻辑
    mode = 'a' if os.path.exists(filename) else 'w'
    with open(filename, mode, encoding='utf-8') as f:
        f.write(json.dumps(data_with_time, ensure_ascii=False) + "\n")
