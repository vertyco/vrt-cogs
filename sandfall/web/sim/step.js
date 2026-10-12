// One step of the world. The order here is part of what keeps every screen in a shared world identical.
import { Dice, mix } from "./dice.js";
import { EL, ELEMENT_COUNT } from "./elements.js";
import { diffuseHeat } from "./heat.js";
import { paintCell } from "./helpers.js";
import { stampParticles } from "./particles.js";
import { RULES as ELECTRIC } from "./rules/electric.js";
import { RULES as FIRE } from "./rules/fire.js";
import { RULES as GASES } from "./rules/gases.js";
import { RULES as LIFE } from "./rules/life.js";
import { RULES as LIQUIDS } from "./rules/liquids.js";
import { RULES as MACHINES } from "./rules/machines.js";
import { RULES as POWDERS } from "./rules/powders.js";
import { RULES as SOLIDS } from "./rules/solids.js";
import { RULES as SPECIAL } from "./rules/special.js";
import { stepSlug } from "./slug.js";
import { H, ROOM, W } from "./world.js";
import { dropSlugHolds, stepZombies } from "./zombies.js";

// One rule per element id (null: the element never acts by itself)
const DISPATCH = new Array(ELEMENT_COUNT).fill(null);
// Each id is set once, so the order these entries are read in can't change the table
for (const rules of [POWDERS, LIQUIDS, GASES, SOLIDS, FIRE, ELECTRIC, SPECIAL, LIFE, MACHINES]) {
  for (const [id, fn] of Object.entries(rules)) {
    DISPATCH[Number(id)] = fn;
  }
}

function recount(w) {
  const { el, tally } = w;
  tally.fill(0);
  for (let i = 0; i < el.length; i++) {
    tally[el[i]] += 1;
  }
}

// Spigot k sprinkles its element into a box at the top centred on x = (k + 1) * W / 5, overwriting what is there
function runSpigots(w, d) {
  for (let k = 0; k < w.spigots.length; k++) {
    const [element, size] = w.spigots[k];
    if (size === 0 || element === 0) {
      continue;
    }
    const centre = Math.trunc(((k + 1) * W) / 5);
    const n = 3 * size;
    for (let y = 1; y <= n; y++) {
      for (let x = centre - n; x <= centre + n; x++) {
        if (d.chance(1000)) {
          // Colored sand from a spigot comes out as a rainbow across its width
          paintCell(w, y * W + x, element, d, x * 8);
        }
      }
    }
  }
}

// Bottom row up, alternating direction each step. Moves land straight in the grid, so anything moving up or along the
// scan direction can be met again later in the same step.
function scan(w, d) {
  const el = w.el;
  const forward = (w.step & 1) === 0;
  for (let y = H - 2; y >= 1; y--) {
    const row = y * W;
    for (let k = 1; k <= W - 2; k++) {
      const x = forward ? k : W - 1 - k;
      const i = row + x;
      const id = el[i];
      if (id === 0) {
        continue;
      }
      const rule = DISPATCH[id];
      if (rule !== null) {
        rule(w, x, y, i, d);
      }
    }
  }
}

function setCell(w, i, id) {
  w.el[i] = id;
  w.shade[i] = 0;
  w.heat[i] = ROOM;
  w.life[i] = 0;
}

// The top row is open (gases leave), the bottom row drains unless the floor is on, the side columns are wall
function edges(w) {
  const bottom = (H - 1) * W;
  const floor = w.settings.floor ? EL.wall : 0;
  for (let x = 1; x <= W - 2; x++) {
    if (w.el[x] !== 0) {
      setCell(w, x, 0);
    }
    if (w.el[bottom + x] !== floor) {
      setCell(w, bottom + x, floor);
    }
  }
  for (let y = 0; y < H; y++) {
    if (w.el[y * W] !== EL.wall) {
      setCell(w, y * W, EL.wall);
    }
    if (w.el[y * W + W - 1] !== EL.wall) {
      setCell(w, y * W + W - 1, EL.wall);
    }
  }
}

// The slug and the zombies move here, last. When the slug bursts, whatever held the old one lets go.
function moveCreatures(w, d) {
  const before = w.slug;
  stepSlug(w, d);
  if (before !== null && w.slug !== before) {
    dropSlugHolds(w);
  }
  stepZombies(w, d);
}

/** Runs one step: recount, spigots, particles, the scan, edges, heat, creatures */
export function stepWorld(w) {
  const d = new Dice(mix(w.seed, w.step, 0));
  w.events.boom = 0;
  w.events.sizzle = 0;
  w.events.zap = 0;
  w.events.bolt = 0;
  recount(w);
  runSpigots(w, d);
  stampParticles(w, d);
  scan(w, d);
  edges(w);
  diffuseHeat(w);
  moveCreatures(w, d);
  w.step = (w.step + 1) >>> 0;
}
