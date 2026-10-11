"""One animal's rules: arriving in a pen, feed and water, growing up, falling ill, healing and dying, breeding, and
the settle that plays those moments out in time order. Each action assumes the farm was settled up to `now` first,
and the caller checks the animal is the player's and any plot it names is an open pen"""

import math
import random

from ..catalog import (
    ANIMALS,
    CARE_WINDOW,
    CROPS,
    DEATH_AFTER,
    HEAL_AFTER,
    MALNOURISHED_AFTER,
    MALNOURISHED_VALUE,
    PEN_SIZE,
    SICKLY_AFTER,
    SICKLY_VALUE,
)
from .calendar import HOUR
from .crops import EMPTY_CAN
from .model import Animal, Farm, Refused, count, pen_animals, take_item, waiting
from .progress import gain_xp

EXCEPTIONAL_ODDS = 0.05
PERFECT_EXCEPTIONAL_ODDS = 0.10
BREED_ODDS = 0.5
MALE_ODDS = 0.5
# A female tries at most once per rest, and a litter comes this long after the try that worked
BREED_REST = 2 * HOUR
PREGNANCY = 1 * HOUR
# Share of the adult's XP a litter gives
LITTER_XP = 0.10
# One item of a feed crop, normal or exceptional, is a meal for any animal
FEED_CROPS = frozenset(f"crop:{key}{grade}" for key, crop in CROPS.items() if crop.feed for grade in ("", ":x"))
# Moments that fall on the same instant happen in this order: a death frees its pen spot before a birth counts the room
ORDER = ("grown", "sickly", "malnourished", "died", "healed", "born")
NEEDS_NOTHING = "Babies waiting in the farmhouse need nothing until they're in a pen"
NO_LUCK = "No luck this time. Try again in 2 hours."


def arrive(animal: Animal, t: float) -> None:
    """The animal reaches a pen at `t`, fed and watered: bought, born there, or moved in from the farmhouse"""
    animal.arrived_at = animal.fed_at = animal.watered_at = animal.cared_since = t


def grown_at(animal: Animal) -> float:
    return animal.arrived_at + ANIMALS[animal.kind].grow_time


def gap_misses(start: float, end: float) -> int:
    """Care windows missed in a gap between two feedings (or two waterings)"""
    return max(0, math.floor((end - start) / CARE_WINDOW))


def open_misses(animal: Animal, now: float) -> int:
    """Windows missed so far in the gaps still open, which `missed` doesn't hold yet. Waiting babies need nothing"""
    if animal.plot is None:
        return 0
    return gap_misses(animal.fed_at, now) + gap_misses(animal.watered_at, now)


def tend(animal: Animal, last: float, now: float) -> None:
    """Close a feeding or watering gap that began at `last`. A gap that missed a window starts a new stretch of care"""
    missed = gap_misses(last, now)
    animal.missed += missed
    if missed:
        animal.cared_since = now


def feed(farm: Farm, animal: Animal, item_key: str, now: float) -> None:
    """One meal: a bag of the animal's own feed, or one feed crop (taking its share of the stack's worth)"""
    if animal.plot is None:
        raise Refused(NEEDS_NOTHING)
    if item_key != f"feed:{animal.kind}" and item_key not in FEED_CROPS:
        raise Refused(f"That isn't food for a {ANIMALS[animal.kind].name.lower()}")
    if count(farm, item_key) < 1:
        raise Refused("You don't have any left")
    take_item(farm, item_key, 1)
    tend(animal, animal.fed_at, now)
    animal.fed_at = now


def water_animal(farm: Farm, animal: Animal, now: float) -> None:
    """A drink from the watering can, 1 water"""
    if animal.plot is None:
        raise Refused(NEEDS_NOTHING)
    if farm.water < 1:
        raise Refused(EMPTY_CAN)
    farm.water -= 1
    tend(animal, animal.watered_at, now)
    animal.watered_at = now


