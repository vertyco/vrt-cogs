"""Hold'em's comings and goings: practice turning into a real game, the card-room rules, topping up, standing up,
timeouts, leaving, closing, and saved stacks coming back after a crash. Credits are never lost or paid twice"""

import asyncio
import logging
import threading

import pytest

from vegas.common.holdem_seats import lapse, return_stacks
from vegas.common.holdem_table import PRACTICE_BLINDS
from vegas.common.memberships import Updater
from vegas.common.money import Money
from vegas.common.table import DECISION_TIME
from vegas.main import Vegas
from vegas.tests.fakes import GUILD_ID, Clock, FakeBank, FakeBot, FakeConn, FakeGuild, member
from vegas.tests.tables_kit import autoplay, hand_over, keep_playing, open_turn, round_over, time_out, until
from vegas.tests.test_holdem_table import (
    BIG,
    CALL,
    CHECK,
    FOLD,
    HEADS_UP,
    PRACTICE,
    acts,
    balance,
    deal_from,
    folds,
    hands_of,
    played,
)

RAISE = {"move": "raise", "amount": 200}
CLOSED = "Texas Hold'em closed, so your chips went back to your bank."


async def real_game(seat, *others):
    """Sam buys in at seat 0 and practices hand 1 alone with 3 CPUs. Ann buys in at seat 4 while it runs and Sam folds
    it, so hand 2 is the first real hand: heads-up, Ann on the button and small blind, Sam the big blind. Anyone in
    others is at the table, watching"""
    host, floor, table, conns = await seat("holdem", 7, 8, *others)
    sam, ann = conns[:2]
    deal_from(table, PRACTICE, HEADS_UP)
    table.choose = folds
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    await until(lambda: 7 in table.decisions)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await autoplay(table, sam, [FOLD])
    await until(lambda: table.hand_no == 2)
    return host, floor, table, conns


async def practicing(seat):
    """Sam sits free at seat 0 and his first practice hand waits on his turn"""
    host, floor, table, conns = await seat("holdem", 7, 8)
    table.choose = folds
    await table.sit(conns[0], 0)
    await until(lambda: 7 in table.decisions)
    return host, floor, table, conns


def unseated(conn) -> list[int]:
    return [e["seat"] for e in conn.of("event") if e["kind"] == "unseat"]


def dealt(events) -> set[int]:
    return {e["seat"] for e in events if e["kind"] == "pitch"}


def forced(events) -> list[tuple]:
    """The blinds and posts of one hand: (seat, move, amount)"""
    return [
        (e["seat"], e["move"], e["amount"]) for e in events if e["kind"] == "act" and e["move"] in ("blind", "post")
    ]


async def stacked(host, floor, user_id: int) -> int:
    return await host.store.stacked(await floor.scope(), user_id)


async def come_back(floor, conn) -> None:
    floor.room.members.append(conn)
    await floor.arrive(conn)
    await floor.enter(conn, "holdem")


async def walk_away(floor, conn) -> None:
    conn.drop()
    await floor.depart(conn)


