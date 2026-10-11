import copy
import itertools
import random
import time
import uuid

import pytest

from farmcord.catalog import ANIMALS, CROPS
from farmcord.game.animals import arrive
from farmcord.game.calendar import DAY, HOUR, date_of_day, day_number, in_season, is_rainy
from farmcord.game.farm import (
    breed,
    feed,
    harvest,
    move_baby,
    plant,
    refill,
    settle,
    till,
    water,
    water_animal,
)
from farmcord.game.market import buy_seeds, sell_crops
from farmcord.game.model import Animal, Refused, add_item, count, new_farm, pen_animals
from farmcord.game.progress import xp_for_level
from farmcord.tests.helpers import Script

NOW = 1_800_000_000.0
MINUTE = 60.0
NOT_YOURS = "That animal isn't on your farm."
# Rolls that turn down an exceptional crop and free seeds
PLAIN = (0.99, 0.99)


def dry_day(after=NOW):
    """The start of the first UTC day from `after` with no rain"""
    number = day_number(after)
    while is_rainy(date_of_day(number)):
        number += 1
    return number * DAY


@pytest.fixture
def start():
    """An hour into a dry day where wildflowers are in season, so rain never waters a test's stages"""
    t = dry_day() + HOUR
    assert in_season("wildflowers", t)
    return t


def open_pen(farm, number=2):
    farm.plots[number].unlocked = True
    farm.plots[number].kind = "animals"


@pytest.fixture
def farm(start):
    """A new farm with Plot 2 open as a pen"""
    farm = new_farm(42, "Vert", start)
    open_pen(farm)
    return farm


def sow(farm, index, crop="wildflowers", at=NOW):
    """Till a spot of Plot 1 and plant `crop` there, giving the farm the level and the seed it needs"""
    farm.level = max(farm.level, CROPS[crop].level)
    add_item(farm, f"seed:{crop}", 1)
    till(farm, 1, index, at)
    plant(farm, 1, index, crop, at)
    return farm.plots[1].spots[index]


def baby(farm, kind="goat", sex="female", plot=2, at=NOW):
    """A baby arriving in a pen at `at`, or waiting in the farmhouse when `plot` is None"""
    animal = Animal(kind=kind, sex=sex, plot=plot)
    if plot is not None:
        arrive(animal, at)
    farm.animals.append(animal)
    return animal


def adult(farm, kind="goat", sex="female", plot=2, at=NOW):
    """A grown-up animal with full value, last fed and watered at `at`"""
    animal = baby(farm, kind, sex, plot, at)
    animal.adult = True
    animal.value = ANIMALS[kind].adult_price
    return animal


def refuses(message, action, farm, *args, **kwargs):
    """The action is turned down with exactly `message`, and the farm is left as it was"""
    before = copy.deepcopy(farm)
    with pytest.raises(Refused) as info:
        action(farm, *args, **kwargs)
    assert str(info.value) == message
    assert farm == before


def achieved(events):
    return [(event["key"], event["at"]) for event in events if event["kind"] == "achievement"]


def moments(events):
    """(kind, at) of each event, leaving out the level-ups XP caused"""
    return [(event["kind"], event["at"]) for event in events if event["kind"] != "level"]


# Finding what the page named


@pytest.mark.parametrize("plot", [0, 8, -1, "1", 1.0, True, None, [1]])
def test_field_actions_refuse_plots_that_dont_exist(farm, start, plot):
    refuses("There's no such plot", till, farm, plot, 0, start)
    refuses("There's no such plot", plant, farm, plot, 0, "wildflowers", start)
    refuses("There's no such plot", water, farm, plot, 0, start)
    refuses("There's no such plot", harvest, farm, plot, 0, start, Script())


def test_field_actions_refuse_locked_plots_and_pens(farm, start):
    for action, args in (
        (till, ()),
        (plant, ("wildflowers",)),
        (water, ()),
    ):
        refuses("That plot is locked", action, farm, 3, 0, *args, start)
        refuses("That plot isn't a crop plot", action, farm, 2, 0, *args, start)
    refuses("That plot is locked", harvest, farm, 3, 0, start, Script())
    refuses("That plot isn't a crop plot", harvest, farm, 2, 0, start, Script())


