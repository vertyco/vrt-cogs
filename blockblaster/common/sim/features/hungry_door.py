"""Feature 15, Hungry Doors: an obstacle over a patch of cubes that is fed by the cubes of its own color dying.

Every death of a single-cell cube of the door's color anywhere takes 1 off every door of that color that isn't already
doomed (PixelColorDoorFeatureController$$OnTargetDeath, RVA 0x56CF8C0, skips big cubes; DamageDoors, RVA 0x56CF064,
skips a door whose pending damage is already lethal, PixelColorDoorFeature$$IsLethalDamage, RVA 0x56CA31C). The damage
is pending at once and lands when a copy of the cube finishes its jump into the door, CUBE_FLY_IN ticks later
(DamageDoor, RVA 0x56CA870, with AddPendingDamage, RVA 0x56CA270, and the callback <DamageDoor>b__0 calling Damage).
When the health reaches 0 the door opens (gea, RVA 0x56CA480, then OpenDoor, RVA 0x56CA3D0) and its cells are free at
once. Until the open animation ends the stuck check waits, and so it does while any cube is still on its way in. The
door implements IRemovablePixelGridObstacle, so the Obstacles revive opens it too (MapRescueController
.<RemoveAllObstacles>d__29). Shots never hit a door. web/sim/features/hungry_door.js mirrors this file.
"""

from __future__ import annotations

from .. import base
from .. import grid as gridx
from ..numbers import CUBE_FLY_IN, DOOR_OPEN

NUMBER = 15


def setup(state: base.State) -> None:
    """Every door as a record, in file order, with its body standing on its cells as an obstacle."""
    listed = state.level.features.get("pixelColorDoors")
    if not listed or not listed["Doors"]:
        return
    grid = state.grid
    doors = []
    for data in listed["Doors"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        body = gridx.make_target(NUMBER, -1, data["Health"], obstacle=True, hittable=False)
        gridx.add(grid, body, cells)
        doors.append(
            {
                "target": body.id,
                "color": data["Material"],
                "start": data["Health"],
                "cells": cells,
                "pending": 0,
                "opening": False,
            }
        )
    state.features[NUMBER] = {"doors": doors}


def on_event(state: base.State, name: str, data: dict) -> None:
    """A single-cell cube died: every door of its color that isn't doomed gets 1 damage on its way."""
    mine = state.features.get(NUMBER)
    if mine is None or name != "cube_died" or not data["single"]:
        return
    for index, door in enumerate(mine["doors"]):
        body = state.grid.targets[door["target"]]
        if door["color"] != data["color"] or body.dead or body.health - door["pending"] <= 0:
            continue
        door["pending"] += 1
        base.schedule(state, CUBE_FLY_IN, "door_land", index)
        base.emit(state, "door_feed", {"door": index, "cell": data["cell"], "color": data["color"]})


def door_land(state: base.State, index: int) -> None:
    """Timer: the cube copy lands in the door, which loses 1 health and opens at 0."""
    door = state.features[NUMBER]["doors"][index]
    body = state.grid.targets[door["target"]]
    door["pending"] = max(0, door["pending"] - 1)
    if body.dead:
        return
    body.health -= 1
    base.emit(state, "door_hit", {"door": index, "target": body.id, "health": body.health})
    if body.health <= 0:
        open_door(state, index, "cubes")


def door_done(state: base.State, index: int) -> None:
    """Timer: the open animation is over."""
    state.features[NUMBER]["doors"][index]["opening"] = False


def open_door(state: base.State, index: int, why: str) -> None:
    """The door is gone from the picture and its cells are free at once. The hit event makes keys and Surprise Pixels
    look at the picture again."""
    door = state.features[NUMBER]["doors"][index]
    body = state.grid.targets[door["target"]]
    body.health = 0
    body.dead = True
    gridx.remove(state.grid, body)
    door["opening"] = True
    base.schedule(state, DOOR_OPEN, "door_done", index)
    base.emit(state, "door_open", {"door": index, "target": body.id, "why": why})
    base.emit(state, "hit", {"target": body.id, "cell": -1, "health": 0})


base.register_timer("door_land", base.PHASE_FEATURES, door_land)
base.register_timer("door_done", base.PHASE_FEATURES, door_done)


def busy(state: base.State) -> bool:
    """Cubes on their way into a door, or a door still opening, hold the stuck check."""
    mine = state.features.get(NUMBER)
    return mine is not None and any(door["pending"] > 0 or door["opening"] for door in mine["doors"])


def revive(state: base.State, name: str) -> int:
    """The Obstacles revive opens every standing door, in file order. Returns the ticks the revive waits (none)."""
    mine = state.features.get(NUMBER)
    if name != "obstacles" or mine is None:
        return 0
    for index, door in enumerate(mine["doors"]):
        if not state.grid.targets[door["target"]].dead:
            open_door(state, index, "revive")
    return 0


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["doors"]))
    for door in mine["doors"]:
        body = state.grid.targets[door["target"]]
        h = base.mix(base.mix(h, body.health), int(body.dead))
        h = base.mix(base.mix(h, door["pending"]), int(door["opening"]))
    return h
