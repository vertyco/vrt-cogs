"""Feature 13, Woods and Hammers: a hammer is a queue entry that never shoots; once it is first in its queue it jumps
onto the weakest wood block on the picture and takes 1 off it.

The controller tries a strike pass after any tap, any pig entering or leaving a queue, a booster or the Super Unicorn
finishing and a revive finishing (WoodHammerFeatureController$$OnEnable, RVA 0x585CF70: every handler it subscribes
calls TryToHitWoods, RVA 0x585D8E8, which does nothing once the woods are all broken or while the map is paused). A
pass sorts the woods by health, lowest first (an insertion sort for so few, so ties keep the level's order), drops the
ones marked broken, and every unused hammer first in its queue takes the first wood left, the k-th of the pass
HAMMER_GAP x k ticks after the first (HitWoodsWithHammers, RVA 0x585D4BC; HammerFeature$$IsAvailableForHitting, RVA
0x5820C78). A strike that will take the wood's last health marks it broken at once, so the next hammer takes another
(HammerFeature$$Hit, RVA 0x5822274: IsLethalDamage counts the strikes already on their way). Each hammer lifts for
HAMMER_LIFT ticks and leaves its queue (TriggerRemoveShooterFromQueue: the queue closes up, which can start another
pass), its damage lands STRIKE_LANDS ticks after its strike starts, and it is gone HAMMER_DONE ticks after it starts
(DestroySelf -> MakeShooterDisappear). When no unbroken wood is left, every unused hammer vanishes, last listed first
(CleanUpRemainingHammers, RVA 0x585DAB4).

A Hand tap on a hammer runs a pass with only that hammer, which strikes even when it isn't first
(OnTapShooterWithLogic, RVA 0x585D988). The tapped event comes after the tap's own work (MapController$$OnTapShooter,
RVA 0x58D04A4), so the hammer is already used when the pass it starts looks. Wood is an obstacle: shots stop at it and
the cubes under it can't be hit until it breaks, but the stuck check sees through it (IIgnoredObstacleAttachable).
web/sim/features/wood_hammer.js mirrors this file.
"""

from __future__ import annotations

from .. import base, checks, places
from .. import grid as gridx
from ..numbers import HAMMER_DONE, HAMMER_GAP, HAMMER_LIFT, STRIKE_LANDS

NUMBER = 13

# Events after which a strike pass runs at once: a pig tapped, pigs entering or leaving a queue, and the outside
# triggers (a booster or the Super Unicorn finished, a revive finished)
STRIKE_AFTER = ("pig_tapped", "queue_changed", "pigs_exit_queue", "booster_done", "revive_done")


def setup(state: base.State) -> None:
    """The hammers in the level's order (a hammer inside a Pig Pipe too, so it comes out as a hammer), and every wood
    block standing on its cells as an obstacle, in file order."""
    listed = state.level.features.get("Hammers")
    woods = state.level.features.get("pixelWoodBlocks")
    hammers = [pig_id for pig_id in listed["Shooters"] if pig_id in state.pigs] if listed else []
    blocks = woods["WoodBlocks"] if woods else []
    if not hammers and not blocks:
        return
    for pig_id in hammers:
        state.pigs[pig_id].tags.append("disabled")
    grid = state.grid
    records = []
    for data in blocks:
        cells = [
            gridx.cell_of(grid, point["X"], point["Y"])
            for point in data["GridPoints"]
            if 0 <= point["X"] < grid.width and 0 <= point["Y"] < grid.height
        ]
        body = gridx.make_target(NUMBER, -1, data["Health"], obstacle=True, hittable=False)
        gridx.add(grid, body, cells)
        records.append({"target": body.id, "start": data["Health"], "size": data["BlockSize"], "pending": 0})
    state.features[NUMBER] = {
        "hammers": hammers,
        "woods": records,
        "broken": [False] * len(records),
        "used": [],
        "strikes": [],
        "active": bool(records),
    }


def is_hammer(state: base.State, pig_id: int) -> bool:
    mine = state.features.get(NUMBER)
    return mine is not None and pig_id in mine["hammers"]


def first_in_queue(state: base.State, pig_id: int) -> bool:
    return any(queue and queue[0] == pig_id for queue in state.queues)


def available(state: base.State, pig_id: int) -> bool:
    """Unused and first in its queue (HammerFeature$$IsAvailableForHitting)."""
    return pig_id not in state.features[NUMBER]["used"] and first_in_queue(state, pig_id)


def open_woods(state: base.State) -> list[int]:
    """Wood indices by health, lowest first and the level's order on ties, without the ones marked broken."""
    mine = state.features[NUMBER]
    health = [state.grid.targets[wood["target"]].health for wood in mine["woods"]]
    order = sorted(range(len(health)), key=lambda index: (health[index], index))
    return [index for index in order if not mine["broken"][index]]


def try_strikes(state: base.State, hammers: list[int], force: bool) -> None:
    """A strike pass over these hammers (TryToHitWoods, then HitWoodsWithHammers). Without force only available
    hammers strike. With no unbroken wood left, before or after, the leftover hammers vanish."""
    mine = state.features[NUMBER]
    if not mine["active"] or state.reviving:
        return
    woods = open_woods(state)
    count = 0
    for pig_id in hammers:
        if not woods:
            break
        if not force and not available(state, pig_id):
            continue
        strike(state, pig_id, woods[0], HAMMER_GAP * count)
        count += 1
        if mine["broken"][woods[0]]:
            woods.pop(0)
    if not woods:
        clean_up(state)