@pytest.mark.asyncio
async def test_a_newcomer_buys_in_and_the_practicer_is_offered_a_seat(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    offer = sam.last("offer")
    assert {key: value for key, value in offer.items() if key != "left"} == {
        "t": "offer",
        "game": "holdem",
        "kind": "join",
        "min": 400,
        "max": 2000,
    }
    assert offer["left"] == pytest.approx(DECISION_TIME, abs=0.5)
    assert not ann.of("offer") and not table.offers[7].done()
    # The practice hand carries on, and Ann's credits wait on her seat
    assert table.mode == "practice" and table.hand_no == 1 and 7 in table.decisions
    assert table.seat_of(8).real == 1000 and await balance(host, ann) == 0
    # Another device, or a page that reloads, gets the open offer when it reaches the table
    phone = FakeConn(floor.room, sam.ctx.author, floor.guild)
    await floor.arrive(phone)
    await floor.enter(phone, "holdem")
    assert phone.last("offer")["kind"] == "join" and 0 < phone.last("offer")["left"] <= offer["left"]


@pytest.mark.asyncio
async def test_an_offer_waits_out_its_players_turn_and_starts_over_when_they_move(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    # A short decision time, so the offer would run out while Sam still thinks about his turn
    table.times["decision"] = 0.3
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await asyncio.sleep(0.6)
    # Sam is asked to move, so the offer's clock waits: his page hides the offer while his action bar is up
    assert not table.offers[7].done()
    await autoplay(table, sam, [FOLD])
    # His turn over, the offer starts over with its full time, and his page hears the new time left
    await until(lambda: len(sam.of("offer")) == 2)
    assert [offer["kind"] for offer in sam.of("offer")] == ["join", "join"]
    assert sam.last("offer")["left"] == pytest.approx(0.3, abs=0.1)
    # Unanswered, it then runs out as any offer does: Sam stands up to watch before the next hand
    await until(lambda: table.seat_of(7) is None)
    assert [offer["kind"] for offer in sam.of("offer")] == ["join", "join", None]


@pytest.mark.asyncio
async def test_an_offer_already_running_when_its_players_turn_comes_waits_for_the_move(seat):
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    gate = threading.Event()

    def held(spot, rng):
        gate.wait(5)
        return folds(spot, rng)

    table.choose = held
    try:
        await table.sit(sam, 0)
        # A CPU thinks before Sam's first turn, and Ann buys in meanwhile: the offer's short clock starts at once
        await until(lambda: table.turn is not None and table.turn != 0)
        table.times["decision"] = 0.4
        await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
        table.times["decision"] = DECISION_TIME
        gate.set()
        await until(lambda: 7 in table.decisions)
        # Sam's turn stops the running clock, so the offer outlasts the time it had left
        await asyncio.sleep(0.7)
        assert not table.offers[7].done()
        table.times["decision"] = 0.4
        await autoplay(table, sam, [FOLD])
        # His move starts it over with all its time
        await until(lambda: len(sam.of("offer")) == 2)
        assert sam.last("offer")["kind"] == "join" and sam.last("offer")["left"] == pytest.approx(0.4, abs=0.1)
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_an_offer_answered_while_it_starts_over_is_not_sent_again(seat, monkeypatch):
    host, floor, table, (sam, ann) = await practicing(seat)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    stakes, reading, release = table.stakes, asyncio.Event(), asyncio.Event()

    async def slow_stakes():
        reading.set()
        await release.wait()
        return await stakes()

    # Sam's move starts the offer over, and the stakes it reads take a while; he says no meanwhile
    monkeypatch.setattr(table, "stakes", slow_stakes)
    moved = asyncio.create_task(autoplay(table, sam, [FOLD]))
    await asyncio.wait_for(reading.wait(), 5)
    await table.decline(sam)
    release.set()
    await moved
    await until(lambda: table.hand_no == 2)
    # The offer he answered never comes back
    assert [offer["kind"] for offer in sam.of("offer")] == ["join", None]


@pytest.mark.asyncio
async def test_saying_yes_starts_the_real_game_after_the_practice_hand(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await table.buy_in(sam, {"seat": None, "amount": 900, "post": False})
    assert sam.last("offer")["kind"] is None and table.offers[7].result() is True
    assert table.seat_of(7).real == 900 and await balance(host, sam) == 100 and await stacked(host, floor, 7) == 900
    # The practice hand finishes first: the CPUs are still seated and Sam's turn is still open
    assert table.mode == "practice" and table.hand_no == 1 and 7 in table.decisions and unseated(sam) == []
    await autoplay(table, sam, [FOLD])
    await until(lambda: table.hand_no == 2 and table.turn is not None)
    # The CPUs left with unseat events, and the first real hand dealt both players with nobody waiting
    assert table.mode == "real" and sorted(unseated(sam)) == [1, 2, 3]
    assert dealt(hands_of(sam)[1]) == {0, 4} and not any(s.waiting for s in table.humans())
    assert [seat["waiting"] for seat in sam.last("table")["seats"] if seat is not None] == [False, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["no", "none"])
async def test_saying_no_stands_the_practicer_up_and_the_newcomer_practices(seat, answer):
    host, floor, table, (sam, ann) = await practicing(seat)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    if answer == "no":
        await table.decline(sam)
        assert sam.last("offer")["kind"] is None
    else:
        # The offer's time runs out, the way its timer ends it
        lapse(table.offers[7])
    # Sam plays the practice hand out first
    assert table.seat_of(7) is not None and table.hand_no == 1
    await autoplay(table, sam, [FOLD])
    await until(lambda: table.hand_no == 2)
    # Sam stood up to watch, and his offer's dialog was closed once
    assert table.seat_of(7) is None and unseated(sam) == [0] and table.is_here(7)
    assert [offer["kind"] for offer in sam.of("offer")] == ["join", None]
    assert await balance(host, sam) == 1000 and not sam.of("notice")
    # Ann practices alone with play chips while her credits wait
    ann_seat = table.seat_of(8)
    assert table.mode == "practice" and [s.number for s in table.seats if s is not None and s.cpu] == [1, 2, 3]
    assert ann_seat.real == 1000 and ann_seat.play == PRACTICE_BLINDS * BIG
    assert await balance(host, ann) == 0 and await stacked(host, floor, 8) == 1000


@pytest.mark.asyncio
async def test_a_broke_player_is_offered_a_top_up_and_stood_up_without_an_answer(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    # Ann's aces beat Sam's kings all in, so Sam has nothing left
    await autoplay(table, ann, [{"move": "raise", "amount": 1000}])
    await autoplay(table, sam, [CALL])
    await until(lambda: sam.of("offer"))
    offer = sam.last("offer")
    assert (offer["kind"], offer["min"], offer["max"]) == ("broke", 400, 2000)
    assert offer["left"] == pytest.approx(DECISION_TIME, abs=0.5)
    assert table.seat_of(7).real == 0 and await stacked(host, floor, 7) == 0
    # Sam doesn't answer before the offer's time runs out
    lapse(table.offers[7])
    await until(lambda: table.hand_no == 3)
    assert table.seat_of(7) is None and unseated(sam) == [1, 2, 3, 0] and sam.last("offer")["kind"] is None
    # Alone again, Ann practices while her 1,940 waits (the cut took 3 big blinds)
    assert table.mode == "practice" and table.seat_of(8).real == 1940
    assert await balance(host, sam) == 0 and await stacked(host, floor, 8) == 1940


@pytest.mark.asyncio
async def test_a_broke_player_who_tops_up_plays_on(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await autoplay(table, ann, [{"move": "raise", "amount": 1000}])
    await autoplay(table, sam, [CALL])
    await until(lambda: sam.of("offer"))
    await host.money.bank.deposit(sam.ctx.author, 1000)
    await table.buy_in(sam, {"seat": None, "amount": 300, "post": False})
    assert sam.last("notice")["text"] == "Buy-ins here are 400 to 2000." and table.seat_of(7).real == 0
    await table.buy_in(sam, {"seat": None, "amount": 500, "post": False})
    assert sam.last("offer")["kind"] is None
    await until(lambda: table.hand_no == 3 and table.turn is not None)
    assert table.mode == "real" and table.seat_of(7).real == 500 and await balance(host, sam) == 500
    assert await stacked(host, floor, 7) == 500 and dealt(hands_of(sam)[2]) == {0, 4}


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["top up", "none"])
async def test_a_broke_player_sits_out_while_the_others_play_on(seat, answer):
    host, floor, table, (sam, ann, bob) = await real_game(seat, 9)
    # Bob buys in and pays a big blind to play the next hand
    await table.buy_in(bob, {"seat": 2, "amount": 1000, "post": True})
    # Ann's aces beat Sam's kings all in, so Sam has nothing left
    await autoplay(table, ann, [{"move": "raise", "amount": 1000}])
    await autoplay(table, sam, [CALL])
    # Ann and Bob both have chips, so the next hand deals at once while Sam's offer to top up stays open
    await until(lambda: table.hand_no == 3 and table.turn is not None)
    assert sam.last("offer")["kind"] == "broke" and not table.offers[7].done()
    assert table.seat_of(7).real == 0 and dealt(hands_of(sam)[2]) == {2, 4}
    if answer == "top up":
        await host.money.bank.deposit(sam.ctx.author, 500)
        await table.buy_in(sam, {"seat": None, "amount": 500, "post": False})
        assert sam.last("offer")["kind"] is None and table.seat_of(7).real == 500
    else:
        lapse(table.offers[7])
    playing = [asyncio.create_task(keep_playing(table, conn)) for conn in (ann, bob)]
    try:
        await until(lambda: table.hand_no == 4 and table.turn is not None)
    finally:
        for task in playing:
            task.cancel()
    if answer == "top up":
        # Topped up, Sam is dealt in again from the next hand
        assert dealt(hands_of(sam)[3]) == {0, 2, 4} and await stacked(host, floor, 7) == 500
    else:
        # No answer: he stood up to watch before the next hand
        assert table.seat_of(7) is None and 0 in unseated(sam) and dealt(hands_of(sam)[3]) == {2, 4}


@pytest.mark.asyncio
async def test_joining_a_real_game_waits_for_the_big_blind_or_posts_one(seat):
    host, floor, table, (sam, ann, bob, dan) = await real_game(seat, 9, 10)
    await table.buy_in(bob, {"seat": 2, "amount": 1000, "post": False})
    assert table.seat_of(9).waiting and not table.seat_of(9).post and bob.last("table")["seats"][2]["waiting"]
    await autoplay(table, ann, [FOLD])
    # Hand 3: the big blind isn't at Bob's seat, so he waits while Sam and Ann play. Dan pays to play the next hand
    await until(lambda: table.hand_no == 3 and open_turn(table, 7, None))
    await table.buy_in(dan, {"seat": 3, "amount": 1000, "post": True})
    assert table.seat_of(10).post and not table.seat_of(10).waiting
    await autoplay(table, sam, [FOLD])
    # Hand 4: Dan, on the button, posts a big blind to play at once. Bob still waits
    await until(lambda: table.hand_no == 4 and open_turn(table, 10, None))
    await autoplay(table, dan, [{"move": "raise", "amount": 100}])
    await autoplay(table, ann, [FOLD])
    await autoplay(table, sam, [FOLD])
    # Hand 5: the big blind reaches Bob, and he is dealt in
    await until(lambda: table.hand_no == 5 and open_turn(table, 10, None))
    hands = hands_of(bob)
    assert dealt(hands[2]) == {0, 4} and forced(hands[2]) == [(0, "blind", 10), (4, "blind", 20)]
    assert dealt(hands[3]) == {0, 3, 4}
    assert forced(hands[3]) == [(4, "blind", 10), (0, "blind", 20), (3, "post", 20)]
    assert dealt(hands[4]) == {0, 2, 3, 4} and forced(hands[4]) == [(0, "blind", 10), (2, "blind", 20)]
    assert not table.seat_of(9).waiting and not table.seat_of(10).post


@pytest.mark.asyncio
async def test_sitting_back_within_30_minutes_needs_what_you_left_with(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await autoplay(table, ann, [RAISE])
    await until(lambda: open_turn(table, 7, None))
    await table.stand(ann)
    await autoplay(table, sam, [FOLD])
    await until(lambda: 4 in unseated(sam))
    # Nobody called Ann's raise, so she left with Sam's big blind: 1,020
    assert await balance(host, ann) == 1020 and ann.last("notice")["text"] == "You cashed out 1020."
    await table.buy_in(ann, {"seat": 5, "amount": 1000, "post": False})
    assert ann.last("notice")["text"] == "Buy-ins here are 1020 to 2000." and table.seat_of(8) is None
    assert await balance(host, ann) == 1020
    host.money.clock.now += 1800
    await table.buy_in(ann, {"seat": 5, "amount": 400, "post": False})
    assert table.seat_of(8).real == 400 and await balance(host, ann) == 620


@pytest.mark.asyncio
async def test_top_up_only_between_hands_and_never_past_the_max(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await host.money.bank.deposit(sam.ctx.author, 2000)
    await until(lambda: open_turn(table, 8, None))
    await table.top_up(sam, {"amount": 100})
    assert sam.last("notice")["text"] == "You can top up between hands." and table.seat_of(7).real == 1000
    # The table holds between hands 2 and 3
    gate = asyncio.Event()
    after_hand = table.after_hand

    async def held():
        await gate.wait()
        await after_hand()

    table.after_hand = held
    await autoplay(table, ann, [RAISE])
    await autoplay(table, sam, [FOLD])
    await hand_over(table, 2)
    assert table.seat_of(7).real == 980
    await table.top_up(sam, {"amount": True})
    assert sam.last("notice")["text"] == "Pick an amount to top up."
    await table.top_up(sam, {"amount": 1021})
    assert sam.last("notice")["text"] == "Buy-ins here are 1 to 1020." and table.seat_of(7).real == 980
    await table.top_up(sam, {"amount": 1020})
    assert table.seat_of(7).real == 2000 and await balance(host, sam) == 980
    assert await stacked(host, floor, 7) == 2000 and sam.last("me")["balance"] == 980
    await table.top_up(sam, {"amount": 1})
    assert sam.last("notice")["text"] == "Your stack is already at the Max." and await balance(host, sam) == 980
    gate.set()
    await until(lambda: table.hand_no == 3 and table.hand is not None)
    sam_in_hand = table.hand.players[0]
    assert sam_in_hand.stack + sam_in_hand.bet == 2000


@pytest.mark.asyncio
async def test_two_timeouts_in_a_row_stand_a_player_up_with_their_chips(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    playing = asyncio.create_task(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]))
    # Sam's clock runs out before the flop. He checks the flop himself, which starts the count again
    await until(lambda: table.street == "preflop" and open_turn(table, 7, None))
    time_out(table, 7)
    await until(lambda: table.street == "flop" and open_turn(table, 7, None))
    assert table.seat_of(7).timeouts == 1
    await table.move(sam, CHECK)
    # His clock runs out on the turn, and again on the river
    await until(lambda: table.street == "turn" and open_turn(table, 7, None))
    assert table.seat_of(7).timeouts == 0
    time_out(table, 7)
    await until(lambda: table.street == "river" and open_turn(table, 7, None))
    assert table.seat_of(7).timeouts == 1 and not table.seat_of(7).leaving
    time_out(table, 7)
    await playing
    await until(lambda: 0 in unseated(ann))
    assert acts(hands_of(sam)[1], 0) == ["check"] * 4
    # Ann's aces took the pot of 40 less a cut of 2, and Sam's 980 went back to his bank
    assert await balance(host, sam) == 980 and sam.last("notice")["text"] == "You cashed out 980."
    assert await stacked(host, floor, 7) == 0 and table.seat_of(8).real == 1018


@pytest.mark.asyncio
async def test_leaving_the_window_mid_hand_folds_you_after_the_grace(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    # Back within the 8-second grace: its timer stops and nothing changes
    await walk_away(floor, sam)
    grace = table.seat_graces[7]
    assert table.busy()
    await come_back(floor, sam)
    await until(grace.done)
    assert grace.cancelled() and not table.seat_graces and not table.seat_of(7).leaving
    # Away past the grace (none at all here): Sam is on his way out, and coming back doesn't change that
    table.times["grace"] = 0
    await walk_away(floor, sam)
    await until(lambda: table.seat_of(7).leaving)
    await come_back(floor, sam)
    await autoplay(table, ann, [RAISE])
    await hand_over(table, 2)
    # His turn didn't wait out his 35 seconds: he folded to the raise at once
    assert acts(hands_of(ann)[1], 0) == ["fold"]
    await until(lambda: 0 in unseated(ann))
    assert await balance(host, sam) == 980 and await stacked(host, floor, 7) == 0


@pytest.mark.asyncio
async def test_a_player_who_drops_keeps_their_turn_through_the_grace(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    # Sam's connection drops just before his turn
    await walk_away(floor, sam)
    await autoplay(table, ann, [RAISE])
    # His turn waits for him on its usual clock, and everyone sees the table wait on him
    await until(lambda: open_turn(table, 7, None))
    state = ann.last("table")
    assert not table.is_here(7) and state["waiting"] == ["7"] and state["left"] > DECISION_TIME - 5
    # He's back inside the 8-second grace: his buttons come back and his move counts
    await come_back(floor, sam)
    assert sam.last("ask")["moves"] == ["fold", "call", "raise"] and not table.seat_graces
    await table.move(sam, CALL)
    await until(lambda: played(ann, 0, "call", hand=1))
    assert not table.seat_of(7).leaving and table.seat_of(7).timeouts == 0


@pytest.mark.asyncio
async def test_a_turn_waits_out_the_grace_then_checks_when_a_check_is_free(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    table.times["grace"] = 0.5
    await walk_away(floor, sam)
    # Ann only calls, so Sam's big blind could check for free
    playing = asyncio.create_task(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]))
    try:
        await until(lambda: open_turn(table, 7, None))
        await hand_over(table, 2)
    finally:
        playing.cancel()
    # He didn't come back in time, so his seat checked it down, and Ann's aces took his big blind
    assert acts(hands_of(ann)[1], 0) == ["check"] * 4
    await until(lambda: 0 in unseated(ann))
    assert await balance(host, sam) == 980 and await stacked(host, floor, 7) == 0


@pytest.mark.asyncio
async def test_stepping_out_at_the_end_of_a_turn_still_counts_the_timeout(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    playing = asyncio.create_task(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]))
    try:
        # Sam is here when his turn opens, steps out just before his clock runs out, and is back inside the grace
        await until(lambda: table.street == "preflop" and open_turn(table, 7, None))
        await walk_away(floor, sam)
        time_out(table, 7)
        await until(lambda: table.street == "flop")
        await come_back(floor, sam)
        assert table.seat_of(7).timeouts == 1
    finally:
        playing.cancel()


@pytest.mark.asyncio
async def test_leaving_the_window_when_not_dealt_in_frees_the_seat_after_the_grace(seat):
    host, floor, table, (sam, ann, bob) = await real_game(seat, 9)
    # The grace runs out at once
    table.times["grace"] = 0
    await table.buy_in(bob, {"seat": 2, "amount": 400, "post": False})
    assert await balance(host, bob) == 600
    await walk_away(floor, bob)
    # Seat 2 emptied once before, when its CPU left for the real game
    await until(lambda: unseated(ann).count(2) == 2)
    assert await balance(host, bob) == 1000 and await stacked(host, floor, 9) == 0
    assert table.hand_no == 2 and unseated(ann)[-1] == 2


@pytest.mark.asyncio
async def test_standing_mid_hand_waits_for_the_hand_to_end(seat):
    host, floor, table, (sam, ann, bob) = await real_game(seat, 9)
    # Bob isn't dealt into the running hand, so standing frees his seat at once
    await table.buy_in(bob, {"seat": 2, "amount": 400, "post": False})
    await table.stand(bob)
    assert table.seat_of(9) is None and await balance(host, bob) == 1000
    assert bob.last("notice")["text"] == "You cashed out 400."
    # Sam is dealt in: he keeps his seat, and his chips stay at the table until the hand ends
    await until(lambda: open_turn(table, 8, None))
    asked = len(sam.of("ask"))
    await table.stand(sam)
    assert table.seat_of(7).leaving and await balance(host, sam) == 0 and await stacked(host, floor, 7) == 1000
    await autoplay(table, ann, [RAISE])
    await hand_over(table, 2)
    # His turn took its default at once: he folded to the raise without being asked
    assert acts(hands_of(sam)[1], 0) == ["fold"] and len(sam.of("ask")) == asked
    await until(lambda: 0 in unseated(ann))
    assert await balance(host, sam) == 980 and sam.last("notice")["text"] == "You cashed out 980."
    events = [(e["kind"], e.get("seat")) for e in hands_of(sam)[1]]
    assert events.index(("win", None)) < events.index(("unseat", 0))


@pytest.mark.asyncio
async def test_standing_up_mid_hand_checks_when_a_check_is_free(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    await table.stand(sam)
    # Ann only calls, so Sam's big blind could check for free
    playing = asyncio.create_task(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]))
    try:
        await hand_over(table, 2)
    finally:
        playing.cancel()
    assert acts(hands_of(ann)[1], 0) == ["check"] * 4
    await until(lambda: 0 in unseated(ann))
    assert await balance(host, sam) == 980 and sam.last("notice")["text"] == "You cashed out 980."


@pytest.mark.asyncio
async def test_closing_the_table_mid_hand_returns_hand_start_stacks_and_takes_no_cut(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await autoplay(table, ann, [RAISE])
    await autoplay(table, sam, [CALL])
    await until(lambda: table.street == "flop" and open_turn(table, 7, None))
    await floor.close()
    # The hand never finished: no winner, no cut, and both stacks went home as they were when it started
    assert "win" not in [e["kind"] for e in hands_of(sam)[1]]
    assert (await balance(host, sam), await balance(host, ann)) == (1000, 1000)
    assert sam.last("notice")["text"] == ann.last("notice")["text"] == "You cashed out 1000."
    assert await host.store.stacks() == [] and not table.humans() and table.task is None
    # Closing again pays nobody twice
    await table.close()
    assert (await balance(host, sam), await balance(host, ann)) == (1000, 1000)


@pytest.mark.asyncio
async def test_a_hand_whose_result_cant_be_saved_goes_back_to_where_it_started(seat, caplog):
    host, floor, table, (sam, ann) = await real_game(seat)
    save_stacks = host.store.save_stacks
    failures = []

    async def fails_once(rows):
        if not failures:
            failures.append(rows)
            raise OSError("disk full")
        await save_stacks(rows)

    host.store.save_stacks = fails_once
    await autoplay(table, ann, [RAISE])
    with caplog.at_level(logging.ERROR, logger="red.vrt.vegas.holdem"):
        await autoplay(table, sam, [FOLD])
        await round_over(table)
    # Ann won 20 at the table, but the result never reached the database, so the hand is undone and both cash out
    assert [len(rows) for rows in failures] == [2] and "A Hold'em session failed" in caplog.text
    assert (await balance(host, sam), await balance(host, ann)) == (1000, 1000)
    assert await host.store.stacks() == [] and not table.humans()


@pytest.mark.asyncio
async def test_new_stakes_start_with_the_next_hand(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    await host.store.save_game(await floor.scope(), "holdem", max_bet=4000)
    # The running hand keeps its blinds of 10 and 20, so Sam may still raise to 40
    await autoplay(table, ann, [CALL])
    await until(lambda: open_turn(table, 7, None))
    assert sam.last("ask")["min_to"] == 40
    await autoplay(table, sam, [{"move": "raise", "amount": 40}])
    await autoplay(table, ann, [FOLD])
    await until(lambda: table.hand_no == 3 and table.turn is not None)
    assert forced(hands_of(sam)[2]) == [(0, "blind", 20), (4, "blind", 40)]
    assert sam.last("table")["stakes"] == {"small": 20, "big": 40, "min": 400, "max": 4000, "cut": 5.0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "closed, refusal", [("holdem", "Texas Hold'em is closed."), ("casino", "The casino is closed.")]
)
async def test_closing_holdem_cashes_everyone_out_after_the_hand(seat, closed, refusal):
    host, floor, table, (sam, ann) = await real_game(seat)
    scope = await floor.scope()
    await until(lambda: open_turn(table, 8, None))
    if closed == "holdem":
        await host.store.save_game(scope, "holdem", is_open=False)
    else:
        await host.store.save_casino(scope, is_open=False)
    # The hand plays out first
    await autoplay(table, ann, [RAISE])
    await autoplay(table, sam, [FOLD])
    await round_over(table)
    kinds = [e["kind"] for e in hands_of(sam)[1]]
    assert kinds.index("win") < kinds.index("unseat") and table.hand_no == 2
    assert sam.last("notice")["text"] == ann.last("notice")["text"] == CLOSED
    assert (await balance(host, sam), await balance(host, ann)) == (980, 1020)
    assert await host.store.stacks() == [] and not table.humans() and table.mode == "idle"
    # Nobody sits down again while it is closed, not even to practice
    await table.sit(sam, 0)
    assert table.seat_of(7) is None and sam.last("notice")["text"] == refusal and table.task is None


@pytest.mark.asyncio
async def test_closing_holdem_tells_a_free_practicer_only_that_it_closed(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    await host.store.save_game(await floor.scope(), "holdem", is_open=False)
    await autoplay(table, sam, [FOLD])
    await round_over(table)
    # Sam had only play chips, so nothing went back to his bank
    assert sam.last("notice")["text"] == "Texas Hold'em closed." and table.seat_of(7) is None
    assert await balance(host, sam) == 1000


@pytest.mark.asyncio
async def test_closing_holdem_while_the_table_waits_on_an_offer_deals_no_more_hands(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    settle_offers, waiting = table.settle_offers, asyncio.Event()

    async def noted_settle():
        waiting.set()
        await settle_offers()

    table.settle_offers = noted_settle
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await autoplay(table, sam, [FOLD])
    # Before the next hand the table waits on Sam's answer, and an admin closes Hold'em meanwhile
    await until(waiting.is_set)
    await host.store.save_game(await floor.scope(), "holdem", is_open=False)
    await table.decline(sam)
    await until(lambda: table.task is None or table.hand_no == 2)
    assert table.hand_no == 1 and not table.humans()
    assert ann.last("notice")["text"] == CLOSED and await balance(host, ann) == 1000
    assert await host.store.stacks() == []


@pytest.mark.asyncio
async def test_nobody_stands_up_without_being_asked_when_a_buy_in_meets_the_next_deal(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    # Ann's buy-in holds the table while her credits are taken
    taking, release = asyncio.Event(), asyncio.Event()
    buy_in = host.money.buy_in

    async def slow_buy_in(*args):
        taking.set()
        await release.wait()
        return await buy_in(*args)

    # The next hand's preparation waits until Ann's buy-in is under way
    reached, gate, asked = asyncio.Event(), asyncio.Event(), []
    prepare, ask_for_buy_ins = table.prepare, table.ask_for_buy_ins

    async def held_prepare():
        reached.set()
        await gate.wait()
        return await prepare()

    async def noted_ask():
        await ask_for_buy_ins()
        asked.append(table.hand_no)

    host.money.buy_in = slow_buy_in
    table.prepare, table.ask_for_buy_ins = held_prepare, noted_ask
    await autoplay(table, sam, [FOLD])
    await until(reached.is_set)
    buying = asyncio.create_task(table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False}))
    await until(taking.is_set)
    gate.set()
    # Nobody had credits when the preparation asked, and it now waits on the table for Ann's buy-in
    await until(lambda: asked)
    release.set()
    await buying
    await until(lambda: table.hand_no == 2 and table.turn is not None)
    # Sam was asked once, and his offer stays open through the practice hand instead of standing him up
    assert table.seat_of(7) is not None and 0 not in unseated(sam)
    assert [offer["kind"] for offer in sam.of("offer")] == ["join"] and not table.offers[7].done()
    assert table.mode == "practice"


@pytest.mark.asyncio
async def test_chips_saved_elsewhere_block_a_buy_in_until_they_go_home(seat):
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    elsewhere_host, elsewhere, other_table, (ann_elsewhere,) = await seat("holdem", 8)
    table.choose = folds
    refused = "You already have chips at another Hold'em table. Stand up there first."
    # Sam's stack from before a restart is still saved: he wasn't found when the cog loaded
    await host.store.save_stack(await floor.scope(), GUILD_ID, 7, 900)
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    assert sam.last("notice")["text"] == refused and table.seat_of(7) is None and await balance(host, sam) == 1000
    # A free practice seat is fine, but answering an offer is a buy-in too
    await table.sit(sam, 0)
    await until(lambda: 7 in table.decisions)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await table.buy_in(sam, {"seat": None, "amount": 1000, "post": False})
    assert sam.last("notice")["text"] == refused and table.seat_of(7).real == 0
    assert await stacked(host, floor, 7) == 900 and await balance(host, sam) == 1000
    # Ann's chips here keep her from buying in at a table in another window
    await other_table.buy_in(ann_elsewhere, {"seat": 0, "amount": 500, "post": False})
    assert ann_elsewhere.last("notice")["text"] == refused and other_table.seat_of(8) is None
    assert await stacked(host, floor, 8) == 1000 and await balance(elsewhere_host, ann_elsewhere) == 1000
    # Once she stands up here and her stack goes home, she can buy in there
    await table.stand(ann)
    assert table.seat_of(8) is None and await stacked(host, floor, 8) == 0 and await balance(host, ann) == 1000
    await other_table.buy_in(ann_elsewhere, {"seat": 0, "amount": 500, "post": False})
    assert other_table.seat_of(8).real == 500 and await stacked(host, floor, 8) == 500
    assert await balance(elsewhere_host, ann_elsewhere) == 500


@pytest.mark.asyncio
async def test_a_mode_switch_mid_session_pays_each_stack_once(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    server = await floor.scope()
    await until(lambda: open_turn(table, 8, None))
    # The bot owner switches to one global casino while both have chips at the table
    await host.store.set_global_mode(True)
    await autoplay(table, ann, [RAISE])
    await autoplay(table, sam, [FOLD])
    await hand_over(table, 2)
    # The hand's result is saved where the chips were bought in, and nothing is saved in the global casino
    assert (await host.store.stacked(server, 7), await host.store.stacked(server, 8)) == (980, 1020)
    assert (await host.store.stacked(0, 7), await host.store.stacked(0, 8)) == (0, 0)
    await table.stand(sam)
    await table.stand(ann)
    await until(lambda: not table.humans())
    # Both stacks went home once, and no saved row is left for the next load to pay again
    assert await host.store.stacks() == []
    assert await balance(host, sam) + await balance(host, ann) == 2000


@pytest.mark.asyncio
async def test_standing_up_from_a_free_seat_keeps_a_stack_saved_from_a_restart(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    # Sam's 900 from before a restart is still saved: he wasn't found when the cog loaded
    await host.store.save_stack(await floor.scope(), GUILD_ID, 7, 900)
    await table.stand(sam)
    await until(lambda: 0 in unseated(ann))
    assert await stacked(host, floor, 7) == 900 and await balance(host, sam) == 1000


@pytest.mark.asyncio
async def test_a_refused_offer_answer_keeps_the_saved_stack_when_the_player_stands_up(seat):
    host, floor, table, (sam, ann) = await practicing(seat)
    await host.store.save_stack(await floor.scope(), GUILD_ID, 7, 900)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    # Sam's yes is refused because of the saved 900, his offer runs out, and the next deal stands him up
    await table.buy_in(sam, {"seat": None, "amount": 1000, "post": False})
    lapse(table.offers[7])
    await autoplay(table, sam, [FOLD])
    await until(lambda: 0 in unseated(ann))
    assert await stacked(host, floor, 7) == 900 and await balance(host, sam) == 1000


@pytest.mark.asyncio
async def test_standing_up_from_a_free_seat_at_another_table_keeps_your_stack_there(seat):
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    elsewhere_host, elsewhere, other_table, (ann_elsewhere,) = await seat("holdem", 8)
    table.choose = other_table.choose = folds
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    # In another window Ann sits free to practice, then stands up before a hand is dealt there
    await other_table.sit(ann_elsewhere, 0)
    await other_table.stand(ann_elsewhere)
    assert other_table.seat_of(8) is None and await stacked(host, floor, 8) == 1000
    # Her stack here still counts, so she can't buy in there yet
    await other_table.buy_in(ann_elsewhere, {"seat": 1, "amount": 500, "post": False})
    refused = "You already have chips at another Hold'em table. Stand up there first."
    assert ann_elsewhere.last("notice")["text"] == refused and other_table.seat_of(8) is None
    assert await stacked(host, floor, 8) == 1000 and await balance(elsewhere_host, ann_elsewhere) == 1000


@pytest.mark.asyncio
async def test_a_full_bank_at_cash_out_holds_the_rest_as_pending_credits(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    host.money.bank.maximum = 500
    await autoplay(table, ann, [RAISE])
    await until(lambda: open_turn(table, 7, None))
    await table.stand(ann)
    await autoplay(table, sam, [FOLD])
    await until(lambda: 4 in unseated(sam))
    # Ann leaves with 1,020 and her bank holds at most 500
    held = "You cashed out 500. 520 is held because your bank is full. An admin can release it."
    assert ann.last("notice")["text"] == held and await balance(host, ann) == 500
    assert (await host.store.player(await floor.scope(), 8)).pending == 520 and await stacked(host, floor, 8) == 0


@pytest.mark.asyncio
async def test_turns_missed_while_reconnecting_are_not_timeouts(seat):
    host, floor, table, (sam, ann) = await real_game(seat)
    await until(lambda: open_turn(table, 8, None))
    # Sam's connection drops, and each of his turns runs out of time while it is down
    await walk_away(floor, sam)
    playing = asyncio.create_task(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]))
    for street in ("preflop", "flop", "turn", "river"):
        await until(lambda: table.street == street and open_turn(table, 7, None))
        time_out(table, 7)
    await playing
    await hand_over(table, 2)
    assert acts(hands_of(ann)[1], 0) == ["check"] * 4
    # He's back inside the 8-second grace with no strikes, so he keeps his seat and plays on
    await come_back(floor, sam)
    assert table.seat_of(7).timeouts == 0 and not table.seat_of(7).leaving
    await until(lambda: table.hand_no == 3 and open_turn(table, 7, None))
    assert 0 not in unseated(ann)


def recovery_world(store, maximum: int = 2**63 - 1):
    """A bot with one server, and `discord`: people Discord would find who aren't in the bot's cache"""
    bot = FakeBot()
    guild = FakeGuild()
    bot.guilds[guild.id] = guild
    bank = FakeBank(start=1000, maximum=maximum)
    discord = {}

    async def fetch(user_id):
        if user_id not in discord:
            raise LookupError("Unknown Member")
        return discord[user_id]

    guild.fetch_member = bot.fetch_user = fetch
    return bot, guild, bank, Money(store, bank, Clock()), discord


@pytest.mark.asyncio
async def test_recovery_returns_saved_stacks_and_holds_what_a_full_bank_cannot_take(store):
    bot, guild, bank, money, discord = recovery_world(store, maximum=2000)
    guild.add(7)
    guild.add(8)
    # Dan isn't in the bot's member cache (no members intent), but Discord still finds him
    discord[10] = member(10, guild=guild)
    await store.save_stack(GUILD_ID, GUILD_ID, 7, 900)
    await store.save_stack(GUILD_ID, GUILD_ID, 8, 1500)
    await store.save_stack(GUILD_ID, GUILD_ID, 10, 200)
    assert await return_stacks(bot, store, money) == 3
    # Sam's 900 fits; Ann's bank had room for 1,000, so 500 waits as pending credits
    assert bank.balances == {7: 1900, 8: 2000, 10: 1200}
    assert (await store.player(GUILD_ID, 7)).pending == 0 and (await store.player(GUILD_ID, 8)).pending == 500
    assert await store.stacks() == []
    # With Red's bank global, the owner is found among all the bot's users, or fetched from Discord
    bank.global_bank = True
    bot.users[9] = member(9)
    discord[11] = member(11)
    await store.save_stack(0, GUILD_ID, 9, 300)
    await store.save_stack(0, GUILD_ID, 11, 400)
    assert await return_stacks(bot, store, money) == 2
    assert (bank.balances[9], bank.balances[11]) == (1300, 1400) and await store.stacks() == []


@pytest.mark.asyncio
async def test_a_stack_whose_owner_cant_be_found_stays_saved(store, caplog):
    bot, guild, bank, money, discord = recovery_world(store)
    # Sam left the server (Discord doesn't find him either), and the bot can't see the server Ann's stack is from
    await store.save_stack(GUILD_ID, GUILD_ID, 7, 900)
    await store.save_stack(600, 600, 8, 500)
    with caplog.at_level(logging.WARNING, logger="red.vrt.vegas.holdem"):
        assert await return_stacks(bot, store, money) == 0
    assert sorted((row.user_id, row.amount) for row in await store.stacks()) == [(7, 900), (8, 500)]
    assert bank.balances == {} and len(caplog.records) == 2
    assert all(record.levelno == logging.WARNING for record in caplog.records)
    # Nor is a user Discord doesn't know, with a global bank; the next load tries again
    bank.global_bank = True
    assert await return_stacks(bot, store, money) == 0 and len(await store.stacks()) == 2


def casino_for(store, bot, bank, money, monkeypatch) -> Vegas:
    """The cog, ready to run its load without Red or migrations"""
    casino = Vegas(bot)
    casino.store, casino.bank, casino.money = store, bank, money
    casino.updater = Updater(bot, store, bank, casino.refresh_players)

    async def nothing(*args, **kwargs):
        return None

    bot.wait_until_red_ready = nothing
    monkeypatch.setattr("vegas.main.engine.register_cog", nothing)
    return casino


@pytest.mark.asyncio
async def test_the_casino_opens_only_after_saved_stacks_are_returned(store, monkeypatch):
    bot, guild, bank, money, discord = recovery_world(store)
    guild.add(7)
    await store.save_stack(GUILD_ID, GUILD_ID, 7, 900)
    casino = casino_for(store, bot, bank, money, monkeypatch)
    opened_at_payout = []
    cash_out = money.cash_out

    async def paying(scope, who, amount):
        opened_at_payout.append(casino.ready.is_set())
        return await cash_out(scope, who, amount)

    money.cash_out = paying
    try:
        await casino.initialize()
        assert opened_at_payout == [False] and casino.ready.is_set()
        assert await store.stacks() == [] and bank.balances[7] == 1900
    finally:
        await casino.cog_unload()


@pytest.mark.asyncio
async def test_the_casino_opens_even_when_saved_stacks_cant_be_returned(store, monkeypatch, caplog):
    bot, guild, bank, money, discord = recovery_world(store)
    guild.add(7)
    await store.save_stack(GUILD_ID, GUILD_ID, 7, 900)
    casino = casino_for(store, bot, bank, money, monkeypatch)

    async def unreadable():
        raise OSError("database is locked")

    store.stacks = unreadable
    try:
        with caplog.at_level(logging.ERROR, logger="red.vrt.vegas"):
            await casino.initialize()
        # The row stays saved for the next load, and the casino opens anyway
        assert casino.ready.is_set() and "stay saved for the next load" in caplog.text
        assert await store.stacked(GUILD_ID, 7) == 900 and bank.balances == {}
    finally:
        await casino.cog_unload()
