"""
Boulder Bash's numbers, all read from Neopets' Destruct-O-Match III.

Line references point into the decompiled original: Level is classLevel.as, Game is classGame928.as, Cell is
classCell.as and Explosion is classExplosion.as. Nothing here imports Discord, so tests use it directly.
"""

import math
import random

# Modes, in the original's order (Level:73-81)
ZEN = 0
NORMAL = 1
EXTREME = 2
NORMAL2 = 3
EXTREME2 = 4
MODES = (ZEN, NORMAL, EXTREME, NORMAL2, EXTREME2)
MODE_NAMES = ("Zen", "Normal", "Extreme", "Normal x2", "Extreme x2")
EXTREMES = (EXTREME, EXTREME2)
TWO_BOARDS = (NORMAL2, EXTREME2)
LAST_LEVEL = 10  # Game:264, Game:686

STAGE_W = 800
STAGE_H = 600

# Grid sizes, the original's "zoom" steps (Game:126-149):
# rows, one-board columns, tile width, tile height, board x, board y, two-board columns, right board x
ZOOMS = (
    (12, 14, 48, 32, 64, 96, 6, 448),
    (13, 15, 44, 29, 70, 103, 7, 422),
    (14, 16, 42, 28, 64, 88, 7, 442),
    (16, 18, 37, 24, 67, 96, 8, 437),
)

# Block colors. 0-8 are the nine normal colors; Stone and the black base can't be tapped and never match
MAX_COLORS = 9  # Level:365
STONE = 10  # Level:1533
BASE = 11  # Level:1714, Level:1718

# Special blocks (Level:83-101)
REFILL = 1
COUNTDOWN = 2
TRIPLE = 3
BOMB = 4
WIPE = 5
SHIFTER = 6
WILD = 7
UNDO = 8
SHUFFLE = 9
HOLD = 10
SPECIAL_NAMES = {
    REFILL: "Refill",
    COUNTDOWN: "Countdown",
    TRIPLE: "Triple",
    BOMB: "Bomb",
    WIPE: "Color wipe",
    SHIFTER: "Shifter",
    WILD: "Wild",
    UNDO: "Undo",
    SHUFFLE: "Shuffle",
    HOLD: "Column hold",
}
NUM_SPECIALS = 9  # the type roll's range and the per-level cap (Level:367, Level:2659)
SPECIAL_ROLL = (8, 4)  # getRandom(0, 8) == 4, exactly 1 in 8 (Level:1709)
HOLD_ROLL = (42, 21)  # getRandom(0, 42) == 21, exactly 1 in 42 (Level:1702)
SPECIAL_SAFE_ROWS = 2  # the bottom two rows never get one (Level:1707)
TRIPLE_MIN_LEVEL = 3  # Level:2664

MIN_GROUP = 2  # Level:1458
BOMB_POINTS = 1  # Level:1913-1916
TRIPLE_TIMES = 3  # Level:1917-1921
LEFT_BONUS = (100, 90, 80, 70, 60, 50, 40, 30, 20, 10)  # Level:1884-1888
CLEAR_BONUS = {EXTREME: 50, EXTREME2: 25}  # Level:2243-2250

# Timing. The original's logic ran about 60 times a second; the rain-in ran every 120 fps frame (Level:2143-2148)
TICK_MS = 1000 / 60
RAIN_STEP_MS = 1000 / 120
COUNTDOWN_MS = 16_000  # Cell:146
COUNTDOWN_SHOWN = 15  # Cell:91
COUNTDOWN_WARNING = 5  # beeps below this (Cell:95)
SHIFTER_MS = 6000  # Cell:151
ROW_INTERVAL = 3000  # Level:374
EXTREME_START_CUT = 300  # Level:686-689
SPEEDUP_CUT = 400  # Level:983
ROW_GAP_EXTRA = 1000  # Level:1869
EXTREME_FIRST_ROW = 6  # max(3, 7 - level) on level 1, the only level Extreme builds (Level:2162-2166)

