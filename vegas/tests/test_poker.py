from vegas.common.games.poker import VALUES, HandRank, best_hand, describe, hand_name

SUIT_NAMES = {"c": "clubs", "d": "diamonds", "h": "hearts", "s": "spades"}


def c(text):  # "As" -> ("A", "spades"), "Th" -> ("10", "hearts")
    rank = "10" if text[0] == "T" else text[0]
    return (rank, SUIT_NAMES[text[1]])


def cards(text):
    return [c(part) for part in text.split()]


def test_values():
    assert VALUES["2"] == 2 and VALUES["10"] == 10 and VALUES["A"] == 14


def test_every_category_ranks_above_the_one_below():
    ladder = [
        "Ah Kd 9c 6s 3d",  # high card
        "Ah Ad 9c 6s 3d",  # pair
        "Ah Ad 9c 9s 3d",  # two pair
        "Ah Ad Ac 6s 3d",  # trips
        "5h 6d 7c 8s 9d",  # straight
        "Ah 9h 6h 3h 2h",  # flush
        "Ah Ad Ac 6s 6d",  # full house
        "Ah Ad Ac As 3d",  # quads
        "9s 8s 7s 6s 5s",  # straight flush
    ]
    ranks = [best_hand(cards(hand)) for hand in ladder]
    assert [r.category for r in ranks] == list(range(9))
    for low, high in zip(ranks, ranks[1:]):
        assert high > low
        assert isinstance(high, HandRank)


def test_the_wheel_is_a_five_high_straight():
    assert best_hand(cards("As 2d 3c 4h 5s Kd Qc")).tiebreak == (5,)
    assert hand_name(best_hand(cards("As 2d 3c 4h 5s Kd Qc"))) == "Straight, 5 high"


def test_kickers_break_ties_and_equal_hands_tie():
    assert best_hand(cards("Ah Ad Kc 9s 4d 3c 2h")) > best_hand(cards("As Ac Qc 9d 4s 3d 2c"))
    assert best_hand(cards("Ah Kd Qc Js 9d")) == best_hand(cards("As Kc Qd Jh 9c"))


def test_the_best_five_of_seven_are_returned():
    assert set(best_hand(cards("2c 3c 4c 5c 6c Ac Kd")).cards) == set(cards("2c 3c 4c 5c 6c"))


def test_names():
    assert describe(cards("7h 7d")) == "Pair of 7s"
    assert describe(cards("Ah 9d")) == "High card, Ace"
    assert describe(cards("Kh Kd 4c 4s 9d")) == "Two pair, Kings and 4s"
    assert describe(cards("Kh Kd Kc 4s 4d")) == "Full house, Kings over 4s"
    assert describe(cards("Ah 9h 6h 3h 2h")) == "Flush, Ace high"
    assert describe(cards("Ah Kh Qh Jh Th")) == "Royal flush"
    assert describe(cards("9s 8s 7s 6s 5s")) == "Straight flush, 9 high"
    assert describe(cards("Qh Qd Qc Qs 2d")) == "Four of a kind, Queens"
    assert describe(cards("Th Td Tc 3s 2d")) == "Three of a kind, 10s"
    assert describe(cards("Ah Ad")) == "Pair of Aces"
    assert describe(cards("Ah 5s 7d 9c Kd 2h 3c")) == "High card, Ace"
