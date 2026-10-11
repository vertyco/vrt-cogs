import random
from collections import Counter

import pytest

from boulderbash.common.board import Board
from boulderbash.common.rules import (
    BASE,
    BOMB,
    COUNTDOWN,
    EXTREME,
    EXTREME2,
    HOLD,
    NORMAL,
    NORMAL2,
    SHIFTER,
    SHUFFLE,
    STONE,
    TICK_MS,
    TRIPLE,
    UNDO,
    WILD,
    ZEN,
)

from .helpers import board_from, picture, tidy


# Tapping and groups


def test_a_first_tap_selects_and_a_tap_on_the_selection_smashes_it():
    board = board_from(
        """
        . . .
        1 2 .
        1 1 2
        """
    )
    tap = board.tap(2, 0)
    assert tap.kind == "select"
    assert sorted(tap.cells) == [(1, 0), (2, 0), (2, 1)]
    assert sorted(board.selection) == [(1, 0), (2, 0), (2, 1)]
    tap = board.tap(1, 0)
    assert tap.kind == "smash"
    assert tap.move.points == 3
    assert board.score == 3 and board.level_score == 3
    assert board.selection == []
    assert picture(board) == tidy(
        """
        . . .
        . . .
        . 2 2
        """
    )


def test_tapping_a_different_group_selects_that_one_instead():
    board = board_from("1 1 2 2")
    board.tap(0, 0)
    tap = board.tap(0, 3)
    assert tap.kind == "select"
    assert sorted(board.selection) == [(0, 2), (0, 3)]


def test_a_lone_block_does_nothing_and_clears_the_selection():
    board = board_from("1 1 2 3")
    board.tap(0, 0)
    tap = board.tap(0, 2)
    assert tap.kind == "clear"
    assert board.selection == []
    assert picture(board) == "1 1 2 3"


def test_extreme_smashes_on_the_first_tap():
    board = board_from("1 1 2", mode=EXTREME)
    tap = board.tap(0, 1)
    assert tap.kind == "smash"
    assert picture(board) == ". . 2"


def test_the_flood_fill_carries_the_tapped_color_through_a_wild_block():
    board = board_from("1 W 1 2")
    tap = board.tap(0, 0)
    assert sorted(tap.cells) == [(0, 0), (0, 1), (0, 2)]


def test_a_wild_block_does_not_link_two_different_colors():
    board = board_from("1 W 2")
    assert sorted(board.tap(0, 0).cells) == [(0, 0), (0, 1)]
    board.selection = []
    assert sorted(board.tap(0, 2).cells) == [(0, 1), (0, 2)]


def test_diagonals_never_connect():
    board = board_from(
        """
        1 2
        2 1
        """
    )
    assert board.tap(0, 0).kind == "clear"


def test_wild_blocks_and_empty_cells_ignore_taps_and_keep_the_selection():
    board = board_from(
        """
        . 2 2
        1 W 3
        """
    )
    board.tap(0, 1)
    assert board.tap(1, 1).kind == "none"
    assert board.tap(0, 0).kind == "none"
    assert sorted(board.selection) == [(0, 1), (0, 2), (1, 1)]


# Scoring


def test_a_bomb_smashes_its_3x3_for_one_point_without_setting_off_another_bomb():
    board = board_from(
        """
        1 2 3 4
        5 B B 6
        7 S W 8
        """
    )
    tap = board.tap(1, 1)
    assert tap.kind == "smash" and tap.move.bomb
    assert tap.move.points == 1
    assert picture(board) == tidy(
        """
        . . . 4
        . . . 6
        . . . 8
        """
    )


def test_a_bomb_smashes_on_one_tap_even_in_normal_and_clears_the_selection():
    board = board_from(
        """
        3 3 . .
        1 2 B 4
        """
    )
    board.tap(0, 0)
    tap = board.tap(1, 2)
    assert tap.kind == "smash"
    assert board.selection == []


