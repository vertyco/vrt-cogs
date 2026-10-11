import pytest

from farmcord.catalog import ACHIEVEMENTS, CROPS, MAX_LEVEL, unlocks_at
from farmcord.game.model import new_farm
from farmcord.game.progress import check_achievements, earn, gain_xp, level_for_xp, xp_for_level

NOW = 1_800_000_000.0


@pytest.fixture
def farm():
    return new_farm(1, "Vert", NOW)


def test_xp_for_level_matches_the_tuned_table():
    table = {2: 29, 5: 268, 10: 1260, 15: 3086, 25: 9510, 50: 43726, 75: 106707, 90: 159368, 100: 200943}
    for level, xp in table.items():
        assert xp_for_level(level) == xp


def test_level_one_costs_nothing_and_the_curve_only_climbs():
    assert xp_for_level(1) == 0
    totals = [xp_for_level(level) for level in range(1, MAX_LEVEL + 1)]
    assert totals == sorted(set(totals))


def test_level_for_xp_at_the_edges():
    assert level_for_xp(0) == 1
    assert level_for_xp(28) == 1
    assert level_for_xp(29) == 2
    assert level_for_xp(267) == 4
    assert level_for_xp(268) == 5
    assert level_for_xp(200942) == 99
    assert level_for_xp(200943) == 100


def test_level_for_xp_is_capped_at_the_top():
    assert level_for_xp(200944) == 100
    assert level_for_xp(10**9) == 100


def test_level_for_xp_agrees_with_xp_for_level_on_every_level():
    for level in range(2, MAX_LEVEL + 1):
        assert level_for_xp(xp_for_level(level)) == level
        assert level_for_xp(xp_for_level(level) - 1) == level - 1


def test_gain_xp_below_the_next_level_only_adds_xp(farm):
    assert gain_xp(farm, 21, NOW) == []
    assert (farm.xp, farm.level, farm.coins) == (21, 1, 0)


def test_gain_xp_pays_a_level_up_and_reports_it(farm):
    events = gain_xp(farm, 29, NOW)
    assert events == [{"kind": "level", "at": NOW, "level": 2, "coins": 20, "unlocks": unlocks_at(2)}]
    assert (farm.xp, farm.level, farm.coins) == (29, 2, 20)


def test_gain_xp_across_several_levels_pays_each_one(farm):
    events = gain_xp(farm, 268, NOW)
    assert [event["level"] for event in events] == [2, 3, 4, 5]
    assert [event["coins"] for event in events] == [20, 30, 40, 50]
    assert farm.level == 5
    assert farm.coins == 140
    assert farm.xp == 268


def test_gain_xp_lists_what_each_level_unlocks(farm):
    events = {event["level"]: event for event in gain_xp(farm, 268, NOW)}
    assert {entry["key"] for entry in events[3]["unlocks"]} == {"tulips", "flower_pot"}
    assert {entry["key"] for entry in events[5]["unlocks"]} == {"big_watering_can", "2"}
    assert events[2]["unlocks"] == []
    assert all(event["at"] == NOW for event in events.values())


def test_gain_xp_continues_from_where_the_farm_stands(farm):
    gain_xp(farm, 29, NOW)
    events = gain_xp(farm, 132, NOW + 5)
    assert [event["level"] for event in events] == [3, 4]
    assert farm.coins == 20 + 30 + 40


def test_gain_xp_stops_paying_at_the_top_level(farm):
    events = gain_xp(farm, 10**7, NOW)
    assert farm.level == MAX_LEVEL
    assert len(events) == MAX_LEVEL - 1
    assert farm.coins == sum(10 * level for level in range(2, MAX_LEVEL + 1))
    assert gain_xp(farm, 1000, NOW) == []
    assert farm.level == MAX_LEVEL


def test_gain_xp_of_nothing_changes_nothing(farm):
    assert gain_xp(farm, 0, NOW) == []
    assert (farm.xp, farm.level, farm.coins) == (0, 1, 0)


