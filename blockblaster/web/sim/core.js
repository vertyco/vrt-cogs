// One level's rules: a new state, the tick, taps and the checksum.
// The same level, seed and taps at the same ticks always give the same state. The bot runs common/sim/core.py, which
// mirrors this file function for function; both use whole numbers only so they agree bit for bit. The state records,
// timers and events live in base.js, which every module shares; this module ties the others together and none
// imports it.
import * as aim from "./aim.js";
import {
  FNV_START,
  MODULES,
  PHASE_BELT,
  PHASE_CHECKS,
  PHASE_FEATURES,
  PHASE_RELEASE,
  PHASE_SHOOT,
  PHASE_SHOTS,
  PHASE_TAPS,
  PLACES,
  callHooks,
  fireTimers,
  makePig,
  mix,
  mixText,
  registerTimer,
} from "./base.js";
import * as belt from "./belt.js";
import * as boosters from "./boosters.js";
import * as checks from "./checks.js";
import * as biscuit from "./features/biscuit.js";
import * as connected from "./features/connected.js";
import * as eggBox from "./features/egg_box.js";
import * as frozenPig from "./features/frozen_pig.js";
import * as gate from "./features/gate.js";
import * as hungryDoor from "./features/hungry_door.js";
import * as iceBlock from "./features/ice_block.js";
import * as locksKeys from "./features/locks_keys.js";
import * as pigPipe from "./features/pig_pipe.js";
import * as pixelPipe from "./features/pixel_pipe.js";
import * as rocket from "./features/rocket.js";
import * as snake from "./features/snake.js";
import * as surprisePig from "./features/surprise_pig.js";
import * as surprisePixel from "./features/surprise_pixel.js";
import * as wall from "./features/wall.js";
import * as woodHammer from "./features/wood_hammer.js";
import * as gridx from "./grid.js";
import { idiv } from "./mathx.js";
import * as places from "./places.js";
import { Rng } from "./rng.js";
import * as unicorn from "./unicorn.js";

// Every feature module, in feature-number order
MODULES.push(
  surprisePig,
  connected,
  locksKeys,
  gate,
  pixelPipe,
  surprisePixel,
  snake,
  wall,
  eggBox,
  pigPipe,
  iceBlock,
  woodHammer,
  frozenPig,
  hungryDoor,
  biscuit,
  rocket,
);

// board is board.json: beltPath holds its belt (points every 100 L along the lap, picture space), weapon the pig's
// shoot point in its own axes (L). belt holds the trays, newest first; a tray is {id, pos, started, pig}.
// unicornActive: the player has the Super Unicorn this level (the bot decides)
export function newState(level, seed, board, unicornActive = false) {
  const state = {
    level,
    seed,
    beltPath: board.belt,
    weapon: [...board.weapon],
    rng: new Rng(seed),
    grid: gridx.newGrid(level),
    tick: 0,
    seq: 0, // timer order among timers due at the same tick
    pigs: {},
    queues: [], // pig ids, front first
    slots: new Array(level.slotCount).fill(null),
    rescue: [],
    entrance: [], // [pig id, tick it fails at] waiting for a slot at the belt's exit, in order
    belt: [],
    trayTotal: level.conveyorLimit,
    traySeq: 0, // the next tray's id
    shooters: [], // pigs on started trays, in the order their trays started
    shots: [], // aim.makeShot records, in firing order
    timers: [], // [tick, seq, kind, args]
    events: [], // this tick's events, for the page to draw
    features: {}, // feature number -> that module's state
    cubesStart: level.cubes.length,
    cubesLeft: level.cubes.length,
    finishing: false, // the auto-finisher is running
    reviving: false, // a revive is working: the belt and the exit line wait and pigs can't be tapped
    over: null, // result(state)
    unicorn: unicorn.newUnicorn(level.cubes.length, unicornActive), // the Super Unicorn's bar
  };
  for (const queue of level.queues) {
    const ids = [];
    for (const [pigId, ammo, color] of queue) {
      state.pigs[pigId] = makePig(pigId, color, ammo, "queue");
      ids.push(pigId);
    }
    state.queues.push(ids);
  }
  // Pigs inside pipes exist from the start: other features list them
  pigPipe.addPigs(state);
  for (const module of MODULES) {
    module.setup(state);
  }
  // Hooks that read the finished picture (every module has put its parts on it by now)
  callHooks(state, "ready");
  return state;
}

