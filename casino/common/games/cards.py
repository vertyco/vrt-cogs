"""A deck of playing cards, and what a card or hand is worth in Blackjack and War"""

import random

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("clubs", "diamonds", "hearts", "spades")
# A card is (rank, suit), for example ("A", "spades"). Lists of two strings travel to the page as JSON
Card = tuple[str, str]

WAR_VALUES = {rank: index + 2 for index, rank in enumerate(RANKS)}  # 2 is lowest, Ace (14) is highest


class Deck:
    """One shuffled 52-card deck. When it can't cover what's asked, a fresh shuffled deck replaces it, like the original"""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.cards: list[Card] = []

    def __len__(self) -> int:
        return len(self.cards)

    def fresh(self) -> None:
        self.cards = [(rank, suit) for suit in SUITS for rank in RANKS]
        self.rng.shuffle(self.cards)

    def ensure(self, count: int) -> None:
        if len(self.cards) < count:
            self.fresh()

    def draw(self) -> Card:
        self.ensure(1)
        return self.cards.pop()

    def burn(self, count: int) -> None:
        self.ensure(count)
        del self.cards[-count:]


def card_value(card: Card) -> int:
    """A card's Blackjack value, counting an Ace as 1"""
    rank = card[0]
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 1
    return int(rank)


def hand_total(hand: list[Card]) -> int:
    """A Blackjack hand's total: one Ace counts as 11 when that keeps the total at 21 or less"""
    total = sum(card_value(card) for card in hand)
    if any(card[0] == "A" for card in hand) and total <= 11:
        total += 10
    return total


def war_value(card: Card) -> int:
    return WAR_VALUES[card[0]]
