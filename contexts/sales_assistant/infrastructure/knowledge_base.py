# -*- coding: utf-8 -*-
"""销售 FAQ 知识库：BGE-M3 + Milvus Lite 语义检索（dense 默认 / hybrid 开关）。

- MilvusKnowledgeBase：运行时检索适配器（进程常驻，实例化即 load）
- build_knowledge_base：一次性建库（读 data/*.md → 清洗 → 按 ### 切 FAQ → 写入 Milvus）

检索模式说明：
- dense：仅用稠密向量（BGE-M3 句向量）做内积检索，速度快、部署简单；
- hybrid：稠密向量 + BM25 稀疏向量双路召回，再按权重融合，关键词命中更稳。
"""

import html
import os
import re
from pathlib import Path

# 与 embeddings.py 一致，避免 import 顺序影响镜像/离线设置。
# 必须在导入 transformers / sentence-transformers 之前设置，否则不生效。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from langchain_core.documents import Document
from langchain_milvus import Milvus, BM25BuiltInFunction
from langchain_text_splitters import MarkdownHeaderTextSplitter
from contexts.sales_assistant.domain.faq import FaqHit

# Milvus 集合名，建库与检索必须一致
COLLECTION_NAME = "sales_assistant_faq"

# dense: IP/FLAT（内积≈余弦）；sparse: BM25 倒排索引
DENSE_INDEX = {"metric_type": "IP", "index_type": "FLAT"}
SPARSE_INDEX = {"metric_type": "BM25", "index_type": "SPARSE_INVERTED_INDEX"}
# 双向量字段名，hybrid 模式下同时写入/检索
VECTOR_FIELDS = ["dense", "sparse"]

# Milvus Lite 内嵌 gRPC 无需 keepalive 心跳，关闭避免 too_many_pings
GRPC_OPTIONS = {"grpc.keepalive_time_ms": 2**31 - 1}

# hybrid 双路加权融合权重（仅 retrieval_mode=hybrid 时生效）
# 顺序与 VECTOR_FIELDS 对应：dense 占 0.7，sparse(BM25) 占 0.3
HYBRID_WEIGHTS = [0.7, 0.3]

# 项目根目录（contexts/sales_assistant/infrastructure -> 上三级）  也就是从当前目录往上返三级
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# 知识库 Markdown 数据目录（contexts/sales_assistant/data）
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# 默认 Milvus Lite 文件：项目根 data/milvus_sales_faq.db
DEFAULT_MILVUS_URI = str(PROJECT_ROOT / "data" / "milvus_sales_faq.db")


def default_milvus_uri() -> str:
    """返回默认 Milvus Lite 数据库文件路径，供外部（如配置装配）引用。"""
    return DEFAULT_MILVUS_URI


def clean_markdown(text: str) -> str:
    """清洗 Markdown：HTML 解码、统一换行、删除分隔线、压缩空行。

    处理内容：
    - HTML 实体解码（如 &nbsp; &amp;）；
    - 统一 CRLF/CR 为 LF，不换行空格替换为普通空格；
    - 逐行 strip，丢弃单字符 "-" 行与 3 个以上 -/*/_ 组成的分隔线；
    - 连续 3 个及以上换行压缩为 2 个（保留段落间隔）。
    """
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line == "-":
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_by_markdown_header(markdown_text: str, source: str) -> list[Document]:
    """按 ### 标题切分 FAQ，标题作为 question 写入 metadata 与正文。
    Args:
        markdown_text: 已清洗的 Markdown 文本。
        source: 来源文件名，写入 metadata 便于溯源。
    Returns:
        Document 列表；每个 Document 的 page_content 为"问题 + 答案"，
        metadata 含 question/source/category。
    下面的文档内容经过转换的流程
    ### 报名后可以退款吗？
    7 天内可无条件退款。
       ⬇️
    Document(
        page_content="7 天内可无条件退款。",
        metadata={"question": "报名后可以退款吗？"}   # ← 标题被存进 question
    ),
    """

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("###", "question")], strip_headers=True
    )
    faq_documents = []
    # markdown_text 这份文档被切分成多个  所以才会出现for 循环
    for doc in splitter.split_text(markdown_text):
        question = doc.metadata.get("question", "").strip()  # 得到问题
        # 无标题的片段（如文件开头的说明文字）跳过，避免污染问答对
        if not question:
            continue
        # 把问题拼回正文，保证 embedding 同时编码"问题 + 答案"
        content = f"{question}\n\n{doc.page_content.strip()}"
        faq_documents.append(
            Document(
                page_content=content,
                metadata={
                    "question": question,
                    "source": source,
                    "category": "sales_assistant_faq",
                },
            )
        )
    return faq_documents


