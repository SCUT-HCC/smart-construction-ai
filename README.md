# PDF 处理全流程工具 (OCR -> 清洗 -> 验证)

本项目是一个基于群体智能思想重构的 PDF 自动化处理系统，旨在解决复杂 PDF 文档转换为高质量 Markdown 的需求。

## 项目结构

- `main.py`: 程序入口，负责解析命令行参数并启动处理流程。
- `config.py`: 全局配置中心，包含 LLM、OCR 及清洗规则的默认配置。
- `processor.py`: 核心调度器，封装了从文件读取到处理保存的全生命周期。
- `crawler.py`: MonkeyOCR 客户端，负责与 OCR 服务交互。
- `cleaning.py`: 清洗逻辑类，包含正则预处理及 LLM 语义清洗。
- `verifier.py`: 结果验证工具（工具代码检查工具），确保输出质量。
- `utils/logger_system.py`: 统一日志管理系统。

## 核心功能

1. **OCR 识别**: 调用 MonkeyOCR API 将 PDF 转换为 Markdown。
2. **正则清洗**: 基于预定义的正则表达式清理 OCR 产生的噪声（如水印、页码、LaTex 装饰符等）。
3. **LLM 清洗**: 利用 DeepSeek 等大模型对 Markdown 进行语义重构、标题合并及段落流优化。
4. **质量验证**: 自动检查输出结果的字数损失、LLM 幻觉及 Markdown 结构合法性。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行处理

处理单个文件：
```bash
python main.py --input data/1.pdf --output output
```

处理整个文件夹：
```bash
python main.py --input data --output output
```

### 参数说明

- `--api_key`: LLM API 密钥（优先级高于 config.py）。
- `--base_url`: LLM API 基础 URL。
- `--model`: 使用的 LLM 模型名称。
- `--ocr_url`: MonkeyOCR 服务地址。
- `--input`: 输入路径（文件或目录）。
- `--output`: 输出目录。

## 配置建议

清洗规则可在 `config.py` 的 `CLEANING_CONFIG` 中根据具体业务需求进行调整。
质量验证阈值可在 `VERIFY_CONFIG` 中设定。
