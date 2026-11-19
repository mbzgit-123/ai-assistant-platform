from pydantic import BaseModel


class PlanRequest(BaseModel):
    position: str
    studentId: str | None = None


class RefreshRequest(BaseModel):
    position: str
    studentId: str
