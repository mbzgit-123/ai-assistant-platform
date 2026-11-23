from contexts.sales_assistant.domain.catalog import SubjectNode
from contexts.sales_assistant.domain.directions import (
    find_child,
    normalize_direction,
    normalize_position,
)


def test_normalize_direction_known():
    assert normalize_direction("想学Java") == "后端开发"
    assert normalize_direction("前端") == "前端开发"
    assert normalize_direction("人工智能") == "人工智能"
    assert normalize_direction("大模型") == "人工智能"
    assert normalize_direction("数据库") == "数据库开发"


def test_normalize_direction_no_match_returns_none():
    assert normalize_direction("我没方向") is None
    assert normalize_direction("不知道") is None
    assert normalize_direction("随便") is None


def test_normalize_direction_unclear_returns_none():
    assert normalize_direction("") is None
    assert normalize_direction(None) is None


def test_normalize_direction_non_string_returns_none():
    assert normalize_direction(123) is None
    assert normalize_direction(["AI"]) is None


def test_normalize_position_known():
    assert normalize_position("大模型算法岗") == "大模型算法开发岗"
    assert normalize_position("算法岗") == "大模型算法开发岗"
    assert normalize_position("应用开发") == "大模型应用开发岗"
    assert normalize_position("公共知识") == "大模型公共知识"


def test_normalize_position_unknown_returns_none():
    assert normalize_position("随便") is None
    assert normalize_position("") is None
    assert normalize_position(None) is None


def test_normalize_position_non_string_returns_none():
    assert normalize_position(123) is None
    assert normalize_position({"x": 1}) is None


def _children(*names):
    return tuple(SubjectNode(id=f"id_{n}", name=n, parent_id="p") for n in names)


def test_find_child_by_name_substring():
    children = _children("JavaScript", "jquery")
    assert find_child("想学 JavaScript", children).name == "JavaScript"


def test_find_child_by_position_alias():
    children = _children("大模型应用开发岗", "大模型算法开发岗", "大模型公共知识")
    assert find_child("算法", children).name == "大模型算法开发岗"
    assert find_child("大模型算法岗", children).name == "大模型算法开发岗"


def test_find_child_no_match_returns_none():
    children = _children("JavaScript", "jquery")
    assert find_child("随便", children) is None
    assert find_child(None, children) is None
    assert find_child("", ()) is None
