import os
from typing import List
from tqdm import tqdm
from crawler import MonkeyOCRClient
from cleaning import RegexCleaning, LLMCleaning
from verifier import MarkdownVerifier
from utils.logger_system import log_msg, log_json

class PDFProcessor:
    def __init__(self, ocr_client: MonkeyOCRClient, regex_cleaner: RegexCleaning, 
                 llm_cleaner: LLMCleaning, verifier: MarkdownVerifier):
        self.ocr_client = ocr_client
        self.regex_cleaner = regex_cleaner
        self.llm_cleaner = llm_cleaner
        self.verifier = verifier

    def process_file(self, pdf_path: str, output_dir: str):
        filename = os.path.basename(pdf_path)
        md_filename = os.path.splitext(filename)[0] + ".md"
        output_path = os.path.join(output_dir, md_filename)
        
        log_msg("INFO", f"开始处理: {filename}")
        
        try:
            raw_md = self.ocr_client.to_markdown(pdf_path)
            if not raw_md:
                log_msg("ERROR", "OCR 识别结果为空，跳过后续步骤。")
                return

            regex_md = self.regex_cleaner.clean(raw_md)
            final_md = self.llm_cleaner.clean(regex_md)
            
            self.verifier.verify(raw_md, final_md)
            
            os.makedirs(output_dir, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_md)
            
            log_msg("INFO", f"处理完成: {output_path}")
            log_json({"file": filename, "status": "success", "output": output_path})
            
        except Exception as e:
            log_msg("WARNING", f"文件 {filename} 处理失败: {str(e)}")
            log_json({"file": filename, "status": "failed", "error": str(e)})

    def process_directory(self, input_dir: str, output_dir: str):
        if not os.path.exists(input_dir):
            log_msg("ERROR", f"输入目录不存在: {input_dir}")
            
        pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            log_msg("WARNING", f"目录 {input_dir} 中未找到 PDF 文件。")
            return

        log_msg("INFO", f"发现 {len(pdf_files)} 个文件，开始批量处理...")
        for pdf_file in tqdm(pdf_files):
            self.process_file(os.path.join(input_dir, pdf_file), output_dir)
