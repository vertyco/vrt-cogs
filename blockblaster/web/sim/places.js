// Where pigs wait, taps that send them onto the belt, the slots, the end of a lap and vanishing.
// A pig that reaches the end of a lap with ammo left drops into the leftmost free slot. With none free it waits in the
// line at the belt's exit (SlotEntranceQueueController), and if no slot opens in time the level fails "Out of space".
// common/sim/places.py mirrors this file.
import * as base from "./base.js";
import * as belt from "./belt.js";
import * as checks from "./checks.js";
import { HOP, HOP_GAP, PLACE_WAIT, SLOT_GRACE, TRAY_START_GAP } from "./numbers.js";

// A tap on a queue's front pig. Returns why it was refused, or null
export function tapFront(state, queue) {
  if (queue < 0 || queue >= state.queues.length) {
    return "no such queue";
  }
  if (!state.queues[queue].length) {
    return "queue empty";
  }
  return tapPig(state, state.pigs[state.queues[queue][0]], false);
}

// A tap on a slot's pig: it goes round again, placed like a queue front. Returns why it was refused, or null
export function tapSlot(state, slot) {
  if (slot < 0 || slot >= state.slots.length) {
    return "no such slot";
  }
  if (state.slots[slot] === null) {
    return "slot empty";
  }
  return tapPig(state, state.pigs[state.slots[slot]], false);
}

// A tap on a pig in the rescue queue. It isn't one of the level's queues, so any of its pigs can be tapped, not only
// the front one (MapProvider$$IsShooterFirstInMapQueue, RVA 0x58F7858, is false for it and the slot-pig rule lets it
// pass). Returns why it was refused, or null
export function tapRescue(state, index) {
  if (index < 0 || index >= state.rescue.length) {
    return "no such rescue pig";
  }
  return tapPig(state, state.pigs[state.rescue[index]], false);
}

// The tap check, then a feature's own tap or placing the pig, or its whole Connected group, on the belt (whose first
// steps, up to its one-frame wait, run at once), then the tapped event (MapController$$OnTapShooter, RVA 0x58D04A4:
// ExecuteTap, then MapEvents' TriggerShooterTapped). `hand` is true for the Hand booster's pick
export function tapPig(state, pig, hand) {
  const reason = tapCheck(state, pig, hand);
  if (reason !== null) {
    return reason;
  }
  let result = null;
  if (!base.MODULES.some((module) => module.onTap && module.onTap(state, pig, hand))) {
    result = placeBatch(state, batchOf(state, pig));
  }
  base.emit(state, "pig_tapped", { pig: pig.id });
  return result;
}

// The pigs a tap on this pig sends onto the belt: its Connected group in group order, or the pig alone
export function batchOf(state, pig) {
  for (const module of base.MODULES) {
    if (module.group) {
      const members = module.group(state, pig);
      if (members !== null) {
        return members;
      }
    }
  }
  return [pig.id];
}

// The tap rules (CanTapShooterCondition$$CheckMainConditions, RVA 0x58B3258): not while a revive works
// (ShooterTapDisabledCondition, sharedassets3 #422, reads Is Rescue Map Running), not on the belt or mid-hop
// (Shooter$$get_IsBusy), a free tray, and no feature against it. The caller has already applied the position rules (the
// front of a queue, or any queue pig with the Hand), so `hand` only reaches the features
export function tapCheck(state, pig, hand) {
  if (state.reviving) {
    return "reviving";
  }
  if (pig.place === "belt" || state.tick < pig.freeAt) {
    return "busy";
  }
  if (belt.freeTrays(state) === 0) {
    return "belt full";
  }
  if (pig.tags.includes("untappable")) {
    return "can't tap that";
  }
  for (const module of base.MODULES) {
    if (module.canTap) {
      const reason = module.canTap(state, pig, hand);
      if (reason !== null && reason !== undefined) {
        return reason;
      }
    }
  }
  return null;
}

// Where the pig stands in its level queue (-1 when it is in none of them)
export function queueIndex(state, pig) {
  for (const queue of state.queues) {
    const at = queue.indexOf(pig.id);
    if (at >= 0) {
      return at;
    }
  }
  return -1;
}

