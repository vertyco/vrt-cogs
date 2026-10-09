import logging
import random
from types import SimpleNamespace

import pytest

from marblemunch.common.leaderboard import Result
from marblemunch.common.match import (
    COUNTDOWN_SECONDS,
    GRACE_SECONDS,
    LOOP_FAILED,
    PLAYING,
    RESULTS,
    RESULTS_SECONDS,
    SEAT_TAKEN,
    STARTING,
    STARTING_SECONDS,
    WAITING,
    Match,
)
from marblemunch.common.rules import DT, MARBLE_COUNT, ROUND_SECONDS, TICK_RATE, Marble
from marblemunch.tests.fakes import Clock, FakeConn, FakeRoom


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


async def arrive(game, user_id):
    conn = FakeConn(game.room, user_id)
    await game.match.join(conn)
    return conn


def leave(game, conn):
    conn.drop()
    game.match.leave(conn)


def last_state(conn):
    return next(message["state"] for message in reversed(conn.sent) if "state" in message)


async def playing(game, user_ids=(1,), seats=(0,)):
    """Seat these players, press Start, and run until the round is under way"""
    conns = []
    for user_id, seat in zip(user_ids, seats):
        conn = await arrive(game, user_id)
        await game.match.message(conn, {"sit": seat})
        conns.append(conn)
    await game.match.message(conns[0], {"start": True})
    await run_ticks(game, 1 + STARTING_SECONDS * TICK_RATE)
    assert game.match.stage == PLAYING
    return conns


def keep_going(board):
    """One marble parked in a corner no hippo can reach, so the round lasts until its time limit"""
    board.marbles = [Marble(0, 150.0, 150.0, 0.0, 0.0)]
    board.released = MARBLE_COUNT


@pytest.mark.asyncio
async def test_everyone_arrives_watching():
    game = make_game()
    conn = await arrive(game, 1)
    state = last_state(conn)
    assert state["stage"] == WAITING
    assert [seat["kind"] for seat in state["seats"]] == ["empty"] * 4
    assert state["watching"] == 1 and state["countdown"] is None


@pytest.mark.asyncio
async def test_tapping_an_empty_hippo_sits_you_and_starts_the_countdown():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 2})
    await game.match.tick()
    state = last_state(conn)
    assert state["seats"][2] == {
        "kind": "human",
        "id": "1",
        "name": "Player 1",
        "avatar": "https://cdn.discordapp.com/avatars/1/a.png",
        "away": False,
    }
    assert state["countdown"] == COUNTDOWN_SECONDS and state["watching"] == 0


@pytest.mark.asyncio
async def test_two_taps_on_one_hippo_seat_the_first_and_tell_the_second():
    game = make_game()
    first, second = await arrive(game, 1), await arrive(game, 2)
    await game.match.message(first, {"sit": 0})
    await game.match.message(second, {"sit": 0})
    assert game.match.seats[0].user_id == 1
    assert second.sent[-1] == {"notice": SEAT_TAKEN}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [{"sit": True}, {"sit": 4}, {"sit": -1}, {"sit": "0"}, {"sit": 0, "x": 1}, "sit", [0], None, {"stand": 1}],
)
async def test_odd_messages_are_ignored(data):
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, data)
    assert all(seat.user_id is None for seat in game.match.seats)
    assert not any("notice" in message for message in conn.sent)


@pytest.mark.asyncio
async def test_one_player_sits_in_one_seat():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    await game.match.message(conn, {"sit": 1})
    assert game.match.seats[0].user_id == 1 and game.match.seats[1].user_id is None


@pytest.mark.asyncio
async def test_standing_up_stops_the_countdown_when_nobody_is_left():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    await run_for(game, 1)
    await game.match.message(conn, {"stand": True})
    await game.match.tick()
    state = last_state(conn)
    assert state["seats"][0]["kind"] == "empty" and state["countdown"] is None


