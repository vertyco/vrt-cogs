import logging
import random
from types import SimpleNamespace

import pytest

from tanks.common.items import AIR_STRIKE, REPAIR, TELEPORT, WEAK_SHIELD
from tanks.common.match import (
    DT,
    EVERYONE_LEFT,
    LOOP_FAILED,
    PLAYING,
    RESULTS,
    SEAT_TAKEN,
    SETUP,
    SETUP_GRACE_SECONDS,
    SHOP,
    TAKEOVER_SECONDS,
    TICK_RATE,
    Match,
)
from tanks.common.tank import MIN_X
from tanks.tests.fakes import Clock, FakeConn, FakeRoom


def make_game():
    room, recorded, ended, clock = FakeRoom(), [], [], Clock()
    match = Match(room, recorded.append, ended.append, rng=random.Random(7), clock=clock)
    return SimpleNamespace(match=match, room=room, clock=clock, recorded=recorded, ended=ended)


async def run_ticks(game, count):
    for _ in range(count):
        game.clock.now += DT
        await game.match.tick()


async def run_for(game, seconds):
    await run_ticks(game, round(seconds * TICK_RATE))


async def run_until(game, check, seconds=120):
    for _ in range(round(seconds * TICK_RATE)):
        if check():
            return
        await run_ticks(game, 1)
    assert check()


async def arrive(game, user_id):
    conn = FakeConn(game.room, user_id)
    await game.match.join(conn)
    return conn


def leave(game, conn):
    conn.drop()
    game.match.leave(conn)


def last_state(conn):
    return next(message["state"] for message in reversed(conn.sent) if "state" in message)


def shots(conn):
    return [message["shot"] for message in conn.sent if "shot" in message]


async def seated(game, user_ids=(1,), cpus=((1, "hard"),)):
    """Seat these players from seat 0 up, and the computers where asked"""
    conns = []
    for seat, user_id in enumerate(user_ids):
        conn = await arrive(game, user_id)
        await game.match.message(conn, {"sit": seat})
        conns.append(conn)
    for seat, level in cpus:
        await game.match.message(conns[0], {"cpu": [seat, level]})
    return conns


async def playing(game, user_ids=(1,), cpus=((1, "hard"),)):
    """Seat everyone, start, and skip the first shop"""
    conns = await seated(game, user_ids, cpus)
    await game.match.message(conns[0], {"start": True})
    for conn in conns:
        await game.match.message(conn, {"done": True})
    await run_ticks(game, 1)
    assert game.match.stage == PLAYING
    return conns


async def shot_done(game):
    await run_ticks(game, 1)
    await run_until(game, lambda: not game.match.firing)


def last_one_standing(game, number):
    for seat, tank in game.match.tanks.items():
        if seat != number:
            tank.alive, tank.energy = False, 0


# ---------- Setup ----------


@pytest.mark.asyncio
async def test_everyone_arrives_watching_five_empty_seats():
    game = make_game()
    conn = await arrive(game, 1)
    state = last_state(conn)
    assert state["stage"] == SETUP and state["host"] is None
    assert [seat["kind"] for seat in state["seats"]] == ["empty"] * 5
    assert state["watching"] == 1 and state["rounds"] == 5 and state["landscape"] == "random"


@pytest.mark.asyncio
async def test_the_first_person_seated_hosts():
    game = make_game()
    first, second = await seated(game, (1, 2), cpus=())
    await run_ticks(game, 1)
    state = last_state(second)
    assert state["host"] == 0
    assert state["seats"][0]["name"] == "Player 1" and state["seats"][0]["id"] == "1"
    assert state["watching"] == 0


@pytest.mark.asyncio
async def test_two_taps_on_one_seat_seat_the_first_and_tell_the_second():
    game = make_game()
    first, second = await arrive(game, 1), await arrive(game, 2)
    await game.match.message(first, {"sit": 3})
    await game.match.message(second, {"sit": 3})
    assert second.sent[-1] == {"notice": SEAT_TAKEN}
    assert game.match.seats[3].user_id == 1


