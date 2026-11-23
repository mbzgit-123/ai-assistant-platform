from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.port import LLMResult
from shared.infrastructure.memory.in_memory import InMemoryStore

from contexts.sales_assistant.application.service import (
    SalesChatService,
    NO_COURSE_REPLY,
    LEAD_ASK_CONTACT_REPLY,
)
from contexts.sales_assistant.domain.catalog import CourseInfo, SubjectNode
from contexts.sales_assistant.domain.faq import FAQ_NO_MATCH_REPLY, FaqHit
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


class FakeKnowledgeBase:
    def __init__(self, hits: list[FaqHit] | None = None):
        self._hits = hits or []

    def search(self, question: str, top_k: int = 4) -> list[FaqHit]:
        return list(self._hits[:top_k])


TREE = [
    SubjectNode(
        id="ai_id",
        name="人工智能",
        parent_id=None,
        children=(
            SubjectNode(id="app_id", name="大模型应用开发岗", parent_id="ai_id"),
            SubjectNode(id="algo_id", name="大模型算法开发岗", parent_id="ai_id"),
        ),
    ),
    SubjectNode(id="fe_id", name="前端开发", parent_id=None, children=()),
]


class FakeCourseCatalog:
    def __init__(self, tree=None, courses=None):
        self._tree = tree if tree is not None else TREE
        self._courses = courses or []
        self.calls = []

    def get_subject_tree(self):
        return self._tree

    def get_courses(self, subject_id, subject_parent_id):
        self.calls.append((subject_id, subject_parent_id))
        return list(self._courses)


def _course(**kw):
    defaults = dict(
        id="c1", title="AI算法课", description="d", price=100.0,
        lesson_num=18, duration=9902.0, cover="",
    )
    defaults.update(kw)
    return CourseInfo(**defaults)


