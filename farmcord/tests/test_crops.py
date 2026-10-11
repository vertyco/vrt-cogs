import copy

import pytest

from farmcord.catalog import CROPS
from farmcord.game.calendar import DAY, EPOCH, HOUR, date_of_day, day_number, in_season, is_rainy, season_at
from farmcord.game.crops import (
    dry_stages,
    harvest,
    plant,
    refill,
    ripe_at,
    settle_spot,
    spoil_of,
    stage_of,
    stage_watered,
    till,
    value_multiplier,
    water,
    water_row,
)
from farmcord.game.model import Refused, add_item, count, new_farm
from farmcord.tests.helpers import Script

NOW = 1_800_000_000.0
MINUTE = 60.0
# Autumn gives way to winter here, and winter to spring a week later. Wildflowers grow in autumn, not in winter
AUTUMN_ENDS = EPOCH + 21 * DAY
WINTER_ENDS = EPOCH + 28 * DAY
EMPTY_CAN = "Your watering can is empty. Refill it at the Pond."
ROTTED = "It rotted. Clear it with the hoe."
# Rolls that turn down an exceptional crop and free seeds
PLAIN = (0.99, 0.99)


def dry_day(after=NOW):
    """The start of the first UTC day from `after` with no rain"""
    number = day_number(after)
    while is_rainy(date_of_day(number)):
        number += 1
    return number * DAY


def rain_arrives(after=NOW):
    """A midnight where a dry UTC day gives way to a rainy one"""
    number = day_number(after)
    while is_rainy(date_of_day(number)) or not is_rainy(date_of_day(number + 1)):
        number += 1
    return (number + 1) * DAY


def sow(farm, crop="wildflowers", at=NOW, index=0):
    """Till a spot of Plot 1 and plant `crop` there, giving the farm the level and the seed it needs"""
    farm.level = max(farm.level, CROPS[crop].level)
    add_item(farm, f"seed:{crop}", 1)
    spot = farm.plots[1].spots[index]
    spot.state = "tilled"
    plant(farm, spot, crop, at)
    return spot


@pytest.fixture
def farm():
    return new_farm(42, "Vert", NOW)


@pytest.fixture
def start():
    """An hour into a dry day, so rain never waters a test's stages"""
    return dry_day() + HOUR


@pytest.fixture
def perfect(farm, start):
    """Wildflowers in spot 0 with every stage watered by hand"""
    spot = sow(farm, at=start)
    spot.watered = 0b111
    return spot


def test_stages_and_ripe_moment_in_season():
    farm = new_farm(42, "Vert", NOW)
    t = AUTUMN_ENDS - MINUTE
    assert season_at(t) == "autumn" and in_season("wildflowers", t)
    spot = sow(farm, at=t)
    assert spot.stage_len == 10 * MINUTE
    assert spot.planted_at == t
    assert ripe_at(spot) == t + 30 * MINUTE
    marks = {0: 0, 599: 0, 600: 1, 1199: 1, 1200: 2, 1799: 2, 1800: 3, 5000: 3}
    for after, stage in marks.items():
        assert stage_of(spot, t + after) == stage
    # Winter came a minute after planting, and the speed stayed what it was
    assert season_at(t + 30 * MINUTE) == "winter"
    assert spot.stage_len == 10 * MINUTE


def test_stages_and_ripe_moment_out_of_season():
    farm = new_farm(42, "Vert", NOW)
    t = WINTER_ENDS - MINUTE
    assert season_at(t) == "winter" and not in_season("wildflowers", t)
    spot = sow(farm, at=t)
    assert spot.stage_len == 20 * MINUTE
    assert ripe_at(spot) == t + HOUR
    marks = {0: 0, 1199: 0, 1200: 1, 2399: 1, 2400: 2, 3599: 2, 3600: 3}
    for after, stage in marks.items():
        assert stage_of(spot, t + after) == stage
    # Spring came a minute after planting, and the crop still grows at half speed
    assert season_at(t + MINUTE) == "spring"
    assert ripe_at(spot) == t + HOUR


def test_plant_uses_a_seed_and_starts_growing(farm):
    spot = farm.plots[1].spots[4]
    spot.state = "tilled"
    spot.cycle = 3
    plant(farm, spot, "wildflowers", NOW)
    assert (spot.state, spot.crop, spot.planted_at, spot.watered, spot.cycle) == ("growing", "wildflowers", NOW, 0, 0)
    assert count(farm, "seed:wildflowers") == 4


