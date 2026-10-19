// The run's only source of chance. The bot picks the seed, so the page and the bot's check roll the same numbers in
// the same order.

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
}
