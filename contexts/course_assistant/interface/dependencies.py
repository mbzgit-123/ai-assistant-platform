from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.course_assistant.application.service import (
    CourseAssistantService,
    SupervisionService,
)
from contexts.course_assistant.infrastructure.message_channel import StubMessageChannel
from contexts.course_assistant.infrastructure.path_knowledge import InMemoryPathKnowledge
from contexts.course_assistant.infrastructure.repository import CourseRepository
from shared.infrastructure.config import get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.factory import get_llm

_path_knowledge = InMemoryPathKnowledge()
_message_channel = StubMessageChannel()


def get_course_assistant_service(
    session: Session = Depends(get_session),
) -> CourseAssistantService:
    return CourseAssistantService(
        llm=get_llm(get_settings()),
        path_knowledge=_path_knowledge,
        progress=CourseRepository(session),
    )


def get_supervision_service(
    session: Session = Depends(get_session),
) -> SupervisionService:
    return SupervisionService(
        progress=CourseRepository(session),
        message_channel=_message_channel,
    )
