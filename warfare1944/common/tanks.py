"""Tanks and the bunker.

A tank squad has one member, the tank (sprite 913), with three timelines (common/timeline.py): the main gun (sprite
700), whose 96-frame firing animation is its reload, the machine gun (sprite 696), three frames a shot, and the turret
(sprite 711 American, 910 German), which turns to face the target's lane. The bunker (sprite 929) is a CPU squad with
one member like a tank's that never moves, never fires its main gun, and turns its own turret (sprite 924) and fires
its own machine gun (sprite 923). The guns' frame scripts turn the member's `firing` and `firingSecondary` flags on and
off; the turret keeps its own flags, and a gun fires only while its own flag is off and the turret is not turning
(B41: in the original a turn's end also cleared the gun flags and cut a reload short).

When this runs (common/battle.py's step order): the tank and bunker states in step 4, each squad's turn; the gun and
turret timelines in step 2.
"""

import math
import typing as t

from .blasts import new_shell
from .combat import hit
from .data import BUNKER, CONQUER_AREA
from .morale import flank

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

CREEP_GAP = 50  # an engaging tank creeps on while 50 or more pixels short of its target's leader, F6:3216, 3236
SHELL_SCATTER = (200, 100)  # the shell lands at the leader's x + random(200) - 100, F6:3294
SHELL_DROP = (50, 25)  # and y + random(50) - 25
GUN_REST = (20, 10)  # the main gun's counters reset once waitCounter >= random(20) + 10, F6:3301
MG_BURST = (5, 3)  # a tank's machine gun fires while mgBurstCounter <= random(5) + 3, F6:3306
MG_REST = (60, 30)  # then rests until mgWaitCounter >= random(60) + 30, F6:3332
FLANK_LANES = (1, 3)  # a tank past the far edge in lane 1 or 3 drives off the field, F6:3177, 3193
CONQUER_LANE = 2  # a tank past the conquer line in lane 2 wins, F6:3182, 3198
# The six turns, in the order the original checks them (F6:3253-3288, bunker F6:3068-3103): where the target's lane
# is from the member's own (-1 a lane above, 1 below, 0 the same), the turret's facing now, and the turn to play
TURNS = (
    (-1, "straight", "moveUp"),
    (1, "straight", "moveDown"),
    (-1, "down", "moveUpFromDown"),
    (1, "up", "moveDownFromUp"),
    (0, "down", "moveStraightFromDown"),
    (0, "up", "moveStraightFromUp"),
)


def facing(side: str) -> int:
    """+1 for the British, who advance to the right; -1 for the Germans"""
    return 1 if side == "british" else -1


def flash_round(value: float) -> int:
    """ActionScript's Math.round: halves go up"""
    return math.floor(value + 0.5)


def leader_of(squad: "Squad | None") -> "Soldier | Tank | None":
    """The original's `enemyTarget.members[0]`: None when there is no target or it has no members left"""
    if squad is None or not squad.members:
        return None
    return squad.members[0]


def lane_end(battle: "Battle", squad: "Squad", tank: "Tank") -> bool:
    """The far end of the lane for a tank, read from the tank itself (F6:3175-3205, 3222-3247, B43). Past the conquer
    line, a tank in lane 2 wins; one in lane 1 or 3 drives off once past the edge itself (the American side at the
    field's width or beyond, the German side below 0). True when the squad left the field"""
    if squad.side == "british":
        near, past = tank.x >= battle.width - CONQUER_AREA, tank.x >= battle.width
    else:
        near, past = tank.x <= CONQUER_AREA, tank.x < 0
    if not near:
        return False
    if past and squad.lane in FLANK_LANES:
        flank(battle, squad)
        return True
    if squad.lane == CONQUER_LANE:
        battle.conquer(squad.side)
    return False


def state_tank_moving(battle: "Battle", squad: "Squad") -> None:
    """tankMoving (F6:3162-3209): forward at the squad's speed (the owner's Engine Upgrade and a broken engine are in
    it), then the lane's end. The wheels turn on the page."""
    # for (m in members), F6:3164
    for tank in battle.newest_first(squad.members):
        if not tank.alive:
            continue
        tank.x += facing(squad.side) * squad.speed
        if lane_end(battle, squad, tank):
            return


def creep(battle: "Battle", squad: "Squad", tank: "Tank") -> bool:
    """An engaging tank creeps on at half speed while its target isn't a tank and it is at least 50 pixels short of
    the target's leader (F6:3216-3249). With no leader to measure from, the original's comparison fails. True when
    the squad drove off the field"""
    target = squad.target
    leader = leader_of(target)
    if not tank.alive or leader is None or target.kind == "tank":
        return False
    ahead = facing(squad.side)
    if ahead * tank.x <= ahead * (leader.x - ahead * CREEP_GAP):
        tank.x += ahead * squad.speed / 2
        return lane_end(battle, squad, tank)
    return False


def turning(tank: "Tank") -> bool:
    """The turret is mid-turn: from the turn's first frame to its last (movingTurret, S711, S910, S924)"""
    return bool(tank.turret.flags.get("movingTurret"))


def turn_turret(battle: "Battle", tank: "Tank", lane: int | None) -> None:
    """Turn the turret to face `lane`, the target's, unless it already turned there for this target or is turning
    (F6:3251-3289, bunker F6:3066-3104). A new target clears `turretInPosition` (common/targeting.py). With no target
    nothing turns; with the target in its own lane and the turret straight, none of the six turns fits, so it stays."""
    flags = tank.turret.flags
    if lane is None or flags.get("turretInPosition") or flags.get("movingTurret"):
        return
    own = tank.squad.lane
    where = (lane > own) - (lane < own)
    for want, facing_now, label in TURNS:
        if where == want and flags.get("state") == facing_now:
            tank.turret.goto_and_play(label)
            tank.turret_stamp = battle.step
            return


