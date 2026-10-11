"""The farm as the page draws it, worked out for one moment and ready for JSON. Ids are text, moments are unix
seconds, and a detail that only means something for a growing crop or an animal in a pen is None otherwise"""

from ..catalog import CANS, CARE_WINDOW, MAX_LEVEL
from ..game import animals, crops
from ..game.calendar import day_ends_at, season_at, season_ends_at, weather_at
from ..game.market import SLOTS, can_have_free_packet, switch_fee, switch_refusal
from ..game.model import Animal, Decoration, Farm, Plot, Spot, pen_animals, storage_limit, waiting
from ..game.progress import xp_for_level

# What a spot says about its crop's growth. All None while nothing grows: a bare spot has no planting moment or stage
# length, so the crop rules would give nonsense for it
GROWTH = ("planted_at", "stage", "stage_ends_at", "watered", "dry", "ripe_at", "spoil", "spoil_ends_at", "value")


def player(farm: Farm) -> dict:
    return {
        "id": str(farm.user_id),
        "name": farm.name,
        "coins": farm.coins,
        "xp": farm.xp,
        "level": farm.level,
        # The XP this level started at, and the XP the next one starts at (None at the top level)
        "level_xp": xp_for_level(farm.level),
        "next_xp": xp_for_level(farm.level + 1) if farm.level < MAX_LEVEL else None,
    }


def next_spoil_at(spot: Spot, now: float) -> float | None:
    """The crop's next mark after `now`: when it ripens, dries, withers or rots"""
    ripe = crops.ripe_at(spot)
    return next((ripe + after for mark, after in crops.SPOIL_MARKS if now < ripe + after), None)


def growth(spot: Spot, now: float) -> dict:
    """A growing crop at `now`: its stage and when that ends, whether the stage counts as watered (None once ripe,
    when it takes no more water), the stages left dry, when it ripens, how far it has spoiled and when it spoils
    further, and the share (0 to 1) of a full harvest's FarmCoins and XP it would bring"""
    stage = crops.stage_of(spot, now)
    ripe = stage == crops.STAGES
    return {
        "planted_at": spot.planted_at,
        "stage": stage,
        "stage_ends_at": None if ripe else crops.stage_start(spot, stage + 1),
        "watered": None if ripe else crops.stage_watered(spot, stage, now),
        "dry": crops.dry_stages(spot, now),
        "ripe_at": crops.ripe_at(spot),
        "spoil": crops.spoil_of(spot, now),
        "spoil_ends_at": next_spoil_at(spot, now),
        "value": crops.value_multiplier(spot, now),
    }


def spot_row(spot: Spot, now: float) -> dict:
    row = {"index": spot.index, "state": spot.state, "crop": spot.crop, "cycle": spot.cycle}
    return {**row, **(growth(spot, now) if spot.state == "growing" else dict.fromkeys(GROWTH))}


def switch_offer(farm: Farm, plot: Plot) -> dict | None:
    """The kind this plot can switch to right now and what that costs, or None while it can't switch"""
    kind = "crops" if plot.kind == "animals" else "animals"
    if not plot.unlocked or switch_refusal(farm, plot, kind):
        return None
    # Plot 1 always goes back to crops for free
    free = plot.number == 1 and kind == "crops"
    return {"kind": kind, "fee": 0 if free else switch_fee(farm)}


def plot_row(farm: Farm, plot: Plot, now: float) -> dict:
    pen = plot.kind == "animals"
    return {
        "number": plot.number,
        "unlocked": plot.unlocked,
        "kind": plot.kind,
        "spots": [] if pen else [spot_row(spot, now) for spot in plot.spots],
        "animals": [animal.id for animal in pen_animals(farm, plot.number)],
        "switch": switch_offer(farm, plot),
    }


def animal_row(farm: Farm, animal: Animal, now: float) -> dict:
    """An animal at `now`. A baby waiting in the farmhouse has no clock, so it grows, eats and drinks on no schedule"""
    penned = animal.plot is not None
    refusal = animals.breed_refusal(farm, animal, now)
    return {
        "id": animal.id,
        "kind": animal.kind,
        "sex": animal.sex,
        "plot": animal.plot,
        "adult": animal.adult,
        "exceptional": animal.exceptional,
        "grows_up_at": animals.grown_at(animal) if penned and not animal.adult else None,
        "condition": animals.condition(animal, now),
        # Past these moments it has missed a meal or a drink
        "feed_by": animal.fed_at + CARE_WINDOW if penned else None,
        "water_by": animal.watered_at + CARE_WINDOW if penned else None,
        "can_breed": refusal is None,
        # Why she can't try for babies now, in the bot's own words
        "breed_refusal": refusal,
        "expecting_until": animal.pregnant_until or None,
        "price": animals.sell_price(animal) if animal.adult else None,
    }


def decoration_row(decoration: Decoration) -> dict:
    return {"id": decoration.id, "item": decoration.item, "room": decoration.room, "x": decoration.x, "y": decoration.y}


def state(farm: Farm, now: float) -> dict:
    """Everything the page draws, for a farm already settled up to `now`"""
    return {
        "now": now,
        "player": player(farm),
        "season": {"name": season_at(now), "ends_at": season_ends_at(now)},
        "weather": {"name": weather_at(now), "ends_at": day_ends_at(now)},
        "tools": {
            "can": farm.can_tier,
            "hoe": farm.hoe_tier,
            "water": farm.water,
            "capacity": CANS[farm.can_tier].capacity,
        },
        "storage": {"tier": farm.storage_tier, "limit": storage_limit(farm)},
        "items": {key: {"quantity": item.quantity, "worth": item.worth} for key, item in sorted(farm.items.items())},
        "plots": [plot_row(farm, farm.plots[number], now) for number in sorted(farm.plots)],
        "animals": [animal_row(farm, animal, now) for animal in farm.animals if animal.plot is not None],
        "waiting": [animal_row(farm, animal, now) for animal in waiting(farm)],
        "achievements": dict(farm.achievements),
        "decorations": [decoration_row(decoration) for decoration in farm.decorations],
        "rooms": farm.rooms,
        "descriptions": {str(room): text for room, text in sorted(farm.descriptions.items())},
        "outfit": {slot: getattr(farm, slot) for slot in SLOTS},
        "outfits": sorted(farm.outfits),
        "prefs": {"sound": farm.sound, "music": farm.music},
        "switch_fee": switch_fee(farm),
        "free_packet": can_have_free_packet(farm),
    }
