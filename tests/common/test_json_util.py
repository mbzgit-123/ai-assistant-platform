from shared.common.util.json_util import JsonUtil


def test_roundtrip():
    assert JsonUtil.loads(JsonUtil.dumps({"a": 1})) == {"a": 1}


def test_dumps_no_ascii_escape():
    assert "中文" in JsonUtil.dumps({"a": "中文"})


def test_loads_invalid_returns_default():
    assert JsonUtil.loads("{bad json", default=None) is None
