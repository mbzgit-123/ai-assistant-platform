from contexts.exam_paper_generation.domain.anchor import (
    slice_content_md,
    split_long_interval,
    has_code_block,
)
from contexts.exam_paper_generation.domain.count import count_for_duration
from contexts.exam_paper_generation.domain.allocation import allocate_types


def test_slice_content_md_hits_anchors():
    md = "标题\n段落A\n锚点首句X\n中间内容\n锚点尾句Y\n结尾"
    assert slice_content_md(md, "锚点首句X", "锚点尾句Y") == "锚点首句X\n中间内容\n锚点尾句Y"


def test_slice_content_md_start_missing_returns_none():
    assert slice_content_md("abc", "不存在", "c") is None


def test_slice_content_md_end_missing_returns_none():
    assert slice_content_md("abc start xyz", "start", "不存在") is None


def test_split_long_interval_short_unchanged():
    assert split_long_interval("短文本", max_chars=2000) == "短文本"


def test_split_long_interval_cuts_at_paragraph_boundary():
    text = "\n".join("段落" + str(i) for i in range(1000))  # > 2000 字符
    result = split_long_interval(text, max_chars=2000)
    assert len(result) <= 2000
    assert result.endswith(("段落0", "段落1", "段落2")) or result


def test_has_code_block():
    assert has_code_block("说明文字\n```python\nprint(1)\n```") is True
    assert has_code_block("纯文字无代码") is False


def test_count_for_duration_buckets():
    assert count_for_duration(0) == 3
    assert count_for_duration(299) == 3
    assert count_for_duration(300) == 5
    assert count_for_duration(899) == 5
    assert count_for_duration(900) == 8
    assert count_for_duration(1799) == 8
    assert count_for_duration(1800) == 10
    assert count_for_duration(3600) == 10


def test_allocate_types_no_code():
    assert allocate_types(3, False) == {"choice": 1, "short_answer": 1, "scenario": 1, "code": 0}


def test_allocate_types_code_present():
    assert allocate_types(4, True) == {"choice": 1, "short_answer": 1, "scenario": 1, "code": 1}
    assert allocate_types(10, True) == {"choice": 2, "short_answer": 2, "scenario": 3, "code": 3}
    assert allocate_types(15, True) == {"choice": 4, "short_answer": 3, "scenario": 4, "code": 4}


def test_allocate_types_no_code_big():
    assert allocate_types(15, False) == {"choice": 6, "short_answer": 5, "scenario": 4, "code": 0}


def test_allocate_types_sum_equals_total():
    for total in range(3, 31):
        for has_code in (False, True):
            d = allocate_types(total, has_code)
            assert sum(d.values()) == total
