"""Who a squad aims at, and what it walks into: targets, officers, wire and mines.

Each function is one of the original's finders, walked in the original's order: `for (x in list)` loops go newest
first, `while` loops count up. The finders read a squad's first member (`members[0]`), as the original does, not its
first living one: a dead soldier leaves the list, but a dead tank stays in it with `alive` false.

When they run (common/battle.py's step order): `find_cover` then `find_enemy`, American then German each, on the
find tick (F6:10017-10030); `find_mines`, `find_wire` and `find_officers`, German before American each, on the medium tick
(F6:10002-10016).
"""

import math
import typing as t

from .blasts import mine_blast
from .data import (
    COVER_REACH,
    MINE_BOUNDARY,
    MINE_CHANCE,
    OFFICER_REACH,
    TARGETING_BUFFER,
)
from .squads import Cover, Squad, set_state, stop_firing

if t.TYPE_CHECKING:
    from .battle import Battle

NO_TARGET = 999999  # targetProx with no target, F6:1534, 3529
LANE_REACH = 1  # an enemy counts in the same lane or the next one (deployZone, F6:3466-3474)
BAZOOKA_REACH = 200  # a bazooka squad takes a tank out to its range + 200, F6:3475
WIRE_REACH = 50  # a leader within 50 pixels of a wire line is in it, F6:3773
# States the general pick never changes (F6:3503), and the states a squad keeps when it loses its target or skips the
# search (F6:3535, 3579)
# States in which a squad looks for no cover: in it, leaving it, or fighting in the open (F6:3654)
NO_COVER_SEARCH = ("exitTrench", "entrench", "engaging")
HOLD_ON_PICK = ("entrench", "exitTrench", "engaging")
KEEP_ON_LOSS = ("moving", "assaultTrench", "entrench", "exitTrench")
ARMOUR = ("tank", "bunker")


def head(squad: Squad):
    """The squad's `members[0]`, or None before its first member spawns or after its last one died"""
    return squad.members[0] if squad.members else None


def head_x(squad: Squad) -> float:
    """`members[0]._x`: NaN with no first member, so every comparison with it fails, as undefined does in a SWF"""
    member = head(squad)
    return math.nan if member is None else member.x


def head_alive(squad: Squad | None) -> bool:
    """`members[0].alive == true`: false with no squad, or a squad with no members"""
    member = None if squad is None else head(squad)
    return member is not None and member.alive


def in_band(battle: "Battle", x: float) -> bool:
    """Inside the targeting band, x 30 to width - 30 (targetingBuffer, F6:3498)"""
    return TARGETING_BUFFER < x < battle.width - TARGETING_BUFFER


def in_reach(squad: Squad, enemy: Squad) -> bool:
    """inZone (F6:3466-3474): lanes at most 1 apart, so the top and bottom lanes never see each other and the middle
    lane sees all three"""
    return abs(squad.lane - enemy.lane) <= LANE_REACH


def turn_turret(squad: Squad) -> None:
    """A tank or the bunker has a new target, or none: its turret must turn again (`turretInPosition`, F6:3487), a
    flag in the turret's own frame-script variables"""
    member = head(squad)
    if member is not None and squad.kind in ARMOUR:
        member.turret.flags["turretInPosition"] = False


def aim(squad: Squad, enemy: Squad, distance: float) -> None:
    squad.target = enemy
    squad.target_dist = distance


def clear_target(squad: Squad) -> None:
    squad.target = None
    squad.target_dist = NO_TARGET
    stop_firing(squad)


def walk_on(squad: Squad) -> None:
    """Back to Moving: no member is mid-change to a run or still in its run pose (F6:3537-3543, 3581-3587)"""
    squad.last_state = squad.state
    for member in squad.members:
        member.flags["changingToMove"] = False
        member.flags["moveAnim"] = False
    squad.state = "moving"


def drop_target(squad: Squad) -> None:
    """No search this pass (F6:3569-3604): the enemy has no squads, the own leader is dead, or the squad is firing
    smoke rounds. It drops its target and walks on, unless it is near cover, assaulting, in or leaving cover, a tank
    (Tank moving) or the bunker (Bunker idle)."""
    clear_target(squad)
    if not squad.near_cover and squad.state not in KEEP_ON_LOSS and squad.kind not in ARMOUR:
        walk_on(squad)
    if squad.kind == "tank":
        turn_turret(squad)
        squad.state = "tankMoving"
    if squad.kind == "bunker":
        turn_turret(squad)
        squad.state = "bunkerIdle"