@pytest.mark.asyncio
async def test_only_the_host_sets_up_the_match():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    for data in ({"cpu": [2, "normal"]}, {"rounds": 3}, {"landscape": 2}):
        await game.match.message(guest, data)
    assert not game.match.seats[2].filled and game.match.rounds == 5 and game.match.landscape == "random"
    for data in ({"cpu": [2, "normal"]}, {"rounds": 3}, {"landscape": 2}):
        await game.match.message(host, data)
    assert game.match.seats[2].level == "normal" and game.match.seats[2].name == "CPU 3"
    assert game.match.rounds == 3 and game.match.landscape == 2
    await game.match.message(host, {"cpu": [2, None]})
    assert not game.match.seats[2].filled


@pytest.mark.asyncio
async def test_the_host_cannot_put_a_computer_in_a_persons_seat():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    await game.match.message(host, {"cpu": [1, "hard"]})
    assert game.match.seats[1].user_id == 2 and game.match.seats[1].level is None


@pytest.mark.asyncio
async def test_start_needs_two_tanks_and_opens_the_shop():
    game = make_game()
    (host,) = await seated(game, (1,), cpus=())
    await game.match.message(host, {"start": True})
    assert game.match.stage == SETUP
    await game.match.message(host, {"cpu": [4, "easy"]})
    await game.match.message(host, {"start": True})
    await run_ticks(game, 1)
    state = last_state(host)
    assert state["stage"] == SHOP
    assert state["kits"][0]["money"] == 5000 and state["kits"][4]["guns"][0] == 99


@pytest.mark.asyncio
async def test_standing_up_hands_the_host_to_the_next_person():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    await game.match.message(host, {"stand": True})
    assert game.match.host == 1 and not game.match.seats[0].filled


@pytest.mark.asyncio
async def test_a_player_who_drops_before_the_match_keeps_their_seat_for_20_seconds():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    leave(game, host)
    assert game.match.host == 1
    await run_for(game, SETUP_GRACE_SECONDS - 1)
    assert game.match.seats[0].user_id == 1
    await run_for(game, 1)
    assert not game.match.seats[0].filled


# ---------- The shop ----------


@pytest.mark.asyncio
async def test_buying_takes_the_price_and_says_when_it_cant():
    game = make_game()
    (host,) = await seated(game)
    await game.match.message(host, {"start": True})
    await game.match.message(host, {"buy": ["item", 0]})
    kit = game.match.seats[0].kit
    assert kit.extras[0] == 5 and kit.money == 0
    await game.match.message(host, {"buy": ["weapon", 1]})
    assert host.sent[-1] == {"notice": "Not enough money."} and kit.guns[1] == 0


@pytest.mark.asyncio
async def test_computers_never_shop():
    game = make_game()
    (host,) = await seated(game)
    await game.match.message(host, {"start": True})
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.seats[1].kit.money == 5000 and game.match.seats[1].kit.guns[0] == 99


@pytest.mark.asyncio
async def test_the_shop_closes_when_everyone_is_done_or_after_60_seconds():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    await game.match.message(host, {"start": True})
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.stage == SHOP and last_state(host)["clock"] == 60
    await run_ticks(game, 60 * TICK_RATE - 2)
    assert game.match.stage == SHOP
    await run_ticks(game, 1)
    assert game.match.stage == PLAYING and game.match.round == 1


@pytest.mark.asyncio
async def test_the_shop_waits_for_a_player_whose_connection_drops():
    game = make_game()
    (host,) = await seated(game)
    await game.match.message(host, {"start": True})
    await run_ticks(game, 1)
    leave(game, host)
    await run_ticks(game, 1)
    assert game.match.stage == SHOP
    host = await arrive(game, 1)
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.stage == PLAYING


# ---------- Turns ----------


@pytest.mark.asyncio
async def test_a_round_starts_with_every_tank_on_the_ground_and_the_lowest_seat_first():
    game = make_game()
    (host,) = await playing(game)
    await run_ticks(game, 1)
    state = last_state(host)
    assert state["turn"] == 0
    assert len(state["field"]["ground"]) == 550
    for number in (0, 1):
        tank = state["tanks"][number]
        assert tank["alive"] and tank["health"] == 100 and tank["fuel"] == 500


