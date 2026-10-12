// The simulation's only source of chance. Every screen in a shared world seeds it the same way, so every screen rolls
// the same numbers in the same order.

/** A small xorshift32 number generator */
export class Dice {
  constructor(state) {
    // xorshift32 never leaves 0, so 0 is swapped for a fixed non-zero start
    this.state = state >>> 0 || 0x9e3779b9;
  }

  /** The next whole number, 0 to 2^32 - 1 */
  next() {
    let x = this.state;
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    this.state = x >>> 0;
    return this.state;
  }

  /** A whole number from 0 to n - 1 */
  roll(n) {
    return n <= 1 ? 0 : this.next() % n;
  }

  /** True with chance p out of 10,000 ("25%" is chance(2500)) */
  chance(p) {
    return this.roll(10000) < p;
  }
}

function scramble(h) {
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
}

/** A non-zero uint32 seed made from three whole numbers, so nearby inputs give unrelated dice */
export function mix(a, b, c) {
  let h = scramble((a >>> 0) ^ 0x6a09e667);
  h = scramble(h ^ Math.imul(b >>> 0, 0x9e3779b1));
  h = scramble(h ^ Math.imul(c >>> 0, 0x85ebca77));
  return h || 1;
}
