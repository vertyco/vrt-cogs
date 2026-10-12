// Life: seeds, bugs, fish and fireflies. They are single cells, not bodies.
//
// What each creature keeps in its cell's life field (16 bits). Bit 15 is shared: it holds the parity of the last step
// the cell acted in, so a creature that moves along the scan is not met again and made to act twice in one step.
//   bug      bit 0 walking right, bits 1 to 3 plants eaten (0 to 5), bits 4 to 12 steps spent under water
//   fish     bits 0 to 7 steps spent out of water, bits 8 to 10 dart heading, bits 11 to 13 dart steps left
//   firefly  bits 0 to 2 heading (eighth turns, 0 up, clockwise), bit 3 turning clockwise, bit 4 can lay eggs
// elements.js hands new bugs and fireflies a random heading with the same layout.
import { EL, ELEMENTS } from "../elements.js";
import { fall, near, put, SIDES, sink, swap, touching } from "../helpers.js";
import { spawnTree } from "../particles.js";
import { H, W } from "../world.js";

const TURN = 0x8000;
const BURNS_AT = 300;
const SET_ALIGHT = 3000;

const SEED_FALLS = 9500;
const SEED_GROWS = 100;

const BUG_RIGHT = 1;
const BUG_EATEN_SHIFT = 1;
const BUG_EATEN_MASK = 7;
const BUG_WET_SHIFT = 4;
const BUG_WET_MASK = 0x1ff;
const BUG_DROWNS_AFTER = 300;
const BUG_FULL = 5;
const BUG_SINKS = 2500;
const BUG_EATS = 200;
const BUG_WALKS = 3000;
const BUG_TURNS = 200;
const FOODS = [EL.plant, EL.leaf, EL.honey];
// Where a bug lays its egg: left, right, above
const NURSERY = [-1, 1, -W];

const FISH_OUT_MASK = 0xff;
const FISH_OUT_LIMIT = 200;
const FISH_HEADING_SHIFT = 8;
const FISH_DART_SHIFT = 11;
const FISH_DART_BITS = (7 << FISH_HEADING_SHIFT) | (7 << FISH_DART_SHIFT);
const FISH_DART_START = 800;
const FISH_EATS = 5000;
const FISH_BREEDS = 5;
const FISH_SINKS = 5000;
const FISH_HOPS = 1500;

const FLY_HEADING_MASK = 7;
const FLY_CLOCKWISE = 8;
const FLY_LAYS = 16;
const FLY_LIMIT = 60;
const FLY_MOVES = 5000;
const FLY_BENDS = 2500;
const FLY_FLIPS = 300;
const FLY_LAYS_NEAR_PLANT = 300;
// The 8 headings, clockwise from up
const HEADING_DX = [0, 1, 1, 1, 0, -1, -1, -1];
const HEADING_DY = [-1, -1, 0, 1, 1, 1, 0, -1];
// Up-left and up-right of a fish out of water, in the order it hops
const HOPS = [-W - 1, -W + 1];

function isWater(id) {
  return id === EL.water || id === EL.saltWater;
}

// Whether the creature at cell i has not yet acted this step. Marks it as having acted.
function takeTurn(w, i) {
  const mark = (w.step & 1) << 15;
  const state = w.life[i];
  if ((state & TURN) === mark) {
    return false;
  }
  w.life[i] = (state & ~TURN) | mark;
  return true;
}

// A creature that burns turns to fire when it is hot or a flame is next to it
function singe(w, i, d) {
  if (w.heat[i] >= BURNS_AT || (d.chance(SET_ALIGHT) && near(w, i, d, EL.fire) >= 0)) {
    put(w, i, EL.fire, d);
    return true;
  }
  return false;
}

// Rests on wet soil: now and then it grows a tree from its own cell. In water it becomes a plant.
function seed(w, x, y, i, d) {
  if (touching(w, i, d, EL.water) >= 0) {
    put(w, i, EL.plant, d);
    return;
  }
  if (fall(w, i, d, SEED_FALLS, false)) {
    return;
  }
  if (w.el[i + W] === EL.wetSoil && d.chance(SEED_GROWS)) {
    put(w, i, 0, d);
    if (!spawnTree(w, x, y, d)) {
      put(w, i, EL.seed, d);
    }
  }
}

