"""Who a squad aims at, and what it walks into: targets, officers, trenches, wire and mines.

Each function is one of the original's finders, walked in the original's order: `for (x in list)` loops go newest
first, `while` loops count up. The finders read a squad's first member (`members[0]`), as the original does, not its
first living one: a dead soldier leaves the list, but a dead tank stays in it with `alive` false.

When they run (common/battle.py's step order): `find_enemy` both ways and `find_trenches` for both sides before
every squad's turn (F5:1311-1317); `find_mines`, `find_wire` and `find_officers`, German before British each, on the
medium tick (F5:6843-6857).
"""

import math
import typing as t

from .data import (
    MINE_BOUNDARY,
    MINE_CHANCE,
    OFFICER_REACH,
    TARGETING_BUFFER,
    TRENCH_BOUNDARY,
    UPGRADE_EFFECTS,
)
from .blasts import mine_blast
from .squads import TRENCH_SLOTS, Squad, Trench, stop_firing

if t.TYPE_CHECKING:
    from .battle import Battle

NO_TARGET = 999999  # targetProx with no target, F5:1074, 2248
# States a squad keeps when it loses its target (F5:2254, 2274)
KEEP_ON_LOSS = ("assaultTrench", "stopped", "entrench", "exitTrench")


def head(squad: Squad):
    """The squad's `members[0]`, or None before its first member spawns or after its last one died"""
    return squad.members[0] if squad.members else None


def head_x(squad: Squad) -> float:
    """`members[0]._x`: NaN with no first member, so every comparison with it fails, as undefined does in a SWF"""
    member = head(squad)
    return math.nan if member is None else member.x


def head_alive(squad: Squad) -> bool:
    member = head(squad)
    return member is not None and member.alive


def in_band(battle: "Battle", x: float) -> bool:
    """Inside the targeting band, x 120 to width - 120 (targetingBuffer, F5:2225)"""
    return TARGETING_BUFFER < x < battle.width - TARGETING_BUFFER


def lose_target(squad: Squad) -> None:
    """The target is gone: clear it, stop firing, and walk on (F5:2245-2264, 2266-2282). A tank always goes back to
    Tank moving; other squads keep a trench or assault state"""
    squad.target = None
    squad.target_dist = NO_TARGET
    stop_firing(squad)
    if not squad.near_trench and squad.kind != "tank" and squad.state not in KEEP_ON_LOSS:
        squad.state = "moving"
    if squad.kind == "tank":
        squad.state = "tankMoving"


def take_target(squad: Squad, enemy: Squad, distance: float) -> None:
    """A new, closer target and the state that goes with it (F5:2227-2243)"""
    squad.target = enemy
    squad.target_dist = distance
    if squad.state not in ("entrench", "exitTrench"):
        if not squad.near_trench and enemy.state == "entrench" and squad.kind == "assault":
            squad.state = "assaultTrench"
        elif not squad.near_trench and squad.state not in ("entrench", "assaultTrench"):
            squad.state = "engaging"
    if squad.kind == "tank":
        squad.state = "tankEngaging"


def target_gone(squad: Squad) -> bool:
    """The original's check on the current target (F5:2245): true with no target at all, since `undefined.alive`
    equals undefined, so a squad with no target runs the loss work every time it meets a live enemy"""
    if squad.target is None or not squad.target.members:
        return True
    return not squad.target.members[0].alive


def find_enemy(battle: "Battle", side: str, enemy_side: str) -> None:
    """findEnemy (F5:2208-2285). Distance is measured ahead of the squad; an enemy that has run past it has a
    negative distance and is never picked (the original picked it as the closest)."""
    enemies = battle.sides[enemy_side].squads
    ahead = 1 if side == "british" else -1
    # for (v in friendly squads), F5:2210
    for squad in battle.newest_first(battle.sides[side].squads):
        if not enemies or not head_alive(squad):
            lose_target(squad)
            continue
        own_x = head_x(squad)
        # for (e in enemy squads), F5:2214
        for enemy in battle.newest_first(enemies):
            if not head_alive(enemy):
                continue
            enemy_x = head_x(enemy)
            distance = ahead * (enemy_x - own_x)
            if (
                enemy is not squad.target
                and 0 <= distance < squad.target_dist
                and distance < squad.range
                and in_band(battle, own_x)
                and in_band(battle, enemy_x)
            ):
                take_target(squad, enemy, distance)
            if target_gone(squad):
                lose_target(squad)


