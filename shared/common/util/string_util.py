class StringUtil:
    @staticmethod
    def is_blank(value: str | None) -> bool:
        return value is None or value.strip() == ""

    @staticmethod
    def strip_to_none(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def truncate(value: str, max_len: int, suffix: str = "...") -> str:
        if len(value) <= max_len:
            return value
        return value[:max_len] + suffix
