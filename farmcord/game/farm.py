"""Settling a farm, and the field actions the page sends: the hoe, seeds, the watering can, the harvest and the
animals. Each action finds what the page named, checks the plot is open and of the right kind, applies the rule from
crops.py or animals.py, and earns the achievements it reached. Actions expect the farm settled up to `now` first"""

import random

from ..catalog import SPOTS
from . import animals, crops
from .model import Animal, Farm, Plot, Refused, Spot
from .progress import check_achievements, earn

# The can tier that waters a whole row per tap
SPRINKLER = 2
NOT_YOURS = "That animal isn't on your farm."
WRONG_KIND = {"crops": "That plot isn't a crop plot", "animals": "That plot isn't a pen"}


def find_plot(farm: Farm, number: int) -> Plot:
    """Plot `number`, open or not. Only a real int names a plot: True and 1.0 would pass for 1 as a dict key"""
    plot = farm.plots.get(number) if type(number) is int else None
    if plot is None:
        raise Refused("There's no such plot")
    return plot


def open_plot(farm: Farm, number: int, kind: str | None = None) -> Plot:
    """An unlocked plot, holding `kind` ("crops" or "animals") when one is asked for"""
    plot = find_plot(farm, number)
    if not plot.unlocked:
        raise Refused("That plot is locked")
    if kind and plot.kind != kind:
        raise Refused(WRONG_KIND[kind])
    return plot


def find_spot(farm: Farm, number: int, index: int) -> tuple[Plot, Spot]:
    """A spot of an open crop plot"""
    plot = open_plot(farm, number, "crops")
    if type(index) is not int or not 0 <= index < SPOTS:
        raise Refused("There's no such spot")
    return plot, plot.spots[index]


def find_animal(farm: Farm, animal_id: str) -> Animal:
    for animal in farm.animals:
        if animal.id == animal_id:
            return animal
    raise Refused(NOT_YOURS)


def settle_crops(farm: Farm, since: float, now: float) -> list[dict]:
    events = []
    for plot in farm.plots.values():
        if plot.unlocked and plot.kind == "crops":
            for spot in plot.spots:
                events += crops.settle_spot(spot, since, now, plot.number)
    return events


def settle(farm: Farm, now: float, rng: random.Random) -> list[dict]:
    """Everything that happened since the farm was last settled: crops ripening and spoiling, then the animals'
    moments in time order, then the achievements those reached. The clock never moves back, so settling at an older
    moment changes nothing"""
    since = farm.settled_at
    events = settle_crops(farm, since, now)
    moments = animals.settle_animals(farm, since, now, rng)
    events += moments
    for event in moments:
        if event["kind"] == "grown" and event["exceptional"]:
            events += earn(farm, "exceptional_animal", event["at"])
    # Litters are counted at each birth, so the breeding goals are checked once the births are in
    events += check_achievements(farm, now)
    farm.settled_at = max(since, now)
    return events


def till(farm: Farm, plot: int, index: int, now: float, dig: bool = False) -> tuple[dict, list[dict]]:
    """A hoe tap. A living crop is dug up only when `dig` is True: the page asks the player first"""
    target, spot = find_spot(farm, plot, index)
    return {"spots": crops.till(farm, target, spot.index, now, dig is True)}, []


def plant(farm: Farm, plot: int, index: int, crop: str, now: float) -> tuple[dict, list[dict]]:
    _, spot = find_spot(farm, plot, index)
    if not isinstance(crop, str):
        raise Refused("There's no such crop")
    crops.plant(farm, spot, crop, now)
    return {}, []


def water(farm: Farm, plot: int, index: int, now: float) -> tuple[dict, list[dict]]:
    """The can on a spot. The sprinkler can waters every spot in that row that needs it"""
    target, spot = find_spot(farm, plot, index)
    if farm.can_tier == SPRINKLER:
        return {"spots": crops.water_row(farm, target, spot.index, now)}, []
    crops.water(farm, spot, now)
    return {"spots": [spot.index]}, []


def refill(farm: Farm) -> tuple[dict, list[dict]]:
    crops.refill(farm)
    return {}, []


def harvest(farm: Farm, plot: int, index: int, now: float, rng: random.Random) -> tuple[dict, list[dict]]:
    """Pick a ripe crop, earning what this harvest reached: the first crop, free seeds, an exceptional or a perfect
    crop, and one of each crop"""
    _, spot = find_spot(farm, plot, index)
    result, events = crops.harvest(farm, spot, now, rng)
    reached = {
        "first_crop": True,
        "free_seeds": result["seeds"] > 0,
        "exceptional_crop": result["exceptional"],
        "perfect_crop": result["perfect"],
    }
    for key, hit in reached.items():
        if hit:
            events += earn(farm, key, now)
    events += check_achievements(farm, now)
    return result, events


def feed(farm: Farm, animal_id: str, item: str, now: float) -> tuple[dict, list[dict]]:
    animal = find_animal(farm, animal_id)
    if not isinstance(item, str):
        raise Refused("There's no such item")
    animals.feed(farm, animal, item, now)
    return {}, []


def water_animal(farm: Farm, animal_id: str, now: float) -> tuple[dict, list[dict]]:
    animals.water_animal(farm, find_animal(farm, animal_id), now)
    return {}, []


def breed(farm: Farm, animal_id: str, now: float, rng: random.Random) -> tuple[dict, list[dict]]:
    """Tap a female to try for babies. The litter's achievements come with its birth, in a later settle"""
    return animals.breed(farm, find_animal(farm, animal_id), now, rng)


def move_baby(farm: Farm, animal_id: str, plot: int, now: float) -> tuple[dict, list[dict]]:
    pen = open_plot(farm, plot, "animals")
    animals.move_baby(farm, find_animal(farm, animal_id), pen.number, now)
    return {}, []
