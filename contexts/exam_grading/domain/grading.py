def grade_choice(answer_content: dict, reference_answer: dict) -> tuple[bool, float]:
    """选择题确定性判分：比对所选选项与参考答案，返回 (is_correct, score)。"""
    correct = answer_content.get("selected") == reference_answer.get("correct")
    return (correct, 1.0 if correct else 0.0)


def rubric_hits(reference_answer: dict, answer_text: str) -> int:
    """统计参考答案要点在作答文本中命中的条数（确定性 rubric 校验）。"""
    points = reference_answer.get("points", [])
    return sum(1 for p in points if p and p in answer_text)
