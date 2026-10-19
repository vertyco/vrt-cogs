"""Feature 12, Ice Blocks: an obstacle that cracks as single-cell cubes die and breaks all at once.

Every death of a single-cell cube anywhere, of any color, takes 1 off every ice block at once; big cubes don't count
(PixelIceBlockFeatureController$$OnTargetDeath, RVA 0x56DCC88, which adds 1 to its pending count unless the dead
target is a big cube and then runs ExecuteIceDamage, RVA 0x56DB658, in the same call; each block takes the whole
pending count through PixelIceBlockFeature$$Damage, RVA 0x56D5E9C). Shots never hit the ice. A block stands on its cells
as an obstacle (shots stop at it and the cubes under it can't be hit) until its health reaches 0 and it breaks
(PixelIceBlockFeature$$OnDamage, RVA 0x56D97D4: a hit with health left plays the hit effect, otherwise the shatter).
The block is an IRemovablePixelGridObstacle, so the Obstacles revive removes it (MapRescueController
.<RemoveAllObstacles>d__29 walks every such obstacle). BlockSize is drawing only. web/sim/features/ice_block.js
mirrors this file.
"""

from __future__ import annotations

from .. import base
from .. import grid as gridx

NUMBER = 12


def setup(state: base.State) -> None:
    """Every ice block as a record, in file order, with its body standing on its cells as an obstacle."""
    listed = state.level.features.get("pixelIceBlocks")
    if not listed or not listed["IceBlocks"]:
        return
    grid = state.grid
    blocks = []
    for data in listed["IceBlocks"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        body = gridx.make_target(NUMBER, -1, data["Health"], obstacle=True, hittable=False)
        gridx.add(grid, body, cells)
        blocks.append({"target": body.id, "size": data["BlockSize"], "start": data["Health"], "cells": cells})
    state.features[NUMBER] = {"blocks": blocks}


def on_event(state: base.State, name: str, data: dict) -> None:
    """A single-cell cube died: every standing block loses 1, and breaks at 0."""
    if name != "cube_died" or NUMBER not in state.features or not data["single"]:
        return
    for block in state.features[NUMBER]["blocks"]:
        body = state.grid.targets[block["target"]]
        if body.dead:
            continue
        body.health -= 1
        if body.health > 0:
            base.emit(state, "ice_hit", {"target": body.id, "health": body.health})
        else:
            body.health = 0
            shatter(state, body, "cubes")


def shatter(state: base.State, body: gridx.Target, why: str) -> None:
    """The block is gone from the picture and its cells are free at once."""
    body.dead = True
    gridx.remove(state.grid, body)
    base.emit(state, "ice_gone", {"target": body.id, "why": why})


def revive(state: base.State, name: str) -> int:
    """The Obstacles revive breaks every standing block, in file order. Returns the ticks the revive waits (none)."""
    mine = state.features.get(NUMBER)
    if name != "obstacles" or mine is None:
        return 0
    for block in mine["blocks"]:
        body = state.grid.targets[block["target"]]
        if not body.dead:
            body.health = 0
            shatter(state, body, "revive")
    return 0


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["blocks"]))
    for block in mine["blocks"]:
        body = state.grid.targets[block["target"]]
        h = base.mix(base.mix(h, body.health), int(body.dead))
    return h
