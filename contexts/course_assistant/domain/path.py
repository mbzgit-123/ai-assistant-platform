from dataclasses import dataclass, field


@dataclass
class PathStep:
    course_id: str
    chapter_ids: list[str]
    is_foundation: bool = False


@dataclass
class PlanItem:
    course_id: str
    chapter_ids: list[str]
    title: str
    content: str


@dataclass
class LearningPlan:
    position: str
    student_id: str | None
    items: list[PlanItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "studentId": self.student_id,
            "items": [
                {
                    "courseId": item.course_id,
                    "chapterIds": item.chapter_ids,
                    "title": item.title,
                    "content": item.content,
                }
                for item in self.items
            ],
        }
