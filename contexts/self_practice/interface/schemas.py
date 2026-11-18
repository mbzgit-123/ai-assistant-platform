from pydantic import BaseModel


class StartPracticeRequest(BaseModel):
    studentId: str
    chapterId: str
    videoIds: list[str]


class AnswerItem(BaseModel):
    questionId: str
    answerContent: dict


class SubmitPracticeRequest(BaseModel):
    practiceId: str
    answers: list[AnswerItem]
