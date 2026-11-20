import asyncio
import logging
import random
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from penguinwars.common.cpu import NAMES
from penguinwars.common.leaderboard import Result
from penguinwars.common.maps import classic_map
from penguinwars.common.match import (
    COUNTDOWN_SECONDS,
    GRACE_SECONDS,
    LOOP_FAILED,
    PLAYING,
    RESULTS,
    RESULTS_SECONDS,
    STARTING,
    STARTING_SECONDS,
    WAITING,
    Match,
)
from penguinwars.common.round import DT, SWIM, TICK_RATE
from penguinwars.common.shop import Played
from penguinwars.common.tuning import Tuning
from penguinwars.tests.fakes import Clock, FakeConn, FakeRoom

LOOKS = {}


def make_game():
    room, ended, clock, saved, played = FakeRoom(), [], Clock(), [], []
    match = Match(
        room,
        Tuning(),
        ended.append,
        rng=random.Random(7),
        clock=clock,
        recorded=lambda guild_id, results: saved.append((guild_id, results)),
        played=lambda match, people: played.append(people),
    )
    # Every round here is played on the whole floe with no hazard, where each penguin's start spot is known
    match.fixed_map = classic_map()
    return SimpleNamespace(match=match, room=room, clock=clock, ended=ended, saved=saved, played=played)


async def run_ticks(game, count):
    for _ in range(count):
        game.clock.now += DT
        await game.match.tick()


async def run_for(game, seconds):
    await run_ticks(game, round(seconds * TICK_RATE))


async def arrive(game, user_id, looks=LOOKS):
    conn = FakeConn(game.room, user_id)
    await game.match.join(conn, looks)
    return conn


def leave(game, conn):
    conn.drop()
    game.match.leave(conn)


def last_state(conn):
    return next(message["state"] for message in reversed(conn.sent) if "state" in message)


async def seat_group(game, user_ids):
    """Seat these people between rounds. Alone, Play starts a round at once, so the first is seated the way the line
    seats someone, and the others press Play, which starts the 10-second countdown"""
    conns = [await arrive(game, user_id) for user_id in user_ids]
    game.match.seat_person(0, conns[0])
    for conn in conns[1:]:
        await game.match.message(conn, {"sit": True})
    return conns


async def playing(game, user_ids=(1,)):
    """Seat these players and start, then run until the round is under way and the starting cooldown is over. Alone,
    Play starts the round. A group is seated and the first presses Start"""
    if len(user_ids) == 1:
        conns = [await arrive(game, user_ids[0])]
        await game.match.message(conns[0], {"sit": True})
    else:
        conns = await seat_group(game, user_ids)
        await game.match.message(conns[0], {"start": True})
    await run_ticks(game, 1 + STARTING_SECONDS * TICK_RATE)
    assert game.match.stage == PLAYING
    await run_for(game, 0.5)
    return conns


async def into_results(game, user_ids=(1,)):
    """Everyone but seat 0 falls off, and the round runs out its end pause"""
    conns = await playing(game, user_ids)
    for p in game.match.round.penguins[1:]:
        p.alive = False
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    return conns


@pytest.mark.asyncio
async def test_sitting_beside_someone_takes_the_first_free_spot_and_starts_the_countdown():
    game = make_game()
    first, second = await arrive(game, 1), await arrive(game, 2)
    assert last_state(first)["stage"] == WAITING and last_state(first)["countdown"] is None
    game.match.seat_person(0, first)
    assert game.match.countdown is None
    await game.match.tick()
    assert last_state(first)["countdown"] is None
    await game.match.message(second, {"sit": True})
    await game.match.tick()
    state = last_state(first)
    assert state["seats"][0] == {
        "kind": "human",
        "id": "1",
        "name": "Player 1",
        "away": False,
        "looks": {},
        "played": False,
    }
    assert state["seats"][1]["id"] == "2" and state["seats"][2]["kind"] == "empty"
    assert state["countdown"] == COUNTDOWN_SECONDS and state["watching"] == 0
    assert state["round"] == 1 and state["board"] is None and state["results"] is None
    assert state["rules"] == asdict(Tuning())


@pytest.mark.asyncio
async def test_a_second_sit_from_a_seated_player_changes_nothing():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": True})
    await game.match.message(conn, {"sit": True})
    assert [seat.user_id for seat in game.match.seats] == [1, None, None, None, None, None]


@pytest.mark.asyncio
async def test_one_of_two_standing_up_stops_the_countdown_and_nothing_starts():
    game = make_game()
    first, second = await seat_group(game, (1, 2))
    await game.match.tick()
    assert last_state(first)["countdown"] == COUNTDOWN_SECONDS
    await game.match.message(second, {"stand": True})
    await game.match.tick()
    state = last_state(first)
    assert game.match.countdown is None and state["countdown"] is None and state["seats"][1]["kind"] == "empty"
    await run_for(game, COUNTDOWN_SECONDS + 1)
    assert game.match.stage == WAITING and game.match.seats[0].user_id == 1


