def count_for_duration(duration_seconds: int) -> int:
    """按视频时长区间映射单视频默认题量（确定性取区间下限）。

    <5 分钟→3；5–15 分钟→5；15–30 分钟→8；>30 分钟→10（封顶 15 的区间下限）。
    """
    if duration_seconds < 300:
        return 3
    if duration_seconds < 900:
        return 5
    if duration_seconds < 1800:
        return 8
    return 10


def plan_question_counts(content_len: int, has_code: bool) -> dict[str, int]:
    """按文档切片长度确定各题型数量（前端练习卷固定规格）。

    - 不定项选择 10~15、论述 3~5：按切片字符数分档（<1500 / 1500~4000 / >4000）
    - 代码填空：切片含 ≥15 行代码块出 1 道，否则 0
    - 场景分析：固定 1 道
    """
    if content_len < 1500:
        multi_choice, short_answer = 10, 3
    elif content_len <= 4000:
        multi_choice, short_answer = 12, 4
    else:
        multi_choice, short_answer = 15, 5
    return {
        "multi_choice": multi_choice,
        "short_answer": short_answer,
        "code_fill": 1 if has_code else 0,
        "scenario": 1,
    }


def plan_chapter_exam_counts() -> dict[str, int]:
    """章节考试固定题型规格：20 不定项 + 5 论述 + 1 代码填空 + 1 场景。"""
    return {
        "multi_choice": 20,
        "short_answer": 5,
        "code_fill": 1,
        "scenario": 1,
    }
