import pytest

from farmcord.game.model import (
    Animal,
    Refused,
    add_item,
    count,
    new_farm,
    pen_animals,
    storage_limit,
    take_item,
    waiting,
)

NOW = 1_800_000_000.0


@pytest.fixture
def farm():
    return new_farm(42, "Vert", NOW)


def test_new_farm_matches_the_starting_farm(farm):
    assert (farm.user_id, farm.name) == (42, "Vert")
    assert (farm.coins, farm.level, farm.xp) == (0, 1, 0)
    assert (farm.storage_tier, farm.can_tier, farm.hoe_tier) == (0, 0, 0)
    assert farm.water == 10
    assert (farm.rooms, farm.switches) == (0, 0)
    assert (farm.hat, farm.top, farm.bottom) == (None, None, None)
    assert farm.outfits == set()
    assert (farm.sound, farm.music) == (True, True)
    assert (farm.crops_sold, farm.animals_sold, farm.litters) == (0, 0, 0)
    assert farm.harvested == set()
    assert farm.settled_at == NOW
    assert farm.animals == []
    assert farm.achievements == {}
    assert farm.decorations == []
    assert farm.descriptions == {}


def test_new_farm_starts_with_five_wildflower_packets(farm):
    assert list(farm.items) == ["seed:wildflowers"]
    packets = farm.items["seed:wildflowers"]
    assert (packets.key, packets.quantity, packets.worth) == ("seed:wildflowers", 5, 0)


def test_new_farm_has_seven_plots_with_only_the_first_open(farm):
    assert list(farm.plots) == [1, 2, 3, 4, 5, 6, 7]
    assert [plot.unlocked for plot in farm.plots.values()] == [True, False, False, False, False, False, False]
    for number, plot in farm.plots.items():
        assert plot.number == number
        assert plot.kind == "crops"


def test_every_plot_has_nine_untilled_spots_in_order(farm):
    for plot in farm.plots.values():
        assert [spot.index for spot in plot.spots] == list(range(9))
        for spot in plot.spots:
            assert spot.state == "untilled"
            assert spot.crop is None
            assert (spot.planted_at, spot.stage_len, spot.watered, spot.cycle) == (0.0, 0.0, 0, 0)


def test_two_new_farms_share_nothing(farm):
    other = new_farm(43, "Other", NOW)
    farm.plots[1].spots[0].state = "tilled"
    farm.items["seed:wildflowers"].quantity = 1
    farm.harvested.add("wheat")
    assert other.plots[1].spots[0].state == "untilled"
    assert other.items["seed:wildflowers"].quantity == 5
    assert other.harvested == set()


def test_refused_carries_its_text_as_it_is():
    refusal = Refused("Storage full")
    assert isinstance(refusal, Exception)
    assert str(refusal) == "Storage full"


def test_storage_limit_follows_the_tier(farm):
    limits = []
    for tier in range(4):
        farm.storage_tier = tier
        limits.append(storage_limit(farm))
    assert limits == [25, 50, 100, 200]


def test_count_is_zero_for_an_item_not_held(farm):
    assert count(farm, "seed:wildflowers") == 5
    assert count(farm, "crop:wheat") == 0


def test_add_item_makes_a_stack_and_grows_it(farm):
    add_item(farm, "crop:tulips", 3, worth=27)
    add_item(farm, "crop:tulips", 2, worth=18)
    stack = farm.items["crop:tulips"]
    assert (stack.quantity, stack.worth) == (5, 45)
    assert count(farm, "crop:tulips") == 5


def test_add_item_allows_exactly_the_limit(farm):
    add_item(farm, "crop:wheat", 25)
    assert count(farm, "crop:wheat") == 25


def test_add_item_refuses_past_the_limit_and_changes_nothing(farm):
    add_item(farm, "crop:wheat", 24, worth=100)
    with pytest.raises(Refused, match="Storage full"):
        add_item(farm, "crop:wheat", 2, worth=10)
    assert (farm.items["crop:wheat"].quantity, farm.items["crop:wheat"].worth) == (24, 100)


def test_add_item_refuses_a_single_stack_past_the_limit_without_leaving_an_empty_one(farm):
    with pytest.raises(Refused, match="Storage full"):
        add_item(farm, "crop:wheat", 26)
    assert "crop:wheat" not in farm.items


def test_the_limit_applies_to_each_key_on_its_own(farm):
    add_item(farm, "crop:wheat", 25)
    add_item(farm, "crop:wheat:x", 25)
    add_item(farm, "feed:cow", 25)
    assert count(farm, "crop:wheat") == count(farm, "crop:wheat:x") == count(farm, "feed:cow") == 25


def test_a_bigger_storage_tier_raises_the_limit(farm):
    add_item(farm, "crop:wheat", 25)
    farm.storage_tier = 1
    add_item(farm, "crop:wheat", 25)
    assert count(farm, "crop:wheat") == 50
    with pytest.raises(Refused, match="Storage full"):
        add_item(farm, "crop:wheat", 1)


def test_take_item_takes_a_share_of_the_worth(farm):
    add_item(farm, "crop:corn", 4, worth=100)
    assert take_item(farm, "crop:corn", 1) == 25
    stack = farm.items["crop:corn"]
    assert (stack.quantity, stack.worth) == (3, 75)


def test_take_item_shares_add_back_up_to_the_stacks_worth(farm):
    add_item(farm, "crop:corn", 7, worth=100)
    shares = [take_item(farm, "crop:corn", 3), take_item(farm, "crop:corn", 3), take_item(farm, "crop:corn", 1)]
    assert shares == [42, 43, 15]
    assert sum(shares) == 100
    assert "crop:corn" not in farm.items


def test_take_item_taking_everything_returns_the_whole_worth(farm):
    add_item(farm, "crop:corn", 9, worth=101)
    assert take_item(farm, "crop:corn", 9) == 101
    assert count(farm, "crop:corn") == 0


def test_take_item_from_a_stack_without_worth_returns_zero(farm):
    assert take_item(farm, "seed:wildflowers", 2) == 0
    assert count(farm, "seed:wildflowers") == 3


def test_take_item_refuses_when_short_and_changes_nothing(farm):
    add_item(farm, "crop:corn", 2, worth=30)
    with pytest.raises(Refused):
        take_item(farm, "crop:corn", 3)
    stack = farm.items["crop:corn"]
    assert (stack.quantity, stack.worth) == (2, 30)


def test_take_item_refuses_an_item_not_held(farm):
    with pytest.raises(Refused):
        take_item(farm, "crop:pumpkin", 1)


def test_pen_animals_lists_the_animals_in_that_plot(farm):
    hen = Animal(kind="chicken", sex="female", plot=2)
    rooster = Animal(kind="chicken", sex="male", plot=2)
    goose = Animal(kind="goose", sex="female", plot=3)
    baby = Animal(kind="chicken", sex="female", plot=None)
    farm.animals = [hen, goose, baby, rooster]
    assert pen_animals(farm, 2) == [hen, rooster]
    assert pen_animals(farm, 3) == [goose]
    assert pen_animals(farm, 4) == []


def test_waiting_lists_the_babies_in_the_farmhouse(farm):
    hen = Animal(kind="chicken", sex="female", plot=2)
    baby = Animal(kind="chicken", sex="female", plot=None)
    farm.animals = [hen, baby]
    assert waiting(farm) == [baby]


def test_animals_get_their_own_ids():
    first = Animal(kind="pig", sex="male")
    second = Animal(kind="pig", sex="male")
    assert first.id != second.id
    assert len(first.id) == 32