def trench_holds(trench: Trench, side: str) -> bool:
    """Whether any of the trench's slots holds a squad of `side`"""
    return any(slot is not None and slot.side == side for slot in trench.slots)


def trench_full(trench: Trench, squad: Squad) -> bool:
    """All three slots hold squads other than this one (F5:2366, 2410)"""
    return all(slot is not None and slot is not squad for slot in trench.slots)


def pass_through(squad: Squad, trench: Trench) -> None:
    """The trench is full or locked: go in, and out again once every member is in (F5:2368-2375, 2412-2419)"""
    if squad.in_trench:
        return
    squad.state = "entrench"
    squad.trench = trench
    squad.in_trench = True
    squad.passing = True
    squad.target = None


def claim_slot(squad: Squad, trench: Trench, enemy_owned: bool) -> None:
    """The first free slot, counting up (`while (r <= 3)`, F5:2377-2403, 2421-2456). The squad turns to Entrenching
    even when no slot is free to it. Taking an enemy trench turns it and drops the lock its owner set."""
    for slot in range(TRENCH_SLOTS):
        if squad.in_trench:
            continue
        squad.state = "entrench"
        if trench.slots[slot] is not None:
            continue
        if enemy_owned:
            # Only a human side locks, and the original drops the lock when the CPU takes the trench (F5:2437-2440).
            # With two human sides the lock belongs to the side that set it, so either one's capture drops it
            trench.locked = False
        elif trench.locked:
            continue
        trench.owner = squad.side
        squad.trench = trench
        squad.trench_slot = slot
        squad.in_trench = True
        trench.slots[slot] = squad
        squad.passing = False
        squad.target = None


def near_check(squad: Squad, trench: Trench, leader_x: float) -> None:
    """Sets `near_trench` for this trench (F5:2337-2362): 1 to 120 pixels ahead and no enemy in it. A trench that is
    near but holds an enemy leaves the flag as the last trench set it."""
    ahead = trench.x - leader_x if squad.side == "british" else leader_x - trench.x
    if 0 < ahead <= TRENCH_BOUNDARY:
        enemy = "german" if squad.side == "british" else "british"
        if not trench_holds(trench, enemy):
            squad.near_trench = True
    else:
        squad.near_trench = False


def find_trenches(battle: "Battle", side: str) -> None:
    """findTrenches (F5:2326-2471) for every squad but tanks, against each trench in turn. A full or locked trench
    of its own (or nobody's) is passed through; a full enemy trench too, since locks only stop the lock's owner."""
    # for (w in squads), F5:2328
    for squad in battle.newest_first(battle.sides[side].squads):
        leader = head(squad)
        if leader is not None and leader.type == "tankMarkIV":
            continue
        leader_x = math.nan if leader is None else leader.x
        # for (p in trenches), F5:2334
        for trench in battle.newest_first(battle.trenches):
            near_check(squad, trench, leader_x)
            if not squad.near_trench or squad.state == "exitTrench":
                continue
            enemy_owned = trench.owner is not None and trench.owner != side
            if trench_full(trench, squad) or (trench.locked and not enemy_owned):
                pass_through(squad, trench)
            claim_slot(squad, trench, enemy_owned)


def panel_open(battle: "Battle", side: str, index: int) -> Trench | None:
    """The trench whose panel a human side may use: no enemy squad holds it, and either one of its squads holds a
    slot or it owns the trench (the original needed a squad inside, which left a locked, emptied trench stuck
    locked). None when the order is refused."""
    owner = battle.sides.get(side)
    if owner is None or not owner.human or battle.state != "playing" or battle.paused:
        return None
    if not 0 <= index < len(battle.trenches):
        return None
    trench = battle.trenches[index]
    enemy = "german" if side == "british" else "british"
    if trench_holds(trench, enemy) or not (trench_holds(trench, side) or trench.owner == side):
        return None
    return trench


