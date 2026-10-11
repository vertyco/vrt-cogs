"""Random play through every mode until the game ends, checking the board never breaks or gets stuck"""

import random

import pytest

from boulderbash.common.board import Board
from boulderbash.common.rules import (
    BOMB,
    EXTREME,
    EXTREME2,
    LAST_LEVEL,
    MAX_COLORS,
    MODES,
    NORMAL,
    SHUFFLE,
    TICK_MS,
    TWO_BOARDS,
    UNDO,
    WILD,
    ZEN,
)
from boulderbash.common.timing import board_ticks


def playable(board: Board) -> list[tuple[int, int]]:
    """Cells a tap would do something with: Bombs and blocks in a group of 2 or more"""
    # A colored block is in a group of 2 or more exactly when a neighbor shares its color or is Wild
    cells = []
    for row, col, cell in board.cells():
        if cell.special == BOMB:
            cells.append((row, col))
        elif cell.color < MAX_COLORS:
            for r, c in ((row, col - 1), (row, col + 1), (row - 1, col), (row + 1, col)):
                other = board.grid[r][c] if 0 <= r < board.rows and 0 <= c < board.cols else None
                if other is not None and (other.color == cell.color or other.special == WILD):
                    cells.append((row, col))
                    break
    return cells


def check(board: Board) -> None:
    for col in range(board.cols):
        stack = [board.grid[row][col] is not None for row in range(board.rows)]
        assert stack == sorted(stack), f"a block floats in column {col}"
    empty = [not any(board.grid[row][col] for row in range(board.rows)) for col in range(board.cols)]
    packed = sorted(empty, reverse=board.side == 0)
    assert empty == packed, "an empty column was left between stacks"
    if not board.extreme and not board.level_over:
        assert board.has_move() and playable(board), "the level kept going with no move"


class Player:
    def __init__(self, mode: int, seed: int):
        self.mode = mode
        self.rng = random.Random(seed)
        sides = 2 if mode in TWO_BOARDS else 1
        self.boards = [Board(mode, side, random.Random(seed * 7 + side)) for side in range(sides)]
        self.done = [False] * sides
        self.undo = self.shuffle = self.ready = False
        self.last: Board | None = None
        self.clock = 0.0
        for board in self.boards:
            board.start_level()
            board.start_timers(self.clock)

    def over(self) -> bool:
        if self.mode in (EXTREME, EXTREME2):
            return any(board.over for board in self.boards)
        return all(self.done)

    def finish_level(self, index: int) -> None:
        board = self.boards[index]
        if board.level_score < board.goal or board.level >= LAST_LEVEL:
            self.done[index] = True
            if self.mode in (NORMAL, ZEN):
                self.done = [True]
            return
        if len(self.boards) == 1:
            board.level_bonus()
        board.start_level()
        board.start_timers(self.clock)

    def tap(self, board: Board) -> None:
        cells = playable(board)
        row, col = self.rng.choice(cells) if cells else (0, 0)
        if board.grid[row][col] is None:
            return
        tap = board.tap(row, col)
        if tap.kind == "select" and self.rng.random() < 0.85:
            tap = board.tap(*self.rng.choice(tap.cells))
        if tap.kind != "smash":
            return
        move = tap.move
        ticks = board_ticks(board, move)
        assert ticks.busy > 0
        self.clock += ticks.busy * TICK_MS
        self.last = board
        self.undo = self.undo or UNDO in move.pickups
        self.shuffle = self.shuffle or SHUFFLE in move.pickups
        self.ready = move.plain
        if board.extreme:
            board.speed_up()
            if board.clear_bonus():
                board.rise()

    def step(self) -> None:
        live = [index for index, done in enumerate(self.done) if not done]
        index = self.rng.choice(live)
        board = self.boards[index]
        roll = self.rng.random()
        if board.extreme and roll < 0.3:
            board.rise()
        elif roll < 0.35:
            self.clock += self.rng.choice([500, 3000, 7000])
            board.fire(self.clock)
        elif roll < 0.4 and self.undo and self.ready and self.last is not None:
            if self.last.undo():
                self.undo = self.ready = False
        elif roll < 0.43 and self.shuffle and self.last is board:
            board.shuffle()
            self.shuffle = self.ready = False
        else:
            self.tap(board)
        for board in self.boards:
            check(board)
        for index, board in enumerate(self.boards):
            if not self.done[index] and not board.extreme and board.level_over:
                self.finish_level(index)


@pytest.mark.parametrize("mode", MODES)
def test_random_play_reaches_game_over_without_breaking(mode):
    for seed in range(10):
        player = Player(mode, seed)
        for _ in range(20_000):
            if player.over():
                break
            player.step()
        assert player.over(), f"seed {seed} never ended"