def test_plant_refusals_change_nothing(farm):
    spot = farm.plots[1].spots[0]
    with pytest.raises(Refused, match="^Till this spot first$"):
        plant(farm, spot, "wildflowers", NOW)
    spot.state = "rotted"
    with pytest.raises(Refused, match="^Till this spot first$"):
        plant(farm, spot, "wildflowers", NOW)
    spot.state = "tilled"
    with pytest.raises(Refused, match="^Unlocks at level 48$"):
        plant(farm, spot, "blueberries", NOW)
    farm.level = 3
    with pytest.raises(Refused, match="^You have no Tulips seeds$"):
        plant(farm, spot, "tulips", NOW)
    with pytest.raises(Refused, match="^There's no such crop$"):
        plant(farm, spot, "cactus", NOW)
    assert spot.state == "tilled"
    assert count(farm, "seed:wildflowers") == 5
    plant(farm, spot, "wildflowers", NOW)
    with pytest.raises(Refused, match="^Something is already growing here$"):
        plant(farm, spot, "wildflowers", NOW)
    assert count(farm, "seed:wildflowers") == 4


def test_watering_each_stage(farm, start):
    spot = sow(farm, at=start)
    stage = spot.stage_len
    water(farm, spot, start)
    assert (spot.watered, farm.water) == (0b001, 9)
    water(farm, spot, start + stage)
    assert (spot.watered, farm.water) == (0b011, 8)
    water(farm, spot, start + 3 * stage - 1)
    assert (spot.watered, farm.water) == (0b111, 7)
    assert dry_stages(spot, ripe_at(spot)) == 0


def test_watering_a_watered_stage_uses_no_water(farm, start):
    spot = sow(farm, at=start)
    water(farm, spot, start + 1)
    with pytest.raises(Refused, match="^Already watered$"):
        water(farm, spot, start + spot.stage_len - 1)
    assert (spot.watered, farm.water) == (0b001, 9)


def test_watering_with_an_empty_can_is_refused(farm, start):
    spot = sow(farm, at=start)
    farm.water = 0
    with pytest.raises(Refused, match=f"^{EMPTY_CAN}$"):
        water(farm, spot, start)
    assert spot.watered == 0


def test_watering_a_ripe_or_missing_crop_is_refused(farm, start):
    spot = sow(farm, at=start)
    with pytest.raises(Refused, match="^It's ripe: harvest it$"):
        water(farm, spot, ripe_at(spot))
    with pytest.raises(Refused, match=f"^{ROTTED}$"):
        water(farm, spot, ripe_at(spot) + 48 * HOUR)
    with pytest.raises(Refused, match="^Nothing is growing here$"):
        water(farm, farm.plots[1].spots[1], start)
    assert (spot.watered, farm.water) == (0, 10)


def test_rain_waters_a_stage_that_overlaps_a_rainy_day_and_not_one_that_doesnt(farm):
    midnight = rain_arrives()
    stage = CROPS["wildflowers"].grow_time / 3 * (1 if in_season("wildflowers", midnight - HOUR) else 2)
    # Stage 0 sits wholly on the dry day, stage 1 runs over midnight and stage 2 sits on the rainy day
    spot = sow(farm, at=midnight - 1.5 * stage)
    assert spot.stage_len == stage
    assert not stage_watered(spot, 0, midnight)
    assert not stage_watered(spot, 1, midnight - 1)
    assert stage_watered(spot, 1, midnight + 1)
    assert stage_watered(spot, 2, ripe_at(spot))
    with pytest.raises(Refused, match="^Already watered$"):
        water(farm, spot, midnight + 1)
    assert farm.water == 10
    assert dry_stages(spot, ripe_at(spot)) == 1


def test_only_finished_stages_count_as_dry(farm, start):
    spot = sow(farm, at=start)
    assert dry_stages(spot, start + spot.stage_len - 1) == 0
    assert dry_stages(spot, start + spot.stage_len) == 1
    assert dry_stages(spot, ripe_at(spot)) == 3


@pytest.mark.parametrize("watered, dry, value", [(0b111, 0, 1.0), (0b101, 1, 0.85), (0, 3, 0.55)])
def test_dry_stages_take_fifteen_percent_each(farm, start, watered, dry, value):
    spot = sow(farm, at=start)
    spot.watered = watered
    assert dry_stages(spot, ripe_at(spot)) == dry
    assert value_multiplier(spot, ripe_at(spot)) == pytest.approx(value)


