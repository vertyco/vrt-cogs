// Feature 13, Woods and Hammers: a hammer is a queue entry that never shoots; once it is first in its queue it jumps
// onto the weakest wood block on the picture and takes 1 off it.
// The controller tries a strike pass after any tap, any pig entering or leaving a queue, a booster or the Super Unicorn
// finishing and a revive finishing (WoodHammerFeatureController$$OnEnable, RVA 0x585CF70: every handler it subscribes
// calls TryToHitWoods, RVA 0x585D8E8, which does nothing once the woods are all broken or while the map is paused). A
// pass sorts the woods by health, lowest first (an insertion sort for so few, so ties keep the level's order), drops
// the ones marked broken, and every unused hammer first in its queue takes the first wood left, the k-th of the pass
// HAMMER_GAP x k ticks after the first (HitWoodsWithHammers, RVA 0x585D4BC; HammerFeature$$IsAvailableForHitting, RVA
// 0x5820C78). A strike that will take the wood's last health marks it broken at once, so the next hammer takes another
// (HammerFeature$$Hit, RVA 0x5822274: IsLethalDamage counts the strikes already on their way). Each hammer lifts for
// HAMMER_LIFT ticks and leaves its queue (TriggerRemoveShooterFromQueue: the queue closes up, which can start another
// pass), its damage lands STRIKE_LANDS ticks after its strike starts, and it is gone HAMMER_DONE ticks after it starts
// (DestroySelf -> MakeShooterDisappear). When no unbroken wood is left, every unused hammer vanishes, last listed
// first (CleanUpRemainingHammers, RVA 0x585DAB4).
// A Hand tap on a hammer runs a pass with only that hammer, which strikes even when it isn't first
// (OnTapShooterWithLogic, RVA 0x585D988). The tapped event comes after the tap's own work (MapController$$OnTapShooter,
// RVA 0x58D04A4), so the hammer is already used when the pass it starts looks. Wood is an obstacle: shots stop at it
// and the cubes under it can't be hit until it breaks, but the stuck check sees through it
// (IIgnoredObstacleAttachable). common/sim/features/wood_hammer.py mirrors this file.
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";
import { HAMMER_DONE, HAMMER_GAP, HAMMER_LIFT, STRIKE_LANDS } from "../numbers.js";
import * as places from "../places.js";

export const NUMBER = 13;

// Events after which a strike pass runs at once: a pig tapped, pigs entering or leaving a queue, and the outside
// triggers (a booster or the Super Unicorn finished, a revive finished)
const STRIKE_AFTER = ["pig_tapped", "queue_changed", "pigs_exit_queue", "booster_done", "revive_done"];

// The hammers in the level's order (a hammer inside a Pig Pipe too, so it comes out as a hammer), and every wood block
// standing on its cells as an obstacle, in file order
export function setup(state) {
  const listed = state.level.features.Hammers;
  const woods = state.level.features.pixelWoodBlocks;
  const hammers = listed ? listed.Shooters.filter((pigId) => pigId in state.pigs) : [];
  const blocks = woods ? woods.WoodBlocks : [];
  if (!hammers.length && !blocks.length) {
    return;
  }
  for (const pigId of hammers) {
    state.pigs[pigId].tags.push("disabled");
  }
  const { grid } = state;
  const records = [];
  for (const data of blocks) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const body = gridx.makeTarget(NUMBER, -1, data.Health, true, false);
    gridx.add(grid, body, cells);
    records.push({ target: body.id, start: data.Health, size: data.BlockSize, pending: 0 });
  }
  state.features[NUMBER] = {
    hammers,
    woods: records,
    broken: new Array(records.length).fill(false),
    used: [],
    strikes: [],
    active: records.length > 0,
  };
}

export function isHammer(state, pigId) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.hammers.includes(pigId);
}

export function firstInQueue(state, pigId) {
  return state.queues.some((queue) => queue.length > 0 && queue[0] === pigId);
}

// Unused and first in its queue (HammerFeature$$IsAvailableForHitting)
export function available(state, pigId) {
  return !state.features[NUMBER].used.includes(pigId) && firstInQueue(state, pigId);
}

// Wood indices by health, lowest first and the level's order on ties, without the ones marked broken
export function openWoods(state) {
  const mine = state.features[NUMBER];
  const health = (index) => state.grid.targets[mine.woods[index].target].health;
  const order = mine.woods.map((_, index) => index).sort((a, b) => health(a) - health(b) || a - b);
  return order.filter((index) => !mine.broken[index]);
}

// A strike pass over these hammers (TryToHitWoods, then HitWoodsWithHammers). Without force only available hammers
// strike. With no unbroken wood left, before or after, the leftover hammers vanish
export function tryStrikes(state, hammers, force) {
  const mine = state.features[NUMBER];
  if (!mine.active || state.reviving) {
    return;
  }
  const woods = openWoods(state);
  let count = 0;
  for (const pigId of hammers) {
    if (!woods.length) {
      break;
    }
    if (!force && !available(state, pigId)) {
      continue;
    }
    strike(state, pigId, woods[0], HAMMER_GAP * count);
    count += 1;
    if (mine.broken[woods[0]]) {
      woods.shift();
    }
  }
  if (!woods.length) {
    cleanUp(state);
  }
}

