from contexts.course_assistant.domain.path import LearningPlan, PathStep, PlanItem
from contexts.course_assistant.domain.ports import PathKnowledgePort, ProgressPort
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
