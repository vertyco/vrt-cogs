"""Every number FarmCord's rules and page share: crops, animals, tools, plots, storage, rooms, cosmetics and
achievements, plus the limits and clock marks. Times are seconds, prices are FarmCoins"""

from dataclasses import asdict, dataclass

# This module is the bottom of the import chain (the calendar reads crop seasons from it), so the time units live
# here and farmcord.game.calendar names them for the game code
HOUR = 3600.0
DAY = 24 * HOUR

SWITCH_FEE = 250
PEN_SIZE = 6
SPOTS = 9
MAX_LEVEL = 100
DESCRIPTION_LIMIT = 200

# The level curve: reaching level L takes round(LEVEL_FACTOR * (L ** LEVEL_POWER - 1)) XP in all. In the balance
# simulation these hold level 90 at about 14 days of nonstop play and 25.5 of casual play: test_balance.py checks it
# after any change here
LEVEL_FACTOR = 8
LEVEL_POWER = 2.2

# How long after a crop ripens it stays fresh, dries, withers and then rots, and what each state is worth
FRESH_UNTIL = 8 * HOUR
DRIED_UNTIL = 24 * HOUR
ROT_AFTER = 48 * HOUR
DRIED_VALUE = 0.75
WITHERED_VALUE = 0.5
# Each growth stage that ended dry takes this share off a harvest
DRY_STAGE_LOSS = 0.15

# An animal needs feed and water once per window. Left alone it turns sickly, then malnourished (for good), then dies
CARE_WINDOW = 8 * HOUR
SICKLY_AFTER = 24 * HOUR
MALNOURISHED_AFTER = 72 * HOUR
DEATH_AFTER = 7 * DAY
# A sickly animal is healthy again after this long without a missed window
HEAL_AFTER = 24 * HOUR
SICKLY_VALUE = 0.75
MALNOURISHED_VALUE = 0.25

CREDIT = "Game design by Vainne"
CREDIT_URL = "https://github.com/Atuelliss"


@dataclass(frozen=True)
class Crop:
    key: str
    name: str
    level: int
    seasons: tuple[str, ...]
    grow_time: float
    seed_price: int
    sell_price: int
    xp: int
    # Bushes keep producing after a harvest, feed crops can be fed to any animal
    bush: bool = False
    feed: bool = False


@dataclass(frozen=True)
class Animal:
    key: str
    name: str
    level: int
    grow_time: float
    baby_price: int
    adult_price: int
    adult_xp: int
    feed_price: int


@dataclass(frozen=True)
class Can:
    key: str
    tier: int
    name: str
    capacity: int
    level: int
    price: int


@dataclass(frozen=True)
class Hoe:
    key: str
    tier: int
    name: str
    level: int
    price: int


@dataclass(frozen=True)
class PlotInfo:
    number: int
    level: int
    price: int


@dataclass(frozen=True)
class StorageInfo:
    tier: int
    limit: int
    level: int
    price: int


@dataclass(frozen=True)
class RoomInfo:
    number: int
    name: str
    level: int
    price: int


@dataclass(frozen=True)
class Cosmetic:
    key: str
    name: str
    # "decoration", "hat", "top" or "bottom"
    kind: str
    level: int
    price: int


@dataclass(frozen=True)
class Achievement:
    key: str
    name: str
    difficulty: str
    coins: int
    xp: int


CROPS = {
    crop.key: crop
    for crop in (
        Crop("wildflowers", "Wildflowers", 1, ("spring", "summer", "autumn"), 0.5 * HOUR, 3, 4, 5),
        Crop("tulips", "Tulips", 3, ("winter", "spring"), 1 * HOUR, 6, 9, 10),
        Crop("lilies", "Lilies", 6, ("spring", "summer"), 1.5 * HOUR, 8, 13, 15),
        Crop("wheat", "Wheat", 10, ("summer", "autumn", "winter"), 2 * HOUR, 12, 18, 21, feed=True),
        Crop("radishes", "Radishes", 14, ("spring", "autumn", "winter"), 3 * HOUR, 18, 28, 32, feed=True),
        Crop("potatoes", "Potatoes", 18, ("spring", "autumn", "winter"), 4 * HOUR, 25, 39, 44, feed=True),
        Crop("peanuts", "Peanuts", 23, ("summer", "autumn"), 5 * HOUR, 33, 51, 56),
        Crop("corn", "Corn", 28, ("summer", "autumn"), 6 * HOUR, 41, 64, 68, feed=True),
        Crop("peppers", "Peppers", 33, ("summer", "autumn"), 8 * HOUR, 57, 89, 93),
        Crop("sunflowers", "Sunflowers", 38, ("summer", "autumn"), 10 * HOUR, 74, 115, 119),
        Crop("hops", "Hops", 43, ("summer", "autumn"), 12 * HOUR, 92, 143, 146),
        Crop("blueberries", "Blueberries", 48, ("spring", "summer"), 14 * HOUR, 440, 104, 174, bush=True),
        Crop("blackberries", "Blackberries", 54, ("summer", "autumn"), 16 * HOUR, 525, 123, 203, bush=True),
        Crop("cranberries", "Cranberries", 60, ("autumn", "winter"), 18 * HOUR, 615, 144, 234, bush=True),
        Crop("watermelon", "Watermelon", 68, ("spring", "summer"), 20 * HOUR, 179, 280, 268),
        Crop("pumpkin", "Pumpkin", 78, ("autumn", "winter"), 24 * HOUR, 228, 356, 334, feed=True),
    )
}

