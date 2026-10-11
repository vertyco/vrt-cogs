import copy

import pytest

from farmcord.catalog import ANIMALS
from farmcord.game.animals import arrive
from farmcord.game.calendar import HOUR
from farmcord.game.market import (
    buy_animal,
    buy_cosmetic,
    buy_feed,
    buy_room,
    buy_seeds,
    buy_storage,
    buy_tool,
    can_have_free_packet,
    describe_room,
    discard,
    free_packet,
    pick_up_decoration,
    place_decoration,
    sell_animal,
    sell_crops,
    set_prefs,
    switch_fee,
    switch_plot,
    unlock_plot,
    wear,
)
from farmcord.game.model import Animal, Decoration, Refused, Spot, add_item, count, new_farm, untilled_spots

NOW = 1_800_000_000.0
NO_COINS = "Not enough FarmCoins"
WHOLE = "Pick a whole number from 1 up"
ALREADY = "You already have that"
IN_ORDER = "Buy the one before it first"
NOT_YOURS = "That animal isn't on your farm."
NO_PACKET = "The free packet is for farms with nothing left to grow or sell"
BAD_QUANTITIES = [0, -1, 1.5, True, "2", None]


@pytest.fixture
def farm():
    return new_farm(42, "Vert", NOW)


def open_plot(farm, number, kind="crops"):
    farm.plots[number].unlocked = True
    farm.plots[number].kind = kind


def animal(farm, kind="goat", sex="female", plot=2, grown=True):
    """An animal that arrived in a pen at NOW, grown up at full value when `grown`"""
    new = Animal(kind=kind, sex=sex, plot=plot)
    if plot is not None:
        arrive(new, NOW)
    new.adult = grown
    new.value = ANIMALS[kind].adult_price if grown else 0
    farm.animals.append(new)
    return new


def refuses(message, action, farm, *args):
    """The action is turned down with exactly `message`, and the farm is left as it was"""
    before = copy.deepcopy(farm)
    with pytest.raises(Refused) as info:
        action(farm, *args)
    assert str(info.value) == message
    assert farm == before


def achieved(events):
    return [(event["key"], event["at"]) for event in events if event["kind"] == "achievement"]


# Seeds and feed


def test_buy_seeds_pays_for_every_packet(farm):
    farm.coins = 100
    assert buy_seeds(farm, "wildflowers", 10) == ({"item": "seed:wildflowers", "quantity": 10, "cost": 30}, [])
    assert (farm.coins, count(farm, "seed:wildflowers")) == (70, 15)


def test_buy_seeds_refusals(farm):
    farm.coins = 1000
    refuses("There's no such crop", buy_seeds, farm, "cactus", 1)
    refuses("There's no such crop", buy_seeds, farm, ["wheat"], 1)
    refuses("Unlocks at level 3", buy_seeds, farm, "tulips", 1)
    for bad in BAD_QUANTITIES:
        refuses(WHOLE, buy_seeds, farm, "wildflowers", bad)
    farm.coins = 5
    refuses(NO_COINS, buy_seeds, farm, "wildflowers", 2)


def test_buying_past_storage_is_refused(farm):
    farm.coins = 1000
    # Five packets to start, so 21 more would make 26
    refuses("Storage full", buy_seeds, farm, "wildflowers", 21)
    buy_seeds(farm, "wildflowers", 20)
    assert count(farm, "seed:wildflowers") == 25
    refuses("Storage full", buy_seeds, farm, "wildflowers", 1)
    # The limit is per item: another crop's seeds still fit
    farm.level = 3
    buy_seeds(farm, "tulips", 25)
    farm.storage_tier = 1
    buy_seeds(farm, "wildflowers", 25)
    assert count(farm, "seed:wildflowers") == 50


