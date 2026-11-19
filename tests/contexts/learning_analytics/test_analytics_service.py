from datetime import datetime

from contexts.learning_analytics.application.service import LearningAnalyticsService
from contexts.learning_analytics.domain.ports import AnswerRecord
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubData:
    def __init__(self, enrolled=0, completed=0, total=0, records=None, last_completed=None):
        self.enrolled = enrolled
        self.completed = completed
        self.total = total
        self.records = records or []
        self.last_completed = last_completed

    def enrolled_course_count(self, student_id):
        return self.enrolled

    def completed_video_count(self, student_id):
        return self.completed

    def enrolled_video_count(self, student_id):
        return self.total

    def answer_records(self, student_id):
        return self.records

    def last_completed_at(self, student_id):
        return self.last_completed


def _svc(data):
    return LearningAnalyticsService(data, FakeLLMAdapter(responses=["归因"]))


def test_profile_aggregates_counts_accuracy_and_subjective_score():
    data = _StubData(
        enrolled=2,
        completed=3,
        total=10,
        records=[
            AnswerRecord(is_correct=True, question_type="choice"),
            AnswerRecord(is_correct=False, question_type="choice"),
            AnswerRecord(is_correct=True, question_type="short_answer", score=8.0),
            AnswerRecord(is_correct=False, question_type="scenario", score=6.0),
        ],
    )
    p = _svc(data).analyze("s1").profile
    assert p.enrolled_courses == 2
    assert p.completed_videos == 3
    assert p.total_videos == 10
    assert p.overall_accuracy == 0.5
    assert p.subjective_avg_score == 7.0


def test_profile_empty_data_is_zeroed():
    p = _svc(_StubData()).analyze("s1").profile
    assert p.enrolled_courses == 0
    assert p.completed_videos == 0
    assert p.total_videos == 0
    assert p.overall_accuracy is None
    assert p.subjective_avg_score is None
    assert p.last_active_at is None


def test_profile_last_active_at_prefers_latest():
    t_video = datetime(2026, 11, 1, 8, 0, 0)
    t_answer = datetime(2026, 11, 10, 20, 0, 0)
    data = _StubData(
        records=[AnswerRecord(answered_at=t_answer)],
        last_completed=t_video,
    )
    p = _svc(data).analyze("s1").profile
    assert p.last_active_at == t_answer


def test_profile_excludes_deterministic_types_from_subjective_score():
    # 不定项选择 / 代码填空为确定性判分，不计入主观题平均分
    data = _StubData(
        records=[
            AnswerRecord(question_type="short_answer", score=8.0),
            AnswerRecord(question_type="multi_choice", score=10.0),
            AnswerRecord(question_type="code_fill", score=9.0),
        ],
    )
    p = _svc(data).analyze("s1").profile
    assert p.subjective_avg_score == 8.0


def test_profile_accuracy_ignores_ungraded_answers():
    data = _StubData(
        records=[
            AnswerRecord(is_correct=True, question_type="choice"),
            AnswerRecord(is_correct=None, question_type="short_answer", score=8.0),
        ],
    )
    p = _svc(data).analyze("s1").profile
    assert p.overall_accuracy == 1.0


def test_trend_buckets_accuracy_by_chapter_and_day():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=True, answered_at=datetime(2026, 11, 1, 9, 0)),
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False, answered_at=datetime(2026, 11, 1, 10, 0)),
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=True, answered_at=datetime(2026, 11, 8, 9, 0)),
        ],
    )
    trend = _svc(data).analyze("s1").trend
    assert [t.period for t in trend] == ["2026-11-01", "2026-11-08"]
    assert [t.accuracy for t in trend] == [0.5, 1.0]
    assert all(t.chapter_id == "ch1" for t in trend)


def test_trend_ignores_answers_without_chapter():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id=None, is_correct=True, answered_at=datetime(2026, 11, 1)),
        ],
    )
    assert _svc(data).analyze("s1").trend == []


def test_weak_points_flags_low_accuracy_chapters():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=True),
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False),
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False),
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False),
            AnswerRecord(chapter_id="ch2", chapter_title="函数", is_correct=True),
            AnswerRecord(chapter_id="ch2", chapter_title="函数", is_correct=True),
            AnswerRecord(chapter_id="ch2", chapter_title="函数", is_correct=True),
            AnswerRecord(chapter_id="ch2", chapter_title="函数", is_correct=False),
        ],
    )
    weak = _svc(data).analyze("s1").weak_points
    assert len(weak) == 1
    assert weak[0].chapter_id == "ch1"
    assert weak[0].chapter_title == "循环"
    assert weak[0].accuracy == 0.25
    assert weak[0].reason == "归因"


def test_weak_points_fallback_when_llm_empty():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False),
        ],
    )
    svc = LearningAnalyticsService(data, FakeLLMAdapter(responses=[""]))
    weak = svc.analyze("s1").weak_points
    assert weak[0].reason == "章节「循环」正确率 0%，建议回看对应视频并加强练习。"


class _RaisingLLM:
    def chat(self, messages):
        raise RuntimeError("llm down")


def test_weak_points_fallback_when_llm_raises():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=False),
        ],
    )
    svc = LearningAnalyticsService(data, _RaisingLLM())
    weak = svc.analyze("s1").weak_points
    assert weak[0].reason == "章节「循环」正确率 0%，建议回看对应视频并加强练习。"


def test_weak_points_no_weak_chapters_returns_empty():
    data = _StubData(
        records=[
            AnswerRecord(chapter_id="ch1", chapter_title="循环", is_correct=True),
        ],
    )
    assert _svc(data).analyze("s1").weak_points == []


def test_weak_points_limits_to_three_weakest():
    records = []
    for i in range(5):
        records.append(AnswerRecord(chapter_id=f"ch{i}", chapter_title=f"章节{i}", is_correct=False))
    data = _StubData(records=records)
    weak = _svc(data).analyze("s1").weak_points
    assert len(weak) == 3
    assert [w.chapter_id for w in weak] == ["ch0", "ch1", "ch2"]
