"""Morale, ground taken and the end of a battle.

Morale (adjustMorale, F5:5508-5625): every death, destroyed tank and ground mark moves a side's morale, and a side whose
morale reaches 0 surrenders at the next slow tick (updateMoraleBar, F5:5674-5691). Ground (updateProgressBar,
F5:3807-3869): each side's front is its most forward squad leader; the bars are whole percents. The battle ends once,
on the first win or surrender; squads then cheer or surrender and nothing else counts (B15).

`how` a battle ended: "ground" (a soldier or tank crossed the conquer line), "morale" (a side's morale ran out),
"surrender" (the player quit the battle), "left" (the player left a versus game).

Quick messages go out as `"msg"` events: key "lowMorale" or "breaking", and the side whose morale it is. The page
words them for whoever is looking ("MORALE IS LOW!" for your side, "ENEMY MORALE IS LOW!" for the other).
"""

import math
import typing as t

from .data import (
    BLAST_GAIN,
    BLAST_LOSS,
    BULLET_GAIN,
    GROUND_FACTOR,
    GROUND_MARKS,
    MORALE_COST,
    SIDES,
    regen_rate,
)

if t.TYPE_CHECKING:
    from .battle import Battle, Side

# Percent of a side's maximum morale where a quick message shows: (highest, lowest, key), F5:5609-5624
MORALE_MESSAGES = ((30, 25, "lowMorale"), (10, 5, "breaking"))
PANIC_GROUND = 50  # the CPU panics while the other side holds this much ground, F5:3845-3860
BAR_MARGIN = 60  # the progress bar leaves 60 pixels at the far end, F5:3841-3842


def flash_round(value: float) -> int:
    """Math.round: halves go up"""
    return math.floor(value + 0.5)


def other_side(name: str) -> str:
    return SIDES[1 - SIDES.index(name)]


def player_order(battle: "Battle") -> tuple[str, str]:
    """The player's side first, then the other. With two players, or none, the British are first."""
    humans = [name for name in SIDES if battle.sides[name].human]
    if len(humans) == 1:
        return (humans[0], other_side(humans[0]))
    return SIDES


def death_cost(mine: "Side", other: "Side", kind: str, how: str | None) -> None:
    """The morale a dead soldier or officer costs its side, and what the other side gains (adjustMorale's officer and
    default cases). A blast costs 1.3 times a bullet; an officer's death gives the other side nothing."""
    blast = how == "explosive"
    if how not in ("normal", "explosive"):
        return
    soldier = MORALE_COST["officer" if kind == "officer" else "soldier"]
    lost = soldier * (BLAST_LOSS if blast else 1)
    mine.morale -= lost
    mine.morale_lost += lost
    if kind != "officer":
        gained = MORALE_COST["soldier"] * (BLAST_GAIN if blast else BULLET_GAIN)
        other.morale += gained
        other.morale_gained += gained


def adjust(battle: "Battle", side: str, kind: str, how: str | None = None, owner: str | None = None) -> None:
    """adjustMorale for `side`. `kind` is the dead squad's kind, or "tank", "ground" or "regen"; `how` is "normal"
    (a bullet or gas) or "explosive" (a blast) for deaths; `owner` is the side whose blast it was."""
    mine = battle.sides[side]
    other = battle.sides[other_side(side)]
    if owner == side:
        mine.morale -= MORALE_COST["friendly_fire"]
    if kind == "tank":
        mine.morale -= MORALE_COST["tank"]
        other.morale += MORALE_COST["tank_killed"]
    elif kind == "ground":
        mine.morale *= GROUND_FACTOR
    elif kind == "regen":
        mine.morale *= regen_rate(mine.ground)
    else:
        death_cost(mine, other, kind, how)
    mine.morale = min(mine.morale, mine.morale_max)
    other.morale = min(other.morale, other.morale_max)
    quick_messages(battle)


def quick_messages(battle: "Battle") -> None:
    """The four morale warnings adjustMorale checks after every change, the other side's before the player's"""
    for name in reversed(player_order(battle)):
        side = battle.sides[name]
        percent = side.morale / side.morale_max * 100
        for high, low, key in MORALE_MESSAGES:
            if low <= percent <= high:
                battle.event("msg", key, side.index)


def regen(battle: "Battle") -> None:
    """Morale comes back with ground held, for both sides (moraleRegen, F5:5626-5673, run every slow tick)"""
    for name in SIDES:
        adjust(battle, name, "regen")


def ground_percent(battle: "Battle", side: "Side", front: float) -> float:
    """How far across the field a front is for its side's ground marks (groundMoraleCheck, F5:5736-5758)"""
    percent = front / battle.width * 100
    return percent if side.name == "british" else 100 - percent


