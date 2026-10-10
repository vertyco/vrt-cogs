"""Craps, War and Double or Nothing: shared rolls, ties and flips, decisions and their defaults"""

import pytest

from casino.tests.tables_kit import Rigged, round_over, until


@pytest.mark.asyncio
async def test_craps_point_is_made_on_the_one_extra_roll(seat):
    host, floor, table, (sam,) = await seat("craps", 7, rng=Rigged(ints=[4, 4, 5, 3]))
    await table.bet(sam, {"amount": 50})
    await until(lambda: 7 in table.decisions)
    assert sam.last("table")["shooter"] == "7" and sam.last("table")["waiting"] == ["7"]
    await table.move(sam, {"move": "roll"})
    await until(lambda: table.point == 8 and 7 in table.decisions)
    await table.move(sam, {"move": "roll"})
    await round_over(table)
    assert [e["dice"] for e in sam.of("event")] == [[4, 4], [5, 3]]
    assert sam.last("result")["payout"] == 100


@pytest.mark.asyncio
async def test_craps_rolls_for_a_slow_shooter_and_pays_triple_on_a_come_out_seven(seat):
    host, floor, table, (sam,) = await seat("craps", 7, rng=Rigged(ints=[3, 4]))
    table.times["shooter"] = 0.01
    await table.bet(sam, {"amount": 50})
    await round_over(table)
    assert sam.last("result")["payout"] == 300  # 50 x 3 x 2.0


@pytest.mark.asyncio
async def test_the_dice_pass_to_the_next_player(seat):
    host, floor, table, (sam, ana) = await seat("craps", 7, 8, rng=Rigged(ints=[3, 4, 3, 4]))
    table.times["shooter"] = 0.01
    shooters = []
    for _ in range(2):
        await table.bet(sam, {"amount": 50})
        await table.bet(ana, {"amount": 50})
        await table.press_go(sam)
        await until(lambda: table.shooter is not None)
        shooters.append(table.shooter)
        await round_over(table)
        host.money.clock.now += 5
    assert shooters == [7, 8]


@pytest.mark.asyncio
async def test_war_tie_going_to_war_wins_the_multiplied_stake_plus_the_war_bet(seat):
    host, floor, table, (sam,) = await seat("war", 7)
    # Drawn from the end: Sam's 9, the dealer's 9, three burned, Sam's K, the dealer's 4
    table.deck.cards = [
        ("4", "clubs"),
        ("K", "hearts"),
        ("2", "c"),
        ("3", "c"),
        ("5", "c"),
        ("9", "clubs"),
        ("9", "spades"),
    ]
    await table.bet(sam, {"amount": 50})
    await until(lambda: 7 in table.decisions)
    await table.move(sam, {"move": "war"})
    await round_over(table)
    assert [e["kind"] for e in sam.of("event")] == ["deal", "deal", "burn", "deal", "deal"]
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["returned"], result["balance"]) == ("win", 75, 50, 1025)


@pytest.mark.asyncio
async def test_war_surrender_gives_back_half_and_is_the_default(seat):
    host, floor, table, (sam,) = await seat("war", 7)
    table.times["decision"] = 0.01
    table.deck.cards = [("9", "clubs"), ("9", "spades")]
    await table.bet(sam, {"amount": 51})
    await round_over(table)
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("surrender", 25, 974)


@pytest.mark.asyncio
async def test_war_is_only_offered_to_players_who_can_cover_it(seat):
    host, floor, table, (sam,) = await seat("war", 7)
    table.deck.cards = [("9", "h"), ("9", "c")]
    host.money.bank.balances[7] = 60
    table.times["decision"] = 0.2
    await table.bet(sam, {"amount": 50})
    await until(lambda: sam.of("ask"))
    assert sam.last("ask")["moves"] == ["surrender"]
    # Refused, so the time runs out and the default, surrender, stands
    await table.move(sam, {"move": "war"})
    await round_over(table)
    assert sam.last("result")["outcome"] == "surrender"


@pytest.mark.asyncio
async def test_double_or_nothing_everyone_rides_the_same_flips(seat):
    rng = Rigged(picks=["heads", "heads", "tails"])
    host, floor, table, (sam, ana) = await seat("double", 7, 8, rng=rng)
    await table.bet(sam, {"amount": 10})
    await table.bet(ana, {"amount": 10})
    await table.press_go(sam)
    await until(lambda: len(table.decisions) == 2)
    await table.move(sam, {"move": "cashout"})
    await table.move(ana, {"move": "keep"})
    await until(lambda: 8 in table.decisions and len(table.flips) == 2)
    await table.move(ana, {"move": "keep"})
    await round_over(table)
    assert sam.last("result")["payout"] == 20
    assert ana.last("result")["outcome"] == "lose" and ana.last("result")["balance"] == 990


