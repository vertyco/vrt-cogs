"""Morale, ground taken, the ways to win and the end of a battle.

Morale (adjustMorale, F6:8212-8381): every death, destroyed tank or bunker and flanking squad moves a side's morale,
and a side whose morale reaches 0 surrenders at the next slow tick (updateMoraleBar, F6:8411-8470). Morale also comes
back by numbers (moraleRegen, F6:8382-8410). Ground (updateProgressBar, F6:5705-5811): each side's front is its most
forward squad leader, the bunker included; the bars are whole percents.

The ways to win, `how` a battle ended: "conquer" (a leader or tank in lane 2 crossed the conquer line), "morale" (a
side's morale ran out), "objective" (an objective squad was wiped out), "defend" (a defend mission's countdown ran out
and the CPU had no squads left), "surrender" (the player quit the battle), "left" (the player left a versus game).
A squad whose leader leaves the far edge of lane 1 or 3 flanks: it is removed, not lost, and the other side loses
morale. The battle ends once, on the first ending; squads then cheer or surrender and nothing else counts (B15).

Quick messages go out as "msg" events: key "lowMorale" or "breaking", and the side whose morale it is, or "depleted"
for the side that has to finish the defend mission's last squads off. The page words them for whoever is looking
("MORALE IS LOW!" for your side, "ENEMY MORALE IS LOW!" for the other). A flank goes out as a "flank" event naming the
side that flanked.
"""

import math
import typing as t

from .data import (
    BLAST_GAIN,
    BONUS_XP_RATE,
    BULLET_GAIN,
    FLANK_LOSS,
    MESSAGE_COOLDOWN_S,
    MORALE_COST,
    OBJECTIVE_DELAY_MS,
    OFFICER_BLAST,
    REGEN_MINUS,
    REGEN_PLUS,
    SIDES,
)

if t.TYPE_CHECKING:
    from .battle import Battle, Side
    from .squads import Squad

# Percent of a side's maximum morale where a quick message shows: (highest, lowest, key), F6:8318-8380
MORALE_MESSAGES = ((30, 25, "lowMorale"), (10, 5, "breaking"))
BAR_MARGIN = 60  # the progress bar leaves 60 pixels at the far end, F6:5740-5741


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
    default cases). A blast costs a soldier the same as a bullet and an officer 1.3 times as much; an officer's death
    gives the other side nothing."""
    blast = how == "explosive"
    if how not in ("normal", "explosive"):
        return
    soldier = MORALE_COST["officer" if kind == "officer" else "soldier"]
    lost = soldier * (OFFICER_BLAST if blast and kind == "officer" else 1)
    mine.morale -= lost
    mine.morale_lost += lost
    if kind != "officer":
        gained = MORALE_COST["soldier"] * (BLAST_GAIN if blast else BULLET_GAIN)
        other.morale += gained
        other.morale_gained += gained


def flank_hit(victim: "Side") -> None:
    """adjustMorale's "flanked" case: the side that was flanked loses a fifth of its own maximum. American Secure
    Flanks takes a fifth off that loss."""
    loss = FLANK_LOSS * victim.morale_max
    if victim.has("flank_morale"):
        loss *= victim.effect("flank_morale")
    victim.morale -= loss


def adjust(battle: "Battle", side: str, kind: str, how: str | None = None, owner: str | None = None) -> None:
    """adjustMorale (F6:8212-8381) for `side`. `kind` is the dead squad's kind, "tank", "bunker" or "flanked" (then
    `side` is the side that flanked); `how` is "normal" (a bullet) or "explosive" (a blast) for deaths; `owner` is the
    side whose blast it was."""
    mine = battle.sides[side]
    other = battle.sides[other_side(side)]
    if owner == side:
        mine.morale -= MORALE_COST["friendly_fire"]
    if kind in ("tank", "bunker"):
        mine.morale -= MORALE_COST[kind]
        other.morale += MORALE_COST[f"{kind}_killed"]
    elif kind == "flanked":
        flank_hit(other)
    else:
        death_cost(mine, other, kind, how)
    cap_morale(battle)
    quick_messages(battle)


def cap_morale(battle: "Battle") -> None:
    for side in battle.sides.values():
        side.morale = min(side.morale, side.morale_max)


def quick_messages(battle: "Battle") -> None:
    """The four morale warnings adjustMorale checks after every change, the other side's before the player's. Each
    shows once, then waits 15 seconds before it may show again."""
    for name in reversed(player_order(battle)):
        side = battle.sides[name]
        percent = side.morale / side.morale_max * 100
        for high, low, key in MORALE_MESSAGES:
            if low <= percent <= high and key not in side.shown:
                side.shown.add(key)
                battle.after(MESSAGE_COOLDOWN_S * 1000, lambda side=side, key=key: side.shown.discard(key))
                battle.event("msg", key, side.index, None)


def army_count(battle: "Battle", name: str) -> int:
    """Living members on the field; a tank or the bunker counts 1"""
    return sum(len(squad.members) for squad in battle.sides[name].squads)


def regen(battle: "Battle") -> None:
    """Morale comes back by numbers (moraleRegen, F6:8382-8410, every slow tick): a side with more than twice the
    other's members gains 1 % and the other loses 1 %."""
    british, german = (army_count(battle, name) for name in SIDES)
    factors = (1.0, 1.0)
    if british / 2 > german and german > 0:
        factors = (REGEN_PLUS, REGEN_MINUS)
    elif british < german / 2 and british > 0:
        factors = (REGEN_MINUS, REGEN_PLUS)
    for name, factor in zip(SIDES, factors, strict=True):
        battle.sides[name].morale *= factor
    cap_morale(battle)
    quick_messages(battle)


