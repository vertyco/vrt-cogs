import random

import pytest

from boulderbash.common.game import Game
from boulderbash.common.rules import (
    EXTREME,
    EXTREME2,
    NORMAL,
    NORMAL2,
    TICK_MS,
    ZEN,
    row_gap_ms,
)
from boulderbash.common.timing import level_start_ms, undo_ticks

from .helpers import cell_from, picture


def load(game: Game, side: int, text: str) -> None:
    game.boards[side].load([[cell_from(part) for part in line.split()] for line in text.strip().splitlines()])


def ready(mode: int, *pictures: str, seed: int = 1) -> Game:
    """A game whose boards hold these pictures and take taps at time 0"""
    game = Game(mode, random.Random(seed), 0)
    for side, text in enumerate(pictures):
        load(game, side, text)
        game.idle_at[side] = 0
        game.boards[side].start_timers(0)
    return game


def kinds(messages: list[dict]) -> list[str]:
    return [next(iter(message)) for message in messages]


def smash(game: Game, side: int, col: int, row: int, now: float) -> dict:
    """Tap a group (twice, outside Extreme), returning the move message"""
    messages = game.tap(side, col, row, now)
    if not game.boards[side].extreme:
        messages += game.tap(side, col, row, now)
    return next(message["move"] for message in messages if "move" in message)


# Taps


def test_a_new_level_takes_no_taps_until_the_blocks_have_rained_in():
    game = Game(NORMAL, random.Random(1), 0)
    before = picture(game.boards[0])
    _, playable = level_start_ms(NORMAL, 1)
    for col in range(14):
        game.tap(0, col, 11, playable - 1)
    assert picture(game.boards[0]) == before and game.boards[0].selection == []
    assert game.snapshot(0)["boards"][0]["idle"] == pytest.approx(playable)


def test_select_then_confirm_then_taps_while_busy_are_ignored():
    game = ready(NORMAL, "1 1 2 2 3")
    assert game.tap(0, 0, 0, 0) == [{"select": {"board": 0, "cells": [[0, 0], [0, 1]]}}]
    move = game.tap(0, 0, 0, 0)[-1]["move"]
    assert move["points"] == 2 and move["score"] == 2
    busy = move["busy"]
    assert busy > 0
    assert game.tap(0, 2, 0, busy / 2) == [{"select": {"board": 0, "cells": []}}]
    assert game.boards[0].selection == []
    assert kinds(game.tap(0, 2, 0, busy + 1)) == ["select"]
    assert game.boards[0].selection == [(0, 2), (0, 3)]


def test_taps_off_the_board_are_ignored():
    game = ready(NORMAL, "1 1 2")
    assert game.tap(0, 3, 0, 0) == []
    assert game.tap(1, 0, 0, 0) == []
    assert game.tap(0, 0, 1, 0) == []


# Levels and popups


def test_a_passed_level_shows_the_level_complete_popup_and_pays_the_bonus():
    game = ready(NORMAL, "1 1 2 3")
    game.boards[0].level_score = 100
    move = smash(game, 0, 0, 0, 0)
    assert move["clear"] > move["busy"]
    assert game.advance(move["busy"]) == []
    messages = game.advance(10_000)
    popup = messages[-1]["popup"]
    assert popup == {"kind": "level", "left": 2, "bonus": 80, "levelScore": 102, "score": 82}
    assert game.state == "popup" and game.score == 82
    assert game.tap(0, 0, 0, 10_000) == []
    messages = game.next(10_000)
    assert kinds(messages) == ["level"]
    assert game.boards[0].level == 2 and game.state == "play"


def test_a_failed_level_shows_game_over_then_ends_the_game():
    game = ready(NORMAL, "1 1 2 3")
    move = smash(game, 0, 0, 0, 0)
    assert game.advance(move["busy"] + 2000)[-1]["popup"]["kind"] == "over"
    messages = game.next(5000)
    assert messages == [{"over": {"score": 2, "mode": NORMAL}}]
    assert game.state == "over"


