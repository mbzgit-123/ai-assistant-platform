from contexts.course_assistant.domain.path import PathStep
from contexts.course_assistant.infrastructure.path_knowledge import DEFAULT_PATHS, InMemoryPathKnowledge


def test_default_path_orders_steps_with_foundation_first():
    kb = InMemoryPathKnowledge()
    steps = kb.get_path("大模型应用开发岗")
    assert [s.course_id for s in steps] == ["ai_py_basic", "llm_foundation", "llm_app_dev"]
    assert steps[0].is_foundation is True
    assert steps[1].is_foundation is False


def test_unknown_position_returns_empty():
    kb = InMemoryPathKnowledge()
    assert kb.get_path("不存在的岗位") == []


def test_custom_paths_override_defaults():
    kb = InMemoryPathKnowledge({"测试岗": [PathStep("c1", ["ch1"], is_foundation=True)]})
    assert kb.get_path("测试岗")[0].course_id == "c1"


def test_all_three_positions_have_paths():
    kb = InMemoryPathKnowledge()
    for p in ("Java 开发岗", "大模型算法岗", "大模型应用开发岗"):
        assert kb.get_path(p) != []