@pytest.mark.parametrize("index", [-1, 9, "0", 1.0, True, None])
def test_field_actions_refuse_spots_that_dont_exist(farm, start, index):
    refuses("There's no such spot", till, farm, 1, index, start)
    refuses("There's no such spot", plant, farm, 1, index, "wildflowers", start)
    refuses("There's no such spot", water, farm, 1, index, start)
    refuses("There's no such spot", harvest, farm, 1, index, start, Script())


@pytest.mark.parametrize("bad", [None, "", 7, ["x"]])
def test_animal_actions_refuse_ids_not_on_the_farm(farm, start, bad):
    refuses(NOT_YOURS, feed, farm, bad, "feed:goat", start)
    refuses(NOT_YOURS, water_animal, farm, bad, start)
    refuses(NOT_YOURS, breed, farm, bad, start, Script())
    refuses(NOT_YOURS, move_baby, farm, bad, 2, start)


def test_another_players_animal_is_not_on_the_farm(farm, start):
    other = new_farm(7, "Someone", start)
    open_pen(other)
    stranger = adult(other, at=start)
    add_item(farm, "feed:goat", 1)
    refuses(NOT_YOURS, feed, farm, stranger.id, "feed:goat", start)
    refuses(NOT_YOURS, water_animal, farm, stranger.id, start)
    refuses(NOT_YOURS, breed, farm, stranger.id, start, Script())
    refuses(NOT_YOURS, move_baby, farm, stranger.id, 2, start)


# Field actions


def test_till_reports_the_spots_it_changed(farm, start):
    assert till(farm, 1, 4, start) == ({"spots": [4]}, [])
    assert farm.plots[1].spots[4].state == "tilled"
    farm.hoe_tier = 1
    assert till(farm, 1, 0, start) == ({"spots": [0, 1, 2]}, [])


def test_till_digs_up_a_crop_only_when_asked(farm, start):
    spot = sow(farm, 4, at=start)
    refuses("Something is growing here", till, farm, 1, 4, start)
    # Anything but a real True leaves the crop where it is
    refuses("Something is growing here", till, farm, 1, 4, start, dig="yes")
    assert till(farm, 1, 4, start, dig=True) == ({"spots": [4]}, [])
    assert spot.state == "untilled"


def test_plant_sows_a_seed(farm, start):
    till(farm, 1, 0, start)
    assert plant(farm, 1, 0, "wildflowers", start) == ({}, [])
    assert farm.plots[1].spots[0].crop == "wildflowers"
    assert count(farm, "seed:wildflowers") == 4


@pytest.mark.parametrize("crop", ["cactus", ["wheat"], None, 3])
def test_plant_refuses_crops_that_dont_exist(farm, start, crop):
    till(farm, 1, 0, start)
    refuses("There's no such crop", plant, farm, 1, 0, crop, start)


@pytest.mark.parametrize("tier", [0, 1])
def test_water_one_spot_without_the_sprinkler(farm, start, tier):
    farm.can_tier = tier
    for index in range(3):
        sow(farm, index, at=start)
    assert water(farm, 1, 1, start + MINUTE) == ({"spots": [1]}, [])
    assert farm.water == 9
    assert [spot.watered for spot in farm.plots[1].spots[:3]] == [0, 1, 0]


def test_the_sprinkler_waters_the_tapped_spots_row(farm, start):
    farm.can_tier = 2
    farm.water = 50
    for index in (3, 5, 6):
        sow(farm, index, at=start)
    # Spot 4 is bare, but tapping it still waters its row. Spot 6 is in the next row
    assert water(farm, 1, 4, start + MINUTE) == ({"spots": [3, 5]}, [])
    assert farm.water == 48
    assert farm.plots[1].spots[6].watered == 0


def test_refill_fills_the_can(farm):
    farm.water = 0
    assert refill(farm) == ({}, [])
    assert farm.water == 10


# Harvest achievements


def perfect_spot(farm, start, index=0):
    """Wildflowers with every stage watered, ripe at start + 30 minutes"""
    spot = sow(farm, index, at=start)
    for stage in range(3):
        water(farm, 1, index, start + stage * 10 * MINUTE)
    return spot