def condition(animal: Animal, now: float) -> str:
    """ "healthy", "sickly" or "malnourished". Babies never fall ill. An adult's neglect counts from its older clock,
    so the answer holds even before a settle marks it"""
    neglect = now - min(animal.fed_at, animal.watered_at) if animal.adult else 0.0
    if animal.malnourished or neglect >= MALNOURISHED_AFTER:
        return "malnourished"
    if animal.sickly or neglect >= SICKLY_AFTER:
        return "sickly"
    return "healthy"


def sell_price(animal: Animal) -> int:
    """Its value, cut while it is sickly and for good once malnourished. A baby's value is 0 until it grows up"""
    share = MALNOURISHED_VALUE if animal.malnourished else SICKLY_VALUE if animal.sickly else 1.0
    return round(animal.value * share)


def is_perfect(animal: Animal, now: float) -> bool:
    """It never missed a care window, counting the gaps still open"""
    return animal.missed + open_misses(animal, now) == 0


def readiness(female: Animal, now: float) -> str | None:
    """Why she herself can't try for babies now, or None when she can"""
    if female.sex != "female":
        return "Only a female can have babies"
    if not female.adult:
        return "She's too young to have babies"
    state = condition(female, now)
    if state == "malnourished":
        return "She's malnourished and can't have babies"
    if state == "sickly":
        return "She's sickly. Nurse her back to health first"
    if female.pregnant_until:
        return "She's already expecting"
    if female.bred:
        return "She's already had her babies"
    rest = female.tried_at + BREED_REST - now
    if rest > 0:
        minutes = math.ceil(rest / 60)
        return f"She needs a rest. Try again in {minutes} minute{'' if minutes == 1 else 's'}"
    return None


def is_mate(male: Animal, female: Animal, now: float) -> bool:
    return male.sex == "male" and male.adult and male.kind == female.kind and condition(male, now) == "healthy"


def breed_refusal(farm: Farm, female: Animal, now: float) -> str | None:
    """Why the female can't try for babies now, or None when she can"""
    reason = readiness(female, now)
    if reason:
        return reason
    if not any(is_mate(male, female, now) for male in pen_animals(farm, female.plot)):
        return f"She needs a healthy grown-up male {ANIMALS[female.kind].name.lower()} in her pen"
    if waiting(farm):
        return "Move the babies waiting in the farmhouse into a pen first"
    return None


def breed(farm: Farm, female: Animal, now: float, rng: random.Random) -> tuple[dict, list[dict]]:
    """Tap a female to try for babies. Half the tries work: her litter comes an hour later and she never breeds again.
    A try that fails still counts, so she rests before the next one"""
    reason = breed_refusal(farm, female, now)
    if reason:
        raise Refused(reason)
    female.tried_at = now
    if rng.random() >= BREED_ODDS:
        return {"success": False, "message": NO_LUCK}, []
    roll = rng.random()
    female.bred = True
    female.pregnant_until = now + PREGNANCY
    female.litter = 1 if roll < 0.6 else 2 if roll < 0.9 else 3
    return {"success": True, "due": female.pregnant_until}, []


def move_baby(farm: Farm, animal: Animal, plot: int, now: float) -> None:
    """Bring a waiting baby from the farmhouse into a pen with room. Its clock starts now"""
    if animal.plot is not None:
        raise Refused("It's already in a pen")
    if len(pen_animals(farm, plot)) >= PEN_SIZE:
        raise Refused("That pen is full")
    animal.plot = plot
    arrive(animal, now)


def moments(animal: Animal) -> list[tuple[float, str]]:
    """The changes still ahead for an animal in a pen, as (when, what). Waiting babies have no clock"""
    if animal.plot is None:
        return []
    grown = grown_at(animal)
    if not animal.adult:
        return [(grown, "grown")]
    # Only adults fall ill, so neglect counted while it was a baby lands at the moment it grows up
    neglected = min(animal.fed_at, animal.watered_at)
    ahead = [(max(neglected + DEATH_AFTER, grown), "died")]
    if animal.pregnant_until:
        ahead.append((animal.pregnant_until, "born"))
    if not animal.sickly:
        ahead.append((max(neglected + SICKLY_AFTER, grown), "sickly"))
    if not animal.malnourished:
        ahead.append((max(neglected + MALNOURISHED_AFTER, grown), "malnourished"))
    # Healing needs a full stretch of care that ends before either open gap reaches a window
    healed = animal.cared_since + HEAL_AFTER
    if animal.sickly and not animal.malnourished and healed <= neglected + CARE_WINDOW:
        ahead.append((healed, "healed"))
    return ahead