// Counts steps under water in the bug's life. Returns true when it has drowned.
function drown(w, i) {
  const state = w.life[i];
  const rest = state & ~(BUG_WET_MASK << BUG_WET_SHIFT);
  if (!isWater(w.el[i - W])) {
    w.life[i] = rest;
    return false;
  }
  const wet = ((state >> BUG_WET_SHIFT) & BUG_WET_MASK) + 1;
  w.life[i] = rest | (wet << BUG_WET_SHIFT);
  return wet >= BUG_DROWNS_AFTER;
}

// Falls through empty space and gas, sinks through water now and then. Returns whether it is in the air or water.
function dropBug(w, i, d) {
  const below = w.el[i + W];
  if (below === 0 || ELEMENTS[below].kind === "gas") {
    swap(w, i, i + W);
    return true;
  }
  if (isWater(below)) {
    if (d.chance(BUG_SINKS)) {
      swap(w, i, i + W);
    }
    return true;
  }
  return false;
}

// Puts a new bug into the first free cell beside or above this one, looking from a random start. Returns success.
function layBug(w, i, d) {
  const from = d.roll(NURSERY.length);
  for (let k = 0; k < NURSERY.length; k++) {
    const j = i + NURSERY[(from + k) % NURSERY.length];
    if (w.el[j] === 0) {
      put(w, j, EL.bug, d);
      return true;
    }
  }
  return false;
}

// Eats a plant, leaf or honey it touches. After the fifth meal it lays a bug, as soon as there is room.
function feed(w, i, d) {
  let eaten = (w.life[i] >> BUG_EATEN_SHIFT) & BUG_EATEN_MASK;
  if (eaten < BUG_FULL && d.chance(BUG_EATS)) {
    for (const food of FOODS) {
      const j = touching(w, i, d, food);
      if (j >= 0) {
        put(w, j, 0, d);
        eaten += 1;
        break;
      }
    }
  }
  if (eaten >= BUG_FULL && layBug(w, i, d)) {
    eaten = 0;
  }
  w.life[i] = (w.life[i] & ~(BUG_EATEN_MASK << BUG_EATEN_SHIFT)) | (eaten << BUG_EATEN_SHIFT);
}

// One stride along the surface: forward, up a 1-cell step, or turn round at a wall
function walk(w, x, y, i, d) {
  const right = (w.life[i] & BUG_RIGHT) === BUG_RIGHT;
  const dx = right ? 1 : -1;
  const ahead = i + dx;
  const inside = x + dx >= 1 && x + dx <= W - 2;
  if (inside && w.el[ahead] === 0) {
    swap(w, i, ahead);
  } else if (inside && w.el[ahead - W] === 0 && w.el[i - W] === 0) {
    swap(w, i, ahead - W);
  } else {
    w.life[i] ^= BUG_RIGHT;
  }
}

function bug(w, x, y, i, d) {
  if (!takeTurn(w, i) || singe(w, i, d)) {
    return;
  }
  if (drown(w, i)) {
    put(w, i, 0, d);
    return;
  }
  if (dropBug(w, i, d)) {
    return;
  }
  feed(w, i, d);
  if (d.chance(BUG_TURNS)) {
    w.life[i] ^= BUG_RIGHT;
  }
  if (d.chance(BUG_WALKS)) {
    walk(w, x, y, i, d);
  }
}

// Whether a fish is in water: water on at least 2 of its 4 sides
function swimming(w, i) {
  let wet = 0;
  for (const offset of SIDES) {
    if (isWater(w.el[i + offset])) {
      wet += 1;
    }
  }
  return wet >= 2;
}

// Out of water: falls, sinks back into a pond it lands on, otherwise hops about until the 200 steps are up
function flop(w, i, d) {
  const out = (w.life[i] & FISH_OUT_MASK) + 1;
  if (out > FISH_OUT_LIMIT) {
    put(w, i, 0, d);
    return;
  }
  w.life[i] = (w.life[i] & ~FISH_OUT_MASK) | out;
  const below = w.el[i + W];
  if (below === 0) {
    swap(w, i, i + W);
  } else if (isWater(below)) {
    sink(w, i, d, below, FISH_SINKS);
  } else if (d.chance(FISH_HOPS)) {
    const j = i + HOPS[d.roll(2)];
    if (w.el[j] === 0 && w.el[i - W] === 0) {
      swap(w, i, j);
    }
  }
}

