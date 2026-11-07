"""The practice CPU: decides one Hold'em move from what it can see. Pure rules code, no async"""

import math
import random
from dataclasses import dataclass

from .cards import RANKS, SUITS, Card
from .holdem import Action, Legal
from .poker import VALUES, best_hand

TRIALS = 120  # simulated run-outs per decision; the 50 ms budget is why this is not higher

BLUFF_CHANCE = 0.08  # junk bets when checking is free
VALUE_BET = 0.62  # share of run-outs won before the CPU bets for value
RAISE_FACING_BET = 0.80  # share won before the CPU raises someone else's bet
MARGIN = 0.04  # extra share over the pot odds a call needs

CHEN_HIGH = {14: 10, 13: 8, 12: 7, 11: 6}
CHEN_GAP = (0, -1, -2, -4)


@dataclass(frozen=True)
class Spot:
    hole: tuple[Card, Card]
    board: tuple[Card, ...]
    legal: Legal
    pot: int  # every chip in the middle, this round's bets included
    big: int
    opponents: int  # players still in, not counting this CPU
    street: str
    bet: int = 0  # this CPU's chips already in this round


def preflop_score(hole: tuple[Card, Card]) -> float:
    """Chen formula points for two hole cards: 20 for pocket Aces, negative for the worst hands"""
    high, low = sorted((VALUES[hole[0][0]], VALUES[hole[1][0]]), reverse=True)
    points = CHEN_HIGH.get(high, high / 2)
    if high == low:
        return max(points * 2, 5)
    if hole[0][1] == hole[1][1]:
        points += 2
    gap = high - low - 1
    points += CHEN_GAP[gap] if gap < len(CHEN_GAP) else -5
    if gap <= 1 and high < 12:
        points += 1
    return math.ceil(points)


def strength(hole, board, opponents: int, rng: random.Random, trials: int = TRIALS) -> float:
    """Share of simulated run-outs this hand wins against random hands (a tie counts as a split share)"""
    seen = set(hole) | set(board)
    unseen = [(rank, suit) for suit in SUITS for rank in RANKS if (rank, suit) not in seen]
    missing = 5 - len(board)
    need = missing + 2 * opponents
    won = 0.0
    for _ in range(trials):
        drawn = rng.sample(unseen, need)
        full = [*board, *drawn[:missing]]
        mine = best_hand([*hole, *full])
        best_other = max(best_hand([*drawn[missing + 2 * i : missing + 2 * i + 2], *full]) for i in range(opponents))
        if mine > best_other:
            won += 1
        elif mine == best_other:
            won += 0.5  # a split with one rival; more than one tie is rare enough to ignore
    return won / trials


def raise_to(spot: Spot, rng: random.Random) -> Action:
    """A raise of about half to the whole pot, clamped into what is legal"""
    legal = spot.legal
    size = (spot.pot + legal.call) * rng.uniform(0.5, 1.0)
    target = int(spot.bet + legal.call + size)
    return Action("raise", max(legal.min_to, min(legal.max_to, target)))


def passive(legal: Legal) -> Action:
    """Check when it is free, otherwise fold"""
    if legal.check:
        return Action("check")
    return Action("fold" if legal.fold else "call")


def preflop(spot: Spot, rng: random.Random) -> Action:
    legal = spot.legal
    score = preflop_score(spot.hole)
    if legal.min_to is not None and score >= 10 and legal.call <= 8 * spot.big:
        return raise_to(spot, rng)
    if legal.call == 0:
        if legal.min_to is not None and score >= 7 and rng.random() < 0.3:
            return raise_to(spot, rng)
        return Action("check")
    cheap = legal.call <= 2 * spot.big
    if score >= 12 or (score >= 8 and legal.call <= 6 * spot.big) or (score >= 5 and cheap):
        return Action("call")
    return passive(legal)


def postflop(spot: Spot, rng: random.Random) -> Action:
    legal = spot.legal
    share = strength(spot.hole, spot.board, spot.opponents, rng)
    can_raise = legal.min_to is not None
    if legal.call == 0:
        if can_raise and share >= VALUE_BET and rng.random() < 0.85:
            return raise_to(spot, rng)
        if can_raise and share < 0.35 and rng.random() < BLUFF_CHANCE:
            return raise_to(spot, rng)
        return Action("check")
    odds = legal.call / (spot.pot + legal.call)
    if can_raise and share >= RAISE_FACING_BET and rng.random() < 0.6:
        return raise_to(spot, rng)
    if share >= odds + MARGIN:
        return Action("call")
    return passive(legal)


def choose(spot: Spot, rng: random.Random) -> Action:
    action = preflop(spot, rng) if not spot.board else postflop(spot, rng)
    if action.move in spot.legal.moves():
        return action
    return Action(spot.legal.moves()[0])
