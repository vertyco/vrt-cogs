// Gas rules. Each rule is (w, x, y, i, d) and runs once per cell per step during the scan.
import { EL, ELEMENTS } from "../elements.js";
import { put, rise, swap, touching } from "../helpers.js";
import { spawnFireball } from "../particles.js";
import { W } from "../world.js";

const COOLS_BELOW = 80;
// Condensing gives the heat away, so the new drop falls as rain instead of meeting the steam around it and boiling again
const RAIN_HEAT = 40;
const METHANE_LIGHTS_AT = 400;

// What sinks through methane and steam: powders and liquids, lava too, so lava over water never rests on its own steam
const HEAVIER = Uint8Array.from(ELEMENTS, (e) => (e.kind === "powder" || e.kind === "liquid" ? 1 : 0));
// The cells above a gas cell: straight up, then the two diagonals
const ABOVE = [-W, -W - 1, -W + 1];

// Steam turns back into water when it cools, touches water or a spout, or collects under a ceiling
function condense(w, i, d) {
  if (w.heat[i] < COOLS_BELOW) {
    put(w, i, EL.water, d);
    w.heat[i] = RAIN_HEAT;
    return true;
  }
  if (d.chance(500) && (touching(w, i, d, EL.water) >= 0 || touching(w, i, d, EL.spout) >= 0)) {
    put(w, i, EL.water, d);
    w.heat[i] = RAIN_HEAT;
    return true;
  }
  if (w.el[i - W] !== 0 && w.el[i + W] === 0 && d.chance(200)) {
    put(w, i, d.chance(3000) ? EL.water : 0, d);
    return true;
  }
  return false;
}

function steam(w, x, y, i, d) {
  if (!condense(w, i, d) && !rise(w, i, d, 7000)) {
    bubble(w, i, d, 7000);
  }
}

// Smoke counts its life down and fades away; it is made with 60 to 200 steps
function smoke(w, x, y, i, d) {
  if (w.life[i] <= 1) {
    put(w, i, 0, d);
    return;
  }
  w.life[i] -= 1;
  rise(w, i, d, 5000);
}

// Anything heavier above a gas swaps down through it p of the steps, so the gas bubbles up through everything
function bubble(w, i, d, p) {
  if (!d.chance(p)) {
    return;
  }
  const from = d.roll(3);
  for (let k = 0; k < 3; k++) {
    const j = i + ABOVE[(from + k) % 3];
    if (HEAVIER[w.el[j]] === 1) {
      swap(w, i, j);
      return;
    }
  }
}

// Fire beside methane (or enough heat) sets off a quick fireball; with no fireball free the methane itself burns
function methane(w, x, y, i, d) {
  if (d.chance(2500) && (w.heat[i] >= METHANE_LIGHTS_AT || touching(w, i, d, EL.fire) >= 0)) {
    w.events.boom += 1;
    if (!spawnFireball(w, x, y, "methane", d)) {
      put(w, i, EL.fire, d);
      return;
    }
  }
  if (!rise(w, i, d, 2500)) {
    bubble(w, i, d, 8500);
  }
}

// Acid fumes fade after the life they are made with, and eat any plant or leaf they touch
function acidFumes(w, x, y, i, d) {
  if (w.life[i] <= 1) {
    put(w, i, 0, d);
    return;
  }
  w.life[i] -= 1;
  if (d.chance(500)) {
    let j = touching(w, i, d, EL.plant);
    if (j < 0) {
      j = touching(w, i, d, EL.leaf);
    }
    if (j >= 0) {
      put(w, j, 0, d);
    }
  }
  rise(w, i, d, 4000);
}

export const RULES = {
  [EL.steam]: steam,
  [EL.smoke]: smoke,
  [EL.methane]: methane,
  [EL.acidFumes]: acidFumes,
};
