"""A farm and the few helpers every rule touches. No Discord, no database: tests build farms directly"""

import uuid
from dataclasses import dataclass, field

from ..catalog import CANS, PLOTS, SPOTS, STORAGE


class Refused(Exception):
    """A request the game turns down. Its text is shown to the player as it is"""


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Spot:
    index: int
    # "untilled", "tilled", "growing" or "rotted"
    state: str = "untilled"
    crop: str | None = None
    planted_at: float = 0.0
    # Seconds one growth stage lasts, fixed when planted
    stage_len: float = 0.0
    # Bit k is set when stage k was watered by hand
    watered: int = 0
    # Bush harvests so far
    cycle: int = 0


def untilled_spots() -> list[Spot]:
    """A plot's nine spots, rows being 0-2, 3-5 and 6-8"""
    return [Spot(index) for index in range(SPOTS)]


@dataclass
class Plot:
    number: int
    unlocked: bool = False
    # "crops" or "animals"
    kind: str = "crops"
    spots: list[Spot] = field(default_factory=untilled_spots)


@dataclass(kw_only=True)
class Animal:
    id: str = field(default_factory=new_id)
    kind: str
    # "male" or "female"
    sex: str
    # The pen's plot number, or None while the baby waits in the farmhouse
    plot: int | None = None
    arrived_at: float = 0.0
    fed_at: float = 0.0
    watered_at: float = 0.0
    # Care windows missed over its whole life, and the ones missed before it grew up (fixed at adulthood)
    missed: int = 0
    missed_young: int = 0
    adult: bool = False
    # FarmCoins it sells for when healthy, set at adulthood
    value: int = 0
    exceptional: bool = False
    # Whether it has had its one litter
    bred: bool = False
    # The last breeding try, 0 if never
    tried_at: float = 0.0
    # When the babies come, 0 if not expecting
    pregnant_until: float = 0.0
    litter: int = 0
    sickly: bool = False
    malnourished: bool = False
    # Start of the current stretch with no missed care window
    cared_since: float = 0.0


@dataclass
class Item:
    key: str
    quantity: int = 0
    # What the whole stack sells for. Crops only: every harvest is worth a different amount
    worth: int = 0


@dataclass(kw_only=True)
class Decoration:
    id: str = field(default_factory=new_id)
    item: str
    # "yard", "room2", "room3", or None while it is not placed
    room: str | None = None
    # Where it sits, as a share (0 to 1) of the room's width and height
    x: float = 0.0
    y: float = 0.0


@dataclass(kw_only=True)
class Farm:
    user_id: int
    # The player's Discord display name, for the leaderboard
    name: str
    coins: int = 0
    xp: int = 0
    level: int = 1
    storage_tier: int = 0
    can_tier: int = 0
    hoe_tier: int = 0
    # Water in the can
    water: int = 0
    # Extra farmhouse rooms owned
    rooms: int = 0
    # Plot switches paid for
    switches: int = 0
    hat: str | None = None
    top: str | None = None
    bottom: str | None = None
    outfits: set[str] = field(default_factory=set)
    sound: bool = True
    music: bool = True
    crops_sold: int = 0
    animals_sold: int = 0
    litters: int = 0
    # Crop keys ever harvested
    harvested: set[str] = field(default_factory=set)
    settled_at: float = 0.0
    plots: dict[int, Plot] = field(default_factory=dict)
    animals: list[Animal] = field(default_factory=list)
    items: dict[str, Item] = field(default_factory=dict)
    # Achievement key to when it was earned
    achievements: dict[str, float] = field(default_factory=dict)
    decorations: list[Decoration] = field(default_factory=list)
    # Extra room number (2 or 3) to the text the player wrote for it
    descriptions: dict[int, str] = field(default_factory=dict)


def new_farm(user_id: int, name: str, now: float) -> Farm:
    """A first-time player's farm: five wildflower packets, a full starter can, and only Plot 1 open"""
    return Farm(
        user_id=user_id,
        name=name,
        water=CANS[0].capacity,
        items={"seed:wildflowers": Item("seed:wildflowers", 5)},
        plots={number: Plot(number, unlocked=number == 1) for number in PLOTS},
        settled_at=now,
    )


def storage_limit(farm: Farm) -> int:
    """How many of each item the farm holds"""
    return STORAGE[farm.storage_tier].limit


def count(farm: Farm, key: str) -> int:
    item = farm.items.get(key)
    return item.quantity if item else 0


def add_item(farm: Farm, key: str, n: int, worth: int = 0) -> None:
    """Put `n` of an item in storage, adding `worth` to its stack. Refused when that many don't fit"""
    if count(farm, key) + n > storage_limit(farm):
        raise Refused("Storage full")
    item = farm.items.setdefault(key, Item(key))
    item.quantity += n
    item.worth += worth


def take_item(farm: Farm, key: str, n: int) -> int:
    """Take `n` of an item out of storage and return its share of the stack's worth. The stack keeps the rest"""
    item = farm.items.get(key)
    if item is None or item.quantity < n:
        raise Refused("You don't have that many")
    share = item.worth * n // item.quantity
    item.quantity -= n
    item.worth -= share
    if item.quantity == 0:
        del farm.items[key]
    return share


def pen_animals(farm: Farm, plot: int) -> list[Animal]:
    return [animal for animal in farm.animals if animal.plot == plot]


def waiting(farm: Farm) -> list[Animal]:
    """The babies waiting in the farmhouse for a pen"""
    return [animal for animal in farm.animals if animal.plot is None]
