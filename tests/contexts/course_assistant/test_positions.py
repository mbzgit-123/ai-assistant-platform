from contexts.course_assistant.domain.positions import POSITIONS


def test_positions_contain_three_job_roles():
    assert POSITIONS == ("Java 开发岗", "大模型算法岗", "大模型应用开发岗")
