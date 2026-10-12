// Solid rules. Each rule is (w, x, y, i, d) and runs once per cell per step during the scan.
import { EL } from "../elements.js";
import { AROUND, burnPlus, near, put, putKeepHeat, SIDES, touching } from "../helpers.js";
import { spawnBigFireball } from "../particles.js";
import { H, N, W } from "../world.js";
import { carryCurrent } from "./electric.js";
import { ignite, waxDrip } from "./fire.js";

const WOOD_CATCHES_AT = 300;
const ICE_MELTS_AT = 5;
const METAL_MELTS_AT = 1500;
const GLASS_MELTS_AT = 1700;
// Wax melts near real heat (lava, a heater, burning thermite, a big fire). It barely carries heat, so a candle's flame
// only warms the wax right under it, and that wax is spared by flameNear.
const WAX_MELTS_AT = 200;
const FLAME_REACH = 4;
// A flame takes the wax it touches 0.33% of the steps. The originals' 1% is scaled by a third like the slug's lengths,
// since their worlds were three times bigger: a candle of the same look then burns for minutes, as it did there.
const WAX_DRIPS = 33;
const C4_GOES_OFF_AT = 400;
// Metal rusts 0.05% of steps next to water, 4 times as often next to salt water
const RUST_IN_WATER = 5;
const RUST_IN_BRINE = 20;
const FUSE_BURST_LIMIT = 40;
const BURST_SKIPS = 2000;

// What turns chilled ice back into ice at once when it is next to it
const THAWS_CHILLED_ICE = new Set([EL.salt, EL.saltWater, EL.lava, EL.fire, EL.steam]);

// Scratch for the fuse's flame spill: a cell is marked with the current pass number once the spill has looked at it
const seen = new Uint32Array(N);
let pass = 0;

// Wood catches fire from a flame next to it, or from being hot enough
function wood(w, x, y, i, d) {
  if (w.heat[i] >= WOOD_CATCHES_AT || (d.chance(300) && near(w, i, d, EL.fire) >= 0)) {
    ignite(w, i, d);
  }
}

// Melted ice is never colder than its melting point, or it would freeze again at once
function melt(w, i, d) {
  putKeepHeat(w, i, EL.water, d);
  if (w.heat[i] < ICE_MELTS_AT) {
    w.heat[i] = ICE_MELTS_AT;
  }
}

// Whether something touching the ice melts it this step: fire or lava, steam, salt and water, each at its own chance
function meltedByNeighbour(w, i, d) {
  const touches = (id, p) => d.chance(p) && touching(w, i, d, id) >= 0;
  if (d.chance(5000) && (touching(w, i, d, EL.fire) >= 0 || touching(w, i, d, EL.lava) >= 0)) {
    return true;
  }
  return touches(EL.steam, 7000) || touches(EL.salt, 1000) || touches(EL.water, 100);
}

function ice(w, x, y, i, d) {
  if (w.heat[i] >= ICE_MELTS_AT || meltedByNeighbour(w, i, d)) {
    melt(w, i, d);
  }
}

// Lava next to a wall now and then melts it
function wall(w, x, y, i, d) {
  if (d.chance(50) && near(w, i, d, EL.lava) >= 0) {
    put(w, i, EL.lava, d);
  }
}

function metal(w, x, y, i, d) {
  if (w.heat[i] >= METAL_MELTS_AT) {
    put(w, i, EL.moltenMetal, d);
    return;
  }
  carryCurrent(w, i, d);
  const roll = d.roll(10000);
  if (roll >= RUST_IN_BRINE) {
    return;
  }
  if (touching(w, i, d, EL.saltWater) >= 0 || (roll < RUST_IN_WATER && touching(w, i, d, EL.water) >= 0)) {
    put(w, i, EL.rust, d);
  }
}

function glass(w, x, y, i, d) {
  if (w.heat[i] >= GLASS_MELTS_AT) {
    put(w, i, EL.moltenGlass, d);
  }
}

// Whether something that thaws chilled ice is among the 8 cells around it
function thawedByNeighbour(w, i) {
  for (const offset of AROUND) {
    if (THAWS_CHILLED_ICE.has(w.el[i + offset])) {
      return true;
    }
  }
  return false;
}

// Spreads into water near it half the time, then thaws into ice (at once next to salt, lava, fire or steam)
function chilledIce(w, x, y, i, d) {
  if (thawedByNeighbour(w, i)) {
    put(w, i, EL.ice, d);
    return;
  }
  if (d.chance(5000)) {
    const j = near(w, i, d, EL.water);
    if (j >= 0) {
      putKeepHeat(w, j, EL.chilledIce, d);
    }
  }
  if (d.chance(600)) {
    put(w, i, EL.ice, d);
  }
}

