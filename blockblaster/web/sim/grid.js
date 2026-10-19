// The picture's cells and everything standing on them.
// Cells are numbered y * width + x, with x to the right and y up the screen. A target is anything a pig can hit or
// that blocks a line of fire: every cube, and every feature's hittable or blocking part. A big cube is one target that
// sits in every cell it covers. common/sim/grid.py mirrors this file function for function.
import { idiv } from "./mathx.js";

export const AXIS_ROW = 0; // a line is a row (fixed y), scanned along x; Left and Right pigs fire along rows
export const AXIS_COLUMN = 1; // a line is a column (fixed x), scanned along y; Bottom and Top pigs fire along columns
export const FROM_START = 0; // scan from index 0 (Left, Bottom)
export const FROM_END = 1; // scan from the far index (Right, Top)

export const NO_CELL = -1;
export const UNKNOWN = -2;

// owner: 0 for a cube, else the feature number. id: index in grid.targets, set by add. color: -1 for none.
// colors: a feature's color set, or null. matchAll: takes every color (Biscuits, Rockets). cells: the cells it stands
// on now, empty once removed. obstacle: an active obstacle (IObstacle). pending: damage of shots in flight at it
// (HitTarget's pending damage list). claimed: a shot in flight will kill it, so no pig aims at it
// (ShootersOffenseController$$ClaimTargetDead). freeShot: shots at it cost no ammo (IFreeShootTarget: Biscuits,
// Rockets)
export function makeTarget(owner, color, health, obstacle = false, hittable = true) {
  return {
    owner,
    id: -1,
    color,
    colors: null,
    matchAll: false,
    health,
    cells: [],
    obstacle,
    hittable,
    dead: false,
    pending: 0,
    claimed: false,
    freeShot: false,
  };
}

// The picture with every cube placed, in the level's cube order (target id = cube index)
export function newGrid(level) {
  const width = level.width;
  const height = level.height;
  const grid = {
    width,
    height,
    size: idiv(level.pw, Math.max(width, height)), // cube size in L
    targets: [],
    cells: [], // target ids per cell, cubes first
    firsts: new Array(2 * height + 2 * width).fill(UNKNOWN), // firstSolid cache, see lineSlot
    reach: null, // reachOutside cache
  };
  for (let cell = 0; cell < width * height; cell++) {
    grid.cells.push([]);
  }
  for (const [x, y, color, ax, ay, health] of level.cubes) {
    const cube = makeTarget(0, color, health);
    const cells = [];
    for (let cx = x; cx < x + ax; cx++) {
      for (let cy = y; cy < y + ay; cy++) {
        cells.push(cellOf(grid, cx, cy));
      }
    }
    add(grid, cube, cells);
  }
  return grid;
}

export function cellOf(grid, x, y) {
  return y * grid.width + x;
}

// Column x's center in picture space, L
export function centerX(grid, x) {
  return idiv((2 * x - (grid.width - 1)) * grid.size, 2);
}

// Row y's center in picture space, L
export function centerY(grid, y) {
  return idiv((2 * y - (grid.height - 1)) * grid.size, 2);
}

// A cell's center in picture space, L (PixelGridController$$GridToWorldPoint, RVA 0x54BCD40)
export function cellCenter(grid, cell) {
  return [centerX(grid, cell % grid.width), centerY(grid, idiv(cell, grid.width))];
}

// Stops a line of fire: an active obstacle or a living hit target (TargetableExtensions$$IsSolid)
export function isSolid(target) {
  return target.obstacle || (target.hittable && !target.dead);
}

export function cellSolid(grid, cell) {
  for (const targetId of grid.cells[cell]) {
    if (isSolid(grid.targets[targetId])) {
      return true;
    }
  }
  return false;
}

// Everything on a cell, cubes first, then the rest in the order they arrived
export function at(grid, cell) {
  return grid.cells[cell].map((targetId) => grid.targets[targetId]);
}

export function place(grid, target, cell) {
  const occupants = grid.cells[cell];
  if (target.owner !== 0) {
    occupants.push(target.id);
    return;
  }
  let index = 0;
  while (index < occupants.length && grid.targets[occupants[index]].owner === 0) {
    index += 1;
  }
  occupants.splice(index, 0, target.id);
}

