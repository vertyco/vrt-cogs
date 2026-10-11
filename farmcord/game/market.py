"""The Market, the farmhouse and the plots: buying and selling, storage and extra rooms, unlocking and switching
plots, cosmetics and the free starter packet. Every FarmCoin and level check lives here, never in the page. Each
action takes values as the page sent them and refuses any it can't use"""

import math

from ..catalog import (
    ANIMALS,
    CANS,
    COSMETICS,
    CROPS,
    DESCRIPTION_LIMIT,
    HOES,
    PEN_SIZE,
    PLOTS,
    ROOMS,
    STORAGE,
    SWITCH_FEE,
)
from .animals import arrive, is_perfect, sell_price
from .farm import find_animal, find_plot, open_plot
from .model import (
    Animal,
    Decoration,
    Farm,
    Plot,
    Refused,
    add_item,
    count,
    pen_animals,
    storage_limit,
    take_item,
    untilled_spots,
)
from .progress import check_achievements, earn

KINDS = ("crops", "animals")
SEXES = ("male", "female")
SLOTS = ("hat", "top", "bottom")
TOOLS = {"can": CANS, "hoe": HOES}
# Where a decoration can stand, and how many extra farmhouse rooms the player needs for it
PLACES = {"yard": 0, "room2": 1, "room3": 2}
CROP_ITEMS = frozenset(f"crop:{key}{grade}" for key in CROPS for grade in ("", ":x"))
DISCARDABLE = CROP_ITEMS | {f"seed:{key}" for key in CROPS}
STARTER = "wildflowers"
NO_COINS = "Not enough FarmCoins"
WHOLE = "Pick a whole number from 1 up"
ALREADY = "You already have that"
IN_ORDER = "Buy the one before it first"
EXPECTING = "She's expecting. Sell her after the babies arrive."


def entry(table: dict, key: str, what: str):
    """The catalog entry the page named. Only a string can be a key: a list from the page would break the lookup"""
    if not isinstance(key, str) or key not in table:
        raise Refused(f"There's no such {what}")
    return table[key]


def check_quantity(quantity: int) -> None:
    """A count from the page: a real int (True and 2.0 don't pass) of 1 or more"""
    if type(quantity) is not int or quantity < 1:
        raise Refused(WHOLE)


def reach(farm: Farm, level: int) -> None:
    if farm.level < level:
        raise Refused(f"Unlocks at level {level}")


def pay(farm: Farm, price: int) -> None:
    if farm.coins < price:
        raise Refused(NO_COINS)
    farm.coins -= price


def stock(farm: Farm, key: str, quantity: int, price: int) -> dict:
    """Buy `quantity` of an item at `price` each, all of it fitting in storage"""
    check_quantity(quantity)
    if count(farm, key) + quantity > storage_limit(farm):
        raise Refused("Storage full")
    pay(farm, price * quantity)
    add_item(farm, key, quantity)
    return {"item": key, "quantity": quantity, "cost": price * quantity}


def buy_seeds(farm: Farm, crop: str, quantity: int) -> tuple[dict, list[dict]]:
    info = entry(CROPS, crop, "crop")
    reach(farm, info.level)
    return stock(farm, f"seed:{info.key}", quantity, info.seed_price), []


def buy_feed(farm: Farm, kind: str, quantity: int) -> tuple[dict, list[dict]]:
    """Bags of one animal kind's feed, a meal each"""
    info = entry(ANIMALS, kind, "animal")
    reach(farm, info.level)
    return stock(farm, f"feed:{info.key}", quantity, info.feed_price), []


def buy_animal(farm: Farm, kind: str, sex: str, plot: int, now: float) -> tuple[dict, list[dict]]:
    """A baby of the chosen sex, straight into an open pen with room"""
    info = entry(ANIMALS, kind, "animal")
    if sex not in SEXES:
        raise Refused("Pick male or female")
    pen = open_plot(farm, plot, "animals")
    reach(farm, info.level)
    if len(pen_animals(farm, pen.number)) >= PEN_SIZE:
        raise Refused("That pen is full")
    pay(farm, info.baby_price)
    animal = Animal(kind=info.key, sex=sex, plot=pen.number)
    arrive(animal, now)
    farm.animals.append(animal)
    return {"animal": animal.id}, []


def buy_tool(farm: Farm, tool: str, tier: int) -> tuple[dict, list[dict]]:
    """Any better can or hoe, skipping tiers if the player likes. A new can arrives full"""
    tiers = entry(TOOLS, tool, "tool")
    if type(tier) is not int or not 0 <= tier < len(tiers):
        raise Refused("There's no such tool")
    if tier <= getattr(farm, f"{tool}_tier"):
        raise Refused("You already have that or a better one")
    reach(farm, tiers[tier].level)
    pay(farm, tiers[tier].price)
    setattr(farm, f"{tool}_tier", tier)
    if tool == "can":
        farm.water = tiers[tier].capacity
    return {"tool": tool, "tier": tier}, []