// One hammer takes this wood: it is used, the wood is marked broken now if this strike takes its last health, and
// its leave, damage and end are timed from its start, delay ticks from now
export function strike(state, pigId, index, delay) {
  const mine = state.features[NUMBER];
  const wood = mine.woods[index];
  const body = state.grid.targets[wood.target];
  mine.used.push(pigId);
  if (body.health - (wood.pending + 1) < 1) {
    mine.broken[index] = true;
  }
  wood.pending += 1;
  const start = state.tick + delay;
  mine.strikes.push([pigId, index, start]);
  base.schedule(state, delay + HAMMER_LIFT, "hammer_lift", pigId);
  base.schedule(state, delay + STRIKE_LANDS, "hammer_land", [pigId, index]);
  base.schedule(state, delay + HAMMER_DONE, "hammer_done", pigId);
  base.emit(state, "hammer_strike", { pig: pigId, wood: index, start });
}

// No unbroken wood is left: no more passes, and every unused hammer vanishes, last listed first
export function cleanUp(state) {
  const mine = state.features[NUMBER];
  mine.active = false;
  for (const pigId of [...mine.hammers].reverse()) {
    if (!mine.used.includes(pigId)) {
      places.vanish(state, state.pigs[pigId], "hammer");
    }
  }
}

// Timer: the lift is over and the hammer leaves its queue for the wood; the queue closes up
export function hammerLift(state, pigId) {
  const pig = state.pigs[pigId];
  if (pig.place !== "queue") {
    return;
  }
  const index = places.queueIndex(state, pig);
  const queue = places.takeOut(state, pig);
  pig.place = "held";
  if (queue >= 0) {
    base.emit(state, "pigs_exit_queue", { ids: [pigId], queues: [queue], indices: [index] });
  }
  checks.requestStuckCheck(state);
}

// Timer: the swing lands and the wood loses 1; at 0 it breaks and its cells are free at once
// (PixelWoodBlockFeature$$Damage)
export function hammerLand(state, [pigId, index]) {
  const mine = state.features[NUMBER];
  const wood = mine.woods[index];
  const body = state.grid.targets[wood.target];
  wood.pending = Math.max(0, wood.pending - 1);
  if (body.dead) {
    return;
  }
  body.health = Math.max(0, body.health - 1);
  base.emit(state, "hit", { target: body.id, cell: -1, health: body.health });
  base.emit(state, "wood_hit", { pig: pigId, wood: index, health: body.health });
  if (body.health > 0) {
    return;
  }
  body.dead = true;
  gridx.remove(state.grid, body);
  base.emit(state, "target_died", { target: body.id, owner: NUMBER });
  checks.requestWinCheck(state);
}

// Timer: the swing and the shrink are over and the hammer is gone
export function hammerDone(state, pigId) {
  const mine = state.features[NUMBER];
  mine.strikes = mine.strikes.filter((entry) => entry[0] !== pigId);
  places.vanish(state, state.pigs[pigId], "hammer");
}

base.registerTimer("hammer_lift", base.PHASE_FEATURES, hammerLift);
base.registerTimer("hammer_land", base.PHASE_FEATURES, hammerLand);
base.registerTimer("hammer_done", base.PHASE_FEATURES, hammerDone);

// A hammer can be tapped only with the Hand, and only before it has struck
export function canTap(state, pig, hand) {
  if (!isHammer(state, pig.id)) {
    return null;
  }
  if (!hand) {
    return "can't tap that";
  }
  if (state.features[NUMBER].used.includes(pig.id)) {
    return "busy";
  }
  return null;
}

// The Hand on a hammer: it strikes at once, first in its queue or not (HitWoodsWithHammer with force)
export function onTap(state, pig) {
  if (!isHammer(state, pig.id)) {
    return false;
  }
  tryStrikes(state, [pig.id], true);
  return true;
}

export function onEvent(state, name) {
  const mine = state.features[NUMBER];
  if (mine && STRIKE_AFTER.includes(name)) {
    tryStrikes(state, mine.hammers, false);
  }
}

// A hammer at work holds the stuck check (AnyHammerIsUsedCondition)
export function busy(state) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.strikes.length > 0;
}

// The stuck check sees through every standing wood block
export function ignoredObstacles(state) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return [];
  }
  return mine.woods.filter((wood) => !state.grid.targets[wood.target].dead).map((wood) => wood.target);
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.active ? 1 : 0);
  h = base.mix(h, mine.woods.length);
  mine.woods.forEach((wood, index) => {
    const body = state.grid.targets[wood.target];
    h = base.mix(base.mix(h, body.health), body.dead ? 1 : 0);
    h = base.mix(base.mix(h, wood.pending), mine.broken[index] ? 1 : 0);
  });
  h = base.mix(h, mine.used.length);
  for (const pigId of mine.used) {
    h = base.mix(h, pigId);
  }
  h = base.mix(h, mine.strikes.length);
  for (const [pigId, index, start] of mine.strikes) {
    h = base.mix(base.mix(base.mix(h, pigId), index), start);
  }
  return h;
}