// Eats a bug beside it: the fish takes the bug's place and leaves water behind. Returns whether it ate.
function eatBug(w, i, d) {
  if (!d.chance(FISH_EATS)) {
    return false;
  }
  const j = touching(w, i, d, EL.bug);
  if (j < 0) {
    return false;
  }
  swap(w, i, j);
  put(w, i, EL.water, d);
  return true;
}

// A short dart in one direction through water, then a pause. The dart ends when it hits anything but water.
function dart(w, i, d) {
  const state = w.life[i];
  const left = (state >> FISH_DART_SHIFT) & 7;
  if (left === 0) {
    if (d.chance(FISH_DART_START)) {
      const heading = d.roll(8);
      const steps = 2 + d.roll(4);
      w.life[i] = (state & ~FISH_DART_BITS) | (heading << FISH_HEADING_SHIFT) | (steps << FISH_DART_SHIFT);
    }
    return;
  }
  const heading = (state >> FISH_HEADING_SHIFT) & 7;
  const j = i + HEADING_DX[heading] + HEADING_DY[heading] * W;
  if (!isWater(w.el[j])) {
    w.life[i] = state & ~(7 << FISH_DART_SHIFT);
    return;
  }
  w.life[i] = (state & ~(7 << FISH_DART_SHIFT)) | ((left - 1) << FISH_DART_SHIFT);
  swap(w, i, j);
}

function fish(w, x, y, i, d) {
  if (!takeTurn(w, i)) {
    return;
  }
  if (!swimming(w, i)) {
    flop(w, i, d);
    return;
  }
  w.life[i] &= ~FISH_OUT_MASK;
  if (eatBug(w, i, d)) {
    return;
  }
  if (d.chance(FISH_BREEDS) && near(w, i, d, EL.fish) >= 0) {
    const j = touching(w, i, d, EL.water);
    if (j >= 0) {
      put(w, j, EL.fish, d);
    }
  }
  dart(w, i, d);
}

// Lays a firefly in an empty cell beside this one. The tally is last step's count plus the ones laid since.
function layFirefly(w, i, d) {
  for (const offset of [...SIDES, -W - 1, -W + 1]) {
    if (w.el[i + offset] === 0) {
      put(w, i + offset, EL.firefly, d);
      w.tally[EL.firefly] += 1;
      return;
    }
  }
}

// Flies half the steps. Every few moves the heading bends a notch, which makes loops. Bumping anything picks a new one.
function fly(w, x, y, i, d) {
  const state = w.life[i];
  let heading = state & FLY_HEADING_MASK;
  let clockwise = (state & FLY_CLOCKWISE) !== 0;
  if (d.chance(FLY_BENDS)) {
    heading = (heading + (clockwise ? 1 : 7)) & 7;
  }
  if (d.chance(FLY_FLIPS)) {
    clockwise = !clockwise;
  }
  const tx = x + HEADING_DX[heading];
  const ty = y + HEADING_DY[heading];
  const open = tx >= 1 && tx <= W - 2 && ty >= 1 && ty <= H - 2 && w.el[ty * W + tx] === 0;
  if (!open) {
    heading = d.roll(8);
  }
  const kept = state & ~(FLY_HEADING_MASK | FLY_CLOCKWISE);
  w.life[i] = kept | heading | (clockwise ? FLY_CLOCKWISE : 0);
  if (open) {
    swap(w, i, ty * W + tx);
  }
}

function firefly(w, x, y, i, d) {
  if (!takeTurn(w, i) || singe(w, i, d)) {
    return;
  }
  if (touching(w, i, d, EL.water) >= 0 || touching(w, i, d, EL.saltWater) >= 0) {
    put(w, i, 0, d);
    return;
  }
  const canLay = (w.life[i] & FLY_LAYS) !== 0;
  if (canLay && w.tally[EL.firefly] < FLY_LIMIT && d.chance(FLY_LAYS_NEAR_PLANT) && near(w, i, d, EL.plant) >= 0) {
    layFirefly(w, i, d);
  }
  if (d.chance(FLY_MOVES)) {
    fly(w, x, y, i, d);
  }
}

export const RULES = {
  [EL.seed]: seed,
  [EL.bug]: bug,
  [EL.fish]: fish,
  [EL.firefly]: firefly,
};
