"""Blackjack's rules: the dealer's house rule and how a hand ends"""

from .cards import Card, Deck, hand_total


def dealer_play(hand: list[Card], deck: Deck) -> list[Card]:
    """The cards the dealer draws, added to hand. The original's house rule: a hand holding an Ace that isn't 21
    takes one card, then the dealer draws while under 17"""
    drawn = []
    if any(card[0] == "A" for card in hand) and hand_total(hand) != 21:
        drawn.append(deck.draw())
        hand.append(drawn[-1])
    while hand_total(hand) < 17:
        drawn.append(deck.draw())
        hand.append(drawn[-1])
    return drawn


def outcome(player: list[Card], dealer: list[Card]) -> str:
    """win, bust, push or lose, checked in the original's order"""
    pc, dc = hand_total(player), hand_total(dealer)
    if dc > 21 >= pc or dc < pc <= 21:
        return "win"
    if pc > 21:
        return "bust"
    if dc == pc <= 21:
        return "push"
    return "lose"
