import random

import pytest

from ageofwar.common.data import DIFFICULTIES, UNITS
from ageofwar.common.match import (
    PLAYING,
    RESULTS,
    SEAT_TAKEN,
    SETUP,
    SETUP_GRACE_SECONDS,
    STEPS,
    TAKEOVER_SECONDS,
    TOOK_BACK,
    YOU_LEFT,
    Match,
)
from ageofwar.tests.fakes import Clock, FakeConn, FakeRoom


class Table:
    """A match with a fake room and clock, and the results it sent to the leaderboard"""

    def __init__(self):
        self.room = FakeRoom()
        self.clock = Clock()
        self.recorded = []
        self.match = Match(self.room, self.recorded.extend, lambda match: None, random.Random(9), self.clock)

    def conn(self, user_id: int) -> FakeConn:
        return FakeConn(self.room, user_id)

    async def send(self, conn: FakeConn, data) -> None:
        await self.match.message(conn, data)

    async def tick(self, seconds: float = 0.05) -> None:
        self.clock.now += seconds
        await self.match.tick()


async def seated(*user_ids: int) -> tuple[Table, list[FakeConn]]:
    table = Table()
    conns = []
    for seat, user_id in enumerate(user_ids):
        conn = table.conn(user_id)
        await table.match.join(conn)
        await table.send(conn, {"sit": seat})
        conns.append(conn)
    return table, conns


def last_state(conn: FakeConn) -> dict:
    return next(message["state"] for message in reversed(conn.sent) if "state" in message)


@pytest.mark.asyncio
async def test_the_first_person_seated_hosts_and_starts_against_the_computer():
    table, (host,) = await seated(1)
    match = table.match
    assert match.host == 0
    await table.send(host, {"difficulty": "impossible"})
    await table.send(host, {"start": True})
    assert match.stage == PLAYING and match.players == ["human", "cpu"]
    assert match.battle.sides[2].cpu is not None and match.battle.sides[2].strength == DIFFICULTIES["impossible"]
    assert match.battle.sides[1].cpu is None and match.battle.sides[1].strength == 1.0


@pytest.mark.asyncio
async def test_only_the_host_changes_the_difficulty_and_starts():
    table, (host, guest) = await seated(1, 2)
    await table.send(guest, {"difficulty": "harder"})
    await table.send(guest, {"start": True})
    assert table.match.difficulty == "normal" and table.match.stage == SETUP
    await table.send(host, {"start": True})
    assert table.match.players == ["human", "human"]


@pytest.mark.asyncio
async def test_a_taken_seat_is_refused():
    table, (first,) = await seated(1)
    other = table.conn(2)
    await table.send(other, {"sit": 0})
    assert other.sent[-1] == {"notice": SEAT_TAKEN}
    assert table.match.seats[0].user_id == 1


@pytest.mark.asyncio
async def test_the_host_passes_on_when_they_stand_up():
    table, (host, guest) = await seated(1, 2)
    await table.send(host, {"stand": True})
    assert table.match.host == 1 and not table.match.seats[0].human


@pytest.mark.asyncio
async def test_players_command_their_own_base_and_watchers_nothing():
    table, (host, guest) = await seated(1, 2)
    watcher = table.conn(3)
    await table.match.join(watcher)
    await table.send(host, {"start": True})
    battle = table.match.battle
    await table.send(guest, {"buy": 1})
    await table.send(watcher, {"buy": 1})
    assert battle.sides[2].tray[0] == 1 and battle.sides[1].tray[0] == 0
    assert last_state(watcher)["watching"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"buy": "1"}, {"buy": 1.0}, {"buy": True}, {"build": [1]}, {"buy": 1, "sell": 1}, []])
async def test_odd_messages_are_ignored(bad):
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.send(host, bad)
    side = table.match.battle.sides[1]
    assert side.tray == [0] * 5 and side.cash == 175


@pytest.mark.asyncio
async def test_each_update_runs_two_of_the_originals_frames():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.tick()
    await table.tick()
    frames = [message["f"]["f"] for message in host.sent if "f" in message]
    assert frames == [STEPS, STEPS * 2]


@pytest.mark.asyncio
async def test_only_a_game_against_the_computer_can_pause():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.send(host, {"pause": True})
    frame = table.match.battle.frame
    await table.tick()
    assert table.match.paused and table.match.battle.frame == frame
    await table.send(host, {"buy": 1})
    assert table.match.battle.sides[1].tray[0] == 0
    duo, (left, right) = await seated(1, 2)
    await duo.send(left, {"start": True})
    await duo.send(right, {"pause": True})
    assert not duo.match.paused


@pytest.mark.asyncio
async def test_a_solo_game_waits_for_its_player_then_stops():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    host.drop()
    table.match.leave(host)
    frame = table.match.battle.frame
    await table.tick(1)
    assert table.match.battle.frame == frame
    await table.tick(TAKEOVER_SECONDS)
    assert table.match.stage == SETUP and not table.match.seats[0].human


