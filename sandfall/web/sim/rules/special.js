// Special rules: the ??? wave, the red dust it leaves, and Mystery with its four shows.
import { EL } from "../elements.js";
import { fall, near, put, swap, touching } from "../helpers.js";
import { showRunning, spawnNuke, spawnSpiral, spawnStar } from "../particles.js";
import { H, W } from "../world.js";

const WAVE_SPREADS = 6500;
const RED_DUST_FADES = 200;
const MYSTERY_FALLS = 9500;

// The order the original checks the wave's neighbours in: down, up, right, left
const WAVE_REACH = [W, -W, 1, -1];

// The wave eats everything it touches, walls included, except plants and its own trail. It runs on while it keeps
// spreading and turns to red dust the first time it doesn't. Writing into the row above lets it climb fast.
function wave(w, x, y, i, d) {
  if (!d.chance(WAVE_SPREADS)) {
    put(w, i, EL.redDust, d);
    return;
  }
  for (const offset of WAVE_REACH) {
    const j = i + offset;
    const id = w.el[j];
    if (id !== EL.wave && id !== EL.redDust && id !== EL.plant) {
      put(w, j, EL.wave, d);
    }
  }
}

function redDust(w, x, y, i, d) {
  if (d.chance(RED_DUST_FADES)) {
    put(w, i, 0, d);
  }
}

// Empties every fire and Mystery cell, then swaps every other cell except walls with a random one that is not a wall
function scramble(w, d) {
  const across = W - 2;
  const cells = across * (H - 2);
  for (let y = 1; y <= H - 2; y++) {
    for (let x = 1; x <= W - 2; x++) {
      const i = y * W + x;
      if (w.el[i] === EL.fire || w.el[i] === EL.mystery) {
        put(w, i, 0, d);
      }
    }
  }
  for (let y = 1; y <= H - 2; y++) {
    for (let x = 1; x <= W - 2; x++) {
      const i = y * W + x;
      const pick = d.roll(cells);
      const j = (1 + Math.trunc(pick / across)) * W + 1 + (pick % across);
      if (w.el[i] !== EL.wall && w.el[j] !== EL.wall) {
        swap(w, i, j);
      }
    }
  }
}

// Mystery by what it touches, checked in this order: sand makes a star, salt a spiral, fire scrambles the world,
// pollen sets off a nuke. A show that can't start (the particle pool is full) leaves the Mystery as it was.
function mystery(w, x, y, i, d) {
  if (showRunning()) {
    put(w, i, 0, d);
    return;
  }
  if (near(w, i, d, EL.sand) >= 0 && spawnStar(w, x, y, d)) {
    put(w, i, 0, d);
    return;
  }
  if (near(w, i, d, EL.salt) >= 0 && spawnSpiral(w, d)) {
    put(w, i, 0, d);
    return;
  }
  if (touching(w, i, d, EL.fire) >= 0) {
    scramble(w, d);
    return;
  }
  if (touching(w, i, d, EL.pollen) >= 0 && spawnNuke(w, x, y, d)) {
    w.events.boom += 1;
    put(w, i, 0, d);
    return;
  }
  fall(w, i, d, MYSTERY_FALLS, true);
}

export const RULES = {
  [EL.wave]: wave,
  [EL.redDust]: redDust,
  [EL.mystery]: mystery,
};
