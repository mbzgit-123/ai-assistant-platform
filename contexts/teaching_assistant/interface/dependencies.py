from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.infrastructure.conversation_repository import ConversationRepository
from contexts.teaching_assistant.infrastructure.knowledge_base import (
    MilvusKnowledgeBase,
    default_milvus_uri,
)
from shared.infrastructure.config import get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.embeddings import create_embeddings
from shared.infrastructure.llm.factory import get_llm

_retrieval: MilvusKnowledgeBase | None = None


def _get_retrieval() -> MilvusKnowledgeBase:
    """懒加载 BGE-M3 + Milvus 检索单例（进程常驻，实例化即 load 集合）。"""
    global _retrieval
    if _retrieval is None:
        settings = get_settings()
        _retrieval = MilvusKnowledgeBase(
            uri=default_milvus_uri(),
            embedding=create_embeddings(settings.embedding_model),
            retrieval_mode=settings.retrieval_mode,
            top_k=5,
        )
    return _retrieval


def get_teaching_assistant_service(session: Session = Depends(get_session)) -> TeachingAssistantService:
    llm = get_llm(get_settings())
    return TeachingAssistantService(
        llm=llm,
        retrieval=_get_retrieval(),
        conversation_record=ConversationRepository(session),
    )
