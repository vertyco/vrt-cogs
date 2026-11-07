import random

import pytest

from vegas.common.games.holdem import (
    CUT_CAP_BLINDS,
    SEAT_COUNT,
    Action,
    Hand,
    Pot,
    blinds,
    positions,
    settle,
)
from vegas.common.games.poker import HIGH_CARD, PAIR, HandRank


def deal(stacks, last_button=None, small=10, big=20, posts=()):
    """A hand for the seats in `stacks`. With seats 0, 1, 2 and no last button: button 0, small 1, big 2"""
    spots = positions(list(stacks), [], last_button)
    return Hand(stacks, spots, small, big, posts)


def act(hand, *moves):
    """Plays moves like "call" or "raise 60" for whoever is to act, in order"""
    for move in moves:
        name, _, amount = move.partition(" ")
        hand.apply(hand.to_act, Action(name, int(amount or 0)))


def heads_up_all_in(stack):
    """Button 1 and big blind 3 each start with `stack`, see the flop, then both go all in"""
    hand = deal({1: stack, 3: stack}, last_button=3)
    act(hand, "call", "check")
    hand.next_street()
    act(hand, f"raise {stack - 20}", "call")
    return hand


def test_blinds_come_from_the_max_buy_in():
    assert blinds(2000) == (10, 20) and blinds(10000) == (50, 100) and blinds(200) == (1, 2) and blinds(250) == (1, 2)


def test_three_players_button_moves_clockwise_and_blinds_follow():
    p = positions([0, 2, 4], [], last_button=0)
    assert (p.button, p.small, p.big, p.dealt) == (2, 4, 0, (4, 0, 2))


def test_the_first_button_is_the_lowest_seat_and_it_wraps_past_seat_5():
    p = positions([1, 3, 5], [], last_button=None)
    assert (p.button, p.small, p.big, p.dealt) == (1, 3, 5, (3, 5, 1))
    p = positions([1, 3, 5], [], last_button=5)
    assert (p.button, p.small, p.big) == (1, 3, 5)


def test_heads_up_the_button_posts_the_small_blind():
    p = positions([1, 3], [], last_button=3)
    assert (p.button, p.small, p.big) == (1, 1, 3)
    assert p.dealt == (3, 1) and p.joined == frozenset()


def test_a_waiting_player_joins_when_the_big_blind_reaches_them():
    p = positions([0, 2], [3], last_button=2)  # button 0, small 2, next seat after 2 is waiting seat 3
    assert p.big == 3 and p.joined == frozenset({3}) and set(p.dealt) == {0, 2, 3}
    assert (p.button, p.small) == (0, 2)


def test_a_waiting_player_elsewhere_keeps_waiting():
    p = positions([0, 2, 4], [1], last_button=0)  # button 2, small 4, big 0: seat 1 not reached
    assert 1 not in p.dealt and p.joined == frozenset()
    assert (p.button, p.small, p.big) == (2, 4, 0)


def test_with_one_active_seat_waiting_seats_join_at_once():
    p = positions([0], [3, 5], last_button=None)
    assert set(p.dealt) == {0, 3, 5} and p.joined == frozenset({3, 5})


def test_no_hand_without_two_seats():
    assert positions([2], [], last_button=None) is None
    assert positions([], [4], last_button=1) is None
    assert positions([], [], last_button=None) is None


def test_preflop_order_and_the_big_blinds_option():
    hand = deal({0: 1000, 1: 1000, 2: 1000})  # button 0, small 1, big 2
    assert hand.posted == [(1, "small", 10), (2, "big", 20)]
    assert hand.street == "preflop" and hand.current == 20 and not hand.saw_flop
    assert hand.to_act == 0  # the seat after the big blind
    hand.apply(0, Action("call"))
    assert hand.to_act == 1
    hand.apply(1, Action("call"))
    assert hand.to_act == 2 and not hand.round_over
    legal = hand.legal(2)  # everyone called: the big blind still has the option
    assert legal.moves() == ("check", "raise") and legal.call == 0 and legal.min_to == 40 and legal.max_to == 1000
    hand.apply(2, Action("check"))
    assert hand.round_over and hand.to_act is None and hand.pot_total == 60


