"""Texas Hold'em hand ranking: which five cards make a player's best hand, and what to call it"""

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Sequence

from redbot.core.i18n import Translator

from .cards import RANKS, Card

_ = Translator("Vegas", __file__)

VALUES = {rank: index + 2 for index, rank in enumerate(RANKS)}

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)


@dataclass(frozen=True, order=True)
class HandRank:
    category: int
    tiebreak: tuple[int, ...]
    cards: tuple[Card, ...] = field(default=(), compare=False)


def rank_name(value: int, plural: bool = False) -> str:
    """A rank's name by its value: Ace/Aces, King/Kings, 10/10s"""
    singular = {14: _("Ace"), 13: _("King"), 12: _("Queen"), 11: _("Jack")}
    multiple = {14: _("Aces"), 13: _("Kings"), 12: _("Queens"), 11: _("Jacks")}
    if value in singular:
        return (multiple if plural else singular)[value]
    return f"{value}s" if plural else str(value)


def straight_high(values: Sequence[int]) -> int:
    """The top card of a five-card straight, or 0. The Ace plays low in A-2-3-4-5, which is five high"""
    unique = sorted(set(values))
    if len(unique) != 5:
        return 0
    if unique[-1] - unique[0] == 4:
        return unique[-1]
    return 5 if unique == [2, 3, 4, 5, 14] else 0


def score_five(five: Sequence[Card]) -> tuple[int, tuple[int, ...]]:
    values = [VALUES[rank] for rank, suit in five]
    # Groups sorted by size then value, so the pair or trips come before their kickers
    groups = sorted(Counter(values).items(), key=lambda item: (item[1], item[0]), reverse=True)
    ordered = tuple(group[0] for group in groups)
    sizes = [group[1] for group in groups]
    flush = len({suit for rank, suit in five}) == 1
    high = straight_high(values)
    if high and flush:
        return STRAIGHT_FLUSH, (high,)
    if sizes == [4, 1]:
        return QUADS, ordered
    if sizes == [3, 2]:
        return FULL_HOUSE, ordered
    if flush:
        return FLUSH, ordered
    if high:
        return STRAIGHT, (high,)
    if sizes == [3, 1, 1]:
        return TRIPS, ordered
    if sizes == [2, 2, 1]:
        return TWO_PAIR, ordered
    if sizes == [2, 1, 1, 1]:
        return PAIR, ordered
    return HIGH_CARD, ordered


def best_hand(cards: Sequence[Card]) -> HandRank:
    """The best five-card hand among 5 to 7 cards"""
    ranks = []
    for five in combinations(cards, 5):
        category, tiebreak = score_five(five)
        ranks.append(HandRank(category, tiebreak, tuple(five)))
    return max(ranks)


def hand_name(rank: HandRank) -> str:
    tie = rank.tiebreak
    category = rank.category
    if category == STRAIGHT_FLUSH:
        if tie[0] == 14:
            return _("Royal flush")
        return _("Straight flush, {high} high").format(high=rank_name(tie[0]))
    if category == QUADS:
        return _("Four of a kind, {rank}").format(rank=rank_name(tie[0], True))
    if category == FULL_HOUSE:
        return _("Full house, {trips} over {pair}").format(trips=rank_name(tie[0], True), pair=rank_name(tie[1], True))
    if category == FLUSH:
        return _("Flush, {high} high").format(high=rank_name(tie[0]))
    if category == STRAIGHT:
        return _("Straight, {high} high").format(high=rank_name(tie[0]))
    if category == TRIPS:
        return _("Three of a kind, {rank}").format(rank=rank_name(tie[0], True))
    if category == TWO_PAIR:
        return _("Two pair, {high} and {low}").format(high=rank_name(tie[0], True), low=rank_name(tie[1], True))
    if category == PAIR:
        return _("Pair of {rank}").format(rank=rank_name(tie[0], True))
    return _("High card, {rank}").format(rank=rank_name(tie[0]))


def describe(cards: Sequence[Card]) -> str:
    """A hand's name for 2 to 7 cards. With fewer than five it names only a pair or the high card"""
    if len(cards) >= 5:
        return hand_name(best_hand(cards))
    values = sorted((VALUES[rank] for rank, suit in cards), reverse=True)
    pairs = [value for value, count in Counter(values).items() if count >= 2]
    if pairs:
        return hand_name(HandRank(PAIR, (max(pairs),)))
    return hand_name(HandRank(HIGH_CARD, (values[0],)))
