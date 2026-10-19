// Turns a compact level from a pack into the Level the simulation plays.
// Mirrors common/sim/level.py, which the bot runs; both must give identical output.

export const ALPHABET = "0123456789abcdefghijklmnopqrstuvwx";
export const EMPTY = ".";

// Rebuild the cubes from the color grid, the multi-cell anchors and the health list
export function expand(compact) {
  const width = compact.w;
  const height = compact.h;
  const grid = compact.grid;
  const areas = new Map();
  for (const [x, y, ax, ay] of compact.big) {
    areas.set(y * width + x, [ax, ay]);
  }
  const health = new Map();
  for (const [x, y, hp] of compact.hp) {
    health.set(y * width + x, hp);
  }
  const covered = new Set();
  for (const [x, y, ax, ay] of compact.big) {
    for (let cx = x; cx < x + ax; cx++) {
      for (let cy = y; cy < y + ay; cy++) {
        if (cx !== x || cy !== y) {
          covered.add(cy * width + cx);
        }
      }
    }
  }
  const cubes = [];
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      const cell = y * width + x;
      const char = grid[cell];
      if (char === EMPTY || covered.has(cell)) {
        continue;
      }
      const [ax, ay] = areas.get(cell) || [1, 1];
      cubes.push([x, y, ALPHABET.indexOf(char), ax, ay, health.has(cell) ? health.get(cell) : 1]);
    }
  }
  return {
    number: compact.n,
    difficulty: compact.d,
    width,
    height,
    pw: compact.pw,
    slotCount: compact.slots,
    conveyorLimit: compact.trays,
    cubes,
    queues: structuredClone(compact.queues),
    features: structuredClone(compact.fx),
    used: [...compact.f],
  };
}
