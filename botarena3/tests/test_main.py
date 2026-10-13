import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from botarena3.common import battle as engine
from botarena3.common import career, parts
from botarena3.common.arenas import ARENAS
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
    return [m for m in conn.sent if key in m][-1]


async def say(cog, conn, kind, value):
    await cog.message(conn.ctx, conn, {kind: value})


async def ready(cog, conn):
    await say(cog, conn, "newCareer", True)
    for name in (LIGHT, AURO, LP):
        await say(cog, conn, "buy", name)
    await say(cog, conn, "mount", [0, 0])
    await say(cog, conn, "mount", [0, 0])


async def set_level(cog, user_id, level):
    group = cog.config.user_from_id(user_id)
    data = await group.career()
    data["level"] = level
    await group.career.set(data)


@pytest_asyncio.fixture
async def cog():
    made = BotArena3(bot=None)
    yield made
    await made.cog_unload()


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game(cog):
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(cog)
    assert game.key == "botarena3" and game.name == "Bot Arena 3"
    assert game.icon == "icon.png" and game.thumbnail == "thumb.png"
    assert set(game.socket) == {"join", "message", "leave"}


@pytest.mark.asyncio
async def test_joining_sends_the_data_and_no_career(cog):
    conn = FakeConn(FakeRoom(), 1)
    await cog.join(conn.ctx, conn)
    assert conn.sent[0]["data"]["arenas"][0]["name"] == "ROXTAN PARK ARENA"
    assert last(conn, "career")["career"] is None


@pytest.mark.asyncio
async def test_a_joining_page_never_hears_of_the_secret_laser(cog):
    conn = FakeConn(FakeRoom(), 1)
    await cog.join(conn.ctx, conn)
    data = conn.sent[0]["data"]
    names = [part["name"] for kind in ("weapons", "platings", "chassis") for part in data[kind]]
    assert parts.SECRET_LASER not in names
    assert len(data["weapons"]) == len(parts.WEAPONS) - 1
    # The bot's own rules still know it
    assert parts.SECRET_LASER in parts.WEAPONS


@pytest.mark.asyncio
async def test_shopping_saves_the_career_and_answers_with_the_prompt(cog):
    conn = FakeConn(FakeRoom(), 1)
    await say(cog, conn, "newCareer", True)
    await say(cog, conn, "buy", LIGHT)
    reply = last(conn, "career")
    assert reply["done"] == "buy" and reply["said"] == career.BOUGHT
    assert reply["career"]["cash"] == 5200 and len(reply["career"]["robots"]) == 1
    again = BotArena3(bot=None)
    assert (await again.config.user_from_id(1).career())["cash"] == 5200


@pytest.mark.asyncio
async def test_a_refused_request_resends_the_career_unchanged(cog):
    conn = FakeConn(FakeRoom(), 1)
    await say(cog, conn, "newCareer", True)
    await say(cog, conn, "sell", 4)
    reply = last(conn, "career")
    assert reply["refused"] == career.GONE and reply["career"]["cash"] == 8200
    count = len(conn.sent)
    await say(cog, conn, "sell", "4")
    await cog.message(conn.ctx, conn, {"buy": LP, "sell": 0})
    await cog.message(conn.ctx, conn, ["buy"])
    assert len(conn.sent) == count


@pytest.mark.asyncio
async def test_other_devices_of_the_same_player_get_the_new_career(cog):
    room = FakeRoom()
    phone, desk = FakeConn(room, 1), FakeConn(room, 1)
    await say(cog, phone, "newCareer", True)
    assert last(desk, "career")["career"]["cash"] == 8200 and "done" not in last(desk, "career")


