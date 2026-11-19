import pytest

from shared.common.exception.base import BadRequestError
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.course_assistant.application.service import CourseAssistantService
from contexts.course_assistant.domain.path import PathStep
from contexts.course_assistant.domain.ports import StudentProfile
from contexts.course_assistant.infrastructure.path_knowledge import InMemoryPathKnowledge


class _StubProgress:
    def __init__(self, profile=None, titles=None, completed=None):
        self.profile = profile
        self.titles = titles or {}
        self.completed = completed or set()

    def get_profile(self, student_id):
        return self.profile

    def get_course_title(self, course_id):
        return self.titles.get(course_id)

    def completed_course_ids(self, student_id):
        return self.completed


def _svc(llm_responses=None, progress=None):
    kb = InMemoryPathKnowledge({
        "大模型应用开发岗": [
            PathStep("found", ["ch0"], is_foundation=True),
            PathStep("adv1", ["ch1"], is_foundation=False),
        ],
    })
    llm = FakeLLMAdapter(responses=llm_responses if llm_responses is not None else ["学习内容"])
    return CourseAssistantService(llm, kb, progress or _StubProgress())


def test_generate_plan_keeps_foundation_for_zero_basis():
    svc = _svc(progress=_StubProgress(profile=StudentProfile(education="本科", major=None)))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["found", "adv1"]


def test_generate_plan_skips_foundation_for_experienced():
    svc = _svc(progress=_StubProgress(profile=StudentProfile(education="本科", major="计算机")))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["adv1"]


def test_generate_plan_uses_title_and_llm_content():
    titles = {"found": "Python 基础", "adv1": "大模型应用"}
    svc = _svc(llm_responses=["学习 Python 基础语法"], progress=_StubProgress(titles=titles))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert plan.items[0].title == "Python 基础"
    assert plan.items[0].content == "学习 Python 基础语法"


def test_generate_plan_fallback_content_when_llm_empty():
    titles = {"found": "Python 基础", "adv1": "大模型应用"}
    svc = _svc(llm_responses=[""], progress=_StubProgress(titles=titles))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert plan.items[0].content == "学习《Python 基础》"


def test_generate_plan_unknown_position_raises():
    svc = _svc()
    with pytest.raises(BadRequestError):
        svc.generate_plan("不存在的岗位", "s1")


def test_replan_removes_completed_courses():
    svc = _svc(progress=_StubProgress(completed={"adv1"}, titles={"found": "基础", "adv1": "进阶"}))
    plan = svc.replan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["found"]


def test_replan_all_completed_returns_empty():
    svc = _svc(progress=_StubProgress(completed={"found", "adv1"}, titles={"found": "基础", "adv1": "进阶"}))
    plan = svc.replan("大模型应用开发岗", "s1")
    assert plan.items == []
