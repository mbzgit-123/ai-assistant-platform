from shared.common.util.string_util import StringUtil


def test_is_blank():
    assert StringUtil.is_blank(None) is True
    assert StringUtil.is_blank("") is True
    assert StringUtil.is_blank("   ") is True
    assert StringUtil.is_blank("x") is False


def test_strip_to_none():
    assert StringUtil.strip_to_none("  ") is None
    assert StringUtil.strip_to_none(" a ") == "a"


def test_truncate():
    assert StringUtil.truncate("hi", 5) == "hi"
    assert StringUtil.truncate("hello world", 5) == "hello..."
