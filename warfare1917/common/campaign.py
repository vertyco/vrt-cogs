"""Campaign saves, XP, levels, upgrades and the settings checks for Custom Battle and versus.

A save is a plain dict, one per Discord user, holding what the original keeps in its SharedObject (saveGame,
F5:34-70): the side, the mission to play next, XP, level, upgrade points, the owned upgrades and the 20 career
counts. The cog reads and writes the Config; every function here takes the dict and changes it in place.

Save keys:
    side: "british" | "german".
    mission: 1 to 9, the mission to play next. After winning mission 9 it stays 9 and `finished` is true.
    xp, level, points: experience, level (0 to 19) and unspent upgrade points.
    upgrades: sorted owned upgrade numbers, 1 to 22.
    career: the 20 counts named like the original's `career_<name>` variables, without the prefix.
    finished: the campaign was won.
"""

import typing as t

from .data import LEVELS, SIDES, SUPPORT_KINDS, UNIT_KINDS, UPGRADE_NEEDS, UPGRADES
from .missions import CAMPAIGNS, CUSTOM_MAPS, Mission
from .morale import bonus_xp, trenches_held

if t.TYPE_CHECKING:
    from .battle import Battle

LAST_MISSION = 9
UPGRADE_COUNT = 22

# The 20 career counts in the order the original saves them (F5:50-69)
CAREER_KEYS = (
    "soldiersKilled",
    "soldiersLost",
    "trenchesTaken",
    "supportUsed",
    "wins",
    "losses",
    "moraleWins",
    "moraleLosses",
    "conquerWins",
    "conquerLosses",
    "moraleGained",
    "moraleLost",
    "experienceGained",
    "bonusExpGained",
    "riflemenDeployed",
    "assaultDeployed",
    "machineGunDeployed",
    "sniperDeployed",
    "officerDeployed",
    "tankDeployed",
)

MOODS = ("aggressive", "balanced", "defensive")
DIFFICULTIES = ("easy", "medium", "hard")
MINES = ("none", "few", "medium", "many")
MAX_TRENCHES = 5
MAX_WIRE = 4


def new_save(side: str) -> dict:
    """A fresh campaign on `side`: mission 1, no XP, no upgrades, every career count 0 (F5:421-428, resetCareerStats
    F5:6763-6785)"""
    if side not in SIDES:
        raise ValueError(f"unknown side {side!r}")
    return {
        "side": side,
        "mission": 1,
        "xp": 0,
        "level": 0,
        "points": 0,
        "upgrades": [],
        "career": dict.fromkeys(CAREER_KEYS, 0),
        "finished": False,
    }


def mission_for(save: dict) -> Mission:
    """The mission the save plays next (a finished save gives mission 9 again)"""
    return CAMPAIGNS[save["side"]][save["mission"] - 1]


def level_floor(level: int) -> int:
    """The XP a level starts above (the XP bar's left end, F5:503-521)"""
    return LEVELS[level - 1] if level > 0 else 0


def unlocked(owned: t.Collection[int], number: int) -> bool:
    """Whether an upgrade's row above is owned, so it can be bought (checkUpgrades, F5:5079-5150): a second-row
    upgrade needs the one above it, a third-row upgrade needs either full column above it"""
    needs = UPGRADE_NEEDS.get(number)
    if needs is None:
        return True
    return any(all(need in owned for need in column) for column in needs)


def open_upgrades(save: dict) -> list[int]:
    """Upgrades that are unlocked and not owned yet, whatever the points (the buttons' "open" colour, F5:5021-5078)"""
    owned = save["upgrades"]
    return [n for n in range(1, UPGRADE_COUNT + 1) if n not in owned and unlocked(owned, n)]


def can_buy(save: dict, number: int) -> bool:
    """buyUpgrade's test (F5:5151-5163): unlocked, not owned and enough points"""
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= UPGRADE_COUNT:
        return False
    if number in save["upgrades"] or not unlocked(save["upgrades"], number):
        return False
    return save["points"] >= UPGRADES[save["side"]][number]["cost"]


def buy(save: dict, number: int) -> bool:
    """Spend the points and own the upgrade. False when it can't be bought"""
    if not can_buy(save, number):
        return False
    save["points"] -= UPGRADES[save["side"]][number]["cost"]
    save["upgrades"] = sorted([*save["upgrades"], number])
    return True


def view(save: dict) -> dict:
    """The campaign view the page gets (spec F): the save plus what the map screen shows for its mission. `open` is
    the upgrades whose button is lit; `level_xp` is [this level's floor, next level's], and the next is null at the
    top level. `new` lists the unit and support keys the mission brings, shown as unlock dialogs on every visit to
    the map (checkForUnlocks, F5:5841-5853)."""
    mission = mission_for(save)
    level = save["level"]
    return {
        "side": save["side"],
        "mission": save["mission"],
        "xp": save["xp"],
        "level": level,
        "points": save["points"],
        "level_xp": [level_floor(level), LEVELS[level] if level < len(LEVELS) else None],
        "upgrades": list(save["upgrades"]),
        "open": open_upgrades(save),
        "career": dict(save["career"]),
        "units": list(mission.units[save["side"]]),
        "supports": list(mission.supports[save["side"]]),
        "new": list(mission.new),
        "title": mission.title,
        "description": mission.description,
        "section": mission.section,
        "finished": save["finished"],
    }


