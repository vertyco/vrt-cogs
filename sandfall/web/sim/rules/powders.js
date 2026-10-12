// Powder rules. Each rule is (w, x, y, i, d) and runs once per cell per step during the scan.
import { EL } from "../elements.js";
import { fall, fallStraight, near, put, sink, slideSideways, swap, touching } from "../helpers.js";
import { spawnTree } from "../particles.js";
import { H, W } from "../world.js";

const SAND_TURNS_TO_GLASS_AT = 1700;
const GUNPOWDER_GOES_OFF_AT = 250;
const SNOW_MELTS_AT = 5;
const THERMITE_LIGHTS_AT = 500;
// Above the heat lava holds itself at (1,200), so a crust of stone does not melt back into the lava under it
const STONE_MELTS_AT = 1300;

// Liquids sand sinks through, each at 25%
const SAND_SINKS = [EL.water, EL.saltWater, EL.oil];
// Gunpowder's blast: the 4 cells around it, then the ring beyond them (dx, dy)
const BLAST_NEAR = [
  [-1, 0],
  [1, 0],
  [0, -1],
  [0, 1],
];
const BLAST_FAR = [
  [-2, 0],
  [2, 0],
  [0, -2],
  [0, 2],
  [-1, -1],
  [1, -1],
  [-1, 1],
  [1, 1],
];
// Where the cells above a soil cell are, left to right
const ABOVE = [-W - 1, -W, -W + 1];
// Cells a burning thermite falls through everything except
const THERMITE_STOPS = new Set([EL.wall, EL.glass, EL.burningThermite]);

function sand(w, x, y, i, d) {
  if (w.heat[i] >= SAND_TURNS_TO_GLASS_AT) {
    put(w, i, EL.moltenGlass, d);
    return;
  }
  if (fall(w, i, d, 9500, false)) {
    return;
  }
  for (const liquid of SAND_SINKS) {
    if (sink(w, i, d, liquid, 2500)) {
      return;
    }
  }
}

// Salt touching water: the water becomes salt water and the salt is gone
function dissolve(w, i, d) {
  if (!d.chance(9000)) {
    return false;
  }
  const j = touching(w, i, d, EL.water);
  if (j < 0) {
    return false;
  }
  put(w, j, EL.saltWater, d);
  put(w, i, 0, d);
  return true;
}

// Salt kills a plant it touches. Ice is melted by the ice's own rule.
function salt(w, x, y, i, d) {
  if (dissolve(w, i, d)) {
    return;
  }
  if (d.chance(500)) {
    const j = touching(w, i, d, EL.plant);
    if (j >= 0) {
      put(w, j, 0, d);
    }
  }
  if (!fall(w, i, d, 9500, true)) {
    sink(w, i, d, EL.saltWater, 2500);
  }
}

function inWorld(x, y) {
  return x >= 1 && x <= W - 2 && y >= 0 && y <= H - 2;
}

// A ragged diamond of fire: this cell and the 4 around it burn for certain, the ring beyond leaves half the gunpowder
function blast(w, x, y, i, d) {
  put(w, i, EL.fire, d);
  for (const [dx, dy] of BLAST_NEAR) {
    if (inWorld(x + dx, y + dy)) {
      put(w, i + dy * W + dx, EL.fire, d);
    }
  }
  for (const [dx, dy] of BLAST_FAR) {
    if (!inWorld(x + dx, y + dy)) {
      continue;
    }
    const j = i + dy * W + dx;
    if (w.el[j] !== EL.gunpowder || d.chance(5000)) {
      put(w, j, EL.fire, d);
    }
  }
}

// The powder passes on: the 4 cells around it become gunpowder and it stays, so a trail goes off one cell after another
function spreadPowder(w, x, y, i, d) {
  for (const [dx, dy] of BLAST_NEAR) {
    const j = i + dy * W + dx;
    if (inWorld(x + dx, y + dy) && w.el[j] !== EL.gunpowder) {
      put(w, j, EL.gunpowder, d);
    }
  }
}

function gunpowder(w, x, y, i, d) {
  if (d.chance(9500) && (w.heat[i] >= GUNPOWDER_GOES_OFF_AT || touching(w, i, d, EL.fire) >= 0)) {
    w.events.boom += 1;
    if (d.chance(4000)) {
      blast(w, x, y, i, d);
    } else {
      spreadPowder(w, x, y, i, d);
    }
    return;
  }
  if (!fall(w, i, d, 9500, false)) {
    sink(w, i, d, EL.water, 2500);
  }
}