// Placing pigs runs as a coroutine in the original, which resumes after every script's Update: its steps land at the
// end of a tick, so a tray started at tick T first moves at tick T + 1
registerTimer("hop", PHASE_RELEASE, places.hop);
registerTimer("tray_start", PHASE_RELEASE, belt.startTray);
registerTimer("win_check", PHASE_CHECKS, checks.winCheck);
// The revive is an async task in the original (UniTask, resumed at PlayerLoopTiming.Update before every script's
// Update), so its steps land at the start of a tick
registerTimer("revive_act", PHASE_TAPS, boosters.actRevive);
registerTimer("rescue_pig", PHASE_TAPS, boosters.rescuePig);
registerTimer("revive_done", PHASE_TAPS, boosters.endRevive);

// Timer: the stuck check; when it repairs instead of failing, the pigs it emptied vanish and the auto-finisher may
// start (MapController$$SyncShootersAndPixels, RVA 0x58D1F50)
export function stuckCheck(state, stage) {
  const emptied = checks.stuckCheck(state, stage);
  if (emptied === null) {
    return;
  }
  for (const pigId of emptied) {
    places.vanish(state, state.pigs[pigId], "repair");
  }
  checks.tryAutofinish(state);
}

registerTimer("stuck_check", PHASE_CHECKS, stuckCheck);

// Trays move, spacing, the fail-warning checkpoint, Conveyor Walls, pigs exit; then pigs waiting at the exit run out
// of time
export function moveBelt(state) {
  const [crossed, exited] = belt.moveTrays(state);
  for (const pigId of crossed) {
    places.checkpoint(state, pigId);
  }
  for (const pigId of exited) {
    places.lapEnd(state, pigId);
  }
  places.checkEntrance(state);
}

// Pigs fire, in the order their trays started; pigs that ran dry vanish
export function shoot(state) {
  for (const pigId of aim.stepShooting(state)) {
    places.vanish(state, state.pigs[pigId], "empty");
  }
}

// Shots in flight move and land, in firing order
export function moveShots(state) {
  aim.stepShots(state);
}

// Simulate tick state.tick, then move on to the next tick
export function step(state) {
  state.events = [];
  fireTimers(state, PHASE_TAPS);
  if (state.reviving) {
    // The belt stands still while a revive works (ConveyorController reads GameActionsPausedCondition, which holds
    // while Is Rescue Map Running is on); pigs on it still shoot
    places.holdEntrance(state);
  } else {
    moveBelt(state);
  }
  fireTimers(state, PHASE_BELT);
  shoot(state);
  fireTimers(state, PHASE_SHOOT);
  callHooks(state, "step");
  fireTimers(state, PHASE_FEATURES);
  moveShots(state);
  fireTimers(state, PHASE_SHOTS);
  // The win and stuck checks are timers of this phase
  fireTimers(state, PHASE_CHECKS);
  callHooks(state, "release");
  fireTimers(state, PHASE_RELEASE);
  state.tick += 1;
}

// Step until state.tick reaches tick or the level ends
export function runTo(state, tick) {
  while (state.tick < tick && state.over === null) {
    step(state);
  }
}

// Apply a tap at phase 1 of tick state.tick. Returns why it was refused, or null
export function applyTap(state, tap) {
  if (isTap(tap, "revive")) {
    return boosters.revive(state);
  }
  if (state.over !== null) {
    return "level over";
  }
  if (!Array.isArray(tap) || !tap.length) {
    return "bad tap";
  }
  if (isTap(tap, "tray")) {
    return boosters.applyTray(state);
  }
  if (isTap(tap, "shuffle")) {
    return boosters.applyShuffle(state);
  }
  if (tap[0] === "hand" && tap.length === 3 && Number.isInteger(tap[1]) && Number.isInteger(tap[2])) {
    return boosters.applyHand(state, tap[1], tap[2]);
  }
  if (tap[0] === "bomb" && tap.length === 3 && Number.isInteger(tap[1]) && Number.isInteger(tap[2])) {
    return boosters.applyBomb(state, tap[1], tap[2]);
  }
  if (tap[0] === "super" && tap.length === 3 && Number.isInteger(tap[1]) && Number.isInteger(tap[2])) {
    return boosters.applySuper(state, tap[1], tap[2]);
  }
  if (isTap(tap, "unicorn")) {
    return unicorn.use(state);
  }
  if (tap[0] === "q" && tap.length === 2 && Number.isInteger(tap[1])) {
    return places.tapFront(state, tap[1]);
  }
  if (tap[0] === "s" && tap.length === 2 && Number.isInteger(tap[1])) {
    return places.tapSlot(state, tap[1]);
  }
  if (tap[0] === "r" && tap.length === 2 && Number.isInteger(tap[1])) {
    return places.tapRescue(state, tap[1]);
  }
  return "not yet";
}

