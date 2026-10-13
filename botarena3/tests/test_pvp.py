import asyncio

import pytest
import pytest_asyncio

from botarena3.common import career, leaderboard
from botarena3.common.lobby import Window
from botarena3.main import BotArena3
from botarena3.tests.fakes import FakeConn, FakeRoom

LIGHT = 'AKAUMIN "DLZ-100"'
AURO = 'SANTRIN "AURO"'
LP = 'ZINTEK "LP"'


@pytest.fixture(autouse=True)
def no_loops(monkeypatch):
    # The tests decide when battles step and results save, so no window loop runs behind them
    monkeypatch.setattr(Window, "start", lambda self: None)


def last(conn, key):
    found = [m for m in conn.sent if key in m]
    return found[-1] if found else None


async def say(cog, conn, kind, value):
    await cog.message(conn.ctx, conn, {kind: value})


async def ready(cog, conn, color=1):
    await say(cog, conn, "newCareer", True)
    for name in (LIGHT, AURO, LP):
        await say(cog, conn, "buy", name)
    await say(cog, conn, "mount", [0, 0])
    await say(cog, conn, "mount", [0, 0])
    await say(cog, conn, "color", color)


@pytest_asyncio.fixture
async def cog():
    made = BotArena3(bot=None)
    yield made
    await made.cog_unload()


@pytest.mark.asyncio
async def test_opening_and_joining_starts_a_fight_left_and_right(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest, color=4)
    await say(cog, host, "open", [2, "ORIENTATION", "server"])
    window = cog.windows["window"]
    (fight,) = window.fights.values()
    await say(cog, guest, "join", fight.id)
    run = cog.running(1)
    assert run is cog.running(2) and run.kind == "pvp" and run.players == {1: 1, 2: 2}
    assert run.background == 2 and run.battle.colors == [1, 4] and run.battle.draws
    assert window.fights == {}
    assert last(host, "battle")["battle"]["you"] == 1 and last(guest, "battle")["battle"]["you"] == 2


@pytest.mark.asyncio
async def test_the_same_color_shows_the_joiner_in_the_computers_color(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host, color=3)
    await ready(cog, guest, color=3)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    assert cog.running(1).battle.colors == [3, career.COMPUTER_COLOR]


@pytest.mark.asyncio
async def test_a_team_that_cant_fight_cant_join_and_no_career_cant_open(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await say(cog, guest, "newCareer", True)
    await say(cog, host, "open", [1, "ORIENTATION", "server"])
    fight_id = next(iter(cog.windows["window"].fights))
    await say(cog, guest, "join", fight_id)
    assert cog.running(2) is None and last(guest, "notice")["notice"] == career.NOT_READY
    nobody = FakeConn(room, 3)
    await say(cog, nobody, "open", [1, None, "server"])
    assert last(nobody, "notice")["notice"] == career.NO_TEAM


@pytest.mark.asyncio
async def test_you_cant_join_your_own_fight_and_bad_values_are_ignored(cog):
    room = FakeRoom()
    host = FakeConn(room, 1)
    await ready(cog, host)
    for value in ([4, None, "server"], [1, "FEATHERWEIGHT", "server"], [True, None, "server"], "x", [1]):
        await say(cog, host, "open", value)
    for value in ([1, None], [1, None, "everywhere"], [1, None, True]):
        await say(cog, host, "open", value)
    assert cog.windows["window"].fights == {}
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, host, "join", next(iter(cog.windows["window"].fights)))
    assert cog.running(1) is None


@pytest.mark.asyncio
async def test_cancelling_or_leaving_closes_the_fight(cog):
    room = FakeRoom()
    host = FakeConn(room, 1)
    await ready(cog, host)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, host, "cancel", True)
    window = cog.windows["window"]
    assert window.fights == {}
    await say(cog, host, "open", [1, None, "server"])
    host.drop()
    await cog.leave(host.ctx, host)
    assert window.fights == {}