// Give the target its id and stand it on the cells
export function add(grid, target, cells) {
  target.id = grid.targets.length;
  grid.targets.push(target);
  target.cells = [...cells];
  for (const cell of target.cells) {
    place(grid, target, cell);
  }
  changed(grid, target.cells);
  return target;
}

export function remove(grid, target) {
  const old = target.cells;
  for (const cell of old) {
    const occupants = grid.cells[cell];
    occupants.splice(occupants.indexOf(target.id), 1);
  }
  target.cells = [];
  changed(grid, old);
}

export function move(grid, target, cells) {
  const old = target.cells;
  remove(grid, target);
  target.cells = [...cells];
  for (const cell of target.cells) {
    place(grid, target, cell);
  }
  changed(grid, [...old, ...target.cells]);
}

// Forget what was worked out about these cells' lines. Call it whenever a target on them turns solid or not
export function changed(grid, cells) {
  for (const cell of cells) {
    const x = cell % grid.width;
    const y = idiv(cell, grid.width);
    const row = lineSlot(grid, AXIS_ROW, y, FROM_START);
    const column = lineSlot(grid, AXIS_COLUMN, x, FROM_START);
    grid.firsts[row] = UNKNOWN;
    grid.firsts[row + 1] = UNKNOWN;
    grid.firsts[column] = UNKNOWN;
    grid.firsts[column + 1] = UNKNOWN;
  }
  if (cells.length) {
    grid.reach = null;
  }
}

// Where firstSolid keeps a line's answer: rows first, then columns, two sides each
export function lineSlot(grid, axis, line, side) {
  if (axis === AXIS_ROW) {
    return 2 * line + side;
  }
  return 2 * grid.height + 2 * line + side;
}

export function lineCells(grid, axis, line, side) {
  const cells = [];
  if (axis === AXIS_ROW) {
    for (let x = 0; x < grid.width; x++) {
      cells.push(line * grid.width + x);
    }
  } else {
    for (let y = 0; y < grid.height; y++) {
      cells.push(y * grid.width + line);
    }
  }
  if (side === FROM_END) {
    cells.reverse();
  }
  return cells;
}

// The first cell on a line holding anything solid, scanning from one side, or NO_CELL
// (ShootersOffenseController$$FirstSolidsFromSideAxis, RVA 0x5456C0C)
export function firstSolid(grid, axis, line, side) {
  const slot = lineSlot(grid, axis, line, side);
  if (grid.firsts[slot] !== UNKNOWN) {
    return grid.firsts[slot];
  }
  let found = NO_CELL;
  for (const cell of lineCells(grid, axis, line, side)) {
    if (cellSolid(grid, cell)) {
      found = cell;
      break;
    }
  }
  grid.firsts[slot] = found;
  return found;
}

// 1 for every cell the edge flood reaches, else 0: from every non-solid border cell, spread up, down, left and right
// through non-solid cells (PixelGridController$$TryEnqueueReach, RVA 0x54C1514)
export function reachOutside(grid) {
  if (grid.reach !== null) {
    return grid.reach;
  }
  const width = grid.width;
  const height = grid.height;
  const reached = new Array(width * height).fill(0);
  const queue = [];
  for (const cell of borderCells(grid)) {
    if (!reached[cell] && !cellSolid(grid, cell)) {
      reached[cell] = 1;
      queue.push(cell);
    }
  }
  let index = 0;
  while (index < queue.length) {
    const cell = queue[index];
    index += 1;
    const x = cell % width;
    const y = idiv(cell, width);
    for (const [nx, ny] of [
      [x + 1, y],
      [x - 1, y],
      [x, y + 1],
      [x, y - 1],
    ]) {
      if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
        const near = ny * width + nx;
        if (!reached[near] && !cellSolid(grid, near)) {
          reached[near] = 1;
          queue.push(near);
        }
      }
    }
  }
  grid.reach = reached;
  return reached;
}

export function borderCells(grid) {
  const width = grid.width;
  const height = grid.height;
  const cells = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (x === 0 || y === 0 || x === width - 1 || y === height - 1) {
        cells.push(y * width + x);
      }
    }
  }
  return cells;
}
