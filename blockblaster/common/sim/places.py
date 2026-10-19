"""Where pigs wait, taps that send them onto the belt, the slots, the end of a lap and vanishing.

A pig that reaches the end of a lap with ammo left drops into the leftmost free slot. With none free it waits in the
line at the belt's exit (SlotEntranceQueueController), and if no slot opens in time the level fails "Out of space".
web/sim/places.js mirrors this file.
"""

from __future__ import annotations

from . import base, belt, checks
from .numbers import HOP, HOP_GAP, PLACE_WAIT, SLOT_GRACE, TRAY_START_GAP


def tap_front(state: base.State, queue: int) -> str | None:
    """A tap on a queue's front pig. Returns why it was refused, or None."""
    if queue < 0 or queue >= len(state.queues):
        return "no such queue"
    if not state.queues[queue]:
        return "queue empty"
    return tap_pig(state, state.pigs[state.queues[queue][0]], False)


def tap_slot(state: base.State, slot: int) -> str | None:
    """A tap on a slot's pig: it goes round again, placed like a queue front. Returns why it was refused, or None."""
    if slot < 0 or slot >= len(state.slots):
        return "no such slot"
    if state.slots[slot] is None:
        return "slot empty"
    return tap_pig(state, state.pigs[state.slots[slot]], False)


def tap_rescue(state: base.State, index: int) -> str | None:
    """A tap on a pig in the rescue queue. It isn't one of the level's queues, so any of its pigs can be tapped, not
    only the front one (MapProvider$$IsShooterFirstInMapQueue, RVA 0x58F7858, is false for it and the slot-pig rule
    lets it pass). Returns why it was refused, or None."""
    if index < 0 or index >= len(state.rescue):
        return "no such rescue pig"
    return tap_pig(state, state.pigs[state.rescue[index]], False)


def tap_pig(state: base.State, pig: base.Pig, hand: bool) -> str | None:
    """The tap check, then a feature's own tap or placing the pig, or its whole Connected group, on the belt (whose
    first steps, up to its one-frame wait, run at once), then the tapped event (MapController$$OnTapShooter, RVA
    0x58D04A4: ExecuteTap, then MapEvents' TriggerShooterTapped). `hand` is true for the Hand booster's pick."""
    reason = tap_check(state, pig, hand)
    if reason is not None:
        return reason
    result = None
    if not any(getattr(module, "on_tap", None) and module.on_tap(state, pig, hand) for module in base.MODULES):
        result = place_batch(state, batch_of(state, pig))
    base.emit(state, "pig_tapped", {"pig": pig.id})
    return result


def batch_of(state: base.State, pig: base.Pig) -> list[int]:
    """The pigs a tap on this pig sends onto the belt: its Connected group in group order, or the pig alone."""
    for module in base.MODULES:
        hook = getattr(module, "group", None)
        if hook is not None:
            members = hook(state, pig)
            if members is not None:
                return members
    return [pig.id]


def tap_check(state: base.State, pig: base.Pig, hand: bool) -> str | None:
    """The tap rules (CanTapShooterCondition$$CheckMainConditions, RVA 0x58B3258): not while a revive works
    (ShooterTapDisabledCondition, sharedassets3 #422, reads Is Rescue Map Running), not on the belt or mid-hop
    (Shooter$$get_IsBusy), a free tray, and no feature against it. The caller has already applied the position rules
    (the front of a queue, or any queue pig with the Hand), so `hand` only reaches the features."""
    if state.reviving:
        return "reviving"
    if pig.place == "belt" or state.tick < pig.free_at:
        return "busy"
    if belt.free_trays(state) == 0:
        return "belt full"
    if "untappable" in pig.tags:
        return "can't tap that"
    for module in base.MODULES:
        hook = getattr(module, "can_tap", None)
        if hook is not None:
            reason = hook(state, pig, hand)
            if reason is not None:
                return reason
    return None


def queue_index(state: base.State, pig: base.Pig) -> int:
    """Where the pig stands in its level queue (-1 when it is in none of them)."""
    for queue in state.queues:
        if pig.id in queue:
            return queue.index(pig.id)
    return -1