// Whether a flame is within FLAME_REACH cells. A flame holds 600 degrees, hotter than the heater, so no melting point
// lets the heater melt wax while sparing the wax a candle's flame sits on
function flameNear(w, x, y) {
  for (let yy = Math.max(y - FLAME_REACH, 0); yy <= Math.min(y + FLAME_REACH, H - 1); yy++) {
    for (let xx = Math.max(x - FLAME_REACH, 0); xx <= Math.min(x + FLAME_REACH, W - 1); xx++) {
      if (w.el[yy * W + xx] === EL.fire) {
        return true;
      }
    }
  }
  return false;
}

// A candle: it drips when a flame touches it, and melts when it is hot. Wax near a flame only drips, or the flame
// would melt the wax out from under itself.
function wax(w, x, y, i, d) {
  if (w.heat[i] >= WAX_MELTS_AT && !flameNear(w, x, y)) {
    put(w, i, EL.liquidWax, d);
    return;
  }
  if (d.chance(WAX_DRIPS) && touching(w, i, d, EL.fire) >= 0) {
    waxDrip(w, i, d);
  }
}

function c4(w, x, y, i, d) {
  if (!d.chance(6000) || (w.heat[i] < C4_GOES_OFF_AT && touching(w, i, d, EL.fire) < 0)) {
    return;
  }
  w.events.boom += 1;
  if (!spawnBigFireball(w, x, y, d)) {
    burnPlus(w, i, d);
  }
}

// The cells a spill from j tries next, pushed so that the stack pops them up first, then a random side, down, the other
function pushNeighbours(stack, j, d) {
  const flip = d.roll(2) === 0;
  stack.push(flip ? j + 1 : j - 1, j + W, flip ? j - 1 : j + 1, j - W);
}

// A depth-first spill of fire from cell i, up first. It skips walls, the edge columns and 1 cell in 5, and stops at
// limit cells in all. Fuse cells it reaches are fire too, so the flame runs on down a line of fuse.
function spillFire(w, i, d, limit) {
  pass = (pass + 1) >>> 0;
  if (pass === 0) {
    seen.fill(0);
    pass = 1;
  }
  put(w, i, EL.fire, d);
  seen[i] = pass;
  let count = 1;
  const stack = [];
  pushNeighbours(stack, i, d);
  while (stack.length > 0 && count < limit) {
    const k = stack.pop();
    const kx = k % W;
    const ky = Math.trunc(k / W);
    if (seen[k] === pass || ky < 1 || ky > H - 2 || kx < 1 || kx > W - 2) {
      continue;
    }
    seen[k] = pass;
    if (w.el[k] === EL.wall || d.chance(BURST_SKIPS)) {
      continue;
    }
    put(w, k, EL.fire, d);
    count += 1;
    pushNeighbours(stack, k, d);
  }
}

function fuse(w, x, y, i, d) {
  if (d.chance(9900) && touching(w, i, d, EL.fire) >= 0) {
    spillFire(w, i, d, 1 + d.roll(FUSE_BURST_LIMIT));
  }
}

// Plant grows only through water: every water cell on its 4 sides turns into plant
function plant(w, x, y, i, d) {
  if (d.chance(2000) && touching(w, i, d, EL.fire) >= 0) {
    ignite(w, i, d);
    return;
  }
  if (d.chance(1000)) {
    for (const offset of SIDES) {
      if (w.el[i + offset] === EL.water) {
        put(w, i + offset, EL.plant, d);
      }
    }
  }
}

function branch(w, x, y, i, d) {
  if (d.chance(300) && near(w, i, d, EL.fire) >= 0) {
    ignite(w, i, d);
  }
}

function leaf(w, x, y, i, d) {
  if (d.chance(500) && near(w, i, d, EL.fire) >= 0) {
    ignite(w, i, d);
    return;
  }
  if (d.chance(2000) && touching(w, i, d, EL.salt) >= 0) {
    put(w, i, 0, d);
    return;
  }
  if (d.chance(9)) {
    const j = i + SIDES[d.roll(SIDES.length)];
    if (w.el[j] === 0) {
      put(w, j, EL.pollen, d);
    }
  }
}

export const RULES = {
  [EL.wall]: wall,
  [EL.wood]: wood,
  [EL.metal]: metal,
  [EL.glass]: glass,
  [EL.ice]: ice,
  [EL.chilledIce]: chilledIce,
  [EL.wax]: wax,
  [EL.c4]: c4,
  [EL.fuse]: fuse,
  [EL.plant]: plant,
  [EL.branch]: branch,
  [EL.leaf]: leaf,
};
