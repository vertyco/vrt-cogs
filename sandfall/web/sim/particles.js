// The particle engine. A particle is a small moving shape (a line or a circle) that stamps real cells into the grid
// once a step, before the scan; the normal rules take over from there. Particles live in one fixed pool of whole
// numbers on the world, so every screen in a shared world moves them the same way and a snapshot saves them.
import { Dice, mix } from "./dice.js";
import { EL, ELEMENTS } from "./elements.js";
import { put } from "./helpers.js";
import { electrify, EXPLOSIVES } from "./rules/electric.js";
import { ignite } from "./rules/fire.js";
import { cos256, cos4096, sin256, sin4096 } from "./trig.js";
import { H, PART_FIELDS, PART_MAX, W } from "./world.js";

// Particle type numbers are saved with the world: never renumber them
export const PART = Object.freeze({
  STREAK: 1,
  FIREBALL: 2,
  NAPALM: 3,
  BIG_FIREBALL: 4,
  LAVA_ARC: 5,
  BEAM: 6,
  TREE: 7,
  STAR: 8,
  SPIRAL: 9,
  NUKE: 10,
  BOLT: 11,
  BURST: 12,
});

// Field offsets inside one record. Positions and speeds are in 256ths of a cell.
const TYPE = 0;
const X = 1;
const Y = 2;
const VX = 3;
const VY = 4;
const SIZE = 5;
const AGE = 6;
const LIFE = 7;
const A = 8;
const B = 9;

const ONE = 256;
// No fireball is wider than this many cells, however big the clump that lit it
const MAX_DIAMETER = 120;
// A clump is counted at most this far along each line through the trigger
const CLUMP_REACH = 32;
// Lava arcs fall this many 256ths of a cell per step faster each step
const LAVA_GRAVITY = 15;
// A tree branch's heading stays between these two angles (256ths of a turn, 0 right, 64 straight up, 128 left)
const TREE_FLATTEST = 10;
const TREE_STEEPEST = 118;
// How the A field of a tree record packs: splits left in the low 4 bits, then the three-way flag, then the blossom
const TREE_SPLITS_MASK = 15;
const TREE_THREE_WAY = 16;
const TREE_BLOSSOM_SHIFT = 5;
// Mystery's shows paint with one of these, a spoke or a whole spiral at a time
const SHOW_ELEMENTS = [EL.wall, EL.plant, EL.spout, EL.well, EL.wax, EL.ice];
// A spiral's tip moves this many cells a step, and ends once it is past the world's far corners
const SPIRAL_ARC = 12;
const SPIRAL_END = 200 * ONE;
// Divided by the radius (in 256ths of a cell) this is how many 4096ths of a turn move the tip SPIRAL_ARC cells:
// arc * 4096 * 256 / (2 pi), with 2 pi taken as 804 / 128
const SPIRAL_TURN = Math.trunc((SPIRAL_ARC * 4096 * ONE * 128) / 804);
const SPIRAL_CENTER_X = W >> 1;
const SPIRAL_CENTER_Y = H >> 1;
// A bolt strikes for this many steps. Its path is redrawn from a seed every step, so the record needs no list of cells.
const BOLT_STEPS = 3;
// How far from the target's column a bolt may start at the top, and how far a row of it may wander off the straight line
const BOLT_START_REACH = 20;
const BOLT_WANDER = 8;
// What a bolt does to a cell it passes: sand fuses to glass (kept below glass's own melting point), the rest heat up
const BOLT_HEAT = 3000;
const FUSED_HEAT = 1200;
// True from the moment a star or spiral exists until the step after the last one ends
let showOn = false;

/** Empties the pool */
export function clearParticles(w) {
  w.parts.n = 0;
  showOn = false;
}

/** Whether a Mystery star or spiral is on the go: the rest of the Mystery vanishes while one runs */
export function showRunning() {
  return showOn;
}

// A slug's burst drops fall this many 256ths of a cell per step faster each step, and fly out at most BURST_SPEED
const BURST_GRAVITY = 26;
const BURST_SPEED = 427;
// A drop is 1 to 10 of the original's pixels across, a third of a cell each, kept in 256ths of a cell
const BURST_SIZE_MIN = 85;
const BURST_SIZE_SPAN = 769;

// Takes a free record and fills its first fields. Returns the record's start, or -1 when the pool is full.
function claim(w, type, x, y) {
  const parts = w.parts;
  if (parts.n >= PART_MAX) {
    return -1;
  }
  const at = parts.n * PART_FIELDS;
  parts.n += 1;
  const rec = parts.rec;
  rec.fill(0, at, at + PART_FIELDS);
  rec[at + TYPE] = type;
  rec[at + X] = x * ONE + (ONE >> 1);
  rec[at + Y] = y * ONE + (ONE >> 1);
  return at;
}

/** A spark streak launched from (x, y) in a random direction: nitro going off */
export function spawnStreak(w, x, y, d) {
  const at = claim(w, PART.STREAK, x, y);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  const angle = d.roll(256);
  rec[at + VX] = 5 * cos256(angle);
  rec[at + VY] = 5 * sin256(angle);
  rec[at + SIZE] = 1 + d.roll(5);
  return true;
}

/** One drop of a burst slug at (x, y) in 256ths of a cell, flying off in a random direction. Drawn only, never
 * stamped: it touches no cell. */
export function spawnBurst(w, x, y, d) {
  const at = claim(w, PART.BURST, 0, 0);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  rec[at + X] = x;
  rec[at + Y] = y;
  rec[at + VX] = d.roll(2 * BURST_SPEED + 1) - BURST_SPEED;
  rec[at + VY] = d.roll(2 * BURST_SPEED + 1) - BURST_SPEED;
  rec[at + SIZE] = BURST_SIZE_MIN + d.roll(BURST_SIZE_SPAN);
  return true;
}

// How many cells in a row hold id along one line through i, both ways, up to CLUMP_REACH each way
function run(w, i, id, step) {
  let n = 1;
  for (const dir of [step, -step]) {
    let j = i + dir;
    for (let k = 0; k < CLUMP_REACH && j >= 0 && j < w.el.length && w.el[j] === id; k++) {
      n += 1;
      j += dir;
    }
  }
  return n;
}

// The thinner side of the clump of the trigger's element, counted left and right and up and down, as Pyro Sand does
function clump(w, x, y) {
  const i = y * W + x;
  const id = w.el[i];
  return Math.min(run(w, i, id, 1), run(w, i, id, W));
}

// clump x a random factor from low to high (in 256ths), capped
function blastDiameter(w, x, y, d, low, high) {
  const factor = low + d.roll(high - low + 1);
  return Math.min(MAX_DIAMETER, Math.max(1, (clump(w, x, y) * factor) >> 8));
}

/** A fireball at (x, y). kind is "napalm" (drifts up and sideways) or "methane" (stays put). */
export function spawnFireball(w, x, y, kind, d) {
  const napalm = kind === "napalm";
  const at = claim(w, napalm ? PART.NAPALM : PART.FIREBALL, x, y);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  rec[at + SIZE] = blastDiameter(w, x, y, d, 4 * ONE, 8 * ONE);
  if (napalm) {
    rec[at + VX] = d.roll(2 * ONE + 1) - ONE;
    rec[at + VY] = -(ONE + d.roll(ONE + 1));
  }
  return true;
}

/** C-4's blast at (x, y): as a fireball but 4 to 16 times the clump, and 1 time in 50 a huge one */
export function spawnBigFireball(w, x, y, d) {
  const at = claim(w, PART.BIG_FIREBALL, x, y);
  if (at < 0) {
    return false;
  }
  const huge = d.chance(200);
  w.parts.rec[at + SIZE] = huge ? 2 * (30 + d.roll(31)) : blastDiameter(w, x, y, d, 4 * ONE, 16 * ONE);
  return true;
}

/** A lava arc thrown upward from (x, y), 45 to 135 degrees, speed 3 to 7: lava next to oil */
export function spawnLavaArc(w, x, y, d) {
  const size = 4 + d.roll(4);
  const at = claim(w, PART.LAVA_ARC, x, Math.max(0, y - size));
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  const angle = 32 + d.roll(65);
  const speed = 3 * ONE + d.roll(4 * ONE + 1);
  rec[at + VX] = Math.trunc((speed * cos256(angle)) / ONE);
  rec[at + VY] = -Math.trunc((speed * sin256(angle)) / ONE);
  rec[at + SIZE] = size;
  return true;
}

/** A one-step beam 4 cells wide straight up from (x, y) to the first wall: charged nitro going off */
export function spawnBeam(w, x, y, d) {
  const at = claim(w, PART.BEAM, x, y);
  if (at < 0) {
    return false;
  }
  w.parts.rec[at + SIZE] = 4;
  w.parts.rec[at + LIFE] = 1;
  return true;
}

// Points a record along an angle (256ths of a turn, 0 right, 64 up) at 1 to 1.5 cells a step
function aim(rec, at, angle, d) {
  const speed = ONE + d.roll((ONE >> 1) + 1);
  rec[at + VX] = (speed * cos256(angle)) >> 8;
  rec[at + VY] = -((speed * sin256(angle)) >> 8);
  rec[at + B] = (rec[at + B] & ~255) | angle;
}

// A growth span in steps for a branch whose parent's span was base: 0.8 to 1.2 times it, never under 4
function span(base, d) {
  return Math.max(4, Math.trunc((base * (8 + d.roll(5))) / 10));
}

/**
 * A tree whose trunk starts in the empty cell (x, y) and grows up: 3 to 4 cells thick, splitting after 15 to 60 steps
 * into thinner branches 1 to 3 times, the last ones leaf. 2 trees in 5 blossom. Returns false when the pool is full.
 */
export function spawnTree(w, x, y, d) {
  const at = claim(w, PART.TREE, x, y);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  const life = 15 + d.roll(46);
  const blossom = [0, 0, 0, 1, 2][d.roll(5)];
  const threeWay = d.chance(1900) ? TREE_THREE_WAY : 0;
  rec[at + SIZE] = 3 + d.roll(2);
  rec[at + LIFE] = life;
  rec[at + A] = 1 + d.roll(3) + threeWay + (blossom << TREE_BLOSSOM_SHIFT);
  rec[at + B] = life << 8;
  aim(rec, at, 48 + d.roll(33), d);
  return true;
}

// Starts one child branch where the parent ended, heading angle, its span a share of base. False when the pool is full.
function growBranch(w, parent, angle, base, d) {
  const at = claim(w, PART.TREE, 0, 0);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  rec[at + X] = rec[parent + X];
  rec[at + Y] = rec[parent + Y];
  rec[at + SIZE] = Math.max(2, rec[parent + SIZE] - 1);
  rec[at + LIFE] = span(base, d);
  rec[at + A] = rec[parent + A] - 1;
  rec[at + B] = base << 8;
  aim(rec, at, Math.min(TREE_STEEPEST, Math.max(TREE_FLATTEST, angle)), d);
  return true;
}

// The end of a branch that still has splits left: 2 branches turned out to either side, or for a three-way tree 3
// branches close together. Each generation's span is 0.9 (or 0.6 for a three-way tree) of the last.
function split(w, at, d) {
  const rec = w.parts.rec;
  const angle = rec[at + B] & 255;
  const threeWay = (rec[at + A] & TREE_THREE_WAY) !== 0;
  const base = Math.max(6, Math.trunc(((rec[at + B] >> 8) * (threeWay ? 6 : 9)) / 10));
  if (threeWay) {
    const turn = 16 + d.roll(9);
    for (const delta of [-turn, 0, turn]) {
      growBranch(w, at, angle + delta, base, d);
    }
    return;
  }
  growBranch(w, at, angle + 16 + d.roll(33), base, d);
  growBranch(w, at, angle - 16 - d.roll(33), base, d);
}

/** A star of 5 to 18 spokes flying out from (x, y), each painting one of Mystery's elements. All or nothing. */
export function spawnStar(w, x, y, d) {
  const spokes = 5 + d.roll(14);
  if (PART_MAX - w.parts.n < spokes) {
    return false;
  }
  const turn = d.roll(256);
  for (let k = 0; k < spokes; k++) {
    const at = claim(w, PART.STAR, x, y);
    const rec = w.parts.rec;
    const angle = turn + Math.trunc((256 * k) / spokes);
    const speed = 4 * ONE + d.roll(2 * ONE + 1);
    rec[at + VX] = (speed * cos256(angle)) >> 8;
    rec[at + VY] = -((speed * sin256(angle)) >> 8);
    rec[at + SIZE] = 2 + d.roll(4);
    rec[at + A] = SHOW_ELEMENTS[d.roll(SHOW_ELEMENTS.length)];
  }
  showOn = true;
  return true;
}

/** A spiral winding out from the middle of the world, 2 to 7 cells wide, rings 15 to 48 cells apart */
export function spawnSpiral(w, d) {
  const at = claim(w, PART.SPIRAL, SPIRAL_CENTER_X, SPIRAL_CENTER_Y);
  if (at < 0) {
    return false;
  }
  const rec = w.parts.rec;
  rec[at + SIZE] = 2 + d.roll(6);
  rec[at + VX] = 15 + d.roll(34);
  rec[at + A] = SHOW_ELEMENTS[d.roll(SHOW_ELEMENTS.length)];
  rec[at + B] = d.roll(4096);
  showOn = true;
  return true;
}

/** A fireball a quarter to three eighths of the world wide at (x, y), held for 4 steps */
export function spawnNuke(w, x, y, d) {
  const at = claim(w, PART.NUKE, x, y);
  if (at < 0) {
    return false;
  }
  w.parts.rec[at + SIZE] = (W >> 2) + d.roll((W >> 3) + 1);
  w.parts.rec[at + LIFE] = 4;
  return true;
}

/** A lightning bolt from the top of the world down to the cell (x, y), striking for 3 steps */
export function spawnBolt(w, x, y, d) {
  const at = claim(w, PART.BOLT, x, Math.max(1, y));
  if (at < 0) {
    return false;
  }
  w.parts.rec[at + LIFE] = BOLT_STEPS;
  w.parts.rec[at + B] = mix(d.next(), x, y);
  return true;
}

// How a stamp treats the grid. keep spares walls; life is written into each new cell (a leaf's blossom colour).
const PLAIN = Object.freeze({ keep: false, life: 0 });
const SPARE_WALLS = Object.freeze({ keep: true, life: 0 });
const BLOSSOMS = [SPARE_WALLS, Object.freeze({ keep: true, life: 1 }), Object.freeze({ keep: true, life: 2 })];

// Writes id into cell (x, y) unless it already holds it. Particles never touch the edge rows and columns.
function stampCell(w, x, y, id, d, style) {
  if (x < 1 || x > W - 2 || y < 1 || y > H - 2) {
    return;
  }
  const i = y * W + x;
  if (w.el[i] === id || (style.keep && w.el[i] === EL.wall)) {
    return;
  }
  put(w, i, id, d);
  if (style.life !== 0) {
    w.life[i] = style.life;
  }
}

// A filled circle: the cells where (2dx)^2 + (2dy)^2 <= diameter^2, the same shape as a round brush
function stampDisc(w, cx, cy, diameter, id, d, style = PLAIN) {
  const reach = (diameter + 1) >> 1;
  const limit = diameter * diameter;
  const y0 = Math.max(1, cy - reach);
  const y1 = Math.min(H - 2, cy + reach);
  const x0 = Math.max(1, cx - reach);
  const x1 = Math.min(W - 2, cx + reach);
  for (let y = y0; y <= y1; y++) {
    const dy = 2 * (y - cy);
    for (let x = x0; x <= x1; x++) {
      const dx = 2 * (x - cx);
      if (dx * dx + dy * dy <= limit) {
        stampCell(w, x, y, id, d, style);
      }
    }
  }
}

// The cells of a straight line from (x0, y0) to (x1, y1), both ends included, handed one by one to fn(x, y).
// Stops early and returns true when fn returns true.
function eachOnLine(x0, y0, x1, y1, fn) {
  const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
  for (let k = 0; k <= steps; k++) {
    const x = steps === 0 ? x0 : x0 + Math.trunc(((x1 - x0) * k) / steps);
    const y = steps === 0 ? y0 : y0 + Math.trunc(((y1 - y0) * k) / steps);
    if (fn(x, y)) {
      return true;
    }
  }
  return false;
}

// A thick line: a disc of the given diameter at every cell along it. Skipped while it is wholly outside the world.
function stampLine(w, x0, y0, x1, y1, diameter, id, d, style = PLAIN) {
  const reach = diameter + 1;
  if (Math.max(y0, y1) < -reach || Math.min(y0, y1) > H + reach) {
    return;
  }
  if (Math.max(x0, x1) < -reach || Math.min(x0, x1) > W + reach) {
    return;
  }
  eachOnLine(x0, y0, x1, y1, (x, y) => {
    stampDisc(w, x, y, diameter, id, d, style);
    return false;
  });
}

// Moves a record by its speed; returns its old cell as [x, y]
function move(rec, at) {
  const ox = rec[at + X] >> 8;
  const oy = rec[at + Y] >> 8;
  rec[at + X] += rec[at + VX];
  rec[at + Y] += rec[at + VY];
  return [ox, oy];
}

// A spark streak: a line from where it was to where it is, pulled down harder every 15 steps. Gone below the world.
function streak(w, rec, at, age, d) {
  const [ox, oy] = move(rec, at);
  stampLine(w, ox, oy, rec[at + X] >> 8, rec[at + Y] >> 8, rec[at + SIZE], EL.fire, d);
  if (age % 15 === 0) {
    rec[at + VY] += (3 * ONE * Math.trunc(age / 15)) >> 1;
  }
  return rec[at + Y] < H * ONE;
}

// A fireball: a circle of fire halved every 5 steps. The napalm kind also drifts.
function fireball(w, rec, at, age, d) {
  if (rec[at + TYPE] === PART.NAPALM) {
    move(rec, at);
  }
  stampDisc(w, rec[at + X] >> 8, rec[at + Y] >> 8, rec[at + SIZE], EL.fire, d);
  if (age % 5 === 0) {
    rec[at + SIZE] >>= 1;
  }
  return rec[at + SIZE] > 0;
}

// What a lava arc's tip makes of the cell it meets: [element, chance of 10,000], or null to fly on through it
function landing(id) {
  if (id === EL.water || id === EL.saltWater) {
    return [EL.stone, 5800];
  }
  if (id === EL.ice || id === EL.chilledIce || id === EL.cryo) {
    return [EL.stone, 7000];
  }
  if (id === EL.lava || id === EL.stone) {
    return [EL.lava, 7500];
  }
  if (id === EL.wall) {
    return [EL.lava, 2500];
  }
  const kind = ELEMENTS[id].kind;
  return kind === "powder" || kind === "solid" ? [EL.lava, 5000] : null;
}

// Looks along the arc's path for something it lands on; on a landing it leaves a dot there and returns true
function land(w, ox, oy, nx, ny, size, d) {
  return eachOnLine(ox, oy, nx, ny, (x, y) => {
    if (x < 1 || x > W - 2 || y < 1 || y > H - 2) {
      return false;
    }
    const hit = landing(w.el[y * W + x]);
    if (hit === null || !d.chance(hit[1])) {
      return false;
    }
    stampDisc(w, x, y, size, hit[0], d);
    return true;
  });
}

// A lava arc: a thick trail of fire along a falling curve, until it lands or leaves the sides or bottom
function lavaArc(w, rec, at, d) {
  const [ox, oy] = move(rec, at);
  rec[at + VY] += LAVA_GRAVITY;
  const nx = rec[at + X] >> 8;
  const ny = rec[at + Y] >> 8;
  if (land(w, ox, oy, nx, ny, rec[at + SIZE], d)) {
    return false;
  }
  stampLine(w, ox, oy, nx, ny, rec[at + SIZE], EL.fire, d);
  return nx >= 0 && nx < W && ny < H;
}

// A beam: fire 4 cells wide from the cell above it up to the first wall in its column, for one step
function beam(w, rec, at, d) {
  const x = rec[at + X] >> 8;
  const half = rec[at + SIZE] >> 1;
  for (let y = (rec[at + Y] >> 8) - 1; y >= 1 && w.el[y * W + x] !== EL.wall; y--) {
    for (let bx = x - half + 1; bx <= x + half; bx++) {
      stampCell(w, bx, y, EL.fire, d, PLAIN);
    }
  }
  rec[at + LIFE] -= 1;
  return rec[at + LIFE] > 0;
}

// A tree branch: grows a line of branch (leaf on the last generation) and stops at a wall or the top of the world.
// When its span runs out it splits, or just ends.
function tree(w, rec, at, d) {
  const [ox, oy] = move(rec, at);
  const nx = rec[at + X] >> 8;
  const ny = rec[at + Y] >> 8;
  if (nx < 1 || nx > W - 2 || ny < 1 || w.el[ny * W + nx] === EL.wall) {
    return false;
  }
  const flags = rec[at + A];
  const last = (flags & TREE_SPLITS_MASK) === 0;
  const style = last ? BLOSSOMS[flags >> TREE_BLOSSOM_SHIFT] : SPARE_WALLS;
  stampLine(w, ox, oy, nx, ny, rec[at + SIZE], last ? EL.leaf : EL.branch, d, style);
  rec[at + LIFE] -= 1;
  if (rec[at + LIFE] > 0) {
    return true;
  }
  if (!last) {
    split(w, at, d);
  }
  return false;
}

// One spoke of a star: a thick line of its element until it leaves the world
function spoke(w, rec, at, d) {
  const [ox, oy] = move(rec, at);
  const nx = rec[at + X] >> 8;
  const ny = rec[at + Y] >> 8;
  stampLine(w, ox, oy, nx, ny, rec[at + SIZE], rec[at + A], d);
  return nx >= 0 && nx < W && ny >= 0 && ny < H;
}

// A spiral: the tip moves a fixed distance a step round the middle while the radius grows one ring spacing a turn.
// The angle (B) is in 4096ths of a turn and the radius (VY) in 256ths of a cell.
function spiral(w, rec, at, d) {
  const ox = rec[at + X] >> 8;
  const oy = rec[at + Y] >> 8;
  const radius = rec[at + VY];
  const turn = Math.trunc(SPIRAL_TURN / Math.max(radius, 6 * ONE));
  const angle = (rec[at + B] + turn) & 4095;
  const grown = radius + ((rec[at + VX] * turn) >> 4);
  rec[at + B] = angle;
  rec[at + VY] = grown;
  rec[at + X] = SPIRAL_CENTER_X * ONE + (ONE >> 1) + ((grown * cos4096(angle)) >> 8);
  rec[at + Y] = SPIRAL_CENTER_Y * ONE + (ONE >> 1) + ((grown * sin4096(angle)) >> 8);
  stampLine(w, ox, oy, rec[at + X] >> 8, rec[at + Y] >> 8, rec[at + SIZE], rec[at + A], d);
  return grown < SPIRAL_END;
}

// A nuke: the same big circle of fire for a few steps
function nuke(w, rec, at, d) {
  stampDisc(w, rec[at + X] >> 8, rec[at + Y] >> 8, rec[at + SIZE], EL.fire, d);
  rec[at + LIFE] -= 1;
  return rec[at + LIFE] > 0;
}

// What a bolt does to the cell (x, y) it passes through
function strike(w, x, y, d) {
  if (x < 1 || x > W - 2 || y < 1 || y > H - 2) {
    return;
  }
  const i = y * W + x;
  const id = w.el[i];
  if (id === EL.metal) {
    if (electrify(w, i, false)) {
      w.events.zap += 1;
    }
  } else if (id === EL.sand || id === EL.coloredSand) {
    put(w, i, EL.glass, d);
    w.heat[i] = FUSED_HEAT;
  } else if (id === 0) {
    put(w, i, EL.fire, d);
  } else if (EXPLOSIVES.has(id)) {
    w.heat[i] = BOLT_HEAT;
  } else if (ELEMENTS[id].burns) {
    ignite(w, i, d);
  } else if (id !== EL.wall && id !== EL.glass) {
    w.heat[i] = BOLT_HEAT;
  }
}

// A bolt: a jagged line 2 cells wide (so the fire it leaves reads as one stroke) down from near the target's column
// at the top, straightening as it nears the target
function bolt(w, rec, at, age, d) {
  const tx = rec[at + X] >> 8;
  const ty = rec[at + Y] >> 8;
  const path = new Dice(rec[at + B]);
  const startX = Math.min(W - 3, Math.max(2, tx + path.roll(2 * BOLT_START_REACH + 1) - BOLT_START_REACH));
  let wander = 0;
  let px = startX;
  let py = 1;
  for (let y = 1; y <= ty; y++) {
    wander = Math.min(BOLT_WANDER, Math.max(-BOLT_WANDER, wander + path.roll(5) - 2));
    const straight = startX + Math.trunc(((tx - startX) * y) / ty);
    const x = Math.min(W - 2, Math.max(1, straight + Math.trunc((wander * (ty - y)) / ty)));
    eachOnLine(px, py, x, y, (cx, cy) => {
      strike(w, cx, cy, d);
      strike(w, cx + 1, cy, d);
      return false;
    });
    px = x;
    py = y;
  }
  if (age === 1) {
    w.events.bolt += 1;
  }
  rec[at + LIFE] -= 1;
  return rec[at + LIFE] > 0;
}

// A slug's burst drop falls under gravity until it is below the world
function burst(rec, at) {
  move(rec, at);
  rec[at + VY] += BURST_GRAVITY;
  return rec[at + Y] < H * ONE;
}

// What each particle type does in one step, as fn(w, rec, at, age, d) returning whether it lives on
const ACTS = new Map([
  [PART.STREAK, streak],
  [PART.FIREBALL, fireball],
  [PART.NAPALM, fireball],
  [PART.BIG_FIREBALL, fireball],
  [PART.LAVA_ARC, (w, rec, at, age, d) => lavaArc(w, rec, at, d)],
  [PART.BEAM, (w, rec, at, age, d) => beam(w, rec, at, d)],
  [PART.TREE, (w, rec, at, age, d) => tree(w, rec, at, d)],
  [PART.STAR, (w, rec, at, age, d) => spoke(w, rec, at, d)],
  [PART.SPIRAL, (w, rec, at, age, d) => spiral(w, rec, at, d)],
  [PART.NUKE, (w, rec, at, age, d) => nuke(w, rec, at, d)],
  [PART.BOLT, bolt],
  [PART.BURST, (w, rec, at) => burst(rec, at)],
]);

// Runs one particle for one step; returns whether it lives on
function act(w, rec, at, d) {
  const age = rec[at + AGE] + 1;
  rec[at + AGE] = age;
  const fn = ACTS.get(rec[at + TYPE]);
  return fn === undefined ? false : fn(w, rec, at, age, d);
}

/** Every live particle stamps its cells and moves, oldest first; the spent ones leave and the rest keep their order */
export function stampParticles(w, d) {
  const parts = w.parts;
  const rec = parts.rec;
  showOn = false;
  for (let k = 0; k < parts.n; k++) {
    const type = rec[k * PART_FIELDS + TYPE];
    showOn = showOn || type === PART.STAR || type === PART.SPIRAL;
  }
  let kept = 0;
  for (let k = 0; k < parts.n; k++) {
    const at = k * PART_FIELDS;
    if (!act(w, rec, at, d)) {
      continue;
    }
    if (kept !== k) {
      rec.copyWithin(kept * PART_FIELDS, at, at + PART_FIELDS);
    }
    kept += 1;
  }
  parts.n = kept;
}
