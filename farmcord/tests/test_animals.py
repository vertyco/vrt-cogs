import copy
import re

import pytest

from farmcord.catalog import ANIMALS
from farmcord.game.animals import (
    arrive,
    breed,
    condition,
    feed,
    grown_at,
    is_perfect,
    move_baby,
    open_misses,
    sell_price,
    settle_animals,
    water_animal,
)
from farmcord.game.calendar import DAY, HOUR
from farmcord.game.model import Animal, Refused, add_item, count, new_farm
from farmcord.tests.helpers import Script

NOW = 1_800_000_000.0
EMPTY_CAN = "Your watering can is empty. Refill it at the Pond."
NEEDS_NOTHING = "Babies waiting in the farmhouse need nothing until they're in a pen"
# A roll that turns down an exceptional animal
PLAIN = 0.99
NO_LUCK = "No luck this time. Try again in 2 hours."
NO_MALE = "She needs a healthy grown-up male goat in her pen"
SICKLY = "She's sickly. Nurse her back to health first"
WAIT_FIRST = "Move the babies waiting in the farmhouse into a pen first"


@pytest.fixture
def farm():
    """A new farm with plots 2 and 3 open as pens"""
    farm = new_farm(42, "Vert", NOW)
    for number in (2, 3):
        farm.plots[number].unlocked = True
        farm.plots[number].kind = "animals"
    return farm


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


def care(farm, animal, *hours):
    """Feed and water the animal at each of these hours after NOW"""
    add_item(farm, f"feed:{animal.kind}", len(hours))
    for h in hours:
        feed(farm, animal, f"feed:{animal.kind}", NOW + h * HOUR)
        water_animal(farm, animal, NOW + h * HOUR)


def moments(events):
    """(kind, at) of each animal event, leaving out the level-ups the XP caused"""
    return [(event["kind"], event["at"]) for event in events if event["kind"] != "level"]


# Arriving and care


def test_arrival_sets_every_clock(farm):
    animal = Animal(kind="cow", sex="male", plot=2)
    arrive(animal, NOW)
    assert (animal.arrived_at, animal.fed_at, animal.watered_at, animal.cared_since) == (NOW, NOW, NOW, NOW)
    assert grown_at(animal) == NOW + 16 * HOUR


def test_open_gaps_count_whole_windows(farm):
    animal = baby(farm)
    assert open_misses(animal, NOW + 8 * HOUR - 1) == 0
    # Both feed and water have gone 8 hours
    assert open_misses(animal, NOW + 8 * HOUR) == 2
    animal.fed_at = NOW + 10 * HOUR
    assert open_misses(animal, NOW + 17 * HOUR) == 2
    assert animal.missed == 0


def test_a_waiting_baby_has_no_open_gaps(farm):
    waiting = baby(farm, plot=None)
    assert open_misses(waiting, NOW + 30 * DAY) == 0


def test_feeding_closes_the_gap(farm):
    animal = baby(farm)
    add_item(farm, "feed:goat", 3)
    feed(farm, animal, "feed:goat", NOW + 7 * HOUR)
    assert (animal.fed_at, animal.missed, animal.cared_since) == (NOW + 7 * HOUR, 0, NOW)
    # 17 hours without food: two windows missed, and a new stretch of care starts
    feed(farm, animal, "feed:goat", NOW + 24 * HOUR)
    assert (animal.fed_at, animal.missed, animal.cared_since) == (NOW + 24 * HOUR, 2, NOW + 24 * HOUR)
    assert count(farm, "feed:goat") == 1
    assert animal.watered_at == NOW


@pytest.mark.parametrize("key", ["crop:wheat", "crop:corn:x", "crop:pumpkin"])
def test_feed_crops_of_either_grade_feed_any_animal(farm, key):
    animal = baby(farm, "horse")
    add_item(farm, key, 4, worth=72)
    feed(farm, animal, key, NOW + HOUR)
    assert animal.fed_at == NOW + HOUR
    assert (count(farm, key), farm.items[key].worth) == (3, 54)


def test_the_last_feed_crop_takes_the_rest_of_the_worth(farm):
    animal = baby(farm)
    add_item(farm, "crop:radishes", 1, worth=28)
    feed(farm, animal, "crop:radishes", NOW + HOUR)
    assert "crop:radishes" not in farm.items