def build_knowledge_base(
    data_dir: Path = DATA_DIR,
    uri: str | None = None,
    embedding=None,
    drop_old: bool = True,
) -> None:
    """一次性建库：读 data/*.md → 清洗 → 按 ### 切 FAQ → 写入 Milvus（dense + sparse）。
    Args:
        data_dir: Markdown 数据目录，默认 DATA_DIR。
        uri: Milvus 连接地址；None 时用 default_milvus_uri()。
        embedding: 嵌入模型；None 时延迟导入 create_embeddings() 创建，
            避免建库脚本在未装模型时 import 失败。
        drop_old: 是否先删除同名旧集合（重建场景为 True）。
    Raises:
        FileNotFoundError: 目录下没有 .md 文件。
        ValueError: 所有文件均未识别出 FAQ（检查 ### 标题格式）。
    """
    md_files = sorted(data_dir.glob("*.md"))  # 可以读取多份md 文档
    if not md_files:
        raise FileNotFoundError(f"目录 {data_dir} 下没有找到任何 .md 文件")

    faq_documents: list[Document] = []
    for md_file in md_files:
        markdown_text = clean_markdown(md_file.read_text(encoding="utf-8"))
        # 把另一个列表里的元素逐个追加到当前列表末尾
        faq_documents.extend(
            _split_by_markdown_header(markdown_text, source=md_file.name)
        )

    if not faq_documents:
        raise ValueError("没有从任何 Markdown 文件中识别到 FAQ，请检查 ### 标题格式")

    # 为每条 FAQ 生成稳定编号 Q001/Q002…，便于日志与人工核对
    for i, doc in enumerate(faq_documents, start=1):
        doc.metadata["question_id"] = f"Q{i:03d}"

    # 延迟导入：仅在未传入 embedding 时才加载模型，减少脚本启动依赖
    if embedding is None:
        from contexts.sales_assistant.infrastructure.embeddings import create_embeddings

        # 这里取得的是向量模型的实例对象
        embedding = create_embeddings()

    Milvus.from_documents(
        documents=faq_documents,
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
        # Bounded：允许轻微延迟一致性，换取更高写入吞吐
        consistency_level="Bounded",
        drop_old=drop_old,
    )
    print(
        f"入库完成，共 {len(faq_documents)} 条 FAQ 写入 Milvus 集合「{COLLECTION_NAME}」"
    )


class MilvusKnowledgeBase:
    """Milvus 检索适配器：加载集合，按 dense（默认）或 hybrid 检索 top-k。
    实例化即 load 集合，适合进程常驻（如 Web 服务启动时创建单例）。
    """

    def __init__(
        self, uri: str, embedding, retrieval_mode: str = "dense", top_k: int = 4
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
        """按检索模式构造 Milvus 客户端（hybrid 需声明双向量字段与 BM25 函数）。"""
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

    def search(self, question: str, top_k: int | None = None) -> list[FaqHit]:
        """检索与问题最相关的 FAQ。
        Args:
            question: 用户问题原文。
            top_k: 本次召回条数；None 时用实例默认值。

        Returns:
            FaqHit 列表，score 保留 4 位小数。
            hybrid 模式分数为加权融合分，dense 模式为内积分，两者数值不可直接比较。
        """
        k = top_k if top_k is not None else self._top_k
        if self._retrieval_mode == "hybrid":
            # 双路召回后按 HYBRID_WEIGHTS 加权融合
            results = self._vectorstore.similarity_search_with_score(
                question,
                k=k,
                ranker_type="weighted",
                ranker_params={"weights": HYBRID_WEIGHTS},
            )
        else:
            results = self._vectorstore.similarity_search_with_score(question, k=k)
        return [
            FaqHit(
                question=doc.metadata.get("question", ""),
                content=doc.page_content,
                score=round(float(score), 4),
            )
            for doc, score in results
        ]
