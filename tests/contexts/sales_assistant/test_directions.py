from contexts.sales_assistant.domain.directions import (
    normalize_direction,
    normalize_position,
    match_faq,
    FAQ_ENROLLMENT,
    FAQ_STUDY,
)


def test_normalize_direction_known():
    assert normalize_direction("想学Java") == "Java"
    assert normalize_direction("前端") == "前端"
    assert normalize_direction("人工智能") == "AI"
    assert normalize_direction("大模型") == "AI"


def test_normalize_direction_no_direction():
    assert normalize_direction("我没方向") == "其他"
    assert normalize_direction("不知道") == "其他"


def test_normalize_direction_unclear_returns_none():
    assert normalize_direction("") is None
    assert normalize_direction(None) is None
    assert normalize_direction("随便") is None


def test_normalize_position_known():
    assert normalize_position("大模型算法岗") == "大模型算法岗"
    assert normalize_position("算法岗") == "大模型算法岗"
    assert normalize_position("应用开发") == "大模型应用开发岗"


def test_normalize_position_unknown_returns_none():
    assert normalize_position("随便") is None
    assert normalize_position("") is None
    assert normalize_position(None) is None


def test_match_faq_enrollment_flow_exact_answer():
    assert match_faq("报名流程是什么", FAQ_ENROLLMENT) == "报名流程：1) 在线提交报名信息；2) 顾问老师电话/微信确认；3) 缴费开通课程；4) 进入班级群开始学习。"


def test_match_faq_enrollment_job():
    assert match_faq("包就业吗", FAQ_ENROLLMENT) == FAQ_ENROLLMENT[1][1]


def test_match_faq_study_period():
    assert match_faq("学习周期多久", FAQ_STUDY) == FAQ_STUDY[1][1]


def test_match_faq_miss_returns_none():
    assert match_faq("今天天气如何", FAQ_ENROLLMENT) is None
    assert match_faq("今天天气如何", FAQ_STUDY) is None