def test_a_lucky_perfect_first_harvest_earns_four_achievements_once(farm, start):
    perfect_spot(farm, start)
    ripe = start + 30 * MINUTE
    # One crop, exceptional, with 2 free seeds
    result, events = harvest(farm, 1, 0, ripe, Script(0.0, 0.0, 0.0, choices=[2]))
    assert (result["amount"], result["exceptional"], result["seeds"], result["perfect"]) == (1, True, 2, True)
    assert achieved(events) == [
        ("first_crop", ripe),
        ("free_seeds", ripe),
        ("exceptional_crop", ripe),
        ("perfect_crop", ripe),
    ]
    assert farm.achievements == {key: ripe for key in ("first_crop", "free_seeds", "exceptional_crop", "perfect_crop")}
    # 10 XP from the crop, then 25 + 25 + 100 + 100 from the achievements
    assert farm.xp == 260
    assert farm.coins == 50 + 50 + 150 + 150 + sum(10 * level for level in range(2, 5))
    # The same luck again earns nothing new
    perfect_spot(farm, start + HOUR)
    _, events = harvest(farm, 1, 0, start + 90 * MINUTE, Script(0.0, 0.0, 0.0, choices=[2]))
    assert achieved(events) == []


def test_a_plain_harvest_earns_only_the_first_crop(farm, start):
    sow(farm, 0, at=start)
    ripe = start + 30 * MINUTE
    # Unwatered, so three dry stages and not perfect
    result, events = harvest(farm, 1, 0, ripe, Script(0.0, *PLAIN))
    assert result["perfect"] is False
    assert achieved(events) == [("first_crop", ripe)]


def test_free_seeds_that_dont_fit_earn_nothing(farm, start):
    sow(farm, 0, at=start)
    add_item(farm, "seed:wildflowers", 20)
    assert count(farm, "seed:wildflowers") == 25
    result, events = harvest(farm, 1, 0, start + 30 * MINUTE, Script(0.0, 0.99, 0.0, choices=[1]))
    assert result["seeds"] == 0
    assert [key for key, _ in achieved(events)] == ["first_crop"]


def test_every_crop_comes_with_the_last_new_crop(farm, start):
    farm.harvested = set(CROPS) - {"wildflowers"}
    sow(farm, 0, at=start)
    ripe = start + 30 * MINUTE
    _, events = harvest(farm, 1, 0, ripe, Script(0.0, *PLAIN))
    assert achieved(events) == [("first_crop", ripe), ("every_crop", ripe)]
    sow(farm, 0, at=start + HOUR)
    _, events = harvest(farm, 1, 0, start + 90 * MINUTE, Script(0.0, *PLAIN))
    assert achieved(events) == []


# Animal actions


def test_feed_and_water_find_the_animal_by_id(farm, start):
    goat = baby(farm, at=start)
    add_item(farm, "feed:goat", 1)
    assert feed(farm, goat.id, "feed:goat", start + HOUR) == ({}, [])
    assert (goat.fed_at, count(farm, "feed:goat")) == (start + HOUR, 0)
    assert water_animal(farm, goat.id, start + HOUR) == ({}, [])
    assert (goat.watered_at, farm.water) == (start + HOUR, 9)


@pytest.mark.parametrize("item", [None, 5, ["feed:goat"]])
def test_feed_refuses_items_that_dont_exist(farm, start, item):
    goat = baby(farm, at=start)
    refuses("There's no such item", feed, farm, goat.id, item, start + HOUR)


def test_breed_finds_the_female_by_id(farm, start):
    female = adult(farm, at=start)
    adult(farm, sex="male", at=start)
    result, events = breed(farm, female.id, start, Script(0.0, 0.0))
    assert result == {"success": True, "due": start + HOUR}
    assert events == []


def test_move_baby_needs_an_open_pen(farm, start):
    waiting = baby(farm, plot=None)
    refuses("That plot isn't a pen", move_baby, farm, waiting.id, 1, start)
    refuses("That plot is locked", move_baby, farm, waiting.id, 3, start)
    refuses("There's no such plot", move_baby, farm, waiting.id, "2", start)
    assert move_baby(farm, waiting.id, 2, start) == ({}, [])
    assert (waiting.plot, waiting.arrived_at) == (2, start)


# Settle


def test_settle_plays_out_crops_then_animals_and_marks_the_time(farm, start):
    sow(farm, 0, at=start)
    baby(farm, at=start)
    events = settle(farm, start + 12 * HOUR, Script(0.99))
    assert moments(events) == [
        ("ripe", start + 30 * MINUTE),
        ("dried", start + 30 * MINUTE + 8 * HOUR),
        ("grown", start + 12 * HOUR),
    ]
    assert events[0] == {"kind": "ripe", "at": start + 30 * MINUTE, "plot": 1, "spot": 0, "crop": "wildflowers"}
    assert farm.settled_at == start + 12 * HOUR