@pytest.mark.asyncio
async def test_results_go_on_the_leaderboard(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    run = cog.running(1)
    run.battle.finish(2)
    await cog.save_result(run)
    board = await cog.leaderboard(guest.ctx, {})
    assert [(row["id"], row["wins"], row["losses"]) for row in board["top"]] == [("2", 1, 0), ("1", 0, 1)]
    assert board["you"]["name"] == "Global 2"


@pytest.mark.asyncio
async def test_a_draw_counts_for_both(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    run = cog.running(1)
    run.battle.finish(0)
    await cog.save_result(run)
    board = await cog.leaderboard(host.ctx, {})
    assert sorted(row["id"] for row in board["top"]) == ["1", "2"]
    assert all(row["draws"] == 1 for row in board["top"])


@pytest.mark.asyncio
async def test_deleting_data_takes_a_player_off_the_leaderboard(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    run = cog.running(1)
    run.battle.finish(1)
    await cog.save_result(run)
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    board = await cog.leaderboard(host.ctx, {})
    assert [row["id"] for row in board["top"]] == ["2"] and board["you"] is None


@pytest.mark.asyncio
async def test_data_deleted_during_a_fight_is_not_written_back_by_its_result(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    run = cog.running(1)
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    run.battle.finish(2)
    await cog.save_result(run)
    assert await cog.config.user_from_id(1).all() == {"career": None, "pvp": leaderboard.DEFAULTS}
    board = await cog.leaderboard(host.ctx, {})
    assert [row["id"] for row in board["top"]] == ["2"] and board["you"] is None


@pytest.mark.asyncio
async def test_activityhub_offers_the_leaderboard(cog):
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(cog)
    assert set(game.actions) == {"leaderboard"}


@pytest.mark.asyncio
async def test_an_arena_start_with_no_career_is_refused_out_loud(cog):
    room = FakeRoom()
    conn = FakeConn(room, 1)
    await say(cog, conn, "arena", 0)
    reply = last(conn, "refused")
    assert reply == {"career": None, "refused": career.NO_TEAM}


@pytest.mark.asyncio
async def test_an_arena_start_sends_the_battle_before_the_career(cog):
    room = FakeRoom()
    conn = FakeConn(room, 1)
    await ready(cog, conn)
    conn.sent.clear()
    await say(cog, conn, "arena", 0)
    keys = [next(iter(m)) for m in conn.sent if "battle" in m or "career" in m]
    assert keys == ["battle", "career"]


def kinds(cog, user_id):
    return [run.kind for window in cog.windows.values() for run in window.runs.values() if user_id in run.players]


@pytest.mark.asyncio
async def test_a_join_and_an_arena_start_at_once_leave_the_joiner_in_one_run(cog):
    room = FakeRoom()
    host, guest, other = FakeConn(room, 1), FakeConn(room, 2), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    fight_id = next(iter(cog.windows["window"].fights))
    await asyncio.gather(say(cog, other, "arena", 0), say(cog, guest, "join", fight_id))
    assert len(kinds(cog, 2)) == 1


@pytest.mark.asyncio
async def test_a_join_and_the_openers_arena_start_at_once_leave_the_opener_in_one_run(cog):
    room = FakeRoom()
    host, second, guest = FakeConn(room, 1), FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    fight_id = next(iter(cog.windows["window"].fights))
    await asyncio.gather(say(cog, second, "arena", 0), say(cog, guest, "join", fight_id))
    assert len(kinds(cog, 1)) == 1
    assert cog.windows["window"].fights == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,value", [("arena", 0), ("challenge", 0)])
async def test_starting_a_battle_closes_your_own_open_fight(cog, kind, value):
    room = FakeRoom()
    host = FakeConn(room, 1)
    await ready(cog, host)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, host, kind, value)
    assert cog.windows["window"].fights == {}


@pytest.mark.asyncio
async def test_joining_a_fight_closes_your_own_open_fight(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, guest, "open", [3, None, "server"])
    await say(cog, host, "open", [1, None, "server"])
    window = cog.windows["window"]
    mine = next(f.id for f in window.fights.values() if f.user_id == 1)
    await say(cog, guest, "join", mine)
    assert window.fights == {}


@pytest.mark.asyncio
async def test_a_busy_opener_makes_the_fight_gone_for_the_joiner(cog):
    room = FakeRoom()
    host, guest, third = FakeConn(room, 1), FakeConn(room, 2), FakeConn(room, 3)
    await ready(cog, host)
    await ready(cog, guest)
    await ready(cog, third)
    await say(cog, host, "open", [1, None, "server"])
    fight_id = next(iter(cog.windows["window"].fights))
    await say(cog, host, "challenge", 0)
    await say(cog, guest, "join", fight_id)
    assert cog.windows["window"].fights == {}
    assert cog.running(2) is None
    assert last(guest, "notice")["notice"] == cog.FIGHT_GONE
    await say(cog, host, "open", [1, None, "server"])
    assert last(host, "notice")["notice"] == cog.BUSY


@pytest.mark.asyncio
async def test_only_a_fight_id_that_was_open_is_answered(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    fight_id = next(iter(cog.windows["window"].fights))
    # Not a fight id at all, or the player's own fight: nothing to say
    for value in (None, 5, [fight_id], True):
        await say(cog, guest, "join", value)
    await say(cog, host, "join", fight_id)
    assert last(guest, "notice") is None and last(host, "notice") is None
    # A fight id from a list the page drew before the fight closed
    await say(cog, host, "cancel", True)
    await say(cog, guest, "join", fight_id)
    assert last(guest, "notice")["notice"] == cog.FIGHT_GONE
    assert cog.running(2) is None


@pytest.mark.asyncio
async def test_malformed_weights_are_ignored(cog):
    room = FakeRoom()
    host = FakeConn(room, 1)
    await ready(cog, host)
    for value in ([1, ["ORIENTATION"]], [1, {"a": 1}]):
        await say(cog, host, "open", value)
    assert cog.windows["window"].fights == {}


@pytest.mark.asyncio
async def test_a_second_device_keeps_the_fight_open(cog):
    room = FakeRoom()
    first, second = FakeConn(room, 1), FakeConn(room, 1)
    await ready(cog, first)
    await say(cog, first, "open", [1, None, "server"])
    first.drop()
    await cog.leave(first.ctx, first)
    assert len(cog.windows["window"].fights) == 1
    second.drop()
    await cog.leave(second.ctx, second)
    assert cog.windows["window"].fights == {}


@pytest.mark.asyncio
async def test_an_opener_whose_team_no_longer_qualifies_loses_the_fight(cog):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    third = FakeConn(room, 3)
    await ready(cog, third)
    await say(cog, third, "open", [2, None, "server"])
    await say(cog, host, "open", [1, None, "server"])
    window = cog.windows["window"]
    fight_id = next(f.id for f in window.fights.values() if f.user_id == 1)
    await say(cog, host, "newCareer", True)
    await say(cog, guest, "join", fight_id)
    assert [f.user_id for f in window.fights.values()] == [3] and cog.running(2) is None
    assert last(guest, "notice")["notice"] == cog.FIGHT_GONE


@pytest.mark.asyncio
async def test_one_failed_record_save_does_not_stop_the_other(cog, monkeypatch):
    room = FakeRoom()
    host, guest = FakeConn(room, 1), FakeConn(room, 2)
    await ready(cog, host)
    await ready(cog, guest)
    await say(cog, host, "open", [1, None, "server"])
    await say(cog, guest, "join", next(iter(cog.windows["window"].fights)))
    run = cog.running(1)
    run.battle.finish(1)
    real = leaderboard.add

    def flaky(entry, outcome, name):
        if name == "Global 1":
            raise RuntimeError("boom")
        return real(entry, outcome, name)

    monkeypatch.setattr(leaderboard, "add", flaky)
    await cog.record(run)
    monkeypatch.undo()
    board = await cog.leaderboard(guest.ctx, {})
    assert [row["id"] for row in board["top"]] == ["2"]


# ---------- Whole server or my channel ----------

SERVER = "server-500"


def fights_seen(conn):
    return [fight["user"] for fight in last(conn, "lobby")["lobby"]["fights"]]


@pytest.mark.asyncio
async def test_a_fight_for_the_whole_server_can_be_joined_from_another_channel(cog):
    room = FakeRoom(None, SERVER)
    host, guest = FakeConn(room, 1, "i-1"), FakeConn(room, 2, "i-2")
    await ready(cog, host)
    await ready(cog, guest, color=4)
    await say(cog, host, "open", [1, None, "server"])
    window = cog.windows[SERVER]
    await window.tick()
    assert fights_seen(host) == ["1"] and fights_seen(guest) == ["1"]
    await say(cog, guest, "join", next(iter(window.fights)))
    assert cog.running(2) is cog.running(1) is not None


@pytest.mark.asyncio
async def test_a_fight_for_my_channel_is_listed_only_in_its_channel(cog):
    room = FakeRoom(None, SERVER)
    host, mate, other = FakeConn(room, 1, "i-1"), FakeConn(room, 2, "i-1"), FakeConn(room, 3, "i-2")
    await ready(cog, host)
    await say(cog, host, "open", [1, None, "channel"])
    await cog.windows[SERVER].tick()
    assert fights_seen(host) == ["1"] and fights_seen(mate) == ["1"] and fights_seen(other) == []
    await cog.join(other.ctx, other)
    assert fights_seen(other) == []


@pytest.mark.asyncio
async def test_a_fight_for_one_channel_cant_be_joined_from_another(cog):
    room = FakeRoom(None, SERVER)
    host, other = FakeConn(room, 1, "i-1"), FakeConn(room, 3, "i-2")
    await ready(cog, host)
    await ready(cog, other)
    await say(cog, host, "open", [1, None, "channel"])
    window = cog.windows[SERVER]
    await say(cog, other, "join", next(iter(window.fights)))
    assert last(other, "notice")["notice"] == "That game is only open to its own voice channel."
    assert cog.running(3) is None and len(window.fights) == 1


@pytest.mark.asyncio
async def test_a_join_lands_on_the_pvp_screen_with_the_friends_channel_fight(cog):
    room = FakeRoom(None, SERVER)
    friend = FakeConn(room, 1, "i-1")
    await cog.join(friend.ctx, friend)
    await ready(cog, friend)
    await say(cog, friend, "open", [1, None, "channel"])
    me = FakeConn(room, 2, "i-1")
    me.follow = 1
    await cog.join(me.ctx, me)
    assert last(me, "follow")["follow"] == "pvp" and fights_seen(me) == ["1"]


@pytest.mark.asyncio
async def test_a_fight_stays_open_while_its_opener_has_a_page_that_lists_it(cog):
    room = FakeRoom(None, SERVER)
    phone, desk = FakeConn(room, 1, "i-1"), FakeConn(room, 1, "i-2")
    await ready(cog, phone)
    window = cog.windows[SERVER]
    await say(cog, phone, "open", [1, None, "server"])
    phone.drop()
    await cog.leave(phone.ctx, phone)
    assert len(window.fights) == 1
    # A page in another channel can't see a channel's fight, so the fight goes with its channel's last page
    await say(cog, desk, "open", [1, None, "channel"])
    back = FakeConn(room, 1, "i-1")
    await say(cog, back, "open", [1, None, "channel"])
    back.drop()
    await cog.leave(back.ctx, back)
    assert window.fights == {}
