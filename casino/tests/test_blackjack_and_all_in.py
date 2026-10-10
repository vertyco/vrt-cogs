"""Blackjack's seats, turns and doubles, and All In's private machines"""

import asyncio

import pytest

from casino.common.table import PACE
from casino.tests.tables_kit import Rigged, round_over, until


@pytest.mark.asyncio
async def test_blackjack_needs_a_seat_and_plays_hit_then_stay(seat):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    await table.bet(sam, {"amount": 100})
    assert sam.last("notice")["text"] == "Take a seat to bet."
    await table.sit(sam, 2)
    # Drawn from the end: Sam 5, dealer 10, Sam 6, dealer 7 (hidden), Sam hits a 9, then nothing more for the dealer
    table.deck.cards = [("9", "c"), ("7", "s"), ("6", "h"), ("10", "d"), ("5", "c")]
    await table.bet(sam, {"amount": 100})
    await until(lambda: 7 in table.decisions)
    state = sam.last("table")
    assert state["turn"] == "7" and state["dealer"]["cards"][1] is None and state["dealer"]["total"] == 10
    await table.move(sam, {"move": "hit"})
    await until(lambda: 7 in table.decisions and len(table.hands[7]["cards"]) == 3)
    assert table.allowed[7] == ("hit", "stay")
    await table.move(sam, {"move": "stay"})
    await round_over(table)
    assert sam.last("result")["outcome"] == "win" and sam.last("result")["payout"] == 200


@pytest.mark.asyncio
async def test_blackjack_double_takes_a_second_bet_and_one_card(seat):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    await table.sit(sam, 0)
    table.deck.cards = [("10", "c"), ("7", "s"), ("6", "h"), ("10", "d"), ("5", "c")]
    await table.bet(sam, {"amount": 100})
    await until(lambda: 7 in table.decisions)
    await table.move(sam, {"move": "double"})
    await round_over(table)
    assert len(sam.last("table")["players"]) == 1
    assert sam.last("result")["payout"] == 400 and sam.last("result")["balance"] == 1200


@pytest.mark.asyncio
async def test_blackjack_push_returns_the_stake_and_time_out_means_stay(seat):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    table.times["decision"] = 0.01
    await table.sit(sam, 0)
    # Drawn from the end: Sam 10, dealer 10, Sam 8, dealer 8: 18 against 18
    table.deck.cards = [("8", "s"), ("8", "d"), ("10", "h"), ("10", "c")]
    await table.bet(sam, {"amount": 100})
    await round_over(table)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("push", 100, 1000)


@pytest.mark.asyncio
async def test_only_the_deciding_player_hears_their_moves_and_double_needs_the_credits(seat):
    host, floor, table, (sam, ann) = await seat("blackjack", 7, 8)
    await table.sit(sam, 0)
    table.times["betting"] = 0.05
    table.deck.cards = [("10", "c"), ("7", "s"), ("6", "h"), ("10", "d"), ("5", "c")]
    host.money.bank.balances[7] = 500
    await table.bet(sam, {"amount": 400})
    await until(lambda: sam.of("ask"))
    assert sam.last("ask")["moves"] == ["hit", "stay"] and not ann.of("ask")
    assert sam.last("table")["waiting"] == ["7"]
    await table.leave(sam)
    await table.enter(sam)
    assert sam.last("ask")["moves"] == ["hit", "stay"]
    await table.move(sam, {"move": "stay"})
    await round_over(table)


@pytest.mark.asyncio
async def test_a_player_who_comes_back_within_the_grace_gets_their_turn_back(seat):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    table.times["grace"] = 1.0
    await table.sit(sam, 0)
    table.deck.cards = [("10", "c"), ("7", "s"), ("6", "h"), ("10", "d"), ("5", "c")]
    await table.bet(sam, {"amount": 100})
    await until(lambda: sam.of("ask"))
    await floor.depart(sam)
    sam.sent.clear()
    await floor.arrive(sam)
    await floor.enter(sam, "blackjack")
    assert sam.last("ask")["moves"] == ["hit", "stay", "double"]
    await table.move(sam, {"move": "hit"})
    await until(lambda: len(table.hands[7]["cards"]) == 3)


@pytest.mark.asyncio
async def test_leaving_frees_the_seat_after_the_round(seat):
    host, floor, table, (sam, ana) = await seat("blackjack", 7, 8)
    table.times["decision"] = 0.01
    await table.sit(sam, 0)
    await table.sit(ana, 0)
    assert ana.last("notice")["text"] == "That seat was just taken."
    await table.bet(sam, {"amount": 100})
    await table.press_go(sam)
    await until(lambda: table.phase == "playing")
    await floor.to_lobby(sam)
    assert table.seats[0] is not None
    await round_over(table)
    assert table.seats[0] is None and "result" in {m["t"] for m in sam.sent}


@pytest.mark.asyncio
async def test_all_in_is_private_and_pays_the_balance_times_the_multiplier(seat):
    host, floor, table, (sam, ana) = await seat("allin", 7, 8, rng=Rigged(ints=[0]))
    await table.bet(sam, {"multiplier": 1})
    assert sam.last("notice")["text"] == "Your multiplier must be 2 or higher."
    await table.bet(sam, {"multiplier": 3})
    await until(lambda: not table.pulls)
    assert sam.last("event")["win"] is True and ana.of("event") == []
    assert sam.last("result")["payout"] == 3000 and sam.last("result")["balance"] == 3000