def start_front(width: float, name: str) -> float:
    """Where a side's front starts and returns to: the British one pixel behind the left edge, the Germans at the
    field's right edge (F6:10965-10966)"""
    return -1.0 if name == "british" else width


def ground_bar(width: float, name: str, front: float) -> int:
    """A side's whole-percent ground (F6:5740-5743)"""
    if name == "british":
        return flash_round(front / (width - BAR_MARGIN) * 100)
    return 100 - flash_round((front - BAR_MARGIN) / width * 100)


def move_front(battle: "Battle", side: "Side") -> None:
    """One side's loop of updateProgressBar: a squad whose leader is past the front takes it over (newest squad
    first), then a front whose squad lost every member drops back. The bunker is a German squad, so it counts."""
    for squad in battle.newest_first(side.squads):
        if not squad.members:
            continue
        x = squad.members[0].x
        if (x > side.front) if side.name == "british" else (x < side.front):
            side.front_squad = squad
            side.front = x
    if side.front_squad is None or not side.front_squad.members:
        side.front_squad = None
        side.front = start_front(battle.width, side.name)


def update_ground(battle: "Battle") -> None:
    """Both ground bars (updateProgressBar, F6:5705-5811), British before German. Ground no longer changes morale."""
    for name in SIDES:
        side = battle.sides[name]
        move_front(battle, side)
        side.ground = ground_bar(battle.width, name, side.front)


def check_surrender(battle: "Battle") -> None:
    """updateMoraleBar's checks (F6:8411-8423): morale never above its maximum, and a side at 0 or less loses. The
    player's side is checked first, so both at 0 is a loss."""
    cap_morale(battle)
    for name in player_order(battle):
        if battle.sides[name].morale <= 0:
            end(battle, other_side(name), "morale")


def conquer(battle: "Battle", side: str) -> None:
    """A leader or tank of `side` in lane 2 crossed the conquer line (F6:2133-2136, 2165-2168, 3184-3248). It is
    called on every step the line stays crossed, and only the first counts (B15)."""
    end(battle, side, "conquer")


