"""One crop spot's rules: planting, the three growth stages, watering and rain, spoiling, the harvest and the hoe.
Each function works on the spot (or plot) it is handed; the caller checks the plot is open and holds crops"""

import random

from ..catalog import CANS, CROPS, DRIED_UNTIL, DRIED_VALUE, DRY_STAGE_LOSS, FRESH_UNTIL, ROT_AFTER, WITHERED_VALUE
from .calendar import in_season, rained_between
from .model import Farm, Plot, Refused, Spot, add_item, count, storage_limit, take_item
from .progress import gain_xp

STAGES = 3
# Spots per row: a plot's rows are 0-2, 3-5 and 6-8
ROW = 3
EXCEPTIONAL_ODDS = 0.05
PERFECT_EXCEPTIONAL_ODDS = 0.075
FREE_SEED_ODDS = 0.25
# The most one harvest gives
BIGGEST_HARVEST = 3
# When each spoil state starts, counted from the moment the crop ripens
SPOIL_MARKS = (("fresh", 0.0), ("dried", FRESH_UNTIL), ("withered", DRIED_UNTIL), ("rotted", ROT_AFTER))
# What each spoil state leaves of a harvest's worth. Nothing has spoiled before the crop ripens
SPOIL_VALUES = {None: 1.0, "fresh": 1.0, "dried": DRIED_VALUE, "withered": WITHERED_VALUE, "rotted": 0.0}
EMPTY_CAN = "Your watering can is empty. Refill it at the Pond."
ROTTED = "It rotted. Clear it with the hoe."


def stage_start(spot: Spot, k: int) -> float:
    """When stage k begins. Stage 3 beginning is the crop ripening"""
    return spot.planted_at + k * spot.stage_len


def ripe_at(spot: Spot) -> float:
    return stage_start(spot, STAGES)


def stage_of(spot: Spot, now: float) -> int:
    """The growth stage `now` falls in (0, 1 or 2), or 3 once ripe"""
    return sum(now >= stage_start(spot, k) for k in range(1, STAGES + 1))


def stage_watered(spot: Spot, k: int, now: float) -> bool:
    """Whether stage k counts as watered by `now`: watered by hand, or rain fell on the part of it already over"""
    if spot.watered & (1 << k):
        return True
    return rained_between(stage_start(spot, k), min(stage_start(spot, k + 1), now))


def dry_stages(spot: Spot, now: float) -> int:
    """How many stages have ended without water"""
    return sum(stage_start(spot, k + 1) <= now and not stage_watered(spot, k, now) for k in range(STAGES))


def spoil_of(spot: Spot, now: float) -> str | None:
    """ "fresh", "dried", "withered" or "rotted" once the crop is ripe, None before then or with nothing growing"""
    if spot.state == "rotted":
        return "rotted"
    if spot.state != "growing":
        return None
    spoil = None
    for state, after in SPOIL_MARKS:
        if now >= ripe_at(spot) + after:
            spoil = state
    return spoil


def value_multiplier(spot: Spot, now: float) -> float:
    """The share of a harvest's FarmCoins and XP left after dry stages and spoiling"""
    return (1 - DRY_STAGE_LOSS * dry_stages(spot, now)) * SPOIL_VALUES[spoil_of(spot, now)]


def start_cycle(spot: Spot, now: float) -> None:
    """Begin the three stages at `now`. Out of season every stage takes twice as long, for the whole cycle"""
    crop = CROPS[spot.crop]
    spot.stage_len = crop.grow_time / STAGES * (1 if in_season(crop.key, now) else 2)
    spot.planted_at = now
    spot.watered = 0


def clear(spot: Spot) -> None:
    """Back to bare, untilled ground"""
    spot.state = "untilled"
    spot.crop = None
    spot.planted_at = 0.0
    spot.stage_len = 0.0
    spot.watered = 0
    spot.cycle = 0


def plant(farm: Farm, spot: Spot, crop_key: str, now: float) -> None:
    """Sow one seed packet in a tilled spot"""
    crop = CROPS.get(crop_key)
    if crop is None:
        raise Refused("There's no such crop")
    if spot.state == "growing":
        raise Refused("Something is already growing here")
    if spot.state != "tilled":
        raise Refused("Till this spot first")
    if crop.level > farm.level:
        raise Refused(f"Unlocks at level {crop.level}")
    if count(farm, f"seed:{crop.key}") < 1:
        raise Refused(f"You have no {crop.name} seeds")
    take_item(farm, f"seed:{crop.key}", 1)
    spot.state = "growing"
    spot.crop = crop.key
    spot.cycle = 0
    start_cycle(spot, now)


def water_refusal(spot: Spot, now: float) -> str | None:
    """Why the spot can't take water now, or None when its current stage still needs it"""
    if spoil_of(spot, now) == "rotted":
        return ROTTED
    if spot.state != "growing":
        return "Nothing is growing here"
    if now >= ripe_at(spot):
        return "It's ripe: harvest it"
    if stage_watered(spot, stage_of(spot, now), now):
        return "Already watered"
    return None


def pour(farm: Farm, spot: Spot, now: float) -> None:
    farm.water -= 1
    spot.watered |= 1 << stage_of(spot, now)


def water(farm: Farm, spot: Spot, now: float) -> None:
    """Water the spot's current stage, using 1 water from the can"""
    reason = water_refusal(spot, now)
    if reason:
        raise Refused(reason)
    if farm.water < 1:
        raise Refused(EMPTY_CAN)
    pour(farm, spot, now)


