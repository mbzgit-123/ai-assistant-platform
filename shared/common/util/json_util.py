import json
from typing import Any


class JsonUtil:
    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def loads(value: str, default: Any = None) -> Any:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return default