def test_heads_up_the_button_acts_first_before_the_flop_and_last_after_it():
    hand = deal({1: 500, 3: 500}, last_button=3)  # button 1 posts the small blind
    assert hand.posted == [(1, "small", 10), (3, "big", 20)]
    assert hand.to_act == 1
    act(hand, "call")
    assert hand.to_act == 3
    act(hand, "check")
    hand.next_street()
    assert hand.to_act == 3
    act(hand, "check")
    assert hand.to_act == 1


def test_after_the_flop_the_first_seat_after_the_button_acts_and_folded_or_all_in_seats_are_skipped():
    hand = deal({0: 1000, 1: 1000, 2: 1000, 3: 50})  # button 0, small 1, big 2: seat 3 acts first
    act(hand, "raise 50", "call", "fold", "call")  # 3 all in, 0 calls, 1 folds, 2 calls
    assert hand.round_over
    assert hand.next_street() == "flop" and hand.saw_flop
    assert hand.current == 0 and hand.min_raise == 20
    assert all(player.bet == 0 and not player.acted for player in hand.players.values())
    assert hand.to_act == 2  # seat 1 folded
    act(hand, "check")
    assert hand.to_act == 0  # seat 3 is all in
    assert hand.contenders == [2, 3, 0]


def test_next_street_needs_the_round_over_and_stops_after_the_river():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    with pytest.raises(ValueError):
        hand.next_street()
    act(hand, "call", "call", "check")
    streets = []
    for _ in range(3):
        streets.append(hand.next_street())
        act(hand, "check", "check", "check")
    assert streets == ["flop", "turn", "river"] and hand.round_over
    with pytest.raises(ValueError):
        hand.next_street()


def test_next_street_needs_two_players_still_in():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    act(hand, "fold", "fold")  # everyone folds to the big blind
    assert hand.contenders == [2] and hand.round_over and hand.returned == (2, 10)
    with pytest.raises(ValueError):
        hand.next_street()
    assert not hand.saw_flop


def test_a_short_stack_posts_what_it_has_and_is_all_in():
    hand = deal({0: 1000, 1: 6, 2: 15})
    assert hand.posted == [(1, "small", 6), (2, "big", 15)]
    assert hand.players[1].all_in and hand.players[2].all_in
    assert hand.players[2].total == 15 and hand.current == 15


def test_a_post_is_a_live_big_blind_that_still_gets_its_turn():
    hand = deal({0: 1000, 1: 1000, 2: 1000, 3: 1000}, posts=[3, 1])  # seat 1 is the small blind: no extra post
    assert hand.posted == [(1, "small", 10), (2, "big", 20), (3, "post", 20)]
    assert hand.to_act == 3 and not hand.players[3].acted
    assert hand.legal(3).moves() == ("check", "raise")


def test_a_raise_must_be_at_least_the_last_raise():
    hand = deal({0: 1000, 1: 1000, 2: 1000})  # blinds 10/20
    assert hand.legal(0).min_to == 40
    act(hand, "raise 60")  # a 40 raise
    assert hand.min_raise == 40 and hand.legal(1).min_to == 100
    with pytest.raises(ValueError):
        hand.apply(1, Action("raise", 99))
    act(hand, "raise 100")
    assert hand.legal(2).min_to == 140


def test_a_stack_too_short_for_a_full_raise_may_only_raise_all_in():
    hand = deal({0: 1000, 1: 150, 2: 1000})
    act(hand, "raise 100")  # a full raise to 180 needs more than seat 1's 150
    legal = hand.legal(1)
    assert legal.min_to == legal.max_to == 150 and legal.call == 90


def test_a_short_all_in_does_not_reopen_raising_for_those_who_acted():
    # A is seat 1, B seat 2, C seat 3 (150 left after the first round), D seat 0 on the button
    hand = deal({0: 1000, 1: 1000, 2: 1000, 3: 170})
    act(hand, "call", "call", "call", "check")
    hand.next_street()
    act(hand, "raise 100", "call")  # A bets 100, B calls
    assert hand.legal(3).min_to == hand.legal(3).max_to == 150
    act(hand, "raise 150")  # C all in for 150, short of a full raise to 200
    assert hand.current == 150 and hand.min_raise == 100
    assert hand.legal(0).min_to == 250  # D has not acted yet: may still raise, by at least the last full raise
    act(hand, "call")
    for seat in (1, 2):
        assert hand.to_act == seat
        legal = hand.legal(seat)
        assert legal.moves() == ("fold", "call") and legal.call == 50 and legal.min_to is None and legal.max_to is None
        act(hand, "call")
    assert hand.round_over


