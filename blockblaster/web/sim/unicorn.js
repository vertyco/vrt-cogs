// The Super Unicorn: a bar that charges as cubes take damage, and a merged pig that shoots every color at once.
// While the player has earned it (the bot says so when the level starts), its bar fills by 1 for every point of damage
// a cube takes, except the Unicorn's own (MergedShooterSystem$$OnTargetDamaged, RVA 0x518E55C; CanChargeFrom, RVA
// 0x518E5D0; aim.chargeUnicorn does the counting where damage lands). The tap ["unicorn"] with a full bar merges every
// slot pig, and the rescue pigs Connected to them, into one shooter that fires all their ammo, color after color, at
// targets spread over the picture, then the merged pigs leave and the stuck check's repair runs.
// The original's game is stopped while it runs (MergedShooterSystem is a game pauser), so the whole run lands in the
// one tap and the page plays it with its clock held. Its picks use a time-seeded System.Random only for the bucket
// shuffles and the pick inside a bucket; this module keeps the algorithm and draws from the level's generator in the
// same order of calls. common/sim/unicorn.py mirrors this file.
import * as aim from "./aim.js";
import * as base from "./base.js";
import * as boosters from "./boosters.js";
import * as checks from "./checks.js";
import * as gridx from "./grid.js";
import { idiv, isqrt } from "./mathx.js";
import { SHOT_DAMAGE, UNICORN_CHARGE_COUNT, UNICORN_FILL_PERCENT } from "./numbers.js";
import * as places from "./places.js";

// Candidate tiers (MergedShooterTargetTier) and the priority one tier spans (MergedShooterFeatureTargetOrder)
export const TIER_OPEN_PIXEL = 0;
export const TIER_BLOCKED_PIXEL = 1;
export const TIER_OPEN_FEATURE = 2;
export const TIER_BLOCKED_FEATURE = 3;
export const RANK_SPAN = 100;

// The level's bar: whether the player has the Unicorn this level, the charge, and the charge that fills it
export function newUnicorn(cubes, active) {
  return { active, charge: 0, need: needFor(cubes), running: false };
}

// round(0.9 x cubes / 3), halves to even, at least 1 (LevelRatioChargeRequirement$$Calculate, RVA 0x514B1D0, with
// MergedShooterSettings' FillPercent 0.9 and ChargeCount 3; the float32 steps give the same whole number)
export function needFor(cubes) {
  const span = 100 * UNICORN_CHARGE_COUNT;
  let whole = idiv(cubes * UNICORN_FILL_PERCENT, span);
  const twice = 2 * (cubes * UNICORN_FILL_PERCENT - whole * span);
  if (twice > span || (twice === span && whole % 2 === 1)) {
    whole += 1;
  }
  return Math.max(1, whole);
}

export function full(state) {
  const { unicorn } = state;
  return unicorn.active && unicorn.charge >= unicorn.need;
}

// The ["unicorn"] tap (MergedShooterSystem$$TryActivate, RVA 0x518F1E0; GetUseFailReason, RVA 0x518F09C). Returns
// why it was refused, or null
export function use(state) {
  if (!state.unicorn.active) {
    return "not active";
  }
  if (state.finishing) {
    return "auto-finisher running";
  }
  if (state.cubesLeft <= 0) {
    return "no cubes";
  }
  if (!full(state)) {
    return "not charged";
  }
  const merged = gather(state);
  if (!merged.length) {
    return "no pigs to merge";
  }
  run(state, merged);
  return null;
}

// Every slot pig, in slot order, that may merge, each followed by the pigs of its Connected group waiting in the rescue
// queue (MergedShooterMergeGatherer$$Gather, RVA 0x5170B90; AddWithRescueConnections, RVA 0x516D25C)
export function gather(state) {
  const merged = [];
  for (const pigId of state.slots) {
    if (pigId === null || merged.includes(pigId) || !mergeable(state, state.pigs[pigId])) {
      continue;
    }
    merged.push(pigId);
    for (const member of links(state, state.pigs[pigId]) || []) {
      if (state.rescue.includes(member) && !merged.includes(member)) {
        merged.push(member);
      }
    }
  }
  return merged;
}