def test_a_triple_triples_the_group_after_the_size_multiplier():
    board = board_from("2 2t 2 2 1", level=3)
    tap = board.tap(0, 0)
    tap = board.tap(0, 0)
    assert tap.move.points == 12


def test_a_color_wipe_smashes_every_block_of_the_color_but_only_the_group_scores():
    board = board_from(
        """
        1 2 1 2
        2 1 2 1
        1w 1 2 3
        """
    )
    board.tap(2, 0)
    tap = board.tap(2, 0)
    assert tap.move.points == 3
    assert sorted(tap.move.wiped) == [(0, 0), (0, 2), (1, 3)]
    assert all(cell is None or cell.color != 1 for row in board.grid for cell in row)


def test_zen_never_scores():
    board = board_from("1 1 1 1 2", mode=ZEN)
    board.tap(0, 0)
    tap = board.tap(0, 0)
    assert tap.move.points == 0 and board.score == 0 and board.level_score == 0


# After a smash


def test_blocks_above_fall_straight_down_keeping_their_order():
    board = board_from(
        """
        3 . .
        4 . .
        1 1 2
        """
    )
    board.tap(2, 0)
    tap = board.tap(2, 0)
    assert tap.move.falls == [(1, 0, 2), (0, 0, 1)]
    # Column 1 emptied, so the column that fell slides right to close the gap
    assert picture(board) == tidy(
        """
        . . .
        . 3 .
        . 4 2
        """
    )


def test_refill_drops_one_block_in_every_column_with_room_before_columns_collapse():
    board = board_from(
        """
        2 . .
        1r 1 3
        """
    )
    board.tap(1, 0)
    tap = board.tap(1, 0)
    move = tap.move
    assert sorted((row, col) for row, col, _ in move.refill) == [(0, 0), (0, 2), (1, 1)]
    assert {color for _, _, color in move.refill} <= {2, 3}
    assert move.slides == []
    assert all(board.grid[1][col] is not None for col in range(3))


def test_refill_with_no_colors_left_uses_one_random_color_for_every_block():
    for seed in range(20):
        board = board_from("1r 1 S", seed=seed)
        board.tap(0, 0)
        move = board.tap(0, 0).move
        colors = {color for _, _, color in move.refill}
        assert len(move.refill) == 2 and len(colors) == 1
        assert colors.pop() in range(board.colors)


def test_a_move_notes_an_empty_column_even_when_nothing_slides():
    board = board_from(". 1 1 2", mode=EXTREME)
    move = board.tap(0, 1).move
    assert move.slides == [] and move.gap


def test_one_board_columns_pack_to_the_right():
    board = board_from("2 1 1 3")
    board.tap(0, 1)
    move = board.tap(0, 1).move
    assert picture(board) == ". . 2 3"
    assert move.slides == [(0, 2)]


def test_the_left_of_two_boards_packs_right_and_the_right_board_packs_left():
    left = board_from("2 1 1 3", mode=NORMAL2, side=0)
    left.tap(0, 1)
    left.tap(0, 1)
    assert picture(left) == ". . 2 3"
    right = board_from("2 1 1 3", mode=NORMAL2, side=1)
    right.tap(0, 1)
    move = right.tap(0, 1).move
    assert picture(right) == "2 3 . ."
    assert move.slides == [(3, 1)]


def test_the_move_check_ends_a_level_when_no_group_is_left():
    board = board_from("1 1 2 3")
    board.tap(0, 0)
    move = board.tap(0, 0).move
    assert move.level_over and board.level_over


# Levels


def test_levels_set_grid_size_colors_and_goal():
    board = Board(NORMAL, 0, random.Random(5))
    board.start_level()
    assert (board.rows, board.cols, board.goal) == (12, 14, 100)
    assert all(cell is not None for row in board.grid for cell in row)
    assert {cell.color for row in board.grid for cell in row} - {BASE} <= set(range(4))
    board.start_level()
    board.start_level()
    assert (board.level, board.rows, board.cols, board.goal) == (3, 13, 15, 140)
    assert {cell.color for row in board.grid for cell in row} - {BASE} <= set(range(5))


