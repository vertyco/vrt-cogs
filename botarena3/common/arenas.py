"""The original's 15 career arenas, 7 challenges and 6 weight classes, from data.json"""

from dataclasses import dataclass

from .parts import DATA


@dataclass(frozen=True)
class Arena:
    name: str
    weight_class: str
    fee: int
    prize: int
    level: int
    win_level: int
    background: int
    opponents: tuple


@dataclass(frozen=True)
class Challenge:
    name: str
    background: int
    description: str
    players: tuple
    opponents: tuple


# The most team weight each class allows. The original also lists a least weight per class but never checks it
WEIGHT_CLASSES = {name: most for name, most in DATA["weight_classes"]}
ARENAS = tuple(Arena(**{**row, "opponents": tuple(row["opponents"])}) for row in DATA["arenas"])
CHALLENGES = tuple(
    Challenge(**{**row, "players": tuple(row["players"]), "opponents": tuple(row["opponents"])})
    for row in DATA["challenges"]
)
FINAL = ARENAS[-1]
BACKGROUNDS = (1, 2, 3)