// The pig's Connected group from a feature module's mergeLinks hook, or null
export function links(state, pig) {
  for (const module of base.MODULES) {
    if (module.mergeLinks) {
      const members = module.mergeLinks(state, pig);
      if (members !== null) {
        return members;
      }
    }
  }
  return null;
}

// A Connected pig merges only while its whole group waits in slots or the rescue queue
// (MergedShooterMergeGatherer$$IsEligible, RVA 0x516DD4C)
export function mergeable(state, pig) {
  const members = links(state, pig);
  return members === null || members.every((member) => ["slot", "rescue"].includes(state.pigs[member].place));
}

// [color, ammo] summed over the merged pigs, colors in the order they first appear
// (MergedShooterMergeGatherer$$BuildColorAmmoTable, RVA 0x516FA90)
export function ammoTable(state, merged) {
  const table = [];
  for (const pigId of merged) {
    const pig = state.pigs[pigId];
    if (pig.ammo <= 0) {
      continue;
    }
    const row = table.find((entry) => entry[0] === pig.color);
    if (row) {
      row[1] += pig.ammo;
    } else {
      table.push([pig.color, pig.ammo]);
    }
  }
  return table;
}

// The merge and the shooting, then the merged pigs leave, the repair runs, the bar empties and the Pixel Pipes that
// waited check their colors (<ShootAndFinish>d__43$$MoveNext, RVA 0x5167C88; <ShootAllColors>d__44, RVA 0x51676D0)
export function run(state, merged) {
  const { unicorn } = state;
  unicorn.running = true;
  const table = ammoTable(state, merged);
  for (const pigId of merged) {
    state.pigs[pigId].ammo = 0;
  }
  base.emit(state, "unicorn_start", { ids: [...merged], colors: table.map((row) => [...row]) });
  for (const [color, ammo] of table) {
    for (const pick of takeTargets(state, color, ammo)) {
      shoot(state, color, pick);
    }
  }
  for (const pigId of merged) {
    places.vanish(state, state.pigs[pigId], "merged");
  }
  sync(state);
  unicorn.charge = 0;
  unicorn.running = false;
  base.callHooks(state, "unicornDone");
  checks.requestStuckCheck(state);
  base.emit(state, "unicorn_end", {});
  base.emit(state, "booster_done", { name: "unicorn" });
}

// MapController$$SyncShootersAndPixels, RVA 0x58D1F50: empty pigs vanish, ammo beyond what each color has left is
// taken away lowest pigs first, and the auto-finisher may start
export function sync(state) {
  for (const pigId of checks.repair(state, checks.extraAmmo(state))) {
    places.vanish(state, state.pigs[pigId], "repair");
  }
  checks.tryAutofinish(state);
}

// ---------- Picking targets ----------

// The color's shots: candidates, the spread selection, then where on each target its shots land
// (MergedShooterExecutionFlow$$TakeTargets, RVA 0x515ED0C)
export function takeTargets(state, color, ammo) {
  const picks = selectTargets(state, ammo, collect(state, color, ammo));
  assignPoints(state, picks);
  return picks;
}

// target is a grid target's id (-1 for a feature's queued part, which owner's module names by ref); cells are the
// points its shots may land on and cell its own point
export function candidate(target, owner, ref, cells, cell, priority, capacity) {
  return { target, owner, ref, cells, cell, priority, capacity };
}

// Cubes, then features, then the features' queued parts (MergedShooterTargetCollector$$Collect, RVA 0x519ED94).
// Nothing when maxShots is below 1
export function collect(state, color, maxShots) {
  const found = [];
  if (maxShots < 1) {
    return found;
  }
  collectCubes(state, color, maxShots, found);
  collectFeatures(state, color, maxShots, found);
  collectQueued(state, color, maxShots, found);
  return found;
}