def next_moment(farm: Farm, since: float, now: float) -> tuple[float, str, Animal] | None:
    """The farm's earliest animal moment in (since, now]"""
    due = [
        (at, ORDER.index(what), position)
        for position, animal in enumerate(farm.animals)
        for at, what in moments(animal)
        if since < at <= now
    ]
    if not due:
        return None
    at, rank, position = min(due)
    return at, ORDER[rank], farm.animals[position]


def grow_up(farm: Farm, animal: Animal, rng: random.Random) -> list[dict]:
    """Adulthood: the windows missed as a baby set the care score, and with it the animal's value and XP"""
    info = ANIMALS[animal.kind]
    at = grown_at(animal)
    windows = math.floor(info.grow_time / CARE_WINDOW)
    # Closed gaps plus the open ones cut at this moment, for food and water both
    animal.missed_young = animal.missed + gap_misses(animal.fed_at, at) + gap_misses(animal.watered_at, at)
    score = 1.0 if windows == 0 else max(0.0, 1 - animal.missed_young / (2 * windows))
    animal.exceptional = rng.random() < (PERFECT_EXCEPTIONAL_ODDS if animal.missed_young == 0 else EXCEPTIONAL_ODDS)
    bonus = 2 if animal.exceptional else 1
    animal.value = round(info.adult_price * score * bonus)
    animal.adult = True
    xp = round(info.adult_xp * score * bonus)
    event = {
        "kind": "grown",
        "at": at,
        "animal": animal.id,
        "species": animal.kind,
        "xp": xp,
        "exceptional": animal.exceptional,
    }
    return [event, *gain_xp(farm, xp, at)]


def give_birth(farm: Farm, mother: Animal, at: float, rng: random.Random) -> list[dict]:
    """The litter arrives in the mother's pen while it has room. The rest wait in the farmhouse, with no clock yet"""
    room = PEN_SIZE - len(pen_animals(farm, mother.plot))
    babies = []
    for number in range(mother.litter):
        baby = Animal(kind=mother.kind, sex="male" if rng.random() < MALE_ODDS else "female")
        if number < room:
            baby.plot = mother.plot
            arrive(baby, at)
        babies.append(baby)
    farm.animals += babies
    farm.litters += 1
    mother.pregnant_until = 0.0
    mother.litter = 0
    xp = round(LITTER_XP * ANIMALS[mother.kind].adult_xp)
    event = {
        "kind": "born",
        "at": at,
        "mother": mother.id,
        "species": mother.kind,
        "babies": len(babies),
        "waiting": sum(baby.plot is None for baby in babies),
        "xp": xp,
    }
    return [event, *gain_xp(farm, xp, at)]


def apply_moment(farm: Farm, animal: Animal, what: str, at: float, rng: random.Random) -> list[dict]:
    if what == "born":
        return give_birth(farm, animal, at, rng)
    if what == "grown":
        return grow_up(farm, animal, rng)
    if what == "died":
        farm.animals.remove(animal)
    elif what == "sickly":
        animal.sickly = True
        # Its last stretch of care ended with the neglect that made it ill. Left as it was, that old stretch would
        # pass the healing test at once, and the animal would flip between sickly and healed without end
        animal.cared_since = at
    elif what == "malnourished":
        animal.malnourished = True
    elif what == "healed":
        animal.sickly = False
    return [{"kind": what, "at": at, "animal": animal.id, "species": animal.kind}]


def settle_animals(farm: Farm, since: float, now: float, rng: random.Random) -> list[dict]:
    """Every animal moment in (since, now], one at a time in time order across the whole farm: births, growing up,
    falling sickly, malnourished, healing and dying. Each changes the animal, so none happens twice, and a pen's room
    at a birth is the room left at that moment"""
    events = []
    while moment := next_moment(farm, since, now):
        at, what, animal = moment
        events += apply_moment(farm, animal, what, at, rng)
    return events