@pytest.mark.parametrize(
    "key",
    ["feed:horse", "crop:tulips", "crop:tulips:x", "seed:wheat", "feed:dragon", "crop:wheat:y", "wheat", ""],
)
def test_feeding_what_the_animal_cant_eat_is_refused(farm, key):
    animal = baby(farm)
    if key in ("feed:horse", "crop:tulips", "seed:wheat"):
        add_item(farm, key, 1)
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match="^That isn't food for a goat$"):
        feed(farm, animal, key, NOW + HOUR)
    assert farm == before


def test_feeding_with_none_left_is_refused(farm):
    animal = baby(farm)
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match="^You don't have any left$"):
        feed(farm, animal, "feed:goat", NOW + HOUR)
    with pytest.raises(Refused, match="^You don't have any left$"):
        feed(farm, animal, "crop:wheat:x", NOW + HOUR)
    assert farm == before


def test_a_waiting_baby_needs_no_feed_or_water(farm):
    waiting = baby(farm, plot=None)
    add_item(farm, "feed:goat", 1)
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match=f"^{NEEDS_NOTHING}$"):
        feed(farm, waiting, "feed:goat", NOW)
    with pytest.raises(Refused, match=f"^{NEEDS_NOTHING}$"):
        water_animal(farm, waiting, NOW)
    assert farm == before


def test_watering_uses_the_can_and_closes_the_gap(farm):
    animal = baby(farm)
    water_animal(farm, animal, NOW + 5 * HOUR)
    assert (farm.water, animal.watered_at, animal.missed, animal.cared_since) == (9, NOW + 5 * HOUR, 0, NOW)
    water_animal(farm, animal, NOW + 13 * HOUR)
    assert (farm.water, animal.watered_at, animal.missed, animal.cared_since) == (
        8,
        NOW + 13 * HOUR,
        1,
        NOW + 13 * HOUR,
    )
    assert animal.fed_at == NOW


def test_watering_with_an_empty_can_is_refused(farm):
    animal = baby(farm)
    farm.water = 0
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match=f"^{EMPTY_CAN}$"):
        water_animal(farm, animal, NOW + HOUR)
    assert farm == before


# Condition, price and perfection


def test_condition_follows_the_marks(farm):
    animal = adult(farm)
    assert condition(animal, NOW) == "healthy"
    animal.sickly = True
    assert condition(animal, NOW) == "sickly"
    animal.malnourished = True
    assert condition(animal, NOW) == "malnourished"


def test_condition_reads_an_adults_neglect_before_a_settle(farm):
    animal = adult(farm)
    animal.fed_at = NOW + 10 * HOUR
    assert condition(animal, NOW + 24 * HOUR - 1) == "healthy"
    assert condition(animal, NOW + 24 * HOUR) == "sickly"
    assert condition(animal, NOW + 72 * HOUR) == "malnourished"


def test_babies_never_fall_ill(farm):
    young = baby(farm, "horse")
    assert condition(young, NOW + 30 * HOUR) == "healthy"


@pytest.mark.parametrize(
    "sickly, malnourished, exceptional, price",
    [
        (False, False, False, 85),
        (True, False, False, 64),
        (True, True, False, 21),
        (False, True, False, 21),
        (False, False, True, 170),
    ],
)
def test_sell_price(farm, sickly, malnourished, exceptional, price):
    # 85 x 75% = 63.75 and 85 x 25% = 21.25. An exceptional chicken's value was doubled when it grew up
    animal = adult(farm, "chicken")
    animal.sickly, animal.malnourished, animal.exceptional = sickly, malnourished, exceptional
    animal.value = 170 if exceptional else 85
    assert sell_price(animal) == price


def test_perfect_needs_no_missed_window_closed_or_open(farm):
    animal = adult(farm)
    assert is_perfect(animal, NOW + 8 * HOUR - 1)
    assert not is_perfect(animal, NOW + 8 * HOUR)
    add_item(farm, "feed:goat", 2)
    feed(farm, animal, "feed:goat", NOW + 7 * HOUR)
    water_animal(farm, animal, NOW + 7 * HOUR)
    assert is_perfect(animal, NOW + 14 * HOUR)
    # Fed and watered 9 hours later: the gaps are closed, but the windows they missed still count
    feed(farm, animal, "feed:goat", NOW + 16 * HOUR)
    water_animal(farm, animal, NOW + 16 * HOUR)
    assert (animal.missed, open_misses(animal, NOW + 17 * HOUR)) == (2, 0)
    assert not is_perfect(animal, NOW + 17 * HOUR)


# Growing up


