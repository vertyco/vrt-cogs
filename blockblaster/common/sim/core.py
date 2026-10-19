"""One level's rules: a new state, the tick, taps and the checksum.

The same level, seed and taps at the same ticks always give the same state. The page runs web/sim/core.js, which
mirrors this file function for function; both use whole numbers only so they agree bit for bit. The state records,
timers and events live in base, which every module shares; this module ties the others together and none imports it.
"""

from . import aim, belt, boosters, checks, places, unicorn
from . import grid as gridx
from .base import (
    FNV_START,
    MODULES,
    PHASE_BELT,
    PHASE_CHECKS,
    PHASE_FEATURES,
    PHASE_RELEASE,
    PHASE_SHOOT,
    PHASE_SHOTS,
    PHASE_TAPS,
    PLACES,
    Pig,
    State,
    call_hooks,
    fire_timers,
    mix,
    mix_text,
    register_timer,
)
from .features import (
    biscuit,
    connected,
    egg_box,
    frozen_pig,
    gate,
    hungry_door,
    ice_block,
    locks_keys,
    pig_pipe,
    pixel_pipe,
    rocket,
    snake,
    surprise_pig,
    surprise_pixel,
    wall,
    wood_hammer,
)
from .level import Level
from .mathx import idiv
from .rng import Rng

# Every feature module, in feature-number order
MODULES.extend(
    [
        surprise_pig,
        connected,
        locks_keys,
        gate,
        pixel_pipe,
        surprise_pixel,
        snake,
        wall,
        egg_box,
        pig_pipe,
        ice_block,
        wood_hammer,
        frozen_pig,
        hungry_door,
        biscuit,
        rocket,
    ]
)


def new_state(level: Level, seed: int, board: dict, unicorn_active: bool = False) -> State:
    """A level at tick 0. unicorn_active: the player has the Super Unicorn this level (the bot decides)."""
    state = State(
        level=level,
        seed=seed,
        belt_path=board["belt"],
        weapon=list(board["weapon"]),
        rng=Rng(seed),
        grid=gridx.new_grid(level),
    )
    for queue in level.queues:
        ids = []
        for pig_id, ammo, color in queue:
            state.pigs[pig_id] = Pig(id=pig_id, color=color, ammo=ammo, place="queue")
            ids.append(pig_id)
        state.queues.append(ids)
    # Pigs inside pipes exist from the start: other features list them
    pig_pipe.add_pigs(state)
    state.slots = [None] * level.slot_count
    state.tray_total = level.conveyor_limit
    state.cubes_start = len(level.cubes)
    state.cubes_left = len(level.cubes)
    state.unicorn = unicorn.new_unicorn(len(level.cubes), unicorn_active)
    for module in MODULES:
        module.setup(state)
    # Hooks that read the finished picture (every module has put its parts on it by now)
    call_hooks(state, "ready")
    return state


# Placing pigs runs as a coroutine in the original, which resumes after every script's Update: its steps land at the
# end of a tick, so a tray started at tick T first moves at tick T + 1
register_timer("hop", PHASE_RELEASE, places.hop)
register_timer("tray_start", PHASE_RELEASE, belt.start_tray)
register_timer("win_check", PHASE_CHECKS, checks.win_check)
# The revive is an async task in the original (UniTask, resumed at PlayerLoopTiming.Update before every script's
# Update), so its steps land at the start of a tick
register_timer("revive_act", PHASE_TAPS, boosters.act_revive)
register_timer("rescue_pig", PHASE_TAPS, boosters.rescue_pig)
register_timer("revive_done", PHASE_TAPS, boosters.end_revive)


def stuck_check(state: State, stage: str) -> None:
    """Timer: the stuck check; when it repairs instead of failing, the pigs it emptied vanish and the auto-finisher
    may start (MapController$$SyncShootersAndPixels, RVA 0x58D1F50)."""
    emptied = checks.stuck_check(state, stage)
    if emptied is None:
        return
    for pig_id in emptied:
        places.vanish(state, state.pigs[pig_id], "repair")
    checks.try_autofinish(state)


register_timer("stuck_check", PHASE_CHECKS, stuck_check)


def move_belt(state: State) -> None:
    """Trays move, spacing, the fail-warning checkpoint, Conveyor Walls, pigs exit; then pigs waiting at the exit run
    out of time."""
    crossed, exited = belt.move_trays(state)
    for pig_id in crossed:
        places.checkpoint(state, pig_id)
    for pig_id in exited:
        places.lap_end(state, pig_id)
    places.check_entrance(state)


def shoot(state: State) -> None:
    """Pigs fire, in the order their trays started; pigs that ran dry vanish."""
    for pig_id in aim.step_shooting(state):
        places.vanish(state, state.pigs[pig_id], "empty")


def move_shots(state: State) -> None:
    """Shots in flight move and land, in firing order."""
    aim.step_shots(state)


def step(state: State) -> None:
    """Simulate tick state.tick, then move on to the next tick."""
    state.events = []
    fire_timers(state, PHASE_TAPS)
    if state.reviving:
        # The belt stands still while a revive works (ConveyorController reads GameActionsPausedCondition, which
        # holds while Is Rescue Map Running is on); pigs on it still shoot
        places.hold_entrance(state)
    else:
        move_belt(state)
    fire_timers(state, PHASE_BELT)
    shoot(state)
    fire_timers(state, PHASE_SHOOT)
    call_hooks(state, "step")
    fire_timers(state, PHASE_FEATURES)
    move_shots(state)
    fire_timers(state, PHASE_SHOTS)
    # The win and stuck checks are timers of this phase
    fire_timers(state, PHASE_CHECKS)
    call_hooks(state, "release")
    fire_timers(state, PHASE_RELEASE)
    state.tick += 1


