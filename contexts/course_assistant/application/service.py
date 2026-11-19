from datetime import datetime, timezone

from contexts.course_assistant.domain.path import LearningPlan, PathStep, PlanItem
from contexts.course_assistant.domain.ports import (
    MessageChannelPort,
    PathKnowledgePort,
    ProgressPort,
)
from contexts.course_assistant.domain.supervision import (
    ESCALATION_DAYS,
    ESCALATION_MESSAGE,
    IDLE_REMINDER_DAYS,
    IDLE_REMINDER_MESSAGE,
)
from shared.common.exception.base import BadRequestError
from shared.infrastructure.llm.port import LLMPort

PLAN_SYSTEM_PROMPT = "你是课程规划助手，为课程生成一句话学习内容说明。"


class CourseAssistantService:
    def __init__(
        self,
        llm: LLMPort,
        path_knowledge: PathKnowledgePort,
        progress: ProgressPort,
    ):
        self._llm = llm
        self._path_knowledge = path_knowledge
        self._progress = progress

    def generate_plan(self, position: str, student_id: str | None) -> LearningPlan:
        steps = self._path_knowledge.get_path(position)
        if not steps:
            raise BadRequestError(f"未知岗位方向: {position}")
        if self._has_foundation(student_id):
            steps = [s for s in steps if not s.is_foundation]
        items = [self._to_item(s) for s in steps]
        return LearningPlan(position=position, student_id=student_id, items=items)

    def replan(self, position: str, student_id: str) -> LearningPlan:
        plan = self.generate_plan(position, student_id)
        done = self._progress.completed_course_ids(student_id)
        plan.items = [i for i in plan.items if i.course_id not in done]
        return plan

    def _has_foundation(self, student_id: str | None) -> bool:
        if student_id is None:
            return False
        profile = self._progress.get_profile(student_id)
        return bool(profile and profile.major)

    def _to_item(self, step: PathStep) -> PlanItem:
        title = self._progress.get_course_title(step.course_id) or step.course_id
        content = self._content_for(title)
        return PlanItem(
            course_id=step.course_id,
            chapter_ids=step.chapter_ids,
            title=title,
            content=content,
        )

    def _content_for(self, title: str) -> str:
        result = self._llm.chat(
            [
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": f"课程：{title}。请给出该课程的学习内容简介。"},
            ]
        )
        content = (result.content or "").strip()
        return content or f"学习《{title}》"


class SupervisionService:
    def __init__(self, progress: ProgressPort, message_channel: MessageChannelPort):
        self._progress = progress
        self._message_channel = message_channel

    def check_and_notify(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        sent = []
        for student_id in self._progress.enrolled_student_ids():
            hit = self._detect(student_id, now)
            if hit is None:
                continue
            content, level = hit
            msg_id = self._message_channel.send(student_id, content)
            sent.append(
                {
                    "studentId": student_id,
                    "messageId": msg_id,
                    "content": content,
                    "level": level,
                }
            )
        return sent

    def _detect(self, student_id: str, now: datetime) -> tuple[str, str] | None:
        last = self._progress.last_completed_at(student_id)
        if last is None:
            return ESCALATION_MESSAGE, "escalation"
        days = (now - last).days
        if days >= ESCALATION_DAYS:
            return ESCALATION_MESSAGE, "escalation"
        if days >= IDLE_REMINDER_DAYS:
            return IDLE_REMINDER_MESSAGE, "reminder"
        return None