def test_buy_feed_for_one_animal_kind(farm):
    farm.level, farm.coins = 8, 100
    assert buy_feed(farm, "chicken", 5) == ({"item": "feed:chicken", "quantity": 5, "cost": 10}, [])
    assert (farm.coins, count(farm, "feed:chicken")) == (90, 5)
    refuses("Unlocks at level 20", buy_feed, farm, "goose", 1)
    refuses("There's no such animal", buy_feed, farm, "dragon", 1)
    refuses(WHOLE, buy_feed, farm, "chicken", 0)
    refuses("Storage full", buy_feed, farm, "chicken", 21)


# Animals


def test_a_bought_baby_arrives_fed_and_watered(farm):
    open_plot(farm, 2, "animals")
    farm.level, farm.coins = 8, 100
    result, events = buy_animal(farm, "chicken", "male", 2, NOW)
    chick = farm.animals[0]
    assert (result, events) == ({"animal": chick.id}, [])
    assert (chick.kind, chick.sex, chick.plot, chick.adult) == ("chicken", "male", 2, False)
    assert (chick.arrived_at, chick.fed_at, chick.watered_at, chick.cared_since) == (NOW, NOW, NOW, NOW)
    assert farm.coins == 70


def test_buy_animal_refusals(farm):
    open_plot(farm, 2, "animals")
    farm.level, farm.coins = 8, 1000
    refuses("There's no such animal", buy_animal, farm, "dragon", "male", 2, NOW)
    refuses("There's no such animal", buy_animal, farm, None, "male", 2, NOW)
    for sex in ("other", None, ["male"]):
        refuses("Pick male or female", buy_animal, farm, "chicken", sex, 2, NOW)
    refuses("That plot isn't a pen", buy_animal, farm, "chicken", "male", 1, NOW)
    refuses("That plot is locked", buy_animal, farm, "chicken", "male", 3, NOW)
    refuses("There's no such plot", buy_animal, farm, "chicken", "male", 9, NOW)
    refuses("Unlocks at level 20", buy_animal, farm, "goose", "male", 2, NOW)
    for _ in range(6):
        animal(farm, "chicken")
    refuses("That pen is full", buy_animal, farm, "chicken", "male", 2, NOW)
    farm.animals.clear()
    farm.coins = 29
    refuses(NO_COINS, buy_animal, farm, "chicken", "male", 2, NOW)


# Tools, storage and rooms


def test_tools_go_up_only_and_the_bigger_can_arrives_full(farm):
    farm.level, farm.coins, farm.water = 15, 10_000, 3
    # Straight to the sprinkler can, skipping the big can
    assert buy_tool(farm, "can", 2) == ({"tool": "can", "tier": 2}, [])
    assert (farm.can_tier, farm.water, farm.coins) == (2, 50, 7500)
    refuses("You already have that or a better one", buy_tool, farm, "can", 1)
    refuses("You already have that or a better one", buy_tool, farm, "can", 2)
    assert buy_tool(farm, "hoe", 1) == ({"tool": "hoe", "tier": 1}, [])
    assert buy_tool(farm, "hoe", 2) == ({"tool": "hoe", "tier": 2}, [])
    assert (farm.hoe_tier, farm.coins) == (2, 3700)
    refuses("You already have that or a better one", buy_tool, farm, "hoe", 0)


def test_the_big_can_arrives_full(farm):
    farm.level, farm.coins, farm.water = 5, 400, 0
    buy_tool(farm, "can", 1)
    assert (farm.can_tier, farm.water, farm.coins) == (1, 25, 0)


def test_tool_refusals(farm):
    farm.coins = 10_000
    refuses("Unlocks at level 5", buy_tool, farm, "can", 1)
    refuses("Unlocks at level 15", buy_tool, farm, "hoe", 2)
    for tool, tier in (("spade", 1), (None, 1), ("can", 3), ("can", -1), ("can", "1"), ("hoe", True), ("hoe", 1.0)):
        refuses("There's no such tool", buy_tool, farm, tool, tier)
    farm.level, farm.coins = 8, 799
    refuses(NO_COINS, buy_tool, farm, "hoe", 1)


