// The win check, the stuck check with its repair and fail names, and the auto-finisher.
// Both checks are timed waits that something starts and anything later restarts, as the original's coroutines are
// (GameFinishController$$StartCheckToWin and MapFailController$$TryCheckForCannotShootFail stop the running wait
// before starting a new one). Their timers fire in the checks phase. The stuck check's repair returns the pigs it
// emptied for the core to make vanish, so this module never imports places. common/sim/checks.py mirrors this file.
import * as base from "./base.js";
import * as gridx from "./grid.js";
import { idiv } from "./mathx.js";
import { STUCK_DELAY, STUCK_INPUT_EXTRA, WIN_DELAY } from "./numbers.js";

// Queue-front blockers and grid blockers a stuck fail can be named after, in the order that wins a tie
// (MapFailController$$TriggerBlockerFail, RVA 0x58E585C)
export const FRONT_NAMES = ["locked_out", "frozen", "totem"];
export const GRID_NAMES = ["ufo", "curtain", "spaceship"];

// A pig is about to vanish, a feature left the grid or a target died: (re)start the wait before the win check
// (GameFinishController$$StartCheckToWin, RVA 0x5250D14, restarts <CheckToWinEnumerator>d__29)
export function requestWinCheck(state) {
  base.cancel(state, "win_check");
  base.schedule(state, WIN_DELAY, "win_check", null);
}

// Timer: once nothing holds the finish back (checked every tick), the level is won when no pigs are left anywhere
// (<CheckToWinEnumerator>d__29$$MoveNext, RVA 0x526CF14; MapProvider$$IsMapCleared, RVA 0x58E7F3C)
export function winCheck(state) {
  if (state.over !== null) {
    return;
  }
  for (const module of base.MODULES) {
    if (module.holdsFinish && module.holdsFinish(state)) {
      base.schedule(state, 1, "win_check", null);
      return;
    }
  }
  if (base.livePigCount(state) === 0) {
    state.over = { result: "won", tick: state.tick, kind: null, name: null };
    base.emit(state, "won", {});
  }
}

// A pig was tapped, left a queue, landed in a slot or is about to vanish, or the last shot in flight ended: (re)start
// the stuck check's wait (MapFailController$$TryCheckForCannotShootFail, RVA 0x58DFB98, from the handlers OnEnable
// subscribes)
export function requestStuckCheck(state) {
  base.cancel(state, "stuck_check");
  base.schedule(state, STUCK_DELAY, "stuck_check", "look");
}

// Timer (MapFailController.<CheckForCannotShootFail>d__41$$MoveNext, RVA 0x58E7A8C). "look": after the first wait,
// and then every tick until nothing is mid-action, decide whether the level is stuck; a stuck level blocked only by
// input-only blockers waits STUCK_INPUT_EXTRA more and then acts on that decision without looking again ("act").
// Acting fails the level when every color's ammo fits what is left of it, else repairs. Returns the pigs the repair
// emptied, in the order they vanish, or null when it did not repair
export function stuckCheck(state, stage) {
  if (state.over !== null) {
    return null;
  }
  if (stage === "look") {
    if (busy(state)) {
      base.schedule(state, 1, "stuck_check", "look");
      return null;
    }
    const inputOnly = inputOnlyBlocked(state);
    const stuck = (inputOnly || !canShootAny(state)) && base.livePigCount(state) > 0;
    if (!stuck) {
      return null;
    }
    if (inputOnly) {
      base.schedule(state, STUCK_INPUT_EXTRA, "stuck_check", "act");
      return null;
    }
  }
  const extras = extraAmmo(state);
  if (!extras.length) {
    base.fail(state, "stuck", failName(state));
    return null;
  }
  return repair(state, extras);
}

