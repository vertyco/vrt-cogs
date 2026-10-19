"""Feature 4, Locks and Keys: a lock is a queue entry that never shoots and can't be tapped; a key on the picture
opens one once the picture around it is cleared to the outside.

A key is freed when any of its cells is reached by the edge flood and every cell is inside the grid; the key's own
cells don't have to be clear (PixelGridController$$GetUnblockedAttachables, RVA 0x6645F68, called with its solid
check off). The release check runs at the end of a tick after any hit, tap, vanish, booster or revive
(ReleasablePixelGridAttachablesController: its handlers set a pending flag, LateUpdate RVA 0x578EAD8 clears it and
runs ExecuteRelease RVA 0x578EB4C, which does nothing while the map is paused). Freed keys are taken in the level's
order; each opens the leftmost lock that is first in its queue and not opened yet, and the first key with no such lock
ends the check (LockKeyFeatureController$$OnReleasablesUnblocked, RVA 0x5681570). The lock is marked at once, the key
flies to it for KEY_FLIGHT ticks, then the lock's entry vanishes and its queue moves up (KeyFeature$$Unlock, RVA
0x567F554; DetachInternal, RVA 0x567D744). web/sim/features/locks_keys.js mirrors this file.
"""

from __future__ import annotations

from .. import base, places
from .. import grid as gridx
from ..numbers import KEY_FLIGHT

NUMBER = 4

# Events after which the release check runs at the end of the tick: a target damaged, a pig tapped, a pig about to
# vanish, and the outside triggers (a booster or a revive finished, the walls removed)
CHECK_AFTER = ("hit", "pig_tapped", "pig_vanishing", "booster_done", "revive_done", "walls_removed")


def setup(state: base.State) -> None:
    """The locks, sorted left to right (queue columns stand left to right, and only a queue's first entry can be
    opened, so the order inside a queue never matters), and the keys' cells."""
    listed = state.level.features.get("Locks")
    keys = state.level.features.get("keys")
    lock_ids = [pig_id for pig_id in listed["Shooters"] if pig_id in state.pigs] if listed else []
    key_list = keys["Keys"] if keys else []
    if not lock_ids and not key_list:
        return
    locks = [pig_id for queue in state.queues for pig_id in queue if pig_id in lock_ids]
    for pig_id in locks:
        state.pigs[pig_id].tags.extend(["disabled", "untappable"])
    grid = state.grid
    cells = []
    inside = []
    for key in key_list:
        points = [(point["X"], point["Y"]) for point in key["GridPoints"]]
        valid = [(x, y) for x, y in points if 0 <= x < grid.width and 0 <= y < grid.height]
        cells.append([gridx.cell_of(grid, x, y) for x, y in valid])
        inside.append(len(valid) == len(points))
    state.features[NUMBER] = {
        "locks": locks,
        "opened": [],
        "cells": cells,
        "inside": inside,
        "used": [False] * len(key_list),
        "flights": [],
        "pending": False,
    }


def first_in_queue(state: base.State, pig_id: int) -> bool:
    return any(queue and queue[0] == pig_id for queue in state.queues)


def free_lock(state: base.State) -> int | None:
    """The leftmost lock first in its queue and not opened yet (LockFeature$$IsAvailableToUnlock, RVA 0x5680B24)."""
    mine = state.features[NUMBER]
    for pig_id in mine["locks"]:
        if pig_id not in mine["opened"] and first_in_queue(state, pig_id):
            return pig_id
    return None


def key_free(state: base.State, index: int, reach: list[int]) -> bool:
    mine = state.features[NUMBER]
    return mine["inside"][index] and any(reach[cell] for cell in mine["cells"][index])


def unlock(state: base.State, index: int, lock: int) -> None:
    """The key leaves the picture for its lock. Its leaving is another attachable change, so the release check runs
    again at the end of the next tick."""
    mine = state.features[NUMBER]
    mine["used"][index] = True
    mine["opened"].append(lock)
    land = state.tick + KEY_FLIGHT
    mine["flights"].append([index, lock, land])
    mine["pending"] = True
    base.schedule(state, KEY_FLIGHT, "lock_open", [index, lock])
    base.emit(state, "key_unlock", {"key": index, "lock": lock, "land": land})


def lock_open(state: base.State, args: list[int]) -> None:
    """Timer: the key has reached its lock, and the lock's entry vanishes."""
    index, lock = args
    mine = state.features[NUMBER]
    mine["flights"] = [flight for flight in mine["flights"] if flight[0] != index]
    base.emit(state, "lock_opened", {"key": index, "lock": lock})
    places.vanish(state, state.pigs[lock], "unlock")


base.register_timer("lock_open", base.PHASE_FEATURES, lock_open)


def on_event(state: base.State, name: str, data: dict) -> None:  # noqa: ARG001
    if NUMBER in state.features and name in CHECK_AFTER:
        state.features[NUMBER]["pending"] = True


def release(state: base.State) -> None:
    """End of tick: when something asked for it and the map isn't paused by a revive, every freed key in order opens
    the leftmost free lock, until a key finds none."""
    mine = state.features.get(NUMBER)
    if mine is None or not mine["pending"]:
        return
    mine["pending"] = False
    if state.reviving:
        return
    reach = gridx.reach_outside(state.grid)
    for index in range(len(mine["used"])):
        if mine["used"][index] or not key_free(state, index, reach):
            continue
        lock = free_lock(state)
        if lock is None:
            return
        unlock(state, index, lock)


def busy(state: base.State) -> bool:
    """A key in flight holds the stuck check."""
    mine = state.features.get(NUMBER)
    return mine is not None and bool(mine["flights"])


def blocker(state: base.State, pig: base.Pig) -> str | None:
    mine = state.features.get(NUMBER)
    if mine is not None and pig.id in mine["locks"]:
        return "locked_out"
    return None


def revive(state: base.State, name: str) -> int:
    """The Locked Out revive: each lock first in its queue, queue by queue, takes the last key left, freed or not
    (MapRescueController.<UnlockFirstLocks>d__23$$MoveNext, RVA 0x58F5238), and the revive waits for the flights.
    Returns the ticks the revive waits: the flight, and one more so the locks have vanished when it ends."""
    mine = state.features.get(NUMBER)
    if name != "locked_out" or mine is None:
        return 0
    keys = [index for index, used in enumerate(mine["used"]) if not used]
    fronts = [queue[0] for queue in state.queues if queue and queue[0] in mine["locks"]]
    opened = 0
    for lock in fronts:
        if not keys:
            break
        unlock(state, keys.pop(), lock)
        opened += 1
    return KEY_FLIGHT + 1 if opened else 0


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["opened"]))
    for pig_id in mine["opened"]:
        h = base.mix(h, pig_id)
    for used in mine["used"]:
        h = base.mix(h, int(used))
    h = base.mix(h, len(mine["flights"]))
    for index, lock, land in mine["flights"]:
        h = base.mix(base.mix(base.mix(h, index), lock), land)
    return base.mix(h, int(mine["pending"]))
