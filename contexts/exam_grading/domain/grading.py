def grade_multi_choice(answer_content: dict, reference_answer: dict) -> tuple[bool, float]:
    """不定项选择确定性判分：所选集合与正确集合完全一致才得分（0/1）。"""
    selected = answer_content.get("selected", [])
    correct = reference_answer.get("correct", [])
    is_correct = set(selected) == set(correct)
    return (is_correct, 1.0 if is_correct else 0.0)


def grade_code_fill(answer_content: dict, reference_answer: dict) -> tuple[bool, float]:
    """代码填空确定性判分：逐空位去首尾空白精确比对，按空位比例给分。"""
    expected = reference_answer.get("answers", [])
    if not expected:
        return (False, 0.0)
    submitted = answer_content.get("answers", [])
    correct_count = sum(
        1
        for a, e in zip(submitted, expected)
        if str(a).strip() == str(e).strip()
    )
    score = correct_count / len(expected)
    return (correct_count == len(expected), score)


def rubric_hits(reference_answer: dict, answer_text: str) -> int:
    """统计参考答案要点在作答文本中命中的条数（确定性 rubric 校验）。"""
    points = reference_answer.get("points", [])
    return sum(1 for p in points if p and p in answer_text)
