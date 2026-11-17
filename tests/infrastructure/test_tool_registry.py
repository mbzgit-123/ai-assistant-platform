import pytest

from shared.infrastructure.tool_registry.registry import ToolRegistry


def test_register_get_context_isolation():
    r = ToolRegistry()
    f1 = lambda: 1
    f2 = lambda: 2
    r.register("sales", "query_course", f1)
    r.register("teaching", "query_course", f2)
    assert r.get("sales", "query_course") is f1
    assert r.get("teaching", "query_course") is f2


def test_list_filtered_by_context():
    r = ToolRegistry()
    r.register("sales", "a", lambda: 1)
    r.register("teaching", "b", lambda: 2)
    assert set(r.list("sales").keys()) == {"a"}


def test_get_missing_raises():
    r = ToolRegistry()
    with pytest.raises(KeyError):
        r.get("sales", "nope")
