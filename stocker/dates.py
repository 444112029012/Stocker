from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")


def now_tw() -> datetime:
    return datetime.now(TZ)


def today_tw() -> date:
    return now_tw().date()


def is_weekend(d: date | None = None) -> bool:
    d = d or today_tw()
    return d.weekday() >= 5


def iso_date(d: date | None = None) -> str:
    return (d or today_tw()).strftime("%Y-%m-%d")


def yyyymmdd(d: date | None = None) -> str:
    return (d or today_tw()).strftime("%Y%m%d")


def roc_to_date(value: str) -> date | None:
    """Convert MOPS/TWSE ROC dates like 1150818 or 115/08/18."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 7:
        year = int(digits[:3]) + 1911
        month = int(digits[3:5])
        day = int(digits[5:7])
        return date(year, month, day)
    if len(digits) == 8:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    return None


def format_roc_slash(d: date) -> str:
    """115/08/18 used by some TPEx endpoints."""
    roc_year = d.year - 1911
    return f"{roc_year:03d}/{d.month:02d}/{d.day:02d}"


def previous_business_days(n: int = 7, start: date | None = None) -> list[date]:
    d = start or today_tw()
    out: list[date] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def parse_hhmmss(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit()).zfill(6)[-6:]
    return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"
