// Feature 4, Locks and Keys: a lock is a queue entry that never shoots and can't be tapped; a key on the picture opens
// one once the picture around it is cleared to the outside.
// A key is freed when any of its cells is reached by the edge flood and every cell is inside the grid; the key's own
// cells don't have to be clear (PixelGridController$$GetUnblockedAttachables, RVA 0x6645F68, called with its solid
// check off). The release check runs at the end of a tick after any hit, tap, vanish, booster or revive
// (ReleasablePixelGridAttachablesController: its handlers set a pending flag, LateUpdate RVA 0x578EAD8 clears it and
// runs ExecuteRelease RVA 0x578EB4C, which does nothing while the map is paused). Freed keys are taken in the level's
// order; each opens the leftmost lock that is first in its queue and not opened yet, and the first key with no such
// lock ends the check (LockKeyFeatureController$$OnReleasablesUnblocked, RVA 0x5681570). The lock is marked at once,
// the key flies to it for KEY_FLIGHT ticks, then the lock's entry vanishes and its queue moves up (KeyFeature$$Unlock,
// RVA 0x567F554; DetachInternal, RVA 0x567D744). common/sim/features/locks_keys.py mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";
import { KEY_FLIGHT } from "../numbers.js";
import * as places from "../places.js";

export const NUMBER = 4;

// Events after which the release check runs at the end of the tick: a target damaged, a pig tapped, a pig about to
// vanish, and the outside triggers (a booster or a revive finished, the walls removed)
const CHECK_AFTER = ["hit", "pig_tapped", "pig_vanishing", "booster_done", "revive_done", "walls_removed"];

// The locks, sorted left to right (queue columns stand left to right, and only a queue's first entry can be opened,
// so the order inside a queue never matters), and the keys' cells
export function setup(state) {
  const listed = state.level.features.Locks;
  const keys = state.level.features.keys;
  const lockIds = listed ? listed.Shooters.filter((pigId) => pigId in state.pigs) : [];
  const keyList = keys ? keys.Keys : [];
  if (!lockIds.length && !keyList.length) {
    return;
  }
  const locks = [];
  for (const queue of state.queues) {
    for (const pigId of queue) {
      if (lockIds.includes(pigId)) {
        locks.push(pigId);
      }
    }
  }
  for (const pigId of locks) {
    state.pigs[pigId].tags.push("disabled", "untappable");
  }
  const { grid } = state;
  const cells = [];
  const inside = [];
  for (const key of keyList) {
    const points = key.GridPoints.map((point) => [point.X, point.Y]);
    const valid = points.filter(([x, y]) => x >= 0 && x < grid.width && y >= 0 && y < grid.height);
    cells.push(valid.map(([x, y]) => gridx.cellOf(grid, x, y)));
    inside.push(valid.length === points.length);
  }
  state.features[NUMBER] = {
    locks,
    opened: [],
    cells,
    inside,
    used: new Array(keyList.length).fill(false),
    flights: [],
    pending: false,
  };
}

export function firstInQueue(state, pigId) {
  return state.queues.some((queue) => queue.length > 0 && queue[0] === pigId);
}

// The leftmost lock first in its queue and not opened yet (LockFeature$$IsAvailableToUnlock, RVA 0x5680B24)
export function freeLock(state) {
  const mine = state.features[NUMBER];
  for (const pigId of mine.locks) {
    if (!mine.opened.includes(pigId) && firstInQueue(state, pigId)) {
      return pigId;
    }
  }
  return null;
}

export function keyFree(state, index, reach) {
  const mine = state.features[NUMBER];
  return mine.inside[index] && mine.cells[index].some((cell) => reach[cell]);
}

// The key leaves the picture for its lock. Its leaving is another attachable change, so the release check runs again
// at the end of the next tick
export function unlock(state, index, lock) {
  const mine = state.features[NUMBER];
  mine.used[index] = true;
  mine.opened.push(lock);
  const land = state.tick + KEY_FLIGHT;
  mine.flights.push([index, lock, land]);
  mine.pending = true;
  base.schedule(state, KEY_FLIGHT, "lock_open", [index, lock]);
  base.emit(state, "key_unlock", { key: index, lock, land });
}

// Timer: the key has reached its lock, and the lock's entry vanishes
export function lockOpen(state, [index, lock]) {
  const mine = state.features[NUMBER];
  mine.flights = mine.flights.filter((flight) => flight[0] !== index);
  base.emit(state, "lock_opened", { key: index, lock });
  places.vanish(state, state.pigs[lock], "unlock");
}

base.registerTimer("lock_open", base.PHASE_FEATURES, lockOpen);

export function onEvent(state, name) {
  if (NUMBER in state.features && CHECK_AFTER.includes(name)) {
    state.features[NUMBER].pending = true;
  }
}

// End of tick: when something asked for it and the map isn't paused by a revive, every freed key in order opens the
// leftmost free lock, until a key finds none
export function release(state) {
  const mine = state.features[NUMBER];
  if (!mine || !mine.pending) {
    return;
  }
  mine.pending = false;
  if (state.reviving) {
    return;
  }
  const reach = gridx.reachOutside(state.grid);
  for (let index = 0; index < mine.used.length; index++) {
    if (mine.used[index] || !keyFree(state, index, reach)) {
      continue;
    }
    const lock = freeLock(state);
    if (lock === null) {
      return;
    }
    unlock(state, index, lock);
  }
}

// A key in flight holds the stuck check
export function busy(state) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.flights.length > 0;
}

export function blocker(state, pig) {
  const mine = state.features[NUMBER];
  if (mine && mine.locks.includes(pig.id)) {
    return "locked_out";
  }
  return null;
}

// The Locked Out revive: each lock first in its queue, queue by queue, takes the last key left, freed or not
// (MapRescueController.<UnlockFirstLocks>d__23$$MoveNext, RVA 0x58F5238), and the revive waits for the flights.
// Returns the ticks the revive waits: the flight, and one more so the locks have vanished when it ends
export function revive(state, name) {
  const mine = state.features[NUMBER];
  if (name !== "locked_out" || !mine) {
    return 0;
  }
  const keys = [];
  mine.used.forEach((used, index) => {
    if (!used) {
      keys.push(index);
    }
  });
  const fronts = state.queues.filter((queue) => queue.length && mine.locks.includes(queue[0])).map((queue) => queue[0]);
  let opened = 0;
  for (const lock of fronts) {
    if (!keys.length) {
      break;
    }
    unlock(state, keys.pop(), lock);
    opened += 1;
  }
  return opened ? KEY_FLIGHT + 1 : 0;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.opened.length);
  for (const pigId of mine.opened) {
    h = base.mix(h, pigId);
  }
  for (const used of mine.used) {
    h = base.mix(h, used ? 1 : 0);
  }
  h = base.mix(h, mine.flights.length);
  for (const [index, lock, land] of mine.flights) {
    h = base.mix(base.mix(base.mix(h, index), lock), land);
  }
  return base.mix(h, mine.pending ? 1 : 0);
}
