"""The spec's appendix A: what each game pays back on average with the default multipliers, by simulation"""

import random

from casino.common.games import blackjack, simple
from casino.common.games.cards import Deck, hand_total, war_value

ROUNDS = 60_000


def average(play) -> float:
    rng = random.Random(42)
    return sum(play(rng) for _ in range(ROUNDS)) / ROUNDS


def test_quick_games_pay_back_what_the_spec_says():
    assert abs(average(lambda r: 1.5 * (simple.flip(r) == "heads")) - 0.75) < 0.02
    assert abs(average(lambda r: 1.8 * (simple.hide_coin(r) == 1)) - 0.60) < 0.02
    assert abs(average(lambda r: 1.8 * simple.dice_wins(simple.roll(r))) - 0.50) < 0.02
    assert abs(average(lambda r: 1.7 * simple.hilo_factor("low", simple.roll(r))) - 0.71) < 0.02
    assert abs(average(lambda r: 1.7 * simple.hilo_factor("seven", simple.roll(r))) - 1.42) < 0.05
    assert abs(average(lambda r: 2 * (simple.allin_wins(r, 2))) - 0.50) < 0.02


def test_craps_pays_back_about_126():
    """Come-out wins by simulation, plus the point's one extra roll worked out exactly"""

    def come_out(rng):
        result, factor = simple.craps_come_out(sum(simple.roll(rng)))
        return 2.0 * factor if result == "win" else 0.0

    # A point of 4, 5, 6, 8, 9 or 10 comes up 3, 4, 5, 5, 4 or 3 ways in 36, and must come up again on one roll
    point_part = sum((ways / 36) ** 2 * 2.0 for ways in (3, 4, 5, 5, 4, 3))
    assert abs(average(come_out) + point_part - 1.265) < 0.03


def war(rng) -> float:
    deck = Deck(rng)
    mine, dealer = deck.draw(), deck.draw()
    if war_value(mine) > war_value(dealer):
        return 1.5
    if war_value(mine) < war_value(dealer):
        return 0.0
    deck.burn(3)
    # Going to war stakes a second bet: a win pays 1.5 on the first and returns the second
    return (2.5 if war_value(deck.draw()) >= war_value(deck.draw()) else 0.0) - 1.0


def test_war_pays_back_about_73():
    assert abs(average(war) - 0.73) < 0.02


def blackjack_round(rng) -> float:
    """A simple fixed strategy: hit below 12, stand on 17 or more, and in between stand when the dealer shows 2-6"""
    deck = Deck(rng)
    deck.fresh()
    mine = [deck.draw(), deck.draw()]
    dealer = [deck.draw(), deck.draw()]
    shows = min(hand_total([dealer[0]]), 10)
    while hand_total(mine) < 21:
        total = hand_total(mine)
        if total >= 17 or (total >= 12 and 2 <= shows <= 6):
            break
        mine.append(deck.draw())
    blackjack.dealer_play(dealer, deck)
    outcome = blackjack.outcome(mine, dealer)
    return {"win": 2.0, "push": 1.0}.get(outcome, 0.0)


def test_blackjack_pays_back_close_to_even():
    measured = average(blackjack_round)
    print(f"Blackjack average return per 100 credits: {measured * 100:.1f}")
    assert 0.9 < measured < 1.1