// Damage the target still takes beyond the shots already flying at it (IHitTarget's would-die check)
export function hitsLeft(target) {
  return target.health - target.pending;
}

// Every living cube of the color, row by row from the bottom, each at its lowest-left cell: tier 0 when no obstacle
// stands on it and it isn't a hidden Surprise Pixel, else tier 1 (CollectPixels, RVA 0x519B38C)
export function collectCubes(state, color, maxShots, found) {
  const { grid } = state;
  const cubes = grid.targets.filter((t) => t.owner === 0 && !t.dead && t.cells.length && t.color === color);
  const rowOf = (cube) => idiv(cube.cells[0], grid.width);
  cubes.sort((a, b) => rowOf(a) - rowOf(b) || (a.cells[0] % grid.width) - (b.cells[0] % grid.width));
  for (const cube of cubes) {
    const left = hitsLeft(cube);
    if (left < 1 || !cube.hittable) {
      continue;
    }
    const tier = boosters.superViable(state, cube) ? TIER_OPEN_PIXEL : TIER_BLOCKED_PIXEL;
    const priority = tier * RANK_SPAN;
    found.push(candidate(cube.id, 0, -1, [...cube.cells], cube.cells[0], priority, Math.min(left, maxShots)));
  }
}

// Every feature target of the color that isn't "match all", in the order it joined the picture, at its cell nearest its
// middle: tier 2, or 3 with an obstacle on its cells (CollectFeatures, RVA 0x519B7DC; TryGetGridPoint, RVA 0x519A334;
// IsBlocked, RVA 0x519A714). No feature has a rank yet, so the rank is 0
export function collectFeatures(state, color, maxShots, found) {
  for (const target of state.grid.targets) {
    if (target.owner === 0 || target.dead || !target.hittable || !target.cells.length || target.matchAll) {
      continue;
    }
    const left = hitsLeft(target);
    if (left < 1 || !checks.matches(target, color)) {
      continue;
    }
    const tier = blocked(state, target) ? TIER_BLOCKED_FEATURE : TIER_OPEN_FEATURE;
    const cell = gridPoint(state.grid, target.cells);
    const capacity = Math.min(left, maxShots);
    found.push(candidate(target.id, target.owner, -1, [...target.cells], cell, tier * RANK_SPAN, capacity));
  }
}

// Features' queued parts of the color, from each module's unicornReserves hook as [ref, cells, tier, rank, hits]
// (CollectQueuedFeatures, RVA 0x5199FEC): a Pixel Pipe's cubes still in its queue
export function collectQueued(state, color, maxShots, found) {
  for (const module of base.MODULES) {
    if (!module.unicornReserves) {
      continue;
    }
    for (const [ref, cells, tier, rank, hits] of module.unicornReserves(state, color)) {
      if (hits >= 1 && cells.length) {
        const cell = gridPoint(state.grid, cells);
        const priority = tier * RANK_SPAN + rank;
        found.push(candidate(-1, module.NUMBER, ref, [...cells], cell, priority, Math.min(hits, maxShots)));
      }
    }
  }
}

// Some other obstacle stands on one of the target's cells
export function blocked(state, target) {
  for (const cell of target.cells) {
    for (const other of gridx.at(state.grid, cell)) {
      if (other !== target && other.obstacle && !other.dead) {
        return true;
      }
    }
  }
  return false;
}

// The first of the cells nearest the middle of their bounding box
export function gridPoint(grid, cells) {
  const xs = cells.map((cell) => cell % grid.width);
  const ys = cells.map((cell) => idiv(cell, grid.width));
  const midX = Math.min(...xs) + Math.max(...xs);
  const midY = Math.min(...ys) + Math.max(...ys);
  let best = cells[0];
  let bestDistance = -1;
  cells.forEach((cell, index) => {
    const dx = 2 * xs[index] - midX;
    const dy = 2 * ys[index] - midY;
    const distance = dx * dx + dy * dy;
    if (bestDistance < 0 || distance < bestDistance) {
      best = cell;
      bestDistance = distance;
    }
  });
  return best;
}