@pytest.mark.asyncio
async def test_the_countdown_stops_when_a_dropped_partners_grace_runs_out():
    game = make_game()
    first, second = await seat_group(game, (1, 2))
    leave(game, second)
    # A seat kept for a dropped player still counts, so the countdown runs on
    await run_for(game, 5)
    assert game.match.countdown is not None
    game.clock.now += GRACE_SECONDS
    await run_ticks(game, 1)
    assert game.match.countdown is None and last_state(first)["countdown"] is None
    await run_for(game, COUNTDOWN_SECONDS)
    assert game.match.stage == WAITING


@pytest.mark.asyncio
async def test_alone_play_starts_the_round_at_once():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": True})
    assert game.match.stage == STARTING and game.match.countdown is None
    await game.match.tick()
    state = last_state(conn)
    assert state["stage"] == STARTING and state["left"] == STARTING_SECONDS and state["countdown"] is None
    assert [seat["kind"] for seat in state["seats"]] == ["human"] + ["cpu"] * 5


@pytest.mark.asyncio
async def test_someone_left_alone_in_their_seat_starts_with_start():
    game = make_game()
    first, second = await seat_group(game, (1, 2))
    await game.match.message(second, {"stand": True})
    await run_ticks(game, 1)
    assert game.match.stage == WAITING and game.match.countdown is None
    await game.match.message(first, {"start": True})
    await game.match.tick()
    assert game.match.stage == STARTING and game.match.round_players == {0: 1}


@pytest.mark.asyncio
async def test_coming_back_to_a_kept_seat_starts_the_countdown_only_with_company():
    game = make_game()
    (alone,) = await seat_group(game, (1,))
    leave(game, alone)
    await arrive(game, 1)
    assert game.match.seats[0].dropped_at is None and game.match.countdown is None
    pair = make_game()
    for conn in await seat_group(pair, (1, 2)):
        leave(pair, conn)
    # With only dropped players seated, the countdown runs out and waits for one of them
    await run_for(pair, COUNTDOWN_SECONDS)
    assert pair.match.stage == WAITING and pair.match.countdown is None
    await arrive(pair, 2)
    assert pair.match.countdown == COUNTDOWN_SECONDS * TICK_RATE


@pytest.mark.asyncio
async def test_the_countdown_runs_10_then_3_then_the_round_plays():
    game = make_game()
    conn, _ = await seat_group(game, (1, 2))
    await run_for(game, COUNTDOWN_SECONDS - 1)
    assert game.match.stage == WAITING
    await run_for(game, 1)
    assert game.match.stage == STARTING and last_state(conn)["left"] == STARTING_SECONDS
    await run_for(game, STARTING_SECONDS)
    assert game.match.stage == PLAYING and last_state(conn)["board"] is not None


@pytest.mark.asyncio
async def test_start_skips_the_countdown():
    game = make_game()
    conn, _ = await seat_group(game, (1, 2))
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    assert game.match.stage == STARTING


@pytest.mark.asyncio
async def test_a_spectator_cannot_press_start():
    game = make_game()
    await seat_group(game, (1, 2))
    watcher = await arrive(game, 3)
    await game.match.message(watcher, {"start": True})
    await game.match.tick()
    assert game.match.stage == WAITING and game.match.countdown > 1


@pytest.mark.asyncio
async def test_cpus_fill_every_empty_spot_with_named_penguins():
    game = make_game()
    (conn,) = await playing(game)
    seats = last_state(conn)["seats"]
    assert [seat["kind"] for seat in seats] == ["human"] + ["cpu"] * 5
    assert [seat["name"] for seat in seats[1:]] == NAMES[1:]
    assert all(seat["id"] is None and seat["looks"] == {"neck": "scarf"} for seat in seats[1:])
    assert game.match.round.cpus == {1, 2, 3, 4, 5}


@pytest.mark.asyncio
async def test_a_seventh_player_watches_and_joins_the_line():
    game = make_game()
    await seat_group(game, range(1, 7))
    late = await arrive(game, 7)
    await game.match.message(late, {"sit": True})
    await game.match.tick()
    assert last_state(late)["watching"] == 1 and last_state(late)["line"] == ["7"]


@pytest.mark.asyncio
async def test_sitting_again_while_in_the_line_keeps_the_place():
    game = make_game()
    await seat_group(game, range(1, 7))
    late = await arrive(game, 7)
    await game.match.message(late, {"sit": True})
    await game.match.message(late, {"sit": True})
    assert game.match.line == [7]


@pytest.mark.asyncio
async def test_a_friend_arriving_mid_round_gets_the_live_board_and_can_sit_next_round():
    game = make_game()
    await playing(game)
    friend = await arrive(game, 2)
    state = last_state(friend)
    assert state["stage"] == PLAYING and state["board"]["t"] and len(state["board"]["p"]) == 6
    assert state["watching"] == 1
    await game.match.message(friend, {"sit": True})
    assert game.match.seat_of(2) is None and game.match.line == [2]
    for p in game.match.round.penguins[1:]:
        p.alive = False
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    await run_for(game, RESULTS_SECONDS)
    assert [seat.user_id for seat in game.match.seats[:3]] == [1, 2, None]


