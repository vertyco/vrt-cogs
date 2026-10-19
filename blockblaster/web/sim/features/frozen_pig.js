// Feature 14, the Frozen Pig: a real pig in a queue, wrapped in ice that only other pigs running dry can melt.
// Every pig that vanishes (runs dry, including into a U.F.O. seat or spaceship) takes 1 off every frozen pig, unless it
// is a disabled entry such as a hammer, a lock or a pipe; shots and cubes don't count
// (ShooterIceBlockFeatureController$$OnShooterWillDisappear, RVA 0x57A10BC). It is raised before the vanish is handled,
// so it runs for every pig whether or not a feature then takes the vanish over. A frozen pig can't be tapped; the Hand
// can, and then does 1 to that one ice (OnTapShooterWithLogic, RVA 0x57A0C9C). At 0 the ice shatters and it is a normal
// pig, tappable when first in its queue (DestroyIce, RVA 0x579C910). A frozen pig keeps its ammo and counts as a live
// pig. When no queue front can be tapped and the most common blocker at the fronts is a frozen pig the level fails
// "Frozen!"; its revive shatters the frozen pigs standing first in their queues (ShatterFirstIceBlocks).
// common/sim/features/frozen_pig.py mirrors this file.
import * as base from "../base.js";
import * as checks from "../checks.js";

export const NUMBER = 14;

// Every frozen pig as a record, in file order, with the ice it starts with. A pig inside a Pig Pipe is frozen from the
// start too (the pipe adds its pigs before the modules run)
export function setup(state) {
  const listed = state.level.features.ShooterIceBlocks;
  if (!listed || !listed.IceBlocks.length) {
    return;
  }
  const ice = listed.IceBlocks.filter((data) => data.ShooterId in state.pigs).map((data) => ({
    pig: data.ShooterId,
    start: data.Health,
    health: data.Health,
  }));
  if (ice.length) {
    state.features[NUMBER] = { ice };
  }
}

// The pig's ice while it still has some, else null
export function record(state, pigId) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return null;
  }
  return mine.ice.find((entry) => entry.pig === pigId && entry.health > 0) || null;
}

// The ice loses some health; at 0 it shatters and the pig can be tapped. The ice is gone at once, the page draws the
// shatter
function damage(state, entry, why, amount = 1) {
  entry.health = Math.max(0, entry.health - amount);
  base.emit(state, "frozen_hit", { pig: entry.pig, health: entry.health, why });
  if (entry.health > 0) {
    return;
  }
  base.emit(state, "frozen_thaw", { pig: entry.pig, why });
  checks.requestStuckCheck(state);
}

// A pig is about to vanish: every frozen pig takes 1 off, unless this one is a disabled entry. Never takes the vanish
// over
export function takeVanish(state, pig) {
  const mine = state.features[NUMBER];
  if (!mine || pig.tags.includes("disabled")) {
    return false;
  }
  for (const entry of mine.ice) {
    if (entry.health > 0) {
      damage(state, entry, "vanish");
    }
  }
  return false;
}

// Every pig the level lists carries the feature, frozen or thawed, so Shuffle leaves it where it is
export function pins(state, pigId) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.ice.some((entry) => entry.pig === pigId);
}

// A frozen pig can be tapped only with the Hand
export function canTap(state, pig, hand) {
  if (record(state, pig.id) === null || hand) {
    return null;
  }
  return "frozen";
}

// The Hand on a frozen pig: 1 off its ice, and the pig stays where it is
export function onTap(state, pig, hand) {
  const entry = record(state, pig.id);
  if (entry === null || !hand) {
    return false;
  }
  damage(state, entry, "hand");
  return true;
}

export function blocker(state, pig) {
  return record(state, pig.id) === null ? null : "frozen";
}

// The Frozen! revive shatters the ice of every frozen pig first in its queue, queue by queue. Returns the ticks the
// revive waits (none)
export function revive(state, name) {
  if (name !== "frozen" || !state.features[NUMBER]) {
    return 0;
  }
  for (const queue of state.queues) {
    const entry = queue.length ? record(state, queue[0]) : null;
    if (entry !== null) {
      damage(state, entry, "revive", entry.health);
    }
  }
  return 0;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.ice.length);
  for (const entry of mine.ice) {
    h = base.mix(base.mix(h, entry.pig), entry.health);
  }
  return h;
}
