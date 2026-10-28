import asyncio

import pytest

from activityhub import main
from activityhub.common import playlog as playlog_module
from activityhub.common.playlog import PlayLog
from activityhub.db.tables import TABLES, Play
from activityhub.main import ActivityHub
from activityhub.tests.fakes import make_hub

KEY = ("i-1", 2)


class Clock:
    """A clock the test moves by hand"""

    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def plays(clock):
    return PlayLog(clock=clock, gather=0)


def sync(plays, game, running=True, key=KEY, platform="mobile"):
    plays.sync(key, 500, key[1], game, platform, running)


def rows(plays):
    return [(row.game, row.platform, row.started_at, row.seconds) for row in plays.queue]


def test_opening_a_game_and_going_back_makes_one_play(plays, clock):
    sync(plays, None)
    sync(plays, "vegas")
    clock.now += 30
    sync(plays, None)
    assert rows(plays) == [("vegas", "mobile", 1000.0, 30.0)]
    assert plays.plays == {}


def test_menu_time_makes_no_play(plays, clock):
    sync(plays, None)
    clock.now += 60
    sync(plays, None, running=False)
    assert plays.queue == [] and plays.plays == {}


def test_switching_games_makes_two_plays(plays, clock):
    sync(plays, "vegas")
    clock.now += 10
    sync(plays, "tanks")
    clock.now += 5
    plays.end(KEY)
    assert rows(plays) == [("vegas", "mobile", 1000.0, 10.0), ("tanks", "mobile", 1010.0, 5.0)]


def test_paused_time_is_left_out(plays, clock):
    sync(plays, "vegas")
    clock.now += 10
    sync(plays, "vegas", running=False)
    clock.now += 100
    sync(plays, "vegas")
    clock.now += 5
    plays.end(KEY)
    assert rows(plays) == [("vegas", "mobile", 1000.0, 15.0)]


def test_a_play_that_starts_paused_counts_from_when_it_runs(plays, clock):
    sync(plays, "vegas", running=False)
    clock.now += 50
    sync(plays, "vegas")
    clock.now += 7
    plays.end(KEY)
    assert rows(plays) == [("vegas", "mobile", 1000.0, 7.0)]


def test_the_platform_is_kept_from_the_start(plays):
    sync(plays, "vegas", platform="desktop")
    sync(plays, "vegas", platform="mobile")
    plays.end(KEY)
    assert rows(plays)[0][1] == "desktop"


def test_end_all_ends_every_open_play(plays, clock):
    sync(plays, "vegas")
    sync(plays, "tanks", key=("i-2", 3))
    clock.now += 4
    plays.end_all()
    assert sorted(rows(plays)) == [("tanks", "mobile", 1000.0, 4.0), ("vegas", "mobile", 1000.0, 4.0)]


def test_forget_user_drops_their_open_and_queued_plays(plays):
    sync(plays, "vegas")
    plays.end(KEY)
    sync(plays, "tanks")
    sync(plays, "vegas", key=("i-1", 3))
    plays.forget_user(2)
    assert plays.queue == [] and list(plays.plays) == [("i-1", 3)]


def test_a_database_that_cannot_open_drops_plays_and_keeps_no_more(plays, caplog):
    sync(plays, "vegas")
    plays.end(KEY)
    plays.failed()
    sync(plays, "tanks")
    assert plays.queue == [] and plays.plays == {}
    assert "Dropped 1 plays" in caplog.text


@pytest.mark.asyncio
async def test_plays_wait_for_the_database_then_get_written(plays, clock, playdb):
    sync(plays, "vegas")
    clock.now += 30
    plays.end(KEY)
    await asyncio.sleep(0.01)
    assert plays.writer is None and await Play.count() == 0
    plays.opened()
    await asyncio.wait_for(plays.writer, 1)
    columns = (Play.game, Play.user_id, Play.guild_id, Play.platform, Play.started_at, Play.seconds)
    assert await Play.select(*columns) == [
        {"game": "vegas", "user_id": 2, "guild_id": 500, "platform": "mobile", "started_at": 1000.0, "seconds": 30.0}
    ]
    assert plays.queue == []


@pytest.mark.asyncio
async def test_close_writes_what_is_queued_without_the_wait(clock, playdb):
    plays = PlayLog(clock=clock, gather=60)
    plays.opened()
    sync(plays, "vegas")
    plays.end(KEY)
    await asyncio.wait_for(plays.close(), 2)
    assert await Play.count() == 1


@pytest.mark.asyncio
async def test_close_before_the_database_opens_drops_the_queue(plays, caplog):
    sync(plays, "vegas")
    plays.end(KEY)
    await asyncio.wait_for(plays.close(), 1)
    assert plays.queue == [] and "Gave up on 1 plays" in caplog.text


