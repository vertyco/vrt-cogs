from datetime import date, datetime, timezone

import pytest
import pytest_asyncio

from activityhub.common.playstats import (
    ALL,
    EPOCH,
    OUTSIDE,
    Period,
    StatsQuery,
    bar_kind,
    bar_starts,
    read_query,
    scope_for,
    stats_json,
    week_start,
)
from activityhub.db.tables import Play

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc).timestamp()
NAMES = {"vegas": "Vegas", "tanks": "Tanks", "snake": "Snake"}
GUILDS = {500: "Test Server"}


def day(iso: str) -> int:
    return date.fromisoformat(iso).toordinal() - EPOCH


TODAY = day("2026-10-16")


def play(game, user, hours_ago, seconds, platform="mobile", guild=500):
    return Play(
        guild_id=guild,
        user_id=user,
        game=game,
        platform=platform,
        started_at=NOW - hours_ago * 3600,
        seconds=seconds,
    )


ROWS = [
    ("vegas", 1, 1, 100),
    ("vegas", 1, 2, 300, "desktop"),
    ("vegas", 2, 30, 200),
    ("tanks", 3, 3, 50, ""),
    ("tanks", 3, 24 * 10, 70),
    ("snake", 4, 5, 10, "mobile", None),
    ("gone", 5, 4, 60, "mobile", 600),
]


@pytest_asyncio.fixture
async def seeded(playdb):
    await Play.insert(*[play(*row) for row in ROWS])


async def stats(scope, days=7, offset=0, owner=False):
    return await stats_json(scope, Period.make(days, offset, NOW), NAMES, GUILDS.get, owner)


def spots(counts):
    return {index: count for index, count in enumerate(counts) if count}


def test_read_query():
    assert read_query({"days": "7", "offset": "-300"}) == StatsQuery(None, 7, -300)
    assert read_query({"days": "0", "offset": "840", "server": "all"}) == StatsQuery("all", 0, 840)
    assert read_query({"days": "30", "offset": "0", "server": "none"}) == StatsQuery("none", 30, 0)
    assert read_query({"days": "30", "offset": "-720", "server": "123"}) == StatsQuery("123", 30, -720)


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"days": "7"},
        {"offset": "0"},
        {"days": "14", "offset": "0"},
        {"days": "7", "offset": "841"},
        {"days": "7", "offset": "-721"},
        {"days": "7", "offset": "60.5"},
        {"days": "7", "offset": "abc"},
        {"days": "7", "offset": "\u00b2"},
        {"days": "7", "offset": "0", "server": "abc"},
        {"days": "7", "offset": "0", "server": "1" * 21},
    ],
)
def test_read_query_refuses_bad_settings(query):
    assert read_query(query) is None


def test_scope_for():
    # A server admin: their own server only
    assert scope_for(None, 500, False, True) == 500
    assert scope_for("500", 500, False, True) == 500
    assert scope_for("600", 500, False, True) is None
    assert scope_for(ALL, 500, False, True) is None
    assert scope_for(OUTSIDE, 500, False, True) is None
    # A player
    assert scope_for(None, 500, False, False) is None
    assert scope_for(None, None, False, False) is None
    # The bot owner: anything, and all servers when outside one
    assert scope_for("600", 500, True, True) == 600
    assert scope_for(ALL, 500, True, True) == ALL
    assert scope_for(None, None, True, False) == ALL
    assert scope_for(OUTSIDE, None, True, False) == OUTSIDE


def test_weeks_start_on_monday():
    assert week_start(day("2026-10-16")) == day("2026-10-12")
    assert week_start(day("2026-10-12")) == day("2026-10-12")
    assert week_start(day("2026-10-18")) == day("2026-10-12")


def test_bar_starts():
    assert bar_starts("day", TODAY - 2, TODAY) == [TODAY - 2, TODAY - 1, TODAY]
    assert bar_starts("week", day("2026-10-01"), TODAY) == [day("2026-09-28"), day("2026-10-05"), day("2026-10-12")]
    months = ["2025-11", "2025-12"] + [f"2026-{month:02d}" for month in range(1, 11)]
    assert bar_starts("month", day("2025-11-20"), TODAY) == [day(f"{month}-01") for month in months]


