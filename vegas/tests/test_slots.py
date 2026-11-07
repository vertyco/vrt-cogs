import asyncio
import random
from collections import Counter
from fractions import Fraction
from itertools import product

import pytest

from vegas.common.games.slots import (
    JACKPOT_PERCENT,
    SEED_BETS,
    STRIP,
    after_win,
    factor,
    fed,
    is_jackpot,
    line_of,
    read_strength,
    seed,
    share,
    spin,
    spin_seconds,
    window,
)
from vegas.tests.tables_kit import Rigged, until


def every_line_kind() -> dict[str, int]:
    counts = Counter()
    for stops in product(range(len(STRIP)), repeat=3):
        line = line_of(stops)
        cherries = line.count("cherry")
        if is_jackpot(line):
            counts["jackpot"] += 1
        elif line[0] == line[1] == line[2] and line[0] != "blank":
            counts[line[0]] += 1
        elif cherries == 2:
            counts["two cherries"] += 1
        elif cherries == 1:
            counts["one cherry"] += 1
    return {kind: round(len(STRIP) ** 3 / count) for kind, count in counts.items()}


def test_the_strip_has_22_stops_with_the_spec_counts():
    assert len(STRIP) == 22
    assert Counter(STRIP) == {"seven": 1, "diamond": 2, "coin": 3, "bell": 5, "cherry": 4, "blank": 7}


def test_lines_pay_from_the_table():
    assert [factor((s, s, s)) for s in ("diamond", "coin", "bell", "cherry")] == [50, 25, 14, 8]
    assert factor(("cherry", "blank", "cherry")) == 3 and factor(("bell", "cherry", "seven")) == 1
    assert factor(("seven",) * 3) == 0 and is_jackpot(("seven",) * 3) and not is_jackpot(("seven", "seven", "bell"))
    assert factor(("bell", "bell", "coin")) == 0 and factor(("blank",) * 3) == 0


def test_the_payback_is_exact():
    lines = Counter(line_of(stops) for stops in product(range(22), repeat=3))
    table = sum(Fraction(count, 22**3) * factor(line) for line, count in lines.items())
    assert table == Fraction(9817, 10648) and round(float(table), 3) == 0.922
    hit = Fraction(lines[("seven",) * 3], 22**3)
    assert hit == Fraction(1, 10648)
    # At the max bet: the table, the 2% that goes into the pot, and the seed paid once every 10,648 spins
    total = table + Fraction(JACKPOT_PERCENT, 100) + hit * SEED_BETS
    assert total == Fraction(9877, 10648) + Fraction(1, 50) and round(float(total), 3) == 0.948 and total < 1


EVERY = {"jackpot": 10648, "diamond": 1331, "coin": 394, "bell": 85, "cherry": 166, "two cherries": 12, "one cherry": 3}


def test_how_often_each_line_comes_up():
    # 1 in N, rounded: 22**3 divided by how many of the 10,648 lines are each kind (as House rules shows it)
    assert every_line_kind() == EVERY


def test_a_window_shows_the_stop_and_its_neighbours_around_the_strip():
    assert window(0) == [STRIP[21], STRIP[0], STRIP[1]] and window(21) == [STRIP[20], STRIP[21], STRIP[0]]


def test_a_spin_draws_three_stops_from_the_random_source():
    assert spin(Rigged(ints=[0, 21, 9])) == [0, 21, 9]
    assert all(0 <= stop < 22 for stop in spin(random.Random(3)))


def test_the_pull_sets_the_spin_length_and_bad_strengths_are_the_gentlest():
    assert (spin_seconds(0.0), spin_seconds(0.5), spin_seconds(1.0)) == (1.5, 2.75, 4.0)
    for bad in (None, "fast", True, False, float("nan"), float("inf"), float("-inf"), [1], {"x": 1}):
        assert read_strength(bad) == 0.0
    assert (read_strength(-3), read_strength(7), read_strength(0.25), read_strength(1)) == (0.0, 1.0, 0.25, 1.0)


def test_jackpot_math_in_hundredths():
    assert (seed(500), fed(10), fed(500)) == (3_000_000, 20, 1000)
    assert share(3_000_520, 250, 500) == 15_002 and share(3_000_000, 500, 500) == 30_000
    assert share(3_000_000, 750, 500) == 30_000 and share(3_000_000, 10, 500) == 600
    assert share(3_000_000, 0, 500) == 0 and share(3_000_000, 10, 0) == 0
    assert after_win(3_000_520, 15_002, 500) == 3_000_000 and after_win(9_000_000, 600, 500) == 8_940_000


def test_seven_seven_seven_always_beats_three_diamonds():
    for max_bet in (1, 10, 500, 10_000):
        for bet in {1, max(1, max_bet // 2), max_bet}:
            assert share(seed(max_bet), bet, max_bet) > 50 * bet


@pytest.mark.asyncio
async def test_a_spin_shows_its_reels_only_to_the_player_then_pays_the_table(seat):
    host, floor, table, (sam, ana) = await seat("slots", 7, 8, rng=Rigged(ints=[3, 3, 3]))
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: not table.pulls)
    event = sam.last("event")
    assert (event["game"], event["kind"], event["stops"], event["reels"]) == (
        "slots",
        "spin",
        [3, 3, 3],
        [window(3)] * 3,
    )
    assert (event["seconds"], event["strength"]) == (4.0, 1.0) and ana.of("event") == []
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("win", 1400, 2300)


@pytest.mark.asyncio
async def test_one_cherry_gives_the_bet_back_without_counting_a_win(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[2, 1, 1]))
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: not table.pulls)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("push", 100, 1000)
    row = await host.store.player_game(await floor.scope(), 7, "slots")
    assert (row.played, row.won) == (1, 0)


