// The slug: Hell of Sand's soft-body blob. A ring of 32 points around a centre point, tied together by springs, moved
// by Verlet steps (a point's speed is where it is minus where it was). It is not made of cells: it eats the water and
// salt its outline touches, catches fire from the fire beside it, and is stopped by any filled cell.
//
// Every number is whole: positions in 256ths of a cell, scale in 1000ths, power in 10000ths, other ratios in 1024ths.
// Lengths are a third of the original's, whose world was three times wider.
import { EL } from "./elements.js";
import { put } from "./helpers.js";
import { spawnBurst } from "./particles.js";
import { SLUG_POINTS } from "./slugbytes.js";
import { cos256, isqrt, sin256 } from "./trig.js";
import { H, W } from "./world.js";

export { packSlug, SLUG_BYTES, SLUG_POINTS, unpackSlug } from "./slugbytes.js";

const ONE = 256;
// The ring's points are 1..RING and point 0 is the centre. Each ring point is tied to the next REACH points round
// the ring.
const RING = SLUG_POINTS - 1;
const REACH = RING >> 2;
// The original's ring radius of 10, a third as long
const START_RADIUS = Math.trunc((10 * ONE) / 3);
const START_SCALE = 2000;
const POWER_REST = 2000;
const POWER_MAX = 10000;
// A scale that drops below SCALE_LOW jumps back to SCALE_RESET, as in the original
const SCALE_LOW = 10;
const SCALE_RESET = 100;
// It bursts when scale x (1000 + deaths) drops below this: the original's scale x (10 + deaths x 0.01) < 9
const BURST_BELOW = 900000;
const BURST_PARTS = 20;
// 0.95 of the speed stays each step; gravity is 0.1 cells a step
const DAMP = 973;
const GRAVITY = 26;
// When a point hits the world's edge it keeps a tenth of its sideways move (a half at the bottom)
const EDGE_SLIDE = 102;
const FLOOR_SLIDE = 512;
const WALL_LEFT = 1;
const WALL_RIGHT = 2;
const WALL_TOP = 4;
const WALL_BOTTOM = 8;
// Fire beside the outline catches 95% of the time, and each outline cell that catches costs this much scale. A slug
// caught in fire shrinks and bursts (a new one is born) instead of burning in place for good, held by its own flames.
const FIRE_CATCH = 9500;
const BURN_SCALE = 1;
// What one eaten cell does to scale and power
const WATER_SCALE = 2;
const WATER_POWER = 20;
const SALT_SCALE = -5;
const SALT_POWER = 100;
// The world menu's Slug setting
const MOVE = 0;
const GONE = 2;
// A new slug tries this many random spots for one where none of its points sits in a filled cell
const SPOT_TRIES = 8;

// The springs, as two lists of point numbers: every ring point to the next REACH ring points, then the spokes
const LINK_A = [];
const LINK_B = [];
for (let p = 1; p <= RING; p++) {
  for (let m = 1; m <= REACH; m++) {
    LINK_A.push(p);
    LINK_B.push(((p - 1 + m) % RING) + 1);
  }
}
for (let p = 1; p <= RING; p++) {
  LINK_A.push(0);
  LINK_B.push(p);
}

// The ring's resting outline around (0, 0): radius / (|cos(k a / 4)| + |sin(k a / 4)|) at each point's angle a, a
// lumpy shape that differs with k. Angles are in 256ths of a turn; point p sits at (p + 2) 32nds of a turn.
function outlinePoints(k, radius) {
  const xs = new Int32Array(SLUG_POINTS);
  const ys = new Int32Array(SLUG_POINTS);
  for (let p = 1; p <= RING; p++) {
    const angle = ((p + 2) * 256) / RING;
    const lump = (k * (p + 2) * 2) & 255;
    const r = Math.trunc((radius * 256) / (Math.abs(cos256(lump)) + Math.abs(sin256(lump))));
    xs[p] = Math.trunc((r * cos256(angle)) / 256);
    ys[p] = Math.trunc((r * sin256(angle)) / 256);
  }
  return [xs, ys];
}

// Each spring's rest length, from the outline the slug was born with
function restLengths(slug) {
  const [xs, ys] = outlinePoints(slug.k, slug.radius);
  const rest = new Int32Array(LINK_A.length);
  for (let l = 0; l < LINK_A.length; l++) {
    const dx = xs[LINK_B[l]] - xs[LINK_A[l]];
    const dy = ys[LINK_B[l]] - ys[LINK_A[l]];
    rest[l] = isqrt(dx * dx + dy * dy);
  }
  return rest;
}

// Whether every point of the outline placed at (cx, cy) (256ths) sits in an empty cell inside the world
function spotFree(w, xs, ys, cx, cy) {
  for (let p = 0; p < SLUG_POINTS; p++) {
    const x = (cx + xs[p]) >> 8;
    const y = (cy + ys[p]) >> 8;
    if (x < 1 || x > W - 2 || y < 1 || y > H - 2 || w.el[y * W + x] !== 0) {
      return false;
    }
  }
  return true;
}