def _service(responses, kb_hits=None, catalog=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    return SalesChatService(
        FakeLLMAdapter(responses=responses),
        InMemoryStore(),
        SalesRepository(s),
        StubVipReport(),
        FakeKnowledgeBase(kb_hits),
        catalog=catalog,
    )


# ---------- 方向/课程多轮引导 ----------

def test_chat_guides_direction_lists_real_categories():
    svc = _service(['{"intent": "course_intro", "direction": "", "position": ""}'])
    r = svc.chat(None, "想学编程", "web")
    assert "人工智能" in r["reply"]
    assert "前端开发" in r["reply"]
    assert "后端开发" in r["reply"]
    assert "数据库开发" in r["reply"]
    assert r["courses"] == []
    assert r["direction"] is None
    assert r["position"] is None


def test_chat_picks_direction_guides_position():
    svc = _service(['{"intent": "course_intro", "direction": "人工智能", "position": ""}'])
    r = svc.chat(None, "我想学人工智能", "web")
    assert r["direction"] == "人工智能"
    assert r["position"] is None
    assert "大模型算法开发岗" in r["reply"]
    assert r["courses"] == []


def test_chat_course_intro_returns_courses_from_catalog():
    catalog = FakeCourseCatalog(courses=[_course()])
    svc = _service(
        ['{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}', "这是推荐话术"],
        catalog=catalog,
    )
    r = svc.chat(None, "想学AI算法", "web")
    assert r["reply"] == "这是推荐话术"
    assert r["courses"][0]["courseId"] == "c1"
    assert r["direction"] == "人工智能"
    assert r["position"] == "大模型算法开发岗"
    # 查课程时带上了二级 id 和它的一级父 id
    assert catalog.calls == [("algo_id", "ai_id")]


def test_chat_course_intro_no_course():
    catalog = FakeCourseCatalog(courses=[])
    svc = _service(
        ['{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}'],
        catalog=catalog,
    )
    r = svc.chat(None, "想学AI算法", "web")
    assert r["reply"] == NO_COURSE_REPLY
    assert r["courses"] == []


def test_chat_course_response_omits_lesson_and_price():
    catalog = FakeCourseCatalog(courses=[_course()])
    svc = _service(
        ['{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}', "课程介绍话术"],
        catalog=catalog,
    )
    r = svc.chat(None, "想学AI算法", "web")
    course = r["courses"][0]
    assert "lessonNum" not in course
    assert "price" not in course
    assert course["courseId"] == "c1"
    assert course["name"] == "AI算法课"


def test_chat_multi_turn_resolves_through_tree():
    catalog = FakeCourseCatalog(courses=[_course()])
    svc = _service(
        [
            '{"intent": "course_intro", "direction": "", "position": ""}',
            '{"intent": "course_intro", "direction": "人工智能", "position": ""}',
            '{"intent": "course_intro", "direction": "", "position": "大模型算法开发岗"}',
            "推荐话术",
        ],
        catalog=catalog,
    )
    r1 = svc.chat(None, "想学编程", "web")
    r2 = svc.chat(r1["conversationId"], "人工智能", "web")
    r3 = svc.chat(r1["conversationId"], "大模型算法开发岗", "web")
    assert r2["direction"] == "人工智能"
    assert r2["position"] is None
    assert r3["position"] == "大模型算法开发岗"
    assert r3["courses"][0]["courseId"] == "c1"
    assert catalog.calls == [("algo_id", "ai_id")]


class _RaisingCatalog:
    def get_subject_tree(self):
        raise RuntimeError("down")

    def get_courses(self, subject_id, subject_parent_id):
        raise RuntimeError("down")


def test_chat_catalog_error_falls_back_to_defaults():
    svc = _service(
        ['{"intent": "course_intro", "direction": "", "position": ""}'],
        catalog=_RaisingCatalog(),
    )
    r = svc.chat(None, "想学编程", "web")
    assert "人工智能" in r["reply"]
    assert r["courses"] == []


def test_chat_memory_precedence():
    svc = _service([
        '{"intent": "course_intro", "direction": "后端开发", "position": ""}',
        '{"intent": "course_intro", "direction": "人工智能", "position": ""}',
    ])
    r1 = svc.chat(None, "想学后端", "web")
    r2 = svc.chat(r1["conversationId"], "还是人工智能吧", "web")
    # 已识别的方向优先于本轮新提及
    assert r2["direction"] == "后端开发"


def test_chat_bad_json_falls_back_to_guide():
    svc = _service(["not json", "still not json"])
    r = svc.chat(None, "想学编程", "web")
    assert "人工智能" in r["reply"]


# ---------- FAQ ----------

def test_chat_faq_hit_grounded():
    svc = _service(
        ['{"intent": "enrollment_faq", "direction": "", "position": ""}', "报名流程答复（LLM）"],
        kb_hits=[FaqHit(question="报名流程是怎样的？", content="报名流程：交费→入学→签约", score=0.9)],
    )
    r = svc.chat(None, "报名流程是什么", "web")
    assert r["reply"] == "报名流程答复（LLM）"
    assert r["sources"] == [
        {"question": "报名流程是怎样的？", "content": "报名流程：交费→入学→签约", "score": 0.9}
    ]


def test_chat_faq_no_hit_reply():
    svc = _service(
        ['{"intent": "study_faq", "direction": "", "position": ""}'],
        kb_hits=[],
    )
    r = svc.chat(None, "如何高效学习", "web")
    assert r["reply"] == FAQ_NO_MATCH_REPLY
    assert r["sources"] == []


def test_chat_faq_filters_hits_below_score_threshold():
    svc = _service(
        ['{"intent": "enrollment_faq", "direction": "", "position": ""}', "报名流程答复"],
        kb_hits=[
            FaqHit(question="报名流程", content="交费→入学→签约", score=0.7555),
            FaqHit(question="学习模式", content="一对一线上", score=0.62),
        ],
    )
    r = svc.chat(None, "报名流程是什么", "web")
    assert r["sources"] == [
        {"question": "报名流程", "content": "交费→入学→签约", "score": 0.7555}
    ]


class _RaisingKnowledgeBase:
    def search(self, question: str, top_k: int = 4) -> list[FaqHit]:
        raise RuntimeError("kb unavailable")


def test_chat_faq_search_error_degrades_to_no_match():
    svc = SalesChatService(
        FakeLLMAdapter(responses=['{"intent": "study_faq", "direction": "", "position": ""}']),
        InMemoryStore(),
        SalesRepository(_session()),
        StubVipReport(),
        _RaisingKnowledgeBase(),
    )
    r = svc.chat(None, "学习周期多久", "web")
    assert r["reply"] == FAQ_NO_MATCH_REPLY
    assert r["sources"] == []


# ---------- 留资 ----------

def test_chat_lead_with_contact():
    svc = _service([
        '{"intent": "lead_capture", "direction": "人工智能", "position": "大模型算法开发岗"}',
        '{"contact": "wx123", "remark": "想学AI"}',
    ])
    r = svc.chat(None, "我微信是wx123", "web")
    assert r["leadSaved"] is True
    assert r["direction"] == "人工智能"


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


# ---------- LLM 调用内容 ----------

class _RecordingLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self._calls = []

    def chat(self, messages):
        self._calls.append(messages)
        idx = min(len(self._calls) - 1, len(self._responses) - 1)
        return LLMResult(content=self._responses[idx])


def _service_with_llm(llm):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    return SalesChatService(
        llm,
        InMemoryStore(),
        SalesRepository(s),
        StubVipReport(),
        FakeKnowledgeBase(),
    )


def test_chat_intent_prompt_includes_memory_context():
    llm = _RecordingLLM([
        '{"intent": "course_intro", "direction": "后端开发", "position": ""}',
        '{"intent": "course_intro", "direction": "", "position": ""}',
    ])
    svc = _service_with_llm(llm)

    r1 = svc.chat(None, "想学后端", "web")
    svc.chat(r1["conversationId"], "还有别的吗", "web")

    second_turn_messages = llm._calls[1]
    joined = " ".join(m["content"] for m in second_turn_messages)
    assert "已识别方向" in joined
    assert "后端开发" in joined


def test_chat_faq_prompt_includes_knowledge_base():
    llm = _RecordingLLM([
        '{"intent": "study_faq", "direction": "", "position": ""}',
        "基于知识库的回答",
    ])
    svc = SalesChatService(
        llm,
        InMemoryStore(),
        SalesRepository(_session()),
        StubVipReport(),
        FakeKnowledgeBase([FaqHit(question="学习周期", content="学习周期取决于投入时间，4-6个月", score=0.8)]),
    )
    svc.chat(None, "学习周期多久", "web")

    faq_messages = llm._calls[1]
    joined = " ".join(m["content"] for m in faq_messages)
    assert "学习周期取决于投入时间" in joined
    assert "学习周期多久" in joined


def test_chat_course_prompt_introduces_courses_not_learning_path():
    llm = _RecordingLLM([
        '{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}',
        "课程介绍话术",
    ])
    catalog = FakeCourseCatalog(courses=[_course()])
    svc = SalesChatService(
        llm,
        InMemoryStore(),
        SalesRepository(_session()),
        StubVipReport(),
        FakeKnowledgeBase(),
        catalog=catalog,
    )
    svc.chat(None, "想学AI算法", "web")

    course_system = llm._calls[1][0]["content"]
    assert "课程列表" in course_system
    assert "不要假设或提及用户的学习路径" in course_system
    assert "不要展示课时和价格" in course_system


# ---------- 流式 ----------

def test_chat_stream_faq_events():
    svc = _service(
        ['{"intent": "enrollment_faq", "direction": "", "position": ""}', "报名流程答复"],
        kb_hits=[FaqHit(question="报名流程", content="交费→入学→签约", score=0.9)],
    )
    events = list(svc.chat_stream(None, "报名流程是什么", "web"))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    meta = events[0]
    assert meta["conversationId"].startswith("c_")
    assert meta["courses"] == []
    assert meta["leadSaved"] is False
    assert meta["sources"] == [
        {"question": "报名流程", "content": "交费→入学→签约", "score": 0.9}
    ]
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "报名流程答复"


def test_chat_stream_guide_single_delta():
    svc = _service(['{"intent": "direction_guide", "direction": "", "position": ""}'])
    events = list(svc.chat_stream(None, "你好", "web"))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) == 1
    assert "人工智能" in deltas[0]["content"]


