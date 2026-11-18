from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Chapter
from contexts.teaching_assistant.infrastructure.repository import TeachingRepository


def _repo(chapters=()):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    for c in chapters:
        s.add(Chapter(**c))
    s.commit()
    return TeachingRepository(s)


def test_list_chapters_returns_all():
    repo = _repo([dict(chapter_id="c1", title="t1", content_md="正文1"),
                  dict(chapter_id="c2", title="t2", content_md="正文2")])
    ids = {c.chapter_id for c in repo.list_chapters()}
    assert ids == {"c1", "c2"}
