"""Shooting, damage, deaths and suppression.

A soldier shoots by starting its firing animation; the shot lands at once (every shot hits, there is no miss roll),
and the animation's frame scripts keep `firing` on until it ends. A soldier in its pose and not firing is checked
every step, and its fire type decides whether it shoots: single-shot soldiers shoot at every chance, burst soldiers
shoot while their burst count is under a limit and then rest (F6:2509-2603, 2692-2750, 2896-2990).

A bullet takes its multiplied damage from the target squad's shared pool (hitEnemy, F6:4286-4543). Then only the
newest living member is checked: it dies once the pool is at or below its threshold ((k + 1) x HP for the k-th
member). At most one soldier dies a bullet; a big hit leaves a debt the next bullets collect. A bullet that kills no
one may suppress a member of the target while the shooter's squad lays down Suppressing Fire.

Only rolls that change the battle draw from the battle's generator here. The original's sound variant picks, blood,
ricochets and dust are drawn on the page.
"""

import typing as t

from . import anims
from .data import (
    DAMAGE_MODIFIER,
    DIFFICULTY,
    HIGH_BURST,
    KILL_XP,
    MED_BURST,
    MIN_WAIT,
    OFFICER_BONUS,
    SLOW_BURST,
    SMOKED,
    SOLDIERS,
    UPGRADE_EFFECTS,
)
from .morale import adjust, objective_down

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

TANK_BULLET = 16  # a bullet takes damage / 16 from a tank, F6:4299-4302
BUNKER_BULLET = 4  # and damage / 4 from the bunker before the infantry rules, F6:4295-4298
COVER_BONUS = 1  # trenchBonus, F6:10922: a shooter in cover
COVER_AT_ASSAULT = 0.7  # a shooter in cover firing at an assault squad, F6:4309-4311
# Each burst fire type: it fires while its burst count is at most random(a) + b, drawn fresh at every check, then
# rests until its wait count reaches random(rest) + minWait, also drawn fresh at every check (F6:2509-2585)
FIRE_TYPES = {
    "slowBurst": ((2, 1), SLOW_BURST),
    "medBurst": ((5, 2), MED_BURST),
    "burst": ((8, 4), HIGH_BURST),
}
COVER_MG_BURST = (6, 4)  # a machine gunner in cover fires while its burst count <= random(6) + 4, F6:2952
# The firing animation for a fire pose and a position: "<firePose>_fire_<position>" (F6:2515). Only the pairs the
# soldier sprite has; Flash ignores a jump to a label that doesn't exist, and so does the port
FIRE_LABEL = {tuple(label.split("_fire_")): label for label in anims.SOLDIER["labels"] if "_fire_" in label}
SNIPER_SCARE = 2  # a sharpshooter's kill sends an idle CPU squad out of its cover 1 time in 2, F6:4466-4473
XP_RISE = 30  # the "+n" starts 30 pixels above the body, and 30 back toward the player in cover, F6:8819-8835
HOW = {"bullet": 0, "blast": 1}
# Suppressing Fire works on a target squad in these states (F6:4497)
SUPPRESSIBLE = ("engaging", "entrench", "assaultTrench")
# Every pose plays the crouching suppression, the only one the soldier sprite has (B34, W9)
SUPPRESSED_LABEL = "suppressed_crouch"


def side_index(side: str | None) -> int:
    return -1 if side is None else (0 if side == "british" else 1)


