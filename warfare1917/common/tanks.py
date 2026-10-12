"""Tanks and grenades.

A tank squad has one member, the tank, with two gun timelines (common/timeline.py): the main gun (sprite 650), whose
96-frame firing animation is its reload, and the machine gun (sprite 647), three frames a shot. The frame scripts turn
the tank's `firing` and `firingSecondary` flags on and off, and the engine only fires a gun whose flag is off
(tankMoving and tankEngaging, F5:2019-2113).

Assault soldiers throw grenades instead of shooting now and then (F5:1567-1574, 1700-1707). The throw animation's
frame 1514 lets the grenade go (S626/frame_1514 calls throwGrenade, F5:5759-5791); the grenade clip (sprite 1376) then
flies one of two arcs and bursts on its frame 41 or 83, where it calls explosiveHit for both sides.

When this runs (common/battle.py's step order): the tank states in step 5, each squad's turn; the grenade release in
step 2, when the thrower's timeline reaches it.
"""

import math
import typing as t

from . import anims
from .blasts import new_grenade, new_shell
from .boxes import Box
from .combat import hit
from .data import CONQUER_AREA, UPGRADE_EFFECTS

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

CREEP_GAP = 50  # an engaging tank creeps on while 50 or more pixels short of its target's leader, F5:2056, 2064
SHELL_SCATTER = (200, 100)  # the shell lands at the leader's x + random(200) - 100, F5:2078
SHELL_DROP = (50, 25)  # and y + random(50) - 25
GUN_REST = (20, 10)  # the main gun's counters reset once waitCounter >= random(20) + 10, F5:2085
MG_BURST = (5, 3)  # the machine gun fires while mgBurstCounter <= random(5) + 3, F5:2090
MG_REST = (60, 30)  # then rests until mgWaitCounter >= random(60) + 30, F5:2109
GRENADE_AT_TANK = 2  # an engaging assault soldier throws at a tank 1 time in 2, F5:1569
GRENADE_AT_TRENCH = 6  # an assaulting one 1 time in 6, F5:1702
GRENADE_AIM = 30  # a grenade aims 30 pixels short of the target's leader, F5:5765, 5769
GRENADE_SCATTER = (40, 20)  # then random(40) - 20 along x
GRENADE_DROP = (20, 10)  # y + random(20) + 10 at infantry, F5:5773
GRENADE_DROP_TANK = (10, 5)  # y + random(10) - 5 at a tank, F5:5777


def facing(side: str) -> int:
    """+1 for the British, who advance to the right; -1 for the Germans"""
    return 1 if side == "british" else -1


def flash_round(value: float) -> int:
    """ActionScript's Math.round: halves go up"""
    return math.floor(value + 0.5)


def crossed(battle: "Battle", side: str, x: float) -> bool:
    """A tank at or past the conquer line (F5:2033, 2041, 2059, 2067)"""
    if side == "british":
        return x >= battle.width - CONQUER_AREA
    return x <= CONQUER_AREA


def leader_of(squad: "Squad | None") -> "Soldier | Tank | None":
    """The original's `enemyTarget.members[0]`: None when there is no target or it has no members left"""
    if squad is None or not squad.members:
        return None
    return squad.members[0]


def state_tank_moving(battle: "Battle", squad: "Squad") -> None:
    """tankMoving (F5:2019-2048): forward at the squad's speed, then the conquer line"""
    for tank in battle.newest_first(squad.members):
        if not tank.alive:
            continue
        tank.x += facing(squad.side) * squad.speed
        if crossed(battle, squad.side, tank.x):
            battle.conquer(squad.side)


def creep(battle: "Battle", squad: "Squad", tank: "Tank") -> None:
    """An engaging tank creeps on at half speed while its target isn't a tank and it is at least 50 pixels short of
    the target's leader (F5:2056-2071). With no leader to measure from, the original's comparison fails"""
    target = squad.target
    leader = leader_of(target)
    if not tank.alive or leader is None or target.kind == "tank":
        return
    ahead = facing(squad.side)
    if ahead * tank.x <= ahead * (leader.x - ahead * CREEP_GAP):
        tank.x += ahead * squad.speed / 2
        if crossed(battle, squad.side, tank.x):
            battle.conquer(squad.side)


def tank_shell(battle: "Battle", tank: "Tank") -> None:
    """The main gun fires (F5:2076-2079): its firing animation plays from now, and the shell (tankRound, F5:3713-3720)
    lands scattered around the target's leader"""
    tank.gun.goto_and_play("firing")
    tank.gun_stamp = battle.step
    leader = leader_of(tank.squad.target)
    x = leader.x + battle.random(SHELL_SCATTER[0]) - SHELL_SCATTER[1]
    y = leader.y + battle.random(SHELL_DROP[0]) - SHELL_DROP[1]
    new_shell(battle, tank, x, y)