def test_all_time_uses_weeks_up_to_26_bars_then_months():
    period = Period(0, 0, TODAY)
    assert bar_kind(period, week_start(TODAY) - 25 * 7) == "week"
    assert bar_kind(period, week_start(TODAY) - 26 * 7) == "month"
    assert bar_kind(Period(30, 0, TODAY), TODAY - 29) == "day"


@pytest.mark.asyncio
async def test_a_server_over_7_days(seeded):
    found = await stats(500)
    assert found["server"] == "500" and found["servers"] is None
    assert found["overall"] == {"plays": 4, "players": 3, "phone": pytest.approx(2 / 3)}
    assert found["games"] == [
        {"key": "vegas", "name": "Vegas", "plays": 3, "players": 2, "typical": 200.0, "phone": pytest.approx(2 / 3)},
        {"key": "tanks", "name": "Tanks", "plays": 1, "players": 1, "typical": 50.0, "phone": None},
    ]
    assert found["bars"] == {"kind": "day", "starts": [f"2026-10-{n}" for n in range(10, 17)]}
    assert found["charts"][""]["bars"] == [0, 0, 0, 0, 0, 1, 3]
    assert found["charts"]["vegas"]["bars"] == [0, 0, 0, 0, 0, 1, 2]
    assert spots(found["charts"]["vegas"]["hours"]) == {6: 1, 10: 1, 11: 1}
    assert spots(found["charts"]["tanks"]["hours"]) == {9: 1}


@pytest.mark.asyncio
async def test_days_and_hours_follow_the_viewers_clock(seeded):
    found = await stats(500, offset=720)
    assert found["bars"]["starts"][-1] == "2026-10-17"
    assert found["charts"]["vegas"]["bars"] == [0, 0, 0, 0, 1, 2, 0]
    assert spots(found["charts"]["vegas"]["hours"]) == {18: 1, 22: 1, 23: 1}
    assert spots(found["charts"]["tanks"]["hours"]) == {21: 1}


@pytest.mark.asyncio
async def test_all_time_in_weeks(seeded):
    found = await stats(500, days=0)
    assert found["bars"] == {"kind": "week", "starts": ["2026-10-05", "2026-10-12"]}
    assert found["charts"][""]["bars"] == [1, 4]
    tanks = next(game for game in found["games"] if game["key"] == "tanks")
    # The lower of the two middle lengths
    assert (tanks["plays"], tanks["typical"]) == (2, 50.0)


@pytest.mark.asyncio
async def test_all_time_in_months_once_weeks_get_too_many(seeded):
    await Play.insert(play("vegas", 9, 24 * 400, 5))
    found = await stats(500, days=0)
    assert found["bars"]["kind"] == "month"
    assert found["bars"]["starts"][0] == "2025-09-01" and found["bars"]["starts"][-1] == "2026-10-01"
    assert len(found["bars"]["starts"]) == 14
    assert found["charts"][""]["bars"][0] == 1


@pytest.mark.asyncio
async def test_all_servers_and_outside_servers(seeded):
    found = await stats(ALL, owner=True)
    assert [(game["key"], game["name"]) for game in found["games"]] == [
        ("vegas", "Vegas"),
        ("gone", "gone"),
        ("snake", "Snake"),
        ("tanks", "Tanks"),
    ]
    assert found["servers"] == [
        {"id": "500", "name": "Test Server", "plays": 5},
        {"id": "600", "name": "600", "plays": 1},
        {"id": "none", "name": "Outside servers", "plays": 1},
    ]
    outside = await stats(OUTSIDE, owner=True)
    assert outside["server"] == "none" and [game["key"] for game in outside["games"]] == ["snake"]


@pytest.mark.asyncio
async def test_no_plays_gives_empty_numbers(seeded):
    found = await stats(700, days=0)
    assert found == {
        "server": "700",
        "overall": {"plays": 0, "players": 0, "phone": None},
        "games": [],
        "bars": {"kind": "day", "starts": []},
        "charts": {},
        "servers": None,
    }
    assert (await stats(700))["charts"] == {}
