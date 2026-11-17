import re
from datetime import datetime, timezone

from shared.common.util.date_util import DateUtil


def test_now_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", DateUtil.now_iso())


def test_to_iso():
    dt = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert DateUtil.to_iso(dt) == "2026-11-17T12:00:00+00:00"
