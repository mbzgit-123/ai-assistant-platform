from contexts.course_assistant.domain.path import LearningPlan, PathStep, PlanItem


def test_path_step_default_not_foundation():
    s = PathStep(course_id="c1", chapter_ids=["ch1"])
    assert s.is_foundation is False


def test_learning_plan_to_dict_serializes_items():
    plan = LearningPlan(
        position="大模型应用开发岗",
        student_id="s1",
        items=[PlanItem(course_id="c1", chapter_ids=["ch1"], title="Python 基础", content="学习 Python")],
    )
    assert plan.to_dict() == {
        "position": "大模型应用开发岗",
        "studentId": "s1",
        "items": [
            {"courseId": "c1", "chapterIds": ["ch1"], "title": "Python 基础", "content": "学习 Python"}
        ],
    }
