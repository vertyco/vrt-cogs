// Boosters and the revive.
// A booster's pick and animation happen on the page with its clock stopped, so its whole effect lands in the one tap
// that applies it. The revive is the bot's tap after a fail: the map pauses (the belt stands still, the exit line's
// grace stops counting and pigs can't be tapped) while it works, then play goes on. common/sim/boosters.py mirrors
// this file.
import * as aim from "./aim.js";
import * as base from "./base.js";
import * as belt from "./belt.js";
import * as checks from "./checks.js";
import * as gridx from "./grid.js";
import { BOMB_DAMAGE, BOMB_SIZE, HOP, REVIVE_DELAY, REVIVE_GAP, SHOT_DAMAGE } from "./numbers.js";
import * as places from "./places.js";

// The Tray booster: one more tray on the belt for the rest of the level (TrayPowerupController.<ExecutePowerup>
// d__14$$MoveNext, RVA 0x52CB220, -> ConveyorController$$AddSlot, RVA 0x58AA75C). The booster buttons only work while
// the auto-finisher isn't running (resources #9814). Returns why it was refused, or null
export function applyTray(state) {
  if (state.finishing) {
    return "auto-finisher running";
  }
  state.trayTotal += 1;
  base.emit(state, "tray_added", { trays: state.trayTotal });
  return null;
}

// The Hand booster's pick: that one pig is taken from anywhere in its queue and placed on the belt like a front pig
// (HandPowerupController$$PerformPowerup, RVA 0x52D9F80; CanTapShooterCondition$$CheckMainConditions, RVA 0x58B3258,
// rule 2: with the Hand on any queue pig can be tapped, and only the busy, belt-full and feature rules still apply). A
// feature's own tap (a hammer, frozen block or mallet) runs through its onTap with `hand` true. The buttons only work
// while the auto-finisher isn't running. Returns why it was refused, or null
export function applyHand(state, queue, index) {
  if (state.finishing) {
    return "auto-finisher running";
  }
  if (queue < 0 || queue >= state.queues.length) {
    return "no such queue";
  }
  if (index < 0 || index >= state.queues[queue].length) {
    return "no such pig";
  }
  return places.tapPig(state, state.pigs[state.queues[queue][index]], true);
}

// True for a pig with any feature on it: a tag, or a feature module that lists it (ShooterCanShuffleCondition$$Call, RVA
// 0x5905C38, lets only pigs with no feature through)
export function featurePinned(state, pig) {
  if (pig.tags.length) {
    return true;
  }
  return base.MODULES.some((module) => module.pins && module.pins(state, pig.id));
}

// [queue, index] of every plain pig, queue by queue, front to back
export function shuffleSpots(state) {
  const spots = [];
  state.queues.forEach((queue, queueIndex) => {
    queue.forEach((pigId, index) => {
      if (!featurePinned(state, state.pigs[pigId])) {
        spots.push([queueIndex, index]);
      }
    });
  });
  return spots;
}

// Shuffling needs at least two plain pigs, else nothing could move
export function canShuffle(state) {
  return shuffleSpots(state).length >= 2;
}

// The Shuffle booster: the plain pigs of every queue are pooled front to back, shuffled with a Fisher-Yates loop (i from
// n - 1 down to 1, k from 0 to i) on the level's seeded generator, and refilled into the same spots in the same order,
// so queue lengths and every featured pig stay as they were (MapController$$ShuffleQueues, RVA 0x58CB924). Features
// react to booster_done (a Surprise pig that is now first is revealed). Returns why it was refused, or null
export function applyShuffle(state) {
  if (state.finishing) {
    return "auto-finisher running";
  }
  const spots = shuffleSpots(state);
  if (spots.length < 2) {
    return "nothing to shuffle";
  }
  const pool = spots.map(([queue, index]) => state.queues[queue][index]);
  for (let i = pool.length - 1; i > 0; i--) {
    const k = state.rng.randInt(i + 1);
    [pool[i], pool[k]] = [pool[k], pool[i]];
  }
  const moved = [];
  spots.forEach(([queue, index], at) => {
    if (state.queues[queue][index] !== pool[at]) {
      state.queues[queue][index] = pool[at];
      moved.push(pool[at]);
    }
  });
  base.emit(state, "shuffled", { ids: moved });
  base.emit(state, "booster_done", { name: "shuffle" });
  return null;
}