def test_storage_upgrades_in_order_only(farm):
    farm.level, farm.coins = 60, 20_000
    refuses(IN_ORDER, buy_storage, farm, 2)
    assert buy_storage(farm, 1) == ({"tier": 1}, [])
    assert (farm.storage_tier, farm.coins) == (1, 19_500)
    refuses(ALREADY, buy_storage, farm, 1)
    refuses(IN_ORDER, buy_storage, farm, 3)
    buy_storage(farm, 2)
    buy_storage(farm, 3)
    assert (farm.storage_tier, farm.coins) == (3, 7000)
    for bad in (0, 4, "1", True, None):
        refuses("There's no such upgrade", buy_storage, farm, bad)


def test_storage_needs_its_level_and_price(farm):
    farm.coins = 1000
    refuses("Unlocks at level 10", buy_storage, farm, 1)
    farm.level, farm.coins = 10, 499
    refuses(NO_COINS, buy_storage, farm, 1)


def test_rooms_in_order_only(farm):
    farm.level, farm.coins = 50, 10_000
    refuses(IN_ORDER, buy_room, farm, 3)
    assert buy_room(farm, 2) == ({"room": 2}, [])
    assert (farm.rooms, farm.coins) == (1, 8500)
    refuses(ALREADY, buy_room, farm, 2)
    buy_room(farm, 3)
    assert (farm.rooms, farm.coins) == (2, 2500)
    refuses(ALREADY, buy_room, farm, 3)
    for bad in (1, 4, "2", True, None):
        refuses("There's no such room", buy_room, farm, bad)


def test_rooms_need_their_level_and_price(farm):
    farm.coins = 10_000
    refuses("Unlocks at level 20", buy_room, farm, 2)
    farm.level, farm.coins = 20, 1499
    refuses(NO_COINS, buy_room, farm, 2)


# Cosmetics


def test_decorations_can_be_owned_twice_and_outfits_once(farm):
    farm.coins = 1000
    first, _ = buy_cosmetic(farm, "wooden_fence")
    second, _ = buy_cosmetic(farm, "wooden_fence")
    assert first["decoration"] != second["decoration"]
    assert [(d.id, d.item, d.room) for d in farm.decorations] == [
        (first["decoration"], "wooden_fence", None),
        (second["decoration"], "wooden_fence", None),
    ]
    assert buy_cosmetic(farm, "straw_hat") == ({"outfit": "straw_hat"}, [])
    assert farm.outfits == {"straw_hat"}
    refuses(ALREADY, buy_cosmetic, farm, "straw_hat")
    assert farm.coins == 1000 - 50 - 50 - 50


def test_cosmetic_refusals(farm):
    farm.coins = 1000
    refuses("Unlocks at level 3", buy_cosmetic, farm, "flower_pot")
    refuses("There's no such item", buy_cosmetic, farm, "crown")
    refuses("There's no such item", buy_cosmetic, farm, ["cap"])
    farm.coins = 49
    refuses(NO_COINS, buy_cosmetic, farm, "wooden_fence")
    refuses(NO_COINS, buy_cosmetic, farm, "straw_hat")


def test_wear_owned_pieces_in_their_slot(farm):
    farm.outfits = {"straw_hat", "plaid_shirt"}
    assert wear(farm, "hat", "straw_hat") == ({}, [])
    assert farm.hat == "straw_hat"
    refuses("You don't own that", wear, farm, "hat", "cap")
    refuses("You don't own that", wear, farm, "hat", ["cap"])
    refuses("You don't own that", wear, farm, "hat", "")
    refuses("You can't wear that there", wear, farm, "hat", "plaid_shirt")
    refuses("There's no such slot", wear, farm, "shoes", None)
    refuses("There's no such slot", wear, farm, ["hat"], None)
    wear(farm, "top", "plaid_shirt")
    wear(farm, "hat", None)
    assert (farm.hat, farm.top, farm.bottom) == (None, "plaid_shirt", None)


