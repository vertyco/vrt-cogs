"""
How long the original spent animating each move, so the Red bot can treat a board as busy until then.

The bot works out a move's result at once; this file replays the original's motion tick by tick to count how long
that motion took, using the same integer maths (classMover.as, classMoverControl.as, classLevel.as). The page plays
the same motion with the same numbers, so its animation ends as the board turns idle again.
"""

import typing as t
from dataclasses import dataclass

from .rules import (
    CHUNK_FLOOR,
    CHUNK_GRAVITY,
    CHUNK_VY,
    CHUNK_VY_ADD,
    CLEAR_ROW_MS,
    DROP_ACCEL,
    DROP_SPEED,
    EXTREME_FIRST_ROW,
    EXTREMES,
    FLYER_END,
    FLYER_SPEED,
    FLYER_START,
    HOP_ACCEL,
    HOP_SPEED,
    RAIN_NEXT_TRIGGER,
    RAIN_STEP_MS,
    RAIN_TRIGGER_Y,
    SLIDE_ACCEL,
    SLIDE_SPEED,
    TICK_MS,
    UNDO_FIRST_FRAME,
    UNDO_FRAME_TICKS,
    UNDO_LAST_FRAME,
    board_origin,
    grid_size,
    tile_size,
)

Pos = tuple[int, int]


class Mover:
    """One block's motion, as classMover kept it: whole pixels, a speed and a per-tick speed-up on each axis"""

    __slots__ = ("x", "tx", "vx", "ax", "dx", "at_x", "y", "ty", "vy", "ay", "dy", "at_y", "moving", "killed")

    def __init__(self, x: int, y: int):
        self.x = self.tx = x
        self.y = self.ty = y
        self.vx = self.ax = self.dx = 0
        self.vy = self.ay = self.dy = 0
        self.at_x = self.at_y = True
        self.moving = False
        self.killed = False

    def step(self) -> None:
        """classMoverControl.moveIt"""
        if not self.at_x:
            self.x, self.vx, self.at_x = advance(self.x, self.tx, self.vx, self.ax, self.dx)
        if not self.at_y:
            self.y, self.vy, self.at_y = advance(self.y, self.ty, self.vy, self.ay, self.dy)
        if self.at_x and self.at_y:
            self.moving = False


def advance(pos: int, target: int, speed: int, accel: int, direction: int) -> tuple[int, int, bool]:
    if direction == 0:
        return target, speed, True
    pos += speed * direction
    speed += accel
    if (direction == 1 and pos >= target) or (direction == -1 and pos <= target):
        return target, speed, True
    return pos, speed, False


@dataclass
class MoveTicks:
    busy: int  # ticks from the tap until the board takes taps again
    pause: int  # ticks Extreme adds back to its row timer, when the move collapsed no column
    debris: int  # ticks the last chunks keep flying after the move ends