def take_out(state: base.State, pig: base.Pig) -> int:
    """Remove a pig from its queue, slot or the rescue queue (the rest of the rescue queue closes up); returns the
    queue's index (-1 when it was in none of the level's queues)."""
    for index, queue in enumerate(state.queues):
        if pig.id in queue:
            queue.remove(pig.id)
            return index
    if pig.id in state.slots:
        state.slots[state.slots.index(pig.id)] = None
    if pig.id in state.rescue:
        state.rescue.remove(pig.id)
    return -1


def place_batch(state: base.State, pig_ids: list[int]) -> str | None:
    """Send pigs onto the belt together (MapController.<TryPlaceShootersToConveyor>d__56$$MoveNext, RVA 0x58D7C00):
    reserve a tray each, take them out and close up the slots, wait a frame, hop them on HOP_GAP apart, and once the
    last hop has landed start their trays one a frame in batch order."""
    if belt.free_trays(state) < len(pig_ids):
        return "belt full"
    trays = [belt.reserve(state, pig_id) for pig_id in pig_ids]
    was_full = slots_full(state)
    queues = []
    indices = [queue_index(state, state.pigs[pig_id]) for pig_id in pig_ids]
    for pig_id in pig_ids:
        pig = state.pigs[pig_id]
        queues.append(take_out(state, pig))
        pig.place = "belt"
    arrange_slots(state)
    if was_full:
        drain_entrance(state)
    base.emit(state, "pigs_exit_queue", {"ids": list(pig_ids), "queues": queues, "indices": indices})
    base.emit(state, "pigs_placed", {"ids": list(pig_ids)})
    checks.request_stuck_check(state)
    checks.try_autofinish(state)
    count = len(pig_ids)
    landed = PLACE_WAIT + HOP_GAP * (count - 1) + HOP
    for index, pig_id in enumerate(pig_ids):
        base.schedule(state, PLACE_WAIT + HOP_GAP * index, "hop", pig_id)
        base.schedule(state, landed + TRAY_START_GAP * (index + 1), "tray_start", trays[index].id)
    return None


def hop(state: base.State, pig_id: int) -> None:
    """Timer: a pig leaves the ground for its tray. The hop itself is drawn by the page. A revive may have taken the
    pig off the belt before its hop."""
    if state.pigs[pig_id].place == "belt":
        base.emit(state, "pig_hop", {"pig": pig_id})


def free_slot(state: base.State) -> int:
    """The leftmost free slot, or -1 (Slot.IsAvailable, RVA 0x7DD1210: no pig in it)."""
    for index, pig_id in enumerate(state.slots):
        if pig_id is None:
            return index
    return -1


def slots_full(state: base.State) -> bool:
    return free_slot(state) < 0


def to_slot(state: base.State, pig: base.Pig) -> bool:
    """Drop a pig into the leftmost free slot (SlotGroup$$TrySetItemToAvailableSlot, then
    MapController$$PlaceShooterToSlot, RVA 0x58CFB08). The slot is its at once; it hops there for HOP ticks and
    can't be tapped until it lands. False when no slot is free."""
    slot = free_slot(state)
    if slot < 0:
        return False
    state.slots[slot] = pig.id
    pig.place = "slot"
    pig.free_at = state.tick + HOP + 1
    base.emit(state, "to_slot", {"pig": pig.id, "slot": slot})
    checks.request_stuck_check(state)
    return True


def arrange_slots(state: base.State) -> None:
    """Every occupied slot slides left to the next open position, keeping order (MapController$$ArrangeSlots, RVA
    0x58CD648)."""
    kept = [pig_id for pig_id in state.slots if pig_id is not None]
    packed = kept + [None] * (len(state.slots) - len(kept))
    if packed != state.slots:
        state.slots = packed
        base.emit(state, "slots_arranged", {"slots": list(packed)})


def lap_end(state: base.State, pig_id: int) -> None:
    """A pig's tray reached the end of the lap with the pig still on it (MapController$$TryPlaceShooterToEmptySlot,
    RVA 0x58CC720). While pigs already wait at the exit it joins the back of their line; otherwise it takes a free
    slot or starts the line."""
    pig = state.pigs[pig_id]
    if not state.entrance and to_slot(state, pig):
        return
    enter_line(state, pig)