# Motion, in pixels per tick (Level:1968-1994, Level:2184, Level:2403, Level:2856-2857)
HOP_SPEED = -2
HOP_ACCEL = 2
DROP_SPEED = 6
DROP_ACCEL = 3
SLIDE_SPEED = 1
SLIDE_ACCEL = 4
RAIN_TRIGGER_Y = 10
RAIN_NEXT_TRIGGER = 30
CLEAR_ROW_MS = 25  # Level:2589

# Undo: a 70-frame animation stepped every 30 ms, so every second tick (Level:385-389)
UNDO_FIRST_FRAME = 2
UNDO_REWIND_FRAME = 25
UNDO_STOMP_FRAME = 45
UNDO_LAST_FRAME = 70
UNDO_FRAME_TICKS = 2
# Shuffle: the flyer crosses at 6 px a tick, from x 140 until it passes x 1130 (Level:2490, Level:2520-2522)
FLYER_START = 140
FLYER_END = 1130
FLYER_SPEED = 6

# Flying chunks from smashed blocks (Explosion:31-39, Explosion:107-108)
CHUNK_SCALE = (0.4, 0.35, 0.3, 0.25)
CHUNK_VX = (-15, -12, -10, -8, -5, 5, 8, 10, 12, 15)
CHUNK_VY = (-14, -15, -18, -17, -16, -13, -12, -19)
CHUNK_VY_ADD = 2
CHUNK_DRAG = 0.9
CHUNK_GRAVITY = 1.25
CHUNK_FLOOR = 600
CHUNKS_PER_BLOCK = 2


def biased(rng: random.Random, low: int, high: int) -> int:
    """The original's getRandom: round(low + random * (high - low)), so the two end values are half as likely"""
    return math.floor(low + rng.random() * (high - low) + 0.5)


def zoom_for(mode: int, level: int) -> int:
    """Which grid size a level uses. Extreme builds one board, so it never grows (Game:294-316)"""
    if mode in EXTREMES or level <= 2:
        return 0
    if level <= 5:
        return 1
    if level <= 9:
        return 2
    return 3


def grid_size(mode: int, level: int) -> tuple[int, int]:
    """(rows, columns) of one board"""
    zoom = ZOOMS[zoom_for(mode, level)]
    return zoom[0], zoom[6] if mode in TWO_BOARDS else zoom[1]


def tile_size(mode: int, level: int) -> tuple[int, int]:
    zoom = ZOOMS[zoom_for(mode, level)]
    return zoom[2], zoom[3]


def board_origin(mode: int, level: int, side: int) -> tuple[int, int]:
    """Top-left corner of a board on the 800 x 600 stage. Side 1 is the right board of a two-board mode"""
    zoom = ZOOMS[zoom_for(mode, level)]
    return (zoom[7] if side else zoom[4]), zoom[5]


def colors_for(mode: int, level: int) -> int:
    """Colors in play: 3 (Extreme 2) to start, plus one on levels 1, 3, 5, 7, 9 and 10 (Level:690-717)"""
    count = 2 if mode in EXTREMES else 3
    count += sum(1 for step in (1, 3, 5, 7, 9, 10) if level >= step)
    return min(count, MAX_COLORS)


def goal_for(mode: int, level: int) -> int:
    """The level score a level needs (Level:719-748). Extreme's is the points per speed-up"""
    if mode == NORMAL:
        return 100 + 20 * (level - 1)
    if mode == NORMAL2:
        return 40 + 10 * (level - 1)
    if mode == EXTREME:
        return 150
    if mode == EXTREME2:
        return 75
    return 0


def group_points(size: int) -> int:
    """Points for a group, cut down to a whole number the way the original's int maths did (Level:1893-1912)"""
    if size >= 16:
        return size * 2
    if size >= 11:
        return int(size * 1.6)
    if size >= 7:
        return int(size * 1.4)
    if size >= 4:
        return int(size * 1.2)
    return size


def blocks_left_bonus(left: int) -> int:
    return LEFT_BONUS[left] if 0 <= left < len(LEFT_BONUS) else 0


def row_gap_ms(level: int) -> int:
    """Time between Extreme's rising rows at a speed-up level. Goes below 0 past level 10 (Level:1867-1870)"""
    return ROW_INTERVAL - EXTREME_START_CUT - SPEEDUP_CUT * (level - 1) + ROW_GAP_EXTRA
