// Liquid rules. Each rule is (w, x, y, i, d) and runs once per cell per step during the scan.
import { EL, ELEMENTS } from "../elements.js";
import { burnPlus, fall, layer, near, put, putKeepHeat, SIDES, sink, touching } from "../helpers.js";
import { spawnBeam, spawnFireball, spawnLavaArc, spawnStreak } from "../particles.js";
import { W } from "../world.js";
import { ignite } from "./fire.js";

const BOILS_AT = 100;
const FREEZES_AT = 0;
const BRINE_BOILS_AT = 102;
const BRINE_FREEZES_AT = -10;
const OIL_CATCHES_AT = 300;
const NITRO_GOES_OFF_AT = 300;
const LAVA_COOLS_BELOW = 940;
// Lava is topped back up to this every step, after the check above. Only a thin or well-chilled bit of lava loses
// more than the difference in one step and sets (about 75 degrees a side in open air); a pool or a stream keeps flowing.
const LAVA_HEAT = 1200;
// A lava cell set into stone by water or cryo is cooled to well below the heat where stone melts again
const QUENCHED_HEAT = 600;
const MOLTEN_GLASS_SETS_BELOW = 900;
const MOLTEN_METAL_SETS_BELOW = 1400;

// What acid leaves alone
const ACID_HOLDS = new Set([0, EL.acid, EL.acidFumes, EL.glass, EL.wall]);
// What cryo freezes a crust onto
const CRYO_CRUSTS_ON = new Set([EL.wall, EL.metal, EL.wax, EL.plant, EL.c4, EL.fuse, EL.spout, EL.well]);
// Where a grain of salt left by boiling brine can land: down, the two lower diagonals, then the sides
const SALT_DROPS = [W, W - 1, W + 1, 1, -1];

// Boils to steam when hot; freezes to ice when cold, keeping its own heat so a thawing pond doesn't refreeze at once
function changeState(w, i, d) {
  if (w.heat[i] >= BOILS_AT) {
    put(w, i, EL.steam, d);
    return true;
  }
  if (w.heat[i] <= FREEZES_AT) {
    putKeepHeat(w, i, EL.ice, d);
    return true;
  }
  return false;
}

// A flame next to the water: the flame is gone and the water becomes steam
function quench(w, i, d) {
  if (!d.chance(8000)) {
    return false;
  }
  const flame = touching(w, i, d, EL.fire);
  if (flame < 0) {
    return false;
  }
  put(w, flame, 0, d);
  put(w, i, EL.steam, d);
  w.events.sizzle += 1;
  return true;
}

function water(w, x, y, i, d) {
  if (changeState(w, i, d) || quench(w, i, d)) {
    return;
  }
  if (!sink(w, i, d, EL.oil, 2500)) {
    fall(w, i, d, 9500, true);
  }
}

// Boiling brine becomes steam and now and then leaves a grain of salt in an empty cell beside it
function boilBrine(w, i, d) {
  put(w, i, EL.steam, d);
  if (d.roll(3) !== 0) {
    return;
  }
  for (const offset of SALT_DROPS) {
    if (w.el[i + offset] === 0) {
      put(w, i + offset, EL.salt, d);
      return;
    }
  }
}

function saltWater(w, x, y, i, d) {
  if (w.heat[i] >= BRINE_BOILS_AT) {
    boilBrine(w, i, d);
  } else if (w.heat[i] <= BRINE_FREEZES_AT) {
    putKeepHeat(w, i, EL.ice, d);
  } else if (!layer(w, i, d, EL.water, 5000)) {
    fall(w, i, d, 9500, true);
  }
}

function oil(w, x, y, i, d) {
  if (w.heat[i] >= OIL_CATCHES_AT) {
    put(w, i, EL.fire, d);
  } else if (d.chance(2500) && touching(w, i, d, EL.fire) >= 0) {
    burnPlus(w, i, d);
  } else {
    fall(w, i, d, 9500, true);
  }
}

// Lava at cell j sets into stone, cooled to a heat where it stays stone
function setLava(w, j, d) {
  put(w, j, EL.stone, d);
  if (w.heat[j] > QUENCHED_HEAT) {
    w.heat[j] = QUENCHED_HEAT;
  }
}

// Water or salt water beside the lava turns to steam and the lava sets into stone
function meetWater(w, i, d) {
  let j = touching(w, i, d, EL.water);
  if (j < 0) {
    j = touching(w, i, d, EL.saltWater);
  }
  if (j < 0) {
    return false;
  }
  put(w, j, EL.steam, d);
  setLava(w, i, d);
  w.events.sizzle += 1;
  return true;
}

// Each step 25% of the time, everything beside the lava that can burn catches fire
function scorch(w, i, d) {
  if (!d.chance(2500)) {
    return;
  }
  for (const offset of SIDES) {
    if (ELEMENTS[w.el[i + offset]].burns) {
      ignite(w, i + offset, d);
    }
  }
}

function lava(w, x, y, i, d) {
  if (w.heat[i] < LAVA_COOLS_BELOW) {
    put(w, i, EL.stone, d);
    return;
  }
  if (meetWater(w, i, d)) {
    return;
  }
  if (d.chance(400) && touching(w, i, d, EL.oil) >= 0 && spawnLavaArc(w, x, y, d)) {
    put(w, i, 0, d);
    return;
  }
  scorch(w, i, d);
  if (d.chance(600) && w.el[i - W] === 0) {
    put(w, i - W, EL.fire, d);
  }
  w.heat[i] = LAVA_HEAT;
  fall(w, i, d, 6000, true);
}