@pytest.mark.asyncio
async def test_slide_brace_and_splash_only_move_the_senders_own_penguin():
    game = make_game()
    one, two = await playing(game, (1, 2))
    penguins = game.match.round.penguins
    await game.match.message(one, {"slide": [1, 0, 1]})
    assert penguins[0].vx > 0 and penguins[0].cd > 0
    assert (penguins[1].vx, penguins[1].vz, penguins[1].cd) == (0.0, 0.0, 0.0)
    await game.match.message(two, {"brace": True})
    assert penguins[1].brace > 0 and penguins[0].brace == 0
    penguins[0].alive = False
    penguins[0].seal.state, penguins[0].seal.cd = SWIM, 0.0
    await game.match.message(two, {"splash": 0.5})
    assert penguins[0].seal.state == SWIM
    await game.match.message(one, {"splash": 0.5})
    assert penguins[0].seal.state != SWIM and penguins[0].seal.wait == Tuning().seal_wait


@pytest.mark.asyncio
async def test_inputs_outside_a_round_do_nothing():
    game = make_game()
    conn, _ = await seat_group(game, (1, 2))
    for data in ({"slide": [1, 0, 1]}, {"brace": True}, {"splash": 1.0}):
        await game.match.message(conn, data)
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    assert game.match.stage == STARTING
    await game.match.message(conn, {"slide": [1, 0, 1]})
    assert game.match.round.penguins[0].vx == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"slide": [float("nan"), 0, 1]},
        {"slide": [float("inf"), 0, 1]},
        {"slide": [1e308, 1e308, 1]},
        {"slide": [0, 0, 1]},
        {"slide": [10**400, 0, 1]},
        {"slide": [1, 0, 10**400]},
        {"splash": 10**400},
        {"slide": "left"},
        {"slide": [1, 0]},
        {"slide": [True, 0, 1]},
        {"splash": "edge"},
        {"splash": float("nan")},
        {"brace": False},
        {"sit": 3},
        ["slide"],
        7,
    ],
)
async def test_junk_moves_are_ignored(bad):
    game = make_game()
    (conn,) = await playing(game)
    before = asdict(game.match.round.penguins[0])
    await game.match.message(conn, bad)
    assert asdict(game.match.round.penguins[0]) == before
    assert game.match.round.events == []


@pytest.mark.asyncio
async def test_a_dropped_player_gets_20_seconds_then_a_cpu_takes_over():
    game = make_game()
    conn, _ = await playing(game, (1, 2))
    leave(game, conn)
    await run_for(game, GRACE_SECONDS - 1)
    assert game.match.seats[0].dropped_at is not None and game.match.seats[0].cpu is None
    await run_for(game, 2)
    seat = game.match.seats[0]
    assert seat.cpu is not None and seat.user_id is None and seat.name == NAMES[0]
    assert 0 in game.match.round.cpus


@pytest.mark.asyncio
async def test_with_someone_else_still_on_the_ice_a_leave_keeps_the_grace():
    game = make_game()
    _, second = await playing(game, (1, 2))
    board = game.match.round
    leave(game, second)
    await run_ticks(game, 1)
    seat = game.match.seats[1]
    assert game.match.stage == PLAYING and game.match.round is board
    assert seat.user_id == 2 and seat.dropped_at is not None and seat.cpu is None
    assert last_state(game.room.members[0])["seats"][1]["away"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [STARTING, PLAYING])
async def test_alone_leaving_mid_round_stops_it_and_empties_the_seat(stage):
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": True})
    if stage == PLAYING:
        await run_for(game, STARTING_SECONDS + 1)
    assert game.match.stage == stage
    leave(game, conn)
    match = game.match
    assert match.stage == WAITING and match.round is None and match.results is None and match.countdown is None
    assert all(not seat.human and seat.cpu is None for seat in match.seats)
    # Nobody's seat is kept, so an empty window lets the match end
    assert not match.alive()
    back = await arrive(game, 1)
    state = last_state(back)
    assert state["stage"] == WAITING and state["board"] is None and state["results"] is None
    assert [seat["kind"] for seat in state["seats"]] == ["empty"] * 6


@pytest.mark.asyncio
async def test_the_last_person_leaving_mid_round_stops_it_records_nothing_and_clears_their_seats():
    game = make_game()
    first, second = await playing(game, (1, 2))
    leave(game, second)
    await run_for(game, 1)
    assert game.match.stage == PLAYING
    leave(game, first)
    match = game.match
    assert match.stage == WAITING and match.round is None and match.countdown is None
    # Both left: the one who dropped first and the one whose leave stopped the round
    assert all(not seat.human and seat.cpu is None for seat in match.seats)
    await run_for(game, GRACE_SECONDS + RESULTS_SECONDS)
    assert game.saved == [] and game.played == []
    assert match.stage == WAITING and match.results is None
    back = await arrive(game, 1)
    await game.match.message(back, {"sit": True})
    assert match.stage == STARTING and match.seats[0].user_id == 1


@pytest.mark.asyncio
async def test_coming_back_in_time_gets_the_penguin_back():
    game = make_game()
    conn, _ = await playing(game, (1, 2))
    leave(game, conn)
    await run_for(game, GRACE_SECONDS - 1)
    back = await arrive(game, 1)
    seat = game.match.seats[0]
    assert seat.conn is back and seat.dropped_at is None and seat.cpu is None
    await run_for(game, 5)
    assert seat.cpu is None


