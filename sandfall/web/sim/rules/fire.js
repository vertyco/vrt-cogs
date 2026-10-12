// Fire and torches. Fire has no timer of its own: it is a short-lived cell that climbs, and fuel next to it keeps it
// alive. Fire lit from wood or a branch also carries a fuel count in its life field.
import { EL } from "../elements.js";
import { AROUND, emit, near, put, touching } from "../helpers.js";
import { W } from "../world.js";

// Life values of a fire cell: 0 is ordinary fire, 1 to 40 is the steps of fuel left (wood, branch), and PLANT_FIRE
// marks fire lit from a plant or a leaf
export const PLANT_FIRE = 0x8000;
const FUEL_MIN = 20;
const FUEL_SPAN = 21;
const ASH_FROM_PLANT = 2500;
const SMOKE_CHANCE = 2500;

// What keeps a flame alive next to it (oil only half the time)
const FUELS = new Set([EL.plant, EL.fuse, EL.branch, EL.leaf, EL.wood]);

// The first empty cell a wax drip can land in: down, down-left, down-right, right, left
const DRIP = [W, W - 1, W + 1, 1, -1];

/** Sets cell i alight. What it was decides how the fire lasts: wood and branches burn for a while, plants leave ash */
export function ignite(w, i, d) {
  const was = w.el[i];
  put(w, i, EL.fire, d);
  if (was === EL.wood || was === EL.branch) {
    w.life[i] = FUEL_MIN + d.roll(FUEL_SPAN);
  } else if (was === EL.plant || was === EL.leaf) {
    w.life[i] = PLANT_FIRE;
  }
}

/** A wax cell catches fire and drips: the first empty cell below or beside it becomes liquid wax */
export function waxDrip(w, i, d) {
  put(w, i, EL.fire, d);
  for (const offset of DRIP) {
    if (w.el[i + offset] === 0) {
      put(w, i + offset, EL.liquidWax, d);
      return;
    }
  }
}

// Water next to this fire: the water becomes steam and the fire is gone
function douse(w, i, d) {
  let j = touching(w, i, d, EL.water);
  if (j < 0) {
    j = touching(w, i, d, EL.saltWater);
  }
  if (j < 0 || !d.chance(8000)) {
    return false;
  }
  put(w, j, EL.steam, d);
  put(w, i, 0, d);
  w.events.sizzle += 1;
  return true;
}

// A side neighbour that is wax, solid or melted: a flame heats wax past its melting point, so the melted top of a
// candle has to keep the flame alive too. Returns its index or -1.
function touchingWax(w, i, d) {
  const j = touching(w, i, d, EL.wax);
  return j >= 0 ? j : touching(w, i, d, EL.liquidWax);
}

// Whether something that burns is next to the flame and so keeps it alive. Oil only counts half the time. Wax counts too.
function hasFuel(w, i, d) {
  let oil = false;
  for (const offset of AROUND) {
    const id = w.el[i + offset];
    if (FUELS.has(id)) {
      return true;
    }
    oil = oil || id === EL.oil;
  }
  return (oil && d.chance(5000)) || touchingWax(w, i, d) >= 0;
}

// A flame lit from a plant dies: it leaves ash 1 time in 4, else smoke 1 time in 4, else nothing. Other flames just go.
function goOut(w, i, d) {
  if (w.life[i] !== PLANT_FIRE) {
    put(w, i, 0, d);
  } else if (d.chance(ASH_FROM_PLANT)) {
    put(w, i, EL.ash, d);
  } else if (d.chance(SMOKE_CHANCE)) {
    put(w, i, EL.smoke, d);
  } else {
    put(w, i, 0, d);
  }
}

// Burns down the fuel count. Returns true when the fuel ran out: the cell becomes ash and may puff smoke above it.
function burnFuel(w, i, d) {
  const left = w.life[i];
  if (left === 0 || left >= PLANT_FIRE) {
    return false;
  }
  if (left > 1) {
    w.life[i] = left - 1;
    return false;
  }
  put(w, i, EL.ash, d);
  if (w.el[i - W] === 0 && d.chance(SMOKE_CHANCE)) {
    put(w, i - W, EL.smoke, d);
  }
  return true;
}

// Rules 2 and 3: eat a plant, light a fuse. Returns true when one of them happened. Wax drips by its own rule only,
// so a candle burns down slowly.
function spread(w, i, d) {
  if (d.chance(2000)) {
    const plant = near(w, i, d, EL.plant);
    if (plant >= 0) {
      ignite(w, plant, d);
      return true;
    }
  }
  if (d.chance(8000)) {
    const fuse = near(w, i, d, EL.fuse);
    if (fuse >= 0) {
      ignite(w, fuse, d);
      return true;
    }
  }
  return false;
}

// In order, the first one that happens wins: douse, spread, go out, climb
function fire(w, x, y, i, d) {
  if (burnFuel(w, i, d) || douse(w, i, d) || spread(w, i, d)) {
    return;
  }
  const fueled = w.life[i] > 0 && w.life[i] < PLANT_FIRE;
  if (d.chance(4000) && !fueled && !hasFuel(w, i, d)) {
    goOut(w, i, d);
    return;
  }
  if (d.chance(5000) && w.el[i - W] === 0) {
    put(w, i - W, EL.fire, d);
  }
}

// Never moves, never goes out, and sets fire to whatever is next to it, walls included
function torch(w, x, y, i, d) {
  emit(w, i, d, EL.fire, 2500, true);
}

export const RULES = {
  [EL.fire]: fire,
  [EL.torch]: torch,
};
