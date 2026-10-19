"""Feature 6, the Pixel Pipe: a body on the picture that refills cubes from a queue of color groups.

The body is an obstacle that is never damaged and stays when the pipe is empty. Its front group is the first with
cubes left; the original keeps a queue and moves to the next group the moment the count reaches 0
(PixelPipeFeature$$GetMaterialFromCurrentGroup, RVA 0x5754344, then UpdateState, RVA 0x57532E0).

Refill on death: when a single-cell cube dies on a cell no pipe covers, the first pipe in file order that isn't busy
and whose front group has that color puts a new cube of that color into the dead cube's cell at once and counts down
(PixelPipeFeatureController$$TryToSpawnPixel, RVA 0x575EFA4; SpawnPixel, RVA 0x575BBBC).

Refill when a color runs out: right after each refill on death, a pipe checks its front color
(TryToSpawnAdditionalPixels, RVA 0x575DE80). With no single-cell cube of that color left on the picture it turns busy
and pushes cubes into the first Count cells that held that color in the level file (pixels order, GetSpawnPoints RVA
0x575D4E4), the first at once and then one every PIXEL_PIPE_REFILL ticks; after the last it is free again and checks
once more (PixelPipeFeature.<AutoSpawn>d__73$$MoveNext, RVA 0x575CD14). A run never skips a cell that is already
taken; the original doesn't either. Every level lists at least one file cell for each group's color, so the
original's fallback to random empty cells never runs.

The original pauses refills only while the Super Unicorn runs (the controller's spawnPaused is the "Merged Shooter Is
In Use" flag), and when that run ends every pipe that isn't busy checks its front color (Update, RVA 0x575E3FC, calls
SpawnMissingPixels on that edge only). Nothing else pauses them. web/sim/features/pixel_pipe.js mirrors this file.
"""

from __future__ import annotations

from .. import base
from .. import grid as gridx
from ..numbers import PIXEL_PIPE_REFILL

NUMBER = 6


def setup(state: base.State) -> None:
    """Every pipe as a record, in file order, with its body standing on its cells as an obstacle."""
    listed = state.level.features.get("pixelPipes")
    if not listed or not listed["Pipes"]:
        return
    grid = state.grid
    pipes = []
    for data in listed["Pipes"]:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        body = gridx.make_target(NUMBER, -1, 1, obstacle=True, hittable=False)
        gridx.add(grid, body, cells)
        pipes.append(
            {
                "target": body.id,
                "cells": cells,
                "groups": [[group["Material"], group["Count"]] for group in data["Queue"]],
                "busy": False,
                "points": [],  # the cells of the run in progress
                "next": 0,  # the next of them to fill
            }
        )
    state.features[NUMBER] = {"pipes": pipes}


def front(pipe: dict) -> list[int] | None:
    """The [color, count] group the pipe is giving from, or None once it is empty."""
    for group in pipe["groups"]:
        if group[1] > 0:
            return group
    return None


def under_pipe(state: base.State, cell: int) -> bool:
    """The cell is under a pipe (PixelPipeFeatureController$$IsOnAnyPipe, RVA 0x575DCF4)."""
    return any(cell in pipe["cells"] for pipe in state.features[NUMBER]["pipes"])


def on_event(state: base.State, name: str, data: dict) -> None:
    """A single-cell cube died: the first free pipe giving its color fills its cell again. Not while the Super Unicorn
    runs."""
    if name != "cube_died" or NUMBER not in state.features or not data["single"] or under_pipe(state, data["cell"]):
        return
    if state.unicorn["running"]:
        return
    for index, pipe in enumerate(state.features[NUMBER]["pipes"]):
        group = front(pipe)
        if pipe["busy"] or group is None or group[0] != data["color"]:
            continue
        spawn(state, index, data["cell"])
        group = front(pipe)
        # A pipe still giving the color it just placed has a cube of it on the picture, so only a new group can be
        # missing
        if group is not None and group[0] != data["color"]:
            top_up(state, index)
        return


def spawn(state: base.State, index: int, cell: int) -> None:
    """The pipe's front group gives one cube into the cell, in the grid at once (the jump there is a look)."""
    pipe = state.features[NUMBER]["pipes"][index]
    group = front(pipe)
    color = group[0]
    group[1] -= 1
    cube = gridx.add(state.grid, gridx.make_target(0, color, 1), [cell])
    # The new cube counts as one more the level has had, so the cleared share stays destroyed over all
    state.cubes_start += 1
    state.cubes_left += 1
    base.emit(state, "pipe_spawn", {"pipe": index, "cube": cube.id, "cell": cell, "color": color})


def singles_left(state: base.State, color: int) -> bool:
    """Some single-cell cube of this color is on the picture (PixelGridController$$GetPixelCountByMaterial with the
    controller's one-cell filter)."""
    for target in state.grid.targets:
        if target.owner == 0 and target.color == color and len(target.cells) == 1 and not target.dead:
            return True
    return False


