"""Feature 10, the Egg Box: eggs of different colors sharing one box, every egg a target of its own.

Each egg is a target of its color with health Count, standing on every cell of the box (EggBoxFeature$$AttachInternal,
RVA 0x566430C; EggBoxEggInstance$$get_OccupiedPoints, RVA 0x5662DD8). So at a box cell first in line a pig can hit
any living egg of its color, and the eggs take hits in parallel, in no order. While any egg lives, the box's cells are
solid for every color, since each living egg is a solid hit target on them. The box is gone when the last egg breaks
(OnEggDamaged, RVA 0x5661B84), which frees its cells. An egg whose Count is 0 is hidden at once: it starts dead.
Cells outside the picture are left out. web/sim/features/egg_box.js mirrors this file.
"""

from __future__ import annotations

import typing as t

from .. import base, checks
from .. import grid as gridx

NUMBER = 10


def setup(state: base.State) -> None:
    """Every box as a record, in file order, with one target per egg standing on all of the box's cells."""
    listed = state.level.features.get("eggBoxes")
    if not listed or not listed["EggBoxes"]:
        return
    grid = state.grid
    boxes = []
    for data in listed["EggBoxes"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        eggs = []
        for egg in data["Eggs"]:
            target = gridx.make_target(NUMBER, egg["Material"], egg["Count"])
            if egg["Count"] > 0:
                gridx.add(grid, target, cells)
            else:
                target.dead = True
                gridx.add(grid, target, [])
            eggs.append(target.id)
        boxes.append({"cells": cells, "eggs": eggs, "gone": not any(grid.targets[i].cells for i in eggs)})
    state.features[NUMBER] = {"boxes": boxes}


def on_hit(state: base.State, target: gridx.Target, damage: int, source: t.Any) -> None:
    """A shot lands on an egg: it loses health, and at 0 it breaks and leaves the box; the last egg takes the box
    with it."""
    target.health = max(0, target.health - damage)
    cell = -1 if source is None else source.cell
    base.emit(state, "hit", {"target": target.id, "cell": cell, "health": target.health})
    if target.health > 0:
        return
    target.dead = True
    gridx.remove(state.grid, target)
    base.emit(state, "target_died", {"target": target.id, "owner": NUMBER})
    box = next(b for b in state.features[NUMBER]["boxes"] if target.id in b["eggs"])
    if not box["gone"] and all(state.grid.targets[i].dead for i in box["eggs"]):
        box["gone"] = True
        base.emit(state, "egg_box_gone", {"cells": list(box["cells"])})
    checks.request_win_check(state)


def remaining_hits(state: base.State, color: int) -> int:
    """The hits the living eggs of this color still take."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return 0
    total = 0
    for box in mine["boxes"]:
        for egg_id in box["eggs"]:
            target = state.grid.targets[egg_id]
            if not target.dead and target.color == color:
                total += target.health
    return total


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["boxes"]))
    for box in mine["boxes"]:
        h = base.mix(h, len(box["eggs"]))
        for egg_id in box["eggs"]:
            target = state.grid.targets[egg_id]
            h = base.mix(base.mix(h, target.health), int(target.dead))
    return h
