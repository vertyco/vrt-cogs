"""
One Boulder Bash board: the grid, groups, smashing, falling, Refill, column collapse, special blocks, the move
check, Undo, Shuffle and Extreme's rising rows.

It works out each move's result at once. How long the original spent animating it is timing.py's job. Rows and
columns count from the top-left, as in the original. Randomness comes from the Random passed in, so a seeded board
replays exactly.
"""

import random
import typing as t
from dataclasses import dataclass, field

from .rules import (
    BASE,
    BOMB,
    BOMB_POINTS,
    CLEAR_BONUS,
    COUNTDOWN,
    COUNTDOWN_MS,
    EXTREME_FIRST_ROW,
    EXTREMES,
    HOLD,
    HOLD_ROLL,
    MAX_COLORS,
    MIN_GROUP,
    NUM_SPECIALS,
    REFILL,
    SHIFTER,
    SHIFTER_MS,
    SHUFFLE,
    SPECIAL_ROLL,
    SPECIAL_SAFE_ROWS,
    STONE,
    TRIPLE,
    TRIPLE_MIN_LEVEL,
    TRIPLE_TIMES,
    TWO_BOARDS,
    UNDO,
    WILD,
    WIPE,
    ZEN,
    biased,
    blocks_left_bonus,
    colors_for,
    goal_for,
    grid_size,
    group_points,
)

Pos = tuple[int, int]
# Bomb's 3 x 3, in the order the original collected it (Level:2026-2073)
BLAST = ((-1, 0), (-1, -1), (-1, 1), (0, -1), (0, 1), (1, 0), (1, -1), (1, 1))


class Cell:
    """One block. A cell keeps its identity as it falls, slides and shuffles, so a Shifter's timer goes with it"""

    __slots__ = ("color", "special", "due", "serial")

    def __init__(self, color: int, special: int = 0, serial: int = 0):
        self.color = color
        self.special = special
        # When a Countdown or Shifter next fires, in ms on the game's clock
        self.due: float | None = None
        # Creation order, which breaks ties between timers due at once, as the original's list order did
        self.serial = serial

    def to_json(self) -> list[int]:
        return [self.color, self.special]


@dataclass
class Group:
    """A flood fill's result, plus the special blocks it noted along the way (Level:805-808)"""

    cells: list[Pos]
    color: int
    special: int = 0
    wild: bool = False
    shifter: bool = False

    def note(self, cell: Cell) -> None:
        if cell.special == WILD:
            self.wild = True
        elif cell.special == SHIFTER:
            self.shifter = True
        elif cell.special > 0:
            self.special = cell.special


@dataclass
class Move:
    """Everything one smash did, in the order it happened"""

    tapped: Pos
    color: int
    group: list[Pos]
    points: int
    bomb: bool
    wiped: list[Pos]
    # The group then the Color wipe extras: the order the sweep removes them in, which sets how blocks hop
    kills: list[Pos]
    first: int
    before: set[Pos]
    falls: list[tuple[int, int, int]] = field(default_factory=list)
    refill: list[tuple[int, int, int]] = field(default_factory=list)
    slides: list[tuple[int, int]] = field(default_factory=list)
    # An empty column was left after the smash (and Refill), whether or not anything slid. The original then runs
    # its column-collapse states, which cost a tick or two and skip Extreme's row-timer pause
    gap: bool = False
    held: list[int] = field(default_factory=list)
    pickups: list[int] = field(default_factory=list)
    special: int = 0
    plain: bool = True
    level_over: bool = False

    def to_json(self) -> dict:
        return {
            "tapped": list(self.tapped),
            "color": self.color,
            "group": [list(pos) for pos in self.group],
            "wiped": [list(pos) for pos in self.wiped],
            "kills": [list(pos) for pos in self.kills],
            "first": self.first,
            "points": self.points,
            "bomb": self.bomb,
            "falls": [list(fall) for fall in self.falls],
            "refill": [list(block) for block in self.refill],
            "slides": [list(slide) for slide in self.slides],
            "gap": self.gap,
            "held": self.held,
            "pickups": self.pickups,
            "special": self.special,
        }


