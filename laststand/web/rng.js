// The one random source of a story. Every rule that rolls dice reads it (random(n) is Flash's: a whole number from 0
// to n - 1; float() stands in for Math.random). It is seeded when a story starts or loads, and nothing is replayed, so
// the seed is never saved. Pictures that only need to look different (blood spray, a casing's spin) use Math.random.

// Mulberry32: four lines, a full 32-bit period and no visible pattern at the numbers a game draws
function mulberry(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let next = mulberry(Date.now());

export const rng = {
  // Starts the sequence over from a number (a new story or a load passes the time)
  seed(value = Date.now()) {
    next = mulberry(Number(value) || 0);
  },

  // A number from 0 up to, but not including, 1
  float() {
    return next();
  },

  // Flash's random(n): a whole number from 0 to n - 1
  random(n) {
    return Math.floor(next() * n);
  },

  // The original's getIntInRange: a whole number from a to b, both included
  range(a, b) {
    return Math.floor(a + (b - a + 1) * next());
  },

  // One member of a list, or undefined for an empty one
  pick(list) {
    return list[Math.floor(next() * list.length)];
  },
};
