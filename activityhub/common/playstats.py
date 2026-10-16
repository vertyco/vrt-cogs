"""The Stats tab's numbers, counted by the database so the bot never loads a period's rows"""

import bisect
import typing as t
from dataclasses import dataclass
from datetime import date

from ..db.tables import Play

DAY = 86400
# Day numbers count days since 1970-01-01, a Thursday. EPOCH turns a day number into a date's ordinal
EPOCH = date(1970, 1, 1).toordinal()
# All time shows a bar per week while that makes this many bars or fewer, then a bar per month
WEEK_BARS_MAX = 26
PERIODS = {"7": 7, "30": 30, "0": 0}
# The viewer's clock offset from UTC in minutes, from UTC-12:00 to UTC+14:00
OFFSET_MIN = -720
OFFSET_MAX = 840
ALL = "all"
OUTSIDE = "none"
TABLE = Play._meta.tablename
# One row of plays, players and phone counts. SUM over no rows is NULL, hence the COALESCE
TOTALS = (
    "COUNT(*) AS plays, COUNT(DISTINCT user_id) AS players, "
    "COALESCE(SUM(platform = 'mobile'), 0) AS mobile, COALESCE(SUM(platform != ''), 0) AS known"
)

# A server id, ALL or OUTSIDE
Scope = t.Union[int, str]


@dataclass
class StatsQuery:
    # A server id, ALL, OUTSIDE, or None for wherever the Activity is running
    server: str | None
    # 7, 30, or 0 for all time
    days: int
    # Minutes the viewer's clock is ahead of UTC
    offset: int


