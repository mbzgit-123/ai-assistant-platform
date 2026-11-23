import threading

from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.sales_assistant.application.service import SalesChatService
from contexts.sales_assistant.infrastructure.course_catalog import MbCourseCatalog
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport
from shared.infrastructure.config import Settings, get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.factory import get_llm
from shared.infrastructure.memory.in_memory import InMemoryStore
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_sales_memory = InMemoryStore()


class _EmptyKnowledgeBase:
    """知识库未建/加载失败时的降级实现：恒返回空命中，FAQ 走无命中兜底。"""

    def search(self, question: str, top_k: int = 4) -> list:
        return []


# Milvus 知识库进程常驻单例（BGE-M3 加载重，避免每次请求重建）。
# 懒加载：不在模块导入期 import torch / langchain_milvus，单元测试无需 RAG 依赖。
_kb = None
_kb_lock = threading.Lock()


def _get_kb(settings: Settings):
    global _kb
    if _kb is None:
        with _kb_lock:
            if _kb is None:
                try:
                    from contexts.sales_assistant.infrastructure.embeddings import create_embeddings
                    from contexts.sales_assistant.infrastructure.knowledge_base import (
                        MilvusKnowledgeBase,
                        default_milvus_uri,
                    )

                    _kb = MilvusKnowledgeBase(
                        uri=settings.milvus_uri or default_milvus_uri(),
                        embedding=create_embeddings(settings.embedding_model),
                        retrieval_mode=settings.retrieval_mode,
                        top_k=settings.sales_faq_top_k,
                    )
                except Exception:
                    logger.warning(
                        "sales_assistant.kb_load_failed",
                        hint="知识库未构建或加载失败，FAQ 将走无命中兜底；请运行 build_knowledge_base",
                        exc_info=True,
                    )
                    _kb = _EmptyKnowledgeBase()
    return _kb


# 课程目录客户端进程常驻单例（分类树内部缓存，避免每次请求重复拉取）
_catalog = None
_catalog_lock = threading.Lock()


def _get_catalog(settings: Settings):
    global _catalog
    if _catalog is None:
        with _catalog_lock:
            if _catalog is None:
                _catalog = MbCourseCatalog(
                    settings.subject_api_url, settings.course_list_api_url
                )
    return _catalog


def get_sales_chat_service(session: Session = Depends(get_session)) -> SalesChatService:
    settings = get_settings()
    llm = get_llm(settings)
    return SalesChatService(
        llm=llm,
        memory=_sales_memory,
        repo=SalesRepository(session),
        vip_report=StubVipReport(),
        kb=_get_kb(settings),
        faq_top_k=settings.sales_faq_top_k,
        catalog=_get_catalog(settings),
    )
