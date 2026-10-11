import random
from collections import Counter

import pytest

from boulderbash.common.rules import (
    EXTREME,
    EXTREME2,
    NORMAL,
    NORMAL2,
    ZEN,
    biased,
    blocks_left_bonus,
    board_origin,
    colors_for,
    goal_for,
    grid_size,
    group_points,
    row_gap_ms,
    zoom_for,
)


def test_groups_of_2_to_20_score_like_the_original():
    expected = [2, 3, 4, 6, 7, 9, 11, 12, 14, 17, 19, 20, 22, 24, 32, 34, 36, 38, 40]
    assert [group_points(n) for n in range(2, 21)] == expected


def test_six_blocks_score_7_because_of_the_float_cut():
    # 6 x 1.2 is 7.1999... in floating point, and the original cuts it down
    assert group_points(6) == 7


def test_the_grid_grows_after_levels_2_5_and_9():
    assert [zoom_for(NORMAL, level) for level in range(1, 11)] == [0, 0, 1, 1, 1, 2, 2, 2, 2, 3]
    assert [zoom_for(EXTREME, level) for level in (1, 5, 11, 20)] == [0, 0, 0, 0]
    assert grid_size(NORMAL, 1) == (12, 14)
    assert grid_size(ZEN, 3) == (13, 15)
    assert grid_size(NORMAL, 6) == (14, 16)
    assert grid_size(NORMAL, 10) == (16, 18)
    assert grid_size(NORMAL2, 1) == (12, 6)
    assert grid_size(NORMAL2, 10) == (16, 8)
    assert grid_size(EXTREME2, 7) == (12, 6)


def test_boards_sit_where_the_original_put_them():
    assert board_origin(NORMAL, 1, 0) == (64, 96)
    assert board_origin(NORMAL, 3, 0) == (70, 103)
    assert board_origin(NORMAL2, 6, 1) == (442, 88)
    assert board_origin(NORMAL2, 10, 0) == (67, 96)
    assert board_origin(NORMAL2, 10, 1) == (437, 96)


def test_colors_per_level():
    assert [colors_for(NORMAL, level) for level in range(1, 11)] == [4, 4, 5, 5, 6, 6, 7, 7, 8, 9]
    assert [colors_for(EXTREME, level) for level in range(1, 13)] == [3, 3, 4, 4, 5, 5, 6, 6, 7, 8, 8, 8]
    assert colors_for(NORMAL2, 9) == 8
    assert colors_for(EXTREME2, 3) == 4


def test_goals_per_mode():
    assert goal_for(ZEN, 5) == 0
    assert [goal_for(NORMAL, level) for level in (1, 2, 10)] == [100, 120, 280]
    assert [goal_for(NORMAL2, level) for level in (1, 2, 10)] == [40, 50, 130]
    assert goal_for(EXTREME, 7) == 150
    assert goal_for(EXTREME2, 1) == 75


def test_blocks_left_bonus_table():
    assert [blocks_left_bonus(n) for n in range(0, 12)] == [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0, 0]


def test_extreme_row_gaps_shrink_400_ms_per_speed_up_with_no_floor():
    assert [row_gap_ms(level) for level in range(1, 11)] == [3700, 3300, 2900, 2500, 2100, 1700, 1300, 900, 500, 100]
    assert row_gap_ms(11) < 0


def test_the_biased_pick_makes_the_two_end_values_half_as_likely():
    rng = random.Random(7)
    rolls = Counter(biased(rng, 0, 3) for _ in range(120_000))
    assert set(rolls) == {0, 1, 2, 3}
    for value, share in ((0, 1 / 6), (1, 1 / 3), (2, 1 / 3), (3, 1 / 6)):
        assert rolls[value] / 120_000 == pytest.approx(share, abs=0.006)


def test_the_one_in_eight_roll_is_exact():
    rng = random.Random(3)
    hits = sum(biased(rng, 0, 8) == 4 for _ in range(160_000))
    assert hits / 160_000 == pytest.approx(1 / 8, abs=0.004)