@pytest.mark.asyncio
async def test_start_skips_the_countdown_and_npcs_fill_the_empty_seats():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 1})
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    state = last_state(conn)
    assert state["stage"] == STARTING and state["left"] == STARTING_SECONDS
    assert [seat["kind"] for seat in state["seats"]] == ["npc", "human", "npc", "npc"]
    assert state["seats"][0]["name"] == "Chompy"


@pytest.mark.asyncio
async def test_a_spectator_cannot_press_start():
    game = make_game()
    seated, watcher = await arrive(game, 1), await arrive(game, 2)
    await game.match.message(seated, {"sit": 0})
    await game.match.message(watcher, {"start": True})
    await game.match.tick()
    assert game.match.stage == WAITING


@pytest.mark.asyncio
async def test_the_countdown_runs_out_then_three_two_one_then_play():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    await run_for(game, COUNTDOWN_SECONDS)
    assert game.match.stage == STARTING
    await run_for(game, STARTING_SECONDS)
    assert game.match.stage == PLAYING
    await game.match.tick()
    assert "f" in conn.sent[-1] and len(conn.sent[-1]["r"]) == 4


@pytest.mark.asyncio
async def test_a_seated_player_steers_only_their_own_hippo():
    game = make_game()
    (player,) = await playing(game)
    watcher = await arrive(game, 2)
    await game.match.message(watcher, {"press": True})
    assert not game.match.board.hippos[0].open
    await game.match.message(player, {"press": True})
    assert game.match.board.hippos[0].open
    await game.match.message(player, {"release": True})
    assert not game.match.board.hippos[0].holding


@pytest.mark.asyncio
async def test_presses_before_the_round_starts_are_ignored():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    await game.match.message(conn, {"start": True})
    await game.match.tick()
    await game.match.message(conn, {"press": True})
    assert game.match.stage == STARTING and not game.match.board.hippos[0].open


@pytest.mark.asyncio
async def test_a_dropped_player_keeps_their_seat_and_comes_back_to_it():
    game = make_game()
    (player,) = await playing(game)
    keep_going(game.match.board)
    await game.match.message(player, {"press": True})
    leave(game, player)
    assert not game.match.board.hippos[0].holding
    await run_for(game, GRACE_SECONDS - 1)
    back = await arrive(game, 1)
    seat = game.match.seats[0]
    assert seat.conn is back and seat.dropped_at is None and seat.npc is None
    assert last_state(back)["seats"][0]["kind"] == "human"
    await game.match.message(back, {"press": True})
    assert game.match.board.hippos[0].open


@pytest.mark.asyncio
async def test_after_the_grace_period_an_npc_plays_a_dropped_hippo():
    game = make_game()
    (player,) = await playing(game)
    keep_going(game.match.board)
    game.match.board.hippos[0].score = 5
    leave(game, player)
    await run_for(game, GRACE_SECONDS + 1)
    seat = game.match.seats[0]
    assert seat.npc is not None and seat.user_id is None
    back = await arrive(game, 1)
    assert game.match.seats[0].conn is None
    assert last_state(back)["seats"][0]["kind"] == "npc"
    game.match.board.elapsed = ROUND_SECONDS
    await game.match.tick()
    # The player still gets the round and their marbles, but no win, since an NPC finished it
    assert game.recorded == [[Result(1, "Global 1", 5, False)]]


@pytest.mark.asyncio
async def test_a_second_device_takes_over_and_the_first_leaving_keeps_the_seat():
    game = make_game()
    (phone,) = await playing(game)
    laptop = await arrive(game, 1)
    leave(game, phone)
    seat = game.match.seats[0]
    assert seat.conn is laptop and seat.dropped_at is None


@pytest.mark.asyncio
async def test_the_countdown_waits_while_only_dropped_players_are_seated():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    leave(game, conn)
    await run_for(game, COUNTDOWN_SECONDS + 1)
    assert game.match.stage == WAITING and game.match.countdown is None
    await arrive(game, 1)
    assert game.match.countdown is not None