// Up to ammo shots: the priorities lowest first, and inside each the shots spread over its candidates' area, each
// picked candidate taking as many shots as kill it (MergedShooterTargetingLogic$$SelectTargets, RVA 0x65BE194). Each
// shot is its own copy of its candidate
export function selectTargets(state, ammo, found) {
  const picks = [];
  if (ammo < 1 || !found.length) {
    return picks;
  }
  const priorities = [];
  for (const entry of found) {
    if (!priorities.includes(entry.priority)) {
      priorities.push(entry.priority);
    }
  }
  priorities.sort((a, b) => a - b);
  let remaining = ammo;
  for (const priority of priorities) {
    if (remaining < 1) {
      break;
    }
    remaining -= pickForPriority(state, picks, found, priority, remaining);
  }
  return picks;
}

// PickForPriority: one candidate per bucket a round until the shots run out. Returns the shots it gave
export function pickForPriority(state, picks, found, priority, remaining) {
  const group = [];
  found.forEach((entry, index) => {
    if (entry.priority === priority && entry.capacity >= 1) {
      group.push(index);
    }
  });
  const width = state.grid.width;
  const points = group.map((i) => [found[i].cell % width, idiv(found[i].cell, width)]);
  const spread = setupSpread(state, points, remaining);
  let used = 0;
  while (used < remaining) {
    const index = pickNext(state, spread);
    if (index < 0) {
      break;
    }
    const entry = found[group[index]];
    const take = Math.min(entry.capacity, remaining - used);
    for (let n = 0; n < take; n++) {
      picks.push({ ...entry });
    }
    used += take;
  }
  return used;
}

// ---------- The spread (MergedShooterSpreadLogic) ----------

// Cut the points' bounding box into square buckets of about one shot each, file each point into its bucket, and
// shuffle the non-empty buckets (Setup, RVA 0x519577C; FillBuckets, RVA 0x5197AF4; CollectOrder, RVA 0x5198034)
export function setupSpread(state, points, shotCount) {
  const spread = { order: [], cursor: 0, starts: [], ends: [], items: [] };
  if (!points.length) {
    return spread;
  }
  const lowX = Math.min(...points.map((p) => p[0]));
  const lowY = Math.min(...points.map((p) => p[1]));
  const sizeX = Math.max(...points.map((p) => p[0])) - lowX + 1;
  const sizeY = Math.max(...points.map((p) => p[1])) - lowY + 1;
  const side = bucketSide(sizeX, sizeY, shotCount);
  const columns = idiv(sizeX + side - 1, side);
  const count = columns * idiv(sizeY + side - 1, side);
  const buckets = points.map((p) => idiv(p[1] - lowY, side) * columns + idiv(p[0] - lowX, side));
  const starts = new Array(count + 1).fill(0);
  for (const bucket of buckets) {
    starts[bucket + 1] += 1;
  }
  for (let index = 1; index <= count; index++) {
    starts[index] += starts[index - 1];
  }
  const ends = starts.slice(0, count);
  const items = new Array(points.length).fill(0);
  buckets.forEach((bucket, index) => {
    items[ends[bucket]] = index;
    ends[bucket] += 1;
  });
  Object.assign(spread, { starts, ends, items });
  for (let bucket = 0; bucket < count; bucket++) {
    if (ends[bucket] > starts[bucket]) {
      spread.order.push(bucket);
    }
  }
  shuffle(state, spread.order);
  return spread;
}

// max(1, ceil(sqrt(area / shots))) in whole numbers (GetCellSize, RVA 0x5197A48)
export function bucketSide(sizeX, sizeY, shotCount) {
  const area = sizeX * sizeY;
  const shots = Math.max(1, shotCount);
  let side = isqrt(idiv(area, shots));
  while (side * side * shots < area) {
    side += 1;
  }
  return Math.max(1, side);
}

