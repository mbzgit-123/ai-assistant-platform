# -*- coding: utf-8 -*-
"""教学助教课程知识库：BGE-M3 + Milvus Lite 语义检索（dense 默认 / hybrid 开关）。

- build_knowledge_base：一次性建库（读 data/chunks.jsonl → 写入 Milvus）
- MilvusKnowledgeBase：运行时检索适配器（进程常驻，实例化即 load）

chunks.jsonl 由 build_chunks.py 产出，每条记录含 id/document_name/chapter/
heading_path(数组)/content/chunk_index/total_chunks；入库时 heading_path 压平为字符串。
"""

import json
import os
from pathlib import Path

# 与 shared/infrastructure/embeddings.py 一致，避免 import 顺序影响镜像/离线设置。
# 必须在导入 transformers / sentence-transformers 之前设置，否则不生效。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from langchain_core.documents import Document
from langchain_milvus import Milvus, BM25BuiltInFunction

from contexts.teaching_assistant.domain.chunks import RetrievedChunk

# Milvus 集合名，建库与检索必须一致
COLLECTION_NAME = "teaching_assistant_chunks"

# dense: IP/FLAT（内积≈余弦）；sparse: BM25 倒排索引
DENSE_INDEX = {"metric_type": "IP", "index_type": "FLAT"}
SPARSE_INDEX = {"metric_type": "BM25", "index_type": "SPARSE_INVERTED_INDEX"}
# 双向量字段名，hybrid 模式下同时写入/检索
VECTOR_FIELDS = ["dense", "sparse"]

# Milvus Lite 内嵌 gRPC 无需 keepalive 心跳，关闭避免 too_many_pings
GRPC_OPTIONS = {"grpc.keepalive_time_ms": 2**31 - 1}

# hybrid 双路加权融合权重（仅 retrieval_mode=hybrid 时生效）
HYBRID_WEIGHTS = [0.7, 0.3]

# 项目根目录（contexts/teaching_assistant/infrastructure -> 上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# 教学助教数据目录（contexts/teaching_assistant/data）
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# 切片文件（build_chunks.py 产出）
CHUNKS_FILE = DATA_DIR / "chunks.jsonl"
# 默认 Milvus Lite 文件：项目根 data/milvus_teaching.db
DEFAULT_MILVUS_URI = str(PROJECT_ROOT / "data" / "milvus_teaching.db")


def default_milvus_uri() -> str:
    """返回默认 Milvus Lite 数据库文件路径，供外部（如配置装配）引用。"""
    return DEFAULT_MILVUS_URI


def _load_chunks(chunks_file: Path = CHUNKS_FILE) -> list[Document]:
    """读 chunks.jsonl，把每条切片记录转为 langchain Document。

    heading_path 由数组压平为 " > " 连接字符串（Milvus metadata 仅支持标量）。
    """
    if not chunks_file.exists():
        raise FileNotFoundError(
            f"未找到切片文件 {chunks_file}，请先运行 build_chunks 生成"
        )

    documents: list[Document] = []
    with chunks_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            documents.append(
                Document(
                    page_content=record["content"],
                    metadata={
                        "chunk_id": record["id"],
                        "document_name": record["document_name"],
                        "chapter": record["chapter"],
                        "heading_path": " > ".join(record["heading_path"]),
                        "chunk_index": record["chunk_index"],
                        "total_chunks": record["total_chunks"],
                        "source": "teaching_assistant_chunks",
                    },
                )
            )
    return documents


