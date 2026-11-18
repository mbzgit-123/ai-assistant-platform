DIRECTIONS = ["Java", "前端", "AI", "其他"]
AI_POSITIONS = ["大模型算法岗", "大模型应用开发岗"]


def normalize_direction(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    if "java" in t or "后端" in t:
        return "Java"
    if "前端" in t or "web" in t or "网页" in t:
        return "前端"
    if "ai" in t or "人工智能" in t or "大模型" in t:
        return "AI"
    if any(k in t for k in ("其他", "没方向", "不知道", "不确定", "没想好")):
        return "其他"
    return None


def normalize_position(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    if "算法" in t:
        return "大模型算法岗"
    if "应用" in t:
        return "大模型应用开发岗"
    return None


FAQ_ENROLLMENT = [
    (
        ("报名", "入学", "流程"),
        "报名流程：1) 在线提交报名信息；2) 顾问老师电话/微信确认；3) 缴费开通课程；4) 进入班级群开始学习。",
    ),
    (
        ("包就业", "就业", "内推", "薪资"),
        "我们提供就业指导服务（简历优化、模拟面试、岗位内推），但不承诺包就业。",
    ),
]

FAQ_STUDY = [
    (
        ("自学", "自己学"),
        "可以自学，平台提供录播课、题库与答疑服务；想系统高效学习建议跟班，有老师答疑和督学。",
    ),
    (
        ("周期", "多久", "多长时间"),
        "学习周期因方向与基础而异：全日制约 4-6 个月，业余学习约 6-12 个月。",
    ),
]


def match_faq(message: str, faq_table: list[tuple[tuple[str, ...], str]]) -> str | None:
    for keywords, answer in faq_table:
        if any(k in message for k in keywords):
            return answer
    return None
