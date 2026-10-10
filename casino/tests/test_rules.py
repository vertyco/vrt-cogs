import random

from casino.common.games import blackjack, simple
from casino.common.games.cards import Deck, hand_total, war_value


def cards(*ranks):
    return [(rank, "spades") for rank in ranks]


class StackedDeck(Deck):
    """Draws the given cards in order"""

    def __init__(self, *ranks):
        super().__init__(random.Random(1))
        self.cards = list(reversed(cards(*ranks)))


def test_aces_count_eleven_only_when_that_stays_at_21_or_less():
    assert hand_total(cards("A", "K")) == 21
    assert hand_total(cards("A", "5", "K")) == 16
    assert hand_total(cards("A", "A", "9")) == 21
    assert hand_total(cards("Q", "J", "2")) == 22


def test_a_deck_has_52_different_cards_and_replaces_itself_when_short():
    deck = Deck(random.Random(3))
    drawn = {deck.draw() for _ in range(52)}
    assert len(drawn) == 52
    deck.draw()
    assert len(deck) == 51
    deck.burn(3)
    assert len(deck) == 48


def test_war_values_rank_aces_highest():
    assert war_value(("A", "clubs")) == 14 and war_value(("K", "clubs")) == 13 and war_value(("2", "clubs")) == 2


def test_the_dealer_takes_a_card_with_any_ace_that_isnt_21_then_draws_to_17():
    hand = cards("A", "8")  # soft 19: the house rule still draws once
    drawn = blackjack.dealer_play(hand, StackedDeck("2"))
    assert drawn == cards("2") and hand_total(hand) == 21
    hand = cards("A", "K")
    assert blackjack.dealer_play(hand, StackedDeck("5")) == []
    hand = cards("10", "6")
    assert blackjack.dealer_play(hand, StackedDeck("3", "9")) == cards("3")


def test_blackjack_outcomes_follow_the_originals_order():
    assert blackjack.outcome(cards("10", "9"), cards("10", "7")) == "win"
    assert blackjack.outcome(cards("10", "5"), cards("10", "6", "K")) == "win"
    assert blackjack.outcome(cards("10", "6", "K"), cards("10", "6", "K")) == "bust"
    assert blackjack.outcome(cards("10", "8"), cards("9", "9")) == "push"
    assert blackjack.outcome(cards("10", "7"), cards("10", "8")) == "lose"


def test_all_in_wins_one_time_in_multiplier_plus_two():
    rng = random.Random(5)
    wins = sum(simple.allin_wins(rng, 2) for _ in range(40000))
    assert abs(wins / 40000 - 1 / 4) < 0.01


def test_hilo_pays_five_times_for_a_right_seven():
    assert simple.hilo_factor("seven", (3, 4)) == 5
    assert simple.hilo_factor("low", (3, 3)) == 1
    assert simple.hilo_factor("high", (3, 4)) == 0
    assert simple.hilo_factor("high", (6, 6)) == 1


def test_dice_win_on_2_7_11_and_12():
    assert [total for total in range(2, 13) if simple.dice_wins((1, total - 1))] == [2, 7, 11, 12]


def test_craps_come_out():
    assert simple.craps_come_out(7) == ("win", 3)
    assert simple.craps_come_out(11) == ("win", 1)
    assert [simple.craps_come_out(t)[0] for t in (2, 3, 12)] == ["lose"] * 3
    assert simple.craps_come_out(8) == ("point", 0)
