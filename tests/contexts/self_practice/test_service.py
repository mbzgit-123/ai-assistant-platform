from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Video, StudentVideoProgress
from shared.common.exception.base import BadRequestError
from contexts.self_practice.domain.ports import Question, GradeResult
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService


class FakeQGen:
    def __init__(self):
        self.calls = 0
        self.chapter_exam_doc: str | None = None

    def plan_counts(self, video_ids):
        return {vid: 10 for vid in video_ids}

    def generate_by_video(self, video_id, count):
        self.calls += 1
        return [
            Question(f"q_{video_id}_{i}", video_id, "multi_choice",
                     {"stem": "s", "options": ["A", "B", "C", "D"]},
                     {"correct": ["A"]}, "exp")
            for i in range(count)
        ]

    def generate_from_document(self, course_document):
        self.calls += 1
        return [
            Question("q_mc", "", "multi_choice",
                     {"stem": "选择", "options": ["选项A", "选项B", "选项C", "选项D"]},
                     {"correct": ["A"]}, "exp"),
            Question("q_sa", "", "short_answer",
                     {"stem": "简答"}, {"points": ["p"]}, "exp"),
            Question("q_code", "", "code_fill",
                     {"stem": "代码", "code": "x = ___(1)___\ny = ___(2)___"},
                     {"answers": ["1", "2"]}, "exp"),
            Question("q_sc", "", "scenario",
                     {"scenario": "场景描述", "task": "方案任务"},
                     {"points": ["p"]}, "exp"),
        ]

    def generate_chapter_exam(self, course_document):
        self.calls += 1
        self.chapter_exam_doc = course_document
        return self.generate_from_document(course_document)


class FakeGrader:
    def grade(self, question, answer_content):
        return GradeResult(True, 1.0, "正确")


class RecordingGrader:
    def __init__(self, result=None):
        self._result = result or GradeResult(True, 1.0, "正确")
        self.received = []

    def grade(self, question, answer_content):
        self.received.append((question, answer_content))
        return self._result


def _service(videos=None, completed=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    if videos:
        s.add_all(videos)
        s.commit()
    if completed:
        s.add_all(completed)
        s.commit()
    return PracticeService(FakeQGen(), FakeGrader(), PracticeRepository(s))


def test_start_admission_blocked():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600)])
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"])


def test_start_soft_requires_confirm():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=1800)])
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"])
    result = svc.start_practice("stu", "c1", ["v1"], confirm=True)
    assert result["practiceId"].startswith("pr_")


def test_start_over_limit_blocked():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=5401)])
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"], confirm=True)


def test_start_generates_and_persists():
    svc = _service(videos=[
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600),
    ])
    result = svc.start_practice("stu", "c1", ["v1"])
    assert result["practiceId"].startswith("pr_")
    assert result["groupedByVideo"] is True
    assert len(result["questions"]) == 10


def test_start_reuses_without_regenerating():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
    s.commit()
    repo = PracticeRepository(s)
    # 预置已有题目（复用）
    repo.save_questions("pr_old", [Question("q_existing", "v1", "multi_choice",
        {"stem": "s", "options": ["A", "B", "C", "D"]}, {"correct": ["A"]}, "exp")])
    svc = PracticeService(qgen, FakeGrader(), repo)
    result = svc.start_practice("stu", "c1", ["v1"])
    assert qgen.calls == 0  # 未调用生成
    assert [q["questionId"] for q in result["questions"]] == ["q_existing"]


def test_start_regenerate_forces_regeneration():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
    s.commit()
    repo = PracticeRepository(s)
    repo.save_questions("pr_old", [Question("q_existing", "v1", "multi_choice",
        {"stem": "s", "options": ["A", "B", "C", "D"]}, {"correct": ["A"]}, "exp")])
    svc = PracticeService(qgen, FakeGrader(), repo)
    result = svc.start_practice("stu", "c1", ["v1"], regenerate=True)
    assert qgen.calls == 1  # 强制重新生成
    assert [q["questionId"] for q in result["questions"]] != ["q_existing"]


def test_available_videos_only_completed():
    svc = _service(
        videos=[Video(video_id="v1", chapter_id="c1", title="t1", duration_seconds=600),
                Video(video_id="v2", chapter_id="c1", title="t2", duration_seconds=600)],
        completed=[StudentVideoProgress(id=1, student_id="stu", video_id="v1", chapter_id="c1",
                                        completed_at=datetime(2026, 11, 17))],
    )
    vids = svc.available_videos("stu", "c1")
    assert [v["videoId"] for v in vids] == ["v1"]