// Remove a pig from its queue, slot or the rescue queue (the rest of the rescue queue closes up); returns the queue's
// index (-1 when it was in none of the level's queues)
export function takeOut(state, pig) {
  for (let index = 0; index < state.queues.length; index++) {
    const at = state.queues[index].indexOf(pig.id);
    if (at >= 0) {
      state.queues[index].splice(at, 1);
      return index;
    }
  }
  const slot = state.slots.indexOf(pig.id);
  if (slot >= 0) {
    state.slots[slot] = null;
  }
  const rescued = state.rescue.indexOf(pig.id);
  if (rescued >= 0) {
    state.rescue.splice(rescued, 1);
  }
  return -1;
}

// Send pigs onto the belt together (MapController.<TryPlaceShootersToConveyor>d__56$$MoveNext, RVA 0x58D7C00):
// reserve a tray each, take them out and close up the slots, wait a frame, hop them on HOP_GAP apart, and once the
// last hop has landed start their trays one a frame in batch order
export function placeBatch(state, pigIds) {
  if (belt.freeTrays(state) < pigIds.length) {
    return "belt full";
  }
  const trays = pigIds.map((pigId) => belt.reserve(state, pigId));
  const wasFull = slotsFull(state);
  const queues = [];
  const indices = pigIds.map((pigId) => queueIndex(state, state.pigs[pigId]));
  for (const pigId of pigIds) {
    const pig = state.pigs[pigId];
    queues.push(takeOut(state, pig));
    pig.place = "belt";
  }
  arrangeSlots(state);
  if (wasFull) {
    drainEntrance(state);
  }
  base.emit(state, "pigs_exit_queue", { ids: [...pigIds], queues, indices });
  base.emit(state, "pigs_placed", { ids: [...pigIds] });
  checks.requestStuckCheck(state);
  checks.tryAutofinish(state);
  const landed = PLACE_WAIT + HOP_GAP * (pigIds.length - 1) + HOP;
  pigIds.forEach((pigId, index) => {
    base.schedule(state, PLACE_WAIT + HOP_GAP * index, "hop", pigId);
    base.schedule(state, landed + TRAY_START_GAP * (index + 1), "tray_start", trays[index].id);
  });
  return null;
}

// Timer: a pig leaves the ground for its tray. The hop itself is drawn by the page. A revive may have taken the pig
// off the belt before its hop
export function hop(state, pigId) {
  if (state.pigs[pigId].place === "belt") {
    base.emit(state, "pig_hop", { pig: pigId });
  }
}

// The leftmost free slot, or -1 (Slot.IsAvailable, RVA 0x7DD1210: no pig in it)
export function freeSlot(state) {
  return state.slots.indexOf(null);
}

export function slotsFull(state) {
  return freeSlot(state) < 0;
}

// Drop a pig into the leftmost free slot (SlotGroup$$TrySetItemToAvailableSlot, then MapController$$PlaceShooterToSlot,
// RVA 0x58CFB08). The slot is its at once; it hops there for HOP ticks and can't be tapped until it lands. False when
// no slot is free
export function toSlot(state, pig) {
  const slot = freeSlot(state);
  if (slot < 0) {
    return false;
  }
  state.slots[slot] = pig.id;
  pig.place = "slot";
  pig.freeAt = state.tick + HOP + 1;
  base.emit(state, "to_slot", { pig: pig.id, slot });
  checks.requestStuckCheck(state);
  return true;
}

// Every occupied slot slides left to the next open position, keeping order (MapController$$ArrangeSlots, RVA
// 0x58CD648)
export function arrangeSlots(state) {
  const kept = state.slots.filter((pigId) => pigId !== null);
  const packed = kept.concat(new Array(state.slots.length - kept.length).fill(null));
  if (packed.some((pigId, index) => pigId !== state.slots[index])) {
    state.slots = packed;
    base.emit(state, "slots_arranged", { slots: [...packed] });
  }
}

// A pig's tray reached the end of the lap with the pig still on it (MapController$$TryPlaceShooterToEmptySlot, RVA
// 0x58CC720). While pigs already wait at the exit it joins the back of their line; otherwise it takes a free slot or
// starts the line
export function lapEnd(state, pigId) {
  const pig = state.pigs[pigId];
  if (!state.entrance.length && toSlot(state, pig)) {
    return;
  }
  enterLine(state, pig);
}

