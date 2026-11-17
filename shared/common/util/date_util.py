from datetime import datetime, timezone


class DateUtil:
    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def now_iso() -> str:
        return DateUtil.now().isoformat()

    @staticmethod
    def to_iso(dt: datetime) -> str:
        return dt.isoformat()