def enter_line(state: base.State, pig: base.Pig) -> None:
    """The pig hops to a spot in the line at the exit (SlotEntranceQueueController$$TryEnqueue, RVA 0x58FD778). Once
    it lands its grace time runs one tick at a time; at gracePeriod the level fails (the controller's update, RVA
    0x58FF40C). The hop is HOP ticks and the grace SLOT_GRACE, so it fails at tick HOP + SLOT_GRACE from now."""
    pig.place = "exit"
    state.entrance.append([pig.id, state.tick + HOP + SLOT_GRACE])
    base.emit(state, "to_exit_line", {"pig": pig.id, "index": len(state.entrance) - 1})


def drain_entrance(state: base.State) -> None:
    """Pigs waiting at the exit take free slots, front of the line first, until the slots or the line run out
    (SlotEntranceQueueController$$TryDrainToSlots, RVA 0x58FCFDC, run when a full slot row frees a slot)."""
    while state.entrance and not slots_full(state):
        pig_id, _ = state.entrance.pop(0)
        to_slot(state, state.pigs[pig_id])


def check_entrance(state: base.State) -> None:
    """Phase 2: a pig whose grace ran out at the exit loses the level "Out of space"
    (SlotEntranceQueueController -> MapController.HandleEntranceQueueTimeout -> TriggerSlotsFullAtConveyorExit)."""
    for _, fail_tick in state.entrance:
        if fail_tick <= state.tick:
            base.fail(state, "out_of_space", "out_of_space")
            return


def hold_entrance(state: base.State) -> None:
    """Phase 2 while the map is paused: the grace of every pig that has landed in the exit line stops counting, so
    its fail tick moves one tick later (SlotEntranceQueueController's update skips while GameActionsPausedCondition
    holds, level3 #1022). Pigs still hopping into the line keep hopping."""
    for entry in state.entrance:
        if entry[1] - SLOT_GRACE <= state.tick:
            entry[1] += 1


def checkpoint(state: base.State, pig_id: int) -> None:
    """A pig passed the fail-warning checkpoint halfway round. With every slot full the slots pulse red as a warning
    (MapController$$HandleConveyorCheckpoint, RVA 0x58D1D78; TryTriggerFailWarning, RVA 0x58CF934). A look only."""
    if slots_full(state):
        base.emit(state, "slot_warning", {"pig": pig_id})


def vanish(state: base.State, pig: base.Pig, cause: str) -> None:
    """A pig leaves the game wherever it is (MapController$$MakeShooterDisappear, RVA 0x58CF424): unless a feature
    takes it first, it is removed from its queue, slot, tray or the rescue queue, the slots close up, and when the
    slot row was full the pigs waiting at the exit take the freed slots. Its spin and rise are drawn by the page."""
    if pig.place == "gone":
        return
    for module in base.MODULES:
        hook = getattr(module, "take_vanish", None)
        if hook is not None and hook(state, pig):
            return
    base.emit(state, "pig_vanishing", {"pig": pig.id, "place": pig.place, "cause": cause})
    was_full = slots_full(state)
    if pig.place == "belt":
        belt.remove(state, pig.id)
    elif pig.place == "rescue":
        # A pig on its way to the rescue queue during a revive isn't in it yet
        if pig.id in state.rescue:
            state.rescue.remove(pig.id)
    elif pig.place == "exit":
        state.entrance = [entry for entry in state.entrance if entry[0] != pig.id]
    else:
        index = queue_index(state, pig)
        queue = take_out(state, pig)
        if queue >= 0:
            base.emit(state, "pigs_exit_queue", {"ids": [pig.id], "queues": [queue], "indices": [index]})
    pig.place = "gone"
    arrange_slots(state)
    if was_full:
        drain_entrance(state)
    base.emit(state, "pig_vanished", {"pig": pig.id, "cause": cause})
    checks.request_win_check(state)
    checks.request_stuck_check(state)
    checks.try_autofinish(state)