def test_a_full_raise_reopens_raising_for_everyone():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    act(hand, "call", "call", "check")
    hand.next_street()
    act(hand, "raise 40", "call", "raise 120")  # seat 1 bets, seat 2 calls, seat 0 raises by 80
    assert hand.to_act == 1 and hand.legal(1).min_to == 200
    act(hand, "call")
    assert hand.to_act == 2 and hand.legal(2).min_to == 200


def test_folding_is_only_offered_when_there_is_something_to_call():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    legal = hand.legal(0)
    assert legal.fold and not legal.check and legal.call == 20 and legal.moves() == ("fold", "call", "raise")
    act(hand, "call", "call")
    legal = hand.legal(2)
    assert not legal.fold and legal.check and "fold" not in legal.moves()
    act(hand, "check")
    hand.next_street()
    legal = hand.legal(1)
    assert legal.moves() == ("check", "raise") and legal.min_to == 20  # a first bet is at least one big blind
    act(hand, "raise 20")
    assert hand.legal(2).moves() == ("fold", "call", "raise")
    # Nor played: a free check is never folded, so every slice of the pot keeps someone who can win it
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    act(hand, "call", "call")
    with pytest.raises(ValueError):
        hand.apply(2, Action("fold"))


def test_a_call_is_capped_at_the_stack_and_nobody_raises_against_only_all_in_players():
    hand = deal({1: 1000, 3: 100}, last_button=3)  # button 1, big blind 3
    act(hand, "raise 500")
    legal = hand.legal(3)
    assert legal.moves() == ("fold", "call") and legal.call == 80
    hand = deal({1: 300, 3: 1000}, last_button=3)
    act(hand, "raise 300")  # the button is all in
    legal = hand.legal(3)
    assert legal.moves() == ("fold", "call") and legal.call == 280 and legal.min_to is None
    act(hand, "call")
    assert hand.round_over and hand.betting_done


def test_side_pots_split_by_how_much_each_player_could_match():
    hand = deal({0: 1000, 1: 100, 2: 300})  # C is seat 0 on the button, A seat 1, B seat 2
    act(hand, "raise 300", "call", "call")  # C raises to 300, A calls all in for 100, B calls all in for 300
    assert [hand.players[seat].total for seat in (1, 2, 0)] == [100, 300, 300]
    assert hand.pots() == [Pot(300, (1, 2, 0)), Pot(400, (2, 0))]
    assert hand.pot_total == 700 and hand.round_over and hand.betting_done
    for _ in range(3):
        hand.next_street()
    ranks = {1: HandRank(PAIR, (14,)), 2: HandRank(PAIR, (9,)), 0: HandRank(HIGH_CARD, (13,))}
    awards, final = settle(hand, ranks, 5, button=0)
    assert [(award.winners, award.cut, award.shares) for award in awards] == [
        ((1,), 15, {1: 285}),
        ((2,), 20, {2: 380}),
    ]
    assert final == {1: 285, 2: 380, 0: 700}


def test_an_uncalled_bet_comes_back_uncut():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    act(hand, "call", "call", "check")
    hand.next_street()
    assert hand.returned is None
    act(hand, "raise 100", "fold")
    assert hand.returned is None and hand.players[1].bet == 100  # the round is still open
    act(hand, "fold")  # seat 1 bet 100 and both others folded
    assert hand.contenders == [1] and hand.round_over and not hand.betting_done
    assert hand.returned == (1, 100) and hand.players[1].bet == 0 and hand.current == 0
    assert hand.stacks() == {1: 980, 2: 980, 0: 980} and hand.pot_total == 60
    assert hand.pots() == [Pot(60, (1,))]
    awards, final = settle(hand, {}, 5, button=0)
    assert [(award.cut, award.shares) for award in awards] == [(3, {1: 57})]
    assert final == {1: 1037, 2: 980, 0: 980}