@pytest.mark.asyncio
async def test_close_gives_up_after_its_limit(monkeypatch, plays, caplog, playdb):
    monkeypatch.setattr(playlog_module, "CLOSE_SECONDS", 0.05)

    async def stuck(*rows):
        await asyncio.sleep(10)

    monkeypatch.setattr(Play, "insert", stuck)
    plays.opened()
    sync(plays, "vegas")
    plays.end(KEY)
    await asyncio.sleep(0.01)
    await asyncio.wait_for(plays.close(), 2)
    assert plays.queue == [] and "Gave up on 1 plays" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_and_does_not_raise(monkeypatch, plays, caplog, playdb):
    async def broken(*rows):
        raise RuntimeError("disk full")

    monkeypatch.setattr(Play, "insert", broken)
    plays.opened()
    sync(plays, "vegas")
    plays.end(KEY)
    await asyncio.wait_for(plays.writer, 1)
    assert plays.queue == [] and "Couldn't write 1 plays" in caplog.text


@pytest.mark.asyncio
async def test_the_play_log_opens_once_red_is_ready(monkeypatch):
    hub = make_hub()
    opened = []

    async def register(cog, tables, trace=False):
        opened.append(tables)

    monkeypatch.setattr(main.engine, "register_cog", register)
    await ActivityHub.open_playlog(hub)
    assert opened == [TABLES] and hub.playlog.ready.is_set()


@pytest.mark.asyncio
async def test_a_database_that_cannot_open_leaves_the_hub_working(monkeypatch, caplog):
    hub = make_hub()

    async def broken(cog, tables, trace=False):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(main.engine, "register_cog", broken)
    await ActivityHub.open_playlog(hub)
    assert hub.playlog.broken and not hub.playlog.ready.is_set()
    assert "couldn't open" in caplog.text and "disk gone" in caplog.text


@pytest.mark.asyncio
async def test_deleting_a_user_deletes_their_plays(playdb):
    hub = make_hub()
    hub.playlog.opened()
    await Play.insert(
        Play(guild_id=500, user_id=2, game="snake", platform="", started_at=1.0, seconds=1.0),
        Play(guild_id=500, user_id=3, game="snake", platform="", started_at=1.0, seconds=1.0),
    )
    # Mid-play when the request comes: the open play must not be written afterwards
    hub.playlog.sync(("i-1", 2), 500, 2, "tanks", "", True)
    await ActivityHub.red_delete_data_for_user(hub, requester="user", user_id=2)
    hub.playlog.end_all()
    assert await Play.select(Play.user_id) == [{"user_id": 3}]
    assert hub.playlog.queue == []


@pytest.mark.asyncio
async def test_deleting_gives_up_when_the_database_never_opens(monkeypatch, caplog):
    monkeypatch.setattr(main, "DELETE_WAIT", 0.05)
    hub = make_hub()
    await ActivityHub.red_delete_data_for_user(hub, requester="user", user_id=2)
    assert "couldn't be deleted" in caplog.text


@pytest.mark.asyncio
async def test_deleting_does_not_wait_on_a_database_that_failed(caplog):
    hub = make_hub()
    hub.playlog.failed()
    await asyncio.wait_for(ActivityHub.red_delete_data_for_user(hub, requester="user", user_id=2), 1)
    assert "couldn't be deleted" in caplog.text


@pytest.mark.asyncio
async def test_deleting_waits_for_a_write_already_on_its_way(monkeypatch, playdb):
    hub = make_hub()
    hub.playlog = PlayLog(gather=0)
    started, gate = asyncio.Event(), asyncio.Event()
    real_insert = Play.insert

    async def slow(*rows):
        started.set()
        await gate.wait()
        await real_insert(*rows)

    monkeypatch.setattr(Play, "insert", slow)
    hub.playlog.opened()
    hub.playlog.sync(("i-1", 2), 500, 2, "snake", "", True)
    hub.playlog.end(("i-1", 2))
    # The writer has taken the play and is now writing it
    await asyncio.wait_for(started.wait(), 2)
    deleting = asyncio.create_task(ActivityHub.red_delete_data_for_user(hub, requester="user", user_id=2))
    await asyncio.sleep(0.05)
    gate.set()
    await asyncio.wait_for(deleting, 2)
    await asyncio.wait_for(hub.playlog.writer, 2)
    assert await Play.count() == 0


@pytest.mark.asyncio
async def test_a_queue_emptied_while_gathering_writes_nothing(clock, caplog, playdb):
    plays = PlayLog(clock=clock, gather=0.2)
    plays.opened()
    sync(plays, "vegas")
    plays.end(KEY)
    await asyncio.sleep(0.02)
    # A data deletion empties the queue while the writer waits to gather more
    plays.forget_user(2)
    await asyncio.wait_for(plays.writer, 1)
    assert "Couldn't write" not in caplog.text