@pytest.mark.asyncio
async def test_a_solo_player_who_comes_back_carries_on():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    host.drop()
    table.match.leave(host)
    await table.tick(30)
    again = table.conn(1)
    await table.match.join(again)
    await table.tick()
    assert table.match.stage == PLAYING and table.match.battle.frame == STEPS


@pytest.mark.asyncio
async def test_the_stop_notice_reaches_whoever_is_left():
    table, (host,) = await seated(1)
    watcher = table.conn(2)
    await table.match.join(watcher)
    await table.send(host, {"start": True})
    host.drop()
    table.match.leave(host)
    await table.tick(TAKEOVER_SECONDS + 1)
    assert {"notice": YOU_LEFT} in watcher.sent


@pytest.mark.asyncio
async def test_the_computer_takes_over_an_away_player_and_hands_back_on_return():
    table, (left, right) = await seated(1, 2)
    await table.send(left, {"start": True})
    right.drop()
    table.match.leave(right)
    await table.tick(TAKEOVER_SECONDS + 1)
    side = table.match.battle.sides[2]
    assert table.match.seats[1].stand_in and side.cpu is not None
    back = table.conn(2)
    await table.match.join(back)
    assert not table.match.seats[1].stand_in and side.cpu is None
    assert {"notice": TOOK_BACK} in back.sent


@pytest.mark.asyncio
async def test_an_away_seat_is_freed_after_the_setup_grace():
    table, (host, guest) = await seated(1, 2)
    guest.drop()
    table.match.leave(guest)
    await table.tick(SETUP_GRACE_SECONDS - 1)
    assert table.match.seats[1].human
    await table.tick(2)
    assert not table.match.seats[1].human


@pytest.mark.asyncio
async def test_giving_up_hands_the_win_to_the_other_base():
    table, (left, right) = await seated(1, 2)
    await table.send(left, {"start": True})
    await table.send(right, {"quit": True})
    results = table.match.results
    assert table.match.stage == RESULTS and results["winner"] == 1 and results["difficulty"] is None
    assert table.recorded == []


@pytest.mark.asyncio
async def test_a_win_against_the_computer_is_recorded_with_its_game_time():
    table, (host,) = await seated(1)
    await table.send(host, {"difficulty": "harder"})
    await table.send(host, {"start": True})
    for _ in range(5):
        await table.tick()
    table.match.battle.sides[2].base.health = -5
    await table.tick()
    (result,) = table.recorded
    assert (result.user_id, result.difficulty, result.frames) == (1, "harder", STEPS * 6 - 1)
    assert table.match.results["winner"] == 1


@pytest.mark.asyncio
async def test_a_loss_is_not_recorded():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.send(host, {"quit": True})
    assert table.match.results["winner"] == 2 and table.recorded == []


@pytest.mark.asyncio
async def test_play_again_returns_to_setup_with_the_seats_kept():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.send(host, {"quit": True})
    await table.send(host, {"continue": True})
    assert table.match.stage == SETUP and table.match.seats[0].user_id == 1


@pytest.mark.asyncio
async def test_orders_reach_the_battle():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    side = table.match.battle.sides[1]
    side.cash = side.xp = 10**6
    for message in ({"buy": 3}, {"spot": True}, {"build": [1, 2]}, {"evolve": True}, {"special": True}):
        await table.send(host, message)
    assert side.tray[0] == 3 and side.addons == 1 and side.turrets[1].kind == 1 and side.age == 2
    await table.send(host, {"sell": 2})
    assert side.turrets[1] is None
    assert side.cash < 10**6 - UNITS[3].cost


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [[], {}, 1, None, "easy"])
async def test_odd_difficulties_are_ignored(bad):
    table, (host,) = await seated(1)
    await table.send(host, {"difficulty": bad})
    assert table.match.difficulty == "normal"


@pytest.mark.asyncio
async def test_someone_joining_a_paused_battle_sees_the_field_as_it_stands():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    for _ in range(3):
        await table.tick()
    await table.send(host, {"pause": True})
    await table.tick()
    watcher = table.conn(2)
    await table.match.join(watcher)
    frames = [message["f"] for message in watcher.sent if "f" in message]
    assert len(frames) == 1 and frames[0]["f"] == STEPS * 3 and frames[0]["e"] == []


@pytest.mark.asyncio
async def test_the_last_frame_goes_out_before_the_results():
    table, (host,) = await seated(1)
    await table.send(host, {"start": True})
    await table.tick()
    table.match.battle.sides[2].base.health = -5
    await table.tick()
    kinds = [
        "f" if "f" in message else message["state"]["stage"]
        for message in host.sent
        if "f" in message or "state" in message
    ]
    assert kinds[-2:] == ["f", RESULTS]
