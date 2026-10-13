"""Fire support strikes, mines going off, and what every blast does.

A strike (`launchSpecialAttack`, F6:5192-5220) is a set of rounds. Each round is a strike clip that waits its delay,
counting only unpaused steps, then starts playing at a scattered spot; its blast lands on the clip's blast frame
(anims.STRIKES), where the clip's frame script calls `explosiveHit` (F6:4544-4780) once for each side, the CPU's side
first. The page plays the same clip from the `"round"` event, so its blast frame shows on the step the bot's blast
lands.

A mine clip starts playing the moment a mine goes off (findMines, F6:3782-3815) and bursts on its frame 16. A thrown
grenade, a bazooka rocket (common/teams.py) and a tank shell are clips on the same list, bursting on their own blast
frames.

When this runs (common/battle.py's step order): rounds count down, start and burst in step 2, after the members'
timelines, oldest round first, as the strike clips' own onEnterFrame and frame scripts do.
"""

import typing as t

from . import anims
from .boxes import member_box, overlap
from .combat import HOW, score_xp, side_index, squad_gone, tank_damage
from .data import (
    BLAST_ARMOUR,
    BLAST_REACH,
    ENGINE_BROKEN,
    SIDES,
    SUPPORTS,
    SURVIVAL_CHANCE,
    TANK_DAMAGE_CHANCE,
    UPGRADE_EFFECTS,
)
from .morale import adjust

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier, Squad, Tank

STRIKE_KINDS = ("artillery", "airSupport", "mortar", "mortarAI")
# The CPU's mortar barrage plays the mortar team's round clip (mortarRound, F6:5369)
CLIP = {"mortarAI": "mortar"}
SMOKED_SURVIVAL = 3  # a smoked squad divides the survival chance by 3, F6:4555-4558
ARMOUR_SURVIVAL = 1000000  # a tank or the bunker always takes the blast, F6:4563-4566; the roll is still drawn
DAMAGE_ROLL = 1000  # tankDamageChance is out of random(1000), F6:4594
# The damage report's three parts, by random(3) (F6:4596-4620)
PARTS = ("mg", "gun", "engine")
# The owner's Explosives raises its own infantry explosives on armour (B26, W3)
EXPLOSIVES = ("grenade", "bazooka")
# The collision clip each kind attaches on its blast frame: a mine uses the mortar's
BOX_KIND = {"mine": "mortar"}
HOW_BLAST = HOW["blast"]


class Round:
    """One strike clip on the field. `delay` counts down before it starts; `blast_step` is set once it plays.
    `target_x` and `target_y` are the aimed point, `number` the round's place in its strike (air support lines its
    rounds up by it). `scatter` moves the blast random(scatter) - scatter / 2 off its point as it lands, x then y (a
    bazooka rocket's bazookaImpact, F6:9806-9813)."""

    __slots__ = (
        "id",
        "kind",
        "x",
        "y",
        "owner",
        "target_x",
        "target_y",
        "number",
        "delay",
        "blast_step",
        "box",
        "scatter",
    )

    def __init__(self, round_id: int, kind: str, owner: str, x: float, y: float, delay: int, number: int = 0):
        self.id = round_id
        self.kind = kind
        self.owner = owner
        self.target_x = x
        self.target_y = y
        self.number = number
        self.delay = delay
        self.x = x
        self.y = y
        self.blast_step: int | None = None
        self.box: tuple[float, float, float, float] | None = None
        self.scatter = 0


def x10(value: float) -> int:
    return round(value * 10)


def new_round(battle: "Battle", kind: str, owner: str, x: float, y: float, delay: int, number: int = 0) -> Round:
    """attachMovie of a strike clip (specialRounds++, F6:5246 and siblings)"""
    battle.round_count += 1
    shot = Round(battle.round_count, kind, owner, x, y, delay, number)
    battle.rounds.append(shot)
    return shot


def round_count(battle: "Battle", kind: str, owner: str) -> int:
    """How many rounds a strike fires: the owner's Barrage of Fire adds 10 artillery rounds (F6:5232). Mortar
    Accuracy adds no mortar round (B28)."""
    count = SUPPORTS[kind]["rounds"]
    if kind == "artillery" and battle.sides[owner].has("barrage_rounds"):
        count += UPGRADE_EFFECTS["barrage_rounds"]["value"]
    return count


def call_strike(battle: "Battle", kind: str, x: float, y: float, owner: str) -> None:
    """launchSpecialAttack (F6:5192-5220) for a strike aimed at (x, y): artilleryStrike (F6:5228-5241), airStrike
    (F6:5286-5305), mortarStrike (F6:5357-5368) or mortarStrikeAI (F6:5342-5356). The strike counts once in the
    owner's support used, and each round draws its delay now, `first + random(wait) + n x gap`, counting up
    (`while (v < rounds)`). Air support also flies the plane over the aimed point."""
    if kind not in STRIKE_KINDS:
        raise ValueError(f"Unknown strike {kind!r}")
    battle.sides[owner].support_used += 1
    support = SUPPORTS[kind]
    clip = CLIP.get(kind, kind)
    for number in range(round_count(battle, kind, owner)):
        delay = support["first"] + battle.random(support["wait"]) + number * support["gap"]
        new_round(battle, clip, owner, x, y, delay, number)
    if kind == "airSupport":
        battle.event("plane", x10(x), x10(y), side_index(owner))


