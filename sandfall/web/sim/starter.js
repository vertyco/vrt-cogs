// The scene a player who has never played starts in (spec 7.1): sand dunes, a pond fed by a small waterfall that spills
// off a wall ledge, a tree on a mound of soil with fireflies around it, a lit candle on the rock above the falls, and
// the slug on the dunes beyond the rock. It is a calm scene that stays pretty for minutes, so the spigots are off here
// (new blank worlds keep them). Built with ordinary strokes and a slug placed from the world's seed, so it is the same
// world on every screen for the same seed.
import { Dice, mix } from "./dice.js";
import { EL } from "./elements.js";
import { placeSlug } from "./slug.js";
import { applyStroke, SHAPE, STROKE } from "./strokes.js";
import { sin256 } from "./trig.js";
import { createWorld, H, W } from "./world.js";

const GROUND = 150;
// Flat ground where the scene's pieces stand, so the pond sits level and the tree stands upright. The dunes fade out
// over FADE columns either side of each flat stretch.
const FLATS = [
  [96, 214],
  [34, 78],
];
const FADE = 20;
const POND = { left: 104, right: 188, wallTop: 136, bottom: 151, waterTop: 140 };
// A wall cliff beside the pond with a ledge reaching over it, roofed into a low grotto (a slug born there later can't
// sit under the falls eating the stream). Spouts in the grotto's roof and back wall fill a shallow pool on the ledge,
// which spills over the lip at the ledge's end in one stream into the pond. Two drain cells set into the pond's wall
// at the water line carry off what comes in, so the level holds.
const CLIFF = { left: 189, right: 206, top: 70 };
const LEDGE = { left: 168, top: 92, bottom: 95 };
const ROOF = { left: 174, top: 80, bottom: 82 };
const SPOUTS = { left: 178, top: 83, bottom: 89 };
// The candle stands on the cliff top. It burns down from the top and drips a puddle round its foot, and lasts 2 to 4
// minutes.
const CANDLE = { left: 196, right: 199, height: 34 };
// The tree is painted rather than grown from a seed: a seed's tree is anything from a sapling to one filling the whole
// world, depending on the world's dice. Leaves fill the fork so falling pollen doesn't pile up inside the crown.
const TREE_X = 55;
const TRUNK_TOP = 124;
// The soil mound under the tree, bottom row first, as [left, right]
const MOUND = [
  [40, 70],
  [44, 66],
  [48, 62],
];
// Limbs as [x0, y0, x1, y1, thickness], then leafy clumps as [x, y, size]
const LIMBS = [
  [TREE_X, 126, 44, 112, 3],
  [TREE_X, 125, 67, 110, 3],
  [TREE_X, 124, 56, 104, 3],
  [44, 112, 37, 106, 2],
  [67, 110, 74, 104, 2],
];
const CLUMPS = [
  [56, 101, 20],
  [43, 107, 16],
  [68, 105, 16],
  [35, 110, 10],
  [76, 109, 10],
  [49, 95, 14],
  [63, 94, 14],
  [TREE_X, 114, 14],
];
const FIREFLIES = [
  [28, 112],
  [86, 106],
  [46, 82],
  [70, 84],
  [22, 96],
];
const SPIGOT_SIZE = 4;
const FLOOR = 8;
// The slug starts on the dunes right of the rock, which it can't climb: a slug born at a random spot could land in
// the pond and swell from eating it, or roll into the candle
const SLUG_SPOT = { x: 262, y: 112 };
const SLUG_DICE = 0x5106;

function box(w, element, x0, y0, x1, y1) {
  applyStroke(w, "0", [STROKE.BOX, element, 0, 0, 0, 0, x0, y0, x1, y1], 1);
}

function dot(w, element, x, y) {
  box(w, element, x, y, x, y);
}

function line(w, element, size, shape, x0, y0, x1, y1) {
  applyStroke(w, "0", [STROKE.LINE, element, size, shape, 0, 0, x0, y0, x1, y1], 1);
}

function stamp(w, element, size, x, y) {
  applyStroke(w, "0", [STROKE.PAINT, element, size, SHAPE.ROUND, 0, 0, x, y], 1);
}

