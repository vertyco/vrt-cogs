"""Small worlds for the physics tests: flat ground at a known height, tanks placed by hand, no wind"""

import random

from tanks.common.items import FUEL, Kit
from tanks.common.tank import Tank
from tanks.common.terrain import WIDTH, Field

GROUND = 300.0


def flat(top: float = GROUND, wind: float = 0.0, landscape: int = 3) -> Field:
    return Field(landscape, [top] * WIDTH, wind)


def tank_at(seat: int, x: float, field: Field, energy: float = 100.0) -> Tank:
    """A tank standing on flat ground the way the original settles one: two pixels above the highest column"""
    tank = Tank(seat, Kit(), x)
    tank.y = min(field.top(c) for c in range(int(x) - 6, int(x) + 7)) - 2
    tank.energy = energy
    tank.fuel = tank.kit.extras[FUEL]
    return tank


def rng() -> random.Random:
    return random.Random(11)