def test_spoilage_after_ripe(perfect):
    ripe = ripe_at(perfect)
    marks = [
        (-1, None, 1.0),
        (0, "fresh", 1.0),
        (7 * HOUR + 59 * MINUTE, "fresh", 1.0),
        (8 * HOUR, "dried", 0.75),
        (24 * HOUR - 1, "dried", 0.75),
        (24 * HOUR, "withered", 0.5),
        (48 * HOUR - 1, "withered", 0.5),
        (48 * HOUR, "rotted", 0.0),
    ]
    for after, state, value in marks:
        assert spoil_of(perfect, ripe + after) == state
        assert value_multiplier(perfect, ripe + after) == pytest.approx(value)


def test_spoil_of_an_empty_or_rotted_spot(farm):
    spot = farm.plots[1].spots[0]
    assert spoil_of(spot, NOW) is None
    spot.state = "tilled"
    assert spoil_of(spot, NOW) is None
    spot.state = "rotted"
    assert spoil_of(spot, NOW) == "rotted"


def test_withered_crop_with_one_dry_stage(perfect):
    perfect.watered = 0b110
    assert value_multiplier(perfect, ripe_at(perfect) + 24 * HOUR) == pytest.approx(0.5 * 0.85)


@pytest.mark.parametrize("roll, amount", [(0.0, 1), (0.49, 1), (0.5, 2), (0.89, 2), (0.9, 3), (0.99, 3)])
def test_harvest_amount(farm, perfect, roll, amount):
    rng = Script(roll, *PLAIN)
    result, events = harvest(farm, perfect, ripe_at(perfect), rng)
    assert result["amount"] == amount
    assert count(farm, "crop:wildflowers") == amount
    assert rng.used_up()
    assert events == []


@pytest.mark.parametrize(
    "is_perfect, roll, exceptional",
    [(True, 0.074, True), (True, 0.075, False), (False, 0.049, True), (False, 0.05, False), (False, 0.06, False)],
)
def test_exceptional_odds(farm, perfect, is_perfect, roll, exceptional):
    if not is_perfect:
        perfect.watered = 0b011
    result, _ = harvest(farm, perfect, ripe_at(perfect), Script(0.0, roll, 0.99))
    assert (result["perfect"], result["exceptional"]) == (is_perfect, exceptional)
    assert count(farm, "crop:wildflowers:x") == (1 if exceptional else 0)
    assert count(farm, "crop:wildflowers") == (0 if exceptional else 1)


def test_a_dried_crop_is_not_perfect(farm, perfect):
    result, _ = harvest(farm, perfect, ripe_at(perfect) + 8 * HOUR, Script(0.0, 0.06, 0.99))
    assert (result["perfect"], result["exceptional"]) == (False, False)


@pytest.mark.parametrize("seeds", [1, 2])
def test_free_seeds(farm, perfect, seeds):
    rng = Script(0.0, 0.99, 0.24, choices=[seeds])
    result, _ = harvest(farm, perfect, ripe_at(perfect), rng)
    assert result["seeds"] == seeds
    assert count(farm, "seed:wildflowers") == 5 + seeds
    assert rng.used_up()


def test_no_free_seeds_at_a_quarter(farm, perfect):
    rng = Script(0.0, 0.99, 0.25)
    result, _ = harvest(farm, perfect, ripe_at(perfect), rng)
    assert result["seeds"] == 0
    assert count(farm, "seed:wildflowers") == 5
    assert rng.used_up()


def test_storage_full_refuses_and_changes_nothing(farm, perfect):
    add_item(farm, "crop:wildflowers", 24, worth=96)
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match="^Storage full$"):
        harvest(farm, perfect, ripe_at(perfect), Script(0.5, *PLAIN))
    assert farm == before


@pytest.mark.parametrize("stack", ["crop:wildflowers", "crop:wildflowers:x"])
@pytest.mark.parametrize("held", [23, 25])
@pytest.mark.parametrize("rolls", [(0.0, 0.0, 0.0), (0.99, 0.99, 0.99)])
def test_a_stack_without_room_for_the_biggest_harvest_refuses_before_any_roll(farm, perfect, stack, held, rolls):
    """Refused the same whatever the rolls would be, so tapping again can't fish for an exceptional crop"""
    add_item(farm, stack, held, worth=4 * held)
    before = copy.deepcopy(farm)
    rng = Script(*rolls, choices=[2])
    with pytest.raises(Refused, match="^Storage full$"):
        harvest(farm, perfect, ripe_at(perfect), rng)
    assert farm == before
    assert (rng.rolls, rng.choices) == (list(rolls), [2])