def target_lane(squad: "Squad") -> int | None:
    return None if squad.target is None else squad.target.lane


def tank_shell(battle: "Battle", tank: "Tank") -> None:
    """The main gun fires (F6:3292-3296): its firing animation, the reload, plays from now, and the shell (tankRound,
    F6:5608-5615) lands scattered around the target's leader and bursts 5 steps later"""
    tank.gun.goto_and_play("firing")
    tank.gun_stamp = battle.step
    leader = leader_of(tank.squad.target)
    x = leader.x + battle.random(SHELL_SCATTER[0]) - SHELL_SCATTER[1]
    y = leader.y + battle.random(SHELL_DROP[0]) - SHELL_DROP[1]
    new_shell(battle, tank, x, y)


def gun_ready(tank: "Tank") -> bool:
    """The main gun can fire: the member has one (the bunker's is disabled every step, F6:3105), it isn't broken, it
    isn't reloading (`firing`, sprite 700 frames 7 to 103) and the turret isn't turning"""
    if tank.gun is None or "gun" in tank.broken:
        return False
    return not tank.flags["firing"] and not turning(tank)


def main_gun(battle: "Battle", squad: "Squad", tank: "Tank") -> None:
    """The main gun's chance (F6:3290-3305, bunker F6:3106-3121): it fires when its target has a member, its burst
    counter is under 1 and the gun is ready. Its burst counter starts at 1 (createSoldier F6:1715), so a tank's first
    shot waits for the first reset. The reset's roll is drawn every step, the bunker's too"""
    if leader_of(squad.target) is not None and tank.alive and tank.burst_counter < 1 and gun_ready(tank):
        tank.burst_counter += 1
        tank_shell(battle, tank)
    else:
        tank.wait_counter += 1
    if tank.wait_counter >= battle.random(GUN_REST[0]) + GUN_REST[1]:
        tank.wait_counter = 0
        tank.burst_counter = 0


def machine_gun(battle: "Battle", squad: "Squad", tank: "Tank", burst: tuple[int, int], rest: tuple[int, int]) -> bool:
    """The machine gun's chance (F6:3306-3336, bunker F6:3122-3153): a shot while the burst lasts, the gun isn't
    broken or mid-shot and the turret isn't turning, else an idle step, and the burst starts over after the rest. Both
    limits are drawn fresh at every check; the burst limit only while the member is alive and the gun unbroken, as the
    original's `&&` stops there. True when it fired"""
    target = squad.target
    firing = False
    if tank.alive and "mg" not in tank.broken:
        firing = tank.mg_burst_counter <= battle.random(burst[0]) + burst[1]
    fired = firing and not tank.flags["firingSecondary"] and not turning(tank) and target is not None
    if fired:
        tank.mg_burst_counter += 1
        tank.mg.goto_and_play("firing")
        tank.mg_stamp = battle.step
        leader = leader_of(target)
        battle.event("shot", tank.id, 0 if leader is None else leader.id, int(target.kind == "tank"))
        hit(battle, tank, target)
    else:
        tank.mg_wait_counter += 1
    if tank.mg_wait_counter >= battle.random(rest[0]) + rest[1]:
        tank.mg_wait_counter = 0
        tank.mg_burst_counter = 0
    return fired


def state_tank_engaging(battle: "Battle", squad: "Squad") -> None:
    """tankEngaging (F6:3212-3338): creep, turn the turret, then the main gun, then the machine gun, for each member
    newest first"""
    # for (m in members), F6:3213
    for tank in battle.newest_first(squad.members):
        if creep(battle, squad, tank):
            return
        turn_turret(battle, tank, target_lane(squad))
        main_gun(battle, squad, tank)
        machine_gun(battle, squad, tank, MG_BURST, MG_REST)


def state_bunker_engaging(battle: "Battle", squad: "Squad") -> None:
    """bunkerEngaging (F6:3061-3161): turn the turret, the main gun's chance (never taken), then the machine gun with
    longer bursts and rests. After 200 rounds it reloads: its burst count jumps past any limit and its rest count
    starts at -300, a rest of 360 to 519 steps"""
    # for (m in members), F6:3063
    for bunker in battle.newest_first(squad.members):
        turn_turret(battle, bunker, target_lane(squad))
        main_gun(battle, squad, bunker)
        if machine_gun(battle, squad, bunker, BUNKER["burst"], BUNKER["rest"]):
            bunker.round_count -= 1
        if bunker.round_count <= 0:
            bunker.mg_burst_counter = BUNKER["reload_burst"]
            bunker.mg_wait_counter = BUNKER["reload_rest"]
            bunker.round_count = BUNKER["rounds"]


TANK_STATES = {"tankMoving": state_tank_moving, "tankEngaging": state_tank_engaging}


def tank_act(battle: "Battle", squad: "Squad") -> None:
    """A tank squad's turn in its state. A destroyed tank's squad ("tankDead") does nothing (F6:3210)"""
    handler = TANK_STATES.get(squad.state)
    if handler is not None:
        handler(battle, squad)


def make_bunker(battle: "Battle", side: str, lane: int, x: float) -> "Squad":
    """createSquad for a bunker (F6:1486, 1645-1651): one member at `x` in lane - 100, 1,200 health, the main gun off
    and 200 rounds in its machine gun. It is its side's objective and counts as a squad deployed."""
    return battle.place_squad(side, "bunker", lane, x, True)


def bunker_act(battle: "Battle", squad: "Squad") -> None:
    """The bunker's turn: it waits ("bunkerIdle", F6:3059) until target finding gives it a target"""
    if squad.state == "bunkerEngaging":
        state_bunker_engaging(battle, squad)
