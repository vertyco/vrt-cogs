"""Shooting, damage and deaths.

A soldier shoots by starting its firing animation; the shot lands at once (every shot hits, `hitEnemy` F5:2720), and
the animation's frame scripts keep `firing` on until it ends, so how often a soldier shoots is how long that
animation is. Machine gunners fire in bursts instead (F5:1575-1599, 1852-1877).

A hit takes damage from the target squad's shared pool. Then the death walk: each member dies once the pool is at or
below its threshold ((k + 1) x HP for the k-th member), the walk stops early 9 times in 100, and a death skips the
next member, because the original removes the dead soldier from the list it is walking (F5:2816-2904).

Only rolls that change the battle draw from the battle's generator here. The original's sound variant picks, blood,
ricochets and dust are drawn on the page.
"""

import typing as t

from .data import (
    KILL_XP,
    OFFICER_BONUS,
    TRENCH_BONUS,
    TRENCH_DEFENCE,
    UPGRADE_EFFECTS,
)
from .morale import adjust

if t.TYPE_CHECKING:
    from .battle import Battle, Side
    from .squads import Soldier, Squad, Tank

# The animation a shot starts is "<pose>_fire_<position>" (or "_fire_trench" from a trench), by soldier type
# (firePose, F5:7022-7216). Machine gun crews' riflemen are plain riflemen.
FIRE_POSE = {
    "rifleman": "rifle",
    "grenadier": "rifle",
    "machineGunner": "machineGun",
    "mgAssist": "pistol",
    "sharpShooter": "sniper",
    "lieutenant": "pistol",
}
ASSAULT_IN_TRENCH = 0.7  # a trench shooter's bullet at an assault squad, F5:2743
TANK_BULLET = 16  # a bullet takes damage / 16 from a tank, F5:2731
DUST_CHANCE = 8  # showBulletDustChance, F5:7269: random(100) <= 8 stops the death walk
BURST = (8, 8)  # a machine gunner fires while its burst count <= random(8) + 8, F5:1577, 1854
BURST_REST = (30, 15)  # then rests until its idle count >= random(30) + 15, F5:1595, 1873
TRENCH_DELAY = (3000, 500)  # random(3000) + 500 ms before a soldier in a trench may fire, F5:1848
SNIPER_SCARE = 2  # a sharpshooter's kill sends an idle CPU squad out of its trench 1 time in 2, F5:2862-2871
XP_RISE = 30  # the "+n" starts 30 pixels above the body, and 30 back toward the player in a trench, F5:6011-6026
HOW = {"bullet": 0, "blast": 1, "gas": 2}


def side_index(side: str | None) -> int:
    return -1 if side is None else (0 if side == "british" else 1)


def shooter_bonus(side: "Side", shooter: "Soldier | Tank") -> float:
    """The shooter's side's damage upgrades (step 4 of the order, F5:2782-2808 as fixed): Ballistics for the rifle
    soldiers, Range Training, Fire Support, Sturmtruppen and Tank Command each for their own soldier type"""
    bonus = 1.0
    effects = (
        ("rifle_damage", FIRE_POSE.get(shooter.type) == "rifle"),
        ("sniper_damage", shooter.type == "sharpShooter"),
        ("machine_gun_damage", shooter.type == "machineGunner"),
        ("assault_damage", shooter.type == "grenadier"),
        ("tank_damage", shooter.type == "tankMarkIV"),
    )
    for effect, applies in effects:
        if applies and side.has(effect):
            bonus *= UPGRADE_EFFECTS[effect]["value"]
    return bonus