def test_exceptional_crops_go_in_their_own_stack(farm, perfect):
    add_item(farm, "crop:wildflowers", 22, worth=88)
    result, _ = harvest(farm, perfect, ripe_at(perfect), Script(0.0, 0.0, 0.99))
    assert result["exceptional"]
    assert count(farm, "crop:wildflowers:x") == 1
    assert (farm.items["crop:wildflowers"].quantity, farm.items["crop:wildflowers"].worth) == (22, 88)


def test_free_seeds_are_capped_at_the_limit(farm, perfect):
    farm.items["seed:wildflowers"].quantity = 24
    result, _ = harvest(farm, perfect, ripe_at(perfect), Script(0.0, 0.99, 0.0, choices=[2]))
    assert result["seeds"] == 1
    assert count(farm, "seed:wildflowers") == 25


def test_free_seeds_with_no_room_are_lost(farm, perfect):
    farm.items["seed:wildflowers"].quantity = 25
    result, _ = harvest(farm, perfect, ripe_at(perfect), Script(0.0, 0.99, 0.0, choices=[2]))
    assert result["seeds"] == 0
    assert count(farm, "seed:wildflowers") == 25
    assert count(farm, "crop:wildflowers") == 1


def test_a_perfect_harvest_pays_full_worth_and_xp(farm, perfect):
    result, _ = harvest(farm, perfect, ripe_at(perfect), Script(0.5, *PLAIN))
    assert (result["crop"], result["amount"], result["worth"], result["xp"]) == ("wildflowers", 2, 8, 5)
    assert farm.items["crop:wildflowers"].worth == 8
    assert farm.xp == 5


def test_worth_and_xp_round_after_every_loss(farm, perfect):
    # 4 FarmCoins x 3 x 85% (one dry stage) x 75% (dried) = 7.65; 5 XP x 85% x 75% = 3.19
    add_item(farm, "crop:wildflowers", 2, worth=5)
    perfect.watered = 0b011
    result, _ = harvest(farm, perfect, ripe_at(perfect) + 8 * HOUR, Script(0.9, *PLAIN))
    assert (result["worth"], result["xp"]) == (8, 3)
    assert farm.items["crop:wildflowers"].quantity == 5
    assert farm.items["crop:wildflowers"].worth == 13
    assert farm.xp == 3


def test_exceptional_doubles_worth_and_xp(farm, perfect):
    # Doubled before rounding: 15.3 FarmCoins and 6.38 XP
    perfect.watered = 0b011
    result, _ = harvest(farm, perfect, ripe_at(perfect) + 8 * HOUR, Script(0.9, 0.0, 0.99))
    assert (result["exceptional"], result["worth"], result["xp"]) == (True, 15, 6)
    assert farm.items["crop:wildflowers:x"].worth == 15


def test_harvest_xp_can_level_up(farm, perfect):
    farm.xp = 24
    result, events = harvest(farm, perfect, ripe_at(perfect), Script(0.0, *PLAIN))
    assert result["xp"] == 5
    assert (farm.xp, farm.level, farm.coins) == (29, 2, 20)
    assert [(event["kind"], event["level"], event["coins"]) for event in events] == [("level", 2, 20)]


def test_a_normal_crop_leaves_its_spot_untilled(farm, perfect):
    harvest(farm, perfect, ripe_at(perfect), Script(0.0, *PLAIN))
    assert (perfect.state, perfect.crop, perfect.planted_at, perfect.stage_len) == ("untilled", None, 0.0, 0.0)
    assert (perfect.watered, perfect.cycle) == (0, 0)
    assert farm.harvested == {"wildflowers"}


