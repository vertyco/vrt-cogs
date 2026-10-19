"""Feature 16, the Biscuit: a block that any pig color can hit, standing over cubes until it is shot to pieces.

It is a "match all" target (BiscuitFeature$$Awake, RVA 0x55A298C: the hit target takes every material) with one pool
of LayerCount x LayerHealth hits (SetCapacity, RVA 0x55A41A0); the layers are drawing only. It is an obstacle and a
hit target at once, so the obstacle filter keeps it: a pig whose line meets it shoots the biscuit and cannot reach
the cubes under or beyond it. At 0 it is gone and its cells are free (OnHitTargetDamaged, RVA 0x55A77AC, which only
redraws the layers). It is no IRemovablePixelGridObstacle, so the Obstacles revive leaves it. Its hits belong to no
color, so no color's remaining hits count them. web/sim/features/biscuit.js mirrors this file.
"""

from __future__ import annotations

import typing as t

from .. import base, checks
from .. import grid as gridx

NUMBER = 16


def setup(state: base.State) -> None:
    """Every biscuit as a record, in file order, with its body standing on its cells."""
    listed = state.level.features.get("biscuits")
    if not listed or not listed["Biscuits"]:
        return
    grid = state.grid
    biscuits = []
    for data in listed["Biscuits"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        total = data["LayerCount"] * data["LayerHealth"]
        body = gridx.make_target(NUMBER, -1, total, obstacle=True, hittable=True)
        body.match_all = True
        body.free_shot = True
        gridx.add(grid, body, cells)
        biscuits.append(
            {"target": body.id, "layers": data["LayerCount"], "layer_health": data["LayerHealth"], "total": total}
        )
    state.features[NUMBER] = {"biscuits": biscuits}


def on_hit(state: base.State, target: gridx.Target, damage: int, source: t.Any) -> None:
    """A shot lands on a biscuit: the pool loses health, and at 0 the biscuit is gone and its cells are free."""
    target.health = max(0, target.health - damage)
    cell = -1 if source is None else source.cell
    base.emit(state, "hit", {"target": target.id, "cell": cell, "health": target.health})
    if target.health > 0:
        return
    target.dead = True
    gridx.remove(state.grid, target)
    base.emit(state, "target_died", {"target": target.id, "owner": NUMBER})
    base.emit(state, "biscuit_gone", {"target": target.id})
    checks.request_win_check(state)


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["biscuits"]))
    for biscuit in mine["biscuits"]:
        body = state.grid.targets[biscuit["target"]]
        h = base.mix(base.mix(h, body.health), int(body.dead))
    return h
