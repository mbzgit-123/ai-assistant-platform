from contexts.course_assistant.domain.path import PathStep

DEFAULT_PATHS: dict[str, list[PathStep]] = {
    "大模型应用开发岗": [
        PathStep("ai_py_basic", ["ai_py_basic_c1"], is_foundation=True),
        PathStep("llm_foundation", ["llm_foundation_c1"], is_foundation=False),
        PathStep("llm_app_dev", ["llm_app_dev_c1"], is_foundation=False),
    ],
    "大模型算法岗": [
        PathStep("ai_py_basic", ["ai_py_basic_c1"], is_foundation=True),
        PathStep("math_foundation", ["math_foundation_c1"], is_foundation=True),
        PathStep("machine_learning", ["ml_c1"], is_foundation=False),
        PathStep("llm_algorithm", ["llm_algo_c1"], is_foundation=False),
    ],
    "Java 开发岗": [
        PathStep("java_basic", ["java_basic_c1"], is_foundation=True),
        PathStep("db_foundation", ["db_c1"], is_foundation=False),
        PathStep("spring_framework", ["spring_c1"], is_foundation=False),
        PathStep("microservice", ["microservice_c1"], is_foundation=False),
    ],
}


class InMemoryPathKnowledge:
    def __init__(self, paths: dict[str, list[PathStep]] | None = None):
        self._paths = paths if paths is not None else DEFAULT_PATHS

    def get_path(self, position: str) -> list[PathStep]:
        return list(self._paths.get(position, []))
