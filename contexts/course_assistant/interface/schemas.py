from pydantic import BaseModel


class PlanRequest(BaseModel):
    position: str
    studentId: str | None = None