function snow(w, x, y, i, d) {
  if (w.heat[i] >= SNOW_MELTS_AT && d.chance(200)) {
    put(w, i, EL.water, d);
    return;
  }
  if (d.chance(1000) && slideSideways(w, i, d)) {
    return;
  }
  fall(w, i, d, 5000, true);
}

function ash(w, x, y, i, d) {
  fall(w, i, d, 7000, true);
}

// Water in the 3 cells above: 15% of the time it is drunk and the soil is wet. Returns whether it drank.
function drink(w, i, d) {
  if (!d.chance(1500)) {
    return false;
  }
  const from = d.roll(3);
  for (let k = 0; k < 3; k++) {
    const j = i + ABOVE[(from + k) % 3];
    if (w.el[j] === EL.water) {
      put(w, j, 0, d);
      return true;
    }
  }
  return false;
}

function soil(w, x, y, i, d) {
  if (d.chance(2500)) {
    const j = touching(w, i, d, EL.nitro);
    if (j >= 0) {
      put(w, j, EL.chargedNitro, d);
      put(w, i, EL.chargedNitro, d);
      return;
    }
  }
  if (drink(w, i, d)) {
    put(w, i, EL.wetSoil, d);
    return;
  }
  if (!fallStraight(w, i, d, 9900)) {
    sink(w, i, d, EL.water, 5000);
  }
}

// 5% of steps: usually it dries out when there is no water near, rarely it grows a tree from the top of the ground
function settle(w, x, y, i, d) {
  if (d.chance(9700)) {
    if (near(w, i, d, EL.water) < 0) {
      put(w, i, EL.soil, d);
    }
    return;
  }
  const below = w.el[i + W];
  if (w.el[i - W] === 0 && (below === EL.soil || below === EL.wall)) {
    if (spawnTree(w, x, y - 1, d)) {
      put(w, i, EL.soil, d);
    }
  }
}

function wetSoil(w, x, y, i, d) {
  drink(w, i, d);
  if (d.chance(500)) {
    settle(w, x, y, i, d);
    return;
  }
  fallStraight(w, i, d, 9900);
}

function thermite(w, x, y, i, d) {
  if (w.heat[i] >= THERMITE_LIGHTS_AT || (d.chance(500) && touching(w, i, d, EL.fire) >= 0)) {
    put(w, i, EL.burningThermite, d);
    return;
  }
  fall(w, i, d, 9500, false);
}

// Burns for the steps its life holds, then turns to ash. Meanwhile it drops through everything but wall and glass.
function burningThermite(w, x, y, i, d) {
  if (w.life[i] <= 1) {
    put(w, i, EL.ash, d);
    return;
  }
  w.life[i] -= 1;
  if (!THERMITE_STOPS.has(w.el[i + W])) {
    swap(w, i, i + W);
  }
}

function concrete(w, x, y, i, d) {
  if (fall(w, i, d, 9500, true) || sink(w, i, d, EL.water, 3500)) {
    return;
  }
  if ((d.chance(1000) && near(w, i, d, EL.wall) >= 0) || d.chance(10)) {
    put(w, i, EL.wall, d);
  }
}

// Heavy rock. A stone resting under oil now and then turns one of the pair into methane.
function stone(w, x, y, i, d) {
  if (w.heat[i] >= STONE_MELTS_AT) {
    put(w, i, EL.lava, d);
    return;
  }
  if (w.el[i - W] === EL.oil && d.chance(20)) {
    put(w, d.roll(2) === 0 ? i : i - W, EL.methane, d);
    return;
  }
  if (fallStraight(w, i, d, 9900)) {
    return;
  }
  if (!sink(w, i, d, EL.water, 9500) && !sink(w, i, d, EL.oil, 9500)) {
    sink(w, i, d, EL.lava, 2000);
  }
}

function rust(w, x, y, i, d) {
  fall(w, i, d, 9500, false);
}

function pollen(w, x, y, i, d) {
  fall(w, i, d, 9500, true);
}

export const RULES = {
  [EL.sand]: sand,
  [EL.coloredSand]: sand,
  [EL.salt]: salt,
  [EL.gunpowder]: gunpowder,
  [EL.snow]: snow,
  [EL.ash]: ash,
  [EL.soil]: soil,
  [EL.wetSoil]: wetSoil,
  [EL.thermite]: thermite,
  [EL.burningThermite]: burningThermite,
  [EL.concrete]: concrete,
  [EL.stone]: stone,
  [EL.rust]: rust,
  [EL.pollen]: pollen,
};