@pytest.mark.asyncio
async def test_the_next_round_opens_with_the_lowest_total_score():
    game = make_game()
    (host,) = await playing(game)
    game.match.seats[0].kit.score = 900
    last_one_standing(game, 0)
    await game.match.message(host, {"fire": True})
    await shot_done(game)
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.round == 2 and game.match.turn == 1


@pytest.mark.asyncio
async def test_only_the_turns_player_aims_drives_and_fires():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    await game.match.message(second, {"aim": [10, 90]})
    await game.match.message(second, {"fire": True})
    await run_ticks(game, 1)
    assert not shots(first)
    await game.match.message(first, {"aim": [120, 64.4]})
    tank = game.match.tanks[0]
    assert (tank.angle, tank.power) == (120, 64)
    x = tank.x
    await game.match.message(first, {"drive": 1})
    await run_for(game, 1)
    assert tank.x == pytest.approx(x + 25 * 0.5) and tank.fuel == 475
    await game.match.message(first, {"drive": 0})
    await game.match.message(first, {"fire": True})
    await run_ticks(game, 1)
    assert len(shots(first)) == 1 and len(shots(second)) == 1


@pytest.mark.asyncio
async def test_the_turns_tank_is_sent_in_a_small_live_update():
    game = make_game()
    (host,) = await playing(game)
    await run_ticks(game, 1)
    await game.match.message(host, {"aim": [100, 40]})
    await run_ticks(game, 1)
    tank = game.match.tanks[0]
    # One person against a computer: no clock, so its place is empty
    assert host.sent[-1] == {"t": [0, round(tank.x, 1), round(tank.y, 1), 100, 40, 500, 0, None]}


@pytest.mark.asyncio
async def test_a_turn_with_no_shot_passes_after_60_seconds():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    await run_ticks(game, 1)
    assert first.sent[-1]["t"][7] == 60
    await run_ticks(game, 60 * TICK_RATE - 2)
    assert game.match.turn == 0
    await run_ticks(game, 1)
    assert game.match.turn == 1 and not shots(first)


@pytest.mark.asyncio
async def test_with_one_person_the_shop_and_turns_have_no_time_limit():
    game = make_game()
    (host,) = await seated(game)
    await game.match.message(host, {"start": True})
    await run_for(game, 300)
    assert game.match.stage == SHOP and last_state(host)["clock"] is None
    await game.match.message(host, {"done": True})
    await run_for(game, 300)
    assert game.match.turn == 0 and not shots(host)


@pytest.mark.asyncio
async def test_the_host_sets_the_time_limit_for_the_shop_and_turns():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    for data in ({"timer": 30}, {"timer": "off"}):
        await game.match.message(guest, data)
    for data in ({"timer": 45}, {"timer": True}, {"timer": 30.0}, {"timer": None}):
        await game.match.message(host, data)
    assert game.match.timer == 60
    await game.match.message(host, {"timer": 30})
    await run_ticks(game, 1)
    assert last_state(host)["timer"] == 30
    await game.match.message(host, {"start": True})
    await run_ticks(game, 30 * TICK_RATE - 1)
    assert game.match.stage == SHOP
    await run_ticks(game, 1)
    assert game.match.stage == PLAYING
    await run_ticks(game, 30 * TICK_RATE - 1)
    assert game.match.turn == 0
    await run_ticks(game, 1)
    assert game.match.turn == 1


@pytest.mark.asyncio
async def test_the_host_can_turn_the_clock_off():
    game = make_game()
    host, guest = await seated(game, (1, 2), cpus=())
    await game.match.message(host, {"timer": "off"})
    await run_ticks(game, 1)
    assert last_state(host)["timer"] == "off"
    await game.match.message(host, {"start": True})
    await run_for(game, 300)
    assert game.match.stage == SHOP
    for conn in (host, guest):
        await game.match.message(conn, {"done": True})
    await run_for(game, 300)
    assert game.match.turn == 0 and not shots(host)


@pytest.mark.asyncio
async def test_after_a_shot_the_turn_moves_to_the_next_living_tank():
    game = make_game()
    first, second, third = await playing(game, (1, 2, 3), cpus=())
    game.match.tanks[1].alive = False
    await game.match.message(first, {"fire": True})
    await shot_done(game)
    assert game.match.turn == 2
    assert last_state(first)["turn"] == 2


