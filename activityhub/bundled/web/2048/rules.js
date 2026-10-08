// 2048's rules, mirrored in bundled/twenty48.py. The bot replays a round from its seed and moves, so any
// change here must be made there too, or every saved round will be refused.

export const SIZE = 4;

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

// Cell indexes of each row or column, starting from the edge the tiles slide toward
export function lines(direction) {
  const rows = [];
  const cols = [];
  for (let a = 0; a < SIZE; a++) {
    rows.push([...Array(SIZE).keys()].map((b) => a * SIZE + b));
    cols.push([...Array(SIZE).keys()].map((b) => b * SIZE + a));
  }
  if (direction === "L") {
    return rows;
  }
  if (direction === "R") {
    return rows.map((row) => row.reverse());
  }
  if (direction === "U") {
    return cols;
  }
  return cols.map((col) => col.reverse());
}

export class Board {
  constructor(seed) {
    this.rng = makeRng(seed);
    this.cells = Array(SIZE * SIZE).fill(0);
    this.score = 0;
    this.spawn();
    this.spawn();
  }

  // Returns the cell the new tile went in
  spawn() {
    const free = [];
    this.cells.forEach((value, i) => {
      if (!value) {
        free.push(i);
      }
    });
    const cell = free[this.rng.pick(free.length)];
    this.cells[cell] = this.rng.pick(10) === 0 ? 4 : 2;
    return cell;
  }

  // Slides every tile, merging equal pairs once. Returns null when nothing moved, otherwise what happened:
  // slides lists [from, to] for every tile, merged lists the cells that doubled, spawned is the new tile's cell
  move(direction) {
    const before = [...this.cells];
    const slides = [];
    const merged = [];
    for (const line of lines(direction)) {
      const tiles = line.filter((i) => this.cells[i]).map((i) => ({ from: i, value: this.cells[i] }));
      const out = [];
      while (tiles.length) {
        const to = line[out.length];
        if (tiles.length > 1 && tiles[0].value === tiles[1].value) {
          const value = tiles[0].value * 2;
          slides.push([tiles[0].from, to], [tiles[1].from, to]);
          merged.push(to);
          this.score += value;
          out.push(value);
          tiles.splice(0, 2);
        } else {
          slides.push([tiles[0].from, to]);
          out.push(tiles.shift().value);
        }
      }
      line.forEach((cell, i) => {
        this.cells[cell] = out[i] || 0;
      });
    }
    if (this.cells.every((value, i) => value === before[i])) {
      return null;
    }
    return { slides, merged, spawned: this.spawn() };
  }

  canMove() {
    for (let i = 0; i < this.cells.length; i++) {
      const value = this.cells[i];
      const right = i % SIZE < SIZE - 1 ? this.cells[i + 1] : null;
      const below = i + SIZE < this.cells.length ? this.cells[i + SIZE] : null;
      if (!value || value === right || value === below) {
        return true;
      }
    }
    return false;
  }
}