def clamp(y: float, limits: tuple[float, float]) -> float:
    return min(max(y, limits[0]), limits[1])


def artillery_spot(battle: "Battle", shot: Round) -> tuple[float, float]:
    """artilleryRound (F6:5242-5268): x + random(250) - 125, y + random(100) - 50, y kept in 140 to 340"""
    support = SUPPORTS["artillery"]
    x = shot.target_x + battle.random(support["x_range"]) - support["x_offset"]
    y = shot.target_y + battle.random(support["y_range"]) - support["y_offset"]
    return x, clamp(y, support["y_limits"])


def air_spot(battle: "Battle", shot: Round) -> tuple[float, float]:
    """airSupportRound (F6:5306-5341): round n at x - 150 + 50n for the American side, x + 150 - 50n for the
    German, and y + random(30) - 15, kept in 140 to 340"""
    support = SUPPORTS["airSupport"]
    step = support["x_start"] + support["x_step"] * shot.number
    x = shot.target_x + step if shot.owner == "british" else shot.target_x - step
    y = shot.target_y + battle.random(support["y_range"]) - support["y_offset"]
    return x, clamp(y, support["y_limits"])


def mortar_spot(battle: "Battle", shot: Round) -> tuple[float, float]:
    """mortarRound (F6:5369-5410): x + random(100) - 50, or with the owner's Mortar Accuracy x + (random(80) - 45) x
    0.75; y + random(100) - 50. A y above the top of lane 1 becomes 111 (B56, W15). The original's wider scatter for
    a smoked mortar team reads an owner unit no caller passes (F6:5388-5393), so it never applies."""
    support = SUPPORTS["mortar"]
    if battle.sides[shot.owner].has("mortar_scatter"):
        spread, offset = support["x_accurate"]
        x = shot.target_x + (battle.random(spread) - offset) * UPGRADE_EFFECTS["mortar_scatter"]["value"]
    else:
        x = shot.target_x + battle.random(support["x_range"]) - support["x_offset"]
    y = shot.target_y + battle.random(support["y_range"]) - support["y_offset"]
    return x, max(y, support["y_min"])


SPOTS = {"artillery": artillery_spot, "airSupport": air_spot, "mortar": mortar_spot}


def start_round(battle: "Battle", shot: Round) -> None:
    """The round's onEnterFrame once its delay runs out: the clip plays from its spot, and its blast frame comes
    blast - 1 steps later"""
    shot.x, shot.y = SPOTS[shot.kind](battle, shot)
    shot.blast_step = battle.step + anims.STRIKES[shot.kind]["blast"] - 1
    battle.event("round", shot.kind, x10(shot.x), x10(shot.y), side_index(shot.owner), shot.id)


def mine_blast(battle: "Battle", x: float, y: float, layer: str) -> None:
    """A mine goes off at (x, y): the mine clip plays from now and bursts on its frame 16, with the mortar's box. The
    mine belongs to the side that laid it (the original gave it no owner)."""
    shot = new_round(battle, "mine", layer, x, y, 0)
    shot.blast_step = battle.step + anims.STRIKES["mine"]["blast"] - 1
    battle.event("mine", x10(x), x10(y), side_index(layer))


def new_grenade(
    battle: "Battle",
    thrower: "Soldier",
    x: float,
    y: float,
    arc: int,
    box: tuple[float, float, float, float],
) -> None:
    """A thrown frag grenade clip (sprite 1580) at its landing point, playing arc 1 or 2 from now; it bursts on that
    arc's burst frame with its turned box. Grenades count on their own (grenadeCollisions), not as strike rounds, and
    the page knows them by their thrower."""
    start, burst = anims.GRENADE_ARCS[arc - 1]
    shot = Round(0, "grenade", thrower.squad.side, x, y, 0)
    shot.box = box
    shot.blast_step = battle.step + burst - start
    battle.rounds.append(shot)
    battle.event("grenade", thrower.id, x10(x), x10(y), arc, "frag")


def new_shell(battle: "Battle", tank: "Tank", x: float, y: float) -> None:
    """The tank's shell clip (sprite 428) is placed at (x, y) on its first frame and bursts on its frame 6"""
    shot = new_round(battle, "shell", tank.squad.side, x, y, 0)
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
        if shot.scatter:
            shot.x += battle.random(shot.scatter) - shot.scatter / 2
            shot.y += battle.random(shot.scatter) - shot.scatter / 2
        explode(battle, shot.kind, shot.x, shot.y, shot.owner, shot.box)


