// The movement and neighbour helpers every element rule is built from. Rules only run on cells at least one cell in
// from every edge, so i - W - 1 .. i + W + 1 are always inside the grid.
import { EL, ELEMENTS } from "./elements.js";
import { ROOM, W } from "./world.js";

// Neighbour offsets: the 4 sides, then all 8 (rules that scan the neighbours themselves use these)
export const SIDES = [-1, 1, W, -W];
export const AROUND = [-1, 1, W, -W, W - 1, W + 1, -W - 1, -W + 1];

/** Moves a cell: swaps all four fields of cells i and j */
export function swap(w, i, j) {
  const { el, shade, heat, life } = w;
  const e = el[i];
  el[i] = el[j];
  el[j] = e;
  const s = shade[i];
  shade[i] = shade[j];
  shade[j] = s;
  const t = heat[i];
  heat[i] = heat[j];
  heat[j] = t;
  const l = life[i];
  life[i] = life[j];
  life[j] = l;
}

/** Converts cell i into element id: a new shade, the element's own heat if it has one (else the cell keeps its heat) */
export function put(w, i, id, d) {
  const info = ELEMENTS[id];
  w.el[i] = id;
  w.shade[i] = id === 0 ? 0 : d.roll(256);
  if (info.start !== null) {
    w.heat[i] = info.start;
  }
  w.life[i] = info.init ? info.init(w, i, d) : 0;
}

/** Like put, but the cell keeps its own heat even when the new element has a starting heat (freezing, melting) */
export function putKeepHeat(w, i, id, d) {
  const heat = w.heat[i];
  put(w, i, id, d);
  w.heat[i] = heat;
}

/** A brush writing element id into cell i: like put, but a painted cell starts at room heat unless it has its own */
export function paintCell(w, i, id, d, hue) {
  const info = ELEMENTS[id];
  w.el[i] = id;
  if (id === 0) {
    w.shade[i] = 0;
  } else {
    w.shade[i] = id === EL.coloredSand ? hue & 255 : d.roll(256);
  }
  w.heat[i] = info.start ?? ROOM;
  w.life[i] = info.init ? info.init(w, i, d) : 0;
}

// Moves cell i into the first empty cell among j1, then j2 and j3 in random order. Returns whether it moved.
function moveFirstEmpty(w, i, d, j1, j2, j3) {
  const el = w.el;
  if (el[j1] === 0) {
    swap(w, i, j1);
    return true;
  }
  const flip = d.roll(2) === 0;
  const a = flip ? j2 : j3;
  const b = flip ? j3 : j2;
  if (el[a] === 0) {
    swap(w, i, a);
    return true;
  }
  if (el[b] === 0) {
    swap(w, i, b);
    return true;
  }
  return false;
}

/** Moves cell i into an empty left or right neighbour, trying them in random order. Returns whether it moved. */
export function slideSideways(w, i, d) {
  const flip = d.roll(2) === 0;
  const a = flip ? i - 1 : i + 1;
  const b = flip ? i + 1 : i - 1;
  if (w.el[a] === 0) {
    swap(w, i, a);
    return true;
  }
  if (w.el[b] === 0) {
    swap(w, i, b);
    return true;
  }
  return false;
}

/** With chance p (of 10,000), falls down, else diagonally down; with slide, else sideways. Returns whether it moved. */
export function fall(w, i, d, p, slide) {
  if (!d.chance(p)) {
    return false;
  }
  if (moveFirstEmpty(w, i, d, i + W, i + W - 1, i + W + 1)) {
    return true;
  }
  return slide ? slideSideways(w, i, d) : false;
}

/** With chance p, falls straight down into an empty cell */
export function fallStraight(w, i, d, p) {
  if (!d.chance(p) || w.el[i + W] !== 0) {
    return false;
  }
  swap(w, i, i + W);
  return true;
}

/** fall upside down, always with sliding: gases */
export function rise(w, i, d, p) {
  if (!d.chance(p)) {
    return false;
  }
  if (moveFirstEmpty(w, i, d, i - W, i - W - 1, i - W + 1)) {
    return true;
  }
  return slideSideways(w, i, d);
}

// Swaps cell i with the first cell holding id among j1, then j2 and j3 in random order
function swapFirst(w, i, d, id, j1, j2, j3) {
  const el = w.el;
  if (el[j1] === id) {
    swap(w, i, j1);
    return true;
  }
  const flip = d.roll(2) === 0;
  const a = flip ? j2 : j3;
  const b = flip ? j3 : j2;
  if (el[a] === id) {
    swap(w, i, a);
    return true;
  }
  if (el[b] === id) {
    swap(w, i, b);
    return true;
  }
  return false;
}

/** With chance p, swaps with an id cell below (down, then the diagonals): "heavier than id" */
export function sink(w, i, d, id, p) {
  if (!d.chance(p)) {
    return false;
  }
  return swapFirst(w, i, d, id, i + W, i + W - 1, i + W + 1);
}

/** sink, plus a sideways swap with id at the same chance, so two liquids settle into layers */
export function layer(w, i, d, id, p) {
  if (!d.chance(p)) {
    return false;
  }
  if (swapFirst(w, i, d, id, i + W, i + W - 1, i + W + 1)) {
    return true;
  }
  const flip = d.roll(2) === 0;
  const a = flip ? i - 1 : i + 1;
  const b = flip ? i + 1 : i - 1;
  if (w.el[a] === id) {
    swap(w, i, a);
    return true;
  }
  if (w.el[b] === id) {
    swap(w, i, b);
    return true;
  }
  return false;
}

// Looks through offsets starting at a random one, so no direction is favoured
function findAround(w, i, d, id, offsets) {
  const count = offsets.length;
  const from = d.roll(count);
  for (let k = 0; k < count; k++) {
    const j = i + offsets[(from + k) % count];
    if (w.el[j] === id) {
      return j;
    }
  }
  return -1;
}

/** The index of a side neighbour (of 4) holding id, or -1 */
export function touching(w, i, d, id) {
  return findAround(w, i, d, id, SIDES);
}

/** The index of a neighbour (of all 8) holding id, or -1 */
export function near(w, i, d, id) {
  return findAround(w, i, d, id, AROUND);
}

/** With chance p for each side neighbour, puts id there (empty neighbours only, unless overwrite) */
export function emit(w, i, d, id, p, overwrite) {
  let acted = false;
  for (const offset of SIDES) {
    const j = i + offset;
    if ((overwrite || w.el[j] === 0) && d.chance(p)) {
      put(w, j, id, d);
      acted = true;
    }
  }
  return acted;
}

/** This cell and its 4 side neighbours become fire, whatever they held */
export function burnPlus(w, i, d) {
  put(w, i, EL.fire, d);
  for (const offset of SIDES) {
    put(w, i + offset, EL.fire, d);
  }
  return true;
}
