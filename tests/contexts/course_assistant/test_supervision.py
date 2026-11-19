from datetime import datetime, timedelta

from contexts.course_assistant.application.service import SupervisionService
from contexts.course_assistant.domain.supervision import ESCALATION_MESSAGE, IDLE_REMINDER_MESSAGE


class _StubProgress:
    def __init__(self, enrolled, last_completed=None):
        self.enrolled = enrolled
        self.last_completed = last_completed or {}

    def enrolled_student_ids(self):
        return self.enrolled

    def last_completed_at(self, student_id):
        return self.last_completed.get(student_id)


class _StubChannel:
    def __init__(self):
        self.sent = []

    def send(self, student_id, content):
        self.sent.append((student_id, content))
        return f"msg_{student_id}"


def _svc(enrolled, last):
    return SupervisionService(_StubProgress(enrolled, last), _StubChannel())


def test_never_completed_triggers_escalation():
    svc = _svc(["s1"], {})
    sent = svc.check_and_notify(now=datetime(2026, 11, 18, 12, 0, 0))
    assert len(sent) == 1
    assert sent[0]["content"] == ESCALATION_MESSAGE
    assert sent[0]["level"] == "escalation"
    assert sent[0]["messageId"] == "msg_s1"


def test_idle_3_days_triggers_reminder():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=3)})
    sent = svc.check_and_notify(now=now)
    assert sent[0]["level"] == "reminder"
    assert sent[0]["content"] == IDLE_REMINDER_MESSAGE


def test_idle_7_days_triggers_escalation():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=7)})
    assert svc.check_and_notify(now=now)[0]["level"] == "escalation"


def test_recent_activity_no_notification():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=1)})
    assert svc.check_and_notify(now=now) == []


def test_only_idle_students_notified():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1", "s2"], {"s1": now - timedelta(days=4), "s2": now - timedelta(days=1)})
    sent = svc.check_and_notify(now=now)
    assert [x["studentId"] for x in sent] == ["s1"]