def water_row(farm: Farm, plot: Plot, index: int, now: float) -> list[int]:
    """The sprinkler can: water every spot in the tapped spot's row that needs it, in order, until the can runs dry.
    Returns the indexes watered"""
    first = index // ROW * ROW
    thirsty = [spot for spot in plot.spots[first : first + ROW] if water_refusal(spot, now) is None]
    if not thirsty:
        raise Refused("Nothing in this row needs water")
    if farm.water < 1:
        raise Refused(EMPTY_CAN)
    watered = []
    for spot in thirsty[: farm.water]:
        pour(farm, spot, now)
        watered.append(spot.index)
    return watered


def refill(farm: Farm) -> None:
    """Fill the can at the Pond"""
    farm.water = CANS[farm.can_tier].capacity


def harvest_refusal(spot: Spot, now: float) -> str | None:
    if spoil_of(spot, now) == "rotted":
        return ROTTED
    if spot.state != "growing":
        return "Nothing to harvest here"
    if now < ripe_at(spot):
        return "It isn't ripe yet"
    return None


def roll_harvest(rng: random.Random, perfect: bool) -> tuple[int, bool, int]:
    """The amount (1 to 3), whether it is exceptional, and the free seeds rolled, in that order"""
    roll = rng.random()
    amount = 1 if roll < 0.5 else 2 if roll < 0.9 else 3
    exceptional = rng.random() < (PERFECT_EXCEPTIONAL_ODDS if perfect else EXCEPTIONAL_ODDS)
    seeds = rng.choice([1, 2]) if rng.random() < FREE_SEED_ODDS else 0
    return amount, exceptional, seeds


def regrow(spot: Spot, now: float) -> None:
    """After a harvest a bush starts its next cycle in place; any other crop leaves the spot untilled"""
    if CROPS[spot.crop].bush:
        spot.cycle += 1
        start_cycle(spot, now)
    else:
        clear(spot)


def harvest(farm: Farm, spot: Spot, now: float, rng: random.Random) -> tuple[dict, list[dict]]:
    """Pick a ripe crop into storage and gain its XP. Refused with nothing changed unless both of the crop's stacks have
    room for the biggest harvest. That check comes before any roll: a refusal after the rolls would let a player tap
    again and again until a roll came out exceptional"""
    reason = harvest_refusal(spot, now)
    if reason:
        raise Refused(reason)
    crop = CROPS[spot.crop]
    normal, special = f"crop:{crop.key}", f"crop:{crop.key}:x"
    if any(count(farm, key) + BIGGEST_HARVEST > storage_limit(farm) for key in (normal, special)):
        raise Refused("Storage full")
    dry = dry_stages(spot, now)
    spoil = spoil_of(spot, now)
    dry_mult = 1 - DRY_STAGE_LOSS * dry
    spoil_mult = SPOIL_VALUES[spoil]
    perfect = dry == 0 and spoil == "fresh"
    amount, exceptional, seeds = roll_harvest(rng, perfect)
    bonus = 2 if exceptional else 1
    worth = round(crop.sell_price * amount * dry_mult * spoil_mult * bonus)
    add_item(farm, special if exceptional else normal, amount, worth)
    # Free seeds that don't fit are lost
    seeds = min(seeds, storage_limit(farm) - count(farm, f"seed:{crop.key}"))
    if seeds:
        add_item(farm, f"seed:{crop.key}", seeds)
    xp = round(crop.xp * dry_mult * spoil_mult * bonus)
    farm.harvested.add(crop.key)
    regrow(spot, now)
    result = {
        "crop": crop.key,
        "amount": amount,
        "exceptional": exceptional,
        "seeds": seeds,
        "worth": worth,
        "xp": xp,
        "perfect": perfect,
    }
    return result, gain_xp(farm, xp, now)


def hoe_area(farm: Farm, plot: Plot, index: int) -> list[Spot]:
    """The spots one hoe tap works: the spot itself, its row with the wide hoe, the whole plot with the plow"""
    if farm.hoe_tier == 2:
        return plot.spots
    if farm.hoe_tier == 1:
        first = index // ROW * ROW
        return plot.spots[first : first + ROW]
    return [plot.spots[index]]


def till(farm: Farm, plot: Plot, index: int, now: float, dig: bool = False) -> list[int]:
    """A hoe tap: untilled ground is tilled and rotted crops are cleared across the hoe's area. A living crop on the
    tapped spot is dug up only when `dig` asks for it, and nothing else changes then. Returns the indexes changed"""
    spot = plot.spots[index]
    if spot.state == "growing" and spoil_of(spot, now) != "rotted":
        if not dig:
            raise Refused("Something is growing here")
        clear(spot)
        return [index]
    changed = []
    for other in hoe_area(farm, plot, index):
        if spoil_of(other, now) == "rotted":
            clear(other)
        elif other.state == "untilled":
            other.state = "tilled"
        else:
            continue
        changed.append(other.index)
    if not changed:
        raise Refused("Already tilled")
    return changed


def settle_spot(spot: Spot, since: float, now: float, plot: int) -> list[dict]:
    """The ripe, dried, withered and rotted moments in (since, now], once each. A crop past its rot mark rots"""
    if spot.state != "growing":
        return []
    events = []
    for state, after in SPOIL_MARKS:
        at = ripe_at(spot) + after
        if since < at <= now:
            kind = "ripe" if state == "fresh" else state
            events.append({"kind": kind, "at": at, "plot": plot, "spot": spot.index, "crop": spot.crop})
    if spoil_of(spot, now) == "rotted":
        spot.state = "rotted"
    return events