def test_chat_stream_course_meta_includes_courses():
    catalog = FakeCourseCatalog(courses=[_course()])
    svc = _service(
        ['{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}', "AI课程推荐话术"],
        catalog=catalog,
    )
    events = list(svc.chat_stream(None, "想学AI算法", "web"))
    meta = events[0]
    assert meta["courses"][0]["courseId"] == "c1"
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "AI课程推荐话术"


class _RaisingChatLLM:
    def chat(self, messages):
        raise RuntimeError("llm down")

    def stream(self, messages):
        yield "x"


def test_chat_stream_emits_error_when_route_fails():
    svc = _service_with_llm(_RaisingChatLLM())
    events = list(svc.chat_stream(None, "你好", "web"))
    assert [e["type"] for e in events] == ["error"]


class _RaisingStreamLLM:
    def chat(self, messages):
        return LLMResult(content='{"intent": "enrollment_faq", "direction": "", "position": ""}')

    def stream(self, messages):
        yield "部分"
        raise RuntimeError("stream failed")


def test_chat_stream_emits_error_on_stream_failure():
    svc = SalesChatService(
        _RaisingStreamLLM(),
        InMemoryStore(),
        SalesRepository(_session()),
        StubVipReport(),
        FakeKnowledgeBase([FaqHit(question="报名流程", content="交费→入学", score=0.9)]),
    )
    events = list(svc.chat_stream(None, "报名流程", "web"))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert types[-1] == "error"
    assert "done" not in types
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "部分"


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)
