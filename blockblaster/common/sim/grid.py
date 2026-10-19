"""The picture's cells and everything standing on them.

Cells are numbered y * width + x, with x to the right and y up the screen. A target is anything a pig can hit or that
blocks a line of fire: every cube, and every feature's hittable or blocking part. A big cube is one target that sits
in every cell it covers. web/sim/grid.js mirrors this file function for function.
"""

from dataclasses import dataclass, field

from .level import Level
from .mathx import idiv

AXIS_ROW = 0  # a line is a row (fixed y), scanned along x; Left and Right pigs fire along rows
AXIS_COLUMN = 1  # a line is a column (fixed x), scanned along y; Bottom and Top pigs fire along columns
FROM_START = 0  # scan from index 0 (Left, Bottom)
FROM_END = 1  # scan from the far index (Right, Top)

NO_CELL = -1
UNKNOWN = -2


@dataclass
class Target:
    owner: int  # 0 for a cube, else the feature number
    id: int  # index in grid.targets, set by add
    color: int  # -1 for none
    colors: list[int] | None  # a feature's color set, or None
    match_all: bool  # takes every color (Biscuits, Rockets)
    health: int
    cells: list[int]  # the cells it stands on now, empty once removed
    obstacle: bool  # an active obstacle (IObstacle)
    hittable: bool
    dead: bool
    pending: int = 0  # damage of shots in flight at it (HitTarget's pending damage list)
    claimed: bool = False  # a shot in flight will kill it, so no pig aims at it (RVA 0x5452704)
    free_shot: bool = False  # shots at it cost no ammo (IFreeShootTarget: Biscuits, Rockets)


@dataclass
class Grid:
    width: int
    height: int
    size: int  # cube size in L
    targets: list[Target] = field(default_factory=list)
    cells: list[list[int]] = field(default_factory=list)  # target ids per cell, cubes first
    firsts: list[int] = field(default_factory=list)  # first_solid cache, see line_slot
    reach: list[int] | None = None  # reach_outside cache


def make_target(owner: int, color: int, health: int, obstacle: bool = False, hittable: bool = True) -> Target:
    return Target(
        owner=owner,
        id=-1,
        color=color,
        colors=None,
        match_all=False,
        health=health,
        cells=[],
        obstacle=obstacle,
        hittable=hittable,
        dead=False,
    )


def new_grid(level: Level) -> Grid:
    """The picture with every cube placed, in the level's cube order (target id = cube index)."""
    width, height = level.width, level.height
    grid = Grid(width=width, height=height, size=idiv(level.pw, max(width, height)))
    grid.cells = [[] for _ in range(width * height)]
    grid.firsts = [UNKNOWN] * (2 * height + 2 * width)
    for x, y, color, ax, ay, health in level.cubes:
        cube = make_target(0, color, health)
        add(grid, cube, [cell_of(grid, cx, cy) for cx in range(x, x + ax) for cy in range(y, y + ay)])
    return grid


def cell_of(grid: Grid, x: int, y: int) -> int:
    return y * grid.width + x


def center_x(grid: Grid, x: int) -> int:
    """Column x's center in picture space, L."""
    return idiv((2 * x - (grid.width - 1)) * grid.size, 2)


def center_y(grid: Grid, y: int) -> int:
    """Row y's center in picture space, L."""
    return idiv((2 * y - (grid.height - 1)) * grid.size, 2)


def cell_center(grid: Grid, cell: int) -> tuple[int, int]:
    """A cell's center in picture space, L (PixelGridController$$GridToWorldPoint, RVA 0x54BCD40)."""
    return center_x(grid, cell % grid.width), center_y(grid, idiv(cell, grid.width))


def is_solid(target: Target) -> bool:
    """Stops a line of fire: an active obstacle or a living hit target (TargetableExtensions$$IsSolid)."""
    return target.obstacle or (target.hittable and not target.dead)


def cell_solid(grid: Grid, cell: int) -> bool:
    for target_id in grid.cells[cell]:
        if is_solid(grid.targets[target_id]):
            return True
    return False