@pytest.mark.asyncio
async def test_a_second_device_drives_the_same_penguin():
    game = make_game()
    (phone,) = await playing(game)
    laptop = await arrive(game, 1)
    leave(game, phone)
    seat = game.match.seats[0]
    assert seat.conn is laptop and seat.dropped_at is None
    await game.match.message(laptop, {"slide": [0, 1, 1]})
    assert game.match.round.penguins[0].vz > 0


@pytest.mark.asyncio
async def test_a_dropped_seal_becomes_a_cpu_seal():
    game = make_game()
    conn, _ = await playing(game, (1, 2))
    game.match.round.penguins[0].alive = False
    leave(game, conn)
    await run_for(game, GRACE_SECONDS + 1)
    assert game.match.seats[0].cpu is not None and 0 in game.match.round.cpus


@pytest.mark.asyncio
async def test_results_show_for_6_seconds_then_the_players_go_again():
    game = make_game()
    conn, _ = await into_results(game, (1, 2))
    state = last_state(conn)
    assert state["results"]["winner"] == 0 and state["results"]["name"] == "Player 1"
    # The seconds count to the next round's 3-2-1, through the countdown after the results
    assert state["board"] is not None and state["left"] == RESULTS_SECONDS + COUNTDOWN_SECONDS
    # The results began part way through the last two seconds run, so they end within the 6 seconds
    ticks = 0
    while game.match.stage == RESULTS:
        await run_ticks(game, 1)
        ticks += 1
    assert 4 * TICK_RATE < ticks <= RESULTS_SECONDS * TICK_RATE
    match = game.match
    assert match.stage == WAITING and match.round is None and match.round_number == 2
    assert match.countdown == COUNTDOWN_SECONDS * TICK_RATE
    assert [seat.user_id for seat in match.seats[:2]] == [1, 2] and all(seat.cpu is None for seat in match.seats)
    assert not any(seat.human for seat in match.seats[2:])
    assert last_state(conn)["results"] is None


@pytest.mark.asyncio
async def test_alone_the_results_wait_for_play_again():
    game = make_game()
    (conn,) = await into_results(game)
    await run_for(game, 60)
    match = game.match
    assert match.stage == RESULTS and match.countdown is None
    game.match.dirty = True
    await game.match.tick()
    # Nothing counts down, so the page gets no seconds to show
    state = last_state(conn)
    assert state["stage"] == RESULTS and state["left"] is None and state["countdown"] is None
    assert state["results"]["winner"] == 0
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    assert match.stage == STARTING and match.round_number == 2


@pytest.mark.asyncio
async def test_someone_sitting_during_a_solo_players_results_starts_the_timers():
    game = make_game()
    (conn,) = await into_results(game)
    await run_for(game, RESULTS_SECONDS + 1)
    assert game.match.stage == RESULTS
    friend = await arrive(game, 2)
    await game.match.message(friend, {"sit": True})
    await game.match.tick()
    assert game.match.seat_of(2) is not None and last_state(conn)["left"] == RESULTS_SECONDS + COUNTDOWN_SECONDS
    await run_for(game, RESULTS_SECONDS)
    assert game.match.stage == WAITING and last_state(conn)["countdown"] == COUNTDOWN_SECONDS
    await run_for(game, COUNTDOWN_SECONDS)
    assert game.match.stage == STARTING and game.match.round_players == {0: 1, 1: 2}


@pytest.mark.asyncio
async def test_stepping_out_of_a_solo_players_results_lets_them_end_and_nothing_starts():
    game = make_game()
    (conn,) = await into_results(game)
    await game.match.message(conn, {"stand": True})
    await run_for(game, RESULTS_SECONDS)
    match = game.match
    assert match.stage == WAITING and match.countdown is None and match.round is None
    assert not any(seat.human for seat in match.seats)


@pytest.mark.asyncio
async def test_a_lone_play_during_results_starts_the_round_at_once():
    game = make_game()
    (conn,) = await into_results(game)
    await game.match.message(conn, {"stand": True})
    await run_for(game, 1)
    assert game.match.stage == RESULTS
    await game.match.message(conn, {"sit": True})
    await game.match.tick()
    assert game.match.stage == STARTING and game.match.round_players == {0: 1}


@pytest.mark.asyncio
async def test_a_second_person_sitting_during_results_keeps_the_results_time():
    game = make_game()
    conn, _ = await into_results(game, (1, 2))
    await game.match.message(conn, {"stand": True})
    third = await arrive(game, 3)
    await game.match.message(third, {"sit": True})
    await run_for(game, 1)
    assert game.match.stage == RESULTS and game.match.people_seated() == 2
    await run_for(game, RESULTS_SECONDS)
    assert game.match.stage == WAITING and game.match.countdown is not None


@pytest.mark.asyncio
async def test_someone_in_the_line_keeps_a_solo_players_results_moving():
    game = make_game()
    await playing(game)
    friend = await arrive(game, 2)
    await game.match.message(friend, {"line": True})
    for p in game.match.round.penguins[1:]:
        p.alive = False
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    await run_for(game, RESULTS_SECONDS)
    assert game.match.stage == WAITING and game.match.seat_of(2) is not None
    assert game.match.countdown is not None


@pytest.mark.asyncio
async def test_a_result_without_a_winner_has_no_name():
    game = make_game()
    (conn,) = await playing(game)
    for p in game.match.round.penguins:
        p.alive = False
    await run_for(game, 2)
    assert last_state(conn)["results"]["winner"] is None and last_state(conn)["results"]["name"] is None


