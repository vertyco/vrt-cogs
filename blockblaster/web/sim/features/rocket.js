// Feature 17, the Rocket: a start part and an end part joined by a light path; shots pull the parts together along
// the path until they meet and the rocket launches.
//
// The path runs from each control square's first point (its lowest corner) one cell at a time to the next square's, x
// or y only (a step that changes both is skipped), and ends on the last square's first point; each point is the corner
// of one slice StartEndArea in size (UpdateObstacleGridPoints, RVA 0x57DD844). Health is slices / SegmentDecreasePerHit
// less (max(area) + 1), at least 0 (CalculateAndSetHealth, RVA 0x57E04A8). The start part stands on the first
// area-many cells walking up the slices from its index, the end part on the first area-many walking down from its own
// (GetStartHitTargetPoints, RVA 0x57DF460; GetEndHitTargetPoints, RVA 0x57DF6C0). Both parts share one hit target, a
// "match all" free-shot target that is no obstacle (SplitObjectHitTarget: IHitTarget, IFreeShootTarget). The light path
// is every cell of the slices from the start index to the end index that neither part covers, or the start part's
// cells when that leaves nothing; it is an obstacle with nothing to hit (SplitObjectFeature: IObstacle,
// EnsureOccupiedCache, RVA 0x57DFF14), so a line of fire that meets it first is blocked.
//
// A hit at a cell of the start part moves it one slice forward, at the end part one slice back, and anywhere else (a
// part moved while the shot flew, or damage from no cell, which counts as the start) moves the nearer part, the start on
// ties (OnHitTargetDamaged, RVA 0x57E2B48: each hit moves SegmentDecreasePerHit slices whatever its damage). At 0 the
// rocket detaches from the picture at once and launches (LaunchRocket's state machine calls Detach before the
// animation). When the auto-finisher starts, every rocket with health left takes half of it at its start part and the
// rest at its end part, which kills it (FinishAttachable, RVA 0x57E8340). It is no IRemovablePixelGridObstacle, so the
// Obstacles revive leaves it. common/sim/features/rocket.py mirrors this file.
import * as aim from "../aim.js";
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";
import { idiv } from "../mathx.js";

export const NUMBER = 17;

export const START = 0;
export const END = 1;

// Every slice's corner along the path, in order
export function originsOf(data) {
  const squares = data.GridPoints.map((square) => square.GridPoints[0]);
  if (squares.length === 1) {
    return [[squares[0].X, squares[0].Y]];
  }
  const points = [];
  for (let i = 0; i + 1 < squares.length; i++) {
    const a = squares[i];
    const b = squares[i + 1];
    const dx = b.X - a.X;
    const dy = b.Y - a.Y;
    if (dy !== 0 && dx === 0) {
      const step = dy > 0 ? 1 : -1;
      for (let k = 0; k < Math.abs(dy); k++) {
        points.push([a.X, a.Y + step * k]);
      }
    } else if (dy === 0 && dx !== 0) {
      const step = dx > 0 ? 1 : -1;
      for (let k = 0; k < Math.abs(dx); k++) {
        points.push([a.X + step * k, a.Y]);
      }
    }
  }
  const last = squares[squares.length - 1];
  points.push([last.X, last.Y]);
  return points;
}

// Each slice's cells: the area's cells from its corner
export function slicesOf(grid, origins, wide, tall) {
  return origins.map(([x, y]) => {
    const cells = [];
    for (let i = 0; i < wide; i++) {
      for (let j = 0; j < tall; j++) {
        cells.push(gridx.cellOf(grid, x + i, y + j));
      }
    }
    return cells;
  });
}

// Every rocket as a record, in file order, with its parts and its light path standing on their cells
export function setup(state) {
  const listed = state.level.features.splitObjects;
  if (!listed || !listed.SplitObjects.length) {
    return;
  }
  const { grid } = state;
  const rockets = [];
  for (const data of listed.SplitObjects) {
    const wide = data.StartEndArea.X;
    const tall = data.StartEndArea.Y;
    const slices = slicesOf(grid, originsOf(data), wide, tall);
    const perHit = data.SegmentDecreasePerHit;
    const health = Math.max(0, idiv(slices.length, perHit) - (Math.max(wide, tall) + 1));
    const parts = gridx.makeTarget(NUMBER, -1, health);
    parts.matchAll = true;
    parts.freeShot = true;
    const path = gridx.makeTarget(NUMBER, -1, 0, true, false);
    const rocket = {
      slices,
      area: wide * tall,
      perHit,
      start: 0,
      end: slices.length - 1,
      parts: -1,
      path: -1,
      launched: false,
    };
    if (health === 0) {
      parts.dead = true;
      gridx.add(grid, parts, []);
    } else {
      gridx.add(grid, parts, [...partCells(rocket, START), ...partCells(rocket, END)]);
    }
    gridx.add(grid, path, pathCells(rocket));
    rocket.parts = parts.id;
    rocket.path = path.id;
    rockets.push(rocket);
  }
  state.features[NUMBER] = { rockets };
}

// The cells one part stands on: area-many distinct cells, walking the slices up from the start index or down from the
// end index
export function partCells(rocket, part) {
  const { slices } = rocket;
  const cells = [];
  let index = part === START ? rocket.start : rocket.end;
  while (index >= 0 && index < slices.length && cells.length < rocket.area) {
    for (const cell of slices[index]) {
      if (cells.length >= rocket.area) {
        break;
      }
      if (!cells.includes(cell)) {
        cells.push(cell);
      }
    }
    index += part === START ? 1 : -1;
  }
  return cells;
}