// The pig hops to a spot in the line at the exit (SlotEntranceQueueController$$TryEnqueue, RVA 0x58FD778). Once it
// lands its grace time runs one tick at a time; at gracePeriod the level fails (the controller's update, RVA
// 0x58FF40C). The hop is HOP ticks and the grace SLOT_GRACE, so it fails at tick HOP + SLOT_GRACE from now
export function enterLine(state, pig) {
  pig.place = "exit";
  state.entrance.push([pig.id, state.tick + HOP + SLOT_GRACE]);
  base.emit(state, "to_exit_line", { pig: pig.id, index: state.entrance.length - 1 });
}

// Pigs waiting at the exit take free slots, front of the line first, until the slots or the line run out
// (SlotEntranceQueueController$$TryDrainToSlots, RVA 0x58FCFDC, run when a full slot row frees a slot)
export function drainEntrance(state) {
  while (state.entrance.length && !slotsFull(state)) {
    const [pigId] = state.entrance.shift();
    toSlot(state, state.pigs[pigId]);
  }
}

// Phase 2: a pig whose grace ran out at the exit loses the level "Out of space"
// (SlotEntranceQueueController -> MapController.HandleEntranceQueueTimeout -> TriggerSlotsFullAtConveyorExit)
export function checkEntrance(state) {
  for (const [, failTick] of state.entrance) {
    if (failTick <= state.tick) {
      base.fail(state, "out_of_space", "out_of_space");
      return;
    }
  }
}

// Phase 2 while the map is paused: the grace of every pig that has landed in the exit line stops counting, so its
// fail tick moves one tick later (SlotEntranceQueueController's update skips while GameActionsPausedCondition holds,
// level3 #1022). Pigs still hopping into the line keep hopping
export function holdEntrance(state) {
  for (const entry of state.entrance) {
    if (entry[1] - SLOT_GRACE <= state.tick) {
      entry[1] += 1;
    }
  }
}

// A pig passed the fail-warning checkpoint halfway round. With every slot full the slots pulse red as a warning
// (MapController$$HandleConveyorCheckpoint, RVA 0x58D1D78; TryTriggerFailWarning, RVA 0x58CF934). A look only
export function checkpoint(state, pigId) {
  if (slotsFull(state)) {
    base.emit(state, "slot_warning", { pig: pigId });
  }
}

// A pig leaves the game wherever it is (MapController$$MakeShooterDisappear, RVA 0x58CF424): unless a feature takes it
// first, it is removed from its queue, slot, tray or the rescue queue, the slots close up, and when the slot row was
// full the pigs waiting at the exit take the freed slots. Its spin and rise are drawn by the page
export function vanish(state, pig, cause) {
  if (pig.place === "gone") {
    return;
  }
  for (const module of base.MODULES) {
    if (module.takeVanish && module.takeVanish(state, pig)) {
      return;
    }
  }
  base.emit(state, "pig_vanishing", { pig: pig.id, place: pig.place, cause });
  const wasFull = slotsFull(state);
  if (pig.place === "belt") {
    belt.remove(state, pig.id);
  } else if (pig.place === "rescue") {
    // A pig on its way to the rescue queue during a revive isn't in it yet
    const at = state.rescue.indexOf(pig.id);
    if (at >= 0) {
      state.rescue.splice(at, 1);
    }
  } else if (pig.place === "exit") {
    state.entrance = state.entrance.filter((entry) => entry[0] !== pig.id);
  } else {
    const index = queueIndex(state, pig);
    const queue = takeOut(state, pig);
    if (queue >= 0) {
      base.emit(state, "pigs_exit_queue", { ids: [pig.id], queues: [queue], indices: [index] });
    }
  }
  pig.place = "gone";
  arrangeSlots(state);
  if (wasFull) {
    drainEntrance(state);
  }
  base.emit(state, "pig_vanished", { pig: pig.id, cause });
  checks.requestWinCheck(state);
  checks.requestStuckCheck(state);
  checks.tryAutofinish(state);
}
