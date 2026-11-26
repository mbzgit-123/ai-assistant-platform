from pydantic import BaseModel, ConfigDict


class StartPracticeRequest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    studentId: str
    chapterId: str
    videoIds: list[str]
    confirm: bool = False
    regenerate: bool = False


class AnswerItem(BaseModel):
    questionId: str
    answerContent: dict


class SubmitPracticeRequest(BaseModel):
    practiceId: str
    answers: list[AnswerItem]


class PracticeVideoItem(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    videoId: str = ""


class GeneratePracticeRequest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    studentId: str
    courseDocument: str
    videos: list[PracticeVideoItem]
    courseId: str = ""
    courseTitle: str = ""


class GradeAnswerItem(BaseModel):
    questionId: str
    answer: list | str  # 前端自然作答：indefinite 下标数组 / code 答案数组 / 其余字符串


class GradePracticeRequest(BaseModel):
    practiceId: str
    answers: list[GradeAnswerItem]
