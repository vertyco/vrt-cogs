"""FarmCord's shared calendar: one season per real week and a rainy day about one in four, the same for everyone.
Everything here is UTC unix seconds"""

import hashlib
import math
from datetime import date, datetime, timedelta, timezone

from .. import catalog

HOUR = catalog.HOUR
DAY = catalog.DAY
WEEK = 7 * DAY
SEASONS = ("spring", "summer", "autumn", "winter")
# Monday 2026-01-05 00:00 UTC, the first moment of the first spring
EPOCH = datetime(2026, 1, 5, tzinfo=timezone.utc).timestamp()


def week_index(t: float) -> int:
    """Whole weeks since the epoch, counting backwards before it"""
    return math.floor((t - EPOCH) / DAY) // 7


def season_at(t: float) -> str:
    return SEASONS[week_index(t) % len(SEASONS)]


def season_ends_at(t: float) -> float:
    """The moment the season `t` is in gives way to the next"""
    return EPOCH + (week_index(t) + 1) * WEEK


def day_number(t: float) -> int:
    """UTC days since 1970-01-01"""
    return math.floor(t / DAY)


def date_of_day(number: int) -> date:
    return date(1970, 1, 1) + timedelta(days=number)


def is_rainy(day: date) -> bool:
    """Whether a UTC calendar date is rainy. Worked out from the date alone, so everyone agrees"""
    digest = hashlib.sha256(f"farmcord:{day.isoformat()}".encode()).hexdigest()
    return int(digest, 16) % 4 == 0


def weather_at(t: float) -> str:
    """The weather on the UTC day `t` falls in: sun, rain, or snow (a rainy day in winter)"""
    if not is_rainy(date_of_day(day_number(t))):
        return "sun"
    return "snow" if season_at(t) == "winter" else "rain"


def day_ends_at(t: float) -> float:
    """The next UTC midnight after `t`"""
    return (day_number(t) + 1) * DAY


def rained_between(start: float, end: float) -> bool:
    """Whether any UTC day overlapping [start, end) is rainy"""
    if end <= start:
        return False
    last_day = math.ceil(end / DAY) - 1
    return any(is_rainy(date_of_day(number)) for number in range(day_number(start), last_day + 1))


def in_season(crop_key: str, t: float) -> bool:
    return season_at(t) in catalog.CROPS[crop_key].seasons
