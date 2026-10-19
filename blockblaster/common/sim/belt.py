"""The belt: its trays, how they move and keep apart, where a pig on one stands, and which side of the picture it faces.

A tray's pos is how far it has run along the lap from the start point, in L. board.json's belt table holds a point
every 100 L of the lap in picture space, so neither side ever evaluates the curve. web/sim/belt.js mirrors this file.
"""

from __future__ import annotations

from . import base
from .mathx import idiv
from .numbers import BELT_SPEED, BELT_SPEED_FINISH, TRAY_PUSH_MAX, TRAY_SPACING

# Sides of the picture a pig can face (ShootersOffenseController.Side)
LEFT = 0
RIGHT = 1
BOTTOM = 2
TOP = 3
# The way a pig on each side faces: straight into the picture, picture space
INWARD = {LEFT: (1, 0), RIGHT: (-1, 0), BOTTOM: (0, 1), TOP: (0, -1)}


def tray_total(state: base.State) -> int:
    """Trays the belt carries: the level's ConveyorLimit plus one per Tray booster used."""
    return state.tray_total


def free_trays(state: base.State) -> int:
    """Trays neither reserved nor carrying a pig (ConveyorController$$CanReceiveItemCount, RVA 0x58A8FFC)."""
    return state.tray_total - len(state.belt)


def reserve(state: base.State, pig_id: int) -> base.Tray:
    """Hold a tray for a pig about to hop on. It waits off the lap until start_tray."""
    tray = base.Tray(id=state.tray_seq, pos=0, started=False, pig=pig_id)
    state.tray_seq += 1
    # Started trays stay at the front of the list, newest first; reserved ones wait behind them
    state.belt.append(tray)
    return tray


def find_tray(state: base.State, tray_id: int) -> base.Tray | None:
    for tray in state.belt:
        if tray.id == tray_id:
            return tray
    return None


def start_tray(state: base.State, tray_id: int) -> None:
    """Timer: the tray enters the lap at the start point and becomes the newest tray
    (ConveyorController$$TryActivateSlot, RVA 0x58A8C10). It first moves on the next tick."""
    tray = find_tray(state, tray_id)
    if tray is None:
        return
    state.belt.remove(tray)
    tray.started = True
    tray.pos = 0
    state.belt.insert(0, tray)
    add_shooter(state, tray.pig)
    base.emit(state, "tray_started", {"tray": tray.id, "pig": tray.pig})


def add_shooter(state: base.State, pig_id: int) -> None:
    """A pig whose tray just started joins the shooters, its fire timer fresh so it may fire at once
    (ShootersOffenseController$$AddShooterFromGameObject, RVA 0x5453274)."""
    state.shooters.append(pig_id)
    state.pigs[pig_id].next_fire = 0


def remove_shooter(state: base.State, pig_id: int) -> None:
    if pig_id in state.shooters:
        state.shooters.remove(pig_id)


def remove(state: base.State, pig_id: int) -> None:
    """Take a pig's tray off the belt, started or still reserved; the tray is free again at once
    (ConveyorController$$Remove, RVA 0x58A6FC0)."""
    for tray in state.belt:
        if tray.pig == pig_id:
            state.belt.remove(tray)
            break
    remove_shooter(state, pig_id)


def started_trays(state: base.State) -> list[base.Tray]:
    return [tray for tray in state.belt if tray.started]


def move_trays(state: base.State) -> tuple[list[int], list[int]]:
    """Phase 2 (ConveyorController$$Update, RVA 0x58A5CC0): every started tray runs on, the spacing pushes trays that
    sit too close, then trays at the lap's end loop (auto-finisher) or leave. Returns the pigs that passed the
    fail-warning checkpoint and the pigs that left, both in list order."""
    trays = started_trays(state)
    if not trays:
        return [], []
    if state.finishing:
        # Looping trays wrap to the start, so the list is put back in lap order first (newest, lowest pos, first)
        trays.sort(key=lambda tray: tray.pos)
        state.belt = trays + [tray for tray in state.belt if not tray.started]
    end = state.belt_path["end"]
    speed = BELT_SPEED_FINISH if state.finishing else BELT_SPEED
    ran = [min(end, tray.pos + speed) for tray in trays]
    pushed = push_targets(ran, end)
    checkpoint = state.belt_path["checkpoint"]
    crossed = []
    for index, tray in enumerate(trays):
        old = tray.pos
        tray.pos = settle(tray.pos, ran[index], pushed[index])
        if old < checkpoint <= tray.pos:
            crossed.append(tray.pig)
    return crossed, reach_end(state, end)