def test_a_shove_over_smaller_all_ins_gets_its_unmatched_chips_back_when_the_round_ends():
    hand = deal({0: 2000, 1: 300, 2: 500})  # button 0, small 1, big 2
    act(hand, "raise 1000", "call", "call")  # seat 0 shoves 1000; seats 1 and 2 call all in for 300 and 500
    assert hand.returned == (0, 500)
    assert hand.players[0].bet == hand.players[0].total == hand.current == 500
    assert hand.stacks() == {1: 0, 2: 0, 0: 1500} and not hand.players[0].all_in
    assert hand.pots() == [Pot(900, (1, 2, 0)), Pot(400, (2, 0))] and hand.pot_total == 1300
    assert hand.betting_done

    hand = deal({1: 1000, 3: 300}, last_button=3)  # heads-up: the button shoves 1000, the big blind matches 300
    act(hand, "raise 1000", "call")
    assert hand.returned == (1, 700) and hand.stacks() == {3: 0, 1: 700} and not hand.players[1].all_in
    assert hand.pots() == [Pot(600, (3, 1))] and hand.betting_done


def test_a_big_blind_nobody_can_match_comes_back_at_once():
    hand = deal({1: 6, 3: 1000}, last_button=3)  # heads-up: the button's small blind is all in for 6
    assert hand.posted == [(1, "small", 6), (3, "big", 20)]
    assert hand.round_over and hand.betting_done and hand.returned == (3, 14)
    assert hand.stacks() == {3: 994, 1: 0} and hand.pots() == [Pot(12, (3, 1))]


def test_the_cut_is_5_percent_capped_at_3_big_blinds_and_never_before_the_flop():
    ranks = {1: HandRank(PAIR, (9,)), 3: HandRank(HIGH_CARD, (14,))}
    awards, final = settle(heads_up_all_in(500), ranks, 5, button=1)  # big blind 20, flop seen, a 1000 pot
    assert [award.cut for award in awards] == [50] and final == {1: 950, 3: 0}
    awards, final = settle(heads_up_all_in(1000), ranks, 5, button=1)  # a 2000 pot
    assert [award.cut for award in awards] == [CUT_CAP_BLINDS * 20] == [60] and final == {1: 1940, 3: 0}
    awards, final = settle(heads_up_all_in(500), ranks, 0, button=1)
    assert [award.cut for award in awards] == [0] and final == {1: 1000, 3: 0}
    awards, final = settle(heads_up_all_in(1250), ranks, 2.28, button=1)  # exactly 57, where float math floors to 56
    assert [award.cut for award in awards] == [57]

    hand = deal({0: 1000, 1: 1000, 2: 1000})
    act(hand, "raise 60", "fold", "fold")  # everyone folds to a raise before the flop
    assert hand.returned == (0, 40)
    with pytest.raises(ValueError):
        hand.next_street()  # the hand is over: no flop for it, so nothing for the casino
    assert not hand.saw_flop and hand.street == "preflop"
    awards, final = settle(hand, {}, 5, button=0)
    assert sum(award.cut for award in awards) == 0 and final == {0: 1030, 1: 990, 2: 980}


def test_the_cut_is_shared_across_side_pots_by_size_with_the_leftover_from_the_first():
    hand = deal({0: 1000, 1: 70, 2: 1000})
    act(hand, "call", "call", "check")
    hand.next_street()
    act(hand, "raise 50", "call", "call")  # seat 1 all in: totals 70, 70, 70
    hand.next_street()
    act(hand, "raise 330", "call")  # seats 2 and 0 add 330 each: a 210 main pot and a 660 side pot
    assert hand.pots() == [Pot(210, (1, 2, 0)), Pot(660, (2, 0))]
    hand.next_street()
    act(hand, "check", "check")
    ranks = {1: HandRank(PAIR, (5,)), 2: HandRank(PAIR, (4,)), 0: HandRank(PAIR, (3,))}
    awards, final = settle(hand, ranks, 5, button=0)  # 5% of 870 is 43: 10 and 32 by size, the leftover 1 from the main
    assert [award.cut for award in awards] == [11, 32]
    assert final == {1: 199, 2: 600 + 628, 0: 600}


