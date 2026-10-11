import json

import pytest

from farmcord import catalog
from farmcord.catalog import (
    ACHIEVEMENTS,
    ANIMALS,
    CANS,
    COSMETICS,
    CROPS,
    HOES,
    PLOTS,
    ROOMS,
    STORAGE,
    catalog_payload,
    unlocks_at,
)

HOUR = 3600
DAY = 24 * HOUR


def test_crops_are_the_sixteen_in_level_order():
    assert list(CROPS) == [
        "wildflowers",
        "tulips",
        "lilies",
        "wheat",
        "radishes",
        "potatoes",
        "peanuts",
        "corn",
        "peppers",
        "sunflowers",
        "hops",
        "blueberries",
        "blackberries",
        "cranberries",
        "watermelon",
        "pumpkin",
    ]
    levels = [crop.level for crop in CROPS.values()]
    assert levels == sorted(levels)
    for key, crop in CROPS.items():
        assert crop.key == key


@pytest.mark.parametrize(
    "key,name,level,seasons,grow_time,seed_price,sell_price,xp,bush,feed",
    [
        ("wildflowers", "Wildflowers", 1, ("spring", "summer", "autumn"), 30 * 60, 3, 4, 5, False, False),
        ("hops", "Hops", 43, ("summer", "autumn"), 12 * HOUR, 92, 143, 146, False, False),
        ("blueberries", "Blueberries", 48, ("spring", "summer"), 14 * HOUR, 440, 104, 174, True, False),
        ("pumpkin", "Pumpkin", 78, ("autumn", "winter"), 24 * HOUR, 228, 356, 334, False, True),
    ],
)
def test_crop_rows(key, name, level, seasons, grow_time, seed_price, sell_price, xp, bush, feed):
    crop = CROPS[key]
    assert (crop.name, crop.level, crop.seasons) == (name, level, seasons)
    assert (crop.grow_time, crop.seed_price, crop.sell_price, crop.xp) == (grow_time, seed_price, sell_price, xp)
    assert (crop.bush, crop.feed) == (bush, feed)


def test_bushes_and_feed_crops():
    assert {key for key, crop in CROPS.items() if crop.bush} == {"blueberries", "blackberries", "cranberries"}
    assert {key for key, crop in CROPS.items() if crop.feed} == {"wheat", "radishes", "potatoes", "corn", "pumpkin"}


def test_animals_are_the_six_in_level_order():
    assert list(ANIMALS) == ["chicken", "goose", "pig", "goat", "cow", "horse"]
    levels = [animal.level for animal in ANIMALS.values()]
    assert levels == sorted(levels)
    for key, animal in ANIMALS.items():
        assert animal.key == key


@pytest.mark.parametrize(
    "key,name,level,grow_time,baby_price,adult_price,adult_xp,feed_price",
    [
        ("chicken", "Chicken", 8, 4 * HOUR, 30, 85, 50, 2),
        ("goose", "Goose", 20, 6 * HOUR, 60, 150, 79, 3),
        ("horse", "Horse", 80, 24 * HOUR, 450, 1000, 403, 10),
    ],
)
def test_animal_rows(key, name, level, grow_time, baby_price, adult_price, adult_xp, feed_price):
    animal = ANIMALS[key]
    assert (animal.name, animal.level, animal.grow_time) == (name, level, grow_time)
    assert (animal.baby_price, animal.adult_price, animal.adult_xp, animal.feed_price) == (
        baby_price,
        adult_price,
        adult_xp,
        feed_price,
    )


def test_watering_cans():
    assert [(can.tier, can.name, can.capacity, can.level, can.price) for can in CANS] == [
        (0, "Watering can", 10, 1, 0),
        (1, "Big watering can", 25, 5, 400),
        (2, "Sprinkler can", 50, 12, 2500),
    ]


def test_hoes():
    assert [(hoe.tier, hoe.name, hoe.level, hoe.price) for hoe in HOES] == [
        (0, "Hoe", 1, 0),
        (1, "Wide hoe", 8, 800),
        (2, "Plow", 15, 3000),
    ]