// 10% of steps acid dissolves one random side neighbour that is not on its keep list, sometimes using itself up and
// sometimes puffing fumes above. Returns whether the acid was used up.
function dissolve(w, i, d) {
  if (!d.chance(1000)) {
    return false;
  }
  const from = d.roll(4);
  for (let k = 0; k < 4; k++) {
    const j = i + SIDES[(from + k) % 4];
    if (ACID_HOLDS.has(w.el[j])) {
      continue;
    }
    put(w, j, 0, d);
    if (d.roll(4) === 0 && w.el[i - W] === 0) {
      put(w, i - W, EL.acidFumes, d);
    }
    if (d.roll(3) === 0) {
      put(w, i, 0, d);
      return true;
    }
    return false;
  }
  return false;
}

function acid(w, x, y, i, d) {
  if (d.chance(50)) {
    const wall = touching(w, i, d, EL.wall);
    if (wall >= 0) {
      put(w, wall, 0, d);
    }
  }
  if (!dissolve(w, i, d)) {
    fall(w, i, d, 9500, true);
  }
}

// Honey is thick (a quarter as fast as water) and burns, slowly
function honey(w, x, y, i, d) {
  if (d.chance(100) && touching(w, i, d, EL.fire) >= 0) {
    put(w, i, EL.fire, d);
    return;
  }
  fall(w, i, d, 2500, true);
}

// Nitro goes off next to fire, or when it is hot enough to count as fire. Without a free streak it still flashes.
function nitro(w, x, y, i, d) {
  if (w.heat[i] >= NITRO_GOES_OFF_AT || near(w, i, d, EL.fire) >= 0) {
    if (d.chance(3000)) {
      w.events.boom += 1;
      spawnStreak(w, x, y, d);
      burnPlus(w, i, d);
      return;
    }
    if (d.chance(2000)) {
      put(w, i, EL.fire, d);
      return;
    }
  }
  if (!sink(w, i, d, EL.oil, 2500) && !sink(w, i, d, EL.water, 2500)) {
    fall(w, i, d, 9500, true);
  }
}

// Fire next to it sets it off in a beam straight up. It is fire either way.
function chargedNitro(w, x, y, i, d) {
  if (near(w, i, d, EL.fire) >= 0) {
    w.events.boom += 1;
    spawnBeam(w, x, y, d);
    put(w, i, EL.fire, d);
    return;
  }
  fall(w, i, d, 9500, true);
}

// Fire beside napalm throws a fireball and the napalm stays; with no fireball free the napalm itself burns
function napalm(w, x, y, i, d) {
  if (d.chance(2500) && touching(w, i, d, EL.fire) >= 0) {
    w.events.boom += 1;
    if (!spawnFireball(w, x, y, "napalm", d)) {
      put(w, i, EL.fire, d);
      return;
    }
  }
  fall(w, i, d, 7000, true);
}

// Cryo beside lava is gone and sets the lava into stone
function coolLava(w, i, d) {
  const j = touching(w, i, d, EL.lava);
  if (j < 0) {
    return false;
  }
  setLava(w, j, d);
  put(w, i, 0, d);
  return true;
}

// Cryo beside water or ice turns both into chilled ice
function chillIce(w, i, d) {
  let j = touching(w, i, d, EL.water);
  if (j < 0) {
    j = touching(w, i, d, EL.ice);
  }
  if (j < 0) {
    return false;
  }
  putKeepHeat(w, j, EL.chilledIce, d);
  putKeepHeat(w, i, EL.chilledIce, d);
  return true;
}

// Whether cryo i is against a solid it freezes a crust onto (the solid stays as it was)
function againstSolid(w, i) {
  for (const offset of SIDES) {
    if (CRYO_CRUSTS_ON.has(w.el[i + offset])) {
      return true;
    }
  }
  return false;
}

function cryo(w, x, y, i, d) {
  if (coolLava(w, i, d) || chillIce(w, i, d)) {
    return;
  }
  if (againstSolid(w, i)) {
    putKeepHeat(w, i, EL.chilledIce, d);
    return;
  }
  fall(w, i, d, 9500, true);
}

function moltenGlass(w, x, y, i, d) {
  if (w.heat[i] < MOLTEN_GLASS_SETS_BELOW) {
    put(w, i, EL.glass, d);
    return;
  }
  fall(w, i, d, 4000, true);
}

function moltenMetal(w, x, y, i, d) {
  if (w.heat[i] < MOLTEN_METAL_SETS_BELOW) {
    put(w, i, EL.metal, d);
    return;
  }
  fall(w, i, d, 6000, true);
}

// Drips set where they land: with nowhere to fall (straight down or diagonally) the wax hardens
function liquidWax(w, x, y, i, d) {
  if (w.el[i + W] !== 0 && w.el[i + W - 1] !== 0 && w.el[i + W + 1] !== 0) {
    put(w, i, EL.wax, d);
    return;
  }
  fall(w, i, d, 8000, false);
}

export const RULES = {
  [EL.water]: water,
  [EL.saltWater]: saltWater,
  [EL.oil]: oil,
  [EL.lava]: lava,
  [EL.acid]: acid,
  [EL.honey]: honey,
  [EL.nitro]: nitro,
  [EL.chargedNitro]: chargedNitro,
  [EL.napalm]: napalm,
  [EL.cryo]: cryo,
  [EL.moltenGlass]: moltenGlass,
  [EL.moltenMetal]: moltenMetal,
  [EL.liquidWax]: liquidWax,
};
