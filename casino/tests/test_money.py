import asyncio

import pytest

from casino.common.money import Money, fmt_seconds
from casino.tests.fakes import Clock, FakeBank, member

GUILD = 500


@pytest.fixture
def money(store):
    return Money(store, FakeBank(start=1000), Clock())


async def win_now(money, who, key, amount, returned=0):
    """A win under the settings in force now, as if its bet had just been placed"""
    return await money.win(who, key, amount, await money.terms(GUILD, who.id, key), returned=returned)


@pytest.mark.asyncio
async def test_checks_run_in_the_originals_order(money, store):
    sam = member(7)
    await store.save_casino(GUILD, is_open=False)
    await store.save_game(GUILD, "dice", is_open=False, access=2)
    assert await money.problem(GUILD, sam, "dice", 5000) == "The casino is closed."
    await store.save_casino(GUILD, is_open=True)
    assert await money.problem(GUILD, sam, "dice", 5000) == "Dice is closed."
    await store.save_game(GUILD, "dice", is_open=True)
    assert "needs access level 2. Yours is 0" in await money.problem(GUILD, sam, "dice", 5000)
    await store.save_game(GUILD, "dice", access=0)
    assert await money.problem(GUILD, sam, "dice", 5000, "Pick a cup.") == "Pick a cup."
    assert await money.problem(GUILD, sam, "dice", 5000) == "Bets here are 25 to 100."
    assert await money.problem(GUILD, sam, "coin", 11) == "Bets here are exactly 10."
    await store.save_game(GUILD, "dice", max_bet=5000)
    assert await money.problem(GUILD, sam, "dice", 5000) == "You don't have enough credits for that bet."
    assert await money.problem(GUILD, sam, "dice", 50) is None


@pytest.mark.asyncio
async def test_a_stake_is_taken_counted_and_starts_the_cooldown(money, store):
    sam = member(7)
    assert await money.stake(GUILD, sam, "dice", 50) is None
    assert await money.bank.balance(sam) == 950
    row = await store.player_game(GUILD, 7, "dice")
    assert row.played == 1 and row.ready_at == money.clock.now + 5
    assert await money.stake(GUILD, sam, "dice", 50) == "Dice is ready again in 5 seconds."
    money.clock.now += 5
    assert await money.stake(GUILD, sam, "dice", 50) is None


@pytest.mark.asyncio
async def test_a_membership_cuts_the_cooldown_and_shows_the_right_time_left(money, store):
    sam = member(7)
    gold = await store.save_membership(GUILD, {"name": "Gold", "reduction": 3})
    await store.set_membership(GUILD, 7, gold.id, by_hand=True)
    await money.stake(GUILD, sam, "dice", 50)
    assert await money.ready_in(GUILD, 7, "dice") == 2
    money.clock.now += 2
    assert await money.stake(GUILD, sam, "dice", 50) is None


@pytest.mark.asyncio
async def test_all_in_needs_some_credits_and_ignores_the_bet_range(money):
    assert await money.problem(GUILD, member(7), "allin", 0) == "You need some credits to go all in."
    assert await money.problem(GUILD, member(7), "allin", 1000) is None


@pytest.mark.asyncio
async def test_a_win_pays_stake_times_multiplier_times_bonus(money, store):
    sam = member(7)
    gold = await store.save_membership(GUILD, {"name": "Gold", "bonus": 1.5})
    await store.set_membership(GUILD, 7, gold.id, by_hand=True)
    payout = await win_now(money, sam, "dice", 100)
    assert (payout.total, payout.bonus, payout.held, payout.balance) == (270, 90, False, 1270)
    assert (await store.player_game(GUILD, 7, "dice")).won == 1


@pytest.mark.asyncio
async def test_all_in_and_double_skip_the_multiplier_and_bonus(money, store):
    sam = member(7)
    gold = await store.save_membership(GUILD, {"name": "Gold", "bonus": 2.0})
    await store.set_membership(GUILD, 7, gold.id, by_hand=True)
    assert (await win_now(money, sam, "double", 400)).total == 400
    assert (await win_now(money, sam, "allin", 3000)).total == 3000


@pytest.mark.asyncio
async def test_the_payout_limit_holds_the_real_total_and_held_wins_add_up(money, store):
    sam = member(7)
    await store.save_casino(GUILD, limit_on=True, limit_amount=100)
    payout = await win_now(money, sam, "dice", 60)  # pays 108 after the 1.8 multiplier: over the limit
    assert payout.held and payout.total == 108 and payout.balance == 1000
    await win_now(money, sam, "dice", 60)
    assert (await store.player(GUILD, 7)).pending == 216
    assert (await win_now(money, sam, "dice", 50)).held is False  # 90 is under the limit


@pytest.mark.asyncio
async def test_releasing_pending_credits(money, store):
    sam = member(7)
    assert (await money.release(GUILD, sam))[1] == "They don't have any credits pending."
    await store.add_pending(GUILD, 7, 300)
    money.bank.maximum = 1100
    assert await money.release(GUILD, sam) == (
        300,
        "That would put them over the bank's maximum balance, so it stays pending.",
    )
    money.bank.maximum = 10_000
    assert await money.release(GUILD, sam) == (300, None)
    assert await money.bank.balance(sam) == 1300 and (await store.player(GUILD, 7)).pending == 0


@pytest.mark.asyncio
async def test_war_bet_comes_back_unmultiplied_and_extra_stakes_need_credits(money):
    sam = member(7)
    payout = await win_now(money, sam, "war", 50, returned=50)
    assert payout.total == 75 and payout.balance == 1125
    assert await money.extra(GUILD, sam, 2000) is False
    assert await money.extra(GUILD, sam, 100) is True and await money.bank.balance(sam) == 1025


def test_time_left_reads_like_the_original():
    assert fmt_seconds(5) == "5 seconds"
    assert fmt_seconds(43200) == "12 hours"
    assert fmt_seconds(3725) == "1 hour, 2 minutes and 5 seconds"
    assert fmt_seconds(61) == "1 minute and 1 second"


@pytest.mark.asyncio
async def test_two_windows_cant_spend_the_same_credits(money):
    sam = member(7)
    money.bank.balances[7] = 600
    results = await asyncio.gather(money.stake(GUILD, sam, "craps", 500), money.stake(GUILD, sam, "blackjack", 500))
    assert sorted(results, key=str) == [None, "You don't have enough credits for that bet."]
    assert await money.bank.balance(sam) == 100


@pytest.mark.asyncio
async def test_affording_the_bet_is_checked_before_the_cooldown(money):
    sam = member(7)
    assert await money.stake(GUILD, sam, "dice", 50) is None
    money.bank.balances[7] = 10
    assert await money.problem(GUILD, sam, "dice", 50) == "You don't have enough credits for that bet."


@pytest.mark.asyncio
async def test_a_release_and_a_hand_assigned_membership_both_survive(money, store):
    sam = member(7)
    gold = await store.save_membership(GUILD, {"name": "Gold"})
    await store.add_pending(GUILD, 7, 300)
    real_deposit = money.bank.deposit

    async def slow_deposit(who, amount):
        await asyncio.sleep(0.05)
        return await real_deposit(who, amount)

    money.bank.deposit = slow_deposit
    await asyncio.gather(money.release(GUILD, sam), store.set_membership(GUILD, 7, gold.id, by_hand=True))
    player = await store.player(GUILD, 7)
    assert player.pending == 0 and player.membership == gold.id and player.by_hand


@pytest.mark.asyncio
async def test_a_player_has_one_lock_across_servers(money):
    assert money.lock(1, 7) is money.lock(2, 7)
