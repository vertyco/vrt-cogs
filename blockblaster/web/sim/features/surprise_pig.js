// Feature 1, the Surprise Pig: a pig drawn as a "?" until it is first in its queue.
// Hiding changes only what the page draws. A hidden pig's color and ammo are its listed values the whole time, so no
// rule reads the hidden list; it exists so the bot and the page agree on what is drawn (SurpriseShooterFeature$$Reveal,
// RVA 0x57FBA34). A pig is revealed when it is first in its queue after any queue change, booster or revive
// (SurpriseShooterFeatureController$$HandleFirstShooterReveal, RVA 0x57FBE60), and forced when it goes on the belt or
// vanishes. common/sim/features/surprise_pig.py mirrors this file.
import * as base from "../base.js";

export const NUMBER = 1;

// Events after which the first pig of every queue is revealed
const REVEAL_AFTER = ["pigs_exit_queue", "queue_changed", "booster_done", "revive_done"];

// The listed pigs start hidden, except the ones already first in their queues
export function setup(state) {
  const listed = state.level.features.SurpriseShooters;
  if (!listed) {
    return;
  }
  const hidden = listed.Shooters.filter((pigId) => pigId in state.pigs);
  state.features[NUMBER] = { hidden };
  for (const queue of state.queues) {
    const at = queue.length ? hidden.indexOf(queue[0]) : -1;
    if (at >= 0) {
      hidden.splice(at, 1);
    }
  }
}

// Every pig the level lists carries the feature, hidden or already revealed, so Shuffle leaves it where it is
export function pins(state, pigId) {
  const listed = state.level.features.SurpriseShooters;
  return Boolean(listed) && listed.Shooters.includes(pigId);
}

// Show a hidden pig's real color and number
export function reveal(state, pigId) {
  const { hidden } = state.features[NUMBER];
  const at = hidden.indexOf(pigId);
  if (at >= 0) {
    hidden.splice(at, 1);
    base.emit(state, "pig_revealed", { pig: pigId });
  }
}

export function revealFronts(state) {
  for (const queue of state.queues) {
    if (queue.length) {
      reveal(state, queue[0]);
    }
  }
}

export function onEvent(state, name, data) {
  if (!(NUMBER in state.features)) {
    return;
  }
  if (name === "pigs_placed") {
    for (const pigId of data.ids) {
      reveal(state, pigId);
    }
  } else if (REVEAL_AFTER.includes(name)) {
    revealFronts(state);
  }
}

// A pig that vanishes is revealed first. It never takes the vanish over
export function takeVanish(state, pig) {
  if (NUMBER in state.features) {
    reveal(state, pig.id);
  }
  return false;
}

export function checksum(state, h) {
  if (!(NUMBER in state.features)) {
    return h;
  }
  const { hidden } = state.features[NUMBER];
  h = base.mix(h, hidden.length);
  for (const pigId of hidden) {
    h = base.mix(h, pigId);
  }
  return h;
}
