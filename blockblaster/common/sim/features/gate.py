"""Feature 5, the Gate: one target of its color over a head and a bar that shortens as it is shot.

The target's health starts at Count and covers the head's cells and the bar's. The bar leaves the head's side that
faces Direction, as wide as that side, starting at the next cell; its layers are counted from the head, and the far
layer goes first when the bar shortens (GateFeature$$UpdateSplineGridPoints, RVA 0x566E8B4, called at once from the
damage handler through UpdateSplineClipPercent, RVA 0x566DBA0). The layer count is the ceiling of
clamp(health / Count, 0, 1) x Length, worked out in float32 at each step (GateFeature$$get_HealthPercent, RVA
0x566E46C, a float division; then a float multiply and a round up). A cell outside the picture is left out; the
original keeps it in a set no cell ever matches. At health 0 the gate is gone. web/sim/features/gate.js mirrors
this file.
"""

from __future__ import annotations

import math
import typing as t

from .. import base, checks
from .. import grid as gridx
from ..mathx import f32

NUMBER = 5

# FacingDirection (0 Left, 1 Up, 2 Right, 3 Down) as the step one layer takes
STEPS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


def bar_layers(health: int, count: int, length: int) -> int:
    """The bar's layers at this health: float32 division, clamp to 0..1, float32 multiply by Length, round up."""
    percent = f32(f32(health) / f32(count))
    percent = min(percent, 1.0)
    if percent < 0.0:
        percent = 0.0
    return math.ceil(f32(percent * f32(length)))


def start_side(points: list[tuple[int, int]], direction: int) -> list[tuple[int, int]]:
    """The head's points on the side the bar leaves from (GateFeature$$GetSplineStartSideValue, RVA 0x566CC64: the
    smallest x for Left, the largest y for Up, the largest x for Right, the smallest y for Down)."""
    if direction == 0:
        edge = min(x for x, _ in points)
        return [point for point in points if point[0] == edge]
    if direction == 2:
        edge = max(x for x, _ in points)
        return [point for point in points if point[0] == edge]
    if direction == 1:
        edge = max(y for _, y in points)
        return [point for point in points if point[1] == edge]
    edge = min(y for _, y in points)
    return [point for point in points if point[1] == edge]


def inside(grid: gridx.Grid, x: int, y: int) -> bool:
    return 0 <= x < grid.width and 0 <= y < grid.height


def setup(state: base.State) -> None:
    """Every gate as a record, in file order, with its target standing on the head and the full bar."""
    listed = state.level.features.get("gates")
    if not listed or not listed["Gates"]:
        return
    grid = state.grid
    gates = []
    for data in listed["Gates"]:
        head = [(point["X"], point["Y"]) for point in data["GridPoints"]]
        direction = data["Direction"]
        step_x, step_y = STEPS[direction]
        points = start_side(head, direction)
        layers = []
        for layer in range(1, data["Length"] + 1):
            cells = [
                gridx.cell_of(grid, x + step_x * layer, y + step_y * layer)
                for x, y in points
                if inside(grid, x + step_x * layer, y + step_y * layer)
            ]
            layers.append(cells)
        gate = {
            "target": -1,
            "head": [gridx.cell_of(grid, x, y) for x, y in head if inside(grid, x, y)],
            "points": [[x, y] for x, y in points],
            "layers": layers,
            "direction": direction,
            "length": data["Length"],
            "count": data["Count"],
            "bar": data["Length"],
        }
        target = gridx.make_target(NUMBER, data["Material"], data["Count"])
        gridx.add(grid, target, cells_of(gate))
        gate["target"] = target.id
        gates.append(gate)
    state.features[NUMBER] = {"gates": gates}


def cells_of(gate: dict) -> list[int]:
    """The head's cells, then the bar's layers nearest the head first."""
    cells = list(gate["head"])
    for layer in gate["layers"][: gate["bar"]]:
        cells.extend(layer)
    return cells


def on_hit(state: base.State, target: gridx.Target, damage: int, source: t.Any) -> None:
    """A shot lands on any cell of the gate: it loses health, the bar is recomputed at once, and at 0 the gate is
    gone."""
    gate = next(g for g in state.features[NUMBER]["gates"] if g["target"] == target.id)
    target.health = max(0, target.health - damage)
    cell = -1 if source is None else source.cell
    base.emit(state, "hit", {"target": target.id, "cell": cell, "health": target.health})
    bar = bar_layers(target.health, gate["count"], gate["length"])
    if bar != gate["bar"]:
        gate["bar"] = bar
        base.emit(state, "gate_pull", {"target": target.id, "bar": bar, "health": target.health})
        if target.health > 0:
            gridx.move(state.grid, target, cells_of(gate))
    if target.health > 0:
        return
    target.dead = True
    gridx.remove(state.grid, target)
    base.emit(state, "target_died", {"target": target.id, "owner": NUMBER})
    checks.request_win_check(state)


def remaining_hits(state: base.State, color: int) -> int:
    """The hits the living gates of this color still take."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return 0
    total = 0
    for gate in mine["gates"]:
        target = state.grid.targets[gate["target"]]
        if not target.dead and target.color == color:
            total += target.health
    return total


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["gates"]))
    for gate in mine["gates"]:
        target = state.grid.targets[gate["target"]]
        h = base.mix(base.mix(base.mix(h, target.health), gate["bar"]), int(target.dead))
    return h