@dataclass
class Tap:
    kind: str  # "none", "select", "clear" or "smash"
    cells: list[Pos] = field(default_factory=list)
    move: Move | None = None


@dataclass
class Rise:
    new: list[tuple[int, int, int]]  # (column, color, special) of each new bottom block
    overflow: list[int]
    held: list[int]

    def to_json(self) -> dict:
        return {"new": [list(block) for block in self.new], "overflow": self.overflow, "held": self.held}


@dataclass
class TimerEvent:
    kind: str  # "stone" or "shift"
    cells: list[Pos]
    color: int = 0

    def to_json(self) -> dict:
        return {"kind": self.kind, "cells": [list(pos) for pos in self.cells], "color": self.color}


class Board:
    def __init__(self, mode: int, side: int, rng: random.Random):
        self.mode = mode
        # 1 is the right board of a two-board mode, which packs its columns left
        self.side = side
        self.rng = rng
        self.level = 0
        self.colors = 0
        self.goal = 0
        self.score = 0
        self.level_score = 0
        self.last_points = 0
        self.rows = 0
        self.cols = 0
        self.grid: list[list[Cell | None]] = []
        self.selection: list[Pos] = []
        self.selected = Group([], 0)
        # The last move as ("kill", cell, row, col) and ("move", cell, from row, from col, to row, to col)
        self.record: list[tuple] = []
        # Special block type -> the color it went on, this level (Level:2643-2692)
        self.used: dict[int, int] = {}
        # Extreme's column holds: the original's counts, where above 0 means the column skips the next rise
        self.holds: list[int] = []
        self.critters: list[bool] = []
        self.serial = 0
        self.level_over = False
        self.over = False

    @property
    def extreme(self) -> bool:
        return self.mode in EXTREMES

    def load(self, grid: list[list[Cell | None]]) -> None:
        self.grid = grid
        self.rows, self.cols = len(grid), len(grid[0])
        self.holds = [0] * self.cols
        self.critters = [False] * self.cols

    def new_cell(self, color: int, special: int = 0) -> Cell:
        self.serial += 1
        return Cell(color, special, self.serial)

    def cells(self) -> t.Iterator[tuple[int, int, Cell]]:
        for row, line in enumerate(self.grid):
            for col, cell in enumerate(line):
                if cell is not None:
                    yield row, col, cell

    def occupied(self) -> set[Pos]:
        return {(row, col) for row, col, _ in self.cells()}

    def count(self) -> int:
        return sum(1 for _ in self.cells())

    def colors_on_board(self) -> list[int]:
        """Normal colors with blocks left, counted from the board itself"""
        return sorted({cell.color for _, _, cell in self.cells() if cell.color < MAX_COLORS})

    def snapshot(self) -> list[list[list[int] | None]]:
        return [[cell.to_json() if cell else None for cell in line] for line in self.grid]

    # Levels

    def start_level(self) -> None:
        """Build the next level (Level:680-783). Extreme only ever builds level 1"""
        self.level += 1
        self.colors = colors_for(self.mode, self.level)
        self.goal = goal_for(self.mode, self.level)
        self.level_score = 0
        self.used = {}
        self.selection = []
        self.record = []
        self.level_over = False
        rows, cols = grid_size(self.mode, self.level)
        self.load([[None] * cols for _ in range(rows)])
        self.fill()

    def fill(self) -> None:
        """The starting fill: bottom row first, left to right (Level:2158-2175, Level:1642-1781)"""
        top = EXTREME_FIRST_ROW if self.extreme else 0
        palette = list(range(self.colors))
        roll_max, roll_hit = SPECIAL_ROLL
        for row in range(self.rows - 1, top - 1, -1):
            for col in range(self.cols):
                color = palette[biased(self.rng, 0, len(palette) - 1)]
                special = 0
                if not self.extreme and row < self.rows - SPECIAL_SAFE_ROWS:
                    if biased(self.rng, 0, roll_max) == roll_hit:
                        special = self.roll_special(color)
                if special in (BOMB, WILD):
                    color = BASE
                self.grid[row][col] = self.new_cell(color, special)

    def roll_special(self, color: int) -> int:
        """Level:2643-2692. Color 0 never gets one, a kept quirk: the original's empty slots all read as color 0"""
        if color == 0 or color in self.used.values() or len(self.used) >= NUM_SPECIALS:
            return 0
        kind = 1 + biased(self.rng, 0, NUM_SPECIALS)
        if kind == TRIPLE and self.level < TRIPLE_MIN_LEVEL:
            return 0
        if kind in self.used or kind == HOLD or (kind == SHUFFLE and self.mode in TWO_BOARDS):
            return 0
        self.used[kind] = color
        return kind

    def speed_up(self) -> bool:
        """Extreme: reaching the goal raises the speed-up level and resets the level score (Level:976-1023)"""
        if not self.extreme or self.level_score < self.goal:
            return False
        self.level += 1
        self.level_score = 0
        self.colors = colors_for(self.mode, self.level)
        return True

    def level_bonus(self) -> tuple[int, int]:
        """The blocks-left bonus, added to the score but not the level score. Zen shows it but pays nothing"""
        left = self.count()
        bonus = blocks_left_bonus(left)
        if self.mode != ZEN:
            self.score += bonus
        return left, bonus

    def clear_bonus(self) -> int:
        """Extreme: points for emptying the board (Level:2237-2254)"""
        if not self.extreme or self.count():
            return 0
        bonus = CLEAR_BONUS[self.mode]
        self.score += bonus
        self.level_score += bonus
        return bonus

    # Tapping

    def find_group(self, row: int, col: int) -> Group:
        cell = self.grid[row][col]
        group = Group([(row, col)], cell.color)
        group.note(cell)
        self.flood(row, col, cell.color, group, {(row, col)})
        return group

    def flood(self, row: int, col: int, color: int, group: Group, checked: set[Pos]) -> None:
        """The original's recursive fill: left, right, up, down. A Wild block joins and carries the color on"""
        for r, c in ((row, col - 1), (row, col + 1), (row - 1, col), (row + 1, col)):
            if not (0 <= r < self.rows and 0 <= c < self.cols) or (r, c) in checked:
                continue
            cell = self.grid[r][c]
            if cell is None:
                continue
            checked.add((r, c))
            if cell.color == color or cell.special == WILD:
                group.cells.append((r, c))
                group.note(cell)
                self.flood(r, c, color, group, checked)

    def blast(self, row: int, col: int) -> Group:
        cells = [(row, col)]
        for dr, dc in BLAST:
            r, c = row + dr, col + dc
            if 0 <= r < self.rows and 0 <= c < self.cols and self.grid[r][c] is not None:
                cells.append((r, c))
        return Group(cells, BASE, special=BOMB)

    def tap(self, row: int, col: int) -> Tap:
        """Level:1394-1477, with Stone and Bomb taps clearing the selection properly"""
        cell = self.grid[row][col]
        if cell is None or cell.special == WILD:
            return Tap("none")
        if (row, col) in self.selection:
            group, self.selection = self.selected, []
            return Tap("smash", move=self.smash((row, col), group))
        self.selection = []
        if cell.special == BOMB:
            return Tap("smash", move=self.smash((row, col), self.blast(row, col)))
        if cell.color >= MAX_COLORS:
            return Tap("clear")
        group = self.find_group(row, col)
        if len(group.cells) < MIN_GROUP:
            return Tap("clear")
        if self.extreme:
            return Tap("smash", move=self.smash((row, col), group))
        self.selection, self.selected = group.cells, group
        return Tap("select", cells=list(group.cells))

    # Smashing

    def smash(self, tapped: Pos, group: Group) -> Move:
        """Score, remove and drop, pick up, Refill, collapse, then check for a move (Level:2280-2396)"""
        bomb = group.special == BOMB
        points = BOMB_POINTS if bomb else group_points(len(group.cells))
        if group.special == TRIPLE:
            points *= TRIPLE_TIMES
        if self.mode == ZEN:
            points = 0
        self.score += points
        self.level_score += points
        self.last_points = points
        wiped = self.wipe(group) if group.special == WIPE else []
        kills = group.cells + wiped
        first = max(0, tapped[1] - 1) if bomb else min(col for _, col in kills)
        move = Move(tapped, group.color, list(group.cells), points, bomb, wiped, kills, first, self.occupied())
        self.record = []
        effects = Group([], group.color, group.special, group.wild, group.shifter)
        for col in range(first, self.cols):
            self.sweep(col, kills, move, effects, bomb)
            move.falls += self.settle(col)
        move.special = effects.special
        move.plain = not (effects.special > 0 or effects.wild or effects.shifter)
        if effects.special in (UNDO, SHUFFLE):
            move.pickups.append(effects.special)
        if effects.special == REFILL:
            move.refill = self.refill()
        move.gap = any(self.grid[self.rows - 1][col] is None for col in range(self.cols))
        move.slides = self.collapse()
        if self.extreme:
            self.check_critters(after_rise=False)
        else:
            self.level_over = move.level_over = not self.has_move()
        return move

    def wipe(self, group: Group) -> list[Pos]:
        """Color wipe: every other block of the tapped color, found top-left first (Level:1139-1166)"""
        taken = set(group.cells)
        return [(row, col) for row, col, cell in self.cells() if cell.color == group.color and (row, col) not in taken]

    def sweep(self, col: int, kills: list[Pos], move: Move, effects: Group, bomb: bool) -> None:
        """Remove one column's doomed blocks. A Bomb's blast removes special blocks without their effects"""
        for row, c in kills:
            cell = self.grid[row][c] if c == col else None
            if cell is None:
                continue
            if bomb:
                pass
            elif cell.special == HOLD:
                self.holds[col] = max(self.holds[col], 0) + 1
                self.critters[col] = True
                move.held.append(col)
            else:
                effects.note(cell)
            self.record.append(("kill", cell, row, col))
            self.grid[row][col] = None

    def settle(self, col: int) -> list[tuple[int, int, int]]:
        """Plain gravity: each block falls to the lowest empty cell below it, keeping order (Level:2694-2745)"""
        falls = []
        for row in range(self.rows - 1, -1, -1):
            if self.grid[row][col] is not None:
                continue
            for above in range(row - 1, -1, -1):
                cell = self.grid[above][col]
                if cell is not None:
                    self.grid[row][col], self.grid[above][col] = cell, None
                    self.record.append(("move", cell, above, col, row, col))
                    falls.append((above, col, row))
                    break
        return falls

    def refill(self) -> list[tuple[int, int, int]]:
        """One new block for every column with room, left to right, colored from what's on the board"""
        added = []
        for col in range(self.cols):
            if self.grid[0][col] is not None:
                continue
            present = self.colors_on_board()
            if present:
                color = present[biased(self.rng, 0, len(present) - 1)]
            else:
                color = biased(self.rng, 0, self.colors - 1)
            row = max(row for row in range(self.rows) if self.grid[row][col] is None)
            self.grid[row][col] = self.new_cell(color)
            added.append((row, col, color))
        return added

    def collapse(self) -> list[tuple[int, int]]:
        """Close up empty columns, one column move at a time (Level:910-969, Level:2831-2862)"""
        slides = []
        while (slide := self.next_slide()) is not None:
            src, dst = slide
            for row in range(self.rows):
                cell = self.grid[row][src]
                if cell is not None:
                    self.grid[row][dst], self.grid[row][src] = cell, None
                    self.record.append(("move", cell, row, src, row, dst))
            slides.append(slide)
        return slides

    def next_slide(self) -> tuple[int, int] | None:
        empty = [all(self.grid[row][col] is None for row in range(self.rows)) for col in range(self.cols)]
        if self.side == 1:
            # The right board packs left, so both boards huddle toward the middle
            for dst in range(self.cols - 1):
                if empty[dst]:
                    src = next((col for col in range(dst + 1, self.cols) if not empty[col]), None)
                    if src is not None:
                        return src, dst
            return None
        for dst in range(self.cols - 1, 0, -1):
            if empty[dst]:
                src = next((col for col in range(dst - 1, -1, -1) if not empty[col]), None)
                if src is not None:
                    return src, dst
        return None

    def has_move(self) -> bool:
        """Is a group left? The original's check missed some Wild and Bomb moves (Level:1174-1250); this one doesn't"""
        for row, col, cell in self.cells():
            if cell.special == BOMB:
                return True
            for r, c in ((row, col + 1), (row + 1, col)):
                if r < self.rows and c < self.cols and self.grid[r][c] is not None and pairs(cell, self.grid[r][c]):
                    return True
        return False

    # Undo and Shuffle

    def undo(self) -> bool:
        """Play the last move backwards and take its points off (Level:2421-2486)"""
        if not self.record:
            return False
        for op in reversed(self.record):
            if op[0] == "kill":
                _, cell, row, col = op
                self.grid[row][col] = cell
            else:
                _, cell, row, col, to_row, to_col = op
                self.grid[to_row][to_col] = None
                self.grid[row][col] = cell
        self.record = []
        if self.mode != ZEN:
            self.score -= self.last_points
            self.level_score -= self.last_points
        self.last_points = 0
        self.selection = []
        self.level_over = not self.has_move()
        return True

    def shuffle(self) -> tuple[list[tuple[int, int, int, int]], int]:
        """Swap every occupied cell with a random occupied cell, walking one cell a tick (Level:1588-1622).
        The walk starts at the top block of the leftmost non-empty column, a kept quirk. Returns the swaps and how
        many cells the walk visits"""
        self.selection = []
        self.record = []
        start = next(((row, col) for col in range(self.cols) for row in range(self.rows) if self.grid[row][col]), None)
        if start is None:
            return [], 0
        swaps = []
        first = start[0] * self.cols + start[1]
        for index in range(first, self.rows * self.cols):
            row, col = divmod(index, self.cols)
            if self.grid[row][col] is None:
                continue
            while True:
                r, c = biased(self.rng, 0, self.rows - 1), biased(self.rng, 0, self.cols - 1)
                if self.grid[r][c] is not None:
                    break
            self.grid[row][col], self.grid[r][c] = self.grid[r][c], self.grid[row][col]
            swaps.append((row, col, r, c))
        if not self.extreme:
            self.level_over = not self.has_move()
        return swaps, self.rows * self.cols - first

    # Countdown and Shifter

    def timed(self) -> list[tuple[int, int, Cell]]:
        return [(row, col, cell) for row, col, cell in self.cells() if cell.special in (COUNTDOWN, SHIFTER)]

    def start_timers(self, now: float) -> None:
        """Countdowns and Shifters start counting when the level becomes playable (Level:2204-2208)"""
        for _, _, cell in self.timed():
            cell.due = now + (COUNTDOWN_MS if cell.special == COUNTDOWN else SHIFTER_MS)

    def pause_timers(self, ms: float) -> None:
        """Undo and Shuffle freeze the timers while they play (Level:2482, Level:2524)"""
        for _, _, cell in self.timed():
            if cell.due is not None:
                cell.due += ms

    def next_timer(self) -> float | None:
        due = [cell.due for _, _, cell in self.timed() if cell.due is not None]
        return min(due) if due else None

    def fire(self, now: float) -> list[TimerEvent]:
        """Fire every timer whose deadline has passed, in the order the blocks were made, as the original walked its
        list each tick (Level:1479-1581). The game only calls this while the board is idle"""
        events = []
        for cell in sorted((cell for _, _, cell in self.timed()), key=lambda cell: cell.serial):
            # An earlier Countdown this tick may have turned this block to Stone
            if cell.special not in (COUNTDOWN, SHIFTER) or cell.due is None or not cell.due < now:
                continue
            row, col = next((r, c) for r, c, other in self.cells() if other is cell)
            if cell.special == COUNTDOWN:
                events.append(TimerEvent("stone", self.petrify(row, col)))
                continue
            color = self.shift(row, col, now)
            if color is not None:
                events.append(TimerEvent("shift", [(row, col)], color))
        return events

    def petrify(self, row: int, col: int) -> list[Pos]:
        """A Countdown's whole group turns to Stone (Level:1519-1549). The selection always clears, as before"""
        cells = self.find_group(row, col).cells
        for r, c in cells:
            cell = self.grid[r][c]
            cell.color, cell.special, cell.due = STONE, 0, None
        self.selection = []
        if not self.extreme:
            self.level_over = not self.has_move()
        return cells

    def shift(self, row: int, col: int, now: float) -> int | None:
        """A Shifter takes another color still on the board, or tries again next tick (Level:1550-1572). A selection
        holding it clears either way"""
        cell = self.grid[row][col]
        if (row, col) in self.selection:
            self.selection = []
        present = self.colors_on_board()
        color = present[biased(self.rng, 0, len(present) - 1)]
        if color == cell.color:
            # Due again at once: the original's next tick, since a deadline only fires once it has passed
            cell.due = now
            return None
        cell.color = color
        cell.due = now + SHIFTER_MS
        if not self.extreme:
            self.level_over = not self.has_move()
        return color

    # Extreme

    def rise(self) -> Rise:
        """Every column without a hold moves up a row and a new row fills the bottom (Level:2864-2910)"""
        overflow = []
        held = [col for col in range(self.cols) if self.holds[col] > 0]
        for row in range(self.rows - 1):
            for col in range(self.cols):
                if col in held:
                    continue
                if row == 0 and self.grid[0][col] is not None:
                    overflow.append(col)
                self.grid[row][col], self.grid[row + 1][col] = self.grid[row + 1][col], None
        new = []
        palette = list(range(self.colors))
        hold_max, hold_hit = HOLD_ROLL
        bottom = self.rows - 1
        for col in range(self.cols):
            if self.grid[bottom][col] is None and col not in held:
                color = palette[biased(self.rng, 0, len(palette) - 1)]
                special = HOLD if biased(self.rng, 0, hold_max) == hold_hit else 0
                self.grid[bottom][col] = self.new_cell(color, special)
                new.append((col, color, special))
        for col in range(self.cols):
            if self.holds[col] >= 0:
                self.holds[col] -= 1
        self.check_critters(after_rise=True)
        if overflow:
            self.over = True
        return Rise(new, overflow, held)

    def check_critters(self, after_rise: bool) -> None:
        """A hold ends once spent or when its column empties (Level:1931-1966)"""
        for col in range(self.cols):
            if not self.critters[col]:
                continue
            if (after_rise and self.holds[col] <= -1) or self.grid[self.rows - 1][col] is None:
                self.critters[col] = False
                self.holds[col] = -1


def pairs(a: Cell, b: Cell) -> bool:
    """Two touching blocks that make a group: the same normal color, or a Wild beside any normal color"""
    a_colored, b_colored = a.color < MAX_COLORS, b.color < MAX_COLORS
    if a_colored and b_colored and a.color == b.color:
        return True
    return (a.special == WILD and b_colored) or (b.special == WILD and a_colored)
