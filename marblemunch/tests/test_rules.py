import random

import pytest

from marblemunch.common.rules import (
    DT,
    HOME_DEPTH,
    MARBLE_COUNT,
    MARBLE_RADIUS,
    MAX_REACH,
    MOUTH_RADIUS,
    POOL_MAX,
    POOL_MIN,
    RELEASE_SECONDS,
    ROUND_SECONDS,
    SNAP_COOLDOWN,
    Board,
    Hippo,
    Marble,
    lane_position,
    mouth_position,
)


def steps(thing, seconds):
    for _ in range(round(seconds / DT)):
        thing.step(DT)


def test_each_seat_reaches_straight_out_from_its_own_wall():
    assert mouth_position(0, 250) == (500, 750)
    assert mouth_position(1, 250) == (250, 500)
    assert mouth_position(2, 250) == (500, 250)
    assert mouth_position(3, 250) == (750, 500)
    for seat in range(4):
        assert lane_position(seat, *mouth_position(seat, 320)) == (0, 320)


def test_a_marble_bounces_off_the_walls_and_stays_in_the_pool():
    marble = Marble(0, POOL_MIN + MARBLE_RADIUS + 1, 500.0, -300.0, 0.0)
    marble.move(DT)
    assert marble.vx > 0 and marble.x >= POOL_MIN + MARBLE_RADIUS
    roaming = Marble(1, 500.0, 500.0, 237.0, -191.0)
    for _ in range(3000):
        roaming.move(DT)
        assert POOL_MIN + MARBLE_RADIUS <= roaming.x <= POOL_MAX - MARBLE_RADIUS
        assert POOL_MIN + MARBLE_RADIUS <= roaming.y <= POOL_MAX - MARBLE_RADIUS


def test_marbles_roll_out_of_the_middle_over_the_first_two_seconds():
    board = Board(random.Random(1))
    board.step()
    assert len(board.marbles) == 1
    steps(board, RELEASE_SECONDS)
    assert board.released == MARBLE_COUNT
    assert board.marbles_left == MARBLE_COUNT


def test_holding_stretches_the_neck_at_the_set_speed():
    hippo = Hippo(0)
    hippo.press()
    steps(hippo, 0.3)
    assert hippo.open and hippo.reach == pytest.approx(MAX_REACH / 2, abs=1)


def test_the_mouth_snaps_at_full_reach_and_needs_a_fresh_press():
    hippo = Hippo(0)
    hippo.press()
    snaps = sum(hippo.step(DT) for _ in range(round(2 / DT)))
    assert snaps == 1 and not hippo.open
    # Still held, but pulled back home and waiting for a new press
    assert hippo.reach == 0


def test_letting_go_snaps_the_mouth():
    hippo = Hippo(0)
    hippo.press()
    steps(hippo, 0.2)
    hippo.release()
    assert hippo.step(DT) is True and not hippo.open


def test_a_tap_between_two_updates_still_nibbles():
    hippo = Hippo(0)
    hippo.press()
    hippo.release()
    assert hippo.step(DT) is True


def test_pressing_again_while_open_changes_nothing():
    hippo = Hippo(0)
    hippo.press()
    steps(hippo, 0.1)
    reach = hippo.reach
    hippo.press()
    assert hippo.open and hippo.reach == reach and not hippo.queued


def test_a_press_during_the_wait_opens_the_mouth_once_the_wait_is_over():
    hippo = Hippo(0)
    hippo.press()
    hippo.release()
    hippo.step(DT)
    hippo.press()
    assert not hippo.open and hippo.queued
    steps(hippo, SNAP_COOLDOWN + DT)
    assert hippo.open


def test_a_press_let_go_during_the_wait_is_forgotten():
    hippo = Hippo(0)
    hippo.press()
    hippo.release()
    hippo.step(DT)
    hippo.press()
    hippo.release()
    steps(hippo, SNAP_COOLDOWN + DT)
    assert not hippo.open


def test_a_snap_eats_the_marbles_in_the_mouth():
    board = Board(random.Random(1))
    board.released = MARBLE_COUNT
    x, y = mouth_position(0, HOME_DEPTH + 100)
    board.marbles = [Marble(0, x, y - MOUTH_RADIUS + 5, 0.0, 0.0), Marble(1, x + MOUTH_RADIUS + 5, y, 0.0, 0.0)]
    hippo = board.hippos[0]
    hippo.press()
    steps(board, 0.3)
    hippo.release()
    assert board.step() == [(0, 0)]
    assert hippo.score == 1 and [marble.id for marble in board.marbles] == [1]


def test_the_round_ends_on_the_last_marble_or_the_time_limit():
    board = Board(random.Random(1))
    board.released = MARBLE_COUNT
    board.marbles = []
    assert board.finished
    timed = Board(random.Random(1))
    timed.elapsed = ROUND_SECONDS
    assert timed.finished
    assert not Board(random.Random(1)).finished


def test_a_frame_is_whole_numbers():
    board = Board(random.Random(3))
    steps(board, 1)
    frame = board.frame()
    assert all(isinstance(value, int) for marble in frame["m"] for value in marble)
    assert all(isinstance(value, int) for key in ("r", "o", "s") for value in frame[key])
    assert frame["left"] == MARBLE_COUNT and isinstance(frame["time"], int)


def test_a_snap_eats_marbles_under_the_neck_but_not_beside_it():
    board = Board(random.Random(1))
    board.released = MARBLE_COUNT
    # Between the pool edge and the mouth at home, where the hippo's head and neck cover the marbles
    board.marbles = [
        Marble(0, 500.0 + MOUTH_RADIUS - 5, 1000.0 - (POOL_MIN + MARBLE_RADIUS), 0.0, 0.0),
        Marble(1, 500.0 + MOUTH_RADIUS + 30, 1000.0 - (POOL_MIN + MARBLE_RADIUS), 0.0, 0.0),
    ]
    hippo = board.hippos[0]
    hippo.press()
    hippo.release()
    assert board.step() == [(0, 0)]
    assert [marble.id for marble in board.marbles] == [1]
