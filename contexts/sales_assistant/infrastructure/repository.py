import uuid

from sqlalchemy.orm import Session

from shared.infrastructure.db.models.business import Lead


class SalesRepository:
    def __init__(self, session: Session):
        self._session = session

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