def run_to(state: State, tick: int) -> None:
    """Step until state.tick reaches tick or the level ends."""
    while state.tick < tick and state.over is None:
        step(state)


def apply_tap(state: State, tap: list) -> str | None:
    """Apply a tap at phase 1 of tick state.tick. Returns why it was refused, or None."""
    if tap == ["revive"]:
        return boosters.revive(state)
    if state.over is not None:
        return "level over"
    if not isinstance(tap, list) or not tap:
        return "bad tap"
    if tap == ["tray"]:
        return boosters.apply_tray(state)
    if tap == ["shuffle"]:
        return boosters.apply_shuffle(state)
    if tap[0] == "hand" and len(tap) == 3 and type(tap[1]) is int and type(tap[2]) is int:
        return boosters.apply_hand(state, tap[1], tap[2])
    if tap[0] == "bomb" and len(tap) == 3 and type(tap[1]) is int and type(tap[2]) is int:
        return boosters.apply_bomb(state, tap[1], tap[2])
    if tap[0] == "super" and len(tap) == 3 and type(tap[1]) is int and type(tap[2]) is int:
        return boosters.apply_super(state, tap[1], tap[2])
    if tap == ["unicorn"]:
        return unicorn.use(state)
    if tap[0] == "q" and len(tap) == 2 and type(tap[1]) is int:
        return places.tap_front(state, tap[1])
    if tap[0] == "s" and len(tap) == 2 and type(tap[1]) is int:
        return places.tap_slot(state, tap[1])
    if tap[0] == "r" and len(tap) == 2 and type(tap[1]) is int:
        return places.tap_rescue(state, tap[1])
    return "not yet"


def checksum(state: State) -> int:
    """The state as one number: tick, belt trays, pigs by id, queues, slots, rescue queue, cube totals, shots, the
    shooting, the exit line, the auto-finisher, the revive, the tray count, the Super Unicorn's bar when the player
    has it, then each feature's part in feature-number order."""
    h = mix(FNV_START, state.tick)
    h = mix(h, len(state.belt))
    for tray in state.belt:
        h = mix(mix(mix(mix(h, tray.id), tray.pos), int(tray.started)), -1 if tray.pig is None else tray.pig)
    h = mix_pigs(state, h)
    h = mix_places(state, h)
    h = mix(mix(h, state.cubes_left), cube_health(state))
    h = mix(h, len(state.shots))
    for shot in state.shots:
        h = mix(mix(mix(mix(mix(h, shot.pig), shot.target), shot.cell), shot.fired), shot.land)
    h = mix_shooting(state, h)
    h = mix_waiting(state, h)
    h = mix(mix(mix(h, int(state.finishing)), int(state.reviving)), state.tray_total)
    if state.unicorn["active"]:
        h = mix(mix(h, state.unicorn["charge"]), state.unicorn["need"])
    for module in MODULES:
        hook = getattr(module, "checksum", None)
        if hook is not None:
            h = hook(state, h)
    return h


def mix_pigs(state: State, h: int) -> int:
    h = mix(h, len(state.pigs))
    for pig_id in sorted(state.pigs):
        pig = state.pigs[pig_id]
        h = mix(mix(mix(mix(h, pig.id), pig.color), pig.ammo), PLACES.index(pig.place))
        h = mix(h, len(pig.tags))
        for tag in pig.tags:
            h = mix_text(h, tag)
    return h


def mix_places(state: State, h: int) -> int:
    """Queues, slots and the rescue queue."""
    h = mix(h, len(state.queues))
    for queue in state.queues:
        h = mix(h, len(queue))
        for pig_id in queue:
            h = mix(h, pig_id)
    h = mix(h, len(state.slots))
    for pig_id in state.slots:
        h = mix(h, -1 if pig_id is None else pig_id)
    h = mix(h, len(state.rescue))
    for pig_id in state.rescue:
        h = mix(h, pig_id)
    return h


def mix_shooting(state: State, h: int) -> int:
    """The shooters in order, every pig's fire timer and reservations, and every target's pending damage and claim."""
    h = mix(h, len(state.shooters))
    for pig_id in state.shooters:
        h = mix(h, pig_id)
    for pig_id in sorted(state.pigs):
        pig = state.pigs[pig_id]
        h = mix(mix(h, pig.next_fire), len(pig.reserved))
        for target_id, cell in pig.reserved:
            h = mix(mix(h, target_id), cell)
    for target in state.grid.targets:
        h = mix(mix(h, target.pending), int(target.claimed))
    return h


def mix_waiting(state: State, h: int) -> int:
    """Pigs waiting at the belt's exit, and when each pig can next be tapped."""
    h = mix(h, len(state.entrance))
    for pig_id, fail_tick in state.entrance:
        h = mix(mix(h, pig_id), fail_tick)
    for pig_id in sorted(state.pigs):
        h = mix(h, state.pigs[pig_id].free_at)
    return h


def cube_health(state: State) -> int:
    """Hits still needed by every living cube."""
    total = 0
    for target in state.grid.targets:
        if target.owner == 0 and not target.dead:
            total += target.health
    return total


def result(state: State) -> dict | None:
    """None while the level runs, else {"result", "tick", "kind", "name"}."""
    return state.over


def still(state: State) -> bool:
    """Nothing moving: no tray on the belt, no pig waiting at its exit, no shot in flight, no timer pending."""
    return not state.belt and not state.entrance and not state.shots and not state.timers


def cleared(state: State) -> int:
    """Whole percent of the level's starting cubes destroyed (0 for a level with no cubes)."""
    if state.cubes_start == 0:
        return 0
    return idiv((state.cubes_start - state.cubes_left) * 100, state.cubes_start)
