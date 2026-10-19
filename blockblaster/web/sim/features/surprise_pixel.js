// Feature 7, the Surprise Pixel: a cube drawn blank until a side neighbor is connected to the outside.
// Only the drawing changes. The cube keeps its real color and health the whole time, so pigs shoot it by that color like
// any cube (SurprisePixelFeature$$AttachInternal, RVA 0x57F6E24); the one rule that reads the hidden list is the Super
// Shooter, which skips hidden cubes (hidesCube). A cube is revealed for good when one of the four cells beside its own
// that lie inside the grid is reached by the edge flood; diagonals don't count, and standing on the border alone doesn't.
// A big cube is revealed when any of its cells has such a neighbor (SurprisePixelFeatureController$$HandlePixelReveals,
// RVA 0x57F86C0, takes every Surprise Pixel on the cells PixelGridController$$GetObjectsCanReachOutside, RVA 0x6644968,
// returns: the cells with a reached side neighbor). The check runs at level start, and at the end of a
// tick after any hit and after the outside triggers (a booster or a revive finished).
// common/sim/features/surprise_pixel.py mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";
import { idiv } from "../mathx.js";

export const NUMBER = 7;

// Events after which the reveal check runs at the end of the tick
const CHECK_AFTER = ["hit", "booster_done", "revive_done", "walls_removed"];

// The listed cubes start hidden, as cube ids in file order
export function setup(state) {
  const listed = state.level.features.surprisePixels;
  if (!listed || !listed.Pixels.length) {
    return;
  }
  const { grid } = state;
  const hidden = [];
  for (const point of listed.Pixels) {
    const x = point.X;
    const y = point.Y;
    if (!(x >= 0 && x < grid.width && y >= 0 && y < grid.height)) {
      continue;
    }
    const cell = gridx.cellOf(grid, x, y);
    for (const target of gridx.at(grid, cell)) {
      if (target.owner === 0) {
        if (!hidden.includes(target.id)) {
          hidden.push(target.id);
        }
        break;
      }
    }
  }
  state.features[NUMBER] = { hidden, pending: false };
}

// Level start, once every feature has put its parts on the picture: cubes already beside the outside show their color
// from the first frame
export function ready(state) {
  if (NUMBER in state.features) {
    check(state, false);
  }
}

// Any cell of the cube has a side neighbor, inside the grid, that the edge flood reaches
export function besideOutside(state, cube, reach) {
  const { grid } = state;
  for (const cell of cube.cells) {
    const x = cell % grid.width;
    const y = idiv(cell, grid.width);
    for (const [nx, ny] of [
      [x + 1, y],
      [x - 1, y],
      [x, y + 1],
      [x, y - 1],
    ]) {
      if (nx >= 0 && nx < grid.width && ny >= 0 && ny < grid.height && reach[gridx.cellOf(grid, nx, ny)]) {
        return true;
      }
    }
  }
  return false;
}

// Reveal every hidden cube with a side neighbor connected to the outside; a cube that already broke just leaves the list
export function check(state, announce) {
  const mine = state.features[NUMBER];
  const reach = gridx.reachOutside(state.grid);
  const keep = [];
  const shown = [];
  for (const cubeId of mine.hidden) {
    const cube = state.grid.targets[cubeId];
    if (cube.dead) {
      continue;
    }
    if (besideOutside(state, cube, reach)) {
      shown.push(cubeId);
    } else {
      keep.push(cubeId);
    }
  }
  mine.hidden = keep;
  if (announce) {
    for (const cubeId of shown) {
      base.emit(state, "pixel_revealed", { cube: cubeId });
    }
  }
}

export function onEvent(state, name) {
  if (NUMBER in state.features && CHECK_AFTER.includes(name)) {
    state.features[NUMBER].pending = true;
  }
}

// End of tick: when something asked for it, check the hidden cubes
export function release(state) {
  const mine = state.features[NUMBER];
  if (!mine || !mine.pending) {
    return;
  }
  mine.pending = false;
  check(state, true);
}

// A hidden cube is skipped by the Super Shooter
export function hidesCube(state, cube) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.hidden.includes(cube.id);
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.hidden.length);
  for (const cubeId of mine.hidden) {
    h = base.mix(h, cubeId);
  }
  return base.mix(h, mine.pending ? 1 : 0);
}
