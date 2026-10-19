"""Feature 17, the Rocket: a start part and an end part joined by a light path; shots pull the parts together along
the path until they meet and the rocket launches.

The path runs from each control square's first point (its lowest corner) one cell at a time to the next square's, x
or y only (a step that changes both is skipped), and ends on the last square's first point; each point is the corner
of one slice StartEndArea in size (UpdateObstacleGridPoints, RVA 0x57DD844). Health is slices / SegmentDecreasePerHit
less (max(area) + 1), at least 0 (CalculateAndSetHealth, RVA 0x57E04A8). The start part stands on the first
area-many cells walking up the slices from its index, the end part on the first area-many walking down from its own
(GetStartHitTargetPoints, RVA 0x57DF460; GetEndHitTargetPoints, RVA 0x57DF6C0). Both parts share one hit target, a
"match all" free-shot target that is no obstacle (SplitObjectHitTarget: IHitTarget, IFreeShootTarget). The light path
is every cell of the slices from the start index to the end index that neither part covers, or the start part's
cells when that leaves nothing; it is an obstacle with nothing to hit (SplitObjectFeature: IObstacle,
EnsureOccupiedCache, RVA 0x57DFF14), so a line of fire that meets it first is blocked.

A hit at a cell of the start part moves it one slice forward, at the end part one slice back, and anywhere else (a
part moved while the shot flew, or damage from no cell, which counts as the start) moves the nearer part, the start on
ties (OnHitTargetDamaged, RVA 0x57E2B48: each hit moves SegmentDecreasePerHit slices whatever its damage). At 0 the
rocket detaches from the picture at once and launches (LaunchRocket's state machine calls Detach before the
animation). When the auto-finisher starts, every rocket with health left takes half of it at its start part and the
rest at its end part, which kills it (FinishAttachable, RVA 0x57E8340). It is no IRemovablePixelGridObstacle, so the
Obstacles revive leaves it. web/sim/features/rocket.js mirrors this file.
"""

from __future__ import annotations

import typing as t

from .. import aim, base, checks
from .. import grid as gridx

NUMBER = 17

START = 0
END = 1


def origins_of(data: dict) -> list[list[int]]:
    """Every slice's corner along the path, in order."""
    squares = [square["GridPoints"][0] for square in data["GridPoints"]]
    if len(squares) == 1:
        return [[squares[0]["X"], squares[0]["Y"]]]
    points = []
    for a, b in zip(squares, squares[1:], strict=False):
        dx = b["X"] - a["X"]
        dy = b["Y"] - a["Y"]
        if dy != 0 and dx == 0:
            step = 1 if dy > 0 else -1
            points.extend([a["X"], a["Y"] + step * k] for k in range(abs(dy)))
        elif dy == 0 and dx != 0:
            step = 1 if dx > 0 else -1
            points.extend([a["X"] + step * k, a["Y"]] for k in range(abs(dx)))
    points.append([squares[-1]["X"], squares[-1]["Y"]])
    return points


def slices_of(grid: gridx.Grid, origins: list[list[int]], wide: int, tall: int) -> list[list[int]]:
    """Each slice's cells: the area's cells from its corner."""
    return [[gridx.cell_of(grid, x + i, y + j) for i in range(wide) for j in range(tall)] for x, y in origins]


