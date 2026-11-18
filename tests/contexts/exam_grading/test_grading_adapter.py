from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.self_practice.domain.ports import Question
from contexts.exam_grading.infrastructure.adapter import GradingAdapter


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_grade_choice_deterministic():
    a = GradingAdapter(_session(), FakeLLMAdapter())
    q = Question("q1", "v1", "choice", {"stem": "s", "options": ["A", "B", "C", "D"]}, {"correct": "B"}, "exp")
    r = a.grade(q, {"selected": "B"})
    assert r.is_correct and r.score == 1.0


def test_grade_subjective_uses_llm():
    llm = FakeLLMAdapter(responses=['{"is_correct": true, "score": 0.8, "feedback": "要点基本命中"}'])
    a = GradingAdapter(_session(), llm)
    q = Question("q2", "v1", "short_answer", {"stem": "s"}, {"points": ["闭包"]}, "exp")
    r = a.grade(q, {"text": "闭包是..."})
    assert r.is_correct and r.score == 0.8


def test_grade_subjective_bad_json_falls_back_to_manual():
    a = GradingAdapter(_session(), FakeLLMAdapter(responses=["bad", "bad"]))
    q = Question("q3", "v1", "scenario", {"stem": "s"}, {"points": ["a"]}, "exp")
    r = a.grade(q, {"text": "x"})
    assert r.is_correct is False and r.feedback == "转人工批改"