// A one-word tap such as ["tray"]
export function isTap(tap, word) {
  return Array.isArray(tap) && tap.length === 1 && tap[0] === word;
}

// The state as one number: tick, belt trays, pigs by id, queues, slots, rescue queue, cube totals, shots, the
// shooting, the exit line, the auto-finisher, the revive, the tray count, the Super Unicorn's bar when the player has
// it, then each feature's part in feature-number order
export function checksum(state) {
  let h = mix(FNV_START, state.tick);
  h = mix(h, state.belt.length);
  for (const tray of state.belt) {
    h = mix(mix(mix(mix(h, tray.id), tray.pos), tray.started ? 1 : 0), tray.pig === null ? -1 : tray.pig);
  }
  h = mixPigs(state, h);
  h = mixPlaces(state, h);
  h = mix(mix(h, state.cubesLeft), cubeHealth(state));
  h = mix(h, state.shots.length);
  for (const shot of state.shots) {
    h = mix(mix(mix(mix(mix(h, shot.pig), shot.target), shot.cell), shot.fired), shot.land);
  }
  h = mixShooting(state, h);
  h = mixWaiting(state, h);
  h = mix(mix(mix(h, state.finishing ? 1 : 0), state.reviving ? 1 : 0), state.trayTotal);
  if (state.unicorn.active) {
    h = mix(mix(h, state.unicorn.charge), state.unicorn.need);
  }
  for (const module of MODULES) {
    if (module.checksum) {
      h = module.checksum(state, h);
    }
  }
  return h;
}

export function mixPigs(state, h) {
  const pigIds = Object.keys(state.pigs)
    .map(Number)
    .sort((a, b) => a - b);
  h = mix(h, pigIds.length);
  for (const pigId of pigIds) {
    const pig = state.pigs[pigId];
    h = mix(mix(mix(mix(h, pig.id), pig.color), pig.ammo), PLACES.indexOf(pig.place));
    h = mix(h, pig.tags.length);
    for (const tag of pig.tags) {
      h = mixText(h, tag);
    }
  }
  return h;
}

// Queues, slots and the rescue queue
export function mixPlaces(state, h) {
  h = mix(h, state.queues.length);
  for (const queue of state.queues) {
    h = mix(h, queue.length);
    for (const pigId of queue) {
      h = mix(h, pigId);
    }
  }
  h = mix(h, state.slots.length);
  for (const pigId of state.slots) {
    h = mix(h, pigId === null ? -1 : pigId);
  }
  h = mix(h, state.rescue.length);
  for (const pigId of state.rescue) {
    h = mix(h, pigId);
  }
  return h;
}

// The shooters in order, every pig's fire timer and reservations, and every target's pending damage and claim
export function mixShooting(state, h) {
  h = mix(h, state.shooters.length);
  for (const pigId of state.shooters) {
    h = mix(h, pigId);
  }
  const pigIds = Object.keys(state.pigs)
    .map(Number)
    .sort((a, b) => a - b);
  for (const pigId of pigIds) {
    const pig = state.pigs[pigId];
    h = mix(mix(h, pig.nextFire), pig.reserved.length);
    for (const [targetId, cell] of pig.reserved) {
      h = mix(mix(h, targetId), cell);
    }
  }
  for (const target of state.grid.targets) {
    h = mix(mix(h, target.pending), target.claimed ? 1 : 0);
  }
  return h;
}

// Pigs waiting at the belt's exit, and when each pig can next be tapped
export function mixWaiting(state, h) {
  h = mix(h, state.entrance.length);
  for (const [pigId, failTick] of state.entrance) {
    h = mix(mix(h, pigId), failTick);
  }
  const pigIds = Object.keys(state.pigs)
    .map(Number)
    .sort((a, b) => a - b);
  for (const pigId of pigIds) {
    h = mix(h, state.pigs[pigId].freeAt);
  }
  return h;
}

// Hits still needed by every living cube
export function cubeHealth(state) {
  let total = 0;
  for (const target of state.grid.targets) {
    if (target.owner === 0 && !target.dead) {
      total += target.health;
    }
  }
  return total;
}

// null while the level runs, else {result, tick, kind, name}
export function result(state) {
  return state.over;
}

// Nothing moving: no tray on the belt, no pig waiting at its exit, no shot in flight, no timer pending
export function still(state) {
  return !state.belt.length && !state.entrance.length && !state.shots.length && !state.timers.length;
}

// Whole percent of the level's starting cubes destroyed (0 for a level with no cubes)
export function cleared(state) {
  if (state.cubesStart === 0) {
    return 0;
  }
  return idiv((state.cubesStart - state.cubesLeft) * 100, state.cubesStart);
}
