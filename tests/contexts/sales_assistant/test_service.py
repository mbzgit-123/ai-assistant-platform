from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.memory.in_memory import InMemoryStore

from contexts.sales_assistant.application.service import (
    SalesChatService,
    DIRECTION_PROMPT,
    NO_COURSE_REPLY,
    LEAD_ASK_CONTACT_REPLY,
)
from contexts.sales_assistant.domain.directions import FAQ_ENROLLMENT
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


def _service(responses, courses=()):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    for c in courses:
        s.add(Course(**c))
    s.commit()
    return SalesChatService(
        FakeLLMAdapter(responses=responses),
        InMemoryStore(),
        SalesRepository(s),
        StubVipReport(),
    )


def test_chat_direction_guide_when_unknown():
    svc = _service(['{"intent": "course_intro", "direction": "", "position": ""}'])
    r = svc.chat(None, "想学编程", "web")
    assert r["reply"] == DIRECTION_PROMPT
    assert r["courses"] == []
    assert r["leadSaved"] is False
    assert r["conversationId"].startswith("c_")


def test_chat_course_intro_matched():
    svc = _service(
        ['{"intent": "course_intro", "direction": "AI", "position": "大模型算法岗"}', "这是推荐话术"],
        courses=[dict(course_id="c1", name="AI算法课", price=100, duration_hours=20, highlights="h", direction="AI", position="大模型算法岗")],
    )
    r = svc.chat(None, "想学AI算法", "web")
    assert r["reply"] == "这是推荐话术"
    assert r["courses"][0]["courseId"] == "c1"
    assert r["direction"] == "AI"
    assert r["position"] == "大模型算法岗"


def test_chat_course_intro_no_match():
    svc = _service(['{"intent": "course_intro", "direction": "前端", "position": ""}'])
    r = svc.chat(None, "想学前端", "web")
    assert r["reply"] == NO_COURSE_REPLY
    assert r["courses"] == []


def test_chat_faq_hit_deterministic():
    svc = _service(['{"intent": "enrollment_faq", "direction": "", "position": ""}'])
    r = svc.chat(None, "报名流程是什么", "web")
    assert r["reply"] == FAQ_ENROLLMENT[0][1]


def test_chat_faq_miss_llm_fallback():
    svc = _service(['{"intent": "study_faq", "direction": "", "position": ""}', "学习建议（LLM）"])
    r = svc.chat(None, "如何高效学习", "web")
    assert r["reply"] == "学习建议（LLM）"


def test_chat_lead_with_contact():
    svc = _service([
        '{"intent": "lead_capture", "direction": "AI", "position": "大模型算法岗"}',
        '{"contact": "wx123", "remark": "想学AI"}',
    ])
    r = svc.chat(None, "我微信是wx123", "web")
    assert r["leadSaved"] is True
    assert r["direction"] == "AI"


def test_chat_lead_without_contact():
    svc = _service([
        '{"intent": "lead_capture", "direction": "", "position": ""}',
        '{"contact": "", "remark": ""}',
    ])
    r = svc.chat(None, "我想报名", "web")
    assert r["leadSaved"] is False
    assert r["reply"] == LEAD_ASK_CONTACT_REPLY


def test_chat_lead_unknown_direction_writes_other():
    svc = _service([
        '{"intent": "lead_capture", "direction": "", "position": ""}',
        '{"contact": "13800138000", "remark": ""}',
    ])
    r = svc.chat(None, "电话13800138000", "web")
    assert r["leadSaved"] is True
    assert r["direction"] == "其他"


def test_chat_memory_precedence():
    svc = _service([
        '{"intent": "enrollment_faq", "direction": "Java", "position": ""}',
        '{"intent": "enrollment_faq", "direction": "AI", "position": "大模型算法岗"}',
    ])
    r1 = svc.chat(None, "报名流程", "web")
    r2 = svc.chat(r1["conversationId"], "包就业吗", "web")
    assert r2["direction"] == "Java"


def test_chat_bad_json_falls_back_to_guide():
    svc = _service(["not json", "still not json"])
    r = svc.chat(None, "想学编程", "web")
    assert r["reply"] == DIRECTION_PROMPT