@pytest.mark.asyncio
async def test_starting_an_arena_takes_the_fee_and_starts_the_battle(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    await say(cog, conn, "arena", 0)
    run = cog.running(1)
    assert run is not None and run.kind == "arena" and run.index == 0
    assert last(conn, "battle")["battle"]["id"] == run.id
    assert len(run.battle.robots) == 1 + len(ARENAS[0].opponents)
    assert run.battle.colors == [1, career.COMPUTER_COLOR]


@pytest.mark.asyncio
async def test_a_locked_arena_or_a_team_with_problems_is_refused(cog):
    conn = FakeConn(FakeRoom(), 1)
    await say(cog, conn, "newCareer", True)
    await say(cog, conn, "arena", 0)
    assert cog.running(1) is None and last(conn, "career")["refused"] == career.ARENA_CLOSED
    await ready(cog, conn)
    await say(cog, conn, "arena", 3)
    assert cog.running(1) is None


@pytest.mark.asyncio
async def test_two_starts_at_once_make_one_battle(cog):
    room = FakeRoom()
    phone, desk = FakeConn(room, 1), FakeConn(room, 1)
    await ready(cog, phone)
    await set_level(cog, 1, 2)
    cash = (await cog.config.user_from_id(1).career())["cash"]
    await asyncio.gather(say(cog, phone, "arena", 1), say(cog, desk, "arena", 1))
    window = cog.windows["window"]
    assert len(window.runs) == 1
    saved = await cog.config.user_from_id(1).career()
    assert saved["fee"] == ARENAS[1].fee and saved["cash"] == cash - ARENAS[1].fee


@pytest.mark.asyncio
async def test_a_win_pays_the_prize_and_raises_the_level(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    await say(cog, conn, "arena", 0)
    run = cog.running(1)
    run.battle.finish(1)
    await cog.save_result(run)
    saved = await cog.config.user_from_id(1).career()
    assert saved["cash"] == 8200 - 3000 - 300 - 250 + 200 and saved["level"] == 2 and saved["fee"] == 0
    assert last(conn, "career")["career"]["level"] == 2


@pytest.mark.asyncio
async def test_beating_the_game_gives_the_prizes_and_the_win_screen(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    group = cog.config.user_from_id(1)
    data = await group.career()
    data["level"], data["cash"] = 15, 30000
    await group.career.set(data)
    await say(cog, conn, "arena", len(ARENAS) - 1)
    run = cog.running(1)
    assert run.beats_game
    run.battle.finish(1)
    await cog.save_result(run)
    saved = await group.career()
    assert saved["won"] and saved["level"] == 18


@pytest.mark.asyncio
async def test_a_battle_stopped_by_a_reload_refunds_its_fee():
    first = BotArena3(bot=None)
    conn = FakeConn(FakeRoom(), 1)
    await ready(first, conn)
    await set_level(first, 1, 2)
    group = first.config.user_from_id(1)
    await say(first, conn, "arena", 1)
    paid = (await group.career())["cash"]
    await first.cog_unload()
    second = BotArena3(bot=None)
    try:
        again = FakeConn(FakeRoom("other"), 1)
        await second.join(again.ctx, again)
        assert last(again, "career")["career"]["cash"] == paid + ARENAS[1].fee
        assert (await second.config.user_from_id(1).career())["fee"] == 0
    finally:
        await second.cog_unload()


@pytest.mark.asyncio
async def test_no_refund_while_the_battle_still_runs(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    await say(cog, conn, "arena", 0)
    group = cog.config.user_from_id(1)
    data = await group.career()
    data["fee"] = 500
    await group.career.set(data)
    await cog.join(conn.ctx, conn)
    assert (await group.career())["fee"] == 500


@pytest.mark.asyncio
async def test_a_challenge_never_touches_the_career(cog):
    conn = FakeConn(FakeRoom(), 1)
    await say(cog, conn, "challenge", 0)
    run = cog.running(1)
    assert run.kind == "challenge" and await cog.config.user_from_id(1).career() is None
    assert run.battle.colors == [career.CHALLENGE_COLOR, career.COMPUTER_COLOR]
    await say(cog, conn, "challenge", 1)
    assert cog.running(1) is run and last(conn, "notice")["notice"] == cog.BUSY


@pytest.mark.asyncio
async def test_no_new_career_during_a_battle(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    await say(cog, conn, "arena", 0)
    await say(cog, conn, "newCareer", True)
    assert len((await cog.config.user_from_id(1).career())["robots"]) == 1
    assert last(conn, "notice")["notice"] == cog.BUSY


@pytest.mark.asyncio
async def test_deleting_a_players_data_removes_their_career(cog):
    conn = FakeConn(FakeRoom(), 1)
    await say(cog, conn, "newCareer", True)
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    assert await cog.config.user_from_id(1).career() is None


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_battles(cog):
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    window = cog.window_for(FakeConn(old_room, 1))
    assert cog.window_for(FakeConn(new_room, 1)) is window and window.room is new_room


@pytest.mark.asyncio
async def test_an_arena_and_a_challenge_from_two_devices_make_one_battle(cog):
    room = FakeRoom()
    phone, desk = FakeConn(room, 1), FakeConn(room, 1)
    await ready(cog, phone)
    await asyncio.gather(say(cog, phone, "arena", 0), say(cog, desk, "challenge", 0))
    assert len(cog.windows["window"].runs) == 1


@pytest.mark.asyncio
async def test_starting_an_arena_gives_back_a_fee_held_by_a_stopped_battle(cog):
    conn = FakeConn(FakeRoom(), 1)
    await ready(cog, conn)
    group = cog.config.user_from_id(1)
    data = await group.career()
    data["fee"] = 500
    await group.career.set(data)
    cash = data["cash"]
    await say(cog, conn, "arena", 0)
    saved = await group.career()
    assert saved["cash"] == cash + 500 and saved["fee"] == 0


@pytest.mark.asyncio
async def test_a_page_opened_by_a_join_watches_the_friends_battle(cog):
    room = FakeRoom()
    friend = FakeConn(room, 1)
    await cog.join(friend.ctx, friend)
    await ready(cog, friend)
    await say(cog, friend, "challenge", 0)
    run = cog.running(1)
    me = FakeConn(room, 2)
    me.follow = 1
    await cog.join(me.ctx, me)
    assert last(me, "battle")["battle"]["id"] == run.id and last(me, "battle")["battle"]["you"] is None
    assert run.watchers == [me]


# ---------- One room for the whole server ----------

SERVER = "server-500"


@pytest.mark.asyncio
async def test_the_game_plays_in_one_room_per_server_and_a_dm_call_in_its_own(cog):
    games = pytest.importorskip("activityhub.common.games")
    sessions = pytest.importorskip("activityhub.common.sessions")
    game = await games.validate_game(cog)
    author = SimpleNamespace(id=1)
    server = sessions.ActivityContext(author, guild=SimpleNamespace(id=500), instance_id="i-1")
    dm = sessions.ActivityContext(author, instance_id="i-9")
    assert (await game.context(server)).room_id == SERVER
    assert (await game.context(dm)).room_id == "i-9"


@pytest.mark.asyncio
async def test_two_channels_of_one_server_share_one_window(cog):
    room = FakeRoom(None, SERVER)
    one, two = FakeConn(room, 1, "i-1"), FakeConn(room, 2, "i-2")
    await cog.join(one.ctx, one)
    await cog.join(two.ctx, two)
    assert list(cog.windows) == [SERVER]
    await say(cog, one, "challenge", 0)
    run = cog.running(1)
    await say(cog, two, "watch", run.id)
    assert run.watchers == [two] and last(two, "battle")["battle"]["id"] == run.id


@pytest.mark.asyncio
async def test_a_stopped_window_is_let_go_by_its_rooms_id(cog):
    window = cog.window_for(FakeConn(FakeRoom(None, SERVER), 1, "i-1"))
    cog.window_closed(window)
    assert cog.windows == {}


@pytest.mark.asyncio
async def test_a_battle_carries_on_when_its_player_reopens_the_game_in_another_channel(cog):
    room = FakeRoom(None, SERVER)
    old = FakeConn(room, 1, "i-1")
    await cog.join(old.ctx, old)
    await say(cog, old, "challenge", 0)
    run = cog.running(1)
    old.drop()
    await cog.leave(old.ctx, old)
    new = FakeConn(room, 1, "i-2")
    await cog.join(new.ctx, new)
    assert last(new, "battle")["battle"]["id"] == run.id and last(new, "lobby")["mine"] == run.id
    assert list(cog.windows) == [SERVER] and list(cog.windows[SERVER].runs) == [run.id]


# ---------- Reopening the Activity ----------


async def reopen(cog, old, instance_id="reopened"):
    """The player opened the Activity again in another server or a DM call: another room, with the battle left in the
    first"""
    old.drop()
    await cog.leave(old.ctx, old)
    new = FakeConn(FakeRoom(instance_id), old.ctx.author.id)
    await cog.join(new.ctx, new)
    return new


@pytest.mark.asyncio
async def test_reopening_the_activity_gets_back_to_your_battle(cog):
    old = FakeConn(FakeRoom("first"), 1)
    await cog.join(old.ctx, old)
    await ready(cog, old)
    await say(cog, old, "arena", 0)
    run = cog.running(1)
    group = cog.config.user_from_id(1)
    paid = await group.career()
    new = await reopen(cog, old)
    full = last(new, "battle")["battle"]
    assert full["id"] == run.id and full["you"] == 1 and full["step"] == run.battle.step
    # The fee stays held while the battle runs on
    assert (await group.career()) == paid and paid["fee"] == ARENAS[0].fee
    robot = run.battle.robots[0]
    await say(cog, new, "order", [robot.id, 300, 100])
    assert robot.order[0] == "goto"
    home = cog.windows["first"]
    fan = FakeConn(home.room, 2)
    await say(cog, fan, "watch", run.id)
    await home.tick()
    assert last(new, "u")["u"]["id"] == run.id
    assert [face["id"] for face in last(new, "watchers")["watchers"]["people"]] == ["2"]
    run.battle.finish(1)
    while run.id in home.runs:
        await home.tick()
    await asyncio.gather(*cog.saving)
    assert [m["over"] for m in new.sent if "over" in m] == [{"id": run.id, "next": "shop"}]
    saved = await group.career()
    assert saved["cash"] == 8200 - 3000 - 300 - 250 + 200 and saved["level"] == 2 and saved["fee"] == 0
    # Paid once: opening the game again changes nothing
    await reopen(cog, new, "third")
    assert await group.career() == saved


@pytest.mark.asyncio
async def test_a_battle_whose_player_reopened_elsewhere_is_not_stopped_as_abandoned(cog):
    old = FakeConn(FakeRoom("first"), 1)
    await say(cog, old, "challenge", 0)
    run = cog.running(1)
    new = await reopen(cog, old)
    home = cog.windows["first"]
    run.battle.step = run.battle.last_damage + engine.DRAW_STEPS
    await home.tick()
    assert run.id in home.runs
    new.drop()
    await home.tick()
    assert run.id not in home.runs


@pytest.mark.asyncio
async def test_a_player_in_another_room_hears_when_the_battles_room_fails(cog, monkeypatch):
    old = FakeConn(FakeRoom("first"), 1)
    await say(cog, old, "challenge", 0)
    run = cog.running(1)
    new = await reopen(cog, old)
    home = cog.windows["first"]

    async def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(home, "tick", broken)
    await home.loop()
    assert last(new, "over")["over"] == {"id": run.id, "next": "challenges"}
    assert last(new, "notice")["notice"] == "Something went wrong, so the battles in this server were stopped."
    assert cog.running(1) is None and "first" not in cog.windows


@pytest.mark.asyncio
async def test_a_battle_started_on_one_device_goes_to_the_players_pages_in_other_servers(cog):
    room = FakeRoom(None, "server-500")
    phone, watcher = FakeConn(room, 1, "i-1"), FakeConn(FakeRoom(None, "server-600"), 1, "i-2")
    friend = FakeConn(watcher.room, 2, "i-2")
    await say(cog, friend, "challenge", 1)
    theirs = cog.running(2)
    await say(cog, watcher, "watch", theirs.id)
    assert theirs.watchers == [watcher]
    await say(cog, phone, "challenge", 0)
    mine = cog.running(1)
    assert last(watcher, "battle")["battle"]["id"] == mine.id and last(watcher, "battle")["battle"]["you"] == 1
    assert theirs.watchers == []


@pytest.mark.asyncio
async def test_battle_and_fight_ids_never_repeat_across_windows(cog):
    one, two = FakeConn(FakeRoom("first"), 1), FakeConn(FakeRoom("second"), 2)
    await say(cog, one, "challenge", 0)
    await say(cog, two, "challenge", 0)
    assert cog.running(1).id != cog.running(2).id


class Held:
    """A player's stored data whose career read waits for the test to let it through"""

    def __init__(self, group, gate):
        self.group, self.gate = group, gate

    async def career(self):
        await self.gate.wait()
        return await self.group.career()


@pytest.mark.asyncio
async def test_a_battle_started_while_a_fight_opens_never_leaves_both(cog, monkeypatch):
    room = FakeRoom()
    phone, desk = FakeConn(room, 1), FakeConn(room, 1)
    await ready(cog, phone)
    window = cog.windows["window"]
    gate, real = asyncio.Event(), cog.config.user_from_id
    monkeypatch.setattr(cog.config, "user_from_id", lambda user_id: Held(real(user_id), gate))
    opening = asyncio.create_task(say(cog, phone, "open", [1, None, "server"]))
    await asyncio.sleep(0)
    # The open is past its busy check, reading the career; a challenge (which reads nothing) starts meanwhile
    starting = asyncio.create_task(say(cog, desk, "challenge", 0))
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(opening, starting)
    assert cog.running(1) is not None and window.fights == {}