def lose_target(squad: Squad) -> None:
    """Target lost (F6:3527-3567): no target, or it has no members, or its leader is dead. A squad near cover goes
    back In cover, a tank to Tank moving, the bunker to Bunker idle, and others in the open walk on."""
    clear_target(squad)
    if not squad.near_cover and squad.state not in KEEP_ON_LOSS and squad.kind not in ARMOUR:
        walk_on(squad)
    if squad.near_cover and squad.kind != "tank" and squad.state != "exitTrench":
        for member in squad.members:
            member.flags["moveAnim"] = False
        squad.state = "entrench"
    if squad.kind == "tank":
        turn_turret(squad)
        squad.state = "tankMoving"
    if squad.kind == "bunker":
        squad.state = "bunkerIdle"


def pick_state(squad: Squad) -> None:
    """The state a general pick leads to (F6:3502-3524): an assault squad in the open aimed at a squad in cover
    assaults it; any other squad in the open engages; a squad already engaging, in cover or leaving cover keeps its
    state. A tank engages as a tank and the bunker as the bunker, each turning its turret."""
    if squad.state not in HOLD_ON_PICK and not squad.near_cover:
        if squad.target.state == "entrench" and squad.kind == "assault":
            squad.last_state = squad.state
            squad.state = "assaultTrench"
        elif squad.state not in ("entrench", "assaultTrench"):
            squad.state = "engaging"
    if squad.kind == "tank":
        turn_turret(squad)
        squad.state = "tankEngaging"
    if squad.kind == "bunker":
        turn_turret(squad)
        squad.state = "bunkerEngaging"


def armour_pick(squad: Squad, enemy: Squad, distance: float) -> None:
    """The two armour checks, made over any current target on every pass (F6:3475-3497): a bazooka squad takes a tank
    out to its range + 200; a tank takes a bazooka squad or a tank in its range, so the last match (the oldest)
    wins."""
    if squad.kind == "bazooka" and enemy.kind == "tank" and distance < squad.range + BAZOOKA_REACH:
        aim(squad, enemy, distance)
        if squad.state not in ("entrench", "exitTrench"):
            squad.state = "engaging"
    if squad.kind == "tank" and enemy.kind in ("bazooka", "tank") and distance < squad.range:
        turn_turret(squad)
        aim(squad, enemy, distance)
        squad.state = "tankEngaging"


def general_pick(battle: "Battle", squad: Squad, enemy: Squad, distance: float) -> None:
    """The general pick (F6:3498-3526): only a squad whose target's leader is not alive takes a new one, so it keeps
    its target until that leader dies, however close another enemy comes. Both leaders must be inside the band."""
    if (
        not head_alive(squad.target)
        and enemy is not squad.target
        and distance < squad.range
        and enemy.members
        and in_band(battle, head_x(squad))
        and in_band(battle, head_x(enemy))
    ):
        aim(squad, enemy, distance)
        pick_state(squad)


def weigh(battle: "Battle", squad: Squad, enemy: Squad, ahead: int) -> None:
    """findEnemy's four checks against one enemy squad with a living leader (F6:3461-3567). Distance is measured ahead
    of the squad; an enemy behind it (a negative distance) counts in none of the picks (B14). The target-lost check
    runs after the picks, so a later enemy in the same pass can be picked at once."""
    distance = ahead * (head_x(enemy) - head_x(squad))
    if distance >= 0 and in_reach(squad, enemy):
        armour_pick(squad, enemy, distance)
        general_pick(battle, squad, enemy, distance)
    if not head_alive(squad.target):
        lose_target(squad)


def find_enemy(battle: "Battle", side: str, enemy_side: str) -> None:
    """findEnemy (F6:3447-3605), on the find tick. Each check reads the squad's target and state as the checks before
    it left them, so the walk order decides who picks whom."""
    enemies = battle.sides[enemy_side].squads
    ahead = 1 if side == "british" else -1
    # for (v in friendly squads), F6:3452
    for squad in battle.newest_first(battle.sides[side].squads):
        if not enemies or not head_alive(squad) or squad.firing_smoke:
            drop_target(squad)
            continue
        # for (fee in enemy squads), F6:3457
        for enemy in battle.newest_first(enemies):
            if head_alive(enemy):
                weigh(battle, squad, enemy, ahead)


def enter_cover(squad: Squad, cover: Cover) -> None:
    """In cover: the squad heads for the cover and drops its target (F6:3693-3699, 3707-3714)"""
    set_state(squad, "entrench")
    squad.cover = cover
    squad.target = None