def bullet_damage(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> float:
    """One bullet's damage to an infantry squad, multiplied in the original's order (F5:2734-2814) with its upgrade
    checks fixed: each upgrade works for its owner's side only, on what its text names"""
    own = battle.sides[shooter.squad.side]
    enemy = battle.sides[target.side]
    damage = shooter.damage
    # 1. Firing from a trench
    if shooter.flags.get("inTrench"):
        damage *= TRENCH_BONUS
        if target.kind == "assault":
            damage *= ASSAULT_IN_TRENCH
        if shooter.type == "machineGunner" and own.has("machine_gun_trench"):
            damage *= UPGRADE_EFFECTS["machine_gun_trench"]["value"]
    # 2. Shooting at an entrenched squad
    if target.state == "entrench":
        damage *= TRENCH_DEFENCE
        if enemy.has("entrenched_defence"):
            damage *= UPGRADE_EFFECTS["entrenched_defence"]["value"]
    # 3. Near one of its own officers
    if shooter.squad.near_officer:
        damage *= OFFICER_BONUS
        if own.has("great_leader"):
            damage *= UPGRADE_EFFECTS["great_leader"]["value"]
    # 4. The shooter's own damage upgrades
    damage *= shooter_bonus(own, shooter)
    # 5. The target side's general defence
    if enemy.has("defence"):
        damage *= UPGRADE_EFFECTS["defence"]["value"]
    return damage


def tank_damage(battle: "Battle", target: "Squad", amount: float) -> None:
    """Take damage from a tank squad. Its pool and the tank's health are the same number"""
    if battle.sides[target.side].has("tank_defence"):
        amount *= UPGRADE_EFFECTS["tank_defence"]["value"]
    target.pool -= amount
    for member in target.members:
        member.health = target.pool


def remove_if_empty(battle: "Battle", squad: "Squad") -> None:
    """A squad with no members left is gone from the field: its trench slot frees and its side counts a unit lost
    (F5:2891-2901). A dead officer squad stays in the officers list, which findOfficer reads as gone."""
    side = battle.sides[squad.side]
    if squad.members or squad not in side.squads:
        return
    if squad.trench is not None and squad.trench_slot is not None:
        squad.trench.slots[squad.trench_slot] = None
    side.squads.remove(squad)
    side.lost += 1


def score_xp(battle: "Battle", member: "Soldier", killer: str) -> None:
    """Kill XP for the player's side, only in a campaign and only on the first try (updateExperience,
    F5:5969-6005). The "+n" rises from 30 above the body, moved 30 back toward the player's side in a trench.
    Positions in the event are x10 whole numbers, like the state's."""
    if not battle.campaign or not battle.first_try or not battle.sides[killer].human:
        return
    amount = KILL_XP[member.squad.kind]
    battle.kill_xp[killer] += amount
    battle.score_level(killer)
    x = member.x
    if member.flags.get("inTrench"):
        x += -XP_RISE if killer == "british" else XP_RISE
    battle.event("xp", round(x * 10), round((member.y - XP_RISE) * 10), amount)


def kill(battle: "Battle", member: "Soldier", how: str, killer: str | None) -> None:
    """A soldier dies: the kill counts for the killer's side (none for a blast or mine with no owner), the player's
    side scores kill XP, and the soldier leaves its squad, which is gone once it is empty. A tank's destruction is
    common/tanks.py's: a wreck stays in its squad."""
    squad = member.squad
    member.alive = False
    battle.event("die", member.id, HOW[how], side_index(killer))
    adjust(battle, squad.side, squad.kind, "normal")
    if killer is not None:
        battle.sides[killer].kills += 1
        score_xp(battle, member, killer)
        if how == "bullet":
            battle.sides[killer].soldier_kills += 1
            battle.sides[squad.side].soldier_losses += 1
    squad.members.remove(member)
    remove_if_empty(battle, squad)


def sniper_scare(battle: "Battle", shooter_squad: "Squad", target: "Squad", index: int) -> None:
    """A sharpshooter's kill of a soldier other than the first, in a CPU squad sitting in a trench with no target,
    sends that squad out of its trench 1 time in 2 (F5:2860-2871)"""
    if shooter_squad.kind != "sniper" or index == 0:
        return
    if battle.sides[target.side].human or target.target is not None or not target.in_trench:
        return
    if battle.random(SNIPER_SCARE) == 0:
        target.state = "exitTrench"


def damage_squad(
    battle: "Battle",
    squad: "Squad",
    amount: float,
    how: str,
    killer: str | None,
    allow_early_stop: bool = True,
    shooter: "Squad | None" = None,
) -> None:
    """Take `amount` from an infantry squad's pool, then walk its members to see who dies (F5:2815-2903): a
    `while (m <= length)` walk that counts up, reading one past the last member, where the death check fails and
    the early stop roll is still drawn. A death removes the member, so the walk then skips the one that moved into
    its place. `shooter` is the squad that fired, for the sharpshooter's trench rule."""
    squad.pool -= amount
    index = 0
    while index <= len(squad.members):
        member = squad.members[index] if index < len(squad.members) else None
        if member is not None and member.alive and squad.pool <= member.threshold:
            if shooter is not None:
                sniper_scare(battle, shooter, squad, index)
            kill(battle, member, how, killer)
        elif allow_early_stop and battle.random(100) <= DUST_CHANCE:
            break
        remove_if_empty(battle, squad)
        index += 1


def hit(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> None:
    """hitEnemy (F5:2720-2904): one bullet into the target squad, if it is still on the field. A tank takes
    damage / 16 and never dies here; infantry take the full multiplied damage and run the death walk."""
    if target not in battle.sides[target.side].squads:
        return
    if target.kind == "tank":
        # The walk over a tank only plays ricochets and dust, which the page draws
        tank_damage(battle, target, shooter.damage / TANK_BULLET)
        return
    damage = bullet_damage(battle, shooter, target)
    damage_squad(battle, target, damage, "bullet", shooter.squad.side, shooter=shooter.squad)


def fire(battle: "Battle", soldier: "Soldier", trench: bool = False) -> None:
    """Start the soldier's firing animation and land the shot at its squad's target (F5:1580-1590, 1604-1614,
    1710-1719, 1857-1893). The animation's first frame turns `firing` on and its last turns it off."""
    position = "trench" if trench else soldier.flags["position"]
    soldier.goto(battle, f"{FIRE_POSE[soldier.type]}_fire_{position}", True)
    target = soldier.squad.target
    if target is None:
        return
    leader = target.members[0] if target.members else None
    battle.event("shot", soldier.id, 0 if leader is None else leader.id, int(target.kind == "tank"))
    hit(battle, soldier, target)


def burst(battle: "Battle", soldier: "Soldier", trench: bool) -> None:
    """A machine gunner's firing chance: shoot while the burst lasts, else count idle steps until the rest is over.
    Both limits are drawn fresh at every check (F5:1575-1599, 1852-1877)."""
    if soldier.burst_counter <= battle.random(BURST[0]) + BURST[1]:
        soldier.burst_counter += 1
        fire(battle, soldier, trench)
    else:
        soldier.wait_counter += 1
    if soldier.wait_counter >= battle.random(BURST_REST[0]) + BURST_REST[1]:
        soldier.wait_counter = 0
        soldier.burst_counter = 0


def shoot(battle: "Battle", soldier: "Soldier", trench: bool = False) -> None:
    """A soldier's firing chance in Engaging, Assaulting or a trench: a machine gunner bursts, anyone else fires.
    In the open a soldier mid-throw doesn't (F5:1601, 1708); the trench doesn't check (F5:1879)"""
    if soldier.type == "machineGunner":
        burst(battle, soldier, trench)
    elif trench or not soldier.flags["throwingGrenade"]:
        fire(battle, soldier, trench)


def start_firing(soldier: "Soldier") -> None:
    """startFiringDelay (F5:2204-2207): the soldier in the trench may fire from now on"""
    soldier.start_firing = True


def trench_shot(battle: "Battle", soldier: "Soldier") -> None:
    """A soldier in a trench with a target, not mid-shot (F5:1844-1895): every such step starts a new firing delay
    timer, and once any of them has run, it shoots"""
    battle.after(battle.random(TRENCH_DELAY[0]) + TRENCH_DELAY[1], lambda: start_firing(soldier))
    if soldier.start_firing:
        shoot(battle, soldier, True)