def test_submit_grades_and_returns_summary():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    start = svc.start_practice("stu", "c1", ["v1"])
    pid = start["practiceId"]
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": ["A"]}}
               for q in start["questions"]]
    result = svc.submit_practice(pid, answers)
    assert result["summary"]["total"] == 10
    assert result["summary"]["correct"] == 10
    assert len(result["results"]) == 10


def test_submit_backfills_session_and_history_returns_it():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    start = svc.start_practice("stu", "c1", ["v1"])
    pid = start["practiceId"]
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": ["A"]}}
               for q in start["questions"]]
    svc.submit_practice(pid, answers)
    history = svc.get_history("stu")
    assert len(history["sessions"]) == 1
    s = history["sessions"][0]
    assert s["practiceId"] == pid
    assert s["status"] == "submitted"
    assert s["correctCount"] == 10
    assert s["questionCount"] == 10


def test_history_question_count_reflects_reused_questions():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
    s.commit()
    repo = PracticeRepository(s)
    svc = PracticeService(qgen, FakeGrader(), repo)
    first = svc.start_practice("stu", "c1", ["v1"])
    svc.submit_practice(
        first["practiceId"],
        [{"questionId": q["questionId"], "answerContent": {"selected": ["A"]}}
         for q in first["questions"]],
    )
    second = svc.start_practice("stu", "c1", ["v1"])  # 复用旧题
    assert qgen.calls == 1  # 未重新生成
    svc.submit_practice(
        second["practiceId"],
        [{"questionId": q["questionId"], "answerContent": {"selected": ["A"]}}
         for q in second["questions"]],
    )
    history = svc.get_history("stu")
    second_session = next(
        s for s in history["sessions"] if s["practiceId"] == second["practiceId"]
    )
    assert second_session["questionCount"] == 10


def test_history_orders_sessions_desc():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    p1 = svc.start_practice("stu", "c1", ["v1"])["practiceId"]
    p2 = svc.start_practice("stu", "c1", ["v1"])["practiceId"]
    ids = [s["practiceId"] for s in svc.get_history("stu")["sessions"]]
    assert ids == [p2, p1]


def test_generate_practice_returns_frontend_shape_and_persists():
    svc = _service()
    result = svc.generate_practice("stu", "# 文档", [
        {"videoId": "v1"},
    ])
    assert result["practiceId"].startswith("pr_")

    by_type = {q["type"]: q for q in result["questions"]}
    assert set(by_type) == {"indefinite", "essay", "code", "scenario"}

    # 不定项选项转换：label 从 A 开始，text 来自 options
    assert by_type["indefinite"]["options"] == [
        {"label": "A", "text": "选项A"},
        {"label": "B", "text": "选项B"},
        {"label": "C", "text": "选项C"},
        {"label": "D", "text": "选项D"},
    ]

    # 代码填空：blanks 从 ___(N)___ 占位符计算
    assert by_type["code"]["code"] == "x = ___(1)___\ny = ___(2)___"
    assert by_type["code"]["blanks"] == 2

    # 场景分析：scenario/task 展开
    assert by_type["scenario"]["scenario"] == "场景描述"
    assert by_type["scenario"]["stem"] == "方案任务"

    # 落库：历史能查到该 session
    history = svc.get_history("stu")
    assert len(history["sessions"]) == 1
    assert history["sessions"][0]["practiceId"] == result["practiceId"]


def _service_with_grader(grader, videos=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    if videos:
        s.add_all(videos)
        s.commit()
    return PracticeService(FakeQGen(), grader, PracticeRepository(s))


def test_grade_practice_returns_frontend_shape():
    svc = _service_with_grader(
        RecordingGrader(),
        videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)],
    )
    start = svc.start_practice("stu", "c1", ["v1"])
    pid = start["practiceId"]
    answers = [{"questionId": q["questionId"], "answer": [0]} for q in start["questions"]]
    result = svc.grade_practice(pid, answers)
    assert result["practiceId"] == pid
    assert result["totalScore"] == 10.0
    assert result["fullScore"] == 10
    assert len(result["results"]) == 10
    r = result["results"][0]
    assert set(r) == {"questionId", "isCorrect", "score", "feedback", "correctAnswer", "reference"}