def next_in_line(wanted: int, owned: int) -> None:
    """Upgrades that are bought one after another: `wanted` must come right after `owned`"""
    if wanted <= owned:
        raise Refused(ALREADY)
    if wanted > owned + 1:
        raise Refused(IN_ORDER)


def buy_storage(farm: Farm, tier: int) -> tuple[dict, list[dict]]:
    """The next storage upgrade. The page names the tier it showed, so a repeated tap can't buy two"""
    if type(tier) is not int or not 1 <= tier < len(STORAGE):
        raise Refused("There's no such upgrade")
    next_in_line(tier, farm.storage_tier)
    reach(farm, STORAGE[tier].level)
    pay(farm, STORAGE[tier].price)
    farm.storage_tier = tier
    return {"tier": tier}, []


def buy_room(farm: Farm, room: int) -> tuple[dict, list[dict]]:
    """The next extra farmhouse room. They are numbered 2 and 3 after the main room, so a farm with n extra rooms has
    room n + 1 as its last"""
    if type(room) is not int or room not in ROOMS:
        raise Refused("There's no such room")
    next_in_line(room, farm.rooms + 1)
    reach(farm, ROOMS[room].level)
    pay(farm, ROOMS[room].price)
    farm.rooms += 1
    return {"room": room}, []


def buy_cosmetic(farm: Farm, item: str) -> tuple[dict, list[dict]]:
    """A decoration (each one bought is its own, starting unplaced) or an outfit piece (owned once)"""
    info = entry(COSMETICS, item, "item")
    if info.key in farm.outfits:
        raise Refused(ALREADY)
    reach(farm, info.level)
    pay(farm, info.price)
    if info.kind != "decoration":
        farm.outfits.add(info.key)
        return {"outfit": info.key}, []
    decoration = Decoration(item=info.key)
    farm.decorations.append(decoration)
    return {"decoration": decoration.id}, []


def sell_crops(farm: Farm, item: str, quantity: int, now: float) -> tuple[dict, list[dict]]:
    """Sell from a crop stack, for that share of the stack's worth"""
    if not isinstance(item, str) or item not in CROP_ITEMS:
        raise Refused("Only crops sell at the Market")
    check_quantity(quantity)
    coins = take_item(farm, item, quantity)
    farm.coins += coins
    farm.crops_sold += quantity
    return {"item": item, "quantity": quantity, "coins": coins}, check_achievements(farm, now)


def sell_animal(farm: Farm, animal_id: str, now: float) -> tuple[dict, list[dict]]:
    """Sell a grown-up animal at its price for its condition. One that never missed care is a perfect animal"""
    animal = find_animal(farm, animal_id)
    if not animal.adult:
        raise Refused("Only grown-up animals can be sold")
    if animal.pregnant_until:
        raise Refused(EXPECTING)
    perfect = is_perfect(animal, now)
    coins = sell_price(animal)
    farm.animals.remove(animal)
    farm.coins += coins
    farm.animals_sold += 1
    events = earn(farm, "perfect_animal", now) if perfect else []
    return {"coins": coins, "perfect": perfect}, events + check_achievements(farm, now)


def check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise Refused("Pick crops or animals")


def unlock_plot(farm: Farm, plot: int, kind: str) -> tuple[dict, list[dict]]:
    """Buy a locked plot at its level and price, and pick what it holds. That first pick is free"""
    target = find_plot(farm, plot)
    if target.unlocked:
        raise Refused("That plot is already open")
    check_kind(kind)
    reach(farm, PLOTS[target.number].level)
    pay(farm, PLOTS[target.number].price)
    target.unlocked = True
    target.kind = kind
    target.spots = untilled_spots()
    return {"plot": target.number, "kind": kind}, []


def switch_fee(farm: Farm) -> int:
    """What the next paid switch costs: 250 FarmCoins, doubling with every switch the player has paid for"""
    return SWITCH_FEE * 2**farm.switches


def switch_refusal(farm: Farm, plot: Plot, kind: str) -> str | None:
    """Why the plot can't turn into `kind` now, or None when it can"""
    if kind == plot.kind:
        return "It's already a crop plot" if kind == "crops" else "It's already a pen"
    if plot.kind == "crops" and any(spot.state in ("growing", "rotted") for spot in plot.spots):
        return "Harvest or clear every spot on this plot first"
    if plot.kind == "animals" and pen_animals(farm, plot.number):
        return "Empty the pen first"
    alone = not any(other.unlocked for number, other in farm.plots.items() if number != 1)
    if plot.number == 1 and kind == "animals" and alone:
        return "Plot 1 can become a pen once you own another plot"
    return None