@dataclass
class Period:
    days: int
    # Seconds the viewer's clock is ahead of UTC
    shift: int
    # The viewer's local day number
    today: int

    @classmethod
    def make(cls, days: int, offset: int, now: float) -> "Period":
        shift = offset * 60
        return cls(days, shift, int((now + shift) // DAY))

    @property
    def first(self) -> int | None:
        """The local day the period starts on: today and the days before it, or None for all time"""
        return self.today - self.days + 1 if self.days else None


def whole_number(text: str) -> int | None:
    digits = text.removeprefix("-")
    # isdigit() alone also accepts characters int() refuses, like "²"
    if not digits.isascii() or not digits.isdigit() or len(digits) > 4:
        return None
    return -int(digits) if text.startswith("-") else int(digits)


def is_server_id(text: str) -> bool:
    # Discord ids are at most 20 digits
    return text.isascii() and text.isdigit() and len(text) <= 20


def read_query(query: t.Mapping[str, str]) -> StatsQuery | None:
    """The stats request's settings, or None when one is missing or malformed"""
    days = PERIODS.get(query.get("days", ""))
    offset = whole_number(query.get("offset", ""))
    server = query.get("server")
    if days is None or offset is None or not OFFSET_MIN <= offset <= OFFSET_MAX:
        return None
    if server is not None and server not in (ALL, OUTSIDE) and not is_server_id(server):
        return None
    return StatsQuery(server, days, offset)


def scope_for(server: str | None, guild_id: int | None, is_owner: bool, is_admin: bool) -> Scope | None:
    """Whose plays a viewer may see, or None when not these. Admins see their own server, the owner anything"""
    if server is None:
        server = str(guild_id) if guild_id is not None else ALL
    if server in (ALL, OUTSIDE):
        return server if is_owner else None
    wanted = int(server)
    return wanted if is_owner or (is_admin and wanted == guild_id) else None


def filters(scope: Scope, period: Period) -> tuple[str, list]:
    """The WHERE clause, with Piccolo's {} placeholders, and its values"""
    parts, args = [], []
    if scope == OUTSIDE:
        parts.append("guild_id IS NULL")
    elif scope != ALL:
        parts.append("guild_id = {}")
        args.append(scope)
    if period.first is not None:
        parts.append("started_at >= {}")
        args.append(period.first * DAY - period.shift)
    return (" WHERE " + " AND ".join(parts)) if parts else "", args


def share(mobile: int, known: int) -> float | None:
    return mobile / known if known else None


def week_start(day: int) -> int:
    """The Monday on or before a day. Day 0 was a Thursday"""
    return day - (day + 3) % 7


def month_start(day: int) -> int:
    return date.fromordinal(EPOCH + day).replace(day=1).toordinal() - EPOCH


def next_month(day: int) -> int:
    when = date.fromordinal(EPOCH + day)
    year, month = (when.year + 1, 1) if when.month == 12 else (when.year, when.month + 1)
    return date(year, month, 1).toordinal() - EPOCH


def bar_kind(period: Period, first: int) -> str:
    if period.days:
        return "day"
    weeks = (period.today - week_start(first)) // 7 + 1
    return "week" if weeks <= WEEK_BARS_MAX else "month"


def bar_starts(kind: str, first: int, today: int) -> list[int]:
    """The local day each bar starts on, from the bar holding `first` to the bar holding today"""
    if kind == "day":
        return list(range(first, today + 1))
    if kind == "week":
        return list(range(week_start(first), today + 1, 7))
    starts = [month_start(first)]
    while next_month(starts[-1]) <= today:
        starts.append(next_month(starts[-1]))
    return starts


async def overall(where: str, args: list) -> dict:
    row = (await Play.raw(f"SELECT {TOTALS} FROM {TABLE}{where}", *args))[0]
    return {"plays": row["plays"], "players": row["players"], "phone": share(row["mobile"], row["known"])}


async def medians(where: str, args: list) -> dict[str, float]:
    """Each game's middle play length, the lower middle for an even count, found without loading the lengths"""
    rows = await Play.raw(
        "SELECT game, seconds FROM (SELECT game, seconds, "
        "ROW_NUMBER() OVER (PARTITION BY game ORDER BY seconds) AS n, COUNT(*) OVER (PARTITION BY game) AS c "
        f"FROM {TABLE}{where}) WHERE n = (c + 1) / 2",
        *args,
    )
    return {row["game"]: row["seconds"] for row in rows}


async def game_lines(where: str, args: list, names: dict[str, str]) -> list[dict]:
    rows = await Play.raw(f"SELECT game, {TOTALS} FROM {TABLE}{where} GROUP BY game ORDER BY plays DESC, game", *args)
    middles = await medians(where, args)
    return [
        {
            "key": row["game"],
            # A game uninstalled since shows its key
            "name": names.get(row["game"], row["game"]),
            "plays": row["plays"],
            "players": row["players"],
            "typical": middles.get(row["game"]),
            "phone": share(row["mobile"], row["known"]),
        }
        for row in rows
    ]


def tally(charts: dict, rows: list[dict], part: str, spot: t.Callable[[dict], int], size: int) -> None:
    """Add each row's plays to its game's chart and to the all-games chart"""
    for row in rows:
        for key in ("", row["game"]):
            chart = charts.setdefault(key, {"bars": [0] * size, "hours": [0] * 24})
            chart[part][spot(row)] += row["plays"]


async def charts(where: str, args: list, period: Period) -> dict:
    days = await Play.raw(
        f"SELECT game, CAST((started_at + {{}}) / {DAY} AS INTEGER) AS day, COUNT(*) AS plays "
        f"FROM {TABLE}{where} GROUP BY game, day",
        period.shift,
        *args,
    )
    hours = await Play.raw(
        f"SELECT game, CAST(started_at + {{}} AS INTEGER) % {DAY} / 3600 AS hour, COUNT(*) AS plays "
        f"FROM {TABLE}{where} GROUP BY game, hour",
        period.shift,
        *args,
    )
    first = period.first if period.first is not None else min((row["day"] for row in days), default=None)
    if first is None:
        return {"bars": {"kind": "day", "starts": []}, "charts": {}}
    kind = bar_kind(period, first)
    starts = bar_starts(kind, first, period.today)
    found: dict = {}
    tally(found, days, "bars", lambda row: bisect.bisect_right(starts, row["day"]) - 1, len(starts))
    tally(found, hours, "hours", lambda row: row["hour"], len(starts))
    labels = [date.fromordinal(EPOCH + start).isoformat() for start in starts]
    return {"bars": {"kind": kind, "starts": labels}, "charts": found}


async def server_list(guild_name: t.Callable[[int], str | None]) -> list[dict]:
    """Every server with plays, most first, for the owner's picker. Servers the bot left show their id"""
    rows = await Play.raw(
        f"SELECT guild_id, COUNT(*) AS plays FROM {TABLE} GROUP BY guild_id ORDER BY plays DESC, guild_id"
    )
    servers = [
        {"id": str(row["guild_id"]), "name": guild_name(row["guild_id"]) or str(row["guild_id"]), "plays": row["plays"]}
        for row in rows
        if row["guild_id"] is not None
    ]
    outside = [
        {"id": OUTSIDE, "name": "Outside servers", "plays": row["plays"]} for row in rows if row["guild_id"] is None
    ]
    return servers + outside


async def stats_json(
    scope: Scope, period: Period, names: dict[str, str], guild_name: t.Callable[[int], str | None], owner: bool
) -> dict:
    where, args = filters(scope, period)
    found = await charts(where, args, period)
    return {
        "server": str(scope),
        "overall": await overall(where, args),
        "games": await game_lines(where, args, names),
        "bars": found["bars"],
        "charts": found["charts"],
        "servers": await server_list(guild_name) if owner else None,
    }
