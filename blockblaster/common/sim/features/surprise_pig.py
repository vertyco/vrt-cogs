"""Feature 1, the Surprise Pig: a pig drawn as a "?" until it is first in its queue.

Hiding changes only what the page draws. A hidden pig's color and ammo are its listed values the whole time, so no
rule reads the hidden list; it exists so the bot and the page agree on what is drawn (SurpriseShooterFeature$$Reveal,
RVA 0x57FBA34). A pig is revealed when it is first in its queue after any queue change, booster or revive
(SurpriseShooterFeatureController$$HandleFirstShooterReveal, RVA 0x57FBE60), and forced when it goes on the belt or
vanishes. web/sim/features/surprise_pig.js mirrors this file.
"""

from __future__ import annotations

from .. import base

NUMBER = 1

# Events after which the first pig of every queue is revealed
REVEAL_AFTER = ("pigs_exit_queue", "queue_changed", "booster_done", "revive_done")


def setup(state: base.State) -> None:
    """The listed pigs start hidden, except the ones already first in their queues."""
    listed = state.level.features.get("SurpriseShooters")
    if not listed:
        return
    hidden = [pig_id for pig_id in listed["Shooters"] if pig_id in state.pigs]
    state.features[NUMBER] = {"hidden": hidden}
    for queue in state.queues:
        if queue and queue[0] in hidden:
            hidden.remove(queue[0])


def pins(state: base.State, pig_id: int) -> bool:
    """Every pig the level lists carries the feature, hidden or already revealed, so Shuffle leaves it where it is."""
    listed = state.level.features.get("SurpriseShooters")
    return bool(listed) and pig_id in listed["Shooters"]


def reveal(state: base.State, pig_id: int) -> None:
    """Show a hidden pig's real color and number."""
    hidden = state.features[NUMBER]["hidden"]
    if pig_id in hidden:
        hidden.remove(pig_id)
        base.emit(state, "pig_revealed", {"pig": pig_id})


def reveal_fronts(state: base.State) -> None:
    for queue in state.queues:
        if queue:
            reveal(state, queue[0])


def on_event(state: base.State, name: str, data: dict) -> None:
    if NUMBER not in state.features:
        return
    if name == "pigs_placed":
        for pig_id in data["ids"]:
            reveal(state, pig_id)
    elif name in REVEAL_AFTER:
        reveal_fronts(state)


def take_vanish(state: base.State, pig: base.Pig) -> bool:
    """A pig that vanishes is revealed first. It never takes the vanish over."""
    if NUMBER in state.features:
        reveal(state, pig.id)
    return False


def checksum(state: base.State, h: int) -> int:
    if NUMBER not in state.features:
        return h
    hidden = state.features[NUMBER]["hidden"]
    h = base.mix(h, len(hidden))
    for pig_id in hidden:
        h = base.mix(h, pig_id)
    return h