def switch_plot(farm: Farm, plot: int, kind: str) -> tuple[dict, list[dict]]:
    """Turn an empty open plot into a pen or back into crops. Plot 1 goes back to crops for free and uncounted, so a
    player who loses their animals always has a field"""
    target = open_plot(farm, plot)
    check_kind(kind)
    reason = switch_refusal(farm, target, kind)
    if reason:
        raise Refused(reason)
    free = target.number == 1 and kind == "crops"
    fee = 0 if free else switch_fee(farm)
    pay(farm, fee)
    if not free:
        farm.switches += 1
    target.kind = kind
    target.spots = untilled_spots()
    return {"fee": fee}, []


def discard(farm: Farm, item: str, quantity: int) -> tuple[dict, list[dict]]:
    """Throw seeds or crops away at the farmhouse. Feed can't be thrown away"""
    if not isinstance(item, str) or item not in DISCARDABLE:
        raise Refused("Only seeds and crops can be thrown away")
    check_quantity(quantity)
    take_item(farm, item, quantity)
    return {"item": item, "quantity": quantity}, []


def can_have_free_packet(farm: Farm) -> bool:
    """The safety net: fewer FarmCoins than one wildflower packet costs, no seeds, nothing growing (bushes too), no
    crops in storage and no animals in pens or waiting. Feed doesn't count"""
    stocked = any(item.quantity for key, item in farm.items.items() if key.startswith(("seed:", "crop:")))
    growing = any(spot.state == "growing" for plot in farm.plots.values() for spot in plot.spots)
    return farm.coins < CROPS[STARTER].seed_price and not stocked and not growing and not farm.animals


def free_packet(farm: Farm) -> tuple[dict, list[dict]]:
    if not can_have_free_packet(farm):
        raise Refused("The free packet is for farms with nothing left to grow or sell")
    add_item(farm, f"seed:{STARTER}", 1)
    return {"item": f"seed:{STARTER}", "quantity": 1}, []


def find_decoration(farm: Farm, decoration_id: str) -> Decoration:
    for decoration in farm.decorations:
        if decoration.id == decoration_id:
            return decoration
    raise Refused("You don't have that decoration")


def share(value: float) -> float:
    """A place in a room as a share (0 to 1) of its width or height, pulled back inside the room"""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Refused("That isn't a spot in the room")
    return min(max(float(value), 0.0), 1.0)


def place_decoration(farm: Farm, decoration_id: str, room: str, x: float, y: float) -> tuple[dict, list[dict]]:
    """Put a decoration in the yard or an owned extra room, or move it there"""
    decoration = find_decoration(farm, decoration_id)
    if not isinstance(room, str) or room not in PLACES:
        raise Refused("There's no such room")
    if farm.rooms < PLACES[room]:
        raise Refused("You don't own that room")
    decoration.x, decoration.y = share(x), share(y)
    decoration.room = room
    return {}, []


def pick_up_decoration(farm: Farm, decoration_id: str) -> tuple[dict, list[dict]]:
    decoration = find_decoration(farm, decoration_id)
    if decoration.room is None:
        raise Refused("That decoration isn't placed")
    decoration.room = None
    return {}, []


def wear(farm: Farm, slot: str, outfit: str | None) -> tuple[dict, list[dict]]:
    """Put an owned piece on in its slot, or take the slot's piece off with None"""
    if slot not in SLOTS:
        raise Refused("There's no such slot")
    if outfit is not None:
        if not isinstance(outfit, str) or outfit not in farm.outfits:
            raise Refused("You don't own that")
        if COSMETICS[outfit].kind != slot:
            raise Refused("You can't wear that there")
    setattr(farm, slot, outfit)
    return {}, []


def describe_room(farm: Farm, room: int, text: str) -> tuple[dict, list[dict]]:
    """The player's own words for an extra room they own, trimmed and cut to the length limit. Only printable
    characters and line breaks stay: a lone surrogate can't be saved, and control characters only garble the note"""
    if type(room) is not int or room not in ROOMS:
        raise Refused("There's no such room")
    if room - 1 > farm.rooms:
        raise Refused("You don't own that room")
    if not isinstance(text, str):
        raise Refused("A description is text")
    kept = "".join(char for char in text if char == "\n" or char.isprintable())
    farm.descriptions[room] = kept.strip()[:DESCRIPTION_LIMIT].rstrip()
    return {"text": farm.descriptions[room]}, []


def set_prefs(farm: Farm, sound: bool, music: bool) -> tuple[dict, list[dict]]:
    if not isinstance(sound, bool) or not isinstance(music, bool):
        raise Refused("Sound and music are either on or off")
    farm.sound, farm.music = sound, music
    return {}, []