@pytest.mark.asyncio
async def test_a_computer_swings_its_barrel_then_fires_within_two_seconds():
    game = make_game()
    host = await arrive(game, 1)
    await game.match.message(host, {"sit": 2})
    await game.match.message(host, {"cpu": [0, "easy"]})
    await game.match.message(host, {"cpu": [1, "very_hard"]})
    await game.match.message(host, {"start": True})
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.turn == 0 and game.match.turn_by == "cpu"
    target = game.match.think_to
    await run_for(game, 2)
    assert len(shots(host)) == 1
    assert (game.match.tanks[0].angle, game.match.tanks[0].power) == target


@pytest.mark.asyncio
async def test_repairs_add_ten_health_up_to_the_most_the_tank_can_have():
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    tank.kit.extras[REPAIR] = 3
    tank.energy = 85
    await game.match.message(host, {"use": "repair"})
    await game.match.message(host, {"use": "repair"})
    await game.match.message(host, {"use": "repair"})
    assert tank.energy == 100 and tank.kit.extras[REPAIR] == 1


@pytest.mark.asyncio
async def test_one_shield_at_a_time():
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    tank.kit.extras[WEAK_SHIELD] = 2
    await game.match.message(host, {"use": ["shield", 1]})
    await game.match.message(host, {"use": ["shield", 1]})
    assert tank.shield == WEAK_SHIELD and tank.shield_left == 100 and tank.kit.extras[WEAK_SHIELD] == 1


@pytest.mark.asyncio
async def test_a_teleport_ends_the_turn():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    tank = game.match.tanks[0]
    tank.kit.extras[TELEPORT] = 1
    # Just above the ground: a teleport high in the air falls the rest of the way, and the fall hurts
    spot = game.match.field.top(300) - 10
    await game.match.message(first, {"use": ["teleport", 300, spot]})
    await run_ticks(game, 1)
    script = shots(first)[0]
    assert script["events"][0][1] == "beam"
    assert tank.kit.extras[TELEPORT] == 0
    await shot_done(game)
    assert abs(tank.x - 300) < 3 and tank.alive and game.match.turn == 1


@pytest.mark.asyncio
async def test_the_air_strike_needs_a_spot_and_a_side():
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    tank.kit.guns[AIR_STRIKE] = 1
    await game.match.message(host, {"weapon": AIR_STRIKE})
    await game.match.message(host, {"fire": True})
    assert game.match.queued is None
    await game.match.message(host, {"fire": [275, -1]})
    await run_ticks(game, 1)
    script = shots(host)[0]
    assert script["weapon"] == AIR_STRIKE and len(script["shells"]) == 5
    assert tank.kit.guns[AIR_STRIKE] == 0 and tank.kit.weapon == 0


@pytest.mark.asyncio
async def test_a_weapon_you_dont_have_cannot_be_picked():
    game = make_game()
    (host,) = await playing(game)
    await game.match.message(host, {"weapon": 3})
    assert game.match.tanks[0].kit.weapon == 0


# ---------- Players dropping out ----------


@pytest.mark.asyncio
async def test_an_away_players_turns_are_skipped_then_a_computer_takes_over():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    leave(game, second)
    await game.match.message(first, {"fire": True})
    await shot_done(game)
    # The away player's turn is skipped
    assert game.match.turn == 0
    await run_until(game, lambda: game.match.seats[1].stand_in is not None, TAKEOVER_SECONDS + 5)
    assert last_state(first)["seats"][1]["standIn"]
    await game.match.message(first, {"fire": True})
    await shot_done(game)
    assert game.match.turn == 1 and game.match.turn_by == "cpu"


@pytest.mark.asyncio
async def test_coming_back_takes_the_tank_back_but_not_the_win():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    leave(game, second)
    await run_until(game, lambda: game.match.seats[1].stand_in is not None, TAKEOVER_SECONDS + 35)
    second = await arrive(game, 2)
    await run_until(game, lambda: game.match.turn == 1 and not game.match.firing, 60)
    assert game.match.turn_by == "human" and game.match.seats[1].taken
    game.match.seats[1].kit.score = 10**6
    last_one_standing(game, 1)
    game.match.rounds = game.match.round
    await game.match.message(second, {"fire": True})
    await shot_done(game)
    assert game.match.stage == RESULTS
    assert [r.won for r in game.recorded[0]] == [False, False]
    assert [row["won"] for row in game.match.results] == [False, True]


