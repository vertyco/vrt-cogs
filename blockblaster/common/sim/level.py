"""Turns a compact level from a pack into the Level the simulation plays.

The page runs the same function in web/sim/level.js; both must give identical output.
"""

import copy
import typing as t
from dataclasses import dataclass

ALPHABET = "0123456789abcdefghijklmnopqrstuvwx"
EMPTY = "."


@dataclass
class Level:
    number: int
    difficulty: int  # 0 Easy, 1 Medium, 2 Hard, 3 Very Hard
    width: int
    height: int
    pw: int  # picture width in L (1/1200 of an original unit)
    slot_count: int
    conveyor_limit: int
    cubes: list[list[int]]  # [x, y, color, ax, ay, health], in the original's x-then-y order
    queues: list[list[list[int]]]  # per queue, per pig [id, ammo, color], front first
    features: dict[str, t.Any]  # the original's feature lists under their original field names
    used: list[int]  # sorted feature numbers the level uses


def expand(compact: dict) -> Level:
    """Rebuild the cubes from the color grid, the multi-cell anchors and the health list."""
    width, height = compact["w"], compact["h"]
    grid = compact["grid"]
    areas = {(x, y): (ax, ay) for x, y, ax, ay in compact["big"]}
    health = {(x, y): hp for x, y, hp in compact["hp"]}
    covered: set[tuple[int, int]] = set()
    for (x, y), (ax, ay) in areas.items():
        for cx in range(x, x + ax):
            for cy in range(y, y + ay):
                if (cx, cy) != (x, y):
                    covered.add((cx, cy))
    cubes = []
    for x in range(width):
        for y in range(height):
            char = grid[y * width + x]
            if char == EMPTY or (x, y) in covered:
                continue
            ax, ay = areas.get((x, y), (1, 1))
            cubes.append([x, y, ALPHABET.index(char), ax, ay, health.get((x, y), 1)])
    return Level(
        number=compact["n"],
        difficulty=compact["d"],
        width=width,
        height=height,
        pw=compact["pw"],
        slot_count=compact["slots"],
        conveyor_limit=compact["trays"],
        cubes=cubes,
        queues=copy.deepcopy(compact["queues"]),
        features=copy.deepcopy(compact["fx"]),
        used=list(compact["f"]),
    )