def pay_xp(save: dict, battle: "Battle") -> int:
    """Add the battle's kill XP that the save doesn't hold yet, so a level reached mid-battle can be spent at once
    (updateExperience, F5:5969-6070). Returns the levels gained"""
    unpaid = battle.kill_xp[save["side"]] - battle.xp_paid
    if unpaid <= 0:
        return 0
    battle.xp_paid += unpaid
    return add_xp(save, unpaid)


def add_xp(save: dict, amount: int) -> int:
    """Add XP and level up (updateExperience's loop, F5:6035-6055): a level is reached once XP goes above its
    threshold and gives one upgrade point. Returns the levels gained."""
    save["xp"] += amount
    gained = 0
    while save["level"] < len(LEVELS) and save["xp"] > LEVELS[save["level"]]:
        save["level"] += 1
        save["points"] += 1
        gained += 1
    return gained


def level_marks(save: dict) -> list[int]:
    """Kill XP a battle must pass for each level still to come: the XP above the save's now that reaches each level's
    threshold (add_xp's test)"""
    return [LEVELS[level] - save["xp"] for level in range(save["level"], len(LEVELS))]


def count_battle(save: dict, battle: "Battle", won: bool, gained: int, bonus: int) -> None:
    """The battle's career counts (endBattle F5:4237-4270, postBattleScreen F5:4375-4381, 4490-4496, createSquad
    F5:1058, kills F5:2840-2845, adjustMorale F5:5527-5598). Morale is rounded to hundredths to keep sums tidy."""
    career = save["career"]
    mine = battle.sides[save["side"]]
    ground = battle.how == "ground"
    career["wins" if won else "losses"] += 1
    career[("conquer" if ground else "morale") + ("Wins" if won else "Losses")] += 1
    career["soldiersKilled"] += mine.soldier_kills
    career["soldiersLost"] += mine.soldier_losses
    career["trenchesTaken"] += trenches_held(battle, save["side"])
    career["supportUsed"] += mine.support_used
    career["moraleGained"] = round(career["moraleGained"] + mine.morale_gained, 2)
    career["moraleLost"] = round(career["moraleLost"] + mine.morale_lost, 2)
    career["experienceGained"] += gained
    career["bonusExpGained"] += bonus
    for kind in UNIT_KINDS:
        career[f"{kind}Deployed"] += mine.deployed_kinds.get(kind, 0)


def apply_result(save: dict, battle: "Battle", first_try: bool) -> dict:
    """Fold a finished campaign battle into the save. Kill XP counts on a first try only; the bonus XP comes with a
    win either way. A win moves to the next mission (loadNextBattle, F5:4326-4338) and winning mission 9 finishes
    the campaign; a loss keeps the mission, to be played again as a retry. Returns what changed:
    {"won", "kill_xp", "bonus_xp", "levels", "retry", "finished"}. A battle that ended with no winner changes
    nothing."""
    side = save["side"]
    if battle.winner is None:
        return {"won": False, "kill_xp": 0, "bonus_xp": 0, "levels": 0, "retry": not first_try, "finished": False}
    won = battle.winner == side
    kill_xp = battle.kill_xp[side] if first_try else 0
    bonus = bonus_xp(battle, side)
    # Kill XP already in the save from the battle's level-ups and purchases (Battle.xp_paid) isn't added twice
    levels = add_xp(save, kill_xp - battle.xp_paid + bonus)
    battle.xp_paid = kill_xp
    count_battle(save, battle, won, kill_xp + bonus, bonus)
    if won and save["mission"] == LAST_MISSION:
        save["finished"] = True
    elif won:
        save["mission"] += 1
    return {
        "won": won,
        "kill_xp": kill_xp,
        "bonus_xp": bonus,
        "levels": levels,
        "retry": not won,
        "finished": save["finished"],
    }


def whole(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def flags(value: object, size: int) -> bool:
    return isinstance(value, list) and len(value) == size and all(isinstance(item, bool) for item in value)


def check_custom(value: object, versus: bool) -> dict | None:
    """A Custom Battle's or versus game's settings (spec F), or None when anything is off: a wrong type, a value
    outside its list or range, or no unit picked. Only the known keys come back; a versus game has no difficulty."""
    if not isinstance(value, dict):
        return None
    checks = {
        "side": value.get("side") in SIDES,
        "units": flags(value.get("units"), len(UNIT_KINDS)) and any(value["units"]),
        "supports": flags(value.get("supports"), len(SUPPORT_KINDS)),
        "mood": value.get("mood") in MOODS,
        "map": value.get("map") in tuple(CUSTOM_MAPS),
        "trenches": whole(value.get("trenches"), 0, MAX_TRENCHES),
        "wire": whole(value.get("wire"), 0, MAX_WIRE),
        "mines": value.get("mines") in MINES,
    }
    if not versus:
        checks["difficulty"] = value.get("difficulty") in DIFFICULTIES
    if not all(checks.values()):
        return None
    return {key: list(value[key]) if isinstance(value[key], list) else value[key] for key in checks}
