// The world: four planes of cells plus the few numbers that last from step to step.
import { EL, ELEMENT_COUNT } from "./elements.js";

export const W = 320;
export const H = 180;
export const N = W * H;
export const ROOM = 20;
export const HEAT_MIN = -273;
export const HEAT_MAX = 9999;
// The particle pool: at most PART_MAX live particles, each a record of PART_FIELDS whole numbers
// (type, x, y, vx, vy, size, age, life, a, b), the live ones packed at the front in the order they were made
export const PART_MAX = 600;
export const PART_FIELDS = 10;

/** A fresh empty world. seed is a uint32 the page picks; every screen given the same seed computes the same world. */
export function createWorld({ seed }) {
  const heat = new Int16Array(N);
  heat.fill(ROOM);
  return {
    seed: seed >>> 0,
    step: 0,
    strokeCount: 0,
    el: new Uint8Array(N),
    shade: new Uint8Array(N),
    heat,
    life: new Uint16Array(N),
    spigots: [
      [EL.sand, 1],
      [EL.water, 1],
      [EL.salt, 1],
      [EL.oil, 1],
    ],
    // floor 0 drains the bottom row, 1 makes it solid. slug 0 move, 1 stop, 2 gone. backdrop 0 Dusk..3 Cave.
    settings: { floor: 0, slug: 0, zombies: 0, backdrop: 0 },
    parts: { n: 0, rec: new Int32Array(PART_MAX * PART_FIELDS) },
    slug: null,
    zombies: [],
    grabs: new Map(),
    tally: new Uint32Array(ELEMENT_COUNT),
    events: { boom: 0, sizzle: 0, zap: 0, bolt: 0 },
  };
}