def test_plots():
    assert list(PLOTS) == [1, 2, 3, 4, 5, 6, 7]
    assert [(plot.level, plot.price) for plot in PLOTS.values()] == [
        (1, 0),
        (5, 500),
        (15, 1000),
        (25, 2500),
        (50, 5000),
        (75, 10000),
        (90, 20000),
    ]
    for number, plot in PLOTS.items():
        assert plot.number == number


def test_storage_tiers():
    assert [(tier.limit, tier.level, tier.price) for tier in STORAGE] == [
        (25, 1, 0),
        (50, 10, 500),
        (100, 30, 2500),
        (200, 60, 10000),
    ]
    assert [tier.tier for tier in STORAGE] == [0, 1, 2, 3]


def test_extra_rooms():
    assert list(ROOMS) == [2, 3]
    assert (ROOMS[2].level, ROOMS[2].price) == (20, 1500)
    assert (ROOMS[3].level, ROOMS[3].price) == (50, 6000)


def test_cosmetics():
    assert len(COSMETICS) == 21
    kinds = [item.kind for item in COSMETICS.values()]
    assert {kind: kinds.count(kind) for kind in set(kinds)} == {"decoration": 10, "hat": 4, "top": 4, "bottom": 3}
    fence = COSMETICS["wooden_fence"]
    assert (fence.name, fence.kind, fence.level, fence.price) == ("Wooden fence", "decoration", 1, 50)
    cowboy = COSMETICS["cowboy_hat"]
    assert (cowboy.name, cowboy.kind, cowboy.level, cowboy.price) == ("Cowboy hat", "hat", 30, 800)
    overalls = COSMETICS["red_overalls"]
    assert (overalls.name, overalls.kind, overalls.level, overalls.price) == ("Red overalls", "bottom", 15, 300)
    windmill = COSMETICS["windmill"]
    assert (windmill.kind, windmill.level, windmill.price) == ("decoration", 70, 5000)
    for key, item in COSMETICS.items():
        assert item.key == key


def test_the_fifteen_achievements_keep_their_order_and_names():
    assert [(key, a.name) for key, a in ACHIEVEMENTS.items()] == [
        ("first_crop", "Grow your first crop"),
        ("every_crop", "Grow one of each crop"),
        ("free_seeds", "Get free seeds from a harvest"),
        ("exceptional_crop", "Harvest an exceptional crop"),
        ("exceptional_animal", "Raise an exceptional animal"),
        ("sell_crop", "Sell a crop"),
        ("sell_animal", "Sell an animal"),
        ("sell_10_crops", "Sell 10 crops"),
        ("sell_10_animals", "Sell 10 animals"),
        ("sell_25_crops", "Sell 25 crops"),
        ("sell_25_animals", "Sell 25 animals"),
        ("breed_5", "Breed 5 times"),
        ("breed_15", "Breed 15 times"),
        ("perfect_crop", "Raise a perfect crop"),
        ("perfect_animal", "Raise a perfect animal"),
    ]
    for key, achievement in ACHIEVEMENTS.items():
        assert achievement.key == key


def test_achievement_rewards_follow_difficulty():
    by_difficulty = {}
    for key, achievement in ACHIEVEMENTS.items():
        by_difficulty.setdefault(achievement.difficulty, []).append(key)
    assert by_difficulty["easy"] == ["first_crop", "free_seeds", "sell_crop", "sell_animal", "sell_10_crops"]
    assert by_difficulty["medium"] == [
        "exceptional_crop",
        "exceptional_animal",
        "sell_10_animals",
        "sell_25_crops",
        "sell_25_animals",
        "breed_5",
        "perfect_crop",
    ]
    assert by_difficulty["hard"] == ["every_crop", "breed_15", "perfect_animal"]
    rewards = {a.difficulty: (a.coins, a.xp) for a in ACHIEVEMENTS.values()}
    assert rewards == {"easy": (50, 25), "medium": (150, 100), "hard": (500, 400)}


def test_constants():
    assert catalog.SWITCH_FEE == 250
    assert catalog.PEN_SIZE == 6
    assert catalog.SPOTS == 9
    assert catalog.MAX_LEVEL == 100
    assert catalog.DESCRIPTION_LIMIT == 200
    assert catalog.CREDIT == "Game design by Vainne"
    assert catalog.CREDIT_URL == "https://github.com/Atuelliss"