def test_place_a_decoration_with_its_spot_clamped(farm):
    fence = Decoration(item="wooden_fence")
    farm.decorations.append(fence)
    assert place_decoration(farm, fence.id, "yard", -0.5, 1.7) == ({}, [])
    assert (fence.room, fence.x, fence.y) == ("yard", 0.0, 1.0)
    place_decoration(farm, fence.id, "yard", 0.25, 1)
    assert (fence.x, fence.y) == (0.25, 1.0)


def test_placing_in_a_room_not_owned_is_refused(farm):
    fence = Decoration(item="wooden_fence")
    farm.decorations.append(fence)
    refuses("You don't own that room", place_decoration, farm, fence.id, "room2", 0.5, 0.5)
    farm.rooms = 1
    place_decoration(farm, fence.id, "room2", 0.5, 0.5)
    assert fence.room == "room2"
    refuses("You don't own that room", place_decoration, farm, fence.id, "room3", 0.5, 0.5)
    farm.rooms = 2
    place_decoration(farm, fence.id, "room3", 0.5, 0.5)
    assert fence.room == "room3"


def test_place_refusals(farm):
    fence = Decoration(item="wooden_fence")
    farm.decorations.append(fence)
    refuses("There's no such room", place_decoration, farm, fence.id, "attic", 0.5, 0.5)
    refuses("There's no such room", place_decoration, farm, fence.id, None, 0.5, 0.5)
    refuses("You don't have that decoration", place_decoration, farm, "nope", "yard", 0.5, 0.5)
    for bad in ("0.5", None, True, float("nan"), float("inf")):
        refuses("That isn't a spot in the room", place_decoration, farm, fence.id, "yard", bad, 0.5)
        refuses("That isn't a spot in the room", place_decoration, farm, fence.id, "yard", 0.5, bad)


def test_pick_up_a_decoration(farm):
    fence = Decoration(item="wooden_fence", room="yard", x=0.5, y=0.5)
    farm.decorations.append(fence)
    assert pick_up_decoration(farm, fence.id) == ({}, [])
    assert fence.room is None
    refuses("That decoration isn't placed", pick_up_decoration, farm, fence.id)
    refuses("You don't have that decoration", pick_up_decoration, farm, "nope")


def test_room_descriptions_are_trimmed_and_capped(farm):
    farm.rooms = 1
    assert describe_room(farm, 2, "  My cozy den \n") == ({"text": "My cozy den"}, [])
    assert farm.descriptions == {2: "My cozy den"}
    describe_room(farm, 2, " " + "x" * 250)
    assert farm.descriptions[2] == "x" * 200
    refuses("You don't own that room", describe_room, farm, 3, "hi")
    refuses("There's no such room", describe_room, farm, 1, "hi")
    refuses("There's no such room", describe_room, farm, "2", "hi")
    refuses("A description is text", describe_room, farm, 2, 5)


def test_room_descriptions_keep_only_printable_text_and_line_breaks(farm):
    """A lone surrogate can't be saved as text, and control characters only garble the room's note"""
    farm.rooms = 1
    assert describe_room(farm, 2, "\x00 Our\ud800 den\x07\t\n by the\x1b fire \r\n")[0] == {
        "text": "Our den\n by the fire"
    }
    # A cut that lands just after a space leaves no space hanging at the end
    describe_room(farm, 2, "x" * 199 + " tail")
    assert farm.descriptions[2] == "x" * 199


def test_sound_and_music_switches(farm):
    assert set_prefs(farm, False, True) == ({}, [])
    assert (farm.sound, farm.music) == (False, True)
    refuses("Sound and music are either on or off", set_prefs, farm, 0, True)
    refuses("Sound and music are either on or off", set_prefs, farm, True, None)


# Selling