def ground_mark(battle: "Battle", side: "Side", front: float) -> None:
    """A front that moved on: the side's next ground mark, if the front is past it, lifts its morale by 5 %. One
    mark a call, however far the front jumped."""
    index = len(side.ground_marks)
    if index < len(GROUND_MARKS) and ground_percent(battle, side, front) > GROUND_MARKS[index]:
        side.ground_marks.add(GROUND_MARKS[index])
        adjust(battle, side.name, "ground")


def start_front(width: float, name: str) -> float:
    """Where a side's front starts and returns to: the British one pixel behind the left edge, the Germans at the
    field's right edge (F5:7301-7302)"""
    return -1.0 if name == "british" else width


def ground_bar(width: float, name: str, front: float) -> int:
    """A side's whole-percent ground (F5:3841-3843)"""
    if name == "british":
        return flash_round(front / (width - BAR_MARGIN) * 100)
    return 100 - flash_round((front - BAR_MARGIN) / width * 100)


def move_front(battle: "Battle", side: "Side") -> None:
    """One side's loop of updateProgressBar: a squad whose leader is past the front takes it over (newest squad
    first, each such squad checked for a ground mark), then a front whose squad lost every member drops back"""
    for squad in battle.newest_first(side.squads):
        if not squad.members:
            continue
        x = squad.members[0].x
        if (x > side.front) if side.name == "british" else (x < side.front):
            side.front_squad = squad
            side.front = x
            ground_mark(battle, side, x)
    if side.front_squad is None or not side.front_squad.members:
        side.front_squad = None
        side.front = start_front(battle.width, side.name)


def update_ground(battle: "Battle") -> None:
    """Both ground bars (updateProgressBar, F5:3807-3869), British before German, and the CPU's panic flags"""
    for name in SIDES:
        side = battle.sides[name]
        move_front(battle, side)
        side.ground = ground_bar(battle.width, name, side.front)
    for name in SIDES:
        battle.sides[name].panic = battle.sides[other_side(name)].ground >= PANIC_GROUND


def check_surrender(battle: "Battle") -> None:
    """updateMoraleBar's checks (F5:5674-5691): morale never above its maximum, and a side at 0 or less loses. The
    player's side is checked first, so both at 0 is a loss."""
    for side in battle.sides.values():
        side.morale = min(side.morale, side.morale_max)
    for name in player_order(battle):
        if battle.sides[name].morale <= 0:
            end(battle, other_side(name), "morale")


def conquer(battle: "Battle", side: str) -> None:
    """A soldier or tank of `side` crossed the conquer line: that side wins on ground"""
    end(battle, side, "ground")


def end(battle: "Battle", winner: str, how: str) -> None:
    """endBattle (F5:4237-4319), once only (B15): the winners' squads cheer, the losers' surrender. The page ends the
    run six seconds later (postBattleScreen)."""
    if battle.state != "playing":
        return
    battle.state = "ended"
    battle.ended_at = battle.step
    battle.winner = winner
    battle.how = how
    for name, side in battle.sides.items():
        for squad in side.squads:
            squad.state = "victory" if name == winner else "defeated"
    battle.event("end", SIDES.index(winner), how)


def trenches_held(battle: "Battle", name: str) -> int:
    return sum(1 for trench in battle.trenches if trench.owner == name)


def stats(battle: "Battle") -> dict[str, dict[str, int]]:
    """The results screen's counts for both sides (postBattleScreen, F5:4358-4374)"""
    result = {}
    for name, side in battle.sides.items():
        side.trenches_held = trenches_held(battle, name)
        result[name] = {
            "kills": side.kills,
            "lost": side.lost,
            "deployed": side.deployed,
            "trenches": side.trenches_held,
            "support": side.support_used,
        }
    return result


def bonus_xp(battle: "Battle", side: str) -> int:
    """The bonus XP a campaign win pays (postBattleScreen, F5:4430-4469); nothing for a loss or a Custom Battle.
    British: trenches held plus kills over the enemy's plus the mission number. German: trenches held plus kills over
    the enemy's minus fire support used. Each is times 10, and never below 0."""
    if not battle.campaign or battle.winner != side:
        return 0
    mine = battle.sides[side]
    foe = battle.sides[other_side(side)]
    lead = max(0, mine.kills - foe.kills)
    if side == "british":
        points = trenches_held(battle, side) + lead + (battle.mission.number or 0)
    else:
        points = trenches_held(battle, side) + lead - mine.support_used
    return max(0, flash_round(points * 10))