def test_zen_passes_every_level_and_its_bonus_is_worth_nothing():
    game = ready(ZEN, "1 1 2 3")
    smash(game, 0, 0, 0, 0)
    popup = game.advance(10_000)[-1]["popup"]
    assert popup["kind"] == "level" and popup["bonus"] == 80 and popup["score"] == 0
    assert game.score == 0


def test_level_10_ends_the_game_with_no_popup_and_no_bonus():
    game = ready(NORMAL, "1 1 2 3")
    game.boards[0].level, game.boards[0].goal = 10, 280
    game.boards[0].level_score = 300
    smash(game, 0, 0, 0, 0)
    messages = game.advance(10_000)
    assert kinds(messages) == ["over"]
    assert game.score == 2


def test_a_level_that_starts_with_no_move_ends_at_once():
    game = ready(NORMAL, "1 2 3 4")
    game.boards[0].level_over = True
    game.check_end(0, 0)
    assert kinds(game.advance(10_000)) == ["popup"]


# Two boards


def test_normal_x2_a_failed_board_freezes_while_the_other_plays_on():
    game = ready(NORMAL2, "1 1 2 3", "4 4 5 5 6 6")
    smash(game, 0, 0, 0, 0)
    messages = game.advance(10_000)
    assert messages == [{"done": {"board": 0}}]
    assert game.state == "play"
    assert game.tap(0, 2, 0, 10_000) == []
    move = smash(game, 1, 0, 0, 10_000)
    assert move["board"] == 1 and move["clear"] is None


def test_normal_x2_a_passed_board_starts_its_next_level_at_once_and_the_game_ends_when_both_are_done():
    game = ready(NORMAL2, "1 1 2 3", "4 4 5 6")
    game.boards[0].level_score = 40
    smash(game, 0, 0, 0, 0)
    smash(game, 1, 0, 0, 0)
    messages = game.advance(10_000)
    assert kinds(messages) == ["level", "done"]
    assert game.boards[0].level == 2 and game.state == "play"
    game.end(20_000)
    assert game.state == "over"


def test_extreme_x2_ends_as_soon_as_either_board_overflows():
    game = ready(EXTREME2, "1 2\n3 4", "1 .\n2 3")
    game.row_due = [100_000, 1000]
    messages = game.advance(1000 + TICK_MS)
    assert kinds(messages) == ["rise"] and messages[0]["rise"]["overflow"] == [0]
    assert game.state == "play"
    messages = game.advance(5000)
    assert kinds(messages) == ["over"]


def test_the_slots_act_on_the_board_last_moved_on():
    game = ready(NORMAL2, "1u 1 2 2 3 3", "4 4 5 5 6 6")
    assert kinds(game.use_undo(0)) == []
    smash(game, 0, 0, 0, 0)
    assert game.undo == "hold"
    move = smash(game, 0, 2, 0, 10_000)
    assert game.undo == "ready" and game.last == 0
    smash(game, 1, 0, 0, 10_000)
    assert game.last == 1
    messages = game.use_undo(20_000)
    assert kinds(messages) == ["undo"] and messages[0]["undo"]["board"] == 1
    assert picture(game.boards[1]) == "4 4 5 5 6 6"
    assert move["slots"] == {"undo": "ready", "shuffle": "empty"}


# Extreme rows


def test_extreme_rows_rise_on_their_timer_and_a_move_pauses_it():
    game = Game(EXTREME, random.Random(3), 0)
    _, playable = level_start_ms(EXTREME, 1)
    assert game.row_due[0] == pytest.approx(playable + row_gap_ms(1))
    load(game, 0, ". . .\n3 4 5\n1 1 2")
    game.idle_at[0] = 0
    game.row_due[0] = 5000
    smash(game, 0, 0, 2, 1000)
    paused = game.row_due[0]
    assert paused > 5000
    assert game.advance(paused) == []
    messages = game.advance(paused + TICK_MS)
    assert kinds(messages) == ["rise"]
    assert game.row_due[0] == pytest.approx(paused + TICK_MS + row_gap_ms(1))