def push_targets(ran: list[int], end: int) -> list[int]:
    """Where each tray must be to stay TRAY_SPACING ahead of the tray behind it, working from the newest tray forward
    (ConveyorController$$EnforceSpacing, RVA 0x58A622C). Nothing is pushed past the lap's end."""
    pushed = list(ran)
    for index in range(len(ran) - 1):
        need = min(end, pushed[index] + TRAY_SPACING)
        pushed[index + 1] = min(end, max(pushed[index + 1], need, ran[index + 1]))
    return pushed


def settle(old: int, ran: int, pushed: int) -> int:
    """A pushed tray closes on its pushed spot at most TRAY_PUSH_MAX a tick from where it was, never falling behind
    where the belt alone would take it (the second pass of ConveyorController$$Update)."""
    if ran >= pushed:
        return ran
    if pushed - old > TRAY_PUSH_MAX:
        return max(ran, old + TRAY_PUSH_MAX)
    return pushed


def reach_end(state: base.State, end: int) -> list[int]:
    """Trays at the lap's end, in list order: while the auto-finisher runs they loop unless a feature holds them to
    the normal exit. A leaving tray is taken out of the list at once and the walk moves on
    to the next index, so the tray behind it in the list waits a tick, as the original's loop does. Returns the pigs
    that left."""
    exited = []
    index = 0
    while index < len(state.belt):
        tray = state.belt[index]
        if tray.started and tray.pos >= end:
            if state.finishing and keeps_looping(state, tray.pig):
                tray.pos = 0
            else:
                state.belt.pop(index)
                remove_shooter(state, tray.pig)
                base.emit(state, "lap_end", {"tray": tray.id, "pig": tray.pig})
                exited.append(tray.pig)
        index += 1
    return exited


def keeps_looping(state: base.State, pig_id: int) -> bool:
    """While the auto-finisher runs a tray goes back to the start instead of leaving, unless a feature says its pig
    must leave (ConveyorStayInInfiniteLoopCondition$$Call, RVA 0x5908258)."""
    for module in base.MODULES:
        hook = getattr(module, "keep_looping", None)
        if hook is not None and not hook(state, state.pigs[pig_id]):
            return False
    return True


def point(state: base.State, pos: int) -> tuple[int, int, int]:
    """The lap point pos L from the start point, picture space, and the index of the table segment it sits on."""
    path = state.belt_path
    points = path["points"]
    step = path["step"]
    seg = min(len(points) - 2, idiv(pos, step))
    part = pos - seg * step
    x0, y0 = points[seg]
    x1, y1 = points[seg + 1]
    return x0 + idiv((x1 - x0) * part, step), y0 + idiv((y1 - y0) * part, step), seg


def position(state: base.State, tray: base.Tray) -> tuple[int, int]:
    """Where the pig on this tray shoots from, picture space, L. Before every shot the pig turns to face straight
    into the picture from its side (ShootersOffenseController$$LookAtDirection, RVA 0x5452BE0), so its shoot point
    (board.json weapon, [right, up, forward]) sits forward along that side's inward direction. Its height is
    muzzle_height."""
    x, y, _ = point(state, tray.pos)
    fx, fy = INWARD[side(state, tray)]
    right, _, forward = state.weapon
    # Seen from above, the pig's right is its forward turned a quarter clockwise
    return x + right * fy + forward * fx, y - right * fx + forward * fy


def muzzle_height(state: base.State) -> int:
    """The shoot point's height above the picture, L: the belt's surface plus the shoot point's height on the pig."""
    return state.belt_path["height"] + state.weapon[1]


def side(state: base.State, tray: base.Tray) -> int:
    """The side of the picture the pig on this tray shoots from, by where the pig stands
    (ShootersOffenseController$$GetShooterSide, RVA 0x54520C4): Left or Right when |x| >= |y|, else Bottom or Top."""
    x, y, _ = point(state, tray.pos)
    if abs(x) >= abs(y):
        return RIGHT if x >= 0 else LEFT
    return BOTTOM if y < 0 else TOP