def shooter_bonus(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> float:
    """Step 4: the shooter's side's own damage upgrades, each on the shots its text names (W3), in the original's
    order (F6:4344-4395): Ballistics on rifle shots (B4), American Assault Tactics and Hit 'em Hard on assault squad
    shots (B21), American Fire Support on machine gunner shots, American Anti Infantry on tank machine gun shots
    (B27), German MG Training on machine gunner shots (B2), German Scharfschuetze on sniper shots (B4)"""
    side = battle.sides[shooter.squad.side]
    squad = shooter.squad
    effects = (
        ("rifle_damage", shooter.type in UPGRADE_EFFECTS["rifle_damage"]["types"][side.name]),
        ("assault_damage", squad.kind == "assault"),
        ("flank_damage", squad.kind == "assault" and target.lane != squad.lane),
        ("machine_gun_damage", shooter.type == "machineGunner"),
        ("tank_mg_damage", squad.kind == "tank"),
        ("machine_gun_training", shooter.type == "machineGunner"),
        ("sniper_damage", shooter.type == "sharpShooter"),
    )
    bonus = 1.0
    for effect, applies in effects:
        if applies and side.has(effect):
            bonus *= UPGRADE_EFFECTS[effect]["value"]
    return bonus


def target_defence(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> float:
    """Step 5: the target side's defence upgrades against the other side's shots (F6:4372-4378, 4392-4395, W3): Take
    Cover on every shot, German Secure Flanks on shots from another lane, German Fortified on shots at a squad in
    cover (B23)"""
    side = battle.sides[target.side]
    effects = (
        ("defence", True),
        ("flank_defence", shooter.squad.lane != target.lane),
        ("fortified", target.state == "entrench"),
    )
    defence = 1.0
    for effect, applies in effects:
        if applies and side.has(effect):
            defence *= UPGRADE_EFFECTS[effect]["value"]
    return defence


def bullet_damage(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> float:
    """One bullet's pool loss on an infantry squad, its seven steps in the original's order (F6:4304-4417) with the
    upgrade lines fixed (B1 to B4, B21 to B24, B27): the shooter in cover, the target in cover, the shooter's squad
    near its officer, the shooter side's upgrades, the target side's defence, the shooter's squad smoked, then x1.3
    and the difficulty factor on the player's shots"""
    squad = shooter.squad
    damage = shooter.damage
    if target.kind == "bunker":
        damage /= BUNKER_BULLET
    if shooter.flags.get("inTrench"):
        damage *= COVER_BONUS
        if target.kind == "assault":
            damage *= COVER_AT_ASSAULT
    # In cover, which counts the walk to its spot and passing through. The German Take Cover and Secure Flanks lines
    # here lowered the Germans' own shots, so they are gone (B3)
    if target.state == "entrench" and target.cover is not None:
        damage *= target.cover.defence
    # By squad, with no upgrade on it (B1, B24, W4)
    if squad.near_officer:
        damage *= OFFICER_BONUS
    damage *= shooter_bonus(battle, shooter, target)
    damage *= target_defence(battle, shooter, target)
    if squad.smoked:
        damage *= SMOKED
    damage *= DAMAGE_MODIFIER
    if battle.sides[squad.side].human:
        damage *= DIFFICULTY[battle.difficulty]["bullets"]
    return damage


def tank_damage(battle: "Battle", target: "Squad", amount: float) -> None:
    """Take damage from a tank or bunker squad. Its pool and the tank's health are the same number"""
    target.pool -= amount
    for member in target.members:
        member.health = target.pool


def squad_gone(battle: "Battle", squad: "Squad") -> None:
    """A squad with no members left is gone from the field (F6:4517-4541): it leaves its side's list, frees its cover
    only if it holds it (B46) and counts as a unit lost. A dead officer squad stays in the officers list, which
    findOfficer reads as gone. The page shows the INTEL panel's death message if it was selected. An objective squad
    that is gone ends the battle (common/morale.py `objective_down`)."""
    side = battle.sides[squad.side]
    if squad.members or squad not in side.squads:
        return
    if squad.cover is not None and squad.cover.holder is squad:
        squad.cover.holder = None
    side.squads.remove(squad)
    side.lost += 1
    battle.event("gone", squad.id)
    objective_down(battle, squad)


def score_xp(battle: "Battle", member: "Soldier", killer: str) -> None:
    """Kill XP for the player's side by the dead soldier's squad kind, only in a campaign and only on the first try
    (updateExperience, F6:8771-8882). Tanks and the bunker pay none. The "+n" rises from 30 above the body, moved 30
    back toward the player's side in cover. Positions in the event are x10 whole numbers, like the state's."""
    if not battle.campaign or not battle.first_try or not battle.sides[killer].human:
        return
    amount = KILL_XP.get(member.squad.kind, 0)
    if amount <= 0:
        return
    battle.kill_xp[killer] += amount
    battle.score_level(killer)
    x = member.x
    if member.flags.get("inTrench"):
        x += -XP_RISE if killer == "british" else XP_RISE
    battle.event("xp", round(x * 10), round((member.y - XP_RISE) * 10), amount)


def kill(battle: "Battle", member: "Soldier", how: str, killer: str | None) -> None:
    """A soldier dies (F6:4437-4495): its side's morale drops, the kill counts for the killer's side (none for a blast
    or mine with no owner), the player's side scores kill XP, the career counts, and the soldier leaves its squad,
    which is gone once it is empty. Blood, the death animation and the body's fade 15 s later are the page's. A tank's
    destruction is common/tanks.py's: a wreck stays in its squad."""
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
    squad_gone(battle, squad)


def damage_squad(battle: "Battle", squad: "Squad", amount: float, how: str, killer: str | None) -> "Soldier | None":
    """Take `amount` from an infantry squad's pool, then check only its newest living member: it dies if the pool is
    at or below its threshold (F6:4436-4437). At most one death; a bigger loss is a debt the next hits collect.
    Returns the soldier who died, if one did."""
    squad.pool -= amount
    if not squad.members:
        return None
    newest = squad.members[-1]
    if not newest.alive or squad.pool > newest.threshold:
        return None
    kill(battle, newest, how, killer)
    return newest


def sniper_scare(battle: "Battle", shooter_squad: "Squad", target: "Squad", index: int) -> None:
    """A sharpshooter's kill of a soldier other than the first, in a CPU squad sitting in cover with no target, sends
    that squad out of its cover 1 time in 2 (F6:4466-4473)"""
    if shooter_squad.kind != "sniper" or index == 0:
        return
    if battle.sides[target.side].human or target.target is not None or not target.in_cover:
        return
    if battle.random(SNIPER_SCARE) == 0:
        target.state = "exitTrench"


def suppress(battle: "Battle", shooter_squad: "Squad", target_squad: "Squad") -> None:
    """Suppressing Fire (F6:4495-4513): while the shooter's squad has shots of it left, a bullet that killed no one at
    an Engaging, In cover or Assaulting squad takes one off and picks a random member. One in its pose and not already
    suppressed plays the crouching suppression and its recovery, 60 steps in which it never fires, then is back in its
    own pose (B34, B35, W9; common/squads.py `recover`)."""
    if shooter_squad.suppress <= 0 or target_squad.state not in SUPPRESSIBLE or not target_squad.members:
        return
    shooter_squad.suppress -= 1
    member = target_squad.members[battle.random(len(target_squad.members))]
    if not member.flags.get("inFiringPosition") or member.suppressed:
        return
    member.suppressed = True
    member.suppressed_pose = member.flags["position"]
    member.goto(battle, SUPPRESSED_LABEL, True)


def hit(battle: "Battle", shooter: "Soldier | Tank", target: "Squad") -> None:
    """hitEnemy (F6:4286-4543): one bullet into the shooter squad's target, if it is still on the field. A mortar
    team's shots land nothing (F6:4293). A tank takes damage / 16 and the bunker damage / 4 then the infantry rules;
    bullets never destroy either. Infantry take the multiplied damage and their newest member may die; a bullet that
    kills no one may suppress."""
    if target not in battle.sides[target.side].squads or shooter.squad.kind == "mortarTeam":
        return
    if target.kind == "tank":
        tank_damage(battle, target, shooter.damage / TANK_BULLET)
    elif target.kind == "bunker":
        tank_damage(battle, target, bullet_damage(battle, shooter, target))
    else:
        index = len(target.members) - 1
        dead = damage_squad(battle, target, bullet_damage(battle, shooter, target), "bullet", shooter.squad.side)
        if dead is not None:
            sniper_scare(battle, shooter.squad, target, index)
            return
    suppress(battle, shooter.squad, target)


def fire(battle: "Battle", soldier: "Soldier") -> None:
    """Start the soldier's firing animation for its fire pose and position and land the shot at its squad's target
    (F6:2513-2524). The animation's first frame turns `firing` on and its last turns it off. A soldier whose damage is
    0 (the bazooka man, the mortar carrier) lands no bullet (F6:2592, 4293): its "shot" names no target member, so
    the page plays the weapon's sound without bullet dust."""
    pose = SOLDIERS[soldier.squad.side][soldier.type]["fire_pose"]
    label = FIRE_LABEL.get((pose, soldier.flags["position"]))
    if label is not None:
        soldier.goto(battle, label, True)
    target = soldier.squad.target
    if target is None:
        return
    leader = target.members[0] if target.members else None
    lands = soldier.damage > 0
    member_id = leader.id if lands and leader is not None else 0
    battle.event("shot", soldier.id, member_id, int(target.kind == "tank"))
    if lands:
        hit(battle, soldier, target)


def burst_check(battle: "Battle", soldier: "Soldier", fire_type: str, in_cover: bool) -> None:
    """A burst soldier's chance: shoot while the burst count is at most a fresh limit, else count a wait step; once the
    wait count reaches a fresh rest, both counts restart. The rest is drawn on every check, firing or not
    (F6:2509-2585; in cover F6:2898-2975, the machine gunner's limit random(6) + 4)"""
    limit, rest = FIRE_TYPES[fire_type]
    if in_cover and fire_type == "burst":
        limit = COVER_MG_BURST
    if soldier.burst_counter <= battle.random(limit[0]) + limit[1]:
        soldier.burst_counter += 1
        fire(battle, soldier)
    else:
        soldier.wait_counter += 1
    if soldier.wait_counter >= battle.random(rest) + MIN_WAIT:
        soldier.wait_counter = 0
        soldier.burst_counter = 0


def firing_check(battle: "Battle", soldier: "Soldier", in_cover: bool) -> None:
    """One step's firing chance for a soldier in its pose and not firing, in Engaging, Assaulting cover or In cover.
    A suppressed soldier fires in no state (B35). A single-shot soldier fires at every chance unless it is mid-throw
    (F6:2586-2603, 2976-2988)."""
    if soldier.suppressed:
        return
    fire_type = SOLDIERS[soldier.squad.side][soldier.type]["fire_type"]
    if fire_type is not None:
        burst_check(battle, soldier, fire_type, in_cover)
    elif not soldier.flags["throwingGrenade"]:
        fire(battle, soldier)
