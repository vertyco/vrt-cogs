"""The state every simulation module shares: pig, tray and state records, timers and events.

Every other module in this package imports this one and none imports it back, so any module imports on its own.
web/sim/base.js mirrors this file function for function.

The state is plain data: timers are records [tick, seq, kind, args] looked up by kind, never closures, so
copy.deepcopy copies a whole state.
"""

import typing as t
from dataclasses import dataclass, field

from . import grid as gridx
from .level import Level
from .rng import Rng

# Where a pig is. "exit" is the line at the belt's exit where pigs wait for a free slot
PLACES = ["queue", "slot", "belt", "rescue", "gone", "held", "exit"]

# The fixed order inside one tick (taps are applied before the tick starts, in phase 1)
PHASE_TAPS = 1
PHASE_BELT = 2
PHASE_SHOOT = 3
PHASE_FEATURES = 4
PHASE_SHOTS = 5
PHASE_CHECKS = 6
PHASE_RELEASE = 7

# Every feature module, in feature-number order. The core calls their hooks in this order and skips missing ones
MODULES: list[t.Any] = []

FNV_START = 2166136261
FNV_PRIME = 16777619
MASK = 0xFFFFFFFF

# timer kind -> (phase it fires in, handler(state, args))
TIMER_KINDS: dict[str, tuple[int, t.Callable[["State", t.Any], None]]] = {}


@dataclass
class Pig:
    id: int
    color: int
    ammo: int
    place: str  # one of PLACES
    tags: list[str] = field(default_factory=list)
    next_fire: int = 0  # beat its next shot is due (ShootersOffenseController's next-fire table; 0 for none)
    reserved: list[list[int]] = field(default_factory=list)  # [target id, cell] with a shot of this pig in flight
    free_at: int = 0  # the first tick it can be tapped after hopping into a slot (Shooter.IsMoving until then)


@dataclass
class Tray:
    id: int
    pos: int  # L along the lap from the start point
    started: bool
    pig: int | None


@dataclass
class State:
    level: Level
    seed: int
    belt_path: dict  # board.json's belt: points every 100 L along the lap, picture space
    weapon: list[int]  # the pig's shoot point in its own axes, L
    rng: Rng
    grid: gridx.Grid
    tick: int = 0
    seq: int = 0  # timer order among timers due at the same tick
    pigs: dict[int, Pig] = field(default_factory=dict)
    queues: list[list[int]] = field(default_factory=list)  # pig ids, front first
    slots: list[int | None] = field(default_factory=list)
    rescue: list[int] = field(default_factory=list)
    entrance: list[list[int]] = field(default_factory=list)  # [pig id, tick it fails at] waiting for a slot, in order
    belt: list[Tray] = field(default_factory=list)  # newest first
    tray_total: int = 0
    tray_seq: int = 0  # the next tray's id
    shooters: list[int] = field(default_factory=list)  # pigs on started trays, in the order their trays started
    shots: list[t.Any] = field(default_factory=list)  # aim.Shot, in firing order
    timers: list[list] = field(default_factory=list)  # [tick, seq, kind, args]
    events: list[dict] = field(default_factory=list)  # this tick's events, for the page to draw
    features: dict[int, t.Any] = field(default_factory=dict)  # feature number -> that module's state
    cubes_start: int = 0
    cubes_left: int = 0
    finishing: bool = False  # the auto-finisher is running
    reviving: bool = False  # a revive is working: the belt and the exit line wait and pigs can't be tapped
    over: dict | None = None  # result(state)
    unicorn: dict = field(default_factory=dict)  # the Super Unicorn's bar, see unicorn.new_unicorn


def register_timer(kind: str, phase: int, handler: t.Callable[[State, t.Any], None]) -> None:
    TIMER_KINDS[kind] = (phase, handler)


def schedule(state: State, delay_ticks: int, kind: str, args: t.Any) -> None:
    """Run the kind's handler with args in its phase of tick state.tick + delay_ticks."""
    state.timers.append([state.tick + delay_ticks, state.seq, kind, args])
    state.seq += 1


def cancel(state: State, kind: str) -> None:
    """Drop every pending timer of this kind."""
    state.timers = [timer for timer in state.timers if timer[2] != kind]


def fire_timers(state: State, phase: int) -> None:
    """Every due timer of this phase, by (tick, seq), including ones a handler schedules for now."""
    while True:
        best = -1
        for index, timer in enumerate(state.timers):
            if timer[0] > state.tick or TIMER_KINDS[timer[2]][0] != phase:
                continue
            if best < 0 or (timer[0], timer[1]) < (state.timers[best][0], state.timers[best][1]):
                best = index
        if best < 0:
            return
        timer = state.timers.pop(best)
        TIMER_KINDS[timer[2]][1](state, timer[3])


def emit(state: State, name: str, data: dict) -> None:
    """Tell the features, and record it for the page."""
    state.events.append({"k": name, **data})
    for module in MODULES:
        hook = getattr(module, "on_event", None)
        if hook is not None:
            hook(state, name, data)


def call_hooks(state: State, name: str) -> None:
    for module in MODULES:
        hook = getattr(module, name, None)
        if hook is not None:
            hook(state)


def fail(state: State, kind: str, name: str) -> None:
    """The level is lost at this tick. The first fail stands."""
    if state.over is None:
        state.over = {"result": "failed", "tick": state.tick, "kind": kind, "name": name}
        emit(state, "failed", {"kind": kind, "name": name})


def live_pig_count(state: State) -> int:
    """Pigs still in play: in a queue, a slot, on the belt, in the rescue queue, waiting at the exit or held inside a
    feature (ShooterProvider's list, which the win check and the auto-finisher count, keeps nested shooters)."""
    return sum(1 for pig in state.pigs.values() if pig.place != "gone")


def mix(h: int, value: int) -> int:
    """One step of 32-bit FNV-1a over a whole number."""
    return ((h ^ (value & MASK)) * FNV_PRIME) & MASK


def mix_text(h: int, text: str) -> int:
    h = mix(h, len(text))
    for char in text:
        h = mix(h, ord(char))
    return h
