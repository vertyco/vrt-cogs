"""Feature 9, the Wall: an obstacle that is never damaged and blocks the pigs' sight until it is removed.

Every wall is removed when the auto-finisher starts (WallFeatureController -> DetachAllWalls, RVA 0x581F98C, called
from MapAutoFinisherController$$OnAutoFinisherActivated, RVA 0x58CB6D8) and by the Obstacles revive
(RemoveAllObstacles). Removing a wall frees its cells at once. web/sim/features/wall.js mirrors this file.
"""

from __future__ import annotations

from .. import base
from .. import grid as gridx

NUMBER = 9


def setup(state: base.State) -> None:
    """Every wall as a record, in file order, with its body standing on its cells as an obstacle."""
    listed = state.level.features.get("walls")
    if not listed or not listed["Walls"]:
        return
    grid = state.grid
    walls = []
    for data in listed["Walls"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        body = gridx.make_target(NUMBER, -1, 1, obstacle=True, hittable=False)
        gridx.add(grid, body, cells)
        walls.append({"target": body.id})
    state.features[NUMBER] = {"walls": walls}


def remove_all(state: base.State, why: str) -> int:
    """Take every standing wall off the picture, in file order. Returns how many went."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return 0
    gone = 0
    for wall in mine["walls"]:
        body = state.grid.targets[wall["target"]]
        if body.dead:
            continue
        body.dead = True
        gridx.remove(state.grid, body)
        base.emit(state, "wall_gone", {"target": body.id, "why": why})
        gone += 1
    if gone:
        base.emit(state, "walls_removed", {"why": why})
    return gone


def on_autofinish(state: base.State) -> None:
    """The auto-finisher started: every wall goes."""
    remove_all(state, "autofinish")


def revive(state: base.State, name: str) -> int:
    """The Obstacles revive removes every wall. Returns the ticks the revive waits (none)."""
    if name == "obstacles":
        remove_all(state, "revive")
    return 0


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["walls"]))
    for wall in mine["walls"]:
        h = base.mix(h, int(state.grid.targets[wall["target"]].dead))
    return h
