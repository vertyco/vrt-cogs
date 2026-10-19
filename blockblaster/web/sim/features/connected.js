// Feature 2, the Connected Pig: pigs tied together go on the belt together, ride together and leave together.
// Tapping any member places the whole group, in group order, or nothing: every member needs a free tray and must be
// free to go (ConnectedShooterCanTapCondition$$CheckWithReason, RVA 0x55D5438). A member that runs dry rides on showing
// 0 and keeps its tray while any member still has ammo (ConnectedShooterCanDisappearCondition$$Call, RVA 0x55D3FAC);
// when one member leaves, every member leaves (ConnectedShooterFeatureController$$TryToMakeConnectedShootersDisappear,
// RVA 0x55EB548). While the auto-finisher runs a member's tray loops only while the whole group is on the belt
// (ConveyorStayInInfiniteLoopCondition$$CheckConnectedShooter, RVA 0x5907E30). common/sim/features/connected.py
// mirrors this file.
import * as base from "../base.js";
import * as places from "../places.js";

export const NUMBER = 2;

// The level's groups, each a list of pig ids linked first to last, and the groups that have left
export function setup(state) {
  const listed = state.level.features.ConnectedShooters;
  if (!listed) {
    return;
  }
  const groups = [];
  for (const connection of listed.Connections) {
    const members = connection.Shooters.filter((pigId) => pigId in state.pigs);
    if (members.length >= 2) {
      groups.push(members);
    }
  }
  if (groups.length) {
    state.features[NUMBER] = { groups, left: [] };
  }
}

// The index of the group holding this pig, or -1
export function groupIndex(state, pigId) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return -1;
  }
  return mine.groups.findIndex((members) => members.includes(pigId));
}

// A pig in a group carries the feature, so Shuffle leaves it where it is
export function pins(state, pigId) {
  return groupIndex(state, pigId) >= 0;
}

// The pigs a tap on this pig places, in placing order (ShooterProvider$$GetShootersToPlaceToConveyor, RVA 0x58F989C),
// or null for a pig in no group
export function group(state, pig) {
  const index = groupIndex(state, pig.id);
  if (index < 0) {
    return null;
  }
  return [...state.features[NUMBER].groups[index]];
}

// The Super Unicorn merges a pig with its group: the members, or null for a pig in no group
export function mergeLinks(state, pig) {
  return group(state, pig);
}

// The level queue holding this pig (MapProvider$$GetMapQueueOfShooter), or null in a slot, the rescue queue or on the
// belt
export function queueOf(state, pigId) {
  for (const queue of state.queues) {
    if (queue.includes(pigId)) {
      return queue;
    }
  }
  return null;
}

// A member in a queue is blocked when any pig in front of it is not in its group
// (IConnectedShooterFeature$$IsShooterBlockedInFront, RVA 0x55D50E0). Members in slots or the rescue queue never are
export function blockedInFront(state, pigId, members) {
  const queue = queueOf(state, pigId);
  if (queue === null) {
    return false;
  }
  return queue.slice(0, queue.indexOf(pigId)).some((other) => !members.includes(other));
}

// The other tap conditions the group check runs on every member (its connectedMixCanTapConditions): a non-tappable
// feature on it, or another feature against it
export function otherRulesRefuse(state, pig, hand) {
  if (pig.tags.includes("untappable")) {
    return true;
  }
  for (const module of base.MODULES) {
    if (!module.canTap || module.canTap === canTap) {
      continue;
    }
    const reason = module.canTap(state, pig, hand);
    if (reason !== null && reason !== undefined) {
      return true;
    }
  }
  return false;
}

// One member's part of the group check, in the original's order: busy (mid-hop), the other tap conditions, then with
// the Hand on any member in a queue goes and a member outside one doesn't; without it a member mustn't be blocked in
// its queue or already on the belt
export function memberRefused(state, pigId, members, hand) {
  const pig = state.pigs[pigId];
  if (state.tick < pig.freeAt || otherRulesRefuse(state, pig, hand)) {
    return true;
  }
  const inQueue = queueOf(state, pigId) !== null;
  if (hand) {
    return !inQueue;
  }
  return blockedInFront(state, pigId, members) || pig.place === "belt";
}

// The whole group must fit on the belt, one free tray a member, and every member must be free to go
export function canTap(state, pig, hand) {
  const members = group(state, pig);
  if (members === null) {
    return null;
  }
  if (state.trayTotal - state.belt.length < members.length) {
    return "belt full";
  }
  for (const pigId of members) {
    if (memberRefused(state, pigId, members, hand)) {
      return "group blocked";
    }
  }
  return null;
}

// The stuck check's version (ConnectedShooterIsUnblockedCondition$$CheckWithReason, RVA 0x55D5DBC): every member
// passes the other tap conditions and none is blocked in its queue. The belt being full doesn't matter
export function canTapNormally(state, pig) {
  const members = group(state, pig);
  if (members === null) {
    return null;
  }
  for (const pigId of members) {
    if (otherRulesRefuse(state, state.pigs[pigId], false) || blockedInFront(state, pigId, members)) {
      return "group blocked";
    }
  }
  return null;
}

export function hasAmmo(state, members) {
  return members.some((pigId) => state.pigs[pigId].ammo >= 1);
}

// A member can't leave while any member of its group still has ammo: it rides on showing 0 and keeps its tray
export function takeVanish(state, pig) {
  const members = group(state, pig);
  return members !== null && hasAmmo(state, members);
}

// When one member is about to leave, every other member leaves too, in group order
export function onEvent(state, name, data) {
  if (name !== "pig_vanishing" || !(NUMBER in state.features)) {
    return;
  }
  const index = groupIndex(state, data.pig);
  const mine = state.features[NUMBER];
  if (index < 0 || mine.left.includes(index)) {
    return;
  }
  mine.left.push(index);
  for (const pigId of mine.groups[index]) {
    if (pigId !== data.pig) {
      places.vanish(state, state.pigs[pigId], data.cause);
    }
  }
}

// While the auto-finisher runs, a member's tray loops only while every member of its group is on the belt
export function keepLooping(state, pig) {
  const members = group(state, pig);
  return members === null || members.every((pigId) => state.pigs[pigId].place === "belt");
}

export function checksum(state, h) {
  if (!(NUMBER in state.features)) {
    return h;
  }
  const { left } = state.features[NUMBER];
  h = base.mix(h, left.length);
  for (const index of left) {
    h = base.mix(h, index);
  }
  return h;
}