def test_selling_crops_pays_the_stacks_share(farm):
    add_item(farm, "crop:wheat", 4, worth=72)
    assert sell_crops(farm, "crop:wheat", 1, NOW)[0] == {"item": "crop:wheat", "quantity": 1, "coins": 18}
    assert (farm.items["crop:wheat"].worth, farm.crops_sold) == (54, 1)
    add_item(farm, "crop:wheat:x", 2, worth=90)
    sell_crops(farm, "crop:wheat:x", 2, NOW)
    assert "crop:wheat:x" not in farm.items
    # Plus the first sale's achievement
    assert farm.coins == 18 + 90 + 50
    assert farm.crops_sold == 3


def test_crop_sale_refusals(farm):
    add_item(farm, "crop:wheat", 3, worth=54)
    add_item(farm, "feed:chicken", 3)
    for item in ("seed:wildflowers", "feed:chicken", "crop:cactus", "wheat", None, ["crop:wheat"]):
        refuses("Only crops sell at the Market", sell_crops, farm, item, 1, NOW)
    for bad in BAD_QUANTITIES:
        refuses(WHOLE, sell_crops, farm, "crop:wheat", bad, NOW)
    refuses("You don't have that many", sell_crops, farm, "crop:wheat", 4, NOW)
    refuses("You don't have that many", sell_crops, farm, "crop:corn", 1, NOW)


def test_crop_sales_earn_their_achievements_once_each(farm):
    add_item(farm, "crop:wildflowers", 25, worth=100)
    sales = ((1, ["sell_crop"]), (8, []), (1, ["sell_10_crops"]), (14, []), (1, ["sell_25_crops"]))
    for number, (quantity, keys) in enumerate(sales):
        t = NOW + number * HOUR
        _, events = sell_crops(farm, "crop:wildflowers", quantity, t)
        assert achieved(events) == [(key, t) for key in keys]
    add_item(farm, "crop:wildflowers", 1, worth=4)
    assert achieved(sell_crops(farm, "crop:wildflowers", 1, NOW + 9 * HOUR)[1]) == []
    assert farm.achievements == {"sell_crop": NOW, "sell_10_crops": NOW + 2 * HOUR, "sell_25_crops": NOW + 4 * HOUR}


def test_selling_an_animal(farm):
    goat = animal(farm)
    goat.missed = 1
    result, events = sell_animal(farm, goat.id, NOW + HOUR)
    assert result == {"coins": 410, "perfect": False}
    assert achieved(events) == [("sell_animal", NOW + HOUR)]
    # Plus the first sale's achievement
    assert (farm.animals, farm.coins, farm.animals_sold) == ([], 410 + 50, 1)


def test_a_sickly_or_malnourished_animal_sells_for_less(farm):
    goat = animal(farm)
    goat.sickly = True
    assert sell_animal(farm, goat.id, NOW)[0]["coins"] == 308
    cow = animal(farm, "cow")
    cow.malnourished = True
    assert sell_animal(farm, cow.id, NOW)[0]["coins"] == 154


def test_a_perfect_animal_is_earned_once(farm):
    missed = animal(farm)
    missed.missed = 1
    open_gap = animal(farm)
    perfect = animal(farm)
    later = animal(farm)
    assert achieved(sell_animal(farm, missed.id, NOW + HOUR)[1]) == [("sell_animal", NOW + HOUR)]
    # Eight hours without water is a missed window still open
    open_gap.fed_at = NOW + 7 * HOUR
    assert sell_animal(farm, open_gap.id, NOW + 8 * HOUR)[0]["perfect"] is False
    perfect.fed_at = perfect.watered_at = NOW + 7 * HOUR
    result, events = sell_animal(farm, perfect.id, NOW + 8 * HOUR)
    assert result["perfect"] is True
    assert achieved(events) == [("perfect_animal", NOW + 8 * HOUR)]
    later.fed_at = later.watered_at = NOW + 7 * HOUR
    assert achieved(sell_animal(farm, later.id, NOW + 8 * HOUR)[1]) == []