def blast_box(kind: str, x: float, y: float) -> tuple[float, float, float, float]:
    """The collision clip the blast frame attaches, placed at the blast"""
    left, top, right, bottom = anims.BOXES[BOX_KIND.get(kind, kind)]
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
    box: tuple[float, float, float, float] | None = None,
) -> None:
    """A blast lands: the picture, then explosiveHit for both sides in the blast frame's order. `box` replaces the
    kind's own collision box (a grenade's turned box). Once the battle is over the blast is only a picture."""
    battle.event("blast", kind, x10(x), x10(y), side_index(owner))
    if battle.state != "playing":
        return
    hit_box = box if box is not None else blast_box(kind, x, y)
    for side in blast_order(battle):
        explosive_hit(battle, kind, x, y, hit_box, side, owner)


def in_reach(squad: "Squad", x: float, y: float) -> bool:
    """The squad's first member is within 80 pixels of the blast in x and in y (F6:4550-4553)"""
    if not squad.members:
        return False
    first = squad.members[0]
    return -BLAST_REACH < first.x - x < BLAST_REACH and -BLAST_REACH < first.y - y < BLAST_REACH


def survival_chance(squad: "Squad") -> float:
    """explosionSurvivalChance for one squad in reach (F6:4555-4566): 9, a third of it when smoked, and so large for
    a tank or the bunker that it is always hit"""
    chance = SURVIVAL_CHANCE
    if squad.smoked:
        chance /= SMOKED_SURVIVAL
    if squad.kind in ("tank", "bunker"):
        chance = ARMOUR_SURVIVAL
    return chance


def explosive_hit(
    battle: "Battle",
    kind: str,
    x: float,
    y: float,
    box: tuple[float, float, float, float],
    side: str,
    owner: str,
) -> None:
    """explosiveHit (F6:4544-4780) for one side's squads. A squad in reach is hit unless random(chance) is 0; then
    every living member whose box touches the blast's is hit."""
    # for (ex in squads), F6:4548
    for squad in battle.newest_first(battle.sides[side].squads):
        if not in_reach(squad, x, y):
            continue
        if battle.random(survival_chance(squad)) == 0:
            continue
        # for (em in members), F6:4570: newest first, so removing a member never shifts one still to come
        for member in battle.newest_first(squad.members):
            if not member.alive or not overlap(box, member_box(member)):
                continue
            if squad.kind in ("tank", "bunker"):
                hit_armour(battle, kind, squad, member, owner)
            else:
                blast_kill(battle, squad, member, owner)


def hit_armour(battle: "Battle", kind: str, squad: "Squad", member: "Tank", owner: str) -> None:
    """A blast on a tank or the bunker (F6:4581-4706): the owner's damage for the blast, x1.25 for the owner's
    grenades and rockets with Explosives (B26). A tank may report a broken part; at 0 it is destroyed."""
    battle.event("tankhit", member.id)
    damage = BLAST_ARMOUR[owner][kind]
    if kind in EXPLOSIVES and battle.sides[owner].has("explosives"):
        damage *= UPGRADE_EFFECTS["explosives"]["value"]
    tank_damage(battle, squad, damage)
    if squad.kind == "tank":
        damage_report(battle, squad, member)
    if squad.pool <= 0:
        destroy(battle, squad, member, owner)


def damage_report(battle: "Battle", squad: "Squad", tank: "Tank") -> None:
    """1 time in 10 a part breaks (F6:4592-4624), 1 in 3 each: the machine gun or the main gun stops for good, or
    the engine halves the squad's speed (B40). A part already broken is not broken again, and its roll shows no
    report. The report itself (reportTankDamage, F6:9911-9931) is the page's."""
    if battle.random(DAMAGE_ROLL) >= TANK_DAMAGE_CHANCE:
        return
    part = PARTS[battle.random(len(PARTS))]
    if part in tank.broken:
        return
    tank.broken.add(part)
    if part == "engine":
        squad.speed -= squad.speed / ENGINE_BROKEN
    battle.event("report", tank.id, part)


def destroy(battle: "Battle", squad: "Squad", tank: "Tank", owner: str) -> None:
    """The tank or bunker is destroyed (F6:4626-4706): it burns as a wreck that stays drawn on the field, morale
    moves, the kill counts for the blast's owner, and the squad leaves the field and counts as lost
    (common/combat.py `squad_gone`). Kill XP is never paid for armour."""
    tank.alive = False
    squad.state = "tankDead"
    battle.wrecks.append(tank)
    battle.event("tankdie", tank.id)
    adjust(battle, squad.side, squad.kind, "normal")
    battle.sides[owner].kills += 1
    squad.members.remove(tank)
    squad_gone(battle, squad)


def blast_kill(battle: "Battle", squad: "Squad", soldier: "Soldier", owner: str) -> None:
    """A soldier in the blast dies outright (F6:4709-4774): a kill when it hit the other side, morale, kill XP for
    the owner's player when it hit the other side, and the squad's pool drops by one soldier's HP. The ragdoll, blood
    and the body's fade are the page's."""
    soldier.alive = False
    battle.event("die", soldier.id, HOW_BLAST, side_index(owner))
    if squad.side != owner:
        battle.sides[owner].kills += 1
    adjust(battle, squad.side, squad.kind, "explosive", owner)
    if squad.side != owner:
        score_xp(battle, soldier, owner)
    squad.pool -= squad.hp
    squad.members.remove(soldier)
    squad_gone(battle, squad)
