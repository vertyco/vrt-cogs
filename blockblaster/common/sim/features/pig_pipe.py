"""Feature 11, the Pig Pipe: a queue entry that holds more pigs and lets one out for each pig that leaves ahead of it.

The pipe entry can't be tapped and never goes on the belt. It remembers the index it started at in its queue
(ShooterPipeFeature$$AttachInternal, RVA 0x57A5ADC). When pigs leave its queue from in front of that index it releases
min(pigs that left, pigs inside) pigs at once, each inserted at start + k - released (OnShootersExitingQueue, RVA
0x57A48CC, whose FindAll predicate <OnShootersExitingQueue>b__22_0 is "same queue and index < start"; SpawnShooter, RVA
0x57A3980), so one pig leaving puts the new pig right in front of the pipe and the pipe never moves forward while it
has pigs. When the last pig is out the entry vanishes and the queue closes up (RemoveSelf, RVA 0x57A42F4).

The pigs inside are pigs of the level from the start, held where no rule reaches them (add_pigs makes them before any
other module sets up, since Connected groups, Surprise pigs, hammers and Frozen pigs may list them). They are not on
the map for the stuck check (spec O4), but they are in the shooter list the auto-finisher counts (ShooterProvider keeps
nested shooters in its list and filters them with IsShooterNested). web/sim/features/pig_pipe.js mirrors this file.
"""

from __future__ import annotations

from .. import base, places

NUMBER = 11


def add_pigs(state: base.State) -> None:
    """Every pig inside a pipe, held, in the order the pipes list them."""
    listed = state.level.features.get("ShooterPipes")
    if not listed:
        return
    for data in listed["Pipes"]:
        for shooter in data["Queue"]["shooters"]:
            state.pigs[shooter["id"]] = base.Pig(
                id=shooter["id"], color=shooter["material"], ammo=shooter["ammo"], place="held"
            )


def setup(state: base.State) -> None:
    """Each pipe entry made untappable and disabled, with the queue and index it starts at."""
    listed = state.level.features.get("ShooterPipes")
    if not listed:
        return
    pipes = []
    for data in listed["Pipes"]:
        entry = data["ShooterId"]
        queue = next((index for index, ids in enumerate(state.queues) if entry in ids), -1)
        if queue < 0:
            continue
        state.pigs[entry].tags.extend(["disabled", "untappable"])
        pipes.append(
            {
                "pig": entry,
                "queue": queue,
                "start": state.queues[queue].index(entry),
                "inside": [shooter["id"] for shooter in data["Queue"]["shooters"]],
                "gone": False,
            }
        )
    state.features[NUMBER] = {"pipes": pipes}


def let_out(state: base.State, pipe: dict, left: int) -> None:
    """Let min(left, inside) pigs out, each into the queue at start + k - released. With none inside the entry
    vanishes at once and the queue closes up."""
    count = min(left, len(pipe["inside"]))
    queue = state.queues[pipe["queue"]]
    for k in range(count):
        pig_id = pipe["inside"].pop(0)
        index = pipe["start"] + k - count
        state.pigs[pig_id].place = "queue"
        queue.insert(index, pig_id)
        base.emit(state, "pipe_release", {"pipe": pipe["pig"], "pig": pig_id, "queue": pipe["queue"], "index": index})
    base.emit(state, "queue_changed", {})
    if not pipe["inside"]:
        pipe["gone"] = True
        places.vanish(state, state.pigs[pipe["pig"]], "pipe")


def on_event(state: base.State, name: str, data: dict) -> None:
    """Pigs left a queue: every pipe in it counts those that stood in front of its starting index."""
    mine = state.features.get(NUMBER)
    if mine is None or name != "pigs_exit_queue":
        return
    for pipe in mine["pipes"]:
        if pipe["gone"] or not pipe["inside"]:
            continue
        left = sum(
            1
            for queue, index in zip(data["queues"], data["indices"], strict=True)
            if queue == pipe["queue"] and index < pipe["start"]
        )
        if left > 0:
            let_out(state, pipe, left)


def checksum(state: base.State, h: int) -> int:
    mine = state.features.get(NUMBER)
    if mine is None:
        return h
    h = base.mix(h, len(mine["pipes"]))
    for pipe in mine["pipes"]:
        h = base.mix(base.mix(h, int(pipe["gone"])), len(pipe["inside"]))
        for pig_id in pipe["inside"]:
            h = base.mix(h, pig_id)
    return h