def test_grade_practice_converts_choice_indices_to_labels():
    grader = RecordingGrader()
    svc = _service_with_grader(
        grader,
        videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)],
    )
    start = svc.start_practice("stu", "c1", ["v1"])
    q = start["questions"][0]
    svc.grade_practice(start["practiceId"], [{"questionId": q["questionId"], "answer": [0, 2]}])
    _, content = grader.received[0]
    assert content == {"selected": ["A", "C"]}


def test_grade_practice_converts_answer_formats_per_type():
    grader = RecordingGrader()
    svc = _service_with_grader(grader)
    result = svc.generate_practice("stu", "# 文档", [
        {"videoId": "v1"},
    ])
    by_type = {q["type"]: q for q in result["questions"]}
    svc.grade_practice(result["practiceId"], [
        {"questionId": by_type["indefinite"]["id"], "answer": [1]},
        {"questionId": by_type["essay"]["id"], "answer": "我的作答"},
        {"questionId": by_type["code"]["id"], "answer": ["1", "2"]},
        {"questionId": by_type["scenario"]["id"], "answer": "方案"},
    ])
    received = {q.question_type: c for q, c in grader.received}
    assert received["multi_choice"] == {"selected": ["B"]}
    assert received["short_answer"] == {"text": "我的作答"}
    assert received["code_fill"] == {"answers": ["1", "2"]}
    assert received["scenario"] == {"text": "方案"}


def test_grade_practice_correct_answer_per_type():
    svc = _service_with_grader(RecordingGrader())
    result = svc.generate_practice("stu", "# 文档", [
        {"videoId": "v1"},
    ])
    by_type = {q["type"]: q for q in result["questions"]}
    graded = svc.grade_practice(result["practiceId"], [
        {"questionId": by_type["indefinite"]["id"], "answer": [0]},
        {"questionId": by_type["essay"]["id"], "answer": "x"},
        {"questionId": by_type["code"]["id"], "answer": ["1"]},
        {"questionId": by_type["scenario"]["id"], "answer": "x"},
    ])
    correct = {r["questionId"]: r["correctAnswer"] for r in graded["results"]}
    # 选择题 -> 正确选项字母；代码填空 -> 各空答案；主观题 -> 空
    assert correct[by_type["indefinite"]["id"]] == "A"
    assert correct[by_type["code"]["id"]] == "1、2"
    assert correct[by_type["essay"]["id"]] == ""
    assert correct[by_type["scenario"]["id"]] == ""


def test_get_practice_returns_review_shape():
    svc = _service_with_grader(RecordingGrader())
    result = svc.generate_practice("stu", "# 文档", [
        {"videoId": "v1"},
    ])
    by_type = {q["type"]: q for q in result["questions"]}
    pid = result["practiceId"]
    svc.grade_practice(pid, [
        {"questionId": by_type["indefinite"]["id"], "answer": [0, 2]},
        {"questionId": by_type["essay"]["id"], "answer": "我的作答"},
        {"questionId": by_type["code"]["id"], "answer": ["1", "x"]},
        {"questionId": by_type["scenario"]["id"], "answer": "方案"},
    ])
    detail = svc.get_practice(pid)
    assert detail["practiceId"] == pid
    assert detail["summary"]["total"] == 4
    qs = {q["type"]: q for q in detail["questions"]}
    # 选择题：answer 回转为下标，correctAnswer 为正确选项字母
    assert qs["indefinite"]["answer"] == [0, 2]
    assert qs["indefinite"]["correctAnswer"] == "A"
    assert qs["indefinite"]["options"][0] == {"label": "A", "text": "选项A"}
    # 代码填空：answer 为答案数组，correctAnswer 为各空答案
    assert qs["code"]["answer"] == ["1", "x"]
    assert qs["code"]["correctAnswer"] == "1、2"
    # 主观题：answer 为字符串
    assert qs["essay"]["answer"] == "我的作答"
    assert qs["scenario"]["answer"] == "方案"


