"""Fire support strikes, mines going off, and what every blast does.

A strike (`launchSpecialAttack`, F5:3417-3444) is a set of rounds. Each round is a strike clip that waits its delay,
counting only unpaused steps, then starts playing at a scattered spot; its blast lands on the clip's blast frame
(anims.STRIKES), where the clip's frame script calls `explosiveHit` (F5:2909-3074) once for each side. The page plays
the same clip from the `"round"` event, so its blast frame shows on the step the bot's blast lands.

A mine clip starts playing the moment a mine goes off (findMines, F5:2490-2523) and bursts on its frame 16. A thrown
grenade (common/tanks.py) and a tank shell are clips on the same list, bursting on their own last frames.

When this runs (common/battle.py's step order): rounds count down, start and burst in step 2, after the members'
timelines, oldest round first, as the strike clips' own onEnterFrame and frame scripts do.
"""

import typing as t

from . import anims
from .boxes import member_box, overlap
from .combat import HOW, score_xp, side_index, tank_damage
from .data import BLAST_TANK_DAMAGE, SIDES, SUPPORT_KINDS, SUPPORTS, SURVIVAL_CHANCE, UPGRADE_EFFECTS
from .gas import start_cloud
from .morale import adjust

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

BLAST_REACH = 60  # a squad whose first member is within 60 pixels of the blast's x is in reach, F5:2915
GROUND = 170  # world.ground, F5:4632: a round lands at y 170 + random(120), F5:3492
GROUND_SPREAD = 120
# Extra rounds a side's own upgrades add to its strikes (F5:3456-3462, 3516-3519; Anti-Tank Barrage was never read)
EXTRA_ROUNDS = {
    "mortar": ("mortar_rounds",),
    "artillery": ("artillery_rounds", "barrage_rounds"),
    "antiTank": ("anti_tank_rounds",),
}
# The accuracy upgrade that shrinks a strike's scatter (F5:3483-3490, 3539-3546, 3594-3601)
ACCURACY = {"mortar": "mortar_scatter", "artillery": "artillery_scatter", "antiTank": "mortar_scatter"}
# The tank damage key and the owner's upgrade that raises it, by blast kind (F5:2931-2947 as fixed)
TANK_DAMAGE_KEY = {
    "mortar": "mortar",
    "artillery": "artillery",
    "antiTank": "antiTank",
    "mine": "mine",
    "grenade": "grenade",
    "shell": "tankShell",
}
TANK_DAMAGE_UPGRADE = {
    "mortar": "mortar_tank_damage",
    "artillery": "artillery_tank_damage",
    "antiTank": "artillery_tank_damage",
    "shell": "tank_damage",
}
# The collision clip each kind attaches on its blast frame: a mine uses the mortar's
BOX_KIND = {"mine": "mortar"}
HOW_BLAST = HOW["blast"]


class Round:
    """One strike clip on the field. `delay` counts down before it starts; `blast_step` is set once it plays."""

    __slots__ = ("id", "kind", "x", "y", "owner", "target", "delay", "blast_step", "mirror", "wide", "box")

    def __init__(self, round_id: int, kind: str, owner: str, target: float, delay: int):
        self.id = round_id
        self.kind = kind
        self.owner = owner
        self.target = target
        self.delay = delay
        self.x = target
        self.y = float(GROUND)
        self.blast_step: int | None = None
        # The anti-tank clip is mirrored for a German strike (F5:3584-3587)
        self.mirror = kind == "antiTank" and owner == "german"
        self.wide = False
        self.box: tuple[float, float, float, float] | None = None


def x10(value: float) -> int:
    return round(value * 10)


def new_round(battle: "Battle", kind: str, owner: str, target: float, delay: int) -> Round:
    """attachMovie of a strike clip (specialRounds++, F5:3466)"""
    battle.round_count += 1
    shot = Round(battle.round_count, kind, owner, target, delay)
    battle.rounds.append(shot)
    return shot


