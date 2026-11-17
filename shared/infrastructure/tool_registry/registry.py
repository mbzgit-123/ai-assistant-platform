from collections.abc import Callable


class ToolRegistry:
    """按业务上下文（context）隔离的工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Callable]] = {}

    def register(self, context: str, name: str, fn: Callable) -> None:
        self._tools.setdefault(context, {})[name] = fn

    def get(self, context: str, name: str) -> Callable:
        return self._tools[context][name]

    def list(self, context: str | None = None) -> dict:
        if context is not None:
            return dict(self._tools.get(context, {}))
        return {c: dict(tools) for c, tools in self._tools.items()}