def test_animal_sales_earn_their_achievements_once_each(farm):
    herd = [animal(farm) for _ in range(26)]
    for goat in herd:
        goat.missed = 1
    earned = {}
    for number, goat in enumerate(herd, start=1):
        for key, at in achieved(sell_animal(farm, goat.id, NOW + number)[1]):
            earned[number] = earned.get(number, []) + [key]
            assert at == NOW + number
    assert earned == {1: ["sell_animal"], 10: ["sell_10_animals"], 25: ["sell_25_animals"]}


def test_animal_sale_refusals(farm):
    young = animal(farm, grown=False)
    waiting = animal(farm, plot=None, grown=False)
    mother = animal(farm)
    mother.bred, mother.pregnant_until, mother.litter = True, NOW + HOUR, 2
    refuses("Only grown-up animals can be sold", sell_animal, farm, young.id, NOW)
    refuses("Only grown-up animals can be sold", sell_animal, farm, waiting.id, NOW)
    refuses("She's expecting. Sell her after the babies arrive.", sell_animal, farm, mother.id, NOW)
    for bad in ("nope", None, 3):
        refuses(NOT_YOURS, sell_animal, farm, bad, NOW)


# Plots


def test_unlocking_a_plot_needs_its_level_and_coins(farm):
    farm.coins = 1000
    refuses("Unlocks at level 5", unlock_plot, farm, 2, "crops")
    farm.level, farm.coins = 5, 499
    refuses(NO_COINS, unlock_plot, farm, 2, "crops")
    farm.coins = 600
    assert unlock_plot(farm, 2, "animals") == ({"plot": 2, "kind": "animals"}, [])
    plot = farm.plots[2]
    assert (plot.unlocked, plot.kind, farm.coins, farm.switches) == (True, "animals", 100, 0)
    refuses("That plot is already open", unlock_plot, farm, 2, "crops")
    refuses("That plot is already open", unlock_plot, farm, 1, "crops")


def test_unlock_refusals(farm):
    farm.level, farm.coins = 100, 100_000
    for bad in (0, 8, "3", True, None):
        refuses("There's no such plot", unlock_plot, farm, bad, "crops")
    for kind in ("trees", None, ["crops"]):
        refuses("Pick crops or animals", unlock_plot, farm, 3, kind)


def test_the_switch_fee_doubles_across_plots(farm):
    for number in (2, 3, 4):
        open_plot(farm, number)
    farm.coins = 10_000
    for number, fee in ((2, 250), (3, 500), (4, 1000)):
        assert switch_fee(farm) == fee
        assert switch_plot(farm, number, "animals") == ({"fee": fee}, [])
    assert (farm.switches, farm.coins, switch_fee(farm)) == (3, 8250, 2000)
    # Switching back costs the next fee like any switch
    assert switch_plot(farm, 2, "crops") == ({"fee": 2000}, [])


def test_switching_needs_the_fee(farm):
    open_plot(farm, 2)
    farm.coins = 249
    refuses(NO_COINS, switch_plot, farm, 2, "animals")


def test_plot_one_becomes_a_pen_only_with_another_plot_and_comes_back_free(farm):
    farm.coins = 1000
    refuses("Plot 1 can become a pen once you own another plot", switch_plot, farm, 1, "animals")
    open_plot(farm, 2)
    assert switch_plot(farm, 1, "animals") == ({"fee": 250}, [])
    assert (farm.plots[1].kind, farm.switches, farm.coins) == ("animals", 1, 750)
    assert switch_plot(farm, 1, "crops") == ({"fee": 0}, [])
    assert (farm.plots[1].kind, farm.switches, farm.coins) == ("crops", 1, 750)
    assert farm.plots[1].spots == untilled_spots()


def test_plot_one_back_to_crops_is_free_even_when_broke(farm):
    open_plot(farm, 2)
    open_plot(farm, 1, "animals")
    assert switch_plot(farm, 1, "crops") == ({"fee": 0}, [])


