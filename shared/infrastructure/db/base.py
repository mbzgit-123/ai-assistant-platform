from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import DeclarativeBase

CHINA_TZ = timezone(timedelta(hours=8))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def china_today_start_utc() -> datetime:
    """返回中国时区（UTC+8）今天 00:00 对应的 naive UTC 时间，用于「每日」配额边界。"""
    now_cst = datetime.now(CHINA_TZ)
    today_cst = now_cst.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_cst.astimezone(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass
