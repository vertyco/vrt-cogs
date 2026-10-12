// Strokes: what players do to the world, applied between steps. A stroke is an array of whole numbers whose first item
// is its kind. Every screen applies the same strokes at the same step with the same dice, so they agree cell for cell.
import { Dice, mix } from "./dice.js";
import { EL, ELEMENT_COUNT, ELEMENTS } from "./elements.js";
import { paintCell, swap } from "./helpers.js";
import { clearParticles, spawnBolt } from "./particles.js";
import { electrify } from "./rules/electric.js";
import { resetToStarter } from "./starter.js";
import { H, HEAT_MAX, HEAT_MIN, N, ROOM, W } from "./world.js";
import { handStroke } from "./zombies.js";

export const STROKE = Object.freeze({
  PAINT: 1,
  LINE: 2,
  BOX: 3,
  FILL: 4,
  HEAT: 5,
  SHOVE: 6,
  HAND: 7,
  BOLT: 8,
  SET: 9,
  CLEAR: 10,
  RESET: 11,
});

export const SHAPE = Object.freeze({ ROUND: 0, SQUARE: 1, SPRAY: 2 });
const ONLY_EMPTY = 1;
const MIRROR = 2;
const MAX_POINTS = 64;
const ZOMBIE_COUNTS = [0, 10, 20, 30];

// Scratch space shared by every stroke: a cell is marked when it holds the current generation, and the stack serves
// flood fills. Neither outlives one call, so neither is world state.
const mark = new Uint32Array(N);
const stack = new Int32Array(N);
let generation = 0;

function nextGeneration() {
  generation = (generation + 1) >>> 0;
  if (generation === 0) {
    mark.fill(0);
    generation = 1;
  }
  return generation;
}

// Strokes arrive over the network, so every number is forced into range rather than trusted
function whole(value, low, high) {
  const n = typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0;
  return n < low ? low : n > high ? high : n;
}

// An element id, or -1 when the value isn't one (the stroke is then ignored rather than painting something else)
function elementOf(value) {
  return Number.isInteger(value) && value >= 0 && value < ELEMENT_COUNT ? value : -1;
}

function readPoints(stroke, from) {
  const points = [];
  for (let k = from; k + 1 < stroke.length && points.length < MAX_POINTS; k += 2) {
    points.push([whole(stroke[k], 0, W - 1), whole(stroke[k + 1], 0, H - 1)]);
  }
  return points;
}

// LINE uses only its two end points, the other path kinds every point
function readPath(stroke) {
  const points = readPoints(stroke, 6);
  return stroke[0] === STROKE.LINE ? points.slice(0, 2) : points;
}

// Calls visit(x, y) for every in-world cell of one stamp centred on (cx, cy)
function stampCells(cx, cy, size, shape, visit) {
  const low = -(size >> 1);
  const high = shape === SHAPE.SQUARE ? (size - 1) >> 1 : size >> 1;
  const limit = size * size;
  for (let dy = low; dy <= high; dy++) {
    const y = cy + dy;
    if (y < 0 || y >= H) {
      continue;
    }
    for (let dx = low; dx <= high; dx++) {
      const x = cx + dx;
      const inside = shape === SHAPE.SQUARE || 4 * dx * dx + 4 * dy * dy <= limit;
      if (inside && x >= 0 && x < W) {
        visit(x, y);
      }
    }
  }
}

// Stamps at the first point, then every max(1, size / 2) cells along each segment of the path
function eachStamp(points, size, visit) {
  if (points.length === 0) {
    return;
  }
  const spacing = Math.max(1, size >> 1);
  visit(points[0][0], points[0][1]);
  for (let p = 1; p < points.length; p++) {
    const [ax, ay] = points[p - 1];
    const dx = points[p][0] - ax;
    const dy = points[p][1] - ay;
    const steps = Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / spacing);
    for (let k = 1; k <= steps; k++) {
      visit(ax + Math.trunc((dx * k) / steps), ay + Math.trunc((dy * k) / steps));
    }
  }
}

// Calls visit(i) for (x, y), and for its mirror image across the middle when mirroring
function withMirror(x, y, flags, visit) {
  visit(y * W + x);
  const mx = W - 1 - x;
  if (flags & MIRROR && mx !== x) {
    visit(y * W + mx);
  }
}

// Calls visit(x, y) for every stamp cell along the path, keeping 1 cell in 4 for spray
function eachPathCell(path, size, shape, d, visit) {
  eachStamp(path, size, (cx, cy) =>
    stampCells(cx, cy, size, shape, (x, y) => {
      if (shape !== SHAPE.SPRAY || d.roll(4) === 0) {
        visit(x, y);
      }
    }),
  );
}

function paintInto(w, i, element, flags, hue, d) {
  const here = w.el[i];
  if (element !== 0 && flags & ONLY_EMPTY && here !== 0) {
    return;
  }
  if (element === EL.spark && here === EL.metal) {
    // A spark painted on metal electrifies it rather than replacing it
    electrify(w, i, true);
    return;
  }
  if (here === element && element !== EL.coloredSand) {
    return;
  }
  paintCell(w, i, element, d, hue);
}

// PAINT and LINE: [kind, element, size, shape, flags, hue, x0, y0, x1, y1, ...]
function brush(w, stroke, d) {
  const element = elementOf(stroke[1]);
  if (element < 0) {
    return;
  }
  const size = whole(stroke[2], 1, 40);
  const shape = whole(stroke[3], 0, 2);
  const flags = whole(stroke[4], 0, 3);
  const hue = whole(stroke[5], 0, 255);
  const paint = (i) => paintInto(w, i, element, flags, hue, d);
  // The mirror copy follows the same spray roll, so the two sides match
  eachPathCell(readPath(stroke), size, shape, d, (x, y) => withMirror(x, y, flags, paint));
}

// Calls visit(x, y) for every cell of the rectangle between the first two points, both corners inclusive
function eachBoxCell(stroke, visit) {
  const points = readPoints(stroke, 6);
  if (points.length < 2) {
    return;
  }
  const [[ax, ay], [bx, by]] = points;
  for (let y = Math.min(ay, by); y <= Math.max(ay, by); y++) {
    for (let x = Math.min(ax, bx); x <= Math.max(ax, bx); x++) {
      visit(x, y);
    }
  }
}

// BOX: [kind, element, 0, 0, flags, hue, x0, y0, x1, y1]
function box(w, stroke, d) {
  const element = elementOf(stroke[1]);
  if (element < 0) {
    return;
  }
  const flags = whole(stroke[4], 0, 3);
  const hue = whole(stroke[5], 0, 255);
  const paint = (i) => paintInto(w, i, element, flags, hue, d);
  eachBoxCell(stroke, (x, y) => withMirror(x, y, flags, paint));
}

// Paints the 4-connected area of the element at start with element
function flood(w, start, element, hue, d) {
  const target = w.el[start];
  const gen = nextGeneration();
  let top = 0;
  stack[top++] = start;
  mark[start] = gen;
  while (top > 0) {
    const i = stack[--top];
    paintCell(w, i, element, d, hue);
    const x = i % W;
    const next = [x > 0 ? i - 1 : -1, x < W - 1 ? i + 1 : -1, i - W, i + W];
    for (const j of next) {
      if (j >= 0 && j < N && mark[j] !== gen && w.el[j] === target) {
        mark[j] = gen;
        stack[top++] = j;
      }
    }
  }
}

// FILL: [kind, element, 0, 0, flags, hue, x, y]
function fill(w, stroke, d) {
  const element = elementOf(stroke[1]);
  if (element < 0) {
    return;
  }
  const flags = whole(stroke[4], 0, 3);
  const hue = whole(stroke[5], 0, 255);
  const [point] = readPoints(stroke, 6);
  if (!point) {
    return;
  }
  withMirror(point[0], point[1], flags, (i) => {
    const here = w.el[i];
    const blocked = element !== 0 && flags & ONLY_EMPTY && here !== 0;
    if (!blocked && (here !== element || element === EL.coloredSand)) {
      flood(w, i, element, hue, d);
    }
  });
}

// HEAT: [kind, delta, size, shape, flags, 0, x0, y0, ...]. Each cell under the path changes once per step of the batch.
function heat(w, stroke, steps, d) {
  const amount = whole(stroke[1], -100, 100) * Math.max(1, steps);
  const size = whole(stroke[2], 1, 40);
  const shape = whole(stroke[3], 0, 2);
  const flags = whole(stroke[4], 0, 3);
  const gen = nextGeneration();
  const warm = (i) => {
    if (mark[i] !== gen) {
      mark[i] = gen;
      w.heat[i] = Math.min(HEAT_MAX, Math.max(HEAT_MIN, w.heat[i] + amount));
    }
  };
  eachPathCell(readPoints(stroke, 6), size, shape, d, (x, y) => withMirror(x, y, flags, warm));
}

const SHOVABLE = new Set(["powder", "liquid", "gas"]);

// The drag's direction as a step of -1, 0 or 1 on each axis: an axis counts when it is at least half the other one
function dragStep(from, to) {
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  return [Math.abs(dx) * 2 > Math.abs(dy) ? Math.sign(dx) : 0, Math.abs(dy) * 2 > Math.abs(dx) ? Math.sign(dy) : 0];
}

const isShovable = (w, i) => SHOVABLE.has(ELEMENTS[w.el[i]].kind);

// Slides the run of powders, liquids and gases that starts at cell i one cell by (sx, sy), when the run ends at an
// empty cell inside the world. A wall or the edge in the way leaves it where it is. Returns whether it moved.
function slideRun(w, i, sx, sy) {
  const run = [i];
  let x = i % W;
  let y = Math.trunc(i / W);
  for (;;) {
    x += sx;
    y += sy;
    if (x < 0 || x >= W || y < 0 || y >= H) {
      return false;
    }
    const next = y * W + x;
    if (w.el[next] === 0) {
      for (let k = run.length - 1; k >= 0; k--) {
        swap(w, run[k], k === run.length - 1 ? next : run[k + 1]);
      }
      return true;
    }
    if (!isShovable(w, next)) {
      return false;
    }
    run.push(next);
  }
}

// Pushes each powder, liquid and gas cell in the list one cell by (sx, sy), and with it the ones packed against it
// on the far side. The cells furthest along the push go first, so a row of cells slides as one.
function shoveCells(w, cells, sx, sy) {
  const along = (i) => sx * (i % W) + sy * Math.trunc(i / W);
  cells.sort((a, b) => along(b) - along(a) || a - b);
  for (const i of cells) {
    if (isShovable(w, i)) {
      slideRun(w, i, sx, sy);
    }
  }
}

// SHOVE: [kind, 0, size, shape, flags, 0, x0, y0, ...]. Pushes what is under the path along the path's direction.
function shove(w, stroke) {
  const points = readPoints(stroke, 6);
  if (points.length < 2) {
    return;
  }
  const [sx, sy] = dragStep(points[0], points.at(-1));
  if (sx === 0 && sy === 0) {
    return;
  }
  const size = whole(stroke[2], 1, 40);
  const shape = whole(stroke[3], 0, 2);
  const flags = whole(stroke[4], 0, 3);
  const seen = new Set();
  const mirrored = new Set();
  eachStamp(points, size, (cx, cy) =>
    stampCells(cx, cy, size, shape, (x, y) => {
      seen.add(y * W + x);
      mirrored.add(y * W + (W - 1 - x));
    }),
  );
  shoveCells(w, [...seen], sx, sy);
  if (flags & MIRROR) {
    // The copy on the far side pushes the mirrored way. A cell both sets share was already moved by the first push.
    shoveCells(
      w,
      [...mirrored].filter((i) => !seen.has(i)),
      -sx,
      sy,
    );
  }
}

function setSpigotElement(w, k, value) {
  const id = elementOf(value);
  if (id > 0 && ELEMENTS[id].paint) {
    w.spigots[k][0] = id;
  }
}

// SET: [kind, key, value]. Keys 0-3 spigot elements, 4-7 spigot sizes, 8 floor, 9 slug, 10 zombies, 11 backdrop.
function set(w, stroke) {
  const key = whole(stroke[1], -1, 12);
  const value = stroke[2];
  if (key >= 0 && key <= 3) {
    setSpigotElement(w, key, value);
  } else if (key >= 4 && key <= 7) {
    w.spigots[key - 4][1] = whole(value, 0, 5);
  } else if (key === 8) {
    w.settings.floor = whole(value, 0, 1);
  } else if (key === 9) {
    w.settings.slug = whole(value, 0, 2);
  } else if (key === 10 && ZOMBIE_COUNTS.includes(value)) {
    w.settings.zombies = value;
  } else if (key === 11) {
    w.settings.backdrop = whole(value, 0, 3);
  }
}

// BOLT: [kind, 0, 0, 0, 0, 0, x, y]
function bolt(w, stroke, d) {
  const [point] = readPoints(stroke, 6);
  if (point) {
    spawnBolt(w, point[0], point[1], d);
  }
}

// HAND: [kind, phase, 0, 0, 0, 0, x, y]. Phase 0 grabs, 1 drags, 2 lets go.
function hand(w, player, stroke, steps) {
  const [point] = readPoints(stroke, 6);
  if (point) {
    handStroke(w, String(player), whole(stroke[1], 0, 2), point, steps);
  }
}

// CLEAR: every cell empty at room heat, and every particle gone. Spigots, settings and creatures stay.
function clear(w) {
  w.el.fill(0);
  w.shade.fill(0);
  w.heat.fill(ROOM);
  w.life.fill(0);
  clearParticles(w);
}

/**
 * Applies one stroke between steps. player is the painter's id ("0" in a private world). steps is how many steps the
 * stroke's batch runs, which heat tools multiply by.
 */
export function applyStroke(w, player, stroke, steps) {
  const d = new Dice(mix(w.seed ^ 0x5eed, w.step, w.strokeCount));
  w.strokeCount = (w.strokeCount + 1) >>> 0;
  if (!Array.isArray(stroke) || stroke.length === 0) {
    return;
  }
  const kind = stroke[0];
  if (kind === STROKE.PAINT || kind === STROKE.LINE) {
    brush(w, stroke, d);
  } else if (kind === STROKE.BOX) {
    box(w, stroke, d);
  } else if (kind === STROKE.FILL) {
    fill(w, stroke, d);
  } else if (kind === STROKE.HEAT) {
    heat(w, stroke, steps, d);
  } else if (kind === STROKE.SHOVE) {
    shove(w, stroke);
  } else if (kind === STROKE.HAND) {
    hand(w, player, stroke, steps);
  } else if (kind === STROKE.BOLT) {
    bolt(w, stroke, d);
  } else if (kind === STROKE.SET) {
    set(w, stroke);
  } else if (kind === STROKE.CLEAR) {
    clear(w);
  } else if (kind === STROKE.RESET) {
    resetToStarter(w);
  }
}

/**
 * The cell indexes a stroke would touch, for previews and drag outlines. Needs no world and rolls no dice: spray gives
 * its whole circle, and a fill gives only the cell it starts from.
 */
export function strokeCells(stroke) {
  const cells = [];
  if (!Array.isArray(stroke) || stroke.length === 0) {
    return cells;
  }
  const gen = nextGeneration();
  const add = (i) => {
    if (mark[i] !== gen) {
      mark[i] = gen;
      cells.push(i);
    }
  };
  const kind = stroke[0];
  const flags = kind === STROKE.HAND || kind === STROKE.BOLT ? 0 : whole(stroke[4], 0, 3);
  const cell = (x, y) => withMirror(x, y, flags, add);
  if (kind === STROKE.PAINT || kind === STROKE.LINE || kind === STROKE.HEAT || kind === STROKE.SHOVE) {
    const size = whole(stroke[2], 1, 40);
    const shape = whole(stroke[3], 0, 2);
    eachStamp(readPath(stroke), size, (cx, cy) => stampCells(cx, cy, size, shape, cell));
  } else if (kind === STROKE.BOX) {
    eachBoxCell(stroke, cell);
  } else if (kind === STROKE.FILL || kind === STROKE.HAND || kind === STROKE.BOLT) {
    const [point] = readPoints(stroke, 6);
    if (point) {
      cell(point[0], point[1]);
    }
  }
  return cells;
}