@pytest.mark.asyncio
async def test_a_finished_round_records_only_humans_and_ties_all_win():
    game = make_game()
    await playing(game, user_ids=(1, 2), seats=(0, 1))
    board = game.match.board
    keep_going(board)
    for hippo, score in zip(board.hippos, (4, 4, 2, 1)):
        hippo.score = score
    board.marbles = []
    await game.match.tick()
    assert game.match.stage == RESULTS and game.match.winners == [0, 1]
    assert game.recorded == [[Result(1, "Global 1", 4, True), Result(2, "Global 2", 4, True)]]


@pytest.mark.asyncio
async def test_an_npc_win_goes_to_nobody():
    game = make_game()
    await playing(game)
    board = game.match.board
    keep_going(board)
    for hippo, score in zip(board.hippos, (2, 5, 0, 0)):
        hippo.score = score
    board.marbles = []
    await game.match.tick()
    assert game.match.winners == [1]
    assert game.recorded == [[Result(1, "Global 1", 2, False)]]


@pytest.mark.asyncio
async def test_a_round_nobody_scores_in_has_no_winner():
    game = make_game()
    await playing(game)
    keep_going(game.match.board)
    game.match.board.elapsed = ROUND_SECONDS
    await game.match.tick()
    assert game.match.stage == RESULTS and game.match.winners == []
    assert game.recorded == [[Result(1, "Global 1", 0, False)]]


@pytest.mark.asyncio
async def test_after_results_the_same_seats_wait_again_without_npcs():
    game = make_game()
    (player,) = await playing(game)
    keep_going(game.match.board)
    game.match.board.elapsed = ROUND_SECONDS
    await game.match.tick()
    await run_for(game, RESULTS_SECONDS)
    state = last_state(player)
    assert state["stage"] == WAITING and state["board"] is None
    assert [seat["kind"] for seat in state["seats"]] == ["human", "empty", "empty", "empty"]
    assert state["countdown"] == COUNTDOWN_SECONDS


@pytest.mark.asyncio
async def test_the_match_stays_alive_while_a_dropped_seat_is_kept():
    game = make_game()
    conn = await arrive(game, 1)
    await game.match.message(conn, {"sit": 0})
    leave(game, conn)
    assert game.match.alive()
    await run_for(game, GRACE_SECONDS + 1)
    assert not game.match.alive()


@pytest.mark.asyncio
async def test_a_failing_update_is_logged_once_and_ends_the_match(monkeypatch, caplog):
    game = make_game()
    conn = await arrive(game, 1)

    async def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(game.match, "tick", broken)
    with caplog.at_level(logging.ERROR):
        await game.match.run()
    assert caplog.text.count("Marble Munch stopped a round") == 1
    assert {"notice": LOOP_FAILED} in conn.sent
    assert game.ended == [game.match]


@pytest.mark.asyncio
async def test_marbles_an_npc_eats_after_taking_over_are_not_credited_to_the_player():
    game = make_game()
    (player,) = await playing(game)
    keep_going(game.match.board)
    game.match.board.hippos[0].score = 3
    leave(game, player)
    await run_for(game, GRACE_SECONDS + 1)
    game.match.board.hippos[0].score = 8
    game.match.board.elapsed = ROUND_SECONDS
    await game.match.tick()
    assert game.recorded == [[Result(1, "Global 1", 3, False)]]


@pytest.mark.asyncio
async def test_the_newer_device_leaving_hands_the_seat_back_to_the_older_one():
    game = make_game()
    (phone,) = await playing(game)
    laptop = await arrive(game, 1)
    leave(game, laptop)
    seat = game.match.seats[0]
    assert seat.conn is phone and seat.dropped_at is None
    await game.match.message(phone, {"press": True})
    assert game.match.board.hippos[0].open