def build_knowledge_base(
    chunks_file: Path = CHUNKS_FILE,
    uri: str | None = None,
    embedding=None,
    drop_old: bool = True,
) -> int:
    """一次性建库：读 chunks.jsonl → 写入 Milvus（dense + sparse）。

    Args:
        chunks_file: 切片 JSONL 文件，默认 CHUNKS_FILE。
        uri: Milvus 连接地址；None 时用 default_milvus_uri()。
        embedding: 嵌入模型；None 时延迟导入 create_embeddings() 创建。
        drop_old: 是否先删除同名旧集合（重建场景为 True）。

    Returns:
        写入的切片条数。
    """
    documents = _load_chunks(chunks_file)
    if not documents:
        raise ValueError(f"{chunks_file} 中没有切片记录，请先运行 build_chunks")

    # 延迟导入：仅在未传入 embedding 时才加载模型，减少脚本启动依赖
    if embedding is None:
        from shared.infrastructure.embeddings import create_embeddings

        embedding = create_embeddings()

    Milvus.from_documents(
        documents=documents,
        embedding=embedding,
        collection_name=COLLECTION_NAME,
        # 内置 BM25 函数：写入时自动生成 sparse 向量
        builtin_function=BM25BuiltInFunction(),
        index_params=[DENSE_INDEX, SPARSE_INDEX],
        vector_field=VECTOR_FIELDS,
        connection_args={
            "uri": uri or default_milvus_uri(),
            "grpc_options": GRPC_OPTIONS,
        },
        consistency_level="Bounded",
        drop_old=drop_old,
    )
    print(
        f"入库完成，共 {len(documents)} 条切片写入 Milvus 集合「{COLLECTION_NAME}」"
    )
    return len(documents)


class MilvusKnowledgeBase:
    """Milvus 检索适配器：加载集合，按 dense（默认）或 hybrid 检索 top-k。

    实例化即 load 集合，适合进程常驻（如 Web 服务启动时创建单例）。
    """

    def __init__(
        self, uri: str, embedding, retrieval_mode: str = "dense", top_k: int = 5
    ):
        """
        Args:
            uri: Milvus 连接地址（Lite 为本地 .db 文件路径）。
            embedding: 与建库时一致的嵌入模型，否则向量空间不匹配。
            retrieval_mode: "dense" 或 "hybrid"；其他值按 dense 处理。
            top_k: 默认召回条数，search 时可按次覆盖。
        """
        self._uri = uri
        self._embedding = embedding
        self._retrieval_mode = retrieval_mode
        self._top_k = top_k
        self._vectorstore = self._load()

    def _load(self) -> Milvus:
        connection_args = {"uri": self._uri, "grpc_options": GRPC_OPTIONS}
        if self._retrieval_mode == "hybrid":
            return Milvus(
                embedding_function=self._embedding,
                collection_name=COLLECTION_NAME,
                vector_field=["dense", "sparse"],
                builtin_function=BM25BuiltInFunction(),
                index_params=[DENSE_INDEX, SPARSE_INDEX],
                connection_args=connection_args,
            )
        return Milvus(
            embedding_function=self._embedding,
            collection_name=COLLECTION_NAME,
            vector_field="dense",
            index_params=[DENSE_INDEX],
            connection_args=connection_args,
        )

    def search(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """检索与问题最相关的课件切片。

        Args:
            question: 用户问题原文。
            top_k: 本次召回条数；None 时用实例默认值。

        Returns:
            list[RetrievedChunk]（按分数降序）。
            hybrid 模式分数为加权融合分，dense 模式为内积分，两者数值不可直接比较。
        """
        k = top_k if top_k is not None else self._top_k
        if self._retrieval_mode == "hybrid":
            results = self._vectorstore.similarity_search_with_score(
                question,
                k=k,
                ranker_type="weighted",
                ranker_params={"weights": HYBRID_WEIGHTS},
            )
        else:
            results = self._vectorstore.similarity_search_with_score(question, k=k)
        return [
            RetrievedChunk(
                chunk_id=doc.metadata.get("chunk_id", ""),
                document_name=doc.metadata.get("document_name", ""),
                chapter=doc.metadata.get("chapter", ""),
                heading_path=doc.metadata.get("heading_path", ""),
                text=doc.page_content,
                score=round(float(score), 4),
            )
            for doc, score in results
        ]