@pytest.mark.asyncio
async def test_a_player_who_leaves_mid_decision_takes_the_default_after_a_short_grace(seat):
    host, floor, table, (sam, ann) = await seat("war", 7, 8)
    table.times["grace"] = 0.05
    # Drawn from the end: Sam's 9, Ann's 2, the dealer's 9. Sam ties, Ann loses
    table.deck.cards = [("9", "h"), ("2", "c"), ("9", "c")]
    await table.bet(sam, {"amount": 50})
    await table.bet(ann, {"amount": 50})
    await table.press_go(sam)
    await until(lambda: sam.of("ask"))
    await floor.depart(sam)
    # The table doesn't wait out Sam's 35 seconds: surrender stands, half comes back
    await round_over(table)
    assert await host.money.bank.balance(sam.ctx.author) == 975


@pytest.mark.asyncio
async def test_craps_missed_point_loses_after_exactly_one_extra_roll(seat):
    host, floor, table, (sam,) = await seat("craps", 7, rng=Rigged(ints=[4, 4, 1, 2]))
    table.times["shooter"] = 0.01
    await table.bet(sam, {"amount": 50})
    await round_over(table)
    assert [e["dice"] for e in sam.of("event")] == [[4, 4], [1, 2]]
    result = sam.last("result")
    assert (result["outcome"], result["payout"], result["balance"]) == ("lose", 0, 950)


@pytest.mark.asyncio
async def test_war_bet_comes_back_when_the_table_closes_mid_war(seat):
    host, floor, table, (sam,) = await seat("war", 7)
    table.deck.cards = [("9", "clubs"), ("9", "spades")]
    money = host.money
    taken = money.extra

    async def extra_then_close(*args):
        paid = await taken(*args)
        table.closing.set()
        return paid

    money.extra = extra_then_close
    await table.bet(sam, {"amount": 50})
    await until(lambda: 7 in table.decisions)
    await table.move(sam, {"move": "war"})
    await round_over(table)
    assert await money.bank.balance(sam.ctx.author) == 1000


def table_before(conn, kind: str, nth: int = 0) -> dict:
    """The last table state this connection got before the nth event of this kind"""
    seen, last = 0, None
    for message in conn.sent:
        if message.get("t") == "event" and message["kind"] == kind:
            if seen == nth:
                return last
            seen += 1
        elif message.get("t") == "table":
            last = message
    raise AssertionError(f"No {kind} event number {nth}")


@pytest.mark.asyncio
async def test_double_or_nothing_shows_a_cash_out_before_the_next_flip(seat):
    rng = Rigged(picks=["heads", "heads", "tails"])
    host, floor, table, (sam, ana) = await seat("double", 7, 8, rng=rng)
    await table.bet(sam, {"amount": 10})
    await table.bet(ana, {"amount": 10})
    await table.press_go(sam)
    await until(lambda: len(table.decisions) == 2)
    await table.move(sam, {"move": "cashout"})
    await table.move(ana, {"move": "keep"})
    await until(lambda: 8 in table.decisions and len(table.flips) == 2)
    await table.move(ana, {"move": "keep"})
    await round_over(table)
    assert table_before(ana, "flip", 1)["standing"]["7"]["status"] == "out"


@pytest.mark.asyncio
async def test_war_shows_a_surrender_before_the_burn(seat):
    host, floor, table, (sam, ann) = await seat("war", 7, 8)
    # Drawn from the end: Sam's 9, Ann's 9, the dealer's 9, three burned, Sam's K, the dealer's 4
    table.deck.cards = [
        ("4", "clubs"),
        ("K", "hearts"),
        ("2", "c"),
        ("3", "c"),
        ("5", "c"),
        ("9", "clubs"),
        ("9", "diamonds"),
        ("9", "spades"),
    ]
    await table.bet(sam, {"amount": 50})
    await table.bet(ann, {"amount": 50})
    await table.press_go(sam)
    await until(lambda: len(table.decisions) == 2)
    await table.move(sam, {"move": "war"})
    await table.move(ann, {"move": "surrender"})
    await round_over(table)
    assert table_before(sam, "burn")["hands"]["8"]["status"] == "surrender"
