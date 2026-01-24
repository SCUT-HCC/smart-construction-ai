import requests
import zipfile
import io
import os
from typing import Optional
from utils.logger_system import log_msg

class MonkeyOCRClient:
    def __init__(self, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def to_markdown(self, pdf_path: str) -> str:
        if not os.path.exists(pdf_path):
            log_msg("ERROR", f"PDF 文件不存在: {pdf_path}")

        log_msg("INFO", f"正在上传 PDF 至 MonkeyOCR: {pdf_path}")
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': (os.path.basename(pdf_path), f, 'application/pdf')}
                response = requests.post(
                    f"{self.base_url}/parse", 
                    files=files, 
                    timeout=self.timeout
                )

            if response.status_code != 200:
                log_msg("ERROR", f"MonkeyOCR API 请求失败: {response.status_code}, {response.text}")

            data = response.json()
            if not data.get("success"):
                log_msg("ERROR", f"MonkeyOCR 处理失败: {data.get('message')}")

            download_url = data.get("download_url")
            if not download_url:
                log_msg("ERROR", "未在响应中找到下载 URL")

            full_download_url = (
                f"{self.base_url}{download_url}" 
                if download_url.startswith("/") 
                else download_url
            )

            log_msg("INFO", f"转换成功，正在下载结果: {full_download_url}")
            
            zip_response = requests.get(full_download_url, timeout=self.timeout)
            if zip_response.status_code != 200:
                log_msg("ERROR", f"下载 ZIP 结果失败: {zip_response.status_code}")

            return self._extract_markdown_from_zip(zip_response.content)

        except requests.exceptions.RequestException as e:
            log_msg("ERROR", f"MonkeyOCR 网络请求异常: {str(e)}")
        except Exception as e:
            log_msg("ERROR", f"MonkeyOCR 处理异常: {str(e)}")
        return ""

    def _extract_markdown_from_zip(self, zip_content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
                md_files = [f for f in z.namelist() if f.endswith(".md")]
                if not md_files:
                    log_msg("ERROR", "ZIP 中未找到 Markdown 文件")
                
                return z.read(md_files[0]).decode('utf-8')
        except zipfile.BadZipFile:
            log_msg("ERROR", "下载的内容不是有效的 ZIP 文件")
        return ""
