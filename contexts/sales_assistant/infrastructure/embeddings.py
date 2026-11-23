# -*- coding: utf-8 -*-
"""BGE-M3 嵌入模型适配器（迁移自旧项目 infrastructure/embeddings.py）。"""

import os

# 必须在 import transformers/huggingface_hub 之前设置，否则缓存 endpoint 已固定
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 模型已下载到本地缓存，默认强制离线加载，避免联网校验超时
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from langchain_huggingface import HuggingFaceEmbeddings


def create_embeddings(model_name: str = "BAAI/bge-m3"):
    """创建 BGE-M3 嵌入模型（首次运行会自动下载权重）。"""
    return HuggingFaceEmbeddings(
        model_name=model_name,
        # float16 加载：内存占用减半，检索效果几乎无损
        model_kwargs={"model_kwargs": {"torch_dtype": torch.float16}},
        encode_kwargs={"normalize_embeddings": True},
    )
