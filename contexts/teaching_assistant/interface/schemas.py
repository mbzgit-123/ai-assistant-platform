from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    studentId: str | None = None
