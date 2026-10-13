"""Bazooka teams, mortar teams and grenades: the weapons a soldier's own animation fires.

A bazooka man (both sides, the German one carries a Panzerschreck) always kneels and fires his whole 90-step
animation (S666 `bazooka_fire_crouch`, frames 611 to 701) at every chance. Its frame 634 lets the rocket go
(`bazookaFire`, F6:9756-9805): a clip that flies 35 pixels a step along the line from the bazooka man toward a random
member of the target, starting 36 pixels ahead of him and 17 up, and bursts (`bazookaImpact`, F6:9806-9813) as it
passes the x the target's leader stood at when it was fired.

A mortar carrier always kneels and fires his whole 202-step animation (S666 `mortar_fire_crouch`, frames 703 to 905).
Its frame 829 calls one mortar team round on the target's leader, or, during a Smoke Rounds order, a smoke round at
the ordered point (S666/frame_829); its frame 905 ends the cycle, and starts the next at once while the squad still
fires smoke (S666/frame_905).

A grenade is thrown from the 109-step throw (S666 `standing_throwGrenade`, frame 1416, then `rifle_fire_standing` with
no shot); it leaves the hand on frame 1436, which also charges the thrower's side 50 RP (S666/frame_1436). The
grenade clip (sprite 1580) lands near a random member of the target and bursts on its arc's last frame, 39 or 35
steps later.

When this runs (common/battle.py's step order): the hooks in step 2, as each soldier's timeline reaches its frame; a
rocket's flight and a grenade's burst with the strike clips after the timelines (common/blasts.py `run_rounds`); the
throw's start in the squad's turn (step 4) or on a player's order.
"""

import math
import typing as t

from . import anims
from .blasts import Round, call_strike, new_grenade, x10
from .boxes import Box
from .data import ORDER_COSTS
from .smoke import smoke_round

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

ROCKET_SPEED = 35  # bazookaSpeed, F6:11811: pixels a step along the rocket's line
ROCKET_AHEAD = 36  # bazookaXOffset, F6:11812: the rocket starts 36 pixels ahead of the bazooka man
ROCKET_RISE = 17  # and 17 up, F6:9761
ROCKET_SCATTER = 30  # bazookaAccuracy, F6:11813: the burst lands random(30) - 15 off the rocket's point, x then y
# A rocket aimed behind its own line of travel never passes its burst x; it is dropped once this far off the field
ROCKET_LOST = 1000
GRENADE_X = (40, 20)  # a grenade lands at the member's x + random(40) - 20, F6:8478-8485
GRENADE_Y = (20, 10)  # and y + random(20) - 10 at infantry, F6:8486-8489
GRENADE_Y_TANK = (10, 5)  # or y + random(10) - 5 at a tank, F6:8490-8493
THROW_LABEL = "standing_throwGrenade"
MORTAR_LABEL = "mortar_fire_crouch"
SMOKE_ROUNDS = 3  # specialRoundCount = 3, F6:6479: one smoke round a mortar cycle


def facing(side: str) -> int:
    """+1 for the American side, who advance to the right; -1 for the German"""
    return 1 if side == "british" else -1


def target_member(battle: "Battle", squad: "Squad") -> "Soldier | Tank | None":
    """targetSquad.members[random(members.length)]: a random member of the squad's target, drawn whenever the target
    has members"""
    target = squad.target
    if target is None or not target.members:
        return None
    return target.members[battle.random(len(target.members))]


def flight(side: str, x: float, y: float, angle: float, burst_x: float, width: float) -> tuple[float, float, int]:
    """The rocket's onEnterFrame (F6:9780-9803), run ahead: from the step after it is fired it moves one speed along
    its angle a step, and bursts on the first step it is at or past `burst_x` (the American side's at or right of it,
    the German's at or left). Returns its point and how many steps it flew, or -1 steps for a rocket that leaves the
    field without passing it"""
    step_x = math.cos(angle * math.pi / 180) * ROCKET_SPEED
    step_y = math.sin(angle * math.pi / 180) * ROCKET_SPEED
    ahead = facing(side)
    steps = 0
    while -ROCKET_LOST < x < width + ROCKET_LOST:
        x -= step_x
        y -= step_y
        steps += 1
        if ahead * x >= ahead * burst_x:
            return x, y, steps
    return x, y, -1


def rocket(battle: "Battle", soldier: "Soldier") -> None:
    """The bazooka round leaves (S666/frame_634, bazookaFire F6:9756-9805): it aims at a random member of the target
    and bursts where it passes the target leader's x as it was now, through the blasts' list so it lands with the
    other clips. With no target member left, the original's rocket flies off with nothing to burst at; none is fired.
    The rocket's turn and flame are the page's."""
    squad = soldier.squad
    owner = squad.side
    aim = target_member(battle, squad)
    if aim is None:
        return
    leader = squad.target.members[0]
    start_x = soldier.x + facing(owner) * ROCKET_AHEAD
    start_y = soldier.y - ROCKET_RISE
    angle = math.degrees(math.atan2(soldier.y - aim.y, soldier.x - aim.x))
    x, y, steps = flight(owner, start_x, start_y, angle, leader.x, battle.width)
    burst = -1 if steps < 0 else battle.step + steps
    battle.event("rocket", soldier.id, x10(start_x), x10(start_y), x10(x), x10(y), burst)
    if steps < 0:
        return
    shot = Round(0, "bazooka", owner, x, y, 0)
    shot.blast_step = burst
    shot.scatter = ROCKET_SCATTER
    battle.rounds.append(shot)