def test_harvest_refusals_change_nothing_and_roll_nothing(farm, perfect):
    before = copy.deepcopy(farm)
    with pytest.raises(Refused, match="^It isn't ripe yet$"):
        harvest(farm, perfect, ripe_at(perfect) - 1, Script())
    with pytest.raises(Refused, match=f"^{ROTTED}$"):
        harvest(farm, perfect, ripe_at(perfect) + 48 * HOUR, Script())
    with pytest.raises(Refused, match="^Nothing to harvest here$"):
        harvest(farm, farm.plots[1].spots[1], ripe_at(perfect), Script())
    assert farm == before
    perfect.state = "rotted"
    with pytest.raises(Refused, match=f"^{ROTTED}$"):
        harvest(farm, perfect, ripe_at(perfect), Script())


def test_a_bush_starts_its_next_cycle_without_replanting(farm):
    t = WINTER_ENDS - MINUTE
    spot = sow(farm, "blueberries", at=t)
    assert spot.stage_len == 14 * HOUR / 3 * 2
    spot.watered = 0b111
    ripe = ripe_at(spot)
    assert season_at(ripe) == "spring"
    harvest(farm, spot, ripe, Script(0.0, *PLAIN))
    # The new cycle grows at spring's speed, since the bush is in season now
    assert (spot.state, spot.crop, spot.planted_at, spot.watered, spot.cycle) == ("growing", "blueberries", ripe, 0, 1)
    assert spot.stage_len == 14 * HOUR / 3
    assert count(farm, "seed:blueberries") == 0
    assert count(farm, "crop:blueberries") == 1
    harvest(farm, spot, ripe_at(spot), Script(0.0, *PLAIN))
    assert (spot.state, spot.cycle) == ("growing", 2)
    assert farm.harvested == {"blueberries"}


def test_a_rotted_bush_dies_and_the_hoe_clears_it(farm):
    spot = sow(farm, "blueberries", at=NOW)
    rot = ripe_at(spot) + 48 * HOUR
    settle_spot(spot, NOW, rot, 1)
    assert (spot.state, spot.crop) == ("rotted", "blueberries")
    with pytest.raises(Refused, match=f"^{ROTTED}$"):
        harvest(farm, spot, rot, Script())
    assert till(farm, farm.plots[1], 0, rot) == [0]
    assert (spot.state, spot.crop, spot.cycle) == ("untilled", None, 0)


def test_hoe_on_each_state(farm):
    plot = farm.plots[1]
    spot = plot.spots[0]
    assert till(farm, plot, 0, NOW) == [0]
    assert spot.state == "tilled"
    with pytest.raises(Refused, match="^Already tilled$"):
        till(farm, plot, 0, NOW)
    plant(farm, spot, "wildflowers", NOW)
    with pytest.raises(Refused, match="^Something is growing here$"):
        till(farm, plot, 0, NOW)
    with pytest.raises(Refused, match="^Something is growing here$"):
        till(farm, plot, 0, ripe_at(spot))
    assert spot.state == "growing"
    spot.state = "rotted"
    assert till(farm, plot, 0, NOW) == [0]
    assert (spot.state, spot.crop) == ("untilled", None)


def test_hoe_digs_up_a_growing_crop_only_when_asked(farm):
    plot = farm.plots[1]
    spot = sow(farm, at=NOW)
    spot.watered = 0b001
    assert till(farm, plot, 0, ripe_at(spot), dig=True) == [0]
    assert (spot.state, spot.crop, spot.planted_at, spot.watered) == ("untilled", None, 0.0, 0)


def test_hoe_clears_a_crop_that_rotted_before_it_was_settled(farm):
    spot = sow(farm, at=NOW)
    assert till(farm, farm.plots[1], 0, ripe_at(spot) + 48 * HOUR) == [0]
    assert (spot.state, spot.crop) == ("untilled", None)


def test_wide_hoe_works_the_tapped_row(farm):
    farm.hoe_tier = 1
    plot = farm.plots[1]
    sow(farm, at=NOW, index=5)
    plot.spots[4].state = "rotted"
    plot.spots[4].crop = "wildflowers"
    assert till(farm, plot, 3, NOW) == [3, 4]
    assert [spot.state for spot in plot.spots] == ["untilled"] * 3 + ["tilled", "untilled", "growing"] + [
        "untilled"
    ] * 3
    assert plot.spots[4].crop is None
    assert till(farm, plot, 4, NOW) == [4]
    with pytest.raises(Refused, match="^Already tilled$"):
        till(farm, plot, 3, NOW)


def test_wide_hoe_digging_touches_only_the_tapped_spot(farm):
    farm.hoe_tier = 1
    plot = farm.plots[1]
    sow(farm, at=NOW, index=0)
    sow(farm, at=NOW, index=1)
    assert till(farm, plot, 0, NOW, dig=True) == [0]
    assert [spot.state for spot in plot.spots[:3]] == ["untilled", "growing", "untilled"]