def send_over(battle: "Battle", side: str, index: int, slot: int) -> bool:
    """The panel's squad button (F5:5390-5465): an entrenched squad fully in goes over the top and frees its slot; one
    still getting in is marked to pass through instead, and frees its slot too. False when refused."""
    trench = panel_open(battle, side, index)
    if trench is None or not 0 <= slot < TRENCH_SLOTS:
        return False
    squad = trench.slots[slot]
    if squad is None or squad.side != side or squad.state != "entrench":
        return False
    trench.slots[slot] = None
    # for (m in members), F5:5395: any member not in yet marks the squad as passing
    if any(not member.flags["inTrench"] for member in battle.newest_first(squad.members)):
        squad.passing = True
        return True
    squad.state = "exitTrench"
    squad.in_trench = False
    return True


def flip_lock(battle: "Battle", side: str, index: int) -> bool:
    """The panel's lock button (F5:5375-5389): the side's own squads pass through a locked trench. False when
    refused."""
    trench = panel_open(battle, side, index)
    if trench is None:
        return False
    trench.locked = not trench.locked
    return True


def officer_reach(battle: "Battle", side: str) -> float:
    """officerInfluence: 150, or 250 for British officers with Officer Rally (F5:2288-2291). The original set 250 for
    both sides until the game closed."""
    if battle.sides[side].has("officer_reach"):
        return UPGRADE_EFFECTS["officer_reach"]["value"]
    return OFFICER_REACH


def find_officers(battle: "Battle", side: str) -> None:
    """findOfficer (F5:2286-2325): every other squad of the side whose first member is within reach of an officer
    gets the officer bonus. A dead officer stays in the list with no members, so the squads it led drop it."""
    reach = officer_reach(battle, side)
    officers = battle.sides[side].officers
    # for (x in officers), F5:2292
    for officer in battle.newest_first(officers):
        officer_x = head_x(officer)
        # for (v in squads), F5:2296
        for squad in battle.newest_first(battle.sides[side].squads):
            if squad.kind == "officer":
                continue
            gap = head_x(squad) - officer_x
            if not squad.near_officer and -reach < gap < reach:
                squad.near_officer = True
                squad.officer = officer
            if squad.officer is officer and (gap < -reach or gap > reach):
                squad.near_officer = False
            if squad.officer is not None and not squad.officer.members:
                squad.officer = None
                squad.near_officer = False


def find_wire(battle: "Battle", side: str) -> None:
    """findWire (F5:2472-2489): a squad whose first member is within 50 pixels of a wire line moves at speed / 1.5.
    Tanks get the flag too, as in the original; their movement never reads it."""
    # for (w in squads), F5:2474; while (x <= wire), F5:2479
    for squad in battle.newest_first(battle.sides[side].squads):
        leader_x = head_x(squad)
        squad.in_wire = False
        for wire in battle.wires:
            if -50 < wire - leader_x < 50:
                squad.in_wire = True


def find_mines(battle: "Battle", side: str) -> None:
    """findMines (F5:2490-2523): a Moving squad whose first member is within 60 pixels of an enemy mine spot sets one
    off 1 time in 16, at that member. The mine belongs to the side that laid it, which loses one from its count.
    The count is checked once, before the walk, as in the original."""
    layer = battle.sides["german" if side == "british" else "british"]
    if layer.mine_count <= 0:
        return
    # for (v in squads), F5:2502; for (x in mines), F5:2505
    for squad in battle.newest_first(battle.sides[side].squads):
        for spot in battle.newest_first(layer.mines):
            if squad.state != "moving" or not -MINE_BOUNDARY < spot - head_x(squad) < MINE_BOUNDARY:
                continue
            if battle.random(MINE_CHANCE) == 0:
                # The mine goes off at the first member: the original picks its victim with random() of an
                # undefined length, which is always 0, and draws nothing for it
                layer.mine_count -= 1
                leader = squad.members[0]
                mine_blast(battle, leader.x, leader.y, layer.name)
