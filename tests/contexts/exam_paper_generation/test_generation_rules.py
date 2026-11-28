from contexts.exam_paper_generation.domain.anchor import (
    slice_content_md,
    split_long_interval,
    has_code_block,
    extract_code_blocks,
    blank_code,
)
from contexts.exam_paper_generation.domain.count import (
    count_for_duration,
    plan_question_counts,
    plan_chapter_exam_counts,
)
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


def test_has_code_block_requires_more_than_10_lines():
    long_block = "```python\n" + "\n".join(f"line{i}" for i in range(11)) + "\n```"
    assert has_code_block("说明文字\n" + long_block) is True
    assert has_code_block("说明文字\n```python\nprint(1)\n```") is False
    assert has_code_block("纯文字无代码") is False


def test_extract_code_blocks_returns_inner_code():
    doc = "说明\n```python\nimport torch\nx = 1\n```\n\n```java\nint y = 2;\n```"
    assert extract_code_blocks(doc) == ["import torch\nx = 1", "int y = 2;"]


def test_extract_code_blocks_empty_when_no_code():
    assert extract_code_blocks("纯文字无代码") == []


def test_blank_code_extracts_original_tokens():
    # 优先挖函数调用名/方法名（核心），而不是赋值左侧的变量名
    code = "loss = criterion(output, target)\noptimizer.zero_grad()\nloss.backward()"
    blanked, answers = blank_code(code)
    assert answers == ["criterion", "zero_grad", "backward"]
    assert "loss = ___(1)___(output, target)" in blanked
    assert "optimizer.___(2)___()" in blanked
    assert "loss.___(3)___()" in blanked


def test_blank_code_skips_keywords_and_common_vars():
    code = "import torch\ndef forward(x):\n    return x * 2"
    blanked, answers = blank_code(code)
    assert "def" not in answers
    assert "import" not in answers
    assert "return" not in answers
    assert "x" not in answers  # 占位变量不作为挖空目标
    assert answers == ["torch", "forward"]


def test_blank_code_respects_num_blanks():
    code = "\n".join(f"var_{i} = {i}" for i in range(10))
    blanked, answers = blank_code(code, num_blanks=3)
    assert answers == ["var_0", "var_1", "var_2"]
    assert "var_3" in blanked  # 未挖空部分原样保留
    assert "___(4)___" not in blanked


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
    assert allocate_types(3, False) == {"multi_choice": 1, "short_answer": 1, "scenario": 1, "code_fill": 0}


def test_allocate_types_code_present():
    assert allocate_types(4, True) == {"multi_choice": 1, "short_answer": 1, "scenario": 1, "code_fill": 1}
    assert allocate_types(10, True) == {"multi_choice": 2, "short_answer": 2, "scenario": 3, "code_fill": 3}
    assert allocate_types(15, True) == {"multi_choice": 4, "short_answer": 3, "scenario": 4, "code_fill": 4}


def test_allocate_types_no_code_big():
    assert allocate_types(15, False) == {"multi_choice": 6, "short_answer": 5, "scenario": 4, "code_fill": 0}


def test_allocate_types_sum_equals_total():
    for total in range(3, 31):
        for has_code in (False, True):
            d = allocate_types(total, has_code)
            assert sum(d.values()) == total


def test_plan_question_counts_short():
    assert plan_question_counts(1499, False) == {
        "multi_choice": 10, "short_answer": 3, "code_fill": 0, "scenario": 1,
    }


def test_plan_question_counts_medium():
    assert plan_question_counts(2000, False) == {
        "multi_choice": 12, "short_answer": 4, "code_fill": 0, "scenario": 1,
    }


def test_plan_question_counts_long():
    assert plan_question_counts(4001, False) == {
        "multi_choice": 15, "short_answer": 5, "code_fill": 0, "scenario": 1,
    }


def test_plan_question_counts_boundaries_are_medium():
    assert plan_question_counts(1500, False)["multi_choice"] == 12
    assert plan_question_counts(4000, False)["multi_choice"] == 12


def test_plan_question_counts_with_code():
    assert plan_question_counts(2000, True)["code_fill"] == 1
    assert plan_question_counts(2000, False)["code_fill"] == 0


def test_plan_chapter_exam_counts_fixed():
    assert plan_chapter_exam_counts() == {
        "multi_choice": 20,
        "short_answer": 5,
        "code_fill": 1,
        "scenario": 1,
    }