def round_count(battle: "Battle", kind: str, owner: str) -> int:
    side = battle.sides[owner]
    count = SUPPORTS[owner][kind]["rounds"]
    for effect in EXTRA_ROUNDS.get(kind, ()):
        if side.has(effect):
            count += UPGRADE_EFFECTS[effect]["value"]
    return count


def launch(battle: "Battle", kind: str, x: float, owner: str) -> None:
    """launchSpecialAttack (F5:3417-3444) for either side, with no readiness check: the strike counts once in the
    owner's support used, and each round draws its delay now, `random(first_gap) + n x gap`, counting up
    (`while (v < rounds)`, F5:3463). A gas strike's rounds are millisecond timers instead (gasStrike, F5:3612-3621)."""
    battle.sides[owner].support_used += 1
    if kind == "gas":
        launch_gas(battle, x, owner)
        return
    support = SUPPORTS[owner][kind]
    for number in range(round_count(battle, kind, owner)):
        delay = battle.random(support["first_gap"]) + number * support["gap"]
        new_round(battle, kind, owner, x, delay)


def launch_gas(battle: "Battle", x: float, owner: str) -> None:
    """gasStrike (F5:3612-3621): each round is a timer of `random(800) + n x 1100` ms, drawn now, counting up"""
    support = SUPPORTS[owner]["gas"]
    for number in range(support["rounds"]):
        delay = battle.random(support["first_gap"]) + number * support["gap"]
        battle.after(delay, lambda: gas_round(battle, x, owner))


def gas_round(battle: "Battle", target: float, owner: str) -> None:
    """gasRound (F5:3622-3629): the strike clip is placed at its scattered spot the moment its timer runs, so the
    spot is drawn here (x first, then y), and it plays from this step"""
    scatter = SUPPORTS[owner]["gas"]["scatter"]
    shot = new_round(battle, "gas", owner, target, 0)
    shot.x = target + battle.random(scatter * 2) - scatter
    shot.y = GROUND + battle.random(GROUND_SPREAD)
    shot.blast_step = battle.step + anims.STRIKES["gas"]["blast"] - 1
    battle.event("round", "gas", x10(shot.x), x10(shot.y), side_index(owner), shot.id)


def call_support(battle: "Battle", side: str, slot: int, x: float) -> bool:
    """A human side's press on a charged support slot and its ground target (F5:4080-4107): the strike, then only
    that slot's dial starts over. False when refused."""
    owner = battle.sides.get(side)
    if owner is None or not owner.human or battle.state != "playing" or battle.paused:
        return False
    if not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= len(SUPPORT_KINDS):
        return False
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not 0 <= x <= battle.width:
        return False
    if not owner.support_ready(slot - 1):
        return False
    launch(battle, SUPPORT_KINDS[slot - 1], float(x), side)
    owner.restart_support(slot - 1)
    return True


def start_round(battle: "Battle", shot: Round) -> None:
    """The round's onEnterFrame once its delay runs out (F5:3476-3497): play, then land at the target x plus
    `random(250) - 125` (x0.75 with the owner's accuracy upgrade) and y 170 + random(120)"""
    scatter = SUPPORTS[shot.owner][shot.kind]["scatter"]
    spread = battle.random(scatter * 2) - scatter
    accuracy = ACCURACY[shot.kind]
    if battle.sides[shot.owner].has(accuracy):
        spread *= UPGRADE_EFFECTS[accuracy]["value"]
    shot.x = shot.target + spread
    shot.y = GROUND + battle.random(GROUND_SPREAD)
    shot.blast_step = battle.step + anims.STRIKES[shot.kind]["blast"] - 1
    battle.event("round", shot.kind, x10(shot.x), x10(shot.y), side_index(shot.owner), shot.id)