// The next point: a random one left in the next bucket of the round, the round reshuffled when it ends; a bucket
// leaves the round once empty. -1 when every bucket is empty (TryPickNext, RVA 0x5195B54)
export function pickNext(state, spread) {
  const { order, ends, items } = spread;
  if (!order.length) {
    return -1;
  }
  if (spread.cursor >= order.length) {
    spread.cursor = 0;
    shuffle(state, order);
  }
  const bucket = order[spread.cursor];
  const start = spread.starts[bucket];
  const slot = start + state.rng.randInt(ends[bucket] - start);
  const index = items[slot];
  ends[bucket] -= 1;
  items[slot] = items[ends[bucket]];
  if (ends[bucket] > start) {
    spread.cursor += 1;
  } else {
    order.splice(spread.cursor, 1);
  }
  return index;
}

// Fisher-Yates from the back (MergedShooterSpreadLogic$$Shuffle, RVA 0x51974F8)
export function shuffle(state, values) {
  for (let i = values.length - 1; i > 0; i--) {
    const k = state.rng.randInt(i + 1);
    [values[i], values[k]] = [values[k], values[i]];
  }
}

// Spread the shots of each run of shots at one target over that target's cells, so a big target is hit all over
// (MergedShooterShotPointLogic$$Assign, RVA 0x5196300; AssignRun, RVA 0x5195174). A target on one cell keeps its point
export function assignPoints(state, picks) {
  const width = state.grid.width;
  let start = 0;
  while (start < picks.length) {
    let end = start + 1;
    while (end < picks.length && sameTarget(picks[end], picks[start])) {
      end += 1;
    }
    const cells = picks[start].cells;
    if (cells.length >= 2) {
      const points = cells.map((cell) => [cell % width, idiv(cell, width)]);
      let spread = setupSpread(state, points, end - start);
      for (let index = start; index < end; index++) {
        let point = pickNext(state, spread);
        if (point < 0) {
          spread = setupSpread(state, points, end - index);
          point = pickNext(state, spread);
        }
        picks[index].cell = cells[point];
      }
    }
    start = end;
  }
}

export function sameTarget(a, b) {
  return a.target === b.target && a.owner === b.owner && a.ref === b.ref;
}

// ---------- Shooting ----------

export function moduleOf(owner) {
  return base.MODULES.find((module) => module.NUMBER === owner) || null;
}

// The pick still takes a shot (MergedShooterExecutionFlow$$IsShootable, RVA 0x515F2B4)
export function shootable(state, color, pick) {
  if (pick.target >= 0) {
    const target = state.grid.targets[pick.target];
    return !target.dead && target.cells.length > 0 && hitsLeft(target) >= 1;
  }
  const module = moduleOf(pick.owner);
  return module !== null && module.unicornReserveLeft(state, pick.ref, color) >= 1;
}

// A fresh one-shot pick for a shot whose target died meanwhile (TryFindReplacement, RVA 0x515F364)
export function replacement(state, color) {
  const picks = selectTargets(state, 1, collect(state, color, 1));
  if (!picks.length) {
    return null;
  }
  assignPoints(state, picks);
  return picks[0];
}

// One shot of 1 damage (MergedShooterExecutionFlow$$ShootTarget, RVA 0x515EF9C). A shot with nothing left to shoot is
// lost. A shot at a Pixel Pipe's queue pops one of its cubes out and breaks it (PixelPipeDrainer$$PopPixel, RVA
// 0x5752420)
export function shoot(state, color, pick) {
  if (!shootable(state, color, pick)) {
    pick = replacement(state, color);
    if (pick === null) {
      base.emit(state, "unicorn_miss", { color });
      return;
    }
  }
  base.emit(state, "unicorn_shot", { target: pick.target, owner: pick.owner, cell: pick.cell, color });
  if (pick.target >= 0) {
    aim.hit(state, state.grid.targets[pick.target], SHOT_DAMAGE, null);
    return;
  }
  const cube = moduleOf(pick.owner).unicornPop(state, pick.ref, color);
  if (cube !== null) {
    aim.hit(state, cube, cube.health, null);
  }
}