def test_plow_works_the_whole_plot(farm):
    farm.hoe_tier = 2
    plot = farm.plots[1]
    sow(farm, at=NOW, index=4)
    plot.spots[7].state = "rotted"
    plot.spots[7].crop = "wildflowers"
    plot.spots[2].state = "tilled"
    assert till(farm, plot, 8, NOW) == [0, 1, 3, 5, 6, 7, 8]
    assert [spot.state for spot in plot.spots] == ["tilled"] * 4 + ["growing"] + ["tilled"] * 2 + ["untilled", "tilled"]
    assert till(farm, plot, 0, NOW) == [7]
    with pytest.raises(Refused, match="^Already tilled$"):
        till(farm, plot, 0, NOW)


def test_sprinkler_waters_only_the_spots_that_need_it(farm, start):
    farm.can_tier, farm.water = 2, 50
    plot = farm.plots[1]
    needs = sow(farm, at=start, index=0)
    done = sow(farm, at=start, index=1)
    done.watered = 0b001
    sow(farm, at=start, index=3)
    assert water_row(farm, plot, 2, start) == [0]
    assert (needs.watered, done.watered, farm.water) == (0b001, 0b001, 49)
    assert plot.spots[3].watered == 0
    with pytest.raises(Refused, match="^Nothing in this row needs water$"):
        water_row(farm, plot, 0, start + 1)
    assert farm.water == 49


def test_sprinkler_stops_when_the_can_runs_dry(farm, start):
    farm.can_tier, farm.water = 2, 2
    plot = farm.plots[1]
    for index in (3, 4, 5):
        sow(farm, at=start, index=index)
    assert water_row(farm, plot, 4, start) == [3, 4]
    assert [spot.watered for spot in plot.spots[3:6]] == [0b001, 0b001, 0]
    assert farm.water == 0
    with pytest.raises(Refused, match=f"^{EMPTY_CAN}$"):
        water_row(farm, plot, 5, start)


@pytest.mark.parametrize("tier, capacity", [(0, 10), (1, 25), (2, 50)])
def test_refill_fills_the_can_to_its_capacity(farm, tier, capacity):
    farm.can_tier, farm.water = tier, 3
    refill(farm)
    assert farm.water == capacity


def test_settle_spot_emits_each_spoil_event_once(farm):
    spot = sow(farm, at=NOW, index=2)
    ripe = ripe_at(spot)
    first = settle_spot(spot, NOW, ripe + 10 * HOUR, 1)
    assert first == [
        {"kind": "ripe", "at": ripe, "plot": 1, "spot": 2, "crop": "wildflowers"},
        {"kind": "dried", "at": ripe + 8 * HOUR, "plot": 1, "spot": 2, "crop": "wildflowers"},
    ]
    assert spot.state == "growing"
    second = settle_spot(spot, ripe + 10 * HOUR, ripe + 50 * HOUR, 1)
    assert [(event["kind"], event["at"]) for event in second] == [
        ("withered", ripe + 24 * HOUR),
        ("rotted", ripe + 48 * HOUR),
    ]
    assert (spot.state, spot.crop) == ("rotted", "wildflowers")
    assert settle_spot(spot, ripe + 50 * HOUR, ripe + 100 * HOUR, 1) == []


def test_settle_spot_takes_a_mark_landing_on_now_once(farm):
    spot = sow(farm, at=NOW)
    ripe = ripe_at(spot)
    assert settle_spot(spot, NOW, ripe - 1, 1) == []
    assert [event["kind"] for event in settle_spot(spot, ripe - 1, ripe, 1)] == ["ripe"]
    assert settle_spot(spot, ripe, ripe + 1, 1) == []
    assert [event["kind"] for event in settle_spot(spot, ripe + 1, ripe + 48 * HOUR, 1)] == [
        "dried",
        "withered",
        "rotted",
    ]
    assert spot.state == "rotted"


def test_settle_spot_ignores_spots_with_nothing_growing(farm):
    spot = farm.plots[1].spots[0]
    assert settle_spot(spot, NOW, NOW + 100 * DAY, 1) == []
    spot.state = "rotted"
    assert settle_spot(spot, NOW, NOW + 100 * DAY, 1) == []
