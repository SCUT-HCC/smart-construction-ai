import argparse
import os
import config
from crawler import MonkeyOCRClient
from cleaning import RegexCleaning, LLMCleaning
from verifier import MarkdownVerifier
from processor import PDFProcessor
from utils.logger_system import log_msg

def parse_args():
    parser = argparse.ArgumentParser(description="PDF 处理全流程工具 (OCR -> 清洗 -> 验证)")
    
    parser.add_argument("--api_key", type=str, default=config.LLM_CONFIG["api_key"], help="LLM API Key")
    parser.add_argument("--base_url", type=str, default=config.LLM_CONFIG["base_url"], help="LLM Base URL")
    parser.add_argument("--model", type=str, default=config.LLM_CONFIG["model"], help="LLM Model Name")
    parser.add_argument("--ocr_url", type=str, default=config.MONKEY_OCR_CONFIG["base_url"], help="MonkeyOCR API URL")
    parser.add_argument("--input", type=str, default=config.PATHS["input_dir"], help="输入 PDF 文件夹或文件路径")
    parser.add_argument("--output", type=str, default=config.PATHS["output_dir"], help="输出 Markdown 文件夹路径")
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    ocr_client = MonkeyOCRClient(args.ocr_url, timeout=config.MONKEY_OCR_CONFIG["timeout"])
    regex_cleaner = RegexCleaning(config.CLEANING_CONFIG["regex_patterns"])
    llm_cleaner = LLMCleaning(args.api_key, args.base_url, args.model, config.LLM_CONFIG["temperature"])
    verifier = MarkdownVerifier(
        min_length_ratio=config.VERIFY_CONFIG["min_length_ratio"],
        forbidden_phrases=config.VERIFY_CONFIG["forbidden_phrases"]
    )

    processor = PDFProcessor(ocr_client, regex_cleaner, llm_cleaner, verifier)

    if os.path.isfile(args.input):
        processor.process_file(args.input, args.output)
    else:
        processor.process_directory(args.input, args.output)

    log_msg("INFO", "全流程任务执行结束。")

if __name__ == "__main__":
    main()
