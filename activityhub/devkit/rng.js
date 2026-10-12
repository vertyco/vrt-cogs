// Mulberry32, a small random number generator. rng.py gives the same numbers for the same seed, so the bot can
// replay a round the page played: the bot picks a seed, the page rolls with it, and the bot rolls the same.
// Copy both files into your game: this one into web_dir, rng.py next to your cog's Python.
export function makeRng(seed) {
  let state = seed >>> 0;
  // A whole number from 0 up to, not including, 2 ** 32
  function next() {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), state | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t;
    return (t ^ (t >>> 14)) >>> 0;
  }
  // A whole number from 0 up to, not including, count. rng.py matches it for counts up to about 2 million
  return { next, pick: (count) => Math.floor((next() * count) / 4294967296) };
}
