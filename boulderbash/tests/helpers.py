"""Build boards from little pictures, so a test reads like the board it sets up.

One token per cell, rows top to bottom: `.` empty, `0`-`8` a color, a color plus a letter for a special block on it
(`1r` is a color-1 Refill), `B` a Bomb, `W` a Wild block, `S` Stone.
"""

import random

from boulderbash.common.board import Board, Cell
from boulderbash.common.rules import (
    BASE,
    BOMB,
    COUNTDOWN,
    HOLD,
    NORMAL,
    REFILL,
    SHIFTER,
    SHUFFLE,
    STONE,
    TRIPLE,
    UNDO,
    WILD,
    WIPE,
    colors_for,
    goal_for,
)

LETTERS = {"r": REFILL, "c": COUNTDOWN, "t": TRIPLE, "w": WIPE, "s": SHIFTER, "u": UNDO, "f": SHUFFLE, "h": HOLD}
NAMES = {value: key for key, value in LETTERS.items()}


def cell_from(token: str) -> Cell | None:
    if token == ".":
        return None
    if token == "B":
        return Cell(BASE, BOMB)
    if token == "W":
        return Cell(BASE, WILD)
    if token == "S":
        return Cell(STONE)
    return Cell(int(token[0]), LETTERS[token[1]] if len(token) > 1 else 0)


def token(cell: Cell | None) -> str:
    if cell is None:
        return "."
    if cell.special == BOMB:
        return "B"
    if cell.special == WILD:
        return "W"
    if cell.color == STONE:
        return "S"
    return str(cell.color) + NAMES.get(cell.special, "")


def board_from(text: str, mode: int = NORMAL, level: int = 1, side: int = 0, seed: int = 1) -> Board:
    board = Board(mode, side, random.Random(seed))
    board.level = level
    board.colors = colors_for(mode, level)
    board.goal = goal_for(mode, level)
    board.load([[cell_from(part) for part in line.split()] for line in text.strip().splitlines()])
    return board


def picture(board: Board) -> str:
    return "\n".join(" ".join(token(cell) for cell in row) for row in board.grid)


def tidy(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.strip().splitlines())