@pytest.mark.asyncio
async def test_a_floor_with_a_pull_in_flight_is_busy_and_closing_refunds_the_stake(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("allin", 7, rng=Rigged(ints=[0]))
    monkeypatch.setitem(PACE, "pull", 60.0)
    table.speed = 1.0
    await table.bet(sam, {"multiplier": 3})
    await until(lambda: sam.of("event"))
    assert host.money.bank.balances[7] == 0
    await floor.depart(sam)
    assert not floor.where and table.task is None
    assert table.busy() and not floor.idle()
    await floor.close()
    assert host.money.bank.balances[7] == 1000
    assert not table.busy() and floor.idle()


@pytest.mark.asyncio
async def test_a_second_pull_while_the_first_spins_is_refused(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("allin", 7, rng=Rigged(ints=[0]))
    monkeypatch.setitem(PACE, "pull", 0.3)
    table.speed = 1.0
    await table.bet(sam, {"multiplier": 3})
    await table.bet(sam, {"multiplier": 3})
    assert sam.last("notice")["text"] == "You already bet this round."
    await until(lambda: not table.pulls)
    assert host.money.bank.balances[7] == 3000
    assert sam.last("result")["payout"] == 3000


@pytest.mark.asyncio
async def test_all_in_refuses_bets_once_closing(seat):
    host, floor, table, (sam,) = await seat("allin", 7)
    table.closing.set()
    await table.bet(sam, {"multiplier": 3})
    assert sam.last("notice")["text"] == "This table is closing."
    assert not table.bets and not table.pulls


@pytest.mark.asyncio
async def test_a_failed_pull_refunds_the_stake(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("allin", 7, rng=Rigged(ints=[0]))

    async def broken(*args, **kwargs):
        raise RuntimeError("settle broke")

    monkeypatch.setattr(table, "settle", broken)
    await table.bet(sam, {"multiplier": 3})
    await until(lambda: not table.pulls)
    assert host.money.bank.balances[7] == 1000 and not table.bets


@pytest.mark.asyncio
async def test_a_cancelled_pull_refunds_the_stake(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("allin", 7, rng=Rigged(ints=[0]))
    monkeypatch.setitem(PACE, "pull", 60.0)
    table.speed = 1.0
    await table.bet(sam, {"multiplier": 3})
    await until(lambda: sam.of("event"))
    for task in list(table.pulls):
        task.cancel()
    await until(lambda: not table.pulls)
    assert host.money.bank.balances[7] == 1000


@pytest.mark.asyncio
async def test_a_window_whose_last_player_left_mid_pull_is_dropped_when_the_pull_ends(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("allin", 7, rng=Rigged(ints=[0]))
    monkeypatch.setitem(PACE, "pull", 0.2)
    table.speed = 1.0
    await table.bet(sam, {"multiplier": 3})
    await floor.depart(sam)
    assert floor not in host.done
    await until(lambda: floor in host.done)
    assert host.money.bank.balances[7] == 3000


@pytest.mark.asyncio
async def test_a_failed_double_is_not_offered_again(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    await table.sit(sam, 0)
    table.deck.cards = [("2", "c"), ("2", "h"), ("6", "h"), ("10", "d"), ("5", "c")]

    async def cannot(*args, **kwargs):
        return False

    monkeypatch.setattr(host.money, "extra", cannot)
    await table.bet(sam, {"amount": 100})
    await until(lambda: 7 in table.decisions)
    await table.move(sam, {"move": "double"})
    await until(lambda: sam.of("notice") and 7 in table.decisions and table.allowed[7] == ("hit", "stay"))
    await table.move(sam, {"move": "stay"})
    await round_over(table)


@pytest.mark.asyncio
async def test_closing_right_after_a_double_gives_back_both_stakes(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("blackjack", 7)
    await table.sit(sam, 0)
    table.deck.cards = [("10", "c"), ("7", "s"), ("6", "h"), ("10", "d"), ("5", "c")]
    await table.bet(sam, {"amount": 100})
    await until(lambda: 7 in table.decisions)
    monkeypatch.setitem(PACE, "deal", 60.0)
    table.speed = 1.0
    await table.move(sam, {"move": "double"})
    await until(lambda: 7 in table.bets and table.bets[7].amount == 200)
    assert host.money.bank.balances[7] == 800
    await floor.close()
    assert host.money.bank.balances[7] == 1000


@pytest.mark.asyncio
async def test_a_seated_player_who_drops_between_rounds_keeps_the_seat_for_the_grace(seat):
    host, floor, table, (sam, ana) = await seat("blackjack", 7, 8)
    table.times["grace"] = 0.2
    await table.sit(sam, 0)
    await floor.depart(sam)
    assert table.seats[0] is not None
    await floor.arrive(sam)
    await floor.enter(sam, "blackjack")
    await asyncio.sleep(0.3)
    assert table.seats[0] is not None  # back within the grace: the seat stays theirs
    await floor.depart(sam)
    await until(lambda: table.seats[0] is None)
    assert ana.last("table")["seats"][0] is None