def test_settle_leaves_locked_plots_and_pens_alone(farm, start):
    for number in (2, 3):
        spot = farm.plots[number].spots[0]
        spot.state, spot.crop, spot.planted_at, spot.stage_len = "growing", "wildflowers", start, 600.0
    assert settle(farm, start + 3 * DAY, Script()) == []
    assert farm.plots[3].spots[0].state == "growing"


def test_settling_twice_at_the_same_moment_adds_nothing(farm, start):
    sow(farm, 0, at=start)
    adult(farm, at=start)
    baby(farm, at=start)
    t = start + 30 * HOUR
    assert settle(farm, t, Script(0.99))
    before = copy.deepcopy(farm)
    assert settle(farm, t, Script()) == []
    assert farm == before


def test_settle_never_moves_the_clock_back(farm, start):
    sow(farm, 0, at=start)
    assert moments(settle(farm, start + HOUR, Script())) == [("ripe", start + 30 * MINUTE)]
    assert settle(farm, start, Script()) == []
    assert farm.settled_at == start + HOUR
    # The ripe moment isn't reported a second time
    assert settle(farm, start + 2 * HOUR, Script()) == []


def busy_farm(start):
    """Moments spread over ten days: crops ripening and rotting, a birth, babies growing up and levelling the farm,
    and every animal left alone until it dies"""
    farm = new_farm(42, "Vert", start)
    farm.level, farm.xp = 3, xp_for_level(3)
    open_pen(farm)
    sow(farm, 0, "wildflowers", start)
    sow(farm, 1, "tulips", start + 10 * MINUTE)
    mother = adult(farm, "chicken", "female", at=start)
    mother.bred, mother.pregnant_until, mother.litter = True, start + HOUR, 2
    adult(farm, "chicken", "male", at=start)
    baby(farm, "chicken", at=start)
    return farm


def ordered(events):
    return sorted(events, key=lambda event: (event["at"], repr(event)))


class Ids:
    """Stands in for uuid.uuid4, counting up from 1 again after each restart"""

    def __init__(self):
        self.restart()

    def restart(self):
        self.numbers = itertools.count(1)

    def __call__(self):
        return uuid.UUID(int=next(self.numbers))


@pytest.fixture
def ids(monkeypatch):
    """Animal ids from a counter, so two runs of the same farm name their newborns alike"""
    ids = Ids()
    monkeypatch.setattr(uuid, "uuid4", ids)
    return ids


# Two sex rolls at the birth, then three plain adulthoods
BUSY_ROLLS = (0.99,) * 5
BUSY_MARKS = (30 * MINUTE, HOUR, 4 * HOUR, 13 * HOUR, 2 * DAY, 10 * DAY)


@pytest.mark.parametrize(
    "end, counts",
    [
        (13 * HOUR, {"born": 1, "grown": 3, "died": 0, "rotted": 0}),
        (10 * DAY, {"born": 1, "grown": 3, "died": 5, "rotted": 2}),
    ],
)
def test_settling_in_pieces_matches_one_pass(start, ids, end, counts):
    one = busy_farm(start)
    pieces = copy.deepcopy(one)
    ids.restart()
    whole = settle(one, start + end, Script(*BUSY_ROLLS))
    ids.restart()
    rng = Script(*BUSY_ROLLS)
    parts = [event for mark in BUSY_MARKS if mark <= end for event in settle(pieces, start + mark, rng)]
    assert rng.used_up()
    assert pieces == one
    assert ordered(parts) == ordered(whole)
    kinds = [event["kind"] for event in whole]
    assert {kind: kinds.count(kind) for kind in counts} == counts
    assert "level" in kinds


def test_a_farm_left_for_sixty_days_settles_in_one_pass(start):
    farm = new_farm(42, "Vert", start)
    farm.level = 78
    open_pen(farm, 2)
    open_pen(farm, 3)
    for index, crop in enumerate(("wildflowers", "wheat", "corn", "blueberries", "pumpkin", "hops", "tulips")):
        sow(farm, index, crop, start)
    mother = adult(farm, "horse", "female", plot=2, at=start)
    mother.bred, mother.pregnant_until, mother.litter = True, start + HOUR, 3
    adult(farm, "horse", "male", plot=2, at=start)
    baby(farm, "cow", plot=2, at=start)
    for sex in ("male", "female", "male", "female", "male", "female"):
        baby(farm, "chicken", sex, plot=3, at=start)
    began = time.perf_counter()
    events = settle(farm, start + 60 * DAY, random.Random(1))
    took = time.perf_counter() - began
    assert took < 1.0
    assert farm.animals == []
    assert pen_animals(farm, 2) == [] and pen_animals(farm, 3) == []
    states = [spot.state for spot in farm.plots[1].spots]
    assert states == ["rotted"] * 7 + ["untilled"] * 2
    assert [event["kind"] for event in events].count("died") == 3 + 3 + 6
    assert farm.settled_at == start + 60 * DAY