def test_get_practice_preserves_question_order():
    svc = _service_with_grader(RecordingGrader())
    result = svc.generate_practice("stu", "# 文档", [{"videoId": "v1"}])
    pid = result["practiceId"]
    # 生成顺序固定为 选择 -> 论述 -> 代码 -> 场景，提交也按此顺序
    ordered_ids = [q["id"] for q in result["questions"]]
    svc.grade_practice(pid, [
        {"questionId": ordered_ids[0], "answer": [0]},
        {"questionId": ordered_ids[1], "answer": "x"},
        {"questionId": ordered_ids[2], "answer": ["1"]},
        {"questionId": ordered_ids[3], "answer": "x"},
    ])
    detail = svc.get_practice(pid)
    types = [q["type"] for q in detail["questions"]]
    assert types == ["indefinite", "essay", "code", "scenario"]


def test_grade_practice_reference_is_explanation_text():
    svc = _service_with_grader(RecordingGrader())
    result = svc.generate_practice("stu", "# 文档", [
        {"videoId": "v1"},
    ])
    by_type = {q["type"]: q for q in result["questions"]}
    graded = svc.grade_practice(result["practiceId"], [
        {"questionId": by_type["indefinite"]["id"], "answer": [0]},
        {"questionId": by_type["essay"]["id"], "answer": "x"},
        {"questionId": by_type["code"]["id"], "answer": ["1"]},
        {"questionId": by_type["scenario"]["id"], "answer": "x"},
    ])
    refs = {r["questionId"]: r["reference"] for r in graded["results"]}
    # FakeQGen 所有题 explanation 均为 "exp"，reference 直接取题干解析文本
    assert refs[by_type["indefinite"]["id"]] == "exp"
    assert refs[by_type["code"]["id"]] == "exp"


def test_start_chapter_exam_fuses_summaries_and_persists():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    svc = PracticeService(qgen, FakeGrader(), PracticeRepository(s))
    result = svc.start_chapter_exam("stu", "c1", [
        {"videoId": "v1", "title": "视频一", "summary": "  要点A  "},
        {"videoId": "v2", "title": "视频二", "summary": ""},
        {"videoId": "v3", "title": "视频三", "summary": "要点B"},
    ])
    # 融合：跳过空摘要，标题作小节头，段落空行分隔
    assert qgen.chapter_exam_doc == "## 视频一\n要点A\n\n## 视频三\n要点B"
    assert result["practiceId"].startswith("pr_")
    assert {q["type"] for q in result["questions"]} == {"indefinite", "essay", "code", "scenario"}
    history = svc.get_history("stu")
    assert len(history["sessions"]) == 1
    assert history["sessions"][0]["practiceId"] == result["practiceId"]


def test_start_chapter_exam_empty_summaries_raises():
    svc = _service()
    with pytest.raises(BadRequestError):
        svc.start_chapter_exam("stu", "c1", [{"videoId": "v1", "title": "t", "summary": ""}])


def test_daily_practice_limit():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    svc.start_practice("stu", "c1", ["v1"])
    svc.start_practice("stu", "c1", ["v1"])  # 第 2 次（复用旧题）仍放行
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"])  # 第 3 次超限


def test_daily_chapter_exam_limit():
    svc = _service()
    svc.start_chapter_exam("stu", "c1", [{"videoId": "v1", "title": "t", "summary": "要点"}])
    with pytest.raises(BadRequestError):
        svc.start_chapter_exam("stu", "c1", [{"videoId": "v1", "title": "t", "summary": "要点"}])


def test_quota_separate_practice_and_exam():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    svc.start_practice("stu", "c1", ["v1"])
    svc.start_practice("stu", "c1", ["v1"])  # 练习配额用满
    # 章节考试配额独立，不受练习次数影响
    result = svc.start_chapter_exam("stu", "c1", [{"videoId": "v1", "title": "t", "summary": "要点"}])
    assert result["practiceId"].startswith("pr_")


def test_history_filter_by_type():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    practice_pid = svc.start_practice("stu", "c1", ["v1"])["practiceId"]
    exam_pid = svc.start_chapter_exam("stu", "c1", [{"videoId": "v1", "title": "t", "summary": "要点"}])["practiceId"]

    practice_only = svc.get_history("stu", "practice")["sessions"]
    assert [s["practiceId"] for s in practice_only] == [practice_pid]

    exam_only = svc.get_history("stu", "chapter_exam")["sessions"]
    assert [s["practiceId"] for s in exam_only] == [exam_pid]

    all_sessions = svc.get_history("stu")["sessions"]
    assert {s["practiceId"] for s in all_sessions} == {practice_pid, exam_pid}