def main_gun(battle: "Battle", squad: "Squad", tank: "Tank") -> None:
    """The main gun's chance (F5:2074-2089): it fires when its target has a member and it isn't still reloading. Its
    burst counter starts at 1 (createSoldier F5:1204), so a tank's first shot waits for the first reset"""
    if leader_of(squad.target) is not None and tank.alive and tank.burst_counter < 1 and not tank.flags["firing"]:
        tank.burst_counter += 1
        tank_shell(battle, tank)
    else:
        tank.wait_counter += 1
    if tank.wait_counter >= battle.random(GUN_REST[0]) + GUN_REST[1]:
        tank.wait_counter = 0
        tank.burst_counter = 0


def machine_gun(battle: "Battle", squad: "Squad", tank: "Tank") -> None:
    """The machine gun's chance (F5:2090-2113): a shot while the burst lasts and the gun isn't mid-shot, else an idle
    step, and the burst starts over after the rest. Both limits are drawn fresh at every check; the burst limit only
    while the tank is alive, as the original's `&&` stops there"""
    target = squad.target
    firing = False
    if tank.alive:
        firing = tank.mg_burst_counter <= battle.random(MG_BURST[0]) + MG_BURST[1]
    if firing and not tank.flags["firingSecondary"] and target is not None:
        tank.mg_burst_counter += 1
        tank.mg.goto_and_play("firing")
        tank.mg_stamp = battle.step
        leader = leader_of(target)
        battle.event("shot", tank.id, 0 if leader is None else leader.id, int(target.kind == "tank"))
        hit(battle, tank, target)
    else:
        tank.mg_wait_counter += 1
    if tank.mg_wait_counter >= battle.random(MG_REST[0]) + MG_REST[1]:
        tank.mg_wait_counter = 0
        tank.mg_burst_counter = 0


def state_tank_engaging(battle: "Battle", squad: "Squad") -> None:
    """tankEngaging (F5:2051-2115): creep, then the main gun, then the machine gun, for each member newest first"""
    for tank in battle.newest_first(squad.members):
        creep(battle, squad, tank)
        main_gun(battle, squad, tank)
        machine_gun(battle, squad, tank)


TANK_STATES = {"tankMoving": state_tank_moving, "tankEngaging": state_tank_engaging}


def tank_act(battle: "Battle", squad: "Squad") -> None:
    """A tank squad's turn in its state. A destroyed tank's squad ("tankDead") does nothing (F5:2049)"""
    handler = TANK_STATES.get(squad.state)
    if handler is not None:
        handler(battle, squad)


def grenade_pick(battle: "Battle", squad: "Squad", soldier: "Soldier", chance: int) -> None:
    """An assault soldier's firing chance may become a throw, 1 time in `chance` (F5:1567-1574, 1700-1707). The throw
    animation turns `firing` on, so the shot that would follow doesn't happen"""
    if soldier.flags["throwingGrenade"] or squad.kind != "assault":
        return
    if battle.random(chance) == 0:
        soldier.flags["throwingGrenade"] = True
        soldier.goto(battle, "standing_throwGrenade", True)


def grenade_box(x: float, y: float, rotation: float, flip: bool, wide: bool) -> Box:
    """The grenade's collision clip (sprite 1377) on the field: three times as wide with High Explosive, in a grenade
    clip turned by `rotation` degrees and flipped upside down for a British throw (F5:5784-5788), then measured
    the way hitTest measures it, as the box around the turned corners"""
    left, top, right, bottom = anims.BOXES["grenade"]
    if wide:
        widen = UPGRADE_EFFECTS["grenade_width"]["value"]
        left, right = left * widen, right * widen
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


def throw_grenade(battle: "Battle", soldier: "Soldier") -> None:
    """The grenade leaves the hand (throwGrenade, F5:5759-5791): it lands short of the target's leader, turned by the
    throw's angle, and bursts at the end of one of its two arcs. With no leader left to aim at, the original's
    grenade lands nowhere; its rolls are still drawn"""
    squad = soldier.squad
    owner = squad.side
    leader = leader_of(squad.target)
    x = battle.random(GRENADE_SCATTER[0]) - GRENADE_SCATTER[1] - facing(owner) * GRENADE_AIM
    if leader is not None and squad.target.kind == "tank":
        y = battle.random(GRENADE_DROP_TANK[0]) - GRENADE_DROP_TANK[1]
    else:
        y = battle.random(GRENADE_DROP[0]) + GRENADE_DROP[1]
    arc = battle.random(2) + 1
    if leader is None:
        return
    x += leader.x
    y += leader.y
    angle = flash_round(math.degrees(math.atan2(-(soldier.y - leader.y), soldier.x - leader.x)))
    wide = owner == "british" and battle.sides[owner].has("grenade_width")
    new_grenade(battle, soldier, x, y, arc, wide, grenade_box(x, y, -angle, owner == "british", wide))
