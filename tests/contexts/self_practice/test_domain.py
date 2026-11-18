from contexts.self_practice.domain.admission import check_admission
from contexts.self_practice.domain.merge import merge_counts
from contexts.self_practice.domain.ports import (
    Question,
    GradeResult,
    QuestionGenerationPort,
    GradingPort,
)


def test_check_admission_block():
    r = check_admission(1799)
    assert r.level == "block" and r.shortfall_seconds == 1801


def test_check_admission_soft():
    r = check_admission(1800)
    assert r.level == "soft" and r.shortfall_seconds == 1800


def test_check_admission_allow_boundary():
    r = check_admission(3600)
    assert r.level == "allow" and r.shortfall_seconds == 0


def test_check_admission_allow_over():
    assert check_admission(7200).level == "allow"


def test_check_admission_soft_upper_boundary():
    assert check_admission(3599).level == "soft"


def test_merge_counts_under_cap_unchanged():
    assert merge_counts([10, 10, 10]) == [10, 10, 10]


def test_merge_counts_scales_down():
    assert merge_counts([15, 15, 15]) == [10, 10, 10]
    assert merge_counts([20, 20]) == [15, 15]


def test_merge_counts_small_unchanged():
    assert merge_counts([5, 5]) == [5, 5]


def test_merge_counts_floor_beats_cap_when_too_many_videos():
    # 11 个视频 × 保底 3 = 33 > 上限 30：保底优先，不抛异常、无负题量
    result = merge_counts([3] * 11)
    assert all(c >= 3 for c in result)
    assert sum(result) >= 30


def test_question_and_grade_result_dataclasses():
    q = Question("q1", "v1", "choice", {"stem": "s"}, {"correct": "B"}, "exp")
    assert q.question_id == "q1" and q.video_id == "v1"
    g = GradeResult(True, 1.0, "正确")
    assert g.is_correct and g.score == 1.0
