import json
from pathlib import Path

# Score values, mirrored in web/brickbreaker/game.js
POINTS_PER_BRICK = 10
POINTS_PER_LEVEL = 100

# The fastest a real round can go, kept well below what a lucky player can reach so nobody is refused.
# Multi-ball can break bricks in bursts (three balls caught above the bricks break several a second), so the
# brick floor allows 10 a second averaged over the whole round. Every level starts with one ball resting on the
# paddle, that ball needs about a second to reach the bricks, and every level takes at least 40 hits, so a level
# takes well over 5 seconds even with luck
MIN_SECONDS_PER_LEVEL = 5
MIN_SECONDS_PER_BRICK = 0.1
MAX_LEVELS = 500


def load_levels(path: Path) -> list[list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def breakable_count(level: list[str]) -> int:
    return sum(char in "123" for row in level for char in row)


def bricks_through(levels: list[list[str]], level_count: int) -> int:
    """Total breakable bricks in the first `level_count` levels (the game loops back to level 1 after the last)"""
    return sum(breakable_count(levels[i % len(levels)]) for i in range(level_count))


def run_is_plausible(levels: list[list[str]], bricks: int, levels_cleared: int, elapsed: float) -> bool:
    """
    Check a finished round's numbers against what the levels and the clock allow.

    Brick Breaker's ball physics can't be replayed exactly, so this checks the result instead of the moves.
    """
    if type(bricks) is not int or type(levels_cleared) is not int:
        return False
    if bricks < 0 or not 0 <= levels_cleared <= MAX_LEVELS:
        return False
    # Every cleared level had all its bricks broken, and the level in progress can't give more than it holds
    if not bricks_through(levels, levels_cleared) <= bricks <= bricks_through(levels, levels_cleared + 1):
        return False
    return elapsed >= levels_cleared * MIN_SECONDS_PER_LEVEL and elapsed >= bricks * MIN_SECONDS_PER_BRICK


def run_score(bricks: int, levels_cleared: int) -> int:
    return bricks * POINTS_PER_BRICK + levels_cleared * POINTS_PER_LEVEL