// A random spot (256ths) far enough from the edges for a slug of this ring radius at full size
function pickSpot(w, xs, ys, radius, d) {
  const margin = Math.min(Math.trunc((H - 2) / 2), ((radius * 2) >> 8) + 2);
  let cx = 0;
  let cy = 0;
  for (let t = 0; t < SPOT_TRIES; t++) {
    cx = (margin + d.roll(W - 2 * margin)) * ONE + (ONE >> 1);
    cy = (margin + d.roll(H - 2 * margin)) * ONE + (ONE >> 1);
    if (spotFree(w, xs, ys, cx, cy)) {
      break;
    }
  }
  return [cx, cy];
}

// A new slug. `spot` is its centre in 256ths of a cell, or null for a random free spot.
function makeSlug(w, d, radius, deaths, spot = null) {
  const k = d.roll(256);
  const [xs, ys] = outlinePoints(k, radius);
  const [cx, cy] = spot ?? pickSpot(w, xs, ys, radius, d);
  const slug = {
    k,
    right: 1,
    wall: 0,
    scale: START_SCALE,
    power: POWER_REST,
    deaths,
    radius,
    x: new Int32Array(SLUG_POINTS),
    y: new Int32Array(SLUG_POINTS),
    lx: new Int32Array(SLUG_POINTS),
    ly: new Int32Array(SLUG_POINTS),
    rest: null,
  };
  for (let p = 0; p < SLUG_POINTS; p++) {
    slug.x[p] = slug.lx[p] = cx + xs[p];
    slug.y[p] = slug.ly[p] = cy + ys[p];
  }
  slug.rest = restLengths(slug);
  return slug;
}

/** A fresh slug at a random spot, as the world's slug */
export function newSlug(w, d) {
  w.slug = makeSlug(w, d, START_RADIUS, 0);
  return w.slug;
}

/** A new slug centred on the cell (x, y), its shape picked by `d`. For scenes made by code, like the starter. */
export function placeSlug(w, d, x, y) {
  w.slug = makeSlug(w, d, START_RADIUS, 0, [x * ONE + (ONE >> 1), y * ONE + (ONE >> 1)]);
  return w.slug;
}

// The cells under the outline: a line from each ring point to the next, each cell once, in a fixed order
function outlineCells(slug) {
  const cells = new Set();
  for (let p = 1; p <= RING; p++) {
    const q = p === RING ? 1 : p + 1;
    lineCells(slug.x[p] >> 8, slug.y[p] >> 8, slug.x[q] >> 8, slug.y[q] >> 8, cells);
  }
  return cells;
}

function lineCells(x0, y0, x1, y1, cells) {
  const dx = Math.abs(x1 - x0);
  const dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  let x = x0;
  let y = y0;
  for (;;) {
    if (x >= 1 && x <= W - 2 && y >= 1 && y <= H - 2) {
      cells.add(y * W + x);
    }
    if (x === x1 && y === y1) {
      return;
    }
    const e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y += sy;
    }
  }
}

// Turns to roll toward column x (or away from it). Touching the top of the world holds its direction.
function turn(slug, x, toward) {
  if (slug.wall & WALL_TOP) {
    return;
  }
  const left = slug.x[0] >> 8 < x ? 1 : 0;
  slug.right = toward ? left : 1 - left;
}

// Water, salt or salt water above or beside an outline cell is eaten, one cell per outline cell, as in the original
// (where each of those elements checked the cells below and beside it for the slug)
function eatBeside(w, slug, c, d) {
  for (const j of [c - W, c + 1, c - 1]) {
    const id = w.el[j];
    if (id !== EL.water && id !== EL.salt && id !== EL.saltWater) {
      continue;
    }
    put(w, j, 0, d);
    const water = id === EL.water;
    slug.scale += water ? WATER_SCALE : SALT_SCALE;
    slug.power += water ? WATER_POWER : SALT_POWER;
    turn(slug, j % W, id !== EL.salt);
    return;
  }
}

function fireBeside(w, c) {
  const el = w.el;
  return el[c - 1] === EL.fire || el[c + 1] === EL.fire || el[c - W] === EL.fire || el[c + W] === EL.fire;
}

// The outline's empty cells catch fire from fire beside them (the cell above goes up too), or eat what touches them
function feed(w, slug, d) {
  for (const c of outlineCells(slug)) {
    if (w.el[c] !== 0) {
      continue;
    }
    if (fireBeside(w, c) && d.chance(FIRE_CATCH)) {
      put(w, c, EL.fire, d);
      if (w.el[c - W] === 0) {
        put(w, c - W, EL.fire, d);
      }
      slug.scale -= BURN_SCALE;
      continue;
    }
    eatBeside(w, slug, c, d);
  }
}

// Point p eases toward point q by f 1024ths of the way
function ease(slug, p, q, f) {
  slug.x[p] += Math.trunc(((slug.x[q] - slug.x[p]) * f) / 1024);
  slug.y[p] += Math.trunc(((slug.y[q] - slug.y[p]) * f) / 1024);
}