def test_extreme_starts_with_the_bottom_six_rows_and_no_special_blocks():
    board = Board(EXTREME, 0, random.Random(5))
    board.start_level()
    assert (board.rows, board.cols, board.goal, board.colors) == (12, 14, 150, 3)
    assert all(cell is None for row in board.grid[:6] for cell in row)
    assert all(cell is not None and cell.special == 0 for row in board.grid[6:] for cell in row)


def test_special_blocks_follow_the_originals_rolls():
    types = Counter()
    for seed in range(400):
        board = Board(NORMAL, 0, random.Random(seed))
        for _ in range(3):
            board.start_level()
            specials = [(row, cell) for row, line in enumerate(board.grid) for cell in line if cell.special]
            kinds = [cell.special for _, cell in specials]
            assert len(kinds) == len(set(kinds)), "each type at most once a level"
            assert len(set(board.used.values())) == len(board.used), "one per color a level"
            assert 0 not in board.used.values(), "never on color 0"
            assert all(row < board.rows - 2 for row, _ in specials), "never in the bottom two rows"
            assert HOLD not in kinds
            assert all(cell.color == BASE for _, cell in specials if cell.special in (BOMB, WILD))
            if board.level < 3:
                assert TRIPLE not in kinds
            types.update(kinds)
    assert types[TRIPLE] > 0 and types[SHUFFLE] > 0
    # Types 2-9 come up about twice as often as Refill, whose roll sits at the end of the range
    assert types[COUNTDOWN] > 1.5 * types[1]


def test_two_board_levels_never_get_a_shuffle():
    for seed in range(300):
        board = Board(NORMAL2, seed % 2, random.Random(seed))
        board.start_level()
        assert all(cell.special != SHUFFLE for row in board.grid for cell in row)


# Extreme


def test_extreme_speeds_up_at_its_goal_and_the_extra_points_are_lost():
    board = board_from("1 1 2", mode=EXTREME)
    board.level_score = 160
    assert board.speed_up()
    assert (board.level, board.level_score, board.colors) == (2, 0, 3)
    board.level_score = 150
    assert board.speed_up()
    assert (board.level, board.colors) == (3, 4)
    assert not board.speed_up()


def test_a_rising_row_lifts_every_column_and_overflows_a_full_one():
    board = board_from(
        """
        . . 2
        . 1 2
        1 2 1
        """,
        mode=EXTREME,
    )
    rise = board.rise()
    assert rise.overflow == [2]
    assert board.over
    assert [col for col, _, _ in rise.new] == [0, 1, 2]
    assert picture(board).splitlines()[:2] == [". 1 2", "1 2 1"]


def test_new_rows_only_get_column_holds_about_one_in_42():
    board = board_from(". . . . . .", mode=EXTREME, seed=11)
    specials = Counter()
    for _ in range(4000):
        for _, _, special in board.rise().new:
            specials[special] += 1
        board.load([[None] * 6])
    assert set(specials) <= {0, HOLD}
    assert specials[HOLD] / sum(specials.values()) == pytest.approx(1 / 42, abs=0.004)


def test_a_column_hold_skips_one_rise_and_belongs_to_the_column():
    board = board_from(
        """
        . . .
        . 3 4
        2 1h 1
        """,
        mode=EXTREME,
    )
    board.tap(2, 2)
    assert board.holds[1] == 1 and board.critters[1]
    rise = board.rise()
    assert rise.held == [1]
    assert board.grid[2][1].color == 3 and board.grid[1][1] is None, "the held column stayed put"
    assert board.holds[1] == 0 and board.critters[1]
    rise = board.rise()
    assert rise.held == []
    assert not board.critters[1]


def test_a_hold_is_lost_when_its_column_empties():
    board = board_from(
        """
        . .
        1h 1
        """,
        mode=EXTREME,
    )
    board.tap(1, 0)
    assert not board.critters[0] and board.holds[0] == -1


