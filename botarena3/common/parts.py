"""The original's parts: weapons (repair tools are weapons with negative damage), platings and chassis. The numbers
come from data.json, built from the decompiled game by FlashRE/bot-arena-3/tools/build_data.py"""

import json
from dataclasses import dataclass
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data.json").read_text(encoding="utf-8"))

# Given for beating the game, never sold (their level is 30)
PRIZE_WEAPON = 'PRIZE DARSIK "R200-Z"'
PRIZE_PLATING = 'PRIZE OVERWATCH "R760"'
# The original sells this after beating the game and gives it for a code word. This port leaves it out
SECRET_LASER = 'NEVERLAX "SDW"'


@dataclass(frozen=True)
class Weapon:
    name: str
    kind: str
    weight: int
    cost: int
    gun: int
    damage: int
    refire: int
    max_range: int
    min_range: int
    spread: int
    streak: int
    spark: int
    discharge: int
    sound: str
    rico_min: int
    rico_max: int
    hostile: bool
    level: int
    description: str


@dataclass(frozen=True)
class Plating:
    name: str
    kind: str
    weight: int
    cost: int
    graphic: int
    shielding: int
    level: int
    description: str


@dataclass(frozen=True)
class Chassis:
    name: str
    kind: str
    weight: int
    cost: int
    max_load: int
    graphic: int
    shielding: int
    level: int
    description: str


WEAPONS = {row["name"]: Weapon(**row) for row in DATA["weapons"]}
PLATINGS = {row["name"]: Plating(**row) for row in DATA["platings"]}
CHASSIS = {row["name"]: Chassis(**row) for row in DATA["chassis"]}
KINDS = {"weapon": WEAPONS, "plating": PLATINGS, "chassis": CHASSIS}


def find(name: str) -> Weapon | Plating | Chassis | None:
    return WEAPONS.get(name) or PLATINGS.get(name) or CHASSIS.get(name)


def for_sale(kind: str, level: int) -> list:
    """What the shop lists for a career at this level, in the original's order"""
    return [part for part in KINDS[kind].values() if part.level <= level and part.name != SECRET_LASER]
