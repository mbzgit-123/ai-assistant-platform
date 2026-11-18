from contexts.exam_grading.domain.grading import grade_choice, rubric_hits


def test_grade_choice_correct():
    assert grade_choice({"selected": "B"}, {"correct": "B"}) == (True, 1.0)


def test_grade_choice_incorrect():
    assert grade_choice({"selected": "A"}, {"correct": "B"}) == (False, 0.0)


def test_grade_choice_missing_selected():
    assert grade_choice({}, {"correct": "B"}) == (False, 0.0)


def test_rubric_hits_counts_matching_points():
    ref = {"points": ["闭包", "作用域", "生命周期"]}
    assert rubric_hits(ref, "闭包和作用域是重点") == 2


def test_rubric_hits_zero():
    assert rubric_hits({"points": ["闭包"]}, "完全无关") == 0