ANIMALS = {
    animal.key: animal
    for animal in (
        Animal("chicken", "Chicken", 8, 4 * HOUR, 30, 85, 50, 2),
        Animal("goose", "Goose", 20, 6 * HOUR, 60, 150, 79, 3),
        Animal("pig", "Pig", 35, 8 * HOUR, 110, 245, 113, 4),
        Animal("goat", "Goat", 50, 12 * HOUR, 180, 410, 180, 6),
        Animal("cow", "Cow", 65, 16 * HOUR, 280, 615, 254, 8),
        Animal("horse", "Horse", 80, 24 * HOUR, 450, 1000, 403, 10),
    )
}

# Indexed by tier, so CANS[farm.can_tier] is the can the player holds
CANS = (
    Can("watering_can", 0, "Watering can", 10, 1, 0),
    Can("big_watering_can", 1, "Big watering can", 25, 5, 400),
    Can("sprinkler_can", 2, "Sprinkler can", 50, 12, 2500),
)

HOES = (
    Hoe("hoe", 0, "Hoe", 1, 0),
    Hoe("wide_hoe", 1, "Wide hoe", 8, 800),
    Hoe("plow", 2, "Plow", 15, 3000),
)

PLOTS = {
    plot.number: plot
    for plot in (
        PlotInfo(1, 1, 0),
        PlotInfo(2, 5, 500),
        PlotInfo(3, 15, 1000),
        PlotInfo(4, 25, 2500),
        PlotInfo(5, 50, 5000),
        PlotInfo(6, 75, 10000),
        PlotInfo(7, 90, 20000),
    )
}

# Indexed by tier, so STORAGE[farm.storage_tier].limit is how many of each item fit
STORAGE = (
    StorageInfo(0, 25, 1, 0),
    StorageInfo(1, 50, 10, 500),
    StorageInfo(2, 100, 30, 2500),
    StorageInfo(3, 200, 60, 10000),
)

# The farmhouse's own main room is free, so only rooms 2 and 3 are for sale
ROOMS = {
    room.number: room
    for room in (
        RoomInfo(2, "Second room", 20, 1500),
        RoomInfo(3, "Third room", 50, 6000),
    )
}

COSMETICS = {
    item.key: item
    for item in (
        Cosmetic("wooden_fence", "Wooden fence", "decoration", 1, 50),
        Cosmetic("flower_pot", "Flower pot", "decoration", 3, 80),
        Cosmetic("hay_bale", "Hay bale", "decoration", 8, 120),
        Cosmetic("bench", "Bench", "decoration", 12, 250),
        Cosmetic("birdhouse", "Birdhouse", "decoration", 18, 400),
        Cosmetic("scarecrow", "Scarecrow", "decoration", 25, 600),
        Cosmetic("lantern", "Lantern", "decoration", 30, 750),
        Cosmetic("garden_gnome", "Garden gnome", "decoration", 40, 1000),
        Cosmetic("well", "Well", "decoration", 55, 2500),
        Cosmetic("windmill", "Windmill", "decoration", 70, 5000),
        Cosmetic("straw_hat", "Straw hat", "hat", 1, 50),
        Cosmetic("cap", "Cap", "hat", 10, 150),
        Cosmetic("cowboy_hat", "Cowboy hat", "hat", 30, 800),
        Cosmetic("beanie", "Beanie", "hat", 45, 1200),
        Cosmetic("plaid_shirt", "Plaid shirt", "top", 1, 50),
        Cosmetic("t_shirt", "T-shirt", "top", 12, 200),
        Cosmetic("sweater", "Sweater", "top", 35, 900),
        Cosmetic("jacket", "Jacket", "top", 60, 2000),
        Cosmetic("blue_overalls", "Blue overalls", "bottom", 1, 50),
        Cosmetic("red_overalls", "Red overalls", "bottom", 15, 300),
        Cosmetic("jeans", "Jeans", "bottom", 40, 1000),
    )
}

