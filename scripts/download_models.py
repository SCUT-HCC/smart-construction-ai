"""下载所有候选模型。"""
import os
import sys

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from huggingface_hub import snapshot_download

MODELS = [
    "BAAI/bge-large-zh-v1.5",
    "Qwen/Qwen3-Embedding-0.6B",
    "Qwen/Qwen3-Reranker-0.6B",
    "Qwen/Qwen3-Embedding-4B",
    "Qwen/Qwen3-Reranker-4B",
    "Qwen/Qwen3-Embedding-8B",
    "Qwen/Qwen3-Reranker-8B",
]

if len(sys.argv) > 1:
    MODELS = [m for m in MODELS if any(arg in m for arg in sys.argv[1:])]

for model in MODELS:
    print(f"\n{'='*50}")
    print(f"下载: {model}")
    print(f"{'='*50}")
    try:
        path = snapshot_download(model)
        print(f"完成: {path}")
    except Exception as e:
        print(f"失败: {e}")