@pytest.mark.asyncio
async def test_the_bot_waits_the_whole_spin_before_paying(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("slots", 7)
    table.speed = 0.2
    waits = []
    pause = table.pause

    async def recorded(seconds):
        waits.append(seconds)
        await pause(seconds)

    monkeypatch.setattr(table, "pause", recorded)
    # The gentlest pull spins 1.5 seconds, 0.3 at this speed
    await table.bet(sam, {"amount": 100, "strength": 0})
    await asyncio.sleep(0.15)
    assert sam.of("event") and sam.of("result") == []
    await until(lambda: sam.of("result"), 2)
    # The spin's own length, not All In's pull pace
    assert waits == [1.5]


@pytest.mark.asyncio
async def test_bad_pulls_are_refused_or_clamped(seat):
    host, floor, table, (sam,) = await seat("slots", 7)
    for amount in (True, "100", 1.5, 0, -5, None):
        await table.bet(sam, {"amount": amount, "strength": 1})
        assert sam.last("notice")["text"] == "Pick an amount to bet.", amount
    for amount in (5, 501):
        await table.bet(sam, {"amount": amount, "strength": 1})
        assert sam.last("notice")["text"] == "Bets here are 10 to 500.", amount
    assert not table.pulls and not table.bets and sam.of("event") == []
    assert await host.money.bank.balance(sam.ctx.author) == 1000
    await table.bet(sam, {"amount": 10, "strength": "fast"})
    await until(lambda: not table.pulls)
    assert sam.last("event")["seconds"] == 1.5
    await table.bet(sam, {"amount": 10, "strength": 9})
    await until(lambda: not table.pulls)
    assert sam.last("event")["seconds"] == 4.0


@pytest.mark.asyncio
async def test_a_second_pull_while_the_reels_spin_is_refused(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[3, 3, 3]))
    table.speed = 0.2
    await table.bet(sam, {"amount": 100, "strength": 1})
    await table.bet(sam, {"amount": 100, "strength": 1})
    assert sam.last("notice")["text"] == "You already bet this round."
    await until(lambda: not table.pulls)
    assert len(sam.of("result")) == 1 and host.money.bank.balances[7] == 2300


@pytest.mark.asyncio
async def test_closing_mid_spin_refunds_the_bet(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[3, 3, 3]))
    table.speed = 1
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: sam.of("event"))
    assert host.money.bank.balances[7] == 900
    await floor.close()
    assert sam.of("result") == [] and host.money.bank.balances[7] == 1000
    assert sam.last("notice")["text"] == "The round stopped, so your bet of 100 came back."
    assert not table.pulls and not table.busy()


@pytest.mark.asyncio
async def test_slots_pays_no_membership_bonus(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[3, 3, 3]))
    scope = await floor.scope()
    gold = await host.store.save_membership(scope, {"name": "Gold", "bonus": 2.0})
    await host.store.set_membership(scope, 7, gold.id, by_hand=True)
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: not table.pulls)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["bonus"]) == ("win", 1400, 0)


@pytest.mark.asyncio
async def test_every_spin_feeds_the_pot_and_the_scope_hears_the_new_amount(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[1, 1, 1]))
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: not table.pulls)
    assert sam.last("result")["outcome"] == "lose"
    assert host.jackpots == [(500, 30_002, None)]
    assert sam.last("jackpot") == {"t": "jackpot", "amount": 30_002, "hit": None}


@pytest.mark.asyncio
async def test_seven_seven_seven_pays_the_bet_share_and_names_the_winner(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[0, 0, 0]))
    await table.bet(sam, {"amount": 250, "strength": 1})
    await until(lambda: not table.pulls)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("jackpot", 15_002, 15_752)
    hit = {"id": "7", "name": "Player7", "amount": 15_002}
    assert host.jackpots[-1] == (500, 30_000, hit)
    assert sam.last("jackpot") == {"t": "jackpot", "amount": 30_000, "hit": hit}
    row = await host.store.player_game(await floor.scope(), 7, "slots")
    assert (row.played, row.won) == (1, 1)


@pytest.mark.asyncio
async def test_the_payout_limit_holds_a_jackpot(seat):
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[0, 0, 0]))
    scope = await floor.scope()
    await host.store.save_casino(scope, limit_on=True, limit_amount=10_000)
    await table.bet(sam, {"amount": 250, "strength": 1})
    await until(lambda: not table.pulls)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["held"]) == ("jackpot", 15_002, True)
    assert (await host.store.player(scope, 7)).pending == 15_002
    assert host.money.bank.balances[7] == 750


@pytest.mark.asyncio
async def test_a_refunded_spin_leaves_the_pot_alone(seat):
    # A losing line, so a pot fed by mistake would read 3,000,200
    host, floor, table, (sam,) = await seat("slots", 7, rng=Rigged(ints=[1, 1, 1]))
    table.speed = 1
    await table.bet(sam, {"amount": 100, "strength": 1})
    await until(lambda: sam.of("event"))
    await floor.close()
    assert sam.of("result") == [] and host.money.bank.balances[7] == 1000
    assert host.jackpots == [] and sam.of("jackpot") == []
    assert await host.store.jackpot(500, 500) == 3_000_000