// Something is mid-action: a shot in flight or a feature's own action (FailCheckDelayCondition: a lock opening, a
// mallet or hammer working, a Hungry Door finishing, a spaceship launching, a Pixel Mixer releasing)
export function busy(state) {
  if (state.shots.length) {
    return true;
  }
  for (const module of base.MODULES) {
    if (module.busy && module.busy(state)) {
      return true;
    }
  }
  return false;
}

// The fail name of the feature blocking a queue-front entry, or null
export function frontBlocker(state, pig) {
  for (const module of base.MODULES) {
    if (module.blocker) {
      const name = module.blocker(state, pig);
      if (name !== null && name !== undefined) {
        return name;
      }
    }
  }
  return null;
}

export function fronts(state) {
  return state.queues.filter((queue) => queue.length).map((queue) => state.pigs[queue[0]]);
}

// A queue front that could be tapped if a tray were free: nothing disabling or locking it and no feature against it
// (MapFailController$$<NormallyTappableFirstShooterExists>b__50_0, the additive tap conditions). A feature with a
// canTapNormally hook answers through it instead of canTap (a Connected group needn't fit on the belt here)
export function normallyTappable(state, pig) {
  if (pig.tags.includes("untappable") || pig.tags.includes("disabled")) {
    return false;
  }
  for (const module of base.MODULES) {
    if (module.canTapNormally) {
      if (module.canTapNormally(state, pig) !== null) {
        return false;
      }
      continue;
    }
    if (module.canTap) {
      const reason = module.canTap(state, pig, false);
      if (reason !== null && reason !== undefined) {
        return false;
      }
    }
  }
  return true;
}

// MapFailController$$NormallyTappableFirstShooterExists, RVA 0x58DFF18
export function tappableFrontExists(state) {
  return fronts(state).some((pig) => normallyTappable(state, pig));
}

// No queue front can be tapped and every queue front is a Bull Totem
// (MapFailController$$AreAllQueuesBlockedByInputOnlyBlockers, RVA 0x58E1188)
export function inputOnlyBlocked(state) {
  const front = fronts(state);
  if (!front.length || tappableFrontExists(state)) {
    return false;
  }
  return front.every((pig) => frontBlocker(state, pig) === "totem");
}

// Pigs whose place is on the map, by id
export function livePigs(state) {
  return Object.keys(state.pigs)
    .map(Number)
    .sort((a, b) => a - b)
    .map((pigId) => state.pigs[pigId])
    .filter((pig) => pig.place !== "gone" && pig.place !== "held");
}

// With a tappable queue front, every pig on the map that isn't disabled; otherwise only the pigs outside the queues
// that can be tapped (MapFailController$$CanShootAnyTargetNew, RVA 0x58DFBEC: GetNotDisabledShooters or
// GetShootersOutsideOfQueue)
export function usablePigs(state) {
  const live = livePigs(state);
  if (tappableFrontExists(state)) {
    return live.filter((pig) => !pig.tags.includes("disabled"));
  }
  return live.filter((pig) => pig.place !== "queue" && !pig.tags.includes("untappable"));
}

// The target takes shots of this color (HitTarget$$IsTargetMatch, RVA 0x544E608)
export function matches(target, color) {
  return target.matchAll || target.color === color || (target.colors !== null && target.colors.includes(color));
}

// Some usable pig with ammo has a color some exposed target takes (MapFailController$$CanShoot, RVA 0x58DFFF8)
export function canShootAny(state) {
  const targets = exposedTargets(state);
  for (const pig of usablePigs(state)) {
    if (pig.ammo >= 1 && targets.some((target) => matches(target, pig.color))) {
      return true;
    }
  }
  return false;
}

// Target ids of obstacles the stuck check sees through, such as wood blocks and Music Toys: a level is never called
// stuck because of them, though they still stop real shots (MapFailController$$RebuildIgnoredObstaclesCache, RVA
// 0x58E0A1C)
export function ignoredObstacles(state) {
  const ignored = new Set();
  for (const module of base.MODULES) {
    if (module.ignoredObstacles) {
      for (const targetId of module.ignoredObstacles(state)) {
        ignored.add(targetId);
      }
    }
  }
  return ignored;
}