def test_clearing_an_extreme_board_pays_the_bonus():
    board = board_from("1 1", mode=EXTREME)
    board.tap(0, 0)
    assert board.clear_bonus() == 50
    assert board.score == 52 and board.level_score == 52
    two = board_from("1 1", mode=EXTREME2)
    two.tap(0, 0)
    assert two.clear_bonus() == 25


# Countdown and Shifter


def test_a_countdown_turns_its_whole_group_to_stone():
    board = board_from(
        """
        2 1 3
        1 1c W
        3 2 3
        """
    )
    board.start_timers(1000)
    assert board.grid[1][1].due == 17_000
    assert board.fire(17_000) == [], "timers fire strictly after their deadline"
    event = board.fire(17_001)[0]
    assert event.kind == "stone"
    assert sorted(event.cells) == [(0, 1), (1, 0), (1, 1), (1, 2)]
    assert picture(board) == tidy(
        """
        2 S 3
        S S S
        3 2 3
        """
    )


def test_smashing_a_countdown_defuses_it():
    board = board_from("1c 1 2")
    board.start_timers(0)
    board.tap(0, 0)
    board.tap(0, 0)
    assert board.next_timer() is None


def test_a_shifter_changes_to_another_color_on_the_board_every_6_seconds():
    board = board_from("1s 2 3 2 3", seed=4)
    board.start_timers(0)
    events = []
    now = 6000
    while not events:
        now += TICK_MS
        events = board.fire(now)
    event = events[0]
    assert event.kind == "shift" and event.color in (2, 3)
    assert board.grid[0][0].color == event.color
    assert board.grid[0][0].due == now + 6000


def test_a_shifter_with_only_its_own_color_left_tries_again_next_tick():
    board = board_from("1s 1 S")
    board.start_timers(0)
    assert board.fire(6001) == []
    assert board.grid[0][0].due == 6001


def test_overdue_timers_fire_in_the_order_their_blocks_were_made():
    # The original walks its timer list in creation order, so a Countdown made first turns a Shifter beside it
    # to Stone before the Shifter's own overdue change can happen
    board = board_from("1c 1s 0 2", seed=5)
    board.start_timers(0)
    board.grid[0][0].serial, board.grid[0][1].serial = 1, 2
    board.grid[0][0].due, board.grid[0][1].due = 16_000, 15_900
    events = board.fire(16_010)
    assert [event.kind for event in events] == ["stone"]
    assert picture(board) == "S S 0 2"


def test_a_selected_shifter_clears_the_selection_even_when_its_roll_fails():
    board = board_from("1s 1 S")
    board.start_timers(0)
    board.tap(0, 0)
    assert board.fire(6001) == []
    assert board.selection == []


def test_a_countdown_clears_the_selection():
    board = board_from("1c 2 2 3")
    board.start_timers(0)
    board.tap(0, 1)
    board.fire(16_001)
    assert board.selection == []


def test_timers_pause_for_undo_and_shuffle():
    board = board_from("1c 2s 2 3")
    board.start_timers(0)
    board.pause_timers(2300)
    assert board.grid[0][0].due == 18_300 and board.grid[0][1].due == 8300


# Undo and Shuffle


def test_undo_puts_back_the_last_move_and_takes_its_points_off():
    board = board_from(
        """
        4 3 . .
        2s 3 . 3
        1 1 2 1
        """
    )
    before = picture(board)
    shifter = board.grid[1][0]
    board.start_timers(0)
    board.tap(2, 0)
    move = board.tap(2, 0).move
    assert move.plain
    assert board.score == 2
    assert board.undo()
    assert picture(board) == before
    assert board.score == 0 and board.level_score == 0
    assert board.grid[1][0] is shifter, "the same Shifter, timer and all, is back in place"
    assert not board.undo(), "only the most recent move"


def test_undo_restores_a_shifter_whose_timer_keeps_working():
    board = board_from(
        """
        2s 3 3
        1 1 4
        """,
        seed=2,
    )
    board.start_timers(0)
    board.tap(1, 0)
    board.tap(1, 0)
    board.undo()
    shifter = board.grid[0][0]
    assert shifter.special == SHIFTER and shifter.due == 6000
    now = 6000
    while not board.fire(now := now + TICK_MS):
        pass
    assert board.grid[0][0].color != 2, "its real color changes, not just its picture"


