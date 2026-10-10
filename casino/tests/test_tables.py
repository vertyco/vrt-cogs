"""Shared tables: starting rounds, the betting window, refusals, refunds, and the four quick games"""

import asyncio

import pytest

from casino.tests.tables_kit import Rigged, round_over, until


@pytest.mark.asyncio
async def test_alone_a_bet_starts_the_round_at_once(seat):
    host, floor, table, (sam,) = await seat("coin", 7, rng=Rigged(picks=["heads"]))
    await table.bet(sam, {"amount": 10, "choice": "heads"})
    await round_over(table)
    assert [m["kind"] for m in sam.of("event")] == ["flip"] and sam.last("event")["side"] == "heads"
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("win", 15, 1005)
    assert sam.last("table")["phase"] == "idle"


@pytest.mark.asyncio
async def test_with_others_the_first_bet_opens_a_window_a_bettor_can_skip(seat):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8, rng=Rigged(ints=[3, 4]))
    await table.bet(sam, {"amount": 25})
    await until(lambda: table.deadline is not None)
    assert sam.last("table")["phase"] == "betting" and sam.last("table")["left"] > 9
    await table.press_go(ana)  # a watcher can't skip the window
    assert table.phase == "betting"
    await table.bet(ana, {"amount": 50})
    await table.press_go(ana)
    await round_over(table)
    assert sam.last("result")["payout"] == 45 and ana.last("result")["payout"] == 90


@pytest.mark.asyncio
async def test_bets_are_refused_with_a_reason(seat):
    host, floor, table, (sam, ana) = await seat("hilo", 7, 8)
    await table.bet(sam, {"amount": "lots", "choice": "low"})
    assert sam.last("notice")["text"] == "Pick an amount to bet."
    await table.bet(sam, {"amount": 25, "choice": "middle"})
    assert sam.last("notice")["text"] == "Pick low, high or seven."
    await table.bet(sam, {"amount": 25, "choice": "low"})
    await table.bet(sam, {"amount": 25, "choice": "low"})
    assert sam.last("notice")["text"] == "You already bet this round."
    table.phase = "playing"
    await table.bet(ana, {"amount": 25, "choice": "low"})
    assert ana.last("notice")["text"] == "Wait for the next round."
    await table.close()


@pytest.mark.asyncio
async def test_hilo_seven_pays_five_times_the_multiplier(seat):
    host, floor, table, (sam,) = await seat("hilo", 7, rng=Rigged(ints=[3, 4]))
    await table.bet(sam, {"amount": 25, "choice": "seven"})
    await round_over(table)
    assert sam.last("result")["payout"] == 212  # 25 x 5 x 1.7 = 212.5, rounded like the original


@pytest.mark.asyncio
async def test_cups_reveal_one_cup_for_everyone(seat):
    host, floor, table, (sam, ana) = await seat("cups", 7, 8, rng=Rigged(ints=[2]))
    await table.bet(sam, {"amount": 25, "choice": 2})
    await table.bet(ana, {"amount": 25, "choice": 3})
    await table.press_go(sam)
    await round_over(table)
    assert sam.last("event") == {"t": "event", "game": "cups", "kind": "shuffle", "cup": 2}
    assert sam.last("result")["outcome"] == "win" and ana.last("result")["outcome"] == "lose"
    players = {p["id"]: p for p in ana.last("table")["players"]} if ana.last("table")["phase"] != "idle" else None
    assert players is None or players["7"]["outcome"] == "win"


@pytest.mark.asyncio
async def test_closing_mid_round_refunds_every_open_bet(seat):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8)
    await table.bet(sam, {"amount": 25})
    await until(lambda: table.deadline is not None)
    await floor.close()
    assert await host.money.bank.balance(sam.ctx.author) == 1000 and table.task is None
    assert sam.last("notice")["text"] == "The round stopped, so your bet of 25 came back."
    assert sam.last("me")["balance"] == 1000


@pytest.mark.asyncio
async def test_the_lobby_counts_people_at_each_table(seat):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8)
    await floor.enter(ana, "coin")
    assert sam.last("lobby")["counts"] == {"dice": 1, "coin": 1}
    await floor.depart(sam)
    assert ana.last("lobby")["counts"] == {"coin": 1}


@pytest.mark.asyncio
async def test_a_bet_still_being_staked_when_the_round_starts_joins_the_round(seat):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8, rng=Rigged(ints=[3, 4]))
    bank = host.money.bank
    held, release = asyncio.Event(), asyncio.Event()
    withdraw = bank.withdraw

    async def slow_withdraw(who, amount):
        if who.id == 8:
            held.set()
            await release.wait()
        await withdraw(who, amount)

    bank.withdraw = slow_withdraw
    await table.bet(sam, {"amount": 25})
    await until(lambda: table.deadline is not None)
    pending = asyncio.create_task(table.bet(ana, {"amount": 50}))
    await held.wait()
    await table.press_go(sam)
    await asyncio.sleep(0.05)
    release.set()
    await pending
    await round_over(table)
    assert ana.last("result")["payout"] == 90
    assert await bank.balance(ana.ctx.author) == 1040


@pytest.mark.asyncio
async def test_leaving_again_after_returning_gets_a_full_grace(seat):
    host, floor, table, (sam,) = await seat("coin", 7)
    table.times["grace"] = 0.3
    future = asyncio.get_running_loop().create_future()
    table.decisions[7], table.fallbacks[7] = future, "stay"
    await table.leave(sam)
    await asyncio.sleep(0.2)
    await table.enter(sam)
    await table.leave(sam)
    await asyncio.sleep(0.2)
    assert not future.done()
    await until(future.done)
    assert future.result() == "stay"
    table.decisions.clear()


@pytest.mark.asyncio
async def test_closing_while_a_bet_is_being_staked_refunds_both(seat):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8)
    bank = host.money.bank
    held, release = asyncio.Event(), asyncio.Event()
    withdraw = bank.withdraw

    async def slow_withdraw(who, amount):
        if who.id == 8:
            held.set()
            await release.wait()
        await withdraw(who, amount)

    bank.withdraw = slow_withdraw
    await table.bet(sam, {"amount": 25})
    await until(lambda: table.deadline is not None)
    pending = asyncio.create_task(table.bet(ana, {"amount": 50}))
    await held.wait()
    closing = asyncio.create_task(floor.close())
    await asyncio.sleep(0.05)
    release.set()
    await pending
    await closing
    assert await bank.balance(sam.ctx.author) == 1000 and await bank.balance(ana.ctx.author) == 1000
    await table.bet(sam, {"amount": 25})
    assert sam.last("notice")["text"] == "This table is closing."


@pytest.mark.asyncio
async def test_a_round_pays_by_the_settings_its_bets_were_placed_under(seat, store):
    host, floor, table, (sam, ana) = await seat("dice", 7, 8, rng=Rigged(ints=[3, 4]))
    await store.save_casino(500, limit_on=True, limit_amount=10)
    await table.bet(sam, {"amount": 25})
    await until(lambda: table.deadline is not None)
    # The multiplier goes up in both scopes and the owner switches to global mode while the round is open
    for scope in (500, 0):
        await store.save_game(scope, "dice", multiplier=3.0)
    await store.set_global_mode(True)
    await table.press_go(sam)
    await round_over(table)
    result = sam.last("result")
    assert (result["payout"], result["held"]) == (45, True)  # 25 x the old 1.8, held by the old server's limit
    assert (await store.player(500, 7)).pending == 45 and (await store.player(0, 7)).pending == 0
    assert (await store.player_game(500, 7, "dice")).won == 1
