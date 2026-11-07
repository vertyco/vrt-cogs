"""Slots: one strip of 22 stops on all three reels, a pay table and the jackpot pot math. No money moves here"""

import math
import random
from collections.abc import Sequence
from typing import Any

STRIP = (
    "seven", "blank", "cherry", "bell", "blank", "coin", "bell", "cherry", "blank", "diamond", "bell",
    "blank", "coin", "cherry", "bell", "blank", "diamond", "blank", "coin", "cherry", "bell", "blank",
)  # fmt: skip
THREE = {"diamond": 50, "coin": 25, "bell": 14, "cherry": 8}
TWO_CHERRIES = 3
JACKPOT_PERCENT = 2
SEED_BETS = 60
CENTS = 100  # the pot is kept in hundredths of a credit
MIN_SPIN = 3.0
MAX_SPIN = 5.5


def spin(rng: random.Random) -> list[int]:
    return [rng.randint(0, len(STRIP) - 1) for _ in range(3)]


def window(stop: int) -> list[str]:
    """What the reel shows at a stop: the symbol above, on the pay line, and below"""
    size = len(STRIP)
    return [STRIP[(stop - 1) % size], STRIP[stop % size], STRIP[(stop + 1) % size]]


def line_of(stops: Sequence[int]) -> tuple[str, str, str]:
    a, b, c = (STRIP[stop % len(STRIP)] for stop in stops)
    return a, b, c


def is_jackpot(line: Sequence[str]) -> bool:
    return all(symbol == "seven" for symbol in line)


def factor(line: Sequence[str]) -> int:
    """What the bet is multiplied by: 0 loses, 1 gives the bet back. 7-7-7 pays the jackpot share instead, so 0"""
    if line[0] == line[1] == line[2]:
        return THREE.get(line[0], 0)
    cherries = list(line).count("cherry")
    if cherries == 2:
        return TWO_CHERRIES
    return 1 if cherries == 1 else 0


def read_strength(value: Any) -> float:
    """How hard the lever was pulled, 0 to 1. Anything that is not a finite number counts as 0"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0.0
    return float(min(1.0, max(0.0, value)))


def spin_seconds(strength: float) -> float:
    return round(MIN_SPIN + (MAX_SPIN - MIN_SPIN) * strength, 2)


def seed(max_bet: int) -> int:
    return SEED_BETS * max_bet * CENTS


def fed(bet: int) -> int:
    return bet * JACKPOT_PERCENT


def share(pot: int, bet: int, max_bet: int) -> int:
    """Whole credits of the pot a winning bet takes: the full pot at the max bet, less for a smaller bet"""
    if bet <= 0 or max_bet <= 0:
        return 0
    return (pot // CENTS) * min(bet, max_bet) // max_bet


def after_win(pot: int, paid: int, max_bet: int) -> int:
    return max(pot - paid * CENTS, seed(max_bet))