def test_moves_with_a_special_block_are_not_plain():
    cases = ["1u 1 2", "1 W 2", "1s 1 2", "1r 1 2", "B 1 2"]
    for text in cases:
        board = board_from(text, level=3)
        tap = board.tap(0, 0)
        if tap.kind == "select":
            tap = board.tap(0, 0)
        assert not tap.move.plain, text


def test_smashing_an_undo_or_shuffle_block_picks_it_up():
    board = board_from("1u 1 2 2f")
    board.tap(0, 0)
    assert board.tap(0, 0).move.pickups == [UNDO]
    board.tap(0, 3)
    assert board.tap(0, 3).move.pickups == [SHUFFLE]


def test_undo_does_nothing_before_the_first_move_of_a_level():
    board = Board(NORMAL, 0, random.Random(1))
    board.start_level()
    assert not board.undo()


def test_shuffle_keeps_the_stack_shapes_and_the_blocks():
    board = Board(NORMAL, 0, random.Random(9))
    board.start_level()
    for col in range(0, 14, 3):
        for row in range(0, 5 + col % 4):
            board.grid[row][col] = None
    shape = [[cell is None for cell in row] for row in board.grid]
    blocks = Counter((cell.color, cell.special) for row in board.grid for cell in row if cell)
    swaps, _ = board.shuffle()
    assert swaps
    assert [[cell is None for cell in row] for row in board.grid] == shape
    assert Counter((cell.color, cell.special) for row in board.grid for cell in row if cell) == blocks


def test_the_shuffle_walk_starts_at_the_top_block_of_the_leftmost_column():
    board = board_from(
        """
        . . . 2
        . 1 . 2
        . 1 2 3
        """
    )
    swaps, walk = board.shuffle()
    assert walk == 2 * 4 - 1
    assert swaps[0][:2] == (1, 1)


# Original bugs, fixed


def test_fixed_the_move_check_sees_a_wild_whose_only_partner_is_to_its_right_or_above():
    assert board_from("W 1").has_move()
    assert board_from(
        """
        1
        W
        """
    ).has_move()
    assert not board_from("W S 1 2").has_move()


def test_fixed_the_move_check_sees_a_bomb_in_the_top_right_corner():
    assert board_from(
        """
        1 2 B
        2 1 2
        """
    ).has_move()


def test_fixed_a_countdown_that_leaves_no_moves_ends_the_level():
    board = board_from("1c 1 2 3")
    board.start_timers(0)
    board.fire(16_001)
    assert board.level_over


def test_fixed_a_shifter_that_leaves_no_moves_ends_the_level():
    board = board_from("1s 1 2 S", seed=3)
    board.start_timers(0)
    now = 6000
    while not board.fire(now := now + TICK_MS):
        pass
    assert board.grid[0][0].color == 2
    assert board.level_over


def test_fixed_tapping_stone_clears_the_selection_for_good():
    board = board_from("1 1 S")
    board.tap(0, 0)
    assert board.tap(0, 2).kind == "clear"
    assert board.selection == []


def test_fixed_refill_never_uses_a_color_a_shifter_took_off_the_board():
    for seed in range(30):
        board = board_from("3s 2 1r 1", seed=seed)
        board.start_timers(0)
        now = 6000
        while not board.fire(now := now + TICK_MS):
            pass
        board.tap(0, 2)
        move = board.tap(0, 2).move
        assert board.grid[0][0].color != 3
        assert move.refill and 3 not in {color for _, _, color in move.refill}


def test_fixed_a_wild_turned_to_stone_leaves_the_color_counts_right():
    board = board_from("1c 1 W 2 2")
    board.start_timers(0)
    board.fire(16_001)
    assert board.colors_on_board() == [2]
    assert board.grid[0][2].color == STONE and board.grid[0][2].special == 0