def test_a_split_pot_gives_the_odd_chip_to_the_first_winner_after_the_button():
    hand = deal({0: 1000, 1: 1000, 2: 1000}, small=5, big=10)  # button 0, small 1, big 2
    act(hand, "call", "fold", "check")  # a 25 pot: 10 + 10 + the small blind's dead 5
    tie = HandRank(PAIR, (7, 14, 9, 3))
    same = HandRank(PAIR, (7, 14, 9, 3), (("7", "spades"),))
    awards, final = settle(hand, {0: tie, 2: same}, 0, button=0)
    assert len(awards) == 1 and awards[0].winners == (2, 0) and awards[0].shares == {2: 13, 0: 12}
    assert final == {0: 1002, 1: 995, 2: 1003}


def test_illegal_actions_raise_value_error():
    hand = deal({0: 1000, 1: 1000, 2: 1000})  # seat 0 acts first
    bad = [
        (1, Action("call")),  # out of turn
        (0, Action("raise", 39)),  # below min_to 40
        (0, Action("raise", 1001)),  # above max_to, the whole stack
        (0, Action("check")),  # facing the big blind
        (0, Action("raise", True)),
        (0, Action("raise", "60")),
        (0, Action("double")),
    ]
    for seat, action in bad:
        with pytest.raises(ValueError):
            hand.apply(seat, action)
    assert hand.to_act == 0 and hand.current == 20 and hand.stacks() == {1: 990, 2: 980, 0: 1000}
    act(hand, "call", "call", "check")
    with pytest.raises(ValueError):
        hand.apply(0, Action("check"))  # the round is over: nobody is to act


def test_apply_returns_the_action_as_applied():
    hand = deal({0: 1000, 1: 1000, 2: 1000})
    assert hand.apply(0, Action("raise", 60)) == Action("raise", 60)
    assert hand.apply(1, Action("call", 999)) == Action("call", 0)
    assert hand.apply(2, Action("fold")) == Action("fold", 0)


def assert_nothing_uncalled(hand):
    """Once a betting round ends, the biggest total in the hand is matched by someone: no lone chips wait for settle"""
    totals = sorted(player.total for player in hand.players.values())
    assert totals[-1] == totals[-2]


def play_randomly(rng):
    """A random legal hand to the end. Returns the starting stacks, the awards and the final stacks"""
    seats = rng.sample(range(SEAT_COUNT), rng.randint(2, SEAT_COUNT))
    stacks = {seat: rng.choice([rng.randint(1, 40), rng.randint(1, 600)]) for seat in seats}
    spots = positions(seats, [], rng.choice([None, *range(SEAT_COUNT)]))
    small, big = rng.choice([(1, 2), (5, 10), (10, 20)])
    hand = Hand(stacks, spots, small, big, rng.sample(seats, rng.randint(0, 2)))
    while len(hand.contenders) > 1:
        seat = hand.to_act
        if seat is None:
            assert_nothing_uncalled(hand)
            if hand.street == "river":
                break
            hand.next_street()
            assert hand.returned is None
            continue
        legal = hand.legal(seat)
        move = rng.choice(legal.moves())
        hand.apply(seat, Action(move, rng.randint(legal.min_to, legal.max_to) if move == "raise" else 0))
    assert_nothing_uncalled(hand)
    assert hand.pot_total == sum(pot.amount for pot in hand.pots())
    ranks = {seat: HandRank(rng.randint(0, 1), (rng.randint(2, 3),)) for seat in hand.contenders}
    awards, final = settle(hand, ranks, rng.choice([0, 5, 12.5, 20]), spots.button)
    return hand, stacks, awards, final


def test_chips_are_kept_exactly_minus_the_cut():
    rng = random.Random(7)
    for _ in range(2000):
        hand, stacks, awards, final = play_randomly(rng)
        assert sum(final.values()) + sum(award.cut for award in awards) == sum(stacks.values())
        assert set(final) == set(stacks) and min(final.values()) >= 0
        for award in awards:
            assert sum(award.shares.values()) + award.cut == award.pot.amount
            assert min(award.shares.values()) >= 0 and award.cut >= 0
            assert set(award.winners) <= set(award.pot.eligible) and set(award.shares) == set(award.winners)
        assert sum(award.cut for award in awards) <= CUT_CAP_BLINDS * hand.big
        if not hand.saw_flop:
            assert sum(award.cut for award in awards) == 0