def test_a_chicken_cant_miss_a_window_as_a_baby(farm):
    # A 4-hour baby has no whole 8-hour window to miss, so its care score is 1.0 even left alone
    young = baby(farm, "chicken")
    rng = Script(PLAIN)
    assert settle_animals(farm, NOW, NOW + 4 * HOUR - 1, Script()) == []
    events = settle_animals(farm, NOW + 4 * HOUR - 1, NOW + 4 * HOUR, rng)
    grown = {"kind": "grown", "at": NOW + 4 * HOUR, "animal": young.id, "species": "chicken", "xp": 50}
    assert events[0] == grown | {"exceptional": False}
    assert [event["kind"] for event in events[1:]] == ["level"]
    assert (young.adult, young.missed_young, young.value, young.exceptional) == (True, 0, 85, False)
    assert farm.xp == 50
    assert rng.used_up()


def test_a_horse_fed_only_at_arrival_misses_six_windows(farm):
    young = baby(farm, "horse")
    grown = NOW + 24 * HOUR
    events = settle_animals(farm, NOW, grown, Script(PLAIN))
    assert (young.missed_young, young.value, events[0]["xp"], farm.xp) == (6, 0, 0, 0)
    # A day without care also makes it sickly the moment it grows up
    assert moments(events) == [("grown", grown), ("sickly", grown)]


def test_one_missed_feed_window_on_a_horse(farm):
    young = baby(farm, "horse")
    add_item(farm, "feed:horse", 3)
    for h in (9, 16, 23):
        feed(farm, young, "feed:horse", NOW + h * HOUR)
    for h in (7, 14, 21):
        water_animal(farm, young, NOW + h * HOUR)
    events = settle_animals(farm, NOW, NOW + 24 * HOUR, Script(PLAIN))
    # Care 5/6: 1000 FarmCoins x 5/6 = 833.3, 403 XP x 5/6 = 335.8
    assert (young.missed, young.missed_young, young.value, events[0]["xp"], farm.xp) == (1, 1, 833, 336, 336)


@pytest.mark.parametrize(
    "fed, roll, exceptional",
    [(True, 0.0999, True), (True, 0.10, False), (False, 0.0499, True), (False, 0.05, False), (False, 0.07, False)],
)
def test_exceptional_odds(farm, fed, roll, exceptional):
    # A goat watered at 6 hours; unfed, its open feeding gap misses its one window, for a care score of 0.5
    young = baby(farm)
    water_animal(farm, young, NOW + 6 * HOUR)
    if fed:
        add_item(farm, "feed:goat", 1)
        feed(farm, young, "feed:goat", NOW + 6 * HOUR)
    rng = Script(roll)
    events = settle_animals(farm, NOW, NOW + 12 * HOUR, rng)
    value, xp = (410, 180) if fed else (205, 90)
    bonus = 2 if exceptional else 1
    assert (young.missed, young.missed_young) == (0, 0 if fed else 1)
    assert (young.exceptional, events[0]["exceptional"]) == (exceptional, exceptional)
    assert (young.value, events[0]["xp"]) == (value * bonus, xp * bonus)
    assert rng.used_up()


# Adults left alone


def test_an_adult_turns_sickly_at_exactly_24_hours(farm):
    animal = adult(farm)
    animal.fed_at = NOW + 6 * HOUR
    assert settle_animals(farm, NOW, NOW + 24 * HOUR - 1, Script()) == []
    events = settle_animals(farm, NOW + 24 * HOUR - 1, NOW + 24 * HOUR, Script())
    assert events == [{"kind": "sickly", "at": NOW + 24 * HOUR, "animal": animal.id, "species": "goat"}]
    assert animal.sickly
    assert condition(animal, NOW + 24 * HOUR) == "sickly"


def test_malnourished_at_72_hours_for_good(farm):
    animal = adult(farm)
    events = settle_animals(farm, NOW, NOW + 72 * HOUR, Script())
    assert moments(events) == [("sickly", NOW + 24 * HOUR), ("malnourished", NOW + 72 * HOUR)]
    # Two days of good care afterwards never bring it back
    care(farm, animal, 72, 78, 84, 90, 96, 102, 108, 114)
    assert settle_animals(farm, NOW + 72 * HOUR, NOW + 120 * HOUR, Script()) == []
    assert (animal.malnourished, animal.sickly) == (True, True)
    assert condition(animal, NOW + 120 * HOUR) == "malnourished"