def spawn_points(state: base.State, color: int, count: int) -> list[int]:
    """The first count cells holding this color in the level file, in its pixels order."""
    grid = state.grid
    cells = [gridx.cell_of(grid, x, y) for x, y, cube_color, _, _, _ in state.level.cubes if cube_color == color]
    return cells[:count]


def top_up(state: base.State, index: int) -> None:
    """With no single-cell cube of the front color left, start a run into that color's file cells."""
    pipe = state.features[NUMBER]["pipes"][index]
    group = front(pipe)
    if group is None or singles_left(state, group[0]):
        return
    points = spawn_points(state, group[0], group[1])
    if not points:
        return
    pipe["busy"] = True
    pipe["points"] = points
    pipe["next"] = 0
    run_step(state, index)


def run_step(state: base.State, index: int) -> None:
    """Timer too: the run fills its next cell; after the last the pipe is free and checks its front color again. The
    run's waits are UniTask waits resumed at PlayerLoopTiming.Update, so its later steps land at the start of a tick."""
    pipe = state.features[NUMBER]["pipes"][index]
    cell = pipe["points"][pipe["next"]]
    pipe["next"] += 1
    spawn(state, index, cell)
    if pipe["next"] < len(pipe["points"]):
        base.schedule(state, PIXEL_PIPE_REFILL, "pipe_run", index)
        return
    pipe["busy"] = False
    pipe["points"] = []
    pipe["next"] = 0
    top_up(state, index)


base.register_timer("pipe_run", base.PHASE_TAPS, run_step)


def unicorn_done(state: base.State) -> None:
    """The Super Unicorn's run ended: every pipe that isn't busy checks its front color (Update, RVA 0x575E3FC, calls
    SpawnMissingPixels on the frame the pause ends)."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return
    for index, pipe in enumerate(mine["pipes"]):
        if not pipe["busy"]:
            top_up(state, index)


def color_left(pipe: dict, color: int) -> int:
    """The cubes of this color still in the pipe's groups (PixelPipeFeature$$CountPixels)."""
    return sum(count for group_color, count in pipe["groups"] if group_color == color)


def unicorn_reserves(state: base.State, color: int) -> list[list]:
    """For the Super Unicorn: [pipe index, cells, tier, rank, hits] for every pipe still holding cubes of this color.
    Each pipe is one target per color whose health is that count (PixelPipeDrainer$$CollectTargets, RVA 0x5752A28),
    in the reserve tier 4 with no rank (MergedShooterFeatureTargetOrder$$IsPixelReserve)."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return []
    found = []
    for index, pipe in enumerate(mine["pipes"]):
        left = color_left(pipe, color)
        if left >= 1:
            found.append([index, list(pipe["cells"]), 4, 0, left])
    return found


def unicorn_reserve_left(state: base.State, index: int, color: int) -> int:
    return color_left(state.features[NUMBER]["pipes"][index], color)


def unicorn_pop(state: base.State, index: int, color: int) -> gridx.Target | None:
    """A Super Unicorn shot at the pipe's queue: the first group holding the color gives one cube, placed on the
    first of the pipe's cells with no cube (the first cell when all have one) for the shot to break
    (PixelPipeFeature$$DrainPixel, RVA 0x57506DC; TryTakePixel, RVA 0x57558B4; PixelPipeDrainer$$PopPixel, RVA
    0x5752420; TryFindFreePoint, RVA 0x5751384). None when the color ran out."""
    pipe = state.features[NUMBER]["pipes"][index]
    group = next((g for g in pipe["groups"] if g[1] > 0 and g[0] == color), None)
    if group is None or not pipe["cells"]:
        return None
    group[1] -= 1
    grid = state.grid
    cell = next((c for c in pipe["cells"] if not any(t.owner == 0 for t in gridx.at(grid, c))), pipe["cells"][0])
    cube = gridx.add(grid, gridx.make_target(0, color, 1), [cell])
    state.cubes_start += 1
    state.cubes_left += 1
    base.emit(state, "pipe_pop", {"pipe": index, "cube": cube.id, "cell": cell, "color": color})
    return cube


def remaining_hits(state: base.State, color: int) -> int:
    """The cubes of this color the pipes still hold."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return 0
    return sum(group[1] for pipe in mine["pipes"] for group in pipe["groups"] if group[0] == color)


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["pipes"]))
    for pipe in mine["pipes"]:
        h = base.mix(base.mix(base.mix(h, int(pipe["busy"])), pipe["next"]), len(pipe["points"]))
        for cell in pipe["points"]:
            h = base.mix(h, cell)
        for _, count in pipe["groups"]:
            h = base.mix(h, count)
    return h
