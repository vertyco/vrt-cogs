// Heat: every cell shares its temperature with its right and lower neighbour, then the few fixed heat sources and the
// slow drift of empty air toward room temperature are applied. Everything is whole numbers.
import { EL, ELEMENTS } from "./elements.js";
import { H, HEAT_MAX, HEAT_MIN, N, ROOM, W } from "./world.js";

const COND = Uint8Array.from(ELEMENTS, (e) => e.cond);

// Elements that reset to their own temperature every step: fire, heater, cooler, burning thermite
const HOLDS = new Map([
  [EL.fire, 600],
  [EL.heater, 400],
  [EL.cooler, -100],
  [EL.burningThermite, 2500],
]);
const HELD = new Uint8Array(ELEMENTS.length);
const HELD_HEAT = new Int16Array(ELEMENTS.length);
for (const [id, heat] of HOLDS) {
  HELD[id] = 1;
  HELD_HEAT[id] = heat;
}

// Heat each cell gains this step, filled from the temperatures before any of them change
const gain = new Int32Array(N);

// flow = (hotter - colder) * min(conductivities, 32) / 128, rounded to the nearest whole degree (a half goes toward
// zero), moved from the hotter cell to the colder. A cell shares with 4 neighbours at once, so a pair may pass at most
// 1/4 of the difference (32 / 128) or the heat overshoots and grows without bound. Conductivities keep their order up
// to 32 (metal, the heater and the cooler all pass the most), so metal moves heat about 4 times faster than air. A
// bigger divisor would widen that gap, but rounding down to zero would then leave a dead band wide enough that snow and
// ice stop warming short of melting; rounding to the nearest keeps the band as narrow as it was.
const MOST_CONDUCTED = 32;

function flowBetween(heat, a, b, ca, cb) {
  const diff = heat[a] - heat[b];
  if (diff === 0) {
    return;
  }
  const least = ca < cb ? ca : cb;
  const scaled = (diff < 0 ? -diff : diff) * (least < MOST_CONDUCTED ? least : MOST_CONDUCTED);
  const flow = diff < 0 ? -((scaled + 63) >> 7) : (scaled + 63) >> 7;
  gain[a] -= flow;
  gain[b] += flow;
}

// Moves heat between every cell and its right and lower neighbour
function conduct(w) {
  const { el, heat } = w;
  gain.fill(0);
  for (let y = 0; y < H; y++) {
    const row = y * W;
    for (let x = 0; x < W; x++) {
      const i = row + x;
      const c = COND[el[i]];
      if (x < W - 1) {
        flowBetween(heat, i, i + 1, c, COND[el[i + 1]]);
      }
      if (y < H - 1) {
        flowBetween(heat, i, i + W, c, COND[el[i + W]]);
      }
    }
  }
}

/** One step of heat: sources reset, neighbours share, empty air drifts toward room temperature, then clamp */
export function diffuseHeat(w) {
  const { el, heat } = w;
  for (let i = 0; i < N; i++) {
    if (HELD[el[i]] === 1) {
      heat[i] = HELD_HEAT[el[i]];
    }
  }
  conduct(w);
  const drift = (w.step & 7) === 0;
  for (let i = 0; i < N; i++) {
    let h = heat[i] + gain[i];
    if (drift && el[i] === 0) {
      h += h < ROOM ? 1 : h > ROOM ? -1 : 0;
    }
    heat[i] = h < HEAT_MIN ? HEAT_MIN : h > HEAT_MAX ? HEAT_MAX : h;
  }
}