def test_dead_at_7_days_and_removed(farm):
    animal = adult(farm)
    other = adult(farm, at=NOW + 6 * DAY + 12 * HOUR)
    events = settle_animals(farm, NOW, NOW + 7 * DAY - 1, Script())
    assert [event["animal"] for event in events] == [animal.id, animal.id]
    assert farm.animals == [animal, other]
    events = settle_animals(farm, NOW + 7 * DAY - 1, NOW + 7 * DAY, Script())
    assert events == [{"kind": "died", "at": NOW + 7 * DAY, "animal": animal.id, "species": "goat"}]
    assert farm.animals == [other]


def test_a_neglected_baby_grows_up_falls_ill_and_dies_in_order(farm):
    young = baby(farm, "horse")
    events = settle_animals(farm, NOW, NOW + 60 * DAY, Script(PLAIN))
    assert moments(events) == [
        ("grown", NOW + 24 * HOUR),
        ("sickly", NOW + 24 * HOUR),
        ("malnourished", NOW + 72 * HOUR),
        ("died", NOW + 7 * DAY),
    ]
    assert young not in farm.animals


# Healing


def sick_goat(farm):
    """An adult goat that turned sickly at NOW + 24 h and was left until NOW + 30 h"""
    animal = adult(farm)
    assert moments(settle_animals(farm, NOW, NOW + 30 * HOUR, Script())) == [("sickly", NOW + 24 * HOUR)]
    return animal


def test_a_sickly_animal_heals_after_24_hours_of_care(farm):
    animal = sick_goat(farm)
    # The first feeding and watering close 30-hour gaps, starting a new stretch of care
    care(farm, animal, 30, 37, 44, 51)
    assert animal.cared_since == NOW + 30 * HOUR
    assert settle_animals(farm, NOW + 30 * HOUR, NOW + 54 * HOUR - 1, Script()) == []
    events = settle_animals(farm, NOW + 54 * HOUR - 1, NOW + 54 * HOUR, Script())
    assert events == [{"kind": "healed", "at": NOW + 54 * HOUR, "animal": animal.id, "species": "goat"}]
    assert not animal.sickly
    assert condition(animal, NOW + 54 * HOUR) == "healthy"


@pytest.mark.parametrize("last, heals", [(46, True), (45, False)])
def test_healing_needs_the_open_gaps_under_8_hours(farm, last, heals):
    # Care stops at `last`: the open gaps reach 8 hours at last + 8, which must not come before NOW + 54 h
    animal = sick_goat(farm)
    care(farm, animal, 30, 36, 42, last)
    events = settle_animals(farm, NOW + 30 * HOUR, NOW + 60 * HOUR, Script())
    assert moments(events) == ([("healed", NOW + 54 * HOUR)] if heals else [])
    assert animal.sickly is not heals


def test_a_gap_that_reached_8_hours_restarts_the_24_hours(farm):
    animal = sick_goat(farm)
    care(farm, animal, 30, 36, 42, 45)
    assert settle_animals(farm, NOW + 30 * HOUR, NOW + 60 * HOUR, Script()) == []
    # Back at 60 hours, the 15-hour gaps missed windows: the stretch starts again
    care(farm, animal, 60, 67, 74, 81)
    assert animal.cared_since == NOW + 60 * HOUR
    events = settle_animals(farm, NOW + 60 * HOUR, NOW + 90 * HOUR, Script())
    assert moments(events) == [("healed", NOW + 84 * HOUR)]


def test_care_before_falling_ill_doesnt_heal_it(farm):
    # Two good days, then left alone: the old stretch of care ended with the neglect that made it ill
    animal = adult(farm)
    care(farm, animal, 7, 14, 21, 28, 35, 42)
    assert animal.cared_since == NOW
    events = settle_animals(farm, NOW, NOW + 70 * HOUR, Script())
    assert moments(events) == [("sickly", NOW + 66 * HOUR)]
    assert animal.sickly


# The settle as a whole


def test_moments_happen_in_time_order_across_the_farm(farm):
    goat = baby(farm)
    horse = adult(farm, "horse", at=NOW - 20 * HOUR)
    chicken = baby(farm, "chicken", at=NOW + HOUR)
    events = settle_animals(farm, NOW, NOW + 13 * HOUR, Script(PLAIN, PLAIN))
    assert [(event["kind"], event["animal"]) for event in events if event["kind"] != "level"] == [
        ("sickly", horse.id),
        ("grown", chicken.id),
        ("grown", goat.id),
    ]
    assert [event["at"] for event in events] == sorted(event["at"] for event in events)