def test_spoilage_marks_and_values():
    assert catalog.FRESH_UNTIL == 8 * HOUR
    assert catalog.DRIED_UNTIL == 24 * HOUR
    assert catalog.ROT_AFTER == 48 * HOUR
    assert catalog.DRIED_VALUE == 0.75
    assert catalog.WITHERED_VALUE == 0.5
    assert catalog.DRY_STAGE_LOSS == 0.15


def test_care_marks_and_values():
    assert catalog.CARE_WINDOW == 8 * HOUR
    assert catalog.SICKLY_AFTER == 24 * HOUR
    assert catalog.MALNOURISHED_AFTER == 72 * HOUR
    assert catalog.DEATH_AFTER == 7 * DAY
    assert catalog.HEAL_AFTER == 24 * HOUR
    assert catalog.SICKLY_VALUE == 0.75
    assert catalog.MALNOURISHED_VALUE == 0.25


def ids(entries):
    return {(entry["kind"], entry["key"]) for entry in entries}


def test_unlocks_at_lists_everything_with_that_level():
    assert ids(unlocks_at(3)) == {("crop", "tulips"), ("cosmetic", "flower_pot")}
    assert ids(unlocks_at(5)) == {("tool", "big_watering_can"), ("plot", "2")}
    assert ids(unlocks_at(8)) == {("animal", "chicken"), ("tool", "wide_hoe"), ("cosmetic", "hay_bale")}
    assert ids(unlocks_at(60)) == {("crop", "cranberries"), ("storage", "3"), ("cosmetic", "jacket")}
    assert ids(unlocks_at(20)) == {("animal", "goose"), ("room", "2")}


def test_unlocks_carry_the_display_name():
    names = {entry["key"]: entry["name"] for entry in unlocks_at(5)}
    assert names == {"big_watering_can": "Big watering can", "2": "Plot 2"}


def test_unlocks_at_a_quiet_level_is_empty():
    assert unlocks_at(2) == []
    assert unlocks_at(100) == []


def test_every_catalog_entry_unlocks_at_exactly_one_level():
    total = sum(len(unlocks_at(level)) for level in range(1, catalog.MAX_LEVEL + 1))
    expected = len(CROPS) + len(ANIMALS) + len(CANS) + len(HOES) + len(PLOTS) + len(STORAGE) + len(ROOMS)
    assert total == expected + len(COSMETICS)


def test_payload_is_json_ready():
    payload = catalog_payload()
    assert json.loads(json.dumps(payload)) == payload


def test_payload_carries_keys_names_and_seconds():
    payload = catalog_payload()
    hops = next(crop for crop in payload["crops"] if crop["key"] == "hops")
    assert hops["name"] == "Hops"
    assert hops["grow_time"] == 12 * HOUR
    assert hops["seasons"] == ["summer", "autumn"]
    assert [crop["key"] for crop in payload["crops"]] == list(CROPS)
    assert [animal["key"] for animal in payload["animals"]] == list(ANIMALS)
    assert [can["capacity"] for can in payload["cans"]] == [10, 25, 50]
    assert [hoe["name"] for hoe in payload["hoes"]] == ["Hoe", "Wide hoe", "Plow"]
    assert [plot["number"] for plot in payload["plots"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [tier["limit"] for tier in payload["storage"]] == [25, 50, 100, 200]
    assert [room["number"] for room in payload["rooms"]] == [2, 3]
    assert len(payload["cosmetics"]) == 21
    assert len(payload["achievements"]) == 15


def test_payload_constants():
    constants = catalog_payload()["constants"]
    assert constants["switch_fee"] == 250
    assert constants["pen_size"] == 6
    assert constants["spots"] == 9
    assert constants["max_level"] == 100
    assert constants["description_limit"] == 200
    assert constants["credit"] == "Game design by Vainne"
    assert constants["credit_url"] == "https://github.com/Atuelliss"
    assert constants["care_window"] == 8 * HOUR
    assert constants["rot_after"] == 48 * HOUR
