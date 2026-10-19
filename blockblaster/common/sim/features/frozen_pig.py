"""Feature 14, the Frozen Pig: a real pig in a queue, wrapped in ice that only other pigs running dry can melt.

Every pig that vanishes (runs dry, including into a U.F.O. seat or spaceship) takes 1 off every frozen pig, unless it
is a disabled entry such as a hammer, a lock or a pipe; shots and cubes don't count
(ShooterIceBlockFeatureController$$OnShooterWillDisappear, RVA 0x57A10BC). It is raised before the vanish is handled,
so it runs for every pig whether or not a feature then takes the vanish over. A frozen pig can't be tapped; the Hand
can, and then does 1 to that one ice (OnTapShooterWithLogic, RVA 0x57A0C9C). At 0 the ice shatters and it is a normal
pig, tappable when first in its queue (DestroyIce, RVA 0x579C910). A frozen pig keeps its ammo and counts as a live
pig. When no queue front can be tapped and the most common blocker at the fronts is a frozen pig the level fails
"Frozen!"; its revive shatters the frozen pigs standing first in their queues (ShatterFirstIceBlocks).
web/sim/features/frozen_pig.js mirrors this file.
"""

from __future__ import annotations

from .. import base, checks

NUMBER = 14


def setup(state: base.State) -> None:
    """Every frozen pig as a record, in file order, with the ice it starts with. A pig inside a Pig Pipe is frozen
    from the start too (the pipe adds its pigs before the modules run)."""
    listed = state.level.features.get("ShooterIceBlocks")
    if not listed or not listed["IceBlocks"]:
        return
    ice = [
        {"pig": data["ShooterId"], "start": data["Health"], "health": data["Health"]}
        for data in listed["IceBlocks"]
        if data["ShooterId"] in state.pigs
    ]
    if ice:
        state.features[NUMBER] = {"ice": ice}


def record(state: base.State, pig_id: int) -> dict | None:
    """The pig's ice while it still has some, else None."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return None
    for entry in mine["ice"]:
        if entry["pig"] == pig_id and entry["health"] > 0:
            return entry
    return None


def damage(state: base.State, entry: dict, why: str, amount: int = 1) -> None:
    """The ice loses some health; at 0 it shatters and the pig can be tapped. The ice is gone at once, the page draws
    the shatter."""
    entry["health"] = max(0, entry["health"] - amount)
    base.emit(state, "frozen_hit", {"pig": entry["pig"], "health": entry["health"], "why": why})
    if entry["health"] > 0:
        return
    base.emit(state, "frozen_thaw", {"pig": entry["pig"], "why": why})
    checks.request_stuck_check(state)


def take_vanish(state: base.State, pig: base.Pig) -> bool:
    """A pig is about to vanish: every frozen pig takes 1 off, unless this one is a disabled entry. Never takes the
    vanish over."""
    mine = state.features.get(NUMBER)
    if mine is None or "disabled" in pig.tags:
        return False
    for entry in mine["ice"]:
        if entry["health"] > 0:
            damage(state, entry, "vanish")
    return False


def pins(state: base.State, pig_id: int) -> bool:
    """Every pig the level lists carries the feature, frozen or thawed, so Shuffle leaves it where it is."""
    mine = state.features.get(NUMBER)
    return mine is not None and any(entry["pig"] == pig_id for entry in mine["ice"])


def can_tap(state: base.State, pig: base.Pig, hand: bool) -> str | None:
    """A frozen pig can be tapped only with the Hand."""
    if record(state, pig.id) is None or hand:
        return None
    return "frozen"


def on_tap(state: base.State, pig: base.Pig, hand: bool) -> bool:
    """The Hand on a frozen pig: 1 off its ice, and the pig stays where it is."""
    entry = record(state, pig.id)
    if entry is None or not hand:
        return False
    damage(state, entry, "hand")
    return True


def blocker(state: base.State, pig: base.Pig) -> str | None:
    if record(state, pig.id) is not None:
        return "frozen"
    return None


def revive(state: base.State, name: str) -> int:
    """The Frozen! revive shatters the ice of every frozen pig first in its queue, queue by queue. Returns the ticks
    the revive waits (none)."""
    if name != "frozen" or NUMBER not in state.features:
        return 0
    for queue in state.queues:
        entry = record(state, queue[0]) if queue else None
        if entry is not None:
            damage(state, entry, "revive", entry["health"])
    return 0


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["ice"]))
    for entry in mine["ice"]:
        h = base.mix(base.mix(h, entry["pig"]), entry["health"])
    return h
