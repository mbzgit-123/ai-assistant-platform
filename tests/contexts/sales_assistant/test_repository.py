from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.business import Lead
from contexts.sales_assistant.infrastructure.repository import SalesRepository


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_save_lead_persists():
    s = _session()
    lead = SalesRepository(s).save_lead("13800138000", "人工智能", "大模型算法开发岗", "备注", "web")
    assert lead.lead_id.startswith("lead_")
    assert lead.direction == "人工智能"
    fetched = s.get(Lead, lead.lead_id)
    assert fetched is not None
    assert fetched.contact == "13800138000"
