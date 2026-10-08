// Snake's rules, mirrored in bundled/snake.py. The bot replays a round from its seed and turns, so any
// change here must be made there too, or every saved round will be refused.

export const SIZE = 20;
const START = [
  [10, 10],
  [9, 10],
  [8, 10],
];
export const DIRECTIONS = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] };
export const OPPOSITE = { U: "D", D: "U", L: "R", R: "L" };

// Mulberry32, the same random number generator as bundled/rng.py
export function makeRng(seed) {
  let state = seed >>> 0;
  function next() {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), state | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t;
    return (t ^ (t >>> 14)) >>> 0;
  }
  return { next, pick: (count) => Math.floor((next() * count) / 4294967296) };
}

// Milliseconds per step: the snake speeds up as it eats
export function tickMs(apples) {
  return Math.max(60, 140 - 3 * apples);
}

const cellKey = ([x, y]) => y * SIZE + x;

export class SnakeGame {
  constructor(seed) {
    this.rng = makeRng(seed);
    this.body = START.map((cell) => [...cell]);
    this.cells = new Set(this.body.map(cellKey));
    this.heading = "R";
    this.apples = 0;
    this.over = false;
    this.food = this.placeFood();
  }

  placeFood() {
    const free = [];
    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        if (!this.cells.has(y * SIZE + x)) {
          free.push([x, y]);
        }
      }
    }
    return free.length ? free[this.rng.pick(free.length)] : null;
  }

  // Going the same way or straight back is not a turn
  canTurn(heading) {
    return heading !== this.heading && heading !== OPPOSITE[this.heading];
  }

  turn(heading) {
    if (!this.canTurn(heading)) {
      return false;
    }
    this.heading = heading;
    return true;
  }

  step() {
    const [dx, dy] = DIRECTIONS[this.heading];
    const head = [this.body[0][0] + dx, this.body[0][1] + dy];
    const eating = this.food !== null && head[0] === this.food[0] && head[1] === this.food[1];
    // The tail moves out of the way first, so chasing your own tail is allowed
    if (!eating) {
      this.cells.delete(cellKey(this.body.pop()));
    }
    const outside = head[0] < 0 || head[0] >= SIZE || head[1] < 0 || head[1] >= SIZE;
    if (outside || this.cells.has(cellKey(head))) {
      this.over = true;
      return { ate: false, died: true };
    }
    this.body.unshift(head);
    this.cells.add(cellKey(head));
    if (eating) {
      this.apples += 1;
      this.food = this.placeFood();
      // A full board is a win, and the round ends there
      this.over = this.food === null;
    }
    return { ate: eating, died: false };
  }
}