function set(w, key, value) {
  applyStroke(w, "0", [STROKE.SET, key, value], 1);
}

/** How far column x is from the nearest flat stretch, capped at FADE */
function awayFromFlat(x) {
  let away = FADE;
  for (const [left, right] of FLATS) {
    away = Math.min(away, Math.max(0, left - x, x - right));
  }
  return away;
}

/** The height of the sand's surface in column x */
function groundAt(x) {
  const dune = (sin256(x * 3) * 9 + sin256(x * 7 + 40) * 4) >> 8;
  return GROUND + Math.trunc((dune * awayFromFlat(x)) / FADE);
}

function pond(w) {
  box(w, EL.wall, POND.left, POND.wallTop, POND.right, POND.bottom);
  box(w, EL.empty, POND.left + 2, POND.wallTop - 1, POND.right - 2, POND.bottom - 2);
  box(w, EL.water, POND.left + 2, POND.waterTop, POND.right - 2, POND.bottom - 2);
  box(w, EL.drain, POND.right - 1, POND.waterTop - 1, POND.right - 1, POND.waterTop);
}

function waterfall(w) {
  box(w, EL.wall, CLIFF.left, CLIFF.top, CLIFF.right, GROUND);
  box(w, EL.wall, LEDGE.left, LEDGE.top, CLIFF.left, LEDGE.bottom);
  dot(w, EL.wall, LEDGE.left, LEDGE.top - 1);
  box(w, EL.wall, ROOF.left, ROOF.top, CLIFF.left, ROOF.bottom);
  box(w, EL.spout, SPOUTS.left, ROOF.bottom, CLIFF.left - 1, ROOF.bottom);
  box(w, EL.spout, CLIFF.left, SPOUTS.top, CLIFF.left, SPOUTS.bottom);
}

function candle(w) {
  const top = CLIFF.top - CANDLE.height;
  box(w, EL.wax, CANDLE.left, top, CANDLE.right, CLIFF.top - 1);
  dot(w, EL.fire, (CANDLE.left + CANDLE.right) >> 1, top - 1);
}

function tree(w) {
  MOUND.forEach(([left, right], k) => box(w, EL.soil, left, GROUND - 1 - k, right, GROUND - 1 - k));
  for (const [x, y, size] of CLUMPS) {
    stamp(w, EL.leaf, size, x, y);
  }
  line(w, EL.branch, 3, SHAPE.SQUARE, TREE_X, GROUND - 2, TREE_X, TRUNK_TOP);
  for (const [x0, y0, x1, y1, size] of LIMBS) {
    line(w, EL.branch, size, SHAPE.ROUND, x0, y0, x1, y1);
  }
  for (const [x, y] of FIREFLIES) {
    dot(w, EL.firefly, x, y);
  }
}

/** The first-time scene, in a world whose seed is `seed` */
export function starterWorld(seed) {
  const w = createWorld({ seed });
  // Without a floor the bottom row drains and the dunes would pour away within seconds
  set(w, FLOOR, 1);
  for (let k = 0; k < w.spigots.length; k++) {
    set(w, SPIGOT_SIZE + k, 0);
  }
  for (let x = 0; x < W; x++) {
    box(w, EL.sand, x, groundAt(x), x, H - 1);
  }
  pond(w);
  waterfall(w);
  candle(w);
  tree(w);
  placeSlug(w, new Dice(mix(w.seed, SLUG_DICE, 0)), SLUG_SPOT.x, SLUG_SPOT.y);
  w.strokeCount = 0;
  return w;
}

/**
 * RESET: puts the starter scene back in world w, settings and creatures too. The scene comes from w's own seed, so
 * every screen rebuilds the same one. The clock and stroke count run on, so the dice after it stay in step.
 */
export function resetToStarter(w) {
  const fresh = starterWorld(w.seed);
  w.el.set(fresh.el);
  w.shade.set(fresh.shade);
  w.heat.set(fresh.heat);
  w.life.set(fresh.life);
  w.spigots = fresh.spigots;
  w.settings = fresh.settings;
  w.parts = fresh.parts;
  w.slug = fresh.slug;
  w.zombies = fresh.zombies;
  w.grabs = fresh.grabs;
}
