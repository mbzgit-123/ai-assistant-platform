from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.infrastructure.db.models.sync_cache import Chapter


class TeachingRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_chapters(self) -> list[Chapter]:
        return list(self._session.execute(select(Chapter)).scalars().all())