def flank(battle: "Battle", squad: "Squad") -> None:
    """A squad in lane 1 or 3 whose leader left the far edge (F6:2125-2131, 2157-2163, 3175-3248, B45) is removed from
    the field and the other side loses morale (removeSquad, F6:4785-4810). The squad is not counted as lost, and its
    front goes with it."""
    side = battle.sides[squad.side]
    if squad not in side.squads:
        return
    if squad.cover is not None and squad.cover.holder is squad:
        squad.cover.holder = None
    side.squads.remove(squad)
    squad.members.clear()
    adjust(battle, squad.side, "flanked")
    battle.event("flank", side.index)


def objective_down(battle: "Battle", squad: "Squad") -> None:
    """An objective squad was wiped out, by any means (B49): the side opposing its owner wins 3 seconds later on the
    battle clock (F6:4699-4704, B50). Nothing is queued once the battle is over."""
    if not squad.objective or battle.state != "playing":
        return
    winner = other_side(squad.side)
    battle.objective_timers.append(battle.after(OBJECTIVE_DELAY_MS, lambda: end(battle, winner, "objective")))


def second_tick(battle: "Battle") -> None:
    """oneSecondEnterFrame's timers (F6:10031-10041): the defend countdown, then the mission clock"""
    defend_tick(battle)
    battle.mission_seconds += 1


def defend_tick(battle: "Battle") -> None:
    """timerTick (F6:9665-9707): a defend mission's countdown runs down a second. Once it is below 0 the CPU deploys
    no more, and the player wins as soon as the CPU has no squad left (the bunker counts)."""
    if battle.defend_left is None:
        return
    battle.defend_left = max(-1, battle.defend_left - 1)
    if battle.defend_left >= 0:
        return
    player, comp = player_order(battle)
    if battle.spawn_active and battle.sides[comp].squads:
        battle.event("msg", "depleted", battle.sides[player].index, None)
    battle.spawn_active = False
    if not battle.sides[comp].squads:
        end(battle, player, "defend")


def end(battle: "Battle", winner: str, how: str) -> None:
    """endBattle (F6:6804-6932), once only (B15): pending objective timers and every pre-placed spawn still waiting
    are dropped (B53), the winners' squads cheer and the losers' surrender. The page ends the run six seconds later
    (postBattleScreen)."""
    if battle.state != "playing":
        return
    battle.state = "ended"
    battle.ended_at = battle.step
    battle.winner = winner
    battle.how = how
    for timer in battle.objective_timers + battle.spawn_timers:
        timer.cancel()
    for name, side in battle.sides.items():
        for squad in side.squads:
            squad.state = "victory" if name == winner else "defeated"
    battle.event("end", SIDES.index(winner), how)


def trenches_held(battle: "Battle", name: str) -> int:
    """Covers a side has claimed (B47)"""
    return sum(1 for cover in battle.covers if cover.owner == name)


def stats(battle: "Battle") -> dict[str, dict[str, int]]:
    """The results screen's counts for both sides (postBattleScreen, F6:6951-6985)"""
    result = {}
    for name, side in battle.sides.items():
        side.covers_held = trenches_held(battle, name)
        result[name] = {
            "kills": side.kills,
            "lost": side.lost,
            "deployed": side.deployed,
            "covers": side.covers_held,
            "support": side.support_used,
        }
    return result


def bonus_xp(battle: "Battle", side: str) -> int:
    """The bonus XP a campaign win pays (F6:7056-7082); nothing for a loss or a Custom Battle. Both sides alike:
    round((covers held + kills over the enemy's + the mission number) x 5), never below 0, plus the mission's time
    bonus less the seconds played when that is above 0."""
    if not battle.campaign or battle.winner != side:
        return 0
    mine = battle.sides[side]
    foe = battle.sides[other_side(side)]
    lead = max(0, mine.kills - foe.kills)
    points = trenches_held(battle, side) + lead + (battle.mission.number or 0)
    quick = flash_round(battle.mission.time_bonus - battle.mission_seconds)
    return max(0, flash_round(points * BONUS_XP_RATE)) + max(0, quick)