def strike(state: base.State, pig_id: int, index: int, delay: int) -> None:
    """One hammer takes this wood: it is used, the wood is marked broken now if this strike takes its last health,
    and its leave, damage and end are timed from its start, delay ticks from now."""
    mine = state.features[NUMBER]
    wood = mine["woods"][index]
    body = state.grid.targets[wood["target"]]
    mine["used"].append(pig_id)
    if body.health - (wood["pending"] + 1) < 1:
        mine["broken"][index] = True
    wood["pending"] += 1
    start = state.tick + delay
    mine["strikes"].append([pig_id, index, start])
    base.schedule(state, delay + HAMMER_LIFT, "hammer_lift", pig_id)
    base.schedule(state, delay + STRIKE_LANDS, "hammer_land", [pig_id, index])
    base.schedule(state, delay + HAMMER_DONE, "hammer_done", pig_id)
    base.emit(state, "hammer_strike", {"pig": pig_id, "wood": index, "start": start})


def clean_up(state: base.State) -> None:
    """No unbroken wood is left: no more passes, and every unused hammer vanishes, last listed first."""
    mine = state.features[NUMBER]
    mine["active"] = False
    for pig_id in reversed(mine["hammers"]):
        if pig_id not in mine["used"]:
            places.vanish(state, state.pigs[pig_id], "hammer")


def hammer_lift(state: base.State, pig_id: int) -> None:
    """Timer: the lift is over and the hammer leaves its queue for the wood; the queue closes up."""
    pig = state.pigs[pig_id]
    if pig.place != "queue":
        return
    index = places.queue_index(state, pig)
    queue = places.take_out(state, pig)
    pig.place = "held"
    if queue >= 0:
        base.emit(state, "pigs_exit_queue", {"ids": [pig_id], "queues": [queue], "indices": [index]})
    checks.request_stuck_check(state)


def hammer_land(state: base.State, args: list[int]) -> None:
    """Timer: the swing lands and the wood loses 1; at 0 it breaks and its cells are free at once
    (PixelWoodBlockFeature$$Damage)."""
    pig_id, index = args
    mine = state.features[NUMBER]
    wood = mine["woods"][index]
    body = state.grid.targets[wood["target"]]
    wood["pending"] = max(0, wood["pending"] - 1)
    if body.dead:
        return
    body.health = max(0, body.health - 1)
    base.emit(state, "hit", {"target": body.id, "cell": -1, "health": body.health})
    base.emit(state, "wood_hit", {"pig": pig_id, "wood": index, "health": body.health})
    if body.health > 0:
        return
    body.dead = True
    gridx.remove(state.grid, body)
    base.emit(state, "target_died", {"target": body.id, "owner": NUMBER})
    checks.request_win_check(state)


def hammer_done(state: base.State, pig_id: int) -> None:
    """Timer: the swing and the shrink are over and the hammer is gone."""
    mine = state.features[NUMBER]
    mine["strikes"] = [entry for entry in mine["strikes"] if entry[0] != pig_id]
    places.vanish(state, state.pigs[pig_id], "hammer")


base.register_timer("hammer_lift", base.PHASE_FEATURES, hammer_lift)
base.register_timer("hammer_land", base.PHASE_FEATURES, hammer_land)
base.register_timer("hammer_done", base.PHASE_FEATURES, hammer_done)


def can_tap(state: base.State, pig: base.Pig, hand: bool) -> str | None:
    """A hammer can be tapped only with the Hand, and only before it has struck."""
    if not is_hammer(state, pig.id):
        return None
    if not hand:
        return "can't tap that"
    if pig.id in state.features[NUMBER]["used"]:
        return "busy"
    return None


def on_tap(state: base.State, pig: base.Pig, hand: bool) -> bool:  # noqa: ARG001
    """The Hand on a hammer: it strikes at once, first in its queue or not (HitWoodsWithHammer with force)."""
    if not is_hammer(state, pig.id):
        return False
    try_strikes(state, [pig.id], True)
    return True


def on_event(state: base.State, name: str, data: dict) -> None:  # noqa: ARG001
    mine = state.features.get(NUMBER)
    if mine is not None and name in STRIKE_AFTER:
        try_strikes(state, mine["hammers"], False)


def busy(state: base.State) -> bool:
    """A hammer at work holds the stuck check (AnyHammerIsUsedCondition)."""
    mine = state.features.get(NUMBER)
    return mine is not None and bool(mine["strikes"])


def ignored_obstacles(state: base.State) -> set[int]:
    """The stuck check sees through every standing wood block."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return set()
    return {wood["target"] for wood in mine["woods"] if not state.grid.targets[wood["target"]].dead}


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, int(mine["active"]))
    h = base.mix(h, len(mine["woods"]))
    for index, wood in enumerate(mine["woods"]):
        body = state.grid.targets[wood["target"]]
        h = base.mix(base.mix(h, body.health), int(body.dead))
        h = base.mix(base.mix(h, wood["pending"]), int(mine["broken"][index]))
    h = base.mix(h, len(mine["used"]))
    for pig_id in mine["used"]:
        h = base.mix(h, pig_id)
    h = base.mix(h, len(mine["strikes"]))
    for pig_id, index, start in mine["strikes"]:
        h = base.mix(base.mix(base.mix(h, pig_id), index), start)
    return h
