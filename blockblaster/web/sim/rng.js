// mulberry32 on a 32-bit seed. common/sim/rng.py gives the same numbers for the same seed.
import { idiv } from "./mathx.js";

// Plain data (one whole number, kept unsigned), so a state can be copied
export class Rng {
  constructor(seed) {
    this.state = seed >>> 0;
  }

  nextU32() {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(this.state ^ (this.state >>> 15), this.state | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t;
    return (t ^ (t >>> 14)) >>> 0;
  }

  // A whole number from 0 to n - 1
  randInt(n) {
    return idiv(this.nextU32() * n, 2 ** 32);
  }
}
