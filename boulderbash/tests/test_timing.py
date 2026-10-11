"""Busy times worked out by hand from the original's motion rules (mechanics.md sections 1.3 and 5).

Ticks count from the tap: tick 1 scores the group, then the smash sweeps one column a tick, falls finish, the
after-effects take a tick, and the move check takes one more before the board is idle again.
"""

import pytest

from boulderbash.common.rules import EXTREME, NORMAL, NORMAL2, RAIN_STEP_MS, TICK_MS
from boulderbash.common.timing import (
    chunk_ticks,
    level_end_ms,
    level_start_ms,
    move_ticks,
    rain_in_steps,
    shuffle_ticks,
    undo_ticks,
)

FULL = {(row, col) for row in range(12) for col in range(14)}
ZOOM0 = dict(rows=12, cols=14, tile_w=48, tile_h=32, top=96)


def test_a_one_row_fall_on_a_full_board():
    # The top block of each column hops at -12 px a tick and needs 16 ticks to fall 32 px. Column 1's lands on
    # tick 18, after the sweep ends on tick 15. Then the after-effects (19) and the move check (20)
    ticks = move_ticks(FULL, [(11, 0), (11, 1)], 0, False, [], False, extreme=False, **ZOOM0)
    assert ticks.busy == 20


def test_a_single_block_falling_one_row_lands_eight_ticks_after_its_smash():
    # The block above column 0's smash hops at -2 and lands 8 ticks later, on tick 9; column 1's on tick 10.
    # Both land inside the sweep, so the first wait tick (16) finds nothing moving
    before = {(10, 0), (11, 0), (10, 1), (11, 1)}
    ticks = move_ticks(before, [(11, 0), (11, 1)], 0, False, [], False, extreme=False, **ZOOM0)
    assert ticks.busy == 18
    extreme = move_ticks(before, [(11, 0), (11, 1)], 0, False, [], False, extreme=True, **ZOOM0)
    assert extreme.busy == 17 and extreme.pause == 17


def test_an_eleven_row_fall():
    # Smashed bottom-up, the last smash sits right under the survivor, so it hops at -2 and needs 21 ticks to
    # fall 352 px: it lands on tick 22
    bottom_up = [(row, 0) for row in range(11, 0, -1)]
    assert move_ticks(FULL, bottom_up, 0, False, [], False, extreme=False, **ZOOM0).busy == 24
    # Smashed top-down, the last smash has ten doomed blocks above it, so the survivor hops at -12: 27 ticks
    top_down = [(row, 0) for row in range(1, 12)]
    assert move_ticks(FULL, top_down, 0, False, [], False, extreme=False, **ZOOM0).busy == 30


def test_a_three_column_slide():
    # Three columns each slide 144 px, one starting a tick, and each takes 9 ticks: the last lands on tick 25
    bottom = {(11, col) for col in range(14)}
    kills = [(11, 3), (11, 4), (11, 5)]
    slides = [(2, 5), (1, 4), (0, 3)]
    assert move_ticks(bottom, kills, 3, False, slides, True, extreme=False, **ZOOM0).busy == 26
    # Extreme goes back to play as soon as the last column starts moving, without waiting for it to land
    extreme = move_ticks(bottom, kills, 3, False, slides, True, extreme=True, **ZOOM0)
    assert extreme.busy == 18


def test_a_refill_adds_a_column_a_tick_and_its_falls():
    before = {(11, col) for col in range(14)} | {(10, 0)}
    plain = move_ticks(before, [(11, 1), (11, 2)], 1, False, [], False, extreme=False, **ZOOM0)
    refill = move_ticks(before, [(11, 1), (11, 2)], 1, True, [], False, extreme=False, **ZOOM0)
    assert refill.busy >= plain.busy + 14 + 1


def test_an_empty_column_takes_the_collapse_states_even_when_nothing_slides():
    # The original enters its column-collapse states whenever any column is empty. Extreme then goes straight
    # back to play on the next tick and skips the row-timer pause; Normal also waits a tick and checks
    before = {(10, 12), (10, 13), (11, 12), (11, 13)}
    kills = [(10, 12), (10, 13)]
    extreme = move_ticks(before, kills, 12, False, [], True, extreme=True, **ZOOM0)
    assert extreme.busy == 6 and extreme.pause == 0
    assert move_ticks(before, kills, 12, False, [], True, extreme=False, **ZOOM0).busy == 8


@pytest.mark.parametrize(
    "rows, cols, top, tile_h, first_row, steps",
    [
        (12, 14, 96, 32, 0, 93),
        (13, 15, 103, 29, 0, 100),
        (14, 16, 88, 28, 0, 107),
        (16, 18, 96, 24, 0, 121),
        (12, 6, 96, 32, 0, 61),
        (12, 14, 96, 32, 6, 81),
    ],
)
def test_the_rain_in_for_each_grid_size(rows, cols, top, tile_h, first_row, steps):
    # Rows start 3 steps apart, columns 4 apart, and the last column's top block lands last
    assert rain_in_steps(rows, cols, top, tile_h, first_row) == steps


def test_a_level_becomes_playable_after_its_rain_in():
    timers, playable = level_start_ms(NORMAL, 1)
    assert timers == pytest.approx(3 * TICK_MS + 92 * RAIN_STEP_MS)
    assert playable == pytest.approx(timers + TICK_MS)
    timers, playable = level_start_ms(EXTREME, 1)
    assert playable == timers == pytest.approx(3 * TICK_MS + 80 * RAIN_STEP_MS)
    assert level_start_ms(NORMAL2, 1)[0] == pytest.approx(3 * TICK_MS + 60 * RAIN_STEP_MS)


def test_undo_takes_70_frames_at_two_ticks_each():
    # Frames 2 to 70, then the wait for landed blocks and the move check
    assert undo_ticks() == 138


def test_shuffle_lasts_the_longer_of_its_walk_and_the_flyer():
    assert shuffle_ticks(168) == 170
    assert shuffle_ticks(20) == 167


def test_chunks_from_higher_blocks_fly_longer():
    assert chunk_ticks(96) > chunk_ticks(448) > 0
    ticks = move_ticks(FULL, [(0, 0), (0, 1)], 0, False, [], False, extreme=False, **ZOOM0)
    assert ticks.debris > 0


def test_the_level_end_clears_a_row_every_25_ms_after_the_chunks_land():
    assert level_end_ms(12, 0) == pytest.approx(TICK_MS + 12 * 25)
    assert level_end_ms(12, 5) == pytest.approx(6 * TICK_MS + 12 * 25)