@pytest.mark.asyncio
async def test_play_again_skips_the_countdown():
    game = make_game()
    (conn,) = await into_results(game)
    watcher = await arrive(game, 2)
    await game.match.message(watcher, {"start": True})
    await game.match.tick()
    assert game.match.stage == RESULTS
    old = game.match.round
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    match = game.match
    assert match.stage == STARTING and match.countdown is None and match.round_number == 2
    assert match.round is not old and last_state(conn)["results"] is None
    assert match.round.cpus == {1, 2, 3, 4, 5}


@pytest.mark.asyncio
async def test_without_a_press_the_results_then_the_normal_countdown():
    game = make_game()
    await into_results(game, (1, 2))
    await run_for(game, RESULTS_SECONDS)
    assert game.match.stage == WAITING and game.match.countdown is not None


@pytest.mark.asyncio
async def test_sitting_during_results_takes_an_empty_seat_then_a_cpu_seat_then_is_full():
    game = make_game()
    (first,) = await into_results(game)
    await game.match.message(first, {"stand": True})
    for user_id in range(2, 7):
        await game.match.message(await arrive(game, user_id), {"sit": True})
    assert [seat.user_id for seat in game.match.seats] == [2, 3, 4, 5, 6, None]
    assert game.match.seats[5].cpu is not None
    await game.match.message(await arrive(game, 7), {"sit": True})
    assert game.match.seats[5].user_id == 7 and game.match.seats[5].cpu is None
    extra = await arrive(game, 8)
    await game.match.message(extra, {"sit": True})
    assert game.match.line == [8]


@pytest.mark.asyncio
async def test_a_seat_swapped_in_results_did_not_play_and_the_winner_card_survives():
    game = make_game()
    first, _ = await into_results(game, (1, 3))
    await game.match.message(first, {"stand": True})
    second = await arrive(game, 2)
    await game.match.message(second, {"sit": True})
    await game.match.tick()
    state = last_state(second)
    assert state["seats"][0]["played"] is False and state["results"]["name"] == "Player 1"


@pytest.mark.asyncio
async def test_a_seat_says_whether_its_player_played_the_round():
    game = make_game()
    (conn,) = await playing(game)
    await game.match.tick()
    game.match.dirty = True
    await game.match.tick()
    assert last_state(conn)["seats"][0]["played"] is True


@pytest.mark.asyncio
async def test_no_event_is_lost_when_a_snapshot_replaces_a_frame():
    game = make_game()
    (conn,) = await playing(game)
    game.match.round.events.append(["crack", 3])
    game.match.dirty = True
    await game.match.tick()
    assert ["crack", 3] in last_state(conn)["board"]["e"]
    await game.match.tick()
    assert ["crack", 3] not in conn.sent[-1].get("e", [])


@pytest.mark.asyncio
async def test_a_join_between_two_updates_does_not_swallow_pending_events():
    game = make_game()
    (conn,) = await playing(game)
    game.match.round.events.append(["crack", 3])
    late = await arrive(game, 9)
    assert "e" not in last_state(late)["board"]
    await game.match.tick()
    assert ["crack", 3] in last_state(conn)["board"]["e"]
    assert ["crack", 3] in last_state(late)["board"]["e"]


@pytest.mark.asyncio
async def test_frames_have_only_the_frame_fields():
    game = make_game()
    (conn,) = await playing(game)
    await game.match.tick()
    frame = conn.sent[-1]
    assert set(frame) <= {"f", "p", "e"} and len(frame["p"]) == 6


@pytest.mark.asyncio
async def test_new_tuning_reaches_the_running_round_and_every_page():
    game = make_game()
    (conn,) = await playing(game)
    new = Tuning(slide_speed=14.0)
    game.match.set_tuning(new)
    assert game.match.round.tuning is new and game.match.round.floe.tuning is new
    await game.match.tick()
    assert last_state(conn)["rules"]["slide_speed"] == 14.0


@pytest.mark.asyncio
async def test_looks_follow_the_player_to_their_seat():
    game = make_game()
    conn = await arrive(game, 1, {"hat": "party", "trail": "sparkle"})
    await game.match.message(conn, {"sit": True})
    await game.match.tick()
    assert last_state(conn)["seats"][0]["looks"] == {"hat": "party", "trail": "sparkle"}
    game.match.set_looks(1, {"hat": "crown"})
    await game.match.tick()
    assert last_state(conn)["seats"][0]["looks"] == {"hat": "crown"}


@pytest.mark.asyncio
async def test_the_match_stays_alive_while_a_dropped_seat_is_kept():
    game = make_game()
    (conn,) = await seat_group(game, (1,))
    leave(game, conn)
    assert game.match.alive()
    await run_for(game, GRACE_SECONDS + 1)
    assert not game.match.alive()


@pytest.mark.asyncio
async def test_the_loop_stops_when_the_window_empties():
    game = make_game()
    conn = await arrive(game, 1)
    game.match.start()
    leave(game, conn)
    await asyncio.wait_for(game.match.task, 2)
    assert game.ended == [game.match]