def test_settling_twice_at_the_same_moment_adds_nothing(farm):
    baby(farm, "chicken")
    adult(farm)
    assert len(settle_animals(farm, NOW, NOW + 3 * DAY, Script(PLAIN))) > 0
    assert settle_animals(farm, NOW + 3 * DAY, NOW + 3 * DAY, Script()) == []


def test_a_waiting_baby_has_no_clock(farm):
    waiting = baby(farm, plot=None)
    before = copy.deepcopy(waiting)
    assert settle_animals(farm, NOW, NOW + 30 * DAY, Script()) == []
    assert waiting == before


# Breeding


@pytest.fixture
def pair(farm):
    """A grown-up female and male goat sharing pen 2"""
    return adult(farm), adult(farm, sex="male")


def refuse(farm, female, message, now=NOW + HOUR):
    """Breeding is refused with `message`, changing nothing and rolling nothing"""
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match=f"^{re.escape(message)}$"):
        breed(farm, female, now, Script())
    assert farm == before


def test_a_successful_try(farm, pair):
    female, _ = pair
    rng = Script(0.49, 0.0)
    result, events = breed(farm, female, NOW + HOUR, rng)
    assert (result, events) == ({"success": True, "due": NOW + 2 * HOUR}, [])
    assert (female.bred, female.tried_at, female.pregnant_until, female.litter) == (True, NOW + HOUR, NOW + 2 * HOUR, 1)
    assert rng.used_up()


def test_a_failed_try_then_a_success_2_hours_later(farm, pair):
    female, _ = pair
    t = NOW + HOUR
    assert breed(farm, female, t, Script(0.5)) == ({"success": False, "message": NO_LUCK}, [])
    assert (female.bred, female.tried_at, female.pregnant_until, female.litter) == (False, t, 0.0, 0)
    refuse(farm, female, "She needs a rest. Try again in 119 minutes", t + 60)
    refuse(farm, female, "She needs a rest. Try again in 1 minute", t + 2 * HOUR - 1)
    result, _ = breed(farm, female, t + 2 * HOUR, Script(0.0, 0.0))
    assert result == {"success": True, "due": t + 3 * HOUR}
    assert (female.bred, female.tried_at) == (True, t + 2 * HOUR)


@pytest.mark.parametrize("roll, size", [(0.0, 1), (0.59, 1), (0.6, 2), (0.89, 2), (0.9, 3), (0.99, 3)])
def test_litter_sizes(farm, pair, roll, size):
    female, _ = pair
    breed(farm, female, NOW + HOUR, Script(0.0, roll))
    assert female.litter == size


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("adult", False, "She's too young to have babies"),
        ("sex", "male", "Only a female can have babies"),
        ("sickly", True, SICKLY),
        # 24 hours since her last meal makes her sickly even before a settle marks it
        ("fed_at", NOW - 23 * HOUR, SICKLY),
        ("malnourished", True, "She's malnourished and can't have babies"),
        ("bred", True, "She's already had her babies"),
        ("tried_at", NOW, "She needs a rest. Try again in 60 minutes"),
    ],
)
def test_breed_refusals_for_the_female(farm, pair, field, value, message):
    female, _ = pair
    setattr(female, field, value)
    refuse(farm, female, message)


def test_a_waiting_baby_cant_breed(farm, pair):
    refuse(farm, baby(farm, plot=None), "She's too young to have babies")


def test_an_expecting_female_cant_try_again(farm, pair):
    female, _ = pair
    breed(farm, female, NOW + HOUR, Script(0.0, 0.0))
    refuse(farm, female, "She's already expecting", NOW + 90 * 60)
    settle_animals(farm, NOW + HOUR, NOW + 4 * HOUR, Script(0.5))
    refuse(farm, female, "She's already had her babies", NOW + 4 * HOUR)


@pytest.mark.parametrize("change", ["gone", "kind", "pen", "sickly", "young", "female"])
def test_breeding_needs_a_healthy_grown_up_male_of_her_kind_in_her_pen(farm, pair, change):
    female, male = pair
    if change == "gone":
        farm.animals.remove(male)
    elif change == "kind":
        male.kind = "pig"
    elif change == "pen":
        male.plot = 3
    elif change == "sickly":
        male.sickly = True
    elif change == "young":
        male.adult = False
    else:
        male.sex = "female"
    refuse(farm, female, NO_MALE)


