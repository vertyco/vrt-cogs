"""Feature 7, the Surprise Pixel: a cube drawn blank until a side neighbor is connected to the outside.

Only the drawing changes. The cube keeps its real color and health the whole time, so pigs shoot it by that color like
any cube (SurprisePixelFeature$$AttachInternal, RVA 0x57F6E24); the one rule that reads the hidden list is the Super
Shooter, which skips hidden cubes (hides_cube). A cube is revealed for good when one of the four cells beside its own
that lie inside the grid is reached by the edge flood; diagonals don't count, and standing on the border alone doesn't.
A big cube is revealed when any of its cells has such a neighbor (SurprisePixelFeatureController$$HandlePixelReveals,
RVA 0x57F86C0, takes every Surprise Pixel on the cells PixelGridController$$GetObjectsCanReachOutside, RVA 0x6644968,
returns: the cells with a reached side neighbor). The check runs at level start, and at the end of a
tick after any hit and after the outside triggers (a booster or a revive finished). web/sim/features/surprise_pixel.js
mirrors this file.
"""

from __future__ import annotations

from .. import base
from .. import grid as gridx
from ..mathx import idiv

NUMBER = 7

# Events after which the reveal check runs at the end of the tick
CHECK_AFTER = ("hit", "booster_done", "revive_done", "walls_removed")


def setup(state: base.State) -> None:
    """The listed cubes start hidden, as cube ids in file order."""
    listed = state.level.features.get("surprisePixels")
    if not listed or not listed["Pixels"]:
        return
    grid = state.grid
    hidden: list[int] = []
    for point in listed["Pixels"]:
        x, y = point["X"], point["Y"]
        if not (0 <= x < grid.width and 0 <= y < grid.height):
            continue
        cell = gridx.cell_of(grid, x, y)
        for target in gridx.at(grid, cell):
            if target.owner == 0:
                if target.id not in hidden:
                    hidden.append(target.id)
                break
    state.features[NUMBER] = {"hidden": hidden, "pending": False}


def ready(state: base.State) -> None:
    """Level start, once every feature has put its parts on the picture: cubes already beside the outside show their
    color from the first frame."""
    if NUMBER in state.features:
        check(state, False)


def beside_outside(state: base.State, cube: gridx.Target, reach: list[int]) -> bool:
    """Any cell of the cube has a side neighbor, inside the grid, that the edge flood reaches."""
    grid = state.grid
    for cell in cube.cells:
        x = cell % grid.width
        y = idiv(cell, grid.width)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < grid.width and 0 <= ny < grid.height and reach[gridx.cell_of(grid, nx, ny)]:
                return True
    return False


def check(state: base.State, announce: bool) -> None:
    """Reveal every hidden cube with a side neighbor connected to the outside; a cube that already broke just leaves
    the list."""
    mine = state.features[NUMBER]
    reach = gridx.reach_outside(state.grid)
    keep = []
    shown = []
    for cube_id in mine["hidden"]:
        cube = state.grid.targets[cube_id]
        if cube.dead:
            continue
        if beside_outside(state, cube, reach):
            shown.append(cube_id)
        else:
            keep.append(cube_id)
    mine["hidden"] = keep
    if announce:
        for cube_id in shown:
            base.emit(state, "pixel_revealed", {"cube": cube_id})


def on_event(state: base.State, name: str, data: dict) -> None:  # noqa: ARG001
    if NUMBER in state.features and name in CHECK_AFTER:
        state.features[NUMBER]["pending"] = True


def release(state: base.State) -> None:
    """End of tick: when something asked for it, check the hidden cubes."""
    mine = state.features.get(NUMBER)
    if mine is None or not mine["pending"]:
        return
    mine["pending"] = False
    check(state, True)


def hides_cube(state: base.State, cube: gridx.Target) -> bool:
    """A hidden cube is skipped by the Super Shooter."""
    mine = state.features.get(NUMBER)
    return mine is not None and cube.id in mine["hidden"]


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["hidden"]))
    for cube_id in mine["hidden"]:
        h = base.mix(h, cube_id)
    return base.mix(h, int(mine["pending"]))