@pytest.mark.asyncio
async def test_a_failing_update_tells_the_window_once(monkeypatch, caplog):
    game = make_game()
    conn = await arrive(game, 1)

    async def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(game.match, "tick", broken)
    with caplog.at_level(logging.ERROR):
        await game.match.run()
    assert caplog.text.count("Penguin Wars stopped a round") == 1
    assert conn.sent.count({"notice": LOOP_FAILED}) == 1
    assert game.ended == [game.match]


# ---------- Big groups take turns ----------


def seated_ids(game):
    return [seat.user_id for seat in game.match.seats]


def conn_of(game, user_id):
    return next(conn for conn in game.room.members if conn.ctx.author.id == user_id)


async def full_ice(game, line_ids=()):
    """Players 1 to 6 seated and the round under way, then these people line up"""
    conns = await playing(game, (1, 2, 3, 4, 5, 6))
    for user_id in line_ids:
        conn = await arrive(game, user_id)
        await game.match.message(conn, {"sit": True})
        conns.append(conn)
    return conns


async def finish(game, out_order, winner=0):
    """Knock these seats out in this order, first one first, then run the results to their end"""
    penguins = game.match.round.penguins
    for turn, number in enumerate(out_order):
        penguins[number].alive = False
        penguins[number].place = 6 - turn
    penguins[winner].place = 1
    for number, penguin in enumerate(penguins):
        if number != winner and number not in out_order:
            penguin.alive = False
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    await run_for(game, RESULTS_SECONDS)


@pytest.mark.asyncio
async def test_the_line_takes_the_first_out_spots_and_the_swapped_go_to_the_back():
    game = make_game()
    await full_ice(game, (7, 8))
    assert game.match.line == [7, 8]
    await finish(game, [3, 1, 5, 2, 4])
    # Seat 3 went out first and seat 1 second, so 7 (waiting longest) takes seat 3 and 8 takes seat 1
    assert seated_ids(game) == [1, 8, 3, 7, 5, 6]
    assert game.match.line == [4, 2] and game.match.sat_out == [4, 2]
    assert game.match.seats[1].name == "Player 8"


@pytest.mark.asyncio
async def test_the_swap_comes_back_round_next_round():
    game = make_game()
    await full_ice(game, (7, 8))
    await finish(game, [3, 1, 5, 2, 4])
    await game.match.message(conn_of(game, 1), {"start": True})
    await run_ticks(game, 1 + STARTING_SECONDS * TICK_RATE)
    assert game.match.stage == PLAYING
    # Player 8 (seat 1) goes out first, then player 7 (seat 3)
    await finish(game, [1, 3, 2, 4, 5])
    assert game.match.seats[1].user_id == 4 and game.match.seats[3].user_id == 2
    assert game.match.line == [8, 7]