def test_no_breeding_while_a_baby_waits(farm, pair):
    female, _ = pair
    waiting = baby(farm, plot=None)
    refuse(farm, female, WAIT_FIRST)
    move_baby(farm, waiting, 3, NOW + HOUR)
    result, _ = breed(farm, female, NOW + HOUR, Script(0.0, 0.0))
    assert result["success"]


# Births


def test_babies_arrive_an_hour_later_into_free_spots(farm, pair):
    female, _ = pair
    adult(farm)
    adult(farm)
    # Three babies due, and two free spots in the pen
    breed(farm, female, NOW + HOUR, Script(0.0, 0.95))
    due = NOW + 2 * HOUR
    assert settle_animals(farm, NOW + HOUR, due - 1, Script()) == []
    rng = Script(0.4, 0.6, 0.1)
    events = settle_animals(farm, due - 1, due, rng)
    born = {"kind": "born", "at": due, "mother": female.id, "species": "goat", "babies": 3, "waiting": 1, "xp": 18}
    assert events == [born]
    babies = farm.animals[4:]
    assert [(young.sex, young.plot, young.arrived_at, young.fed_at) for young in babies] == [
        ("male", 2, due, due),
        ("female", 2, due, due),
        ("male", None, 0.0, 0.0),
    ]
    assert all(young.kind == "goat" and not young.adult for young in babies)
    assert (female.bred, female.pregnant_until, female.litter) == (True, 0.0, 0)
    assert (farm.litters, farm.xp) == (1, 18)
    assert rng.used_up()
    # The two in the pen grow up 12 hours after they were born; the one in the farmhouse waits
    events = settle_animals(farm, due, due + 30 * DAY, Script(PLAIN, PLAIN))
    assert moments(events)[:2] == [("grown", due + 12 * HOUR), ("grown", due + 12 * HOUR)]
    assert babies[2] in farm.animals and not babies[2].adult


def test_each_litter_counts_once_and_gives_xp(farm):
    adult(farm, "horse", sex="male")
    first = adult(farm, "horse")
    second = adult(farm, "horse")
    breed(farm, first, NOW + HOUR, Script(0.0, 0.95))
    breed(farm, second, NOW + 2 * HOUR, Script(0.0, 0.0))
    events = settle_animals(farm, NOW + HOUR, NOW + 3 * HOUR, Script(0.5, 0.5, 0.5, 0.5))
    # 10% of a horse's 403 XP, per litter, and the first litter's XP reaches level 2
    assert [(event["kind"], event.get("babies"), event.get("xp")) for event in events] == [
        ("born", 3, 40),
        ("level", None, None),
        ("born", 1, 40),
    ]
    assert (farm.litters, farm.xp, farm.level) == (2, 80, 2)
    assert farm.coins == 20


@pytest.mark.parametrize("dies, waiting", [(-HOUR / 2, 0), (0.0, 0), (HOUR / 2, 1)])
def test_a_pens_room_is_counted_at_the_birth(farm, pair, dies, waiting):
    female, _ = pair
    adult(farm)
    adult(farm)
    adult(farm)
    due = NOW + 2 * HOUR
    # A sixth animal, left alone so long it dies near the birth
    doomed = adult(farm, at=due + dies - 7 * DAY)
    doomed.sickly = doomed.malnourished = True
    breed(farm, female, NOW + HOUR, Script(0.0, 0.0))
    events = settle_animals(farm, NOW + HOUR, NOW + 4 * HOUR, Script(0.1))
    order = [("died", due + dies), ("born", due)] if dies <= 0 else [("born", due), ("died", due + dies)]
    assert moments(events) == order
    assert [event["waiting"] for event in events if event["kind"] == "born"] == [waiting]


# Moving babies


def test_moving_a_waiting_baby_in_starts_its_clock(farm):
    waiting = baby(farm, plot=None)
    later = NOW + 5 * DAY
    move_baby(farm, waiting, 3, later)
    assert waiting.plot == 3
    assert (waiting.arrived_at, waiting.fed_at, waiting.watered_at, waiting.cared_since) == (later,) * 4
    events = settle_animals(farm, later, later + 12 * HOUR, Script(PLAIN))
    assert moments(events) == [("grown", later + 12 * HOUR)]


def test_moving_refusals(farm):
    young = baby(farm)
    for _ in range(6):
        adult(farm, plot=3)
    waiting = baby(farm, plot=None)
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match="^It's already in a pen$"):
        move_baby(farm, young, 2, NOW)
    with pytest.raises(Refused, match="^That pen is full$"):
        move_baby(farm, waiting, 3, NOW)
    assert farm == before
