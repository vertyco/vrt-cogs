"""Feature 8, the Snake: one target of its color over a body that shortens toward its nest as it is shot.

The body is the snake path's cross-sections (spline.build over the nest and its corner squares), nest first; the
snake covers sections 0..index and is hit on any of them. It starts on every section (SnakeFeature$$AttachInternal,
RVA 0x57C190C, sets the index to the last one). Each hit takes 1 health and recomputes the index at once
(OnHitTargetDamaged, RVA 0x57BCD64, through UpdateSplineClipPercent, RVA 0x57B93B4): the spline point at
t = clamp(1 - health / Count, 0.0001, 0.9999), worked out in float32 (get_HealthPercent, RVA 0x57BAF2C, a float
division; GetCurrentClipPercent, RVA 0x57BAEF4), names the cell whose section plus one is the new index
(UpdateCurrentObstaclePointIndex, RVA 0x57BBD1C); a point on no section leaves the index as it was. At health 0 the
snake is gone, nest included. web/sim/features/snake.js mirrors this file.

The index for every health is worked out once at setup, so the state holds whole numbers only and the path's
samples stay out of it.
"""

from __future__ import annotations

import typing as t

from .. import base, checks, spline
from .. import grid as gridx
from ..mathx import f32

NUMBER = 8

# The clamp's bounds are float32 constants in the original
LOW = f32(0.0001)
HIGH = f32(0.9999)


def squares_of(data: dict) -> list[list[list[int]]]:
    """The nest, then each corner square, as lists of [x, y] cells."""
    squares = [[[point["X"], point["Y"]] for point in data["MainGridPoints"]]]
    for square in data["SnakeGridPoints"]:
        squares.append([[point["X"], point["Y"]] for point in square["GridPoints"]])
    return squares


def clip_percent(health: int, count: int) -> float:
    """1 - health / Count in float32, clamped to 0.0001..0.9999 (the spline point the body's far end is cut at)."""
    percent = f32(1.0 - f32(f32(health) / f32(count)))
    if percent > HIGH:
        percent = HIGH
    if percent < LOW:
        percent = LOW
    return percent


def setup(state: base.State) -> None:
    """Every snake as a record, in file order, with its target on every section of its body."""
    listed = state.level.features.get("snakes")
    if not listed or not listed["Snakes"]:
        return
    grid = state.grid
    snakes = []
    for data in listed["Snakes"]:
        path = spline.build(squares_of(data), spline.STRAIGHT_DISTANCE)
        count = data["Count"]
        snake = {
            "target": -1,
            "sections": spline.cross_sections(path, (grid.width, grid.height)),
            # stops[health]: the index spline.index_at gives at that health (-1: keep the index)
            "stops": [spline.index_at(path, clip_percent(health, count)) for health in range(count + 1)],
            "count": count,
            "index": len(path["sections"]) - 1,
        }
        target = gridx.make_target(NUMBER, data["Material"], count)
        gridx.add(grid, target, cells_of(snake))
        snake["target"] = target.id
        snakes.append(snake)
    state.features[NUMBER] = {"snakes": snakes}


def cells_of(snake: dict) -> list[int]:
    """Sections 0..index, nest first, each cell once."""
    cells: list[int] = []
    seen: set[int] = set()
    for section in snake["sections"][: snake["index"] + 1]:
        for cell in section:
            if cell not in seen:
                seen.add(cell)
                cells.append(cell)
    return cells


def on_hit(state: base.State, target: gridx.Target, damage: int, source: t.Any) -> None:
    """A shot lands on any cell of the snake: it loses health, the body is recomputed at once, and at 0 it is gone."""
    snake = next(s for s in state.features[NUMBER]["snakes"] if s["target"] == target.id)
    target.health = max(0, target.health - damage)
    cell = -1 if source is None else source.cell
    base.emit(state, "hit", {"target": target.id, "cell": cell, "health": target.health})
    index = snake["stops"][target.health]
    if index >= 0 and index != snake["index"]:
        snake["index"] = index
        base.emit(state, "snake_shrink", {"target": target.id, "index": index, "health": target.health})
        if target.health > 0:
            gridx.move(state.grid, target, cells_of(snake))
    if target.health > 0:
        return
    target.dead = True
    gridx.remove(state.grid, target)
    base.emit(state, "target_died", {"target": target.id, "owner": NUMBER})
    checks.request_win_check(state)


def remaining_hits(state: base.State, color: int) -> int:
    """The hits the living snakes of this color still take."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return 0
    total = 0
    for snake in mine["snakes"]:
        target = state.grid.targets[snake["target"]]
        if not target.dead and target.color == color:
            total += target.health
    return total


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["snakes"]))
    for snake in mine["snakes"]:
        target = state.grid.targets[snake["target"]]
        h = base.mix(base.mix(base.mix(h, target.health), snake["index"]), int(target.dead))
    return h