class Motion:
    """The original's board during one move: a grid of movers stepped one tick at a time"""

    def __init__(self, before: t.Iterable[Pos], rows: int, cols: int, tile_w: int, tile_h: int, top: int):
        self.rows, self.cols = rows, cols
        self.tile_w, self.tile_h, self.top = tile_w, tile_h, top
        self.grid: list[list[Mover | None]] = [[None] * cols for _ in range(rows)]
        for row, col in before:
            self.grid[row][col] = Mover(col * tile_w, top + row * tile_h)
        self.ticks = 0
        self.debris = 0

    def redraw(self) -> bool:
        """Remove smashed blocks and step every moving block. True once nothing is moving (Level:479-570)"""
        self.debris = max(0, self.debris - 1)
        still = False
        for col in range(self.cols):
            for row in range(self.rows - 1, -1, -1):
                mover = self.grid[row][col]
                if mover is None:
                    continue
                if mover.killed:
                    self.grid[row][col] = None
                elif mover.moving:
                    mover.step()
                    still = still or mover.moving
        return not still

    def tick(self) -> None:
        self.ticks += 1

    def smash(self, row: int, col: int) -> None:
        """Doom a block and make every block above it hop (Level:1296-1356, Level:1968-1994)"""
        self.grid[row][col].killed = True
        self.debris = max(self.debris, chunk_ticks(self.top + row * self.tile_h))
        hop = HOP_SPEED
        for above in range(row - 1, -1, -1):
            mover = self.grid[above][col]
            if mover is not None:
                mover.moving, mover.at_y, mover.ty, mover.dy = True, False, mover.y, 1
                mover.vy, mover.ay = hop, HOP_ACCEL
                hop -= 1

    def drop(self, col: int) -> None:
        """Retarget each block to the lowest empty cell below it (Level:2694-2745)"""
        for row in range(self.rows - 1, -1, -1):
            mover = self.grid[row][col]
            if mover is not None:
                if row == 0 and mover.y < self.top:
                    mover.ty, mover.at_y, mover.moving = self.top, False, True
                continue
            for above in range(row - 1, -1, -1):
                mover = self.grid[above][col]
                if mover is not None:
                    self.grid[row][col], self.grid[above][col] = mover, None
                    mover.ty, mover.at_y, mover.moving = self.top + row * self.tile_h, False, True
                    break

    def wait(self) -> None:
        """FINISHDROP and FINISHMOVE: a tick at a time until everything has landed"""
        while True:
            self.tick()
            if self.redraw():
                return

    def refill(self) -> None:
        """One column a tick: a new block drops in from above the stage (Level:2397-2420)"""
        for col in range(self.cols):
            self.tick()
            self.redraw()
            if self.grid[0][col] is None:
                mover = Mover(col * self.tile_w, -self.tile_h)
                mover.ty, mover.at_y, mover.dy = self.top, False, 1
                mover.vy, mover.ay = DROP_SPEED, DROP_ACCEL
                self.grid[0][col] = mover
                self.drop(col)

    def slide(self, src: int, dst: int) -> None:
        """Move a whole column across, starting slow and speeding up (Level:2831-2862)"""
        direction = 1 if dst > src else -1
        for row in range(self.rows):
            mover = self.grid[row][src]
            if mover is not None:
                self.grid[row][src], self.grid[row][dst] = None, mover
                mover.x, mover.tx, mover.dx = src * self.tile_w, dst * self.tile_w, direction
                mover.vx, mover.ax, mover.at_x, mover.moving = SLIDE_SPEED, SLIDE_ACCEL, False, True


def move_ticks(
    before: t.Iterable[Pos],
    kills: list[Pos],
    first: int,
    refill: bool,
    slides: list[tuple[int, int]],
    gap: bool,
    rows: int,
    cols: int,
    tile_w: int,
    tile_h: int,
    top: int,
    extreme: bool,
) -> MoveTicks:
    """Replay a smash through the original's states, from PREPAREKILL back to PLAYGAME (Level:2280-2580)"""
    motion = Motion(before, rows, cols, tile_w, tile_h, top)
    motion.tick()  # PREPAREKILL
    for col in range(first, cols):
        motion.tick()  # KILLTILES, one column a tick
        for row, c in kills:
            if c == col and motion.grid[row][col] is not None:
                motion.smash(row, col)
        motion.redraw()
        motion.drop(col)
    motion.wait()
    motion.tick()  # AFTERDROP
    pause = motion.ticks
    if refill:
        motion.refill()
        motion.wait()
        motion.tick()  # AFTERDROP again
    if gap:
        for src, dst in slides:
            motion.tick()  # MOVECOLS, one column a tick
            motion.slide(src, dst)
            motion.redraw()
        motion.tick()  # MOVECOLS finds no gap left
        motion.redraw()
        if extreme:
            return MoveTicks(motion.ticks, 0, motion.debris)
        motion.wait()
    if not extreme:
        motion.tick()  # CHECKMOVES
    return MoveTicks(motion.ticks, 0 if gap else pause, motion.debris)


def board_ticks(board: t.Any, move: t.Any) -> MoveTicks:
    """move_ticks for a Board and the Move it just made"""
    tile_w, tile_h = tile_size(board.mode, board.level)
    top = board_origin(board.mode, board.level, board.side)[1]
    return move_ticks(
        move.before,
        move.kills,
        move.first,
        bool(move.refill),
        move.slides,
        move.gap,
        board.rows,
        board.cols,
        tile_w,
        tile_h,
        top,
        board.mode in EXTREMES,
    )