def at(grid: Grid, cell: int) -> list[Target]:
    """Everything on a cell, cubes first, then the rest in the order they arrived."""
    return [grid.targets[target_id] for target_id in grid.cells[cell]]


def place(grid: Grid, target: Target, cell: int) -> None:
    occupants = grid.cells[cell]
    if target.owner != 0:
        occupants.append(target.id)
        return
    index = 0
    while index < len(occupants) and grid.targets[occupants[index]].owner == 0:
        index += 1
    occupants.insert(index, target.id)


def add(grid: Grid, target: Target, cells: list[int]) -> Target:
    """Give the target its id and stand it on the cells."""
    target.id = len(grid.targets)
    grid.targets.append(target)
    target.cells = list(cells)
    for cell in target.cells:
        place(grid, target, cell)
    changed(grid, target.cells)
    return target


def remove(grid: Grid, target: Target) -> None:
    old = target.cells
    for cell in old:
        grid.cells[cell].remove(target.id)
    target.cells = []
    changed(grid, old)


def move(grid: Grid, target: Target, cells: list[int]) -> None:
    old = target.cells
    remove(grid, target)
    target.cells = list(cells)
    for cell in target.cells:
        place(grid, target, cell)
    changed(grid, old + target.cells)


def changed(grid: Grid, cells: list[int]) -> None:
    """Forget what was worked out about these cells' lines. Call it whenever a target on them turns solid or not."""
    for cell in cells:
        x = cell % grid.width
        y = idiv(cell, grid.width)
        row = line_slot(grid, AXIS_ROW, y, FROM_START)
        column = line_slot(grid, AXIS_COLUMN, x, FROM_START)
        grid.firsts[row] = UNKNOWN
        grid.firsts[row + 1] = UNKNOWN
        grid.firsts[column] = UNKNOWN
        grid.firsts[column + 1] = UNKNOWN
    if cells:
        grid.reach = None


def line_slot(grid: Grid, axis: int, line: int, side: int) -> int:
    """Where first_solid keeps a line's answer: rows first, then columns, two sides each."""
    if axis == AXIS_ROW:
        return 2 * line + side
    return 2 * grid.height + 2 * line + side


def line_cells(grid: Grid, axis: int, line: int, side: int) -> list[int]:
    if axis == AXIS_ROW:
        cells = [line * grid.width + x for x in range(grid.width)]
    else:
        cells = [y * grid.width + line for y in range(grid.height)]
    if side == FROM_END:
        cells.reverse()
    return cells


def first_solid(grid: Grid, axis: int, line: int, side: int) -> int:
    """The first cell on a line holding anything solid, scanning from one side, or NO_CELL
    (ShootersOffenseController$$FirstSolidsFromSideAxis, RVA 0x5456C0C)."""
    slot = line_slot(grid, axis, line, side)
    if grid.firsts[slot] != UNKNOWN:
        return grid.firsts[slot]
    found = NO_CELL
    for cell in line_cells(grid, axis, line, side):
        if cell_solid(grid, cell):
            found = cell
            break
    grid.firsts[slot] = found
    return found


def reach_outside(grid: Grid) -> list[int]:
    """1 for every cell the edge flood reaches, else 0: from every non-solid border cell, spread up, down, left and
    right through non-solid cells (PixelGridController$$TryEnqueueReach, RVA 0x54C1514)."""
    if grid.reach is not None:
        return grid.reach
    width, height = grid.width, grid.height
    reached = [0] * (width * height)
    queue = []
    for cell in border_cells(grid):
        if not reached[cell] and not cell_solid(grid, cell):
            reached[cell] = 1
            queue.append(cell)
    index = 0
    while index < len(queue):
        cell = queue[index]
        index += 1
        x = cell % width
        y = idiv(cell, width)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height:
                near = ny * width + nx
                if not reached[near] and not cell_solid(grid, near):
                    reached[near] = 1
                    queue.append(near)
    grid.reach = reached
    return reached


def border_cells(grid: Grid) -> list[int]:
    width, height = grid.width, grid.height
    cells = []
    for y in range(height):
        for x in range(width):
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                cells.append(y * width + x)
    return cells
