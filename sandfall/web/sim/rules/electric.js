// Electricity: the spark, the battery, and the current that runs along metal.
//
// A metal cell keeps its electric state in its life field:
//   0           ready: can be electrified
//   1 or 2      electrified, stamped with the parity of the step that did it (1 + step & 1). The scan writes into the
//               grid as it goes, so a cell electrified this step must not pass the current on until the next one
//   11 to 14    resting after passing the current on, counting down to 0 over 4 steps
import { EL, ELEMENTS } from "../elements.js";
import { AROUND, put, SIDES } from "../helpers.js";
import { HEAT_MAX } from "../world.js";
import { ignite } from "./fire.js";

const LIVE_BASE = 1;
const REST_BASE = 10;
const REST_STEPS = 4;
const BATTERY_EVERY = 8;
const HEATS_BY = 20;
const LIGHTS_AT = 1000;
const CATCH_CHANCE = 1000;
const SET_OFF_HEAT = 1000;

/** What current sets off through the heat the element already counts as fire at */
export const EXPLOSIVES = new Set([EL.gunpowder, EL.c4, EL.nitro, EL.methane]);

/**
 * Electrifies metal cell i when it is ready. early is for strokes, which land between steps: the cell then passes the
 * current on during the very next step instead of the one after. Returns whether it was electrified.
 */
export function electrify(w, i, early) {
  if (w.el[i] !== EL.metal || w.life[i] !== 0) {
    return false;
  }
  w.life[i] = LIVE_BASE + ((w.step + (early ? 1 : 0)) & 1);
  return true;
}

// Whatever burns next to a live cell may catch fire, and explosives go off
function shock(w, i, d) {
  for (const offset of AROUND) {
    const j = i + offset;
    const id = w.el[j];
    if (EXPLOSIVES.has(id)) {
      w.heat[j] = Math.max(w.heat[j], SET_OFF_HEAT);
    } else if (ELEMENTS[id].burns && d.chance(CATCH_CHANCE)) {
      ignite(w, j, d);
    }
  }
}

/** One step of a metal cell's electric state: wait, pass the current on to touching metal, rest */
export function carryCurrent(w, i, d) {
  const state = w.life[i];
  if (state === 0) {
    return;
  }
  if (state > REST_BASE) {
    w.life[i] = state === REST_BASE + 1 ? 0 : state - 1;
    return;
  }
  if (state - LIVE_BASE === (w.step & 1)) {
    return;
  }
  w.heat[i] = Math.min(HEAT_MAX, w.heat[i] + HEATS_BY);
  for (const offset of SIDES) {
    electrify(w, i + offset, false);
  }
  shock(w, i, d);
  w.life[i] = REST_BASE + REST_STEPS;
}

// Electrifies every ready metal cell touching cell i. Returns whether any metal is touching it at all.
function touchMetal(w, i) {
  let found = false;
  for (const offset of SIDES) {
    if (w.el[i + offset] === EL.metal) {
      found = true;
      if (electrify(w, i + offset, false)) {
        w.events.zap += 1;
      }
    }
  }
  return found;
}

// Touching metal it electrifies it and is spent; anywhere else it is a one-step flash of fire
function spark(w, x, y, i, d) {
  put(w, i, touchMetal(w, i) ? 0 : EL.fire, d);
}

// Every 8 steps it electrifies the metal touching it
function battery(w, x, y, i, d) {
  if ((w.step & (BATTERY_EVERY - 1)) === 0) {
    touchMetal(w, i);
  }
}

export const RULES = {
  [EL.spark]: spark,
  [EL.battery]: battery,
};