def chunk_ticks(y: float) -> int:
    """Ticks until the slowest-falling chunk from a block at this height drops off the stage (Explosion:98-122)"""
    speed = min(CHUNK_VY) + CHUNK_VY_ADD
    ticks = 0
    while y <= CHUNK_FLOOR:
        y += speed
        speed += CHUNK_GRAVITY
        ticks += 1
    return ticks


def rain_in_steps(rows: int, cols: int, top: int, tile_h: int, first_row: int = 0) -> int:
    """Steps (at 120 a second) until every block of a new level has rained in (Level:533-556, Level:2176-2192).

    Each block falls from just above the stage. When one passes y = 10 the block above it starts; one step later the
    bottom block of the next column starts. Blocks started during a step move in that same step, as the original's
    loop reached them later in its pass."""
    movers: dict[Pos, list] = {}
    for row in range(first_row, rows):
        for col in range(cols):
            # y, speed, moving, triggered once, trigger y, done with triggers, landed
            movers[(row, col)] = [-tile_h, DROP_SPEED, False, False, RAIN_TRIGGER_Y, False, False]
    movers[(rows - 1, 0)][2] = True
    steps = 0
    while True:
        steps += 1
        still = False
        for col in range(cols):
            for row in range(rows - 1, first_row - 1, -1):
                still = rain_step(movers, row, col, rows, cols, top + row * tile_h) or still
        if not still:
            return steps


def rain_step(movers: dict[Pos, list], row: int, col: int, rows: int, cols: int, target: int) -> bool:
    mover = movers[(row, col)]
    if not mover[2]:
        return False
    if not mover[6]:
        mover[0] += mover[1]
        mover[1] += DROP_ACCEL
        if mover[0] >= target:
            mover[0], mover[6] = target, True
        if mover[0] >= mover[4]:
            mover[3] = True
    mover[2] = not mover[6]
    if mover[3] and not mover[5]:
        if mover[4] == RAIN_TRIGGER_Y:
            mover[4] = RAIN_NEXT_TRIGGER
            if (row - 1, col) in movers:
                movers[(row - 1, col)][2] = True
        else:
            if col < cols - 1 and (rows - 1, col + 1) in movers:
                movers[(rows - 1, col + 1)][2] = True
            mover[5] = True
    return mover[2]


def level_start_ms(mode: int, level: int) -> tuple[float, float]:
    """(when the level's timers start, when it takes taps), in ms from the level's start (Level:2151-2218)"""
    rows, cols = grid_size(mode, level)
    _, tile_h = tile_size(mode, level)
    top = board_origin(mode, level, 0)[1]
    extreme = mode in EXTREMES
    steps = rain_in_steps(rows, cols, top, tile_h, EXTREME_FIRST_ROW if extreme else 0)
    # NEXTLEVEL and CREATELEVEL take a tick each, the first step comes a tick later, then PREPARELEVEL
    timers = 3 * TICK_MS + (steps - 1) * RAIN_STEP_MS
    return timers, timers if extreme else timers + TICK_MS


def undo_ticks() -> int:
    """The Undo animation steps a frame every second tick from frame 2 to 70, then the board settles and checks"""
    return (UNDO_LAST_FRAME - UNDO_FIRST_FRAME) * UNDO_FRAME_TICKS + 2


def undo_frame_tick(frame: int) -> int:
    return (frame - UNDO_FIRST_FRAME) * UNDO_FRAME_TICKS


def shuffle_ticks(walk: int) -> int:
    """One cell a tick, or the flyer's crossing if that is longer, then the move check (Level:2487-2529)"""
    crossing = (FLYER_END - FLYER_START) // FLYER_SPEED + 1
    return max(walk + 1, crossing) + 1


def level_end_ms(rows: int, debris: int) -> float:
    """From a level's last move ending to its popup: wait for chunks, then clear a row every 25 ms (Level:2581-2617)"""
    return (debris + 1) * TICK_MS + rows * CLEAR_ROW_MS


def overflow_end_ms(rows: int, debris: int) -> float:
    """An Extreme overflow blows the board apart a row at a time, then clears it once the last chunks have landed
    (Level:2581-2611). Each of the blow-apart steps also moves the chunks on one step"""
    return TICK_MS + 2 * rows * CLEAR_ROW_MS + max(0, debris - rows) * TICK_MS
