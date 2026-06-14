from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def pt_now() -> datetime:
    return datetime.now(tz=PT)


def pt_date_string() -> str:
    return pt_now().date().isoformat()