def mine_blast(battle: "Battle", x: float, y: float, layer: str) -> None:
    """A mine goes off at (x, y): the mine clip plays from now and bursts on its frame 16. The mine belongs to the side
    that laid it (the original gave it no owner)."""
    shot = new_round(battle, "mine", layer, x, 0)
    shot.x = x
    shot.y = y
    shot.blast_step = battle.step + anims.STRIKES["mine"]["blast"] - 1
    battle.event("mine", x10(x), x10(y), side_index(layer))


def new_grenade(
    battle: "Battle",
    thrower: "Soldier",
    x: float,
    y: float,
    arc: int,
    wide: bool,
    box: tuple[float, float, float, float],
) -> None:
    """A thrown grenade clip (sprite 1376) at its landing point, playing arc 1 or 2 from now; it bursts on that arc's
    last frame with its turned box. Grenades count on their own (grenNumber, F5:5761), not as strike rounds, and the
    page knows them by their thrower."""
    start, burst = anims.GRENADE_ARCS[arc - 1]
    shot = Round(0, "grenade", thrower.squad.side, x, 0)
    shot.y = y
    shot.wide = wide
    shot.box = box
    shot.blast_step = battle.step + burst - start
    battle.rounds.append(shot)
    battle.event("grenade", thrower.id, x10(x), x10(y), arc, int(wide))


def new_shell(battle: "Battle", tank: "Tank", x: float, y: float) -> None:
    """tankRound (F5:3713-3720): the shell clip (sprite 347) is placed at (x, y) on its first frame and bursts on its
    frame 6"""
    shot = new_round(battle, "shell", tank.squad.side, x, 0)
    shot.y = y
    shot.blast_step = battle.step + anims.STRIKES["shell"]["blast"] - 1
    battle.event("shell", tank.id, x10(x), x10(y))


def run_rounds(battle: "Battle") -> None:
    """Step 2's strike clips, oldest first: waiting rounds count down and start once below 0, then every round on its
    blast step bursts and leaves the field"""
    for shot in battle.rounds:
        if shot.blast_step is not None:
            continue
        shot.delay -= 1
        if shot.delay < 0:
            start_round(battle, shot)
    landed = [shot for shot in battle.rounds if shot.blast_step == battle.step]
    if not landed:
        return
    battle.rounds = [shot for shot in battle.rounds if shot.blast_step != battle.step]
    for shot in landed:
        explode(battle, shot.kind, shot.x, shot.y, shot.owner, shot.wide, shot.box, shot.mirror)


def blast_box(kind: str, x: float, y: float, wide: bool, mirror: bool) -> tuple[float, float, float, float]:
    """The collision clip the blast frame attaches, placed at the blast. `wide` is three times the width"""
    left, top, right, bottom = anims.BOXES[BOX_KIND.get(kind, kind)]
    if wide:
        left, right = left * 3, right * 3
    if mirror:
        left, right = -right, -left
    return (x + left, y + top, x + right, y + bottom)


def blast_order(battle: "Battle") -> tuple[str, str]:
    """The blast frames call explosiveHit for the CPU's side, then the player's. With two players (versus) or none,
    the Germans come first."""
    humans = [name for name in SIDES if battle.sides[name].human]
    if len(humans) == 1:
        human = humans[0]
        return (SIDES[1 - SIDES.index(human)], human)
    return ("german", "british")


def explode(
    battle: "Battle",
    kind: str,
    x: float,
    y: float,
    owner: str,
    wide: bool = False,
    box: tuple[float, float, float, float] | None = None,
    mirror: bool = False,
) -> None:
    """A blast lands: the picture, then explosiveHit for both sides in the blast frame's order. `box` replaces the
    kind's own collision box (a grenade's turned box). Once the battle is over the blast is only a picture. A gas
    round's burst starts its cloud, which hurts through the gas module instead of explosiveHit."""
    battle.event("blast", kind, x10(x), x10(y), side_index(owner), int(wide))
    if kind == "gas":
        start_cloud(battle, x, y, owner)
        return
    if battle.state != "playing":
        return
    hit_box = box if box is not None else blast_box(kind, x, y, wide, mirror)
    for side in blast_order(battle):
        explosive_hit(battle, kind, x, hit_box, side, owner)