// The cells a bomb on (x, y) covers, in the original's order: the BOMB_SIZE full rows through y from the lowest, each
// left to right, then the BOMB_SIZE full columns through x from the left, each bottom to top, skipping cells a row
// already listed (CrossSelectionShape.<GetAbsolutePositions>d__3$$MoveNext, RVA 0x553B294)
export function bombCells(state, x, y) {
  const grid = state.grid;
  const half = (BOMB_SIZE > 0 ? BOMB_SIZE - 1 : BOMB_SIZE) >> 1;
  const cells = [];
  const seen = new Set();
  for (let offset = -half; offset <= half; offset++) {
    const row = y + offset;
    if (row >= 0 && row < grid.height) {
      for (let column = 0; column < grid.width; column++) {
        const cell = gridx.cellOf(grid, column, row);
        if (!seen.has(cell)) {
          seen.add(cell);
          cells.push(cell);
        }
      }
    }
  }
  for (let offset = -half; offset <= half; offset++) {
    const column = x + offset;
    if (column >= 0 && column < grid.width) {
      for (let row = 0; row < grid.height; row++) {
        const cell = gridx.cellOf(grid, column, row);
        if (!seen.has(cell)) {
          seen.add(cell);
          cells.push(cell);
        }
      }
    }
  }
  return cells;
}

// Everything a bomb on (x, y) damages: each living hittable target on the cross once, in cell order, cubes before the
// cell's features (DemolishPowerupController.<ExecutePowerup>d__25$$MoveNext, RVA 0x52DF4A0, gives each one a
// DamageInfo of 1). A big cube standing on several cells of the cross takes one hit
export function bombTargets(state, x, y) {
  const found = [];
  const seen = new Set();
  for (const cell of bombCells(state, x, y)) {
    for (const target of gridx.at(state.grid, cell)) {
      if (target.hittable && !target.dead && !seen.has(target.id)) {
        seen.add(target.id);
        found.push(target);
      }
    }
  }
  return found;
}

// The Demolish booster: every damageable thing on the cross through cell (x, y) takes 1 hit at once (the page shows the
// bomb's drop first, with the clock held). A pick with nothing to hit is refused and costs nothing. The stuck check
// starts again, as it does when the last shot in flight ends. Returns why it was refused, or null
export function applyBomb(state, x, y) {
  if (state.finishing) {
    return "auto-finisher running";
  }
  const grid = state.grid;
  if (x < 0 || x >= grid.width || y < 0 || y >= grid.height) {
    return "no such cell";
  }
  const targets = bombTargets(state, x, y);
  if (!targets.length) {
    return "nothing to blow up";
  }
  base.emit(state, "bombed", { x, y, hits: targets.length });
  for (const target of targets) {
    aim.hit(state, target, BOMB_DAMAGE, null);
  }
  checks.requestStuckCheck(state);
  base.emit(state, "booster_done", { name: "bomb" });
  return null;
}

// True for a cube a feature module hides (a Surprise Pixel not yet revealed): the Super Shooter skips it
export function cubeHidden(state, cube) {
  for (const module of base.MODULES) {
    if (module.hidesCube && module.hidesCube(state, cube)) {
      return true;
    }
  }
  return false;
}

// A living cube the Super Shooter may shoot: no obstacle stands on any of its cells and it isn't a hidden Surprise Pixel
// (the powerup's isPixelViableConditions, read from SuperShooterPowerupController, RVA 0x52CD9C4)
export function superViable(state, cube) {
  if (cube.owner !== 0 || cube.dead || !cube.hittable || !cube.cells.length) {
    return false;
  }
  for (const cell of cube.cells) {
    for (const target of gridx.at(state.grid, cell)) {
      if (target.obstacle && !target.dead) {
        return false;
      }
    }
  }
  return !cubeHidden(state, cube);
}

// Every cube the Super Shooter hits for a pick on (x, y): the picked cube's color, row by row from the lowest, each row
// left to right, a big cube once at its first cell (SameMaterialSelectionShape.<GetAbsolutePositions>d__11$$MoveNext,
// RVA 0x553E988, and the HashSet in <ShootPixels>, RVA 0x52D4D5C). A picked cell with no cube, or whose cube fails the
// viability check, selects nothing
export function superTargets(state, x, y) {
  const grid = state.grid;
  if (x < 0 || x >= grid.width || y < 0 || y >= grid.height) {
    return [];
  }
  const picked = gridx.at(grid, gridx.cellOf(grid, x, y)).find((target) => target.owner === 0 && !target.dead);
  if (!picked || !superViable(state, picked)) {
    return [];
  }
  const found = [];
  const seen = new Set();
  for (let row = 0; row < grid.height; row++) {
    for (let column = 0; column < grid.width; column++) {
      for (const target of gridx.at(grid, gridx.cellOf(grid, column, row))) {
        if (target.owner !== 0 || target.dead || target.color !== picked.color || seen.has(target.id)) {
          continue;
        }
        seen.add(target.id);
        if (superViable(state, target)) {
          found.push(target);
        }
      }
    }
  }
  return found;
}

