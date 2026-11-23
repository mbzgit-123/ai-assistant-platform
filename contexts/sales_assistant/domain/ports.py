from typing import Protocol

from contexts.sales_assistant.domain.catalog import CourseInfo, SubjectNode
from contexts.sales_assistant.domain.faq import FaqHit
from shared.infrastructure.db.models.business import Lead


class VipReportPort(Protocol):
    def report_vip(self, lead: Lead) -> bool: ...


class KnowledgeBasePort(Protocol):
    def search(self, question: str, top_k: int = 4) -> list[FaqHit]: ...


class CourseCatalogPort(Protocol):
    def get_subject_tree(self) -> list[SubjectNode]: ...

    def get_courses(self, subject_id: str, subject_parent_id: str) -> list[CourseInfo]: ...
