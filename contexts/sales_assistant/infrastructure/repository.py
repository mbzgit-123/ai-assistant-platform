import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.infrastructure.db.models.business import Lead
from shared.infrastructure.db.models.sync_cache import Course


class SalesRepository:
    def __init__(self, session: Session):
        self._session = session

    def find_courses(self, direction: str, position: str | None = None) -> list[dict]:
        stmt = select(Course).where(Course.direction == direction)
        if position is not None:
            stmt = stmt.where(Course.position == position)
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "courseId": c.course_id,
                "name": c.name,
                "price": float(c.price) if c.price is not None else 0.0,
                "durationHours": c.duration_hours or 0,
                "highlights": c.highlights or "",
            }
            for c in rows
        ]

    def save_lead(
        self,
        contact: str,
        direction: str,
        position: str | None,
        remark: str | None,
        source: str,
    ) -> Lead:
        lead = Lead(
            lead_id="lead_" + uuid.uuid4().hex[:12],
            contact=contact,
            direction=direction,
            position=position,
            remark=remark,
            source=source,
        )
        self._session.add(lead)
        self._session.commit()
        return lead