// 1 for every cell holding something solid that the check doesn't see through, else 0. A cube always counts
export function blockedCells(state, ignored) {
  const grid = state.grid;
  const blocked = new Array(grid.width * grid.height).fill(0);
  grid.cells.forEach((occupants, cell) => {
    for (const targetId of occupants) {
      const target = grid.targets[targetId];
      if (gridx.isSolid(target) && (target.owner === 0 || !ignored.has(targetId))) {
        blocked[cell] = 1;
        break;
      }
    }
  });
  return blocked;
}

// 1 for every cell reached from either end of its row (or column) through cells that aren't blocked
export function clearLines(grid, blocked, axis) {
  const clear = new Array(blocked.length).fill(0);
  const count = axis === gridx.AXIS_ROW ? grid.height : grid.width;
  for (let line = 0; line < count; line++) {
    for (const side of [gridx.FROM_START, gridx.FROM_END]) {
      for (const cell of gridx.lineCells(grid, axis, line, side)) {
        if (blocked[cell]) {
          break;
        }
        clear[cell] = 1;
      }
    }
  }
  return clear;
}

// On an edge, or the neighbor beside it is clear along its row, or the neighbor above or below it is clear along its
// column
export function exposed(grid, rows, columns, cell) {
  const width = grid.width;
  const height = grid.height;
  const x = cell % width;
  const y = idiv(cell, width);
  if (x === 0 || y === 0 || x === width - 1 || y === height - 1) {
    return true;
  }
  return Boolean(rows[cell - 1] || rows[cell + 1] || columns[cell - width] || columns[cell + width]);
}

// Every live hit target in an exposed cell. In a cell holding an obstacle the check doesn't see through, only targets
// that are obstacles themselves count, not the cube under them
// (PixelGridController$$GetObjectsExposedToAnyGridEdgeAxisAligned, RVA 0x6644F40)
export function exposedTargets(state) {
  const grid = state.grid;
  const ignored = ignoredObstacles(state);
  const blocked = blockedCells(state, ignored);
  const rows = clearLines(grid, blocked, gridx.AXIS_ROW);
  const columns = clearLines(grid, blocked, gridx.AXIS_COLUMN);
  const targets = [];
  grid.cells.forEach((occupants, cell) => {
    if (!occupants.length || !exposed(grid, rows, columns, cell)) {
      return;
    }
    const here = occupants.map((targetId) => grid.targets[targetId]);
    const walled = here.some((t) => t.obstacle && t.owner !== 0 && !ignored.has(t.id));
    for (const target of here) {
      if (target.hittable && !target.dead && (!walled || (target.obstacle && target.owner !== 0))) {
        targets.push(target);
      }
    }
  });
  return targets;
}

// The name with the highest count, the earlier in order on a tie; null when every count is 0
export function mostCommon(counts, order) {
  let best = null;
  for (const name of order) {
    if ((counts[name] || 0) > 0 && (best === null || counts[name] > counts[best])) {
      best = name;
    }
  }
  return best;
}

// What a stuck fail is called (MapFailController$$TriggerBlockerFail, RVA 0x58E585C): with no tappable queue front,
// after the most common blocker at the queue fronts; else after the most common of U.F.O.s, curtains and spaceships on
// the grid; else the general obstacle fail
export function failName(state) {
  if (!tappableFrontExists(state)) {
    const counts = {};
    for (const pig of fronts(state)) {
      const name = frontBlocker(state, pig);
      if (name !== null) {
        counts[name] = (counts[name] || 0) + 1;
      }
    }
    const name = mostCommon(counts, FRONT_NAMES);
    if (name !== null) {
      return name;
    }
  }
  const gridCounts = {};
  for (const module of base.MODULES) {
    if (module.failCounts) {
      for (const [name, count] of Object.entries(module.failCounts(state))) {
        gridCounts[name] = (gridCounts[name] || 0) + count;
      }
    }
  }
  return mostCommon(gridCounts, GRID_NAMES) || "obstacles";
}

