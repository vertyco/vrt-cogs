// Machine rules: endless sources (spout, well, gas vent, cloner) and the drain. The heater and cooler have no rule:
// heat.js resets them to their own temperature every step.
import { EL, ELEMENTS } from "../elements.js";
import { emit, put, SIDES, touching } from "../helpers.js";

const SPOUT_EMITS = 500;
const SPOUT_EATEN = 1000;
const WELL_EMITS = 1000;
const VENT_EMITS = 1000;
const CLONER_EMITS = 500;

// A cloner's life holds the element it copies plus one, so 0 means it has not met anything yet
function cloned(w, i) {
  return w.life[i] - 1;
}

// Walls would make every cloner in a cup copy the cup, and machines are never copied
function clonable(id) {
  return id !== 0 && id !== EL.wall && ELEMENTS[id].kind !== "machine";
}

// Water on every free side. One grain of sand next to it turns it to sand, so a line of spouts is eaten grain by grain.
function spout(w, x, y, i, d) {
  emit(w, i, d, EL.water, SPOUT_EMITS, false);
  if (touching(w, i, d, EL.sand) >= 0 && d.chance(SPOUT_EATEN)) {
    put(w, i, EL.sand, d);
  }
}

function well(w, x, y, i, d) {
  emit(w, i, d, EL.oil, WELL_EMITS, false);
}

function gasVent(w, x, y, i, d) {
  emit(w, i, d, EL.methane, VENT_EMITS, false);
}

// Remembers the first thing that touches it (neighbours are looked at from a random side), then pours out copies
function cloner(w, x, y, i, d) {
  if (w.life[i] === 0) {
    const from = d.roll(SIDES.length);
    for (let k = 0; k < SIDES.length; k++) {
      const id = w.el[i + SIDES[(from + k) % SIDES.length]];
      if (clonable(id)) {
        w.life[i] = id + 1;
        return;
      }
    }
    return;
  }
  emit(w, i, d, cloned(w, i), CLONER_EMITS, false);
}

// Whatever touches the drain is gone. Walls and other machines stay, or a drain in a cup would eat the cup.
function drain(w, x, y, i, d) {
  for (const offset of SIDES) {
    const id = w.el[i + offset];
    if (id !== 0 && id !== EL.wall && ELEMENTS[id].kind !== "machine") {
      put(w, i + offset, 0, d);
    }
  }
}

export const RULES = {
  [EL.spout]: spout,
  [EL.well]: well,
  [EL.gasVent]: gasVent,
  [EL.cloner]: cloner,
  [EL.drain]: drain,
};
