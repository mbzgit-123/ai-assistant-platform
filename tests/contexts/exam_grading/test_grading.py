from contexts.exam_grading.domain.grading import grade_multi_choice, grade_code_fill, rubric_hits


def test_grade_multi_choice_correct_exact_set():
    assert grade_multi_choice({"selected": ["B", "D"]}, {"correct": ["B", "D"]}) == (True, 1.0)


def test_grade_multi_choice_incorrect_partial():
    assert grade_multi_choice({"selected": ["B"]}, {"correct": ["B", "D"]}) == (False, 0.0)


def test_grade_multi_choice_order_insensitive():
    assert grade_multi_choice({"selected": ["D", "B"]}, {"correct": ["B", "D"]}) == (True, 1.0)


def test_grade_multi_choice_missing_selected():
    assert grade_multi_choice({}, {"correct": ["B"]}) == (False, 0.0)


def test_grade_code_fill_all_correct():
    ref = {"answers": ["print", "return"]}
    assert grade_code_fill({"answers": ["print", "return"]}, ref) == (True, 1.0)


def test_grade_code_fill_partial_credit():
    ref = {"answers": ["print", "return"]}
    assert grade_code_fill({"answers": ["print", "wrong"]}, ref) == (False, 0.5)


def test_grade_code_fill_strips_whitespace():
    ref = {"answers": ["print", "return"]}
    assert grade_code_fill({"answers": [" print ", "return"]}, ref) == (True, 1.0)


def test_rubric_hits_counts_matching_points():
    ref = {"points": ["闭包", "作用域", "生命周期"]}
    assert rubric_hits(ref, "闭包和作用域是重点") == 2


def test_rubric_hits_zero():
    assert rubric_hits({"points": ["闭包"]}, "完全无关") == 0
