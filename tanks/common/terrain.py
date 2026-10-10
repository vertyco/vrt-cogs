"""The ground: one solid column per pixel across the 550 x 400 field, built fresh each round from the landscape's
generator, as the original builds it from 550 column clips. Only each column's top is kept: its bottom always sits
below the field, where nothing can reach it"""

import math
import random
from dataclasses import dataclass, field

WIDTH = 550
HEIGHT = 400
LANDSCAPES = (1, 2, 3)
# Where the original's column clip sits before a landscape moves it, minus half its 500 pixel height
BASE_TOP = {1: 497.6 - 250, 2: 536 - 250, 3: 615 - 250}
# How far the wind moves each turn at most, per landscape
WIND_CHANGE = {1: 16, 2: 12, 3: 6}


def js_round(value: float) -> int:
    """Flash's Math.round: halves go up, unlike Python's round"""
    return math.floor(value + 0.5)


def flash_random(rng: random.Random, n: int) -> int:
    """Flash's random(n): a whole number from 0 to n - 1"""
    return rng.randrange(n)


@dataclass
class Field:
    landscape: int
    tops: list[float]
    wind: float
    # Decoration only: (x, kind). The page drops each tree onto the ground below it
    trees: list[tuple[int, int]] = field(default_factory=list)

    def top(self, column: int) -> float:
        """A column's top. Outside the field there is no column, and every comparison with NaN is false, as with
        the original's missing clips"""
        if 0 <= column < WIDTH:
            return self.tops[column]
        return math.nan

    def change_wind(self, rng: random.Random) -> None:
        """The original's turn-by-turn wind: it wanders, with no limit"""
        change = WIND_CHANGE[self.landscape]
        self.wind += -flash_random(rng, change) + change / 2

    def ground_view(self) -> list[int]:
        return [js_round(top) for top in self.tops]


def wind_side(rng: random.Random) -> int:
    side = 0
    while side == 0:
        side = flash_random(rng, 3) - 1
    return side


def generate(landscape: int, rng: random.Random) -> Field:
    """A fresh round's ground, starting wind and trees, from the original's three generators"""
    base = BASE_TOP[landscape]
    side = wind_side(rng)
    if landscape == 1:
        wind = (flash_random(rng, 50) + 30) * side
        n3 = flash_random(rng, 300) + 50
        n4 = flash_random(rng, 300) + 50
        ran = flash_random(rng, 500)
        tops = [base + math.sin(math.pi / n3 * i) * math.cos(math.pi / n4 * i) * (ran - i) / 2 for i in range(WIDTH)]
        trees = [(flash_random(rng, WIDTH), 1) for _ in range(flash_random(rng, 5) + 2)]
    elif landscape == 2:
        wind = (flash_random(rng, 25) + 25) * side
        n4 = flash_random(rng, 200) + 50
        ran = flash_random(rng, 500)
        tops = [base + math.sin(math.radians(i)) * math.cos(math.pi / n4 * i) * (ran - i) / 4 / 2 for i in range(WIDTH)]
        trees = spaced_trees(rng)
    else:
        wind = flash_random(rng, 20) * side
        size = flash_random(rng, 400) / 10 + 1
        stretch = (flash_random(rng, 15) + 1) / 10
        tops = [base + math.sin(math.radians(i) * stretch) * size / 2 for i in range(WIDTH)]
        trees = []
    return Field(landscape, tops, float(wind), trees)


def spaced_trees(rng: random.Random) -> list[tuple[int, int]]:
    """The second landscape's row of trees, 8 to 37 pixels apart"""
    trees = []
    x = 0
    while len(trees) < 100:
        trees.append((min(x, WIDTH - 1), 2))
        x += flash_random(rng, 30) + 8
        if x > WIDTH:
            break
    return trees