def weigh_cover(squad: Squad, cover: Cover) -> None:
    """findTrenches against one cover in the squad's lane (F6:3660-3756). Near is 1 to 100 pixels ahead of the
    squad's first member. Each cover outside that sets the squad not near, so the last cover walked decides the flag;
    an enemy-held cover in reach leaves it as it was, and the squad never stops for it. A cover held by a friend is
    passed through; an empty one, whoever owned it last, is claimed."""
    gap = (1 if squad.side == "british" else -1) * (cover.x - head_x(squad))
    enemy_held = cover.holder is not None and cover.holder.side != squad.side
    if 0 < gap <= COVER_REACH:
        if not enemy_held:
            squad.near_cover = True
    else:
        squad.near_cover = False
    if not squad.near_cover or enemy_held or squad.in_cover:
        return
    if cover.holder is not None and cover.holder is not squad:
        enter_cover(squad, cover)
        squad.passing = True
    set_state(squad, "entrench")
    if cover.holder is None:
        enter_cover(squad, cover)
        cover.holder = squad
        squad.in_cover = True
        squad.passing = False


def find_cover(battle: "Battle", side: str) -> None:
    """findTrenches (F6:3646-3759), on the find tick: each squad that is not in cover, leaving cover or engaging,
    and is not a tank or the bunker, weighs every cover in its own lane"""
    # for (w in squads), F6:3648
    for squad in battle.newest_first(battle.sides[side].squads):
        if squad.state in NO_COVER_SEARCH or squad.kind in ARMOUR:
            continue
        # for (_loc3_ in trenches), F6:3656
        for cover in battle.newest_first(battle.covers):
            if cover.lane == squad.lane:
                weigh_cover(squad, cover)


def find_officers(battle: "Battle", side: str) -> None:
    """findOfficer (F6:3606-3645): every other squad of the side, tanks and the bunker included, whose first member is
    within 150 pixels in x of an officer is near it. Lanes are ignored, and the reach is 150 for both sides (B1). A
    dead officer stays in the list with no members, so the squads it led drop it."""
    officers = battle.sides[side].officers
    # for (x in officers), F6:3612
    for officer in battle.newest_first(officers):
        officer_x = head_x(officer)
        # for (v in squads), F6:3616
        for squad in battle.newest_first(battle.sides[side].squads):
            if squad.kind == "officer":
                continue
            gap = head_x(squad) - officer_x
            if not squad.near_officer and -OFFICER_REACH < gap < OFFICER_REACH:
                squad.near_officer = True
                squad.officer = officer
            if squad.officer is officer and (gap < -OFFICER_REACH or gap > OFFICER_REACH):
                squad.near_officer = False
            if squad.officer is not None and not squad.officer.members:
                squad.officer = None
                squad.near_officer = False


def find_wire(battle: "Battle", side: str) -> None:
    """findWire (F6:3761-3780): a squad whose first member is within 50 pixels of a wire line moves at speed / 1.5.
    The check runs whenever the map has wire (the original tested the length of a number, so never ran it; B48).
    Tanks get the flag too; their movement never reads it."""
    if not battle.wires:
        return
    # for (w in squads), F6:3765; while (x <= wire), F6:3771
    for squad in battle.newest_first(battle.sides[side].squads):
        leader_x = head_x(squad)
        squad.in_wire = False
        for wire in battle.wires:
            if -WIRE_REACH < wire - leader_x < WIRE_REACH:
                squad.in_wire = True


def find_mines(battle: "Battle", side: str) -> None:
    """findMines (F6:3782-3815): a Moving squad whose first member is within 60 pixels of an enemy mine spot sets one
    off 1 time in 16, at that member. The mine belongs to the side that laid it (B9), which loses one from its count.
    The count is checked once, before the walk, as in the original."""
    layer = battle.sides["german" if side == "british" else "british"]
    if layer.mine_count <= 0:
        return
    # for (v in squads), F6:3794; for (x in mines), F6:3797
    for squad in battle.newest_first(battle.sides[side].squads):
        for spot in battle.newest_first(layer.mines):
            if squad.state != "moving" or not -MINE_BOUNDARY < spot - head_x(squad) < MINE_BOUNDARY:
                continue
            if battle.random(MINE_CHANCE) == 0:
                # The mine goes off at the first member: the original picks its victim with random() of an
                # undefined length, which is always 0, and draws nothing for it (F6:3804)
                layer.mine_count -= 1
                leader = squad.members[0]
                mine_blast(battle, leader.x, leader.y, layer.name)