@pytest.mark.asyncio
async def test_the_winner_is_never_swapped_even_with_six_in_line():
    game = make_game()
    await full_ice(game, (7, 8, 9, 10, 11, 12))
    await finish(game, [1, 2, 3, 4, 5])
    assert game.match.seats[0].user_id == 1
    assert seated_ids(game)[1:] == [7, 8, 9, 10, 11]
    assert game.match.line == [12, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_someone_who_sat_during_the_results_is_not_swapped():
    game = make_game()
    conns = await full_ice(game)
    for p in game.match.round.penguins[1:]:
        p.alive = False
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    await game.match.message(conns[1], {"stand": True})
    newcomer = await arrive(game, 7)
    await game.match.message(newcomer, {"sit": True})
    assert game.match.seats[1].user_id == 7
    waiting = await arrive(game, 8)
    await game.match.message(waiting, {"sit": True})
    await run_for(game, RESULTS_SECONDS)
    assert game.match.seats[1].user_id == 7
    assert 8 in seated_ids(game) and 8 not in game.match.line


@pytest.mark.asyncio
async def test_empty_and_cpu_spots_fill_before_anyone_is_swapped():
    game = make_game()
    await playing(game, (1, 2))
    for user_id in (3, 4, 5):
        await game.match.message(await arrive(game, user_id), {"sit": True})
    assert game.match.line == [3, 4, 5]
    await finish(game, [1])
    # Seats 2 to 5 were CPU spots, so 3, 4 and 5 take them and nobody is swapped out
    assert seated_ids(game)[:2] == [1, 2]
    assert sorted(seated_ids(game)[2:5]) == [3, 4, 5]
    assert game.match.line == [] and game.match.sat_out == []


@pytest.mark.asyncio
async def test_a_place_in_line_waits_out_a_short_drop_and_goes_after_the_grace_period():
    game = make_game()
    conns = await full_ice(game, (7, 8))
    leave(game, conns[6])
    assert game.match.line == [7, 8]
    game.clock.now += GRACE_SECONDS - 1
    await game.match.tick()
    back = await arrive(game, 7)
    game.clock.now += 2
    await game.match.tick()
    assert game.match.line == [7, 8]
    leave(game, back)
    game.clock.now += GRACE_SECONDS
    await game.match.tick()
    assert game.match.line == [8]


@pytest.mark.asyncio
async def test_a_second_device_keeps_the_place_in_line():
    game = make_game()
    conns = await full_ice(game, (7,))
    again = await arrive(game, 7)
    leave(game, conns[6])
    assert game.match.line == [7]
    await finish(game, [1, 2, 3, 4, 5])
    assert next(seat for seat in game.match.seats if seat.user_id == 7).conn is again


@pytest.mark.asyncio
async def test_no_line_means_the_players_keep_their_spots():
    game = make_game()
    await full_ice(game)
    await finish(game, [1, 2, 3, 4, 5])
    assert seated_ids(game) == [1, 2, 3, 4, 5, 6]
    assert game.match.sat_out == []


@pytest.mark.asyncio
async def test_start_ends_the_results_at_once_and_the_swap_still_happens():
    game = make_game()
    await full_ice(game, (7,))
    penguins = game.match.round.penguins
    for turn, number in enumerate([5, 4, 3, 2, 1]):
        penguins[number].alive = False
        penguins[number].place = 6 - turn
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    await game.match.message(conn_of(game, 1), {"start": True})
    await run_ticks(game, 1)
    assert game.match.stage == STARTING
    # Seat 5 went out first
    assert game.match.seats[5].user_id == 7 and game.match.line == [6]


@pytest.mark.asyncio
async def test_line_messages_say_join_or_leave_so_a_repeat_changes_nothing_and_junk_does_nothing():
    game = make_game()
    await full_ice(game)
    late = await arrive(game, 7)
    await game.match.message(late, {"sit": True})
    assert game.match.line == [7]
    await game.match.message(late, {"line": True})
    assert game.match.line == [7]
    await game.match.message(late, {"line": False})
    await game.match.message(late, {"line": False})
    assert game.match.line == []
    await game.match.message(late, {"line": True})
    await game.match.message(late, {"line": True})
    assert game.match.line == [7]
    for junk in ({"line": 0}, {"line": "no"}, {"line": None}, {"line": [7]}, {"line": False, "x": 1}):
        await game.match.message(late, junk)
    assert game.match.line == [7]
    await game.match.message(conn_of(game, 1), {"line": True})
    assert game.match.line == [7]


@pytest.mark.asyncio
async def test_stand_takes_you_off_the_line_and_never_puts_you_back():
    game = make_game()
    conns = await full_ice(game, (7, 8))
    await game.match.message(conns[6], {"stand": True})
    assert game.match.line == [8]
    # A page sending it again, or before it heard the first, can't put the person back in the line
    await game.match.message(conns[6], {"stand": True})
    assert game.match.line == [8] and game.match.stage == PLAYING
    await game.match.tick()
    assert last_state(conns[6])["line"] == ["8"]


@pytest.mark.asyncio
async def test_stand_clears_the_sat_out_note_with_the_place_in_line():
    game = make_game()
    await full_ice(game, (7,))
    await finish(game, [1, 2, 3, 4, 5])
    assert game.match.sat_out == [2]
    await game.match.message(conn_of(game, 2), {"stand": True})
    assert game.match.line == [] and game.match.sat_out == []


@pytest.mark.asyncio
async def test_the_snapshot_names_the_line_and_who_sat_out():
    game = make_game()
    conns = await full_ice(game, (7,))
    await finish(game, [1, 2, 3, 4, 5])
    await game.match.tick()
    state = last_state(conns[6])
    assert state["line"] == ["2"] and state["out"] == ["2"]


@pytest.mark.asyncio
async def test_leaving_the_line_clears_the_sat_out_note():
    game = make_game()
    await full_ice(game, (7,))
    await finish(game, [1, 2, 3, 4, 5])
    assert game.match.sat_out == [2]
    await game.match.message(conn_of(game, 2), {"line": False})
    assert 2 not in game.match.line
    assert game.match.sat_out == []


async def finish_round(game, user_ids, winner):
    """Seat these players, start, and end the round with this seat the only penguin left"""
    await playing(game, user_ids)
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == winner
    game.match.round.knocked[winner] = 3
    await run_for(game, 2)
    assert game.match.stage == RESULTS


@pytest.mark.asyncio
async def test_a_round_of_two_people_saves_both_with_the_win_and_knockouts():
    game = make_game()
    await finish_round(game, (1, 2), winner=0)
    assert game.saved == [
        (500, [Result(1, "Player 1", 3, True), Result(2, "Player 2", 0, False)]),
    ]


@pytest.mark.asyncio
async def test_a_round_of_one_person_saves_nothing():
    game = make_game()
    await finish_round(game, (1,), winner=0)
    assert game.saved == []


@pytest.mark.asyncio
async def test_a_player_replaced_by_a_cpu_gets_nothing_and_a_cpu_win_gives_no_win():
    game = make_game()
    conns = await playing(game, (1, 2, 3))
    leave(game, conns[1])
    game.clock.now += GRACE_SECONDS + 1
    await game.match.tick()
    assert game.match.seats[1].cpu is not None
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == 1
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    ((guild_id, results),) = game.saved
    assert [r.user_id for r in results] == [1, 3] and not any(r.won for r in results)


@pytest.mark.asyncio
async def test_someone_who_sits_down_mid_round_is_not_saved():
    game = make_game()
    await playing(game, (1, 2))
    third = await arrive(game, 3)
    await game.match.message(third, {"sit": True})
    assert game.match.seat_of(3) is None and game.match.line == [3]
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == 0
    await run_for(game, 2)
    assert [r.user_id for r in game.saved[0][1]] == [1, 2]


@pytest.mark.asyncio
async def test_a_player_who_drops_and_comes_back_in_time_still_gets_credit():
    game = make_game()
    conns = await playing(game, (1, 2))
    leave(game, conns[1])
    # Held still, so the ice does not end the round while the player is away
    game.match.round.floe.crack_timer = 1000.0
    await run_for(game, 15)
    assert game.match.stage == PLAYING and game.match.seat_of(2).dropped_at is not None
    back = await arrive(game, 2)
    assert game.match.seat_of(2).conn is back
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == 1
    # The returned player is the last one standing, in the middle of the ice
    game.match.round.penguins[1].x = game.match.round.penguins[1].z = 0.0
    await run_for(game, 2)
    assert [r.user_id for r in game.saved[0][1]] == [1, 2]
    assert [r.won for r in game.saved[0][1]] == [False, True]


@pytest.mark.asyncio
async def test_a_player_swapped_out_before_a_round_gets_nothing_and_the_one_swapped_in_does():
    game = make_game()
    conns = await into_results(game, (1, 2, 3, 4, 5, 6))
    game.saved.clear()
    seventh, eighth = await arrive(game, 7), await arrive(game, 8)
    await game.match.message(seventh, {"sit": True})
    await game.match.message(eighth, {"sit": True})
    await run_for(game, RESULTS_SECONDS + 1)
    assert game.match.stage == WAITING
    out = [user_id for user_id in game.match.sat_out]
    assert len(out) == 2 and 1 not in out
    await game.match.message(conns[0], {"start": True})
    await run_ticks(game, 1 + STARTING_SECONDS * TICK_RATE)
    for p in game.match.round.penguins:
        p.alive = False
    game.match.round.penguins[0].alive = True
    await run_for(game, 2)
    saved = {r.user_id for r in game.saved[0][1]}
    assert saved.isdisjoint(out) and {7, 8} <= saved and 1 in saved


@pytest.mark.asyncio
async def test_the_saved_name_is_the_display_name_at_the_rounds_end():
    game = make_game()
    conns = await playing(game, (1, 2))
    conns[0].ctx.author.display_name = "Renamed"
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == 0
    await run_for(game, 2)
    assert game.saved[0][1][0].name == "Renamed"


@pytest.mark.asyncio
async def test_a_person_swapped_in_from_the_line_shows_their_hat():
    game = make_game()
    await full_ice(game, (7, 8))
    game.match.set_looks(7, {"hat": "crown", "trail": "flames"})
    await finish(game, [3, 1, 5, 2, 4])
    seat = game.match.seats[3]
    assert seat.user_id == 7 and seat.looks == {"hat": "crown", "trail": "flames"}
    assert game.match.state()["state"]["seats"][3]["looks"] == {"hat": "crown", "trail": "flames"}


# ---------- Play counts ----------


def last_one_standing(game, winner):
    for number, p in enumerate(game.match.round.penguins):
        p.alive = number == winner


@pytest.mark.asyncio
async def test_a_round_alone_against_cpus_is_reported_as_played():
    game = make_game()
    await finish_round(game, (1,), winner=0)
    assert game.played == [[Played(user_id=1, won=True, knockouts=3, fish=0, seal=0, bounce=0, people=1)]]
    # The leaderboard still needs two people
    assert game.saved == []


@pytest.mark.asyncio
async def test_everyone_who_played_gets_their_own_round_numbers():
    game = make_game()
    await playing(game, (1, 2))
    board = game.match.round
    board.knocked[0], board.tally["fish"][0], board.tally["bounce"][0], board.tally["seal"][1] = 3, 2, 1, 4
    last_one_standing(game, 0)
    await run_for(game, 2)
    assert game.played == [
        [
            Played(user_id=1, won=True, knockouts=3, fish=2, seal=0, bounce=1, people=2),
            Played(user_id=2, won=False, knockouts=0, fish=0, seal=4, bounce=0, people=2),
        ]
    ]


@pytest.mark.asyncio
async def test_a_seat_a_cpu_took_over_is_not_reported_and_still_counts_as_a_person_who_started():
    game = make_game()
    conns = await playing(game, (1, 2, 3))
    leave(game, conns[1])
    game.clock.now += GRACE_SECONDS + 1
    await game.match.tick()
    assert game.match.seats[1].cpu is not None
    last_one_standing(game, 1)
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    (people,) = game.played
    assert [p.user_id for p in people] == [1, 3] and not any(p.won for p in people)
    assert [p.people for p in people] == [3, 3]


@pytest.mark.asyncio
async def test_a_round_without_a_winner_is_played_and_nobody_won():
    game = make_game()
    await playing(game, (1, 2))
    last_one_standing(game, None)
    await run_for(game, 2)
    assert game.match.stage == RESULTS
    assert [(p.user_id, p.won) for p in game.played[0]] == [(1, False), (2, False)]


@pytest.mark.asyncio
async def test_telling_one_person_reaches_each_of_their_devices_and_nobody_else():
    game = make_game()
    phone, laptop, other = await arrive(game, 1), await arrive(game, 1), await arrive(game, 2)
    await game.match.tell(1, {"unlocked": ["Monocle"]})
    assert phone.sent[-1] == laptop.sent[-1] == {"unlocked": ["Monocle"]}
    assert {"unlocked": ["Monocle"]} not in other.sent