def mortar_round(battle: "Battle", soldier: "Soldier") -> None:
    """The mortar fires (S666/frame_829): while the squad has smoke rounds to fire, one smoke round at the ordered
    point (smokeStrike, common/smoke.py); else the smoke order is over and a mortar team round falls on the target's
    leader (mortarStrike, common/blasts.py). With no target leader the original aims at nothing and hits nothing;
    no round is fired."""
    squad = soldier.squad
    if squad.smoke_rounds > 0:
        squad.smoke_rounds -= 1
        smoke_round(battle, squad.smoke_target[0], squad.smoke_target[1], squad.side)
        return
    squad.firing_smoke = False
    target = squad.target
    if target is None or not target.members:
        return
    leader = target.members[0]
    call_strike(battle, "mortar", leader.x, leader.y, squad.side)


def mortar_end(battle: "Battle", soldier: "Soldier") -> None:
    """The mortar cycle's last frame (S666/frame_905) has stopped the soldier; while the squad fires smoke it starts
    the next cycle at once, whatever target finding has done"""
    if soldier.squad.firing_smoke:
        soldier.goto(battle, MORTAR_LABEL, True)


def start_smoke_rounds(battle: "Battle", squad: "Squad", x: float, y: float) -> None:
    """A Smoke Rounds order (F6:6476-6483): the mortar fires 3 smoke rounds at (x, y), one a cycle, starting a fresh
    cycle now. Target finding skips the squad until the cycle after the last smoke round. The 100 RP is the order's
    (common/orders.py)."""
    squad.smoke_rounds = SMOKE_ROUNDS
    squad.smoke_target = (x, y)
    squad.firing_smoke = True
    leader = squad.leader
    if leader is not None:
        leader.goto(battle, MORTAR_LABEL, True)


def throw_grenade(battle: "Battle", soldier: "Soldier", target: "Squad | None") -> bool:
    """Start a frag throw (throwGrenadeCommand F6:8547-8555, the CPU's throw F6:2501-2508): the soldier plays the
    throw from its start whatever it was doing, and the grenade leaves 20 steps in (`release_grenade`). Every throw is
    a frag grenade (B37). Nothing happens without a target. True when the throw started"""
    if target is None:
        return False
    soldier.gren_type = "handGrenade"
    soldier.flags["throwingGrenade"] = True
    soldier.goto(battle, THROW_LABEL, True)
    return True


def grenade_box(x: float, y: float, rotation: float, flip: bool) -> Box:
    """The grenade's collision clip (sprite 1581) on the field, never widened (B7): in a grenade clip turned by
    `rotation` degrees and flipped upside down for an American throw (F6:8495-8503), then measured the way hitTest
    measures it, as the box around the turned corners"""
    left, top, right, bottom = anims.BOXES["grenade"]
    flip_y = -1 if flip else 1
    turn = math.radians(rotation)
    cos, sin = math.cos(turn), math.sin(turn)
    xs = []
    ys = []
    for corner_x, corner_y in ((left, top), (right, top), (left, bottom), (right, bottom)):
        corner_y *= flip_y
        xs.append(corner_x * cos - corner_y * sin)
        ys.append(corner_x * sin + corner_y * cos)
    return (x + min(xs), y + min(ys), x + max(xs), y + max(ys))


def release_grenade(battle: "Battle", soldier: "Soldier") -> None:
    """The frag grenade leaves the hand (S666/frame_1436, throwGrenade F6:8473-8506): it lands near a random member
    of the squad's target, turned along the throw, and bursts at the end of arc 1 or 2. The throw costs the thrower's
    side 50 RP, kept at 0 or more, even when the target is gone and nothing is thrown."""
    squad = soldier.squad
    owner = squad.side
    aim = target_member(battle, squad)
    if aim is not None:
        x = aim.x + battle.random(GRENADE_X[0]) - GRENADE_X[1]
        spread = GRENADE_Y_TANK if squad.target.kind == "tank" else GRENADE_Y
        y = aim.y + battle.random(spread[0]) - spread[1]
        angle = math.floor(math.degrees(math.atan2(-(soldier.y - aim.y), soldier.x - aim.x)) + 0.5)
        arc = battle.random(2) + 1
        new_grenade(battle, soldier, x, y, arc, grenade_box(x, y, -angle, owner == "british"))
    soldier.gren_type = "handGrenade"
    battle.adjust_rp(owner, -ORDER_COSTS["grenade"])
