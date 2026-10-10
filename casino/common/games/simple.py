"""The quick games: All In, Coin, Cups, Dice, Hi-Lo and Craps. Each function takes the random source, so tests seed it"""

import random

COIN_SIDES = ("heads", "tails")
CUPS = (1, 2, 3)
HILO_CHOICES = ("low", "high", "seven")


def allin_wins(rng: random.Random, multiplier: int) -> bool:
    """A win is 1 in (multiplier + 2), as the original drew it"""
    return rng.randint(0, multiplier + 1) == 0


def flip(rng: random.Random) -> str:
    return rng.choice(COIN_SIDES)


def hide_coin(rng: random.Random) -> int:
    return rng.randint(1, 3)


def roll(rng: random.Random) -> tuple[int, int]:
    return rng.randint(1, 6), rng.randint(1, 6)


def dice_wins(dice: tuple[int, int]) -> bool:
    return sum(dice) in (2, 7, 11, 12)


def hilo_side(total: int) -> str:
    if total < 7:
        return "low"
    if total > 7:
        return "high"
    return "seven"


def hilo_factor(choice: str, dice: tuple[int, int]) -> int:
    """What the stake is multiplied by before the game's multiplier: 0 for a loss, 5 for a right Seven, else 1"""
    side = hilo_side(sum(dice))
    if choice != side:
        return 0
    return 5 if side == "seven" else 1


def craps_come_out(total: int) -> tuple[str, int]:
    """win (with its factor before the multiplier), lose, or point"""
    if total == 7:
        return "win", 3
    if total == 11:
        return "win", 1
    if total in (2, 3, 12):
        return "lose", 0
    return "point", 0