# Achievements a settle earns


def test_an_exceptional_animal_is_earned_once_when_it_grows_up(farm, start):
    baby(farm, at=start)
    baby(farm, at=start + HOUR)
    events = settle(farm, start + 14 * HOUR, Script(0.01, 0.01))
    grown = [event for event in events if event["kind"] == "grown"]
    assert [event["exceptional"] for event in grown] == [True, True]
    assert achieved(events) == [("exceptional_animal", start + 12 * HOUR)]
    assert farm.achievements == {"exceptional_animal": start + 12 * HOUR}
    baby(farm, at=start + 14 * HOUR)
    assert achieved(settle(farm, start + 27 * HOUR, Script(0.01))) == []


def test_plain_animals_earn_nothing(farm, start):
    baby(farm, at=start)
    assert achieved(settle(farm, start + 13 * HOUR, Script(0.99))) == []


def litter_due(farm, at):
    mother = adult(farm, at=at - HOUR)
    mother.bred, mother.pregnant_until, mother.litter = True, at, 1
    return mother


def test_breeding_achievements_come_with_the_fifth_and_fifteenth_litters(farm, start):
    farm.litters = 3
    litter_due(farm, start + HOUR)
    t = start + 2 * HOUR
    assert achieved(settle(farm, t, Script(0.99))) == []
    litter_due(farm, start + 3 * HOUR)
    t = start + 4 * HOUR
    assert achieved(settle(farm, t, Script(0.99))) == [("breed_5", t)]
    farm.litters = 14
    litter_due(farm, start + 5 * HOUR)
    t = start + 6 * HOUR
    assert achieved(settle(farm, t, Script(0.99))) == [("breed_15", t)]
    assert farm.litters == 15
    litter_due(farm, start + 7 * HOUR)
    assert achieved(settle(farm, start + 8 * HOUR, Script(0.99))) == []


# A whole early game


def test_a_whole_early_game(start):
    """Till and plant five wildflowers, water every stage, harvest, sell and buy seeds again: level 2 on the way"""
    rng = random.Random(1)
    farm = new_farm(42, "Vert", start)
    assert settle(farm, start, rng) == []
    events = []
    for index in range(5):
        till(farm, 1, index, start)
        plant(farm, 1, index, "wildflowers", start)
    assert count(farm, "seed:wildflowers") == 0
    for stage in range(3):
        clock = start + stage * 10 * MINUTE + MINUTE
        events += settle(farm, clock, rng)
        # The starter can holds 10: the third stage needs a trip to the Pond
        if farm.water < 5:
            refill(farm)
        for index in range(5):
            water(farm, 1, index, clock)
    clock = start + 30 * MINUTE
    events += settle(farm, clock, rng)
    assert moments(events) == [("ripe", clock)] * 5
    for index in range(5):
        result, harvested = harvest(farm, 1, index, clock, rng)
        assert result["perfect"] is True
        events += harvested
    assert [spot.state for spot in farm.plots[1].spots[:5]] == ["untilled"] * 5
    sold = 0
    for key in [key for key in farm.items if key.startswith("crop:")]:
        result, sale = sell_crops(farm, key, farm.items[key].quantity, clock)
        sold += result["coins"]
        events += sale
    assert sold >= 5 * 4
    coins = farm.coins
    assert buy_seeds(farm, "wildflowers", 5)[0]["cost"] == 15
    assert farm.coins == coins - 15
    levels = [event for event in events if event["kind"] == "level"]
    assert levels[0] == {"kind": "level", "at": clock, "level": 2, "coins": 20, "unlocks": []}
    assert farm.level >= 2
    keys = [event["key"] for event in events if event["kind"] == "achievement"]
    assert keys[0] == "first_crop" and {"perfect_crop", "sell_crop"} <= set(keys)
    paid = sum(event["coins"] for event in events if event["kind"] in ("level", "achievement"))
    assert farm.coins == paid + sold - 15
    assert farm.settled_at == clock