// The light path: every cell of the slices from the start index to the end index that neither part covers, or the
// start part's cells when that leaves none
export function pathCells(rocket) {
  const start = partCells(rocket, START);
  const end = partCells(rocket, END);
  const cells = [];
  const { slices } = rocket;
  for (let index = rocket.start; index < Math.min(rocket.end + 1, slices.length); index++) {
    for (const cell of slices[index]) {
      if (!start.includes(cell) && !end.includes(cell) && !cells.includes(cell)) {
        cells.push(cell);
      }
    }
  }
  return cells.length ? cells : start;
}

export function rocketOf(state, target) {
  const { rockets } = state.features[NUMBER];
  for (let index = 0; index < rockets.length; index++) {
    if (rockets[index].parts === target.id) {
      return [index, rockets[index]];
    }
  }
  throw new Error(`target ${target.id} is no rocket's parts`);
}

// The smallest squared cell distance from cell to any of cells (-1 for none)
export function nearest(grid, cells, cell) {
  const x = cell % grid.width;
  const y = idiv(cell, grid.width);
  let best = -1;
  for (const other of cells) {
    const dx = (other % grid.width) - x;
    const dy = idiv(other, grid.width) - y;
    const distance = dx * dx + dy * dy;
    if (best < 0 || distance < best) {
      best = distance;
    }
  }
  return best;
}

// Which part a hit at this cell moves: the part standing there, else the nearer one, the start on ties; null when
// neither part has a cell left
export function partHit(state, rocket, cell) {
  if (cell === null || cell < 0) {
    return START;
  }
  const start = partCells(rocket, START);
  if (start.includes(cell)) {
    return START;
  }
  const end = partCells(rocket, END);
  if (end.includes(cell)) {
    return END;
  }
  if (!start.length && !end.length) {
    return null;
  }
  const toStart = nearest(state.grid, start, cell);
  const toEnd = nearest(state.grid, end, cell);
  if (toEnd < 0 || (toStart >= 0 && toStart <= toEnd)) {
    return START;
  }
  return END;
}

// The parts lose health and one part moves; at 0 the rocket launches, else the parts and the path stand anew
export function damage(state, index, rocket, amount, cell) {
  const { grid } = state;
  const parts = grid.targets[rocket.parts];
  parts.health = Math.max(0, parts.health - amount);
  const part = partHit(state, rocket, cell);
  if (part === START) {
    rocket.start = Math.min(rocket.start + rocket.perHit, rocket.end);
  } else if (part === END) {
    rocket.end = Math.max(rocket.end - rocket.perHit, rocket.start);
  }
  base.emit(state, "hit", { target: parts.id, cell: cell === null ? -1 : cell, health: parts.health });
  if (parts.health === 0) {
    launch(state, index, rocket);
    return;
  }
  gridx.move(grid, parts, [...partCells(rocket, START), ...partCells(rocket, END)]);
  gridx.move(grid, grid.targets[rocket.path], pathCells(rocket));
  const move = part === null ? -1 : part;
  base.emit(state, "rocket_move", { rocket: index, part: move, start: rocket.start, end: rocket.end });
}

// The parts meet and the rocket leaves: its parts and its path are gone from the picture at once
export function launch(state, index, rocket) {
  const { grid } = state;
  const parts = grid.targets[rocket.parts];
  parts.dead = true;
  rocket.launched = true;
  gridx.remove(grid, parts);
  gridx.remove(grid, grid.targets[rocket.path]);
  base.emit(state, "target_died", { target: parts.id, owner: NUMBER });
  base.emit(state, "rocket_launch", { rocket: index, start: rocket.start, end: rocket.end });
  checks.requestWinCheck(state);
}

// A shot or a booster lands on a rocket's parts. A shot carries the cell it was aimed at; anything else counts as a
// hit at the start part
export function onHit(state, target, damageDone, source) {
  const [index, rocket] = rocketOf(state, target);
  damage(state, index, rocket, damageDone, source === null ? null : source.cell);
}

// The auto-finisher started: every rocket with health left takes half of it at its start part and the rest at its end
// part, and launches
export function onAutofinish(state) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return;
  }
  mine.rockets.forEach((rocket, index) => {
    const parts = state.grid.targets[rocket.parts];
    if (parts.dead || parts.health < 1) {
      return;
    }
    const { health } = parts;
    const half = idiv(health, 2);
    if (half > 0) {
      finishHit(state, index, rocket, half, START);
    }
    const rest = health - half;
    if (rest > 0 && !parts.dead) {
      finishHit(state, index, rocket, rest, END);
    }
  });
}

// Damage at one part's first cell, freeing pigs' reservations as a landing hit would
export function finishHit(state, index, rocket, amount, part) {
  const cells = partCells(rocket, part);
  if (!cells.length) {
    return;
  }
  const parts = state.grid.targets[rocket.parts];
  aim.release(state, parts, cells[0]);
  damage(state, index, rocket, amount, cells[0]);
  if (parts.dead) {
    aim.release(state, parts, null);
  }
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  let out = base.mix(h, mine.rockets.length);
  for (const rocket of mine.rockets) {
    const parts = state.grid.targets[rocket.parts];
    out = base.mix(base.mix(out, rocket.start), rocket.end);
    out = base.mix(base.mix(out, parts.health), parts.dead ? 1 : 0);
  }
  return out;
}
