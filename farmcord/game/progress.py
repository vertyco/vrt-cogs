"""The level curve, level-ups and achievements. Each function returns the events it caused, as the page shows them"""

from bisect import bisect_right

from ..catalog import ACHIEVEMENTS, CROPS, LEVEL_FACTOR, LEVEL_POWER, MAX_LEVEL, unlocks_at
from .model import Farm

# The achievements a farm's counters decide, each with the test for having reached it
COUNTER_GOALS = {
    "every_crop": lambda farm: farm.harvested >= set(CROPS),
    "sell_crop": lambda farm: farm.crops_sold >= 1,
    "sell_animal": lambda farm: farm.animals_sold >= 1,
    "sell_10_crops": lambda farm: farm.crops_sold >= 10,
    "sell_10_animals": lambda farm: farm.animals_sold >= 10,
    "sell_25_crops": lambda farm: farm.crops_sold >= 25,
    "sell_25_animals": lambda farm: farm.animals_sold >= 25,
    "breed_5": lambda farm: farm.litters >= 5,
    "breed_15": lambda farm: farm.litters >= 15,
}


def xp_for_level(level: int) -> int:
    """Total XP needed to reach `level`"""
    return round(LEVEL_FACTOR * (level**LEVEL_POWER - 1))


LEVEL_XP = tuple(xp_for_level(level) for level in range(1, MAX_LEVEL + 1))


def level_for_xp(xp: float) -> int:
    """The highest level `xp` reaches, at most MAX_LEVEL"""
    return max(1, bisect_right(LEVEL_XP, xp))


def gain_xp(farm: Farm, amount: int, now: float) -> list[dict]:
    """Add XP and pay every level it climbs through: 10 FarmCoins times the new level, each"""
    farm.xp += amount
    events = []
    for level in range(farm.level + 1, level_for_xp(farm.xp) + 1):
        coins = 10 * level
        farm.coins += coins
        farm.level = level
        events.append({"kind": "level", "at": now, "level": level, "coins": coins, "unlocks": unlocks_at(level)})
    return events


def earn(farm: Farm, key: str, now: float) -> list[dict]:
    """Give an achievement's FarmCoins and XP, once. Nothing happens if the farm already has it"""
    if key in farm.achievements:
        return []
    achievement = ACHIEVEMENTS[key]
    farm.achievements[key] = now
    farm.coins += achievement.coins
    event = {"kind": "achievement", "at": now, "key": key, "coins": achievement.coins, "xp": achievement.xp}
    return [event, *gain_xp(farm, achievement.xp, now)]


def check_achievements(farm: Farm, now: float) -> list[dict]:
    """Earn every counter achievement the farm has reached: sales, litters and one of each crop"""
    events = []
    for key, reached in COUNTER_GOALS.items():
        if reached(farm):
            events += earn(farm, key, now)
    return events