def test_earn_pays_coins_and_xp_and_records_the_moment(farm):
    events = earn(farm, "free_seeds", NOW)
    assert events[0] == {"kind": "achievement", "at": NOW, "key": "free_seeds", "coins": 50, "xp": 25}
    assert farm.achievements == {"free_seeds": NOW}
    assert farm.coins == 50
    assert farm.xp == 25
    assert [event["kind"] for event in events] == ["achievement"]


def test_earn_xp_can_level_the_player_up(farm):
    events = earn(farm, "breed_15", NOW)
    assert events[0]["coins"] == 500
    assert events[0]["xp"] == 400
    levels = [event["level"] for event in events[1:]]
    assert levels[0] == 2
    assert levels[-1] == farm.level == level_for_xp(400)


def test_earn_pays_once_only(farm):
    earn(farm, "first_crop", NOW)
    snapshot = (farm.coins, farm.xp, farm.level, dict(farm.achievements))
    assert earn(farm, "first_crop", NOW + 100) == []
    assert (farm.coins, farm.xp, farm.level, farm.achievements) == snapshot


def test_earn_refuses_an_unknown_key(farm):
    with pytest.raises(KeyError):
        earn(farm, "dance_party", NOW)


def earned_keys(events):
    return [event["key"] for event in events if event["kind"] == "achievement"]


def test_check_achievements_with_nothing_done_earns_nothing(farm):
    assert check_achievements(farm, NOW) == []
    assert farm.achievements == {}


def test_check_achievements_for_the_first_sales(farm):
    farm.crops_sold = 1
    farm.animals_sold = 1
    assert earned_keys(check_achievements(farm, NOW)) == ["sell_crop", "sell_animal"]


def test_check_achievements_for_ten_and_twenty_five_sales(farm):
    farm.crops_sold = 10
    assert earned_keys(check_achievements(farm, NOW)) == ["sell_crop", "sell_10_crops"]
    farm.crops_sold = 25
    farm.animals_sold = 25
    assert earned_keys(check_achievements(farm, NOW)) == [
        "sell_animal",
        "sell_10_animals",
        "sell_25_crops",
        "sell_25_animals",
    ]


def test_check_achievements_for_litters(farm):
    farm.litters = 4
    assert check_achievements(farm, NOW) == []
    farm.litters = 5
    assert earned_keys(check_achievements(farm, NOW)) == ["breed_5"]
    farm.litters = 15
    assert earned_keys(check_achievements(farm, NOW)) == ["breed_15"]


def test_check_achievements_for_every_crop(farm):
    farm.harvested = set(CROPS) - {"pumpkin"}
    assert check_achievements(farm, NOW) == []
    farm.harvested = set(CROPS)
    assert earned_keys(check_achievements(farm, NOW)) == ["every_crop"]


def test_check_achievements_leaves_the_event_based_ones_alone(farm):
    farm.crops_sold = 100
    farm.animals_sold = 100
    farm.litters = 100
    farm.harvested = set(CROPS)
    check_achievements(farm, NOW)
    event_based = {
        "first_crop",
        "free_seeds",
        "exceptional_crop",
        "exceptional_animal",
        "perfect_crop",
        "perfect_animal",
    }
    assert not event_based & set(farm.achievements)
    assert set(farm.achievements) == set(ACHIEVEMENTS) - event_based


def test_check_achievements_does_not_pay_twice(farm):
    farm.crops_sold = 25
    check_achievements(farm, NOW)
    coins = farm.coins
    assert check_achievements(farm, NOW + 60) == []
    assert farm.coins == coins


def test_check_achievements_returns_the_level_ups_the_rewards_cause(farm):
    farm.litters = 15
    events = check_achievements(farm, NOW)
    kinds = [event["kind"] for event in events]
    assert kinds.count("achievement") == 2
    assert "level" in kinds
