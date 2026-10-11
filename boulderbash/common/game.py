"""
One player's Boulder Bash game: the mode, one or two boards, levels, popups, the Undo and Shuffle slots, the
timers and game over.

Time is in milliseconds on a clock the caller passes in, so tests drive it directly. Every call returns the
messages for the player's page. The game never runs a move's animation: each board is busy until its idle time,
worked out by timing.py, and taps before then are thrown away, as the original threw them away.
"""

import math
import random

from .board import Board, Move
from .rules import (
    EXTREME,
    LAST_LEVEL,
    SHUFFLE,
    TICK_MS,
    TWO_BOARDS,
    UNDO,
    UNDO_REWIND_FRAME,
    ZEN,
    row_gap_ms,
)
from .timing import (
    board_ticks,
    level_end_ms,
    level_start_ms,
    overflow_end_ms,
    shuffle_ticks,
    undo_frame_tick,
    undo_ticks,
)

# Past Extreme's tenth speed-up the row gap goes below zero, and the original raised a row every second tick
FASTEST_ROWS_MS = 2 * TICK_MS

PLAY = "play"
POPUP = "popup"
OVER = "over"
# A board's phase: taking taps (once idle), clearing at a level's end, or finished or frozen
ENDING = "ending"
DONE = "done"


class Game:
    def __init__(self, mode: int, rng: random.Random, now: float):
        self.mode = mode
        sides = 2 if mode in TWO_BOARDS else 1
        self.boards = [Board(mode, side, rng) for side in range(sides)]
        # When each board next takes taps: after its rain-in, or after the move it is animating
        self.idle_at = [0.0] * sides
        self.phase = [PLAY] * sides
        self.end_at: list[float | None] = [None] * sides
        # When a level's end starts clearing rows, once the last chunks from its board have landed
        self.clear_at: list[float | None] = [None] * sides
        # When the chunks from each board's last smash finish flying. Play keeps them moving, and a level's end
        # waits for them (Level:2581-2588)
        self.debris_until = [0.0] * sides
        self.row_due: list[float | None] = [None] * sides
        self.state = PLAY
        self.popup: dict | None = None
        self.undo = "empty"
        self.shuffle = "empty"
        # The board the slots act on: the last one smashed on. None before the first move (Game:281-329)
        self.last: int | None = None
        for side in range(sides):
            self.begin_level(side, now)

    @property
    def score(self) -> int:
        return sum(board.score for board in self.boards)

    @property
    def slots(self) -> dict:
        return {"undo": self.undo, "shuffle": self.shuffle}

    # Levels

    def begin_level(self, side: int, now: float) -> None:
        board = self.boards[side]
        board.start_level()
        timers, playable = level_start_ms(self.mode, board.level)
        board.start_timers(now + timers)
        self.idle_at[side] = now + playable
        self.phase[side] = PLAY
        self.end_at[side] = None
        if board.extreme:
            self.row_due[side] = now + playable + row_gap_ms(board.level)
        else:
            # The original checks for a move as soon as the blocks land, so a dead start ends the level at once
            board.level_over = not board.has_move()
            self.check_end(side, self.idle_at[side])

    def debris_left(self, side: int, at: float) -> int:
        return max(0, math.ceil((self.debris_until[side] - at) / TICK_MS))

    def check_end(self, side: int, at: float) -> None:
        """Start a level's end once its board has no move left: the rows clear, then it is judged"""
        board = self.boards[side]
        if board.extreme or not board.level_over or self.phase[side] != PLAY:
            return
        debris = self.debris_left(side, at)
        self.phase[side] = ENDING
        self.clear_at[side] = at + (debris + 1) * TICK_MS
        self.end_at[side] = at + level_end_ms(board.rows, debris)

    def clearing(self, side: int, now: float) -> float | None:
        """How long until a board's level-end clear starts, or None when it isn't ending"""
        if self.phase[side] != ENDING or self.clear_at[side] is None:
            return None
        return self.clear_at[side] - now

    def judge(self, side: int, now: float) -> list[dict]:
        """A board's level has ended (Game:248-279, Game:656-701)"""
        board = self.boards[side]
        self.end_at[side] = None
        self.phase[side] = DONE
        if board.extreme:
            if self.mode == EXTREME and board.level_score < board.goal:
                return self.show_popup({"kind": "over", "levelScore": board.level_score})
            return self.game_over()
        passed = board.level_score >= board.goal
        if self.mode in TWO_BOARDS:
            if passed and board.level < LAST_LEVEL:
                self.begin_level(side, now)
                return [{"level": self.view(side, now)}]
            if all(phase == DONE for phase in self.phase):
                return self.game_over()
            return [{"done": {"board": side}}]
        if not passed:
            return self.show_popup({"kind": "over", "levelScore": board.level_score})
        if board.level >= LAST_LEVEL:
            return self.game_over()
        left, bonus = board.level_bonus()
        return self.show_popup({"kind": "level", "left": left, "bonus": bonus, "levelScore": board.level_score})

    def show_popup(self, popup: dict) -> list[dict]:
        self.state = POPUP
        self.popup = {**popup, "score": self.score}
        return [{"popup": self.popup}]

    def game_over(self) -> list[dict]:
        self.state = OVER
        self.popup = None
        return [{"over": {"score": self.score, "mode": self.mode}}]

    # The player's input

    def can_play(self, side: int, now: float) -> bool:
        return self.state == PLAY and self.phase[side] == PLAY and now >= self.idle_at[side]

    def tap(self, side: int, col: int, row: int, now: float) -> list[dict]:
        if not 0 <= side < len(self.boards):
            return []
        board = self.boards[side]
        if self.state != PLAY or self.phase[side] != PLAY or not (0 <= row < board.rows and 0 <= col < board.cols):
            return []
        messages = self.advance(now)
        if not self.can_play(side, now):
            # Thrown away, not saved for later. The page learns the real selection back
            return messages + [self.selection(side)]
        tap = board.tap(row, col)
        if tap.move is None:
            return messages + [self.selection(side)]
        move = tap.move
        ticks = board_ticks(board, move)
        busy = ticks.busy * TICK_MS
        self.idle_at[side] = now + busy
        self.last = side
        if UNDO in move.pickups and self.undo == "empty":
            self.undo = "hold"
        if self.undo != "empty":
            # Undo can't take back a move with a special block in it, so it waits for a plain move
            self.undo = "ready" if move.plain else "hold"
        if SHUFFLE in move.pickups:
            self.shuffle = "ready"
        self.debris_until[side] = now + busy + ticks.debris * TICK_MS
        if board.extreme:
            if not move.gap:
                # The row timer stands still while the move plays, unless it left an empty column (a kept quirk)
                self.row_due[side] += ticks.pause * TICK_MS
            board.speed_up()
        self.check_end(side, now + busy)
        return messages + [{"move": self.move_message(side, move, busy, now)}]

    def selection(self, side: int) -> dict:
        return {"select": {"board": side, "cells": [list(pos) for pos in self.boards[side].selection]}}

    def move_message(self, side: int, move: Move, busy: float, now: float) -> dict:
        return {
            "board": side,
            **move.to_json(),
            "busy": busy,
            "clear": self.clearing(side, now),
            "score": self.score,
            **self.board_numbers(side, now),
            "slots": self.slots,
        }

    def board_numbers(self, side: int, now: float) -> dict:
        board = self.boards[side]
        return {
            "level": board.level,
            "levelScore": board.level_score,
            "goal": board.goal,
            "grid": board.snapshot(),
            "holds": [max(hold, 0) for hold in board.holds],
            "critters": board.critters,
            "timers": self.timers(side, now),
        }

    def use_undo(self, now: float) -> list[dict]:
        side = self.last
        if self.state != PLAY or self.undo != "ready" or side is None:
            return []
        messages = self.advance(now)
        board = self.boards[side]
        # Pressed with nothing to take back, as at a level's start, it does nothing and keeps the charge
        if not self.can_play(side, now) or not board.undo():
            return messages
        self.undo = "empty"
        busy = undo_ticks() * TICK_MS
        board.pause_timers(busy)
        self.idle_at[side] = now + busy
        self.check_end(side, now + busy)
        undo = {
            "board": side,
            "busy": busy,
            # The board is put back on the tick after the creature's frame 25 (Level:2427-2465)
            "rewind": (undo_frame_tick(UNDO_REWIND_FRAME) + 1) * TICK_MS,
            "clear": self.clearing(side, now),
            "score": self.score,
            **self.board_numbers(side, now),
            "slots": self.slots,
        }
        return messages + [{"undo": undo}]

    def use_shuffle(self, now: float) -> list[dict]:
        side = self.last
        if self.state != PLAY or self.shuffle != "ready" or side is None:
            return []
        messages = self.advance(now)
        if not self.can_play(side, now):
            return messages
        board = self.boards[side]
        swaps, walk = board.shuffle()
        self.shuffle = "empty"
        if self.undo != "empty":
            self.undo = "hold"
        busy = shuffle_ticks(walk) * TICK_MS
        board.pause_timers(busy)
        self.idle_at[side] = now + busy
        self.check_end(side, now + busy)
        shuffle = {
            "board": side,
            "swaps": [list(swap) for swap in swaps],
            "busy": busy,
            "clear": self.clearing(side, now),
            **self.board_numbers(side, now),
            "slots": self.slots,
        }
        return messages + [{"shuffle": shuffle}]

    def end(self, now: float) -> list[dict]:
        """The End Game sign: over at once, keeping the score"""
        if self.state == OVER:
            return []
        return self.advance(now) + (self.game_over() if self.state != OVER else [])

    def next(self, now: float) -> list[dict]:
        """Close the popup: on to the next level, or to the game over screen"""
        if self.state != POPUP:
            return []
        popup, self.popup = self.popup, None
        if popup["kind"] == "over":
            return self.game_over()
        self.state = PLAY
        self.begin_level(0, now)
        return [{"level": self.view(0, now)}]

    # Time passing

    def advance(self, now: float) -> list[dict]:
        """Everything due by now, in time order: level ends, Countdowns, Shifters and rising rows"""
        messages: list[dict] = []
        while self.state != OVER:
            found = self.next_event(now)
            if found is None:
                break
            at, side, kind = found
            if kind == "end":
                messages += self.judge(side, at)
            elif kind == "timer":
                messages += self.fire_timer(side, at)
            else:
                messages += self.raise_row(side, at)
        return messages

    def next_event(self, now: float) -> tuple[float, int, str] | None:
        found = []
        for side, board in enumerate(self.boards):
            if self.phase[side] == ENDING and self.end_at[side] <= now:
                found.append((self.end_at[side], side, "end"))
            if self.state != PLAY or self.phase[side] != PLAY:
                continue
            # Timers and rows are checked on the idle board's ticks, and fire on the first tick past their deadline
            idle = self.idle_at[side]
            timer = board.next_timer()
            if timer is not None and max(timer, idle) + TICK_MS <= now:
                found.append((max(timer, idle) + TICK_MS, side, "timer"))
            if board.extreme:
                at = (idle if not board.count() else max(self.row_due[side], idle)) + TICK_MS
                if at <= now:
                    found.append((at, side, "row"))
        return min(found) if found else None

    def fire_timer(self, side: int, at: float) -> list[dict]:
        board = self.boards[side]
        selected = list(board.selection)
        events = board.fire(at)
        if not events:
            # A Shifter that rolled its own color still clears a selection it was in
            return [self.selection(side)] if board.selection != selected else []
        self.check_end(side, at)
        timer = {
            "board": side,
            "events": [event.to_json() for event in events],
            "clear": self.clearing(side, at),
            "selection": [list(pos) for pos in board.selection],
            **self.board_numbers(side, at),
        }
        return [{"timer": timer}]

    def raise_row(self, side: int, at: float) -> list[dict]:
        """Extreme: a row rises when its timer runs out, or at once when the board is emptied (Level:2230-2259)"""
        board = self.boards[side]
        board.speed_up()
        bonus = board.clear_bonus()
        self.row_due[side] = at + max(row_gap_ms(board.level), FASTEST_ROWS_MS)
        rise = board.rise()
        board.speed_up()
        self.idle_at[side] = max(self.idle_at[side], at + TICK_MS)
        end = None
        if rise.overflow:
            self.phase[side] = ENDING
            self.end_at[side] = at + overflow_end_ms(board.rows, self.debris_left(side, at))
            end = self.end_at[side] - at
        message = {
            "board": side,
            **rise.to_json(),
            "bonus": bonus,
            "end": end,
            "score": self.score,
            **self.board_numbers(side, at),
        }
        return [{"rise": message}]

    # What the page needs to draw the whole game

    def view(self, side: int, now: float) -> dict:
        board = self.boards[side]
        due = self.row_due[side]
        return {
            "board": side,
            "rows": board.rows,
            "cols": board.cols,
            "phase": self.phase[side],
            "idle": max(0.0, self.idle_at[side] - now),
            "selection": [list(pos) for pos in board.selection],
            "row": max(0.0, due - now) if board.extreme and due is not None else None,
            **self.board_numbers(side, now),
        }

    def timers(self, side: int, now: float) -> list[list]:
        return [
            [row, col, cell.special, max(0.0, cell.due - now)]
            for row, col, cell in self.boards[side].timed()
            if cell.due is not None
        ]

    def snapshot(self, now: float) -> dict:
        return {
            "mode": self.mode,
            "state": self.state,
            "score": self.score,
            "slots": self.slots,
            "last": self.last,
            "popup": self.popup,
            "boards": [self.view(side, now) for side in range(len(self.boards))],
        }


def payable(mode: int, score: int) -> bool:
    """Zen never scores, so it is never cashed in"""
    return mode != ZEN and score > 0