@pytest.mark.parametrize("state", ["growing", "rotted"])
def test_a_crop_plot_with_crops_in_it_cant_switch(farm, state):
    open_plot(farm, 2)
    farm.coins = 1000
    farm.plots[2].spots[8] = Spot(8, state, "wildflowers", NOW, 600.0)
    refuses("Harvest or clear every spot on this plot first", switch_plot, farm, 2, "animals")


def test_a_switched_crop_plot_starts_untilled(farm):
    open_plot(farm, 2)
    farm.coins = 1000
    farm.plots[2].spots[0].state = "tilled"
    switch_plot(farm, 2, "animals")
    switch_plot(farm, 2, "crops")
    assert farm.plots[2].spots == untilled_spots()


def test_a_pen_with_an_animal_in_it_cant_switch(farm):
    open_plot(farm, 2, "animals")
    farm.coins = 1000
    animal(farm, grown=False)
    refuses("Empty the pen first", switch_plot, farm, 2, "crops")


def test_switch_refusals(farm):
    farm.coins = 1000
    open_plot(farm, 2, "animals")
    refuses("That plot is locked", switch_plot, farm, 3, "animals")
    refuses("There's no such plot", switch_plot, farm, 9, "animals")
    refuses("It's already a crop plot", switch_plot, farm, 1, "crops")
    refuses("It's already a pen", switch_plot, farm, 2, "animals")
    refuses("Pick crops or animals", switch_plot, farm, 2, "trees")


# The farmhouse: throwing things away


def test_discard_seeds_and_crops_but_not_feed(farm):
    assert discard(farm, "seed:wildflowers", 2) == ({"item": "seed:wildflowers", "quantity": 2}, [])
    assert count(farm, "seed:wildflowers") == 3
    add_item(farm, "crop:wheat:x", 2, worth=72)
    discard(farm, "crop:wheat:x", 2)
    assert "crop:wheat:x" not in farm.items
    add_item(farm, "feed:chicken", 3)
    for item in ("feed:chicken", "crop:cactus", None):
        refuses("Only seeds and crops can be thrown away", discard, farm, item, 1)
    refuses("You don't have that many", discard, farm, "seed:wildflowers", 4)
    for bad in BAD_QUANTITIES:
        refuses(WHOLE, discard, farm, "seed:wildflowers", bad)


# The safety net


@pytest.fixture
def broke(farm):
    """The safety net's exact state: fewer FarmCoins than a packet costs, no seeds, nothing growing, no crops in
    storage and no animals. Feed, tilled ground and rotted spots don't count"""
    farm.items.clear()
    farm.coins = 2
    add_item(farm, "feed:chicken", 3)
    farm.plots[1].spots[0].state = "tilled"
    farm.plots[1].spots[1] = Spot(1, "rotted", "wildflowers", NOW, 600.0)
    return farm


def test_the_safety_net_gives_one_packet(broke):
    assert can_have_free_packet(broke)
    assert free_packet(broke) == ({"item": "seed:wildflowers", "quantity": 1}, [])
    assert count(broke, "seed:wildflowers") == 1
    assert not can_have_free_packet(broke)
    refuses(NO_PACKET, free_packet, broke)


def growing_bush(farm):
    farm.plots[1].spots[4] = Spot(4, "growing", "blueberries", NOW, 3600.0, cycle=2)


@pytest.mark.parametrize(
    "breaks",
    [
        lambda farm: setattr(farm, "coins", 3),
        lambda farm: add_item(farm, "seed:tulips", 1),
        lambda farm: add_item(farm, "crop:wheat:x", 1, worth=36),
        growing_bush,
        lambda farm: animal(farm, grown=False),
        lambda farm: animal(farm, plot=None, grown=False),
    ],
    ids=["coins", "seeds", "crops", "growing", "pen", "waiting"],
)
def test_any_one_condition_takes_the_packet_away(broke, breaks):
    breaks(broke)
    assert not can_have_free_packet(broke)
    refuses(NO_PACKET, free_packet, broke)
