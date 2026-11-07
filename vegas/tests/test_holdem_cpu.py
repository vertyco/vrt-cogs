import random
import statistics
import time

from vegas.common.games import holdem_cpu
from vegas.common.games.cards import RANKS, SUITS
from vegas.common.games.holdem import Legal
from vegas.common.games.holdem_cpu import TRIALS, Spot, choose, preflop_score, strength

SUIT_NAMES = {"c": "clubs", "d": "diamonds", "h": "hearts", "s": "spades"}


def cards(text):  # "As Kh" -> [("A", "spades"), ("K", "hearts")]
    return tuple(("10" if part[0] == "T" else part[0], SUIT_NAMES[part[1]]) for part in text.split())


def spot(hole, board="", legal=None, pot=150, big=20, opponents=1, street=None, bet=0):
    board = cards(board) if board else ()
    street = street or {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)]
    legal = legal or Legal(fold=False, check=True, call=0, min_to=20, max_to=2000)
    return Spot(cards(hole), board, legal, pot, big, opponents, street, bet)


def test_preflop_score_orders_hands():
    assert preflop_score(cards("As Ah")) == 20
    assert preflop_score(cards("As Ks")) > preflop_score(cards("As Kh")) > preflop_score(cards("As Qh"))
    assert preflop_score(cards("7s 2h")) < 0


def test_strength_is_sensible():
    rng = random.Random(1)
    assert strength(cards("As Ah"), (), 1, rng) > 0.8
    assert strength(cards("7s 2h"), (), 1, rng) < 0.45
    assert strength(cards("As Ks"), cards("Qs Js Ts"), 1, rng) > 0.99


def test_every_choice_is_legal_over_many_random_spots(monkeypatch):
    monkeypatch.setattr(holdem_cpu, "strength", lambda hole, board, opponents, rng, trials=0: rng.random())
    rng = random.Random(7)
    deck = [(r, s) for r in RANKS for s in SUITS]
    for _ in range(2000):
        drawn = rng.sample(deck, 7)
        board = tuple(drawn[2 : 2 + rng.choice([0, 3, 4, 5])])
        street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)]
        call = rng.choice([0, 0, 10, 40, 300, 5000])
        can_raise = rng.random() < 0.8
        min_to = rng.randint(20, 200) if can_raise else None
        legal = Legal(
            fold=call > 0,
            check=call == 0,
            call=call,
            min_to=min_to,
            max_to=min_to + rng.randint(0, 3000) if can_raise else None,
        )
        s = Spot((drawn[0], drawn[1]), board, legal, rng.randint(30, 4000), 20, rng.randint(1, 3), street)
        action = choose(s, rng)
        assert action.move in legal.moves()
        if action.move == "raise":
            assert legal.min_to <= action.amount <= legal.max_to


def test_aces_raise_before_the_flop():
    legal = Legal(fold=True, check=False, call=20, min_to=40, max_to=2000)
    raises = sum(choose(spot("As Ah", legal=legal, pot=30), random.Random(i)).move == "raise" for i in range(200))
    assert raises >= 180


def test_seven_deuce_folds_to_a_pot_sized_raise():
    legal = Legal(fold=True, check=False, call=100, min_to=200, max_to=2000)
    folds = sum(choose(spot("7s 2h", legal=legal, pot=130), random.Random(i)).move == "fold" for i in range(200))
    assert folds >= 190


def test_a_royal_flush_never_folds():
    legal = Legal(fold=True, check=False, call=500, min_to=1000, max_to=2000)
    for i in range(100):
        s = spot("As Ks", "Qs Js Ts", legal=legal, pot=800, opponents=3)
        assert choose(s, random.Random(i)).move != "fold"


def test_bluffs_happen_but_rarely():
    bets = 0
    for i in range(1000):
        board = "2d 7c 9h" if i % 2 else "2d 7c 9h Kd"
        if choose(spot("3s 4h", board), random.Random(i)).move == "raise":
            bets += 1
    assert 30 <= bets <= 200


def test_a_decision_takes_under_50_ms():
    legal = Legal(fold=True, check=False, call=40, min_to=80, max_to=2000)
    s = spot("Ks Qh", "Jd 9c 2s", legal=legal, opponents=3)
    times = []
    for i in range(7):
        start = time.perf_counter()
        choose(s, random.Random(i))
        times.append(time.perf_counter() - start)
    assert statistics.median(times) < 0.05, (TRIALS, times)


def test_raise_sizing_counts_the_cpus_own_bet():
    legal = Legal(fold=True, check=False, call=40, min_to=80, max_to=5000)
    raised = 0
    for i in range(50):
        action = choose(spot("As Ah", legal=legal, pot=100, bet=20), random.Random(i))
        if action.move == "raise":
            raised += 1
            assert action.amount >= 20 + 40 + 0.5 * (100 + 40)
    assert raised > 0