// The Super Shooter booster: every viable cube of the picked cube's color takes one shot, in row order from the bottom,
// all at once in this tap (the page plays the volley with the clock held). A pick with nothing to shoot is refused and
// costs nothing. The stuck check starts again, as when the last shot in flight ends. Returns why it was refused, or null
export function applySuper(state, x, y) {
  if (state.finishing) {
    return "auto-finisher running";
  }
  const grid = state.grid;
  if (x < 0 || x >= grid.width || y < 0 || y >= grid.height) {
    return "no such cell";
  }
  const targets = superTargets(state, x, y);
  if (!targets.length) {
    return "nothing to shoot";
  }
  base.emit(state, "super_shot", { x, y, color: targets[0].color, ids: targets.map((target) => target.id) });
  for (const target of targets) {
    aim.hit(state, target, SHOT_DAMAGE, null);
  }
  checks.requestStuckCheck(state);
  base.emit(state, "booster_done", { name: "super" });
  return null;
}

// The revive after a fail: the fail is taken back and the map pauses. Its work starts REVIVE_DELAY ticks later
// (MapRescueController.<RescueMap>d__19$$MoveNext, RVA 0x58F27C4: Is Rescue Map Running on, then rescueMapDelay 0.2 s,
// level3 #1051). Returns why it was refused, or null
export function revive(state) {
  if (state.over === null || state.over.result !== "failed") {
    return "not failed";
  }
  if (state.reviving) {
    return "reviving";
  }
  const name = state.over.name;
  state.over = null;
  state.reviving = true;
  base.emit(state, "revive_started", { name });
  base.schedule(state, REVIVE_DELAY, "revive_act", name);
  return null;
}

// Timer: the revive's work for the fail it took back, then the revive ends once that work is done (RescueMap runs one
// task per fail and waits for all of them). Out of space moves pigs to the rescue queue; every other fail is handled
// by the feature modules' revive hooks, each returning the ticks its work takes (RescueMapEventArgs, dump.cs:199338)
export function actRevive(state, name) {
  let done = 0;
  if (name === "out_of_space") {
    const moved = rescueOutOfSpace(state);
    moved.forEach((entry, index) => {
      base.schedule(state, REVIVE_GAP * index, "rescue_pig", entry);
    });
    // Each pig's hop to the rescue row takes HOP ticks; the revive ends when the last one lands
    done = moved.length ? REVIVE_GAP * (moved.length - 1) + HOP : 0;
  } else {
    for (const module of base.MODULES) {
      if (module.revive) {
        done = Math.max(done, module.revive(state, name));
      }
    }
  }
  base.schedule(state, done, "revive_done", name);
}

// Take every slot pig, rearmost first, then the pigs waiting at the belt's exit, then every pig on the belt out of
// their places at once (MapRescueController.<RescueOutOfSpace>d__20$$MoveNext, RVA 0x58F351C: GetFilledMapSlots from
// the back, GetStrayShooters, GetShootersInConveyor; the offer frees every slot and the belt). The last two come in
// the map's shooter list order, which the pig ids stand in for. Returns [pig id, where it was] in the order they join
// the rescue queue
export function rescueOutOfSpace(state) {
  const moved = [];
  for (let slot = state.slots.length - 1; slot >= 0; slot--) {
    const pigId = state.slots[slot];
    if (pigId !== null) {
      state.slots[slot] = null;
      moved.push([pigId, "slot"]);
    }
  }
  const waiting = state.entrance.map((entry) => entry[0]).sort((a, b) => a - b);
  for (const pigId of waiting) {
    moved.push([pigId, "exit"]);
  }
  state.entrance = [];
  const pigIds = Object.keys(state.pigs)
    .map(Number)
    .sort((a, b) => a - b);
  for (const pigId of pigIds) {
    if (state.pigs[pigId].place === "belt") {
      belt.remove(state, pigId);
      moved.push([pigId, "belt"]);
    }
  }
  for (const [pigId] of moved) {
    state.pigs[pigId].place = "rescue";
  }
  return moved;
}

// Timer: a pig joins the back of the rescue queue and hops there; it can't be tapped until it lands
// (MapRescueController$$RescueShooter, RVA 0x58EA538: ShooterQueueController$$Enqueue, then a default 0.25 s jump).
// Pigs follow each other rescueMapJumpInterval 0.05 s apart
export function rescuePig(state, entry) {
  const [pigId, origin] = entry;
  const pig = state.pigs[pigId];
  if (pig.place !== "rescue") {
    return;
  }
  state.rescue.push(pigId);
  pig.freeAt = state.tick + HOP;
  base.emit(state, "to_rescue", { pig: pigId, index: state.rescue.length - 1, from: origin });
}

// Timer: the revive is over and the map runs again; pigs waiting at the exit take any free slots
// (MapEvents$$TriggerRescueMapFinished -> SlotEntranceQueueController$$OnRescueMapFinished). Features react to
// revive_done (the next Surprise pig is revealed)
export function endRevive(state, name) {
  state.reviving = false;
  places.drainEntrance(state);
  base.emit(state, "revive_done", { name });
}