def setup(state: base.State) -> None:
    """Every rocket as a record, in file order, with its parts and its light path standing on their cells."""
    listed = state.level.features.get("splitObjects")
    if not listed or not listed["SplitObjects"]:
        return
    grid = state.grid
    rockets = []
    for data in listed["SplitObjects"]:
        wide = data["StartEndArea"]["X"]
        tall = data["StartEndArea"]["Y"]
        slices = slices_of(grid, origins_of(data), wide, tall)
        per_hit = data["SegmentDecreasePerHit"]
        health = max(0, len(slices) // per_hit - (max(wide, tall) + 1))
        parts = gridx.make_target(NUMBER, -1, health)
        parts.match_all = True
        parts.free_shot = True
        path = gridx.make_target(NUMBER, -1, 0, obstacle=True, hittable=False)
        rocket = {
            "slices": slices,
            "area": wide * tall,
            "per_hit": per_hit,
            "start": 0,
            "end": len(slices) - 1,
            "parts": -1,
            "path": -1,
            "launched": False,
        }
        if health == 0:
            parts.dead = True
            gridx.add(grid, parts, [])
        else:
            gridx.add(grid, parts, part_cells(rocket, START) + part_cells(rocket, END))
        gridx.add(grid, path, path_cells(rocket))
        rocket["parts"] = parts.id
        rocket["path"] = path.id
        rockets.append(rocket)
    state.features[NUMBER] = {"rockets": rockets}


def part_cells(rocket: dict, part: int) -> list[int]:
    """The cells one part stands on: area-many distinct cells, walking the slices up from the start index or down
    from the end index."""
    slices = rocket["slices"]
    cells: list[int] = []
    index = rocket["start"] if part == START else rocket["end"]
    while 0 <= index < len(slices) and len(cells) < rocket["area"]:
        for cell in slices[index]:
            if len(cells) >= rocket["area"]:
                break
            if cell not in cells:
                cells.append(cell)
        index += 1 if part == START else -1
    return cells


def path_cells(rocket: dict) -> list[int]:
    """The light path: every cell of the slices from the start index to the end index that neither part covers, or
    the start part's cells when that leaves none."""
    start = part_cells(rocket, START)
    end = part_cells(rocket, END)
    cells: list[int] = []
    slices = rocket["slices"]
    for index in range(rocket["start"], min(rocket["end"] + 1, len(slices))):
        for cell in slices[index]:
            if cell not in start and cell not in end and cell not in cells:
                cells.append(cell)
    return cells or start


def rocket_of(state: base.State, target: gridx.Target) -> tuple[int, dict]:
    for index, rocket in enumerate(state.features[NUMBER]["rockets"]):
        if rocket["parts"] == target.id:
            return index, rocket
    raise ValueError(f"target {target.id} is no rocket's parts")


def nearest(grid: gridx.Grid, cells: list[int], cell: int) -> int:
    """The smallest squared cell distance from cell to any of cells (-1 for none)."""
    x, y = cell % grid.width, cell // grid.width
    best = -1
    for other in cells:
        dx = other % grid.width - x
        dy = other // grid.width - y
        distance = dx * dx + dy * dy
        if best < 0 or distance < best:
            best = distance
    return best


def part_hit(state: base.State, rocket: dict, cell: int | None) -> int | None:
    """Which part a hit at this cell moves: the part standing there, else the nearer one, the start on ties; None when
    neither part has a cell left."""
    if cell is None or cell < 0:
        return START
    start = part_cells(rocket, START)
    if cell in start:
        return START
    end = part_cells(rocket, END)
    if cell in end:
        return END
    if not start and not end:
        return None
    to_start = nearest(state.grid, start, cell)
    to_end = nearest(state.grid, end, cell)
    if to_end < 0 or (to_start >= 0 and to_start <= to_end):
        return START
    return END


def damage(state: base.State, index: int, rocket: dict, amount: int, cell: int | None) -> None:
    """The parts lose health and one part moves; at 0 the rocket launches, else the parts and the path stand anew."""
    grid = state.grid
    parts = grid.targets[rocket["parts"]]
    parts.health = max(0, parts.health - amount)
    part = part_hit(state, rocket, cell)
    if part == START:
        rocket["start"] = min(rocket["start"] + rocket["per_hit"], rocket["end"])
    elif part == END:
        rocket["end"] = max(rocket["end"] - rocket["per_hit"], rocket["start"])
    base.emit(state, "hit", {"target": parts.id, "cell": -1 if cell is None else cell, "health": parts.health})
    if parts.health == 0:
        launch(state, index, rocket)
        return
    gridx.move(grid, parts, part_cells(rocket, START) + part_cells(rocket, END))
    gridx.move(grid, grid.targets[rocket["path"]], path_cells(rocket))
    move = -1 if part is None else part
    base.emit(state, "rocket_move", {"rocket": index, "part": move, "start": rocket["start"], "end": rocket["end"]})


def launch(state: base.State, index: int, rocket: dict) -> None:
    """The parts meet and the rocket leaves: its parts and its path are gone from the picture at once."""
    grid = state.grid
    parts = grid.targets[rocket["parts"]]
    parts.dead = True
    rocket["launched"] = True
    gridx.remove(grid, parts)
    gridx.remove(grid, grid.targets[rocket["path"]])
    base.emit(state, "target_died", {"target": parts.id, "owner": NUMBER})
    base.emit(state, "rocket_launch", {"rocket": index, "start": rocket["start"], "end": rocket["end"]})
    checks.request_win_check(state)


def on_hit(state: base.State, target: gridx.Target, damage_done: int, source: t.Any) -> None:
    """A shot or a booster lands on a rocket's parts. A shot carries the cell it was aimed at; anything else counts
    as a hit at the start part."""
    index, rocket = rocket_of(state, target)
    damage(state, index, rocket, damage_done, None if source is None else source.cell)


def on_autofinish(state: base.State) -> None:
    """The auto-finisher started: every rocket with health left takes half of it at its start part and the rest at
    its end part, and launches."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return
    for index, rocket in enumerate(mine["rockets"]):
        parts = state.grid.targets[rocket["parts"]]
        if parts.dead or parts.health < 1:
            continue
        health = parts.health
        half = health // 2
        if half > 0:
            finish_hit(state, index, rocket, half, START)
        rest = health - half
        if rest > 0 and not parts.dead:
            finish_hit(state, index, rocket, rest, END)


def finish_hit(state: base.State, index: int, rocket: dict, amount: int, part: int) -> None:
    """Damage at one part's first cell, freeing pigs' reservations as a landing hit would."""
    cells = part_cells(rocket, part)
    if not cells:
        return
    parts = state.grid.targets[rocket["parts"]]
    aim.release(state, parts, cells[0])
    damage(state, index, rocket, amount, cells[0])
    if parts.dead:
        aim.release(state, parts, None)


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["rockets"]))
    for rocket in mine["rockets"]:
        parts = state.grid.targets[rocket["parts"]]
        h = base.mix(base.mix(h, rocket["start"]), rocket["end"])
        h = base.mix(base.mix(h, parts.health), int(parts.dead))
    return h
