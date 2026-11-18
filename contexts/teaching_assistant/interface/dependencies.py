from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.domain.chunks import build_chunks
from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff
from contexts.teaching_assistant.infrastructure.repository import TeachingRepository
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore
from shared.infrastructure.config import get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.factory import get_llm

_embedding = HashEmbedding()
_vector_store = InMemoryVectorStore(_embedding)
_handoff = StubHandoff()


def get_teaching_assistant_service(session: Session = Depends(get_session)) -> TeachingAssistantService:
    llm = get_llm(get_settings())
    repo = TeachingRepository(session)
    for chapter in repo.list_chapters():
        _vector_store.upsert(
            build_chunks(chapter.chapter_id, chapter.course_id, chapter.title, chapter.content_md)
        )
    return TeachingAssistantService(
        llm=llm,
        embedding=_embedding,
        vector_store=_vector_store,
        handoff=_handoff,
    )