# FarmCoins and XP an achievement pays, by how hard it is
REWARDS = {"easy": (50, 25), "medium": (150, 100), "hard": (500, 400)}


def achievement(key: str, name: str, difficulty: str) -> Achievement:
    coins, xp = REWARDS[difficulty]
    return Achievement(key, name, difficulty, coins, xp)


ACHIEVEMENTS = {
    a.key: a
    for a in (
        achievement("first_crop", "Grow your first crop", "easy"),
        achievement("every_crop", "Grow one of each crop", "hard"),
        achievement("free_seeds", "Get free seeds from a harvest", "easy"),
        achievement("exceptional_crop", "Harvest an exceptional crop", "medium"),
        achievement("exceptional_animal", "Raise an exceptional animal", "medium"),
        achievement("sell_crop", "Sell a crop", "easy"),
        achievement("sell_animal", "Sell an animal", "easy"),
        achievement("sell_10_crops", "Sell 10 crops", "easy"),
        achievement("sell_10_animals", "Sell 10 animals", "medium"),
        achievement("sell_25_crops", "Sell 25 crops", "medium"),
        achievement("sell_25_animals", "Sell 25 animals", "medium"),
        achievement("breed_5", "Breed 5 times", "medium"),
        achievement("breed_15", "Breed 15 times", "hard"),
        achievement("perfect_crop", "Raise a perfect crop", "medium"),
        achievement("perfect_animal", "Raise a perfect animal", "hard"),
    )
}


def unlock_rows():
    """(level, kind, key, name) for everything in the catalog that opens at a level"""
    for crop in CROPS.values():
        yield crop.level, "crop", crop.key, crop.name
    for animal in ANIMALS.values():
        yield animal.level, "animal", animal.key, animal.name
    for tool in (*CANS, *HOES):
        yield tool.level, "tool", tool.key, tool.name
    for plot in PLOTS.values():
        yield plot.level, "plot", str(plot.number), f"Plot {plot.number}"
    for tier in STORAGE:
        yield tier.level, "storage", str(tier.tier), f"Storage for {tier.limit} of each item"
    for room in ROOMS.values():
        yield room.level, "room", str(room.number), room.name
    for item in COSMETICS.values():
        yield item.level, "cosmetic", item.key, item.name


UNLOCKS = tuple(unlock_rows())


def unlocks_at(level: int) -> list[dict]:
    """What reaching `level` opens up, as {kind, key, name} entries"""
    return [{"kind": kind, "key": key, "name": name} for at, kind, key, name in UNLOCKS if at == level]


def catalog_payload() -> dict:
    """The whole catalog as JSON-ready data for the page"""
    return {
        "crops": [asdict(crop) | {"seasons": list(crop.seasons)} for crop in CROPS.values()],
        "animals": [asdict(animal) for animal in ANIMALS.values()],
        "cans": [asdict(can) for can in CANS],
        "hoes": [asdict(hoe) for hoe in HOES],
        "plots": [asdict(plot) for plot in PLOTS.values()],
        "storage": [asdict(tier) for tier in STORAGE],
        "rooms": [asdict(room) for room in ROOMS.values()],
        "cosmetics": [asdict(item) for item in COSMETICS.values()],
        "achievements": [asdict(a) for a in ACHIEVEMENTS.values()],
        "constants": {
            "switch_fee": SWITCH_FEE,
            "pen_size": PEN_SIZE,
            "spots": SPOTS,
            "max_level": MAX_LEVEL,
            "description_limit": DESCRIPTION_LIMIT,
            "fresh_until": FRESH_UNTIL,
            "dried_until": DRIED_UNTIL,
            "rot_after": ROT_AFTER,
            "dried_value": DRIED_VALUE,
            "withered_value": WITHERED_VALUE,
            "dry_stage_loss": DRY_STAGE_LOSS,
            "care_window": CARE_WINDOW,
            "sickly_after": SICKLY_AFTER,
            "malnourished_after": MALNOURISHED_AFTER,
            "death_after": DEATH_AFTER,
            "heal_after": HEAL_AFTER,
            "sickly_value": SICKLY_VALUE,
            "malnourished_value": MALNOURISHED_VALUE,
            "credit": CREDIT,
            "credit_url": CREDIT_URL,
        },
    }