// The ring turns like a wheel: each point eases toward its neighbour, clockwise to roll right
function roll(slug) {
  const f = Math.trunc((slug.power * 1024) / 50000);
  if (slug.right) {
    ease(slug, RING, 1, f);
    for (let p = 1; p < RING; p++) {
      ease(slug, p, p + 1, f);
    }
  } else {
    ease(slug, 1, RING, f);
    for (let p = RING; p > 1; p--) {
      ease(slug, p, p - 1, f);
    }
  }
}

// Every spring pulls or pushes its two points, half each, toward its rest length times scale
function springs(slug) {
  const { x, y, rest, scale } = slug;
  for (let l = 0; l < LINK_A.length; l++) {
    const a = LINK_A[l];
    const b = LINK_B[l];
    const dx = x[b] - x[a];
    const dy = y[b] - y[a];
    const length = isqrt(dx * dx + dy * dy);
    if (length === 0) {
      continue;
    }
    const diff = Math.trunc((rest[l] * scale) / 1000) - length;
    const mx = Math.trunc((dx * diff) / (2 * length));
    const my = Math.trunc((dy * diff) / (2 * length));
    x[a] -= mx;
    y[a] -= my;
    x[b] += mx;
    y[b] += my;
  }
}

// Holds point p inside the world. Returns the wall bit it touched, or 0 when it is inside.
function edge(slug, p) {
  const { x, y, lx, ly } = slug;
  if (x[p] < ONE) {
    x[p] = ONE;
    y[p] = ly[p] + Math.trunc(((y[p] - ly[p]) * EDGE_SLIDE) / 1024);
    return WALL_LEFT;
  }
  if (x[p] >= (W - 1) * ONE) {
    x[p] = (W - 1) * ONE - 1;
    y[p] = ly[p] + Math.trunc(((y[p] - ly[p]) * EDGE_SLIDE) / 1024);
    return WALL_RIGHT;
  }
  if (y[p] < 0) {
    y[p] = 0;
    x[p] = lx[p] + Math.trunc(((x[p] - lx[p]) * EDGE_SLIDE) / 1024);
    return WALL_TOP;
  }
  if (y[p] >= (H - 1) * ONE) {
    y[p] = (H - 1) * ONE - 1;
    x[p] = lx[p] + Math.trunc(((x[p] - lx[p]) * FLOOR_SLIDE) / 1024);
    return WALL_BOTTOM;
  }
  return 0;
}

// A point that ends up in a filled cell goes back to where it was
function collide(w, slug) {
  const { x, y, lx, ly } = slug;
  slug.wall = 0;
  for (let p = 0; p < SLUG_POINTS; p++) {
    const hit = edge(slug, p);
    if (hit !== 0) {
      slug.wall |= hit;
    } else if (w.el[(y[p] >> 8) * W + (x[p] >> 8)] !== 0) {
      x[p] = lx[p];
      y[p] = ly[p];
    }
  }
}

// Verlet: each point keeps 0.95 of its last move
function coast(slug) {
  const { x, y, lx, ly } = slug;
  for (let p = 0; p < SLUG_POINTS; p++) {
    const vx = Math.trunc(((x[p] - lx[p]) * DAMP) / 1024);
    const vy = Math.trunc(((y[p] - ly[p]) * DAMP) / 1024);
    lx[p] = x[p];
    ly[p] = y[p];
    x[p] += vx;
    y[p] += vy;
  }
}

function move(w, slug) {
  for (let p = 0; p < SLUG_POINTS; p++) {
    slug.y[p] += GRAVITY;
  }
  if (slug.scale < SCALE_LOW) {
    slug.scale = SCALE_RESET;
  }
  // Power drifts back down to its resting value, a 10000th a step
  if (slug.power > POWER_REST) {
    slug.power -= 1;
  }
  slug.power = Math.min(POWER_MAX, Math.max(0, slug.power));
  roll(slug);
  springs(slug);
  springs(slug);
  collide(w, slug);
  coast(slug);
}

// Too small: it bursts into pale drops and a new one is born somewhere, its ring as small as the old one's last size
function checkBurst(w, slug, d) {
  const size = slug.scale * (1000 + slug.deaths);
  if (size >= BURST_BELOW) {
    return;
  }
  for (let n = 0; n < BURST_PARTS; n++) {
    spawnBurst(w, slug.x[0], slug.y[0], d);
  }
  w.slug = makeSlug(w, d, Math.trunc((size * ONE) / 300000), slug.deaths + 1);
}

/** One step of the slug, after the scan: it eats and burns, moves (unless stopped), and bursts when too small */
export function stepSlug(w, d) {
  const mode = w.settings.slug;
  if (mode === GONE) {
    return;
  }
  if (w.slug === null) {
    newSlug(w, d);
  }
  const slug = w.slug;
  if (slug.rest === null) {
    slug.rest = restLengths(slug);
  }
  feed(w, slug, d);
  if (mode === MOVE) {
    move(w, slug);
  }
  checkBurst(w, slug, d);
}