def explosive_hit(
    battle: "Battle", kind: str, x: float, box: tuple[float, float, float, float], side: str, owner: str
) -> None:
    """explosiveHit (F5:2909-3074) for one side's squads. A squad is in reach when its first member is within 60
    pixels of the blast; then 9 times in 10 every living member whose box touches the blast's is hit."""
    # for (s in squads), F5:2912
    for squad in battle.newest_first(battle.sides[side].squads):
        if not squad.members or not -BLAST_REACH < squad.members[0].x - x < BLAST_REACH:
            continue
        if battle.random(SURVIVAL_CHANCE) == 0:
            continue
        # for (m in members), F5:2919: newest first, so removing a member never shifts one still to come
        for member in battle.newest_first(squad.members):
            if not member.alive or not overlap(box, member_box(member)):
                continue
            if squad.kind == "tank":
                hit_tank(battle, kind, squad, member, owner)
            else:
                blast_kill(battle, squad, member, owner)


def hit_tank(battle: "Battle", kind: str, squad: "Squad", tank: "Tank", owner: str) -> None:
    """A blast on a tank (F5:2929-3014): the owner's damage for the blast, with the owner's own upgrade for it (each
    side's for itself, British Tank Command only on tank shells), less the target's Tank Command defence"""
    battle.event("tankhit", tank.id)
    damage = BLAST_TANK_DAMAGE[owner][TANK_DAMAGE_KEY[kind]]
    upgrade = TANK_DAMAGE_UPGRADE.get(kind)
    if upgrade is not None and battle.sides[owner].has(upgrade):
        damage *= UPGRADE_EFFECTS[upgrade]["value"]
    tank_damage(battle, squad, damage)
    if squad.pool <= 0:
        wreck_tank(battle, squad, tank, owner)


def leave_field(battle: "Battle", squad: "Squad", member: "Soldier | Tank") -> None:
    """The member leaves its squad's list; an empty squad leaves the field and frees its trench slot. The blast path
    counts no lost unit for it, as the original's doesn't (F5:3057-3062)."""
    squad.members.remove(member)
    side = battle.sides[squad.side]
    if squad.members or squad not in side.squads:
        return
    if squad.trench is not None and squad.trench_slot is not None:
        squad.trench.slots[squad.trench_slot] = None
    side.squads.remove(squad)


def wreck_tank(battle: "Battle", squad: "Squad", tank: "Tank", owner: str) -> None:
    """The tank is destroyed (F5:2956-3012): it burns as a wreck that stays on the field (deadTanks), the owner of
    the blast counts a kill and the tank's side a lost unit. Kill XP is never paid for a tank."""
    tank.alive = False
    squad.state = "tankDead"
    battle.sides[owner].kills += 1
    battle.sides[squad.side].lost += 1
    battle.wrecks.append(tank)
    battle.event("tankdie", tank.id)
    adjust(battle, squad.side, "tank", "normal")
    leave_field(battle, squad, tank)


def blast_kill(battle: "Battle", squad: "Squad", soldier: "Soldier", owner: str) -> None:
    """A soldier in the blast dies outright (F5:3014-3062): a kill and kill XP for the owner when it hit the other
    side, and the squad's pool drops by one soldier's HP"""
    soldier.alive = False
    battle.event("die", soldier.id, HOW_BLAST, side_index(owner))
    adjust(battle, squad.side, squad.kind, "explosive", owner)
    if squad.side != owner:
        battle.sides[owner].kills += 1
        score_xp(battle, soldier, owner)
    squad.pool -= squad.hp
    leave_field(battle, squad, soldier)
