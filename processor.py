import os
from typing import List
from tqdm import tqdm
from crawler import MonkeyOCRClient
from cleaning import RegexCleaning, LLMCleaning
from verifier import MarkdownVerifier
from utils.logger_system import log_msg, log_json

class PDFProcessor:
    """
    PDF 处理核心类，负责调度 OCR 识别、正则清洗、LLM 清洗及结果验证。
    """
    def __init__(self, ocr_client: MonkeyOCRClient, regex_cleaner: RegexCleaning, 
                 llm_cleaner: LLMCleaning, verifier: MarkdownVerifier) -> None:
        """
        初始化 PDF 处理器。

        Args:
            ocr_client (MonkeyOCRClient): OCR 客户端实例。
            regex_cleaner (RegexCleaning): 正则清洗工具实例。
            llm_cleaner (LLMCleaning): LLM 语义清洗工具实例。
            verifier (MarkdownVerifier): 结果验证工具实例。
        """
        self.ocr_client = ocr_client
        self.regex_cleaner = regex_cleaner
        self.llm_cleaner = llm_cleaner
        self.verifier = verifier

    def process_file(self, pdf_path: str, output_dir: str) -> None:
        """
        处理单个 PDF 文件。

        该方法会将 OCR 识别、正则清洗、LLM 清洗的结果分别保存到以文件命名的子目录下。

        Args:
            pdf_path (str): PDF 文件路径。
            output_dir (str): 输出基础目录。
        """
        filename = os.path.basename(pdf_path)
        file_stem = os.path.splitext(filename)[0]
        file_output_dir = os.path.join(output_dir, file_stem)
        os.makedirs(file_output_dir, exist_ok=True)
        
        log_msg("INFO", f"开始处理: {filename}")
        
        try:
            raw_md = self.ocr_client.to_markdown(pdf_path)
            if not raw_md:
                log_msg("ERROR", "OCR 识别结果为空，跳过后续步骤。")
                return
            
            with open(os.path.join(file_output_dir, "raw.md"), 'w', encoding='utf-8') as f:
                f.write(raw_md)

            regex_md = self.regex_cleaner.clean(raw_md)
            with open(os.path.join(file_output_dir, "regex.md"), 'w', encoding='utf-8') as f:
                f.write(regex_md)

            final_md = self.llm_cleaner.clean(regex_md)
            with open(os.path.join(file_output_dir, "final.md"), 'w', encoding='utf-8') as f:
                f.write(final_md)
            
            self.verifier.verify(raw_md, final_md)
            
            log_msg("INFO", f"处理完成: {file_output_dir}")
            log_json({"file": filename, "status": "success", "output": file_output_dir})
            
        except Exception as e:
            log_msg("WARNING", f"文件 {filename} 处理失败: {str(e)}")
            log_json({"file": filename, "status": "failed", "error": str(e)})

    def process_directory(self, input_dir: str, output_dir: str) -> None:
        """
        批量处理目录下的所有 PDF 文件。

        Args:
            input_dir (str): 输入目录路径。
            output_dir (str): 输出基础目录。
        """
        if not os.path.exists(input_dir):
            log_msg("ERROR", f"输入目录不存在: {input_dir}")
            
        pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            log_msg("WARNING", f"目录 {input_dir} 中未找到 PDF 文件。")
            return

        log_msg("INFO", f"发现 {len(pdf_files)} 个文件，开始批量处理...")
        for pdf_file in tqdm(pdf_files):
            self.process_file(os.path.join(input_dir, pdf_file), output_dir)