@pytest.mark.asyncio
async def test_a_second_device_takes_over_and_the_first_leaving_keeps_the_seat():
    game = make_game()
    (phone,) = await playing(game)
    laptop = await arrive(game, 1)
    leave(game, phone)
    assert game.match.seats[0].conn is laptop and game.match.seats[0].dropped_at is None
    await game.match.message(laptop, {"aim": [60, 20]})
    assert game.match.tanks[0].angle == 60


@pytest.mark.asyncio
async def test_a_new_connection_mid_turn_stops_the_tank_driving():
    # A phone that switches networks joins again before its old connection is noticed gone, so no "stop" arrives
    game = make_game()
    (phone,) = await playing(game)
    await game.match.message(phone, {"drive": 1})
    await run_ticks(game, 5)
    await arrive(game, 1)
    x = game.match.tanks[0].x
    await run_ticks(game, 20)
    assert game.match.drive == 0 and game.match.tanks[0].x == x


@pytest.mark.asyncio
async def test_when_every_player_has_been_away_a_minute_the_match_stops_unrecorded():
    game = make_game()
    (host,) = await playing(game)
    watcher = await arrive(game, 9)
    leave(game, host)
    await run_for(game, TAKEOVER_SECONDS + 1)
    assert game.match.stage == SETUP and not game.recorded
    assert {"notice": EVERYONE_LEFT} in watcher.sent
    assert not game.match.seats[0].filled and game.match.seats[1].level == "hard"


@pytest.mark.asyncio
async def test_the_match_stays_alive_while_a_dropped_seat_is_kept():
    game = make_game()
    (host,) = await playing(game)
    leave(game, host)
    assert game.match.alive()
    await run_for(game, TAKEOVER_SECONDS + 1)
    assert not game.match.alive()


# ---------- The end of a match ----------


@pytest.mark.asyncio
async def test_the_highest_total_score_wins_and_ties_all_win():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=((2, "easy"),))
    game.match.rounds = 1
    for number, score in ((0, 700), (1, 700), (2, 100)):
        game.match.seats[number].kit.score = score
    last_one_standing(game, 0)
    await game.match.message(first, {"fire": True})
    await shot_done(game)
    state = last_state(first)
    assert state["stage"] == RESULTS
    assert [row["won"] for row in state["results"]] == [True, True, False]
    # Only people go on the leaderboard
    assert [(r.user_id, r.name, r.won) for r in game.recorded[0]] == [(1, "Global 1", True), (2, "Global 2", True)]


@pytest.mark.asyncio
async def test_a_computer_win_goes_to_nobody():
    game = make_game()
    (host,) = await playing(game)
    game.match.rounds = 1
    game.match.seats[1].kit.score = 5000
    last_one_standing(game, 0)
    await game.match.message(host, {"fire": True})
    await shot_done(game)
    assert [r.won for r in game.recorded[0]] == [False]


@pytest.mark.asyncio
async def test_continue_goes_back_to_setup_with_the_same_seats_and_settings():
    game = make_game()
    (host,) = await playing(game)
    game.match.rounds = 1
    last_one_standing(game, 0)
    await game.match.message(host, {"fire": True})
    await shot_done(game)
    await game.match.message(host, {"continue": True})
    await run_ticks(game, 1)
    state = last_state(host)
    assert state["stage"] == SETUP and state["results"] is None and state["rounds"] == 1
    assert [seat["kind"] for seat in state["seats"]] == ["human", "cpu", "empty", "empty", "empty"]


@pytest.mark.asyncio
async def test_watchers_get_setup_back_once_every_player_has_left_the_results():
    game = make_game()
    (host,) = await playing(game)
    game.match.rounds = 1
    last_one_standing(game, 0)
    await game.match.message(host, {"fire": True})
    await shot_done(game)
    watcher = await arrive(game, 9)
    leave(game, host)
    await run_for(game, SETUP_GRACE_SECONDS + 1)
    assert game.match.stage == SETUP
    await game.match.message(watcher, {"sit": 0})
    assert game.match.host == 0