// Pigs on the map that carry ammo for the count, by id (ShooterProvider$$GetAllShootersByMaterial)
export function ammoPigs(state) {
  return livePigs(state).filter((pig) => !pig.tags.includes("disabled"));
}

// Hits still needed for this color: its cubes' health plus what shot features of that color still take
export function hitsLeft(state, color) {
  let total = 0;
  for (const target of state.grid.targets) {
    if (target.owner === 0 && !target.dead && target.color === color) {
      total += target.health;
    }
  }
  for (const module of base.MODULES) {
    if (module.remainingHits) {
      total += module.remainingHits(state, color);
    }
  }
  return total;
}

// [color, extra] for every color whose pigs carry more ammo than it has hits left, by color
// (MapFailController$$CheckShootersAndPixelsInSync, RVA 0x58E509C)
export function extraAmmo(state) {
  const ammo = new Map();
  for (const pig of ammoPigs(state)) {
    ammo.set(pig.color, (ammo.get(pig.color) || 0) + pig.ammo);
  }
  const extras = [];
  for (const color of [...ammo.keys()].sort((a, b) => a - b)) {
    const extra = ammo.get(color) - hitsLeft(state, color);
    if (extra > 0) {
      extras.push([color, extra]);
    }
  }
  return extras;
}

// Lowest on the screen first: the back rows of the queues, then the slot row, the exit line and the rescue row, then
// the belt. The original sorts by the pig's world z (MapController.<>c$$<SyncShootersAndPixels>b__74_1)
export function screenOrder(state, pig) {
  for (let index = 0; index < state.queues.length; index++) {
    const at = state.queues[index].indexOf(pig.id);
    if (at >= 0) {
      return [0, -at, index];
    }
  }
  if (pig.place === "belt") {
    return [2, 0, pig.id];
  }
  return [1, 0, pig.id];
}

// Compare two [a, b, c] sort keys
export function compareKeys(a, b) {
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) {
      return a[i] - b[i];
    }
  }
  return 0;
}

// Instead of failing, take the extra ammo away, lowest pigs first, and return the pigs left empty, after every pig
// already empty (MapController$$SyncShootersAndPixels, RVA 0x58D1F50). The core makes them vanish and then tries the
// auto-finisher
export function repair(state, extras) {
  const emptied = ammoPigs(state)
    .filter((pig) => pig.ammo === 0)
    .map((pig) => pig.id);
  for (const [color, extraStart] of extras) {
    let extra = extraStart;
    const pigs = ammoPigs(state).filter((pig) => pig.color === color);
    pigs.sort((a, b) => compareKeys(screenOrder(state, a), screenOrder(state, b)));
    for (const pig of pigs) {
      const take = Math.min(pig.ammo, extra);
      if (take === 0) {
        continue;
      }
      pig.ammo -= take;
      extra -= take;
      base.emit(state, "ammo_trimmed", { pig: pig.id, ammo: pig.ammo });
      if (pig.ammo === 0) {
        emptied.push(pig.id);
      }
    }
  }
  return emptied;
}

// Start the auto-finisher once the pigs left anywhere fit on the belt's trays (MapController$$TryActivateAutoFinisher,
// RVA 0x58CD8A0): from then on the belt runs twice as fast, pigs fire faster and trays loop instead of leaving
// (MapAutoFinisherController$$OnAutoFinisherActivated, RVA 0x58CB6D8). Features react through onAutofinish
export function tryAutofinish(state) {
  if (state.finishing || base.livePigCount(state) > state.trayTotal) {
    return;
  }
  state.finishing = true;
  base.emit(state, "autofinish", {});
  base.callHooks(state, "onAutofinish");
}