def test_a_move_that_leaves_an_empty_column_does_not_pause_the_row_timer():
    game = ready(EXTREME, ". . .\n. . 3\n1 1 2")
    game.row_due = [5000]
    smash(game, 0, 0, 2, 1000)
    assert game.row_due == [5000]


def test_clearing_an_extreme_board_pays_its_bonus_and_raises_a_row_at_once():
    game = ready(EXTREME, ". .\n1 1")
    game.row_due = [100_000]
    move = smash(game, 0, 0, 1, 0)
    messages = game.advance(move["busy"] + TICK_MS)
    rise = messages[-1]["rise"]
    assert rise["bonus"] == 50 and rise["score"] == 52
    assert game.row_due[0] == pytest.approx(move["busy"] + TICK_MS + row_gap_ms(1))


def test_a_speed_up_resets_the_level_score_and_shortens_the_rows():
    game = ready(EXTREME, ". . 2\n1 1 2")
    game.row_due = [100_000]
    game.boards[0].level_score = 149
    move = smash(game, 0, 0, 1, 0)
    assert move["level"] == 2 and move["levelScore"] == 0


# Undo, Shuffle, timers


def test_undo_takes_the_move_back_after_its_animation_and_spends_the_charge():
    game = ready(NORMAL, "1u 1 2 2 3 3 4 4")
    smash(game, 0, 0, 0, 0)
    assert game.undo == "hold" and kinds(game.use_undo(5000)) == []
    smash(game, 0, 2, 0, 5000)
    assert game.undo == "ready"
    messages = game.use_undo(10_000)
    undo = messages[0]["undo"]
    assert undo["busy"] == pytest.approx(undo_ticks() * TICK_MS)
    assert undo["score"] == 2 and game.undo == "empty"
    assert picture(game.boards[0]).startswith(". . 2 2")


def test_shuffle_spends_its_charge_and_puts_undo_on_hold():
    game = ready(NORMAL, "1u 1 2f 2 3 3 4 4 5 5")
    smash(game, 0, 0, 0, 0)
    smash(game, 0, 2, 0, 5000)
    smash(game, 0, 4, 0, 10_000)
    assert game.undo == "ready" and game.shuffle == "ready"
    messages = game.use_shuffle(15_000)
    assert kinds(messages) == ["shuffle"]
    assert game.shuffle == "empty" and game.undo == "hold"


def test_a_countdown_due_while_busy_fires_once_the_board_is_idle():
    game = ready(NORMAL, "1c 2 2 3 3 4 4")
    move = smash(game, 0, 1, 0, 15_900)
    messages = game.advance(16_000)
    assert messages == []
    assert game.advance(15_900 + move["busy"]) == []
    messages = game.advance(15_900 + move["busy"] + TICK_MS)
    assert kinds(messages) == ["timer"] and messages[0]["timer"]["events"][0]["kind"] == "stone"


# Ending


def test_end_game_ends_at_once_and_keeps_the_score():
    game = ready(NORMAL, "1 1 2 2 3")
    smash(game, 0, 0, 0, 0)
    assert game.end(1) == [{"over": {"score": 2, "mode": NORMAL}}]
    assert game.end(2) == []
    assert game.tap(0, 2, 0, 10_000) == []


def test_extreme_overflow_shows_game_over_first():
    game = ready(EXTREME, "1 2\n3 4")
    game.row_due = [1000]
    game.advance(1000 + TICK_MS)
    messages = game.advance(10_000)
    assert messages[-1]["popup"]["kind"] == "over"
    assert game.next(10_000) == [{"over": {"score": 0, "mode": EXTREME}}]