@pytest.mark.asyncio
async def test_a_failing_update_is_logged_once_and_ends_the_match(monkeypatch, caplog):
    game = make_game()
    conn = await arrive(game, 1)

    async def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(game.match, "tick", broken)
    with caplog.at_level(logging.ERROR, logger="red.vrt.tanks.match"):
        await game.match.run()
    assert len(caplog.records) == 1
    assert conn.sent[-1] == {"notice": LOOP_FAILED} and game.ended == [game.match]


# ---------- Things players do that the rules don't mention ----------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "fire",
        {},
        {"fire": True, "aim": [90, 50]},
        {"sit": True},
        {"sit": 5},
        {"sit": 1.0},
        {"aim": [float("nan"), 50]},
        {"aim": [90, float("inf")]},
        {"aim": [True, 50]},
        {"aim": [90]},
        {"drive": 2},
        {"drive": True},
        {"weapon": -1},
        {"use": ["shield", 9]},
        {"use": ["teleport", "x", 3]},
        {"buy": ["weapon", 0]},
        {"fire": [100, 1]},
        {"nonsense": 1},
    ],
)
async def test_odd_messages_are_ignored(data):
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    before = (tank.angle, tank.power, tank.x, tank.kit.weapon)
    await game.match.message(host, data)
    await run_ticks(game, 2)
    assert (tank.angle, tank.power, tank.x, tank.kit.weapon) == before
    assert not shots(host)


@pytest.mark.asyncio
async def test_whole_numbers_too_big_for_a_float_are_ignored():
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    tank.kit.extras[TELEPORT] = 1
    tank.kit.guns[AIR_STRIKE] = 1
    angle = tank.angle
    await game.match.message(host, {"aim": [10**400, 50]})
    await game.match.message(host, {"use": ["teleport", 10**400, 5]})
    tank.kit.weapon = AIR_STRIKE
    await game.match.message(host, {"fire": [10**400, 1]})
    assert tank.angle == angle and game.match.queued is None


@pytest.mark.asyncio
async def test_taps_while_a_shot_plays_are_ignored():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    await game.match.message(first, {"fire": True})
    await game.match.message(first, {"fire": True})
    await run_ticks(game, 1)
    angle = game.match.tanks[0].angle
    await game.match.message(first, {"aim": [angle + 10, 70]})
    await game.match.message(first, {"fire": True})
    await shot_done(game)
    assert len(shots(first)) == 1 and game.match.tanks[0].angle == angle


@pytest.mark.asyncio
async def test_no_snapshot_overtakes_a_playing_shot_and_late_arrivals_still_get_one():
    game = make_game()
    first, second = await playing(game, (1, 2), cpus=())
    await game.match.message(first, {"fire": True})
    await run_ticks(game, 2)
    sent = len(first.sent)
    late = await arrive(game, 3)
    assert "state" in late.sent[0]
    await run_ticks(game, 1)
    assert len(first.sent) == sent
    await shot_done(game)
    assert "state" in first.sent[-1]


@pytest.mark.asyncio
async def test_a_shot_that_destroys_every_tank_ends_the_round_cleanly():
    game = make_game()
    (host,) = await playing(game)
    for tank in game.match.tanks.values():
        tank.energy = 0
    await game.match.message(host, {"fire": True})
    await shot_done(game)
    assert game.match.stage == SHOP and game.match.round == 1
    await game.match.message(host, {"done": True})
    await run_ticks(game, 1)
    assert game.match.stage == PLAYING and all(tank.alive for tank in game.match.tanks.values())


@pytest.mark.asyncio
async def test_a_teleport_or_air_strike_aimed_off_the_field_lands_on_it():
    game = make_game()
    (host,) = await playing(game)
    tank = game.match.tanks[0]
    tank.kit.extras[TELEPORT] = 1
    await game.match.message(host, {"use": ["teleport", -500, -80]})
    assert game.match.queued == ("teleport", (MIN_X, 0.0))
    game.match.queued = None
    tank.kit.guns[AIR_STRIKE] = 1
    tank.kit.weapon = AIR_STRIKE
    await game.match.message(host, {"fire": [9999, 1]})
    assert game.match.queued == ("fire", (550.0, 1))
