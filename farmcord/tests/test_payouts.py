import asyncio
import logging
import math

import pytest
import pytest_asyncio

from farmcord.catalog import CROPS
from farmcord.common.actions import IN_A_SERVER, NOT_AN_ADMIN, NOTHING_TO_CONVERT, PICK_COINS
from farmcord.common.payouts import BALANCE_FULL, DEFAULTS, MAX_CAP, NONE_LEFT, NOTHING_EARNED, PAYOUTS_OFF
from farmcord.tests.fakes import ADMIN_ID, GUILD_ID, OWNER_ID, PLAYER_ID, ctx_for, edit_farm, make_cog

ON = {"on": True, "rate": 1, "cap": 1000, "plays": 3}


@pytest_asyncio.fixture
async def cog(store):
    return await make_cog(store)


async def turn_on(cog, **settings):
    await cog.config.guild_from_id(GUILD_ID).payouts.set({**ON, **settings})


async def farmer(cog, coins: int, user_id: int = PLAYER_ID):
    """A player whose farm holds this many FarmCoins"""
    await cog.act_open(ctx_for(user_id), {})
    await edit_farm(cog, user_id, coins=coins)


async def coins_of(cog, user_id: int = PLAYER_ID) -> int:
    return (await cog.store.load(user_id)).coins


async def ripens_meanwhile(cog):
    """A wildflower sown now, then the clock moved on until it is ripe. The farm's next look reports that as news"""
    me = ctx_for(PLAYER_ID)
    await cog.act_till(me, {"plot": 1, "spot": 0})
    await cog.act_plant(me, {"plot": 1, "spot": 0, "crop": "wildflowers"})
    cog.clock.move(CROPS["wildflowers"].grow_time + 1)


class BrokenLedger:
    """Where cash-ins are counted, failing to save the count"""

    async def __call__(self) -> dict:
        return {}

    async def set(self, value: dict) -> None:
        raise RuntimeError("the cash-in count wasn't saved")


@pytest.mark.asyncio
async def test_payouts_are_off_until_an_admin_turns_them_on(cog):
    assert DEFAULTS == {"on": False, "rate": 1, "cap": 1000, "plays": 3}
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    assert await cog.act_offer(me, {"coins": 100}) == {"offer": None, "reason": PAYOUTS_OFF}
    assert await cog.act_convert(me, {"coins": 100}) == {"error": PAYOUTS_OFF}
    assert await coins_of(cog) == 500 and cog.payouts.bank.balances == {}
    assert (await cog.act_payouts(ctx_for(ADMIN_ID), {}))["settings"] == DEFAULTS


@pytest.mark.asyncio
async def test_a_conversion_takes_only_the_farmcoins_the_cap_pays_for(cog):
    await turn_on(cog, rate=3, cap=1000)
    await farmer(cog, 5000)
    me = ctx_for(PLAYER_ID)
    most = math.ceil(1000 / 3)
    offer = await cog.act_offer(me, {"coins": 5000})
    assert offer == {
        "offer": {"worth": 1000, "left": 3, "plays": 3, "currency": "credits", "coins": most, "most": most},
        "reason": None,
    }
    converted = await cog.act_convert(me, {"coins": 5000})
    assert converted["result"] == {"paid": 1000, "left": 2, "balance": 1000, "currency": "credits", "coins": most}
    assert converted["state"]["player"]["coins"] == 5000 - most and converted["events"] == []
    assert await coins_of(cog) == 5000 - most and cog.payouts.bank.balances == {PLAYER_ID: 1000}


@pytest.mark.asyncio
async def test_a_conversion_never_takes_more_than_the_farm_has(cog):
    await turn_on(cog)
    await farmer(cog, 50)
    me = ctx_for(PLAYER_ID)
    assert (await cog.act_offer(me, {"coins": 1000}))["offer"]["coins"] == 50
    assert (await cog.act_convert(me, {"coins": 1000}))["result"]["paid"] == 50
    assert await coins_of(cog) == 0
    assert await cog.act_convert(me, {"coins": 10}) == {"error": NOTHING_TO_CONVERT}
    assert (await cog.act_offer(me, {"coins": 10}))["offer"]["worth"] == 0


@pytest.mark.asyncio
async def test_two_conversions_at_once_run_one_after_the_other(cog):
    await turn_on(cog)
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    replies = await asyncio.gather(cog.act_convert(me, {"coins": 500}), cog.act_convert(me, {"coins": 500}))
    paid = [reply for reply in replies if "result" in reply]
    assert len(paid) == 1 and paid[0]["result"]["paid"] == 500
    assert [reply for reply in replies if "result" not in reply] == [{"error": NOTHING_TO_CONVERT}]
    assert cog.payouts.bank.balances == {PLAYER_ID: 500} and await coins_of(cog) == 0


@pytest.mark.asyncio
async def test_converting_nothing_is_refused(cog):
    await turn_on(cog)
    await farmer(cog, 50)
    assert await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 0}) == {"error": PICK_COINS}
    assert await coins_of(cog) == 50


@pytest.mark.asyncio
async def test_farmcoins_leave_the_farm_before_the_bank_pays_and_come_back_when_it_refuses(cog):
    await turn_on(cog)
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    saved_while_paying = []

    async def look(member, amount):
        saved_while_paying.append(await coins_of(cog))

    cog.payouts.bank.on_deposit = look
    cog.payouts.bank.max_balance = 0
    assert await cog.act_convert(me, {"coins": 100}) == {"error": BALANCE_FULL}
    assert saved_while_paying == [400] and await coins_of(cog) == 500
    # Nothing was paid, so no cash-in was used up
    assert (await cog.act_offer(me, {"coins": 100}))["offer"]["left"] == 3


@pytest.mark.asyncio
async def test_farmcoins_come_back_when_the_bank_breaks(cog):
    await turn_on(cog)
    await farmer(cog, 500)

    async def broken(member, amount):
        raise RuntimeError("the bank is down")

    cog.payouts.bank.on_deposit = broken
    with pytest.raises(RuntimeError):
        await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 100})
    assert await coins_of(cog) == 500


@pytest.mark.asyncio
async def test_a_paid_cash_in_keeps_the_farmcoins_taken_when_counting_it_fails(cog, caplog):
    """The credits are in the player's balance by then, so the failed count is logged. Raising would hand the FarmCoins
    back too, and the player would be paid twice"""
    await turn_on(cog)
    await farmer(cog, 500)

    async def ledger(member):
        return BrokenLedger()

    cog.payouts.ledger = ledger
    with caplog.at_level(logging.ERROR):
        converted = await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 100})
    assert converted["result"] == {"paid": 100, "left": 2, "balance": 100, "currency": "credits", "coins": 100}
    assert await coins_of(cog) == 400 and cog.payouts.bank.balances == {PLAYER_ID: 100}
    assert "the cash-in count wasn't saved" in caplog.text


@pytest.mark.asyncio
async def test_the_currency_is_named_before_the_bank_pays(cog):
    """A bank that breaks after paying would see the FarmCoins handed back with the credits already paid"""
    await turn_on(cog)
    await farmer(cog, 500)

    async def broken(guild=None):
        raise RuntimeError("the currency has no name")

    cog.payouts.bank.get_currency_name = broken
    with pytest.raises(RuntimeError):
        await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 100})
    assert cog.payouts.bank.balances == {} and await coins_of(cog) == 500


@pytest.mark.asyncio
async def test_a_vanishingly_small_rate_still_gives_a_most_per_cash_in(cog):
    """Any rate above 0 can be saved. Divided into the biggest cap it is endless as a float, and the counter still
    works"""
    await turn_on(cog, rate=1e-300, cap=MAX_CAP)
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    offer = (await cog.act_offer(me, {"coins": 500}))["offer"]
    assert (offer["coins"], offer["worth"], offer["most"]) == (500, 0, 10**12)
    assert await cog.act_convert(me, {"coins": 500}) == {"error": NOTHING_EARNED}
    assert await coins_of(cog) == 500


@pytest.mark.asyncio
@pytest.mark.parametrize("settings, coins, error", [({"plays": 1}, 10, NONE_LEFT), ({"rate": 0.1}, 5, NOTHING_EARNED)])
async def test_a_conversion_the_bank_would_refuse_takes_nothing_and_keeps_the_farms_news(cog, settings, coins, error):
    """Refused before the FarmCoins leave the farm, so nothing is saved: what happened on the farm meanwhile is still
    news for the player's next action"""
    await turn_on(cog, **settings)
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    if error == NONE_LEFT:
        assert (await cog.act_convert(me, {"coins": coins}))["result"]["left"] == 0
    held = await coins_of(cog)
    await ripens_meanwhile(cog)
    assert await cog.act_convert(me, {"coins": coins}) == {"error": error}
    assert await coins_of(cog) == held
    news = (await cog.act_state(me, {}))["events"]
    assert [(event["kind"], event["crop"]) for event in news] == [("ripe", "wildflowers")]


@pytest.mark.asyncio
async def test_a_rate_too_small_to_pay_a_credit_keeps_the_farmcoins(cog):
    await turn_on(cog, rate=0.1)
    await farmer(cog, 500)
    assert await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 5}) == {"error": NOTHING_EARNED}
    assert await coins_of(cog) == 500


@pytest.mark.asyncio
async def test_cash_ins_run_out_for_the_day_and_come_back(cog):
    await turn_on(cog, plays=2)
    await farmer(cog, 500)
    me = ctx_for(PLAYER_ID)
    assert (await cog.act_convert(me, {"coins": 10}))["result"]["left"] == 1
    assert (await cog.act_convert(me, {"coins": 10}))["result"]["left"] == 0
    assert await cog.act_convert(me, {"coins": 10}) == {"error": NONE_LEFT}
    assert await coins_of(cog) == 480
    assert (await cog.act_offer(me, {"coins": 10}))["offer"]["left"] == 0
    cog.payouts.today.day = "2026-10-11"
    assert (await cog.act_convert(me, {"coins": 10}))["result"]["paid"] == 10
    assert await coins_of(cog) == 470 and cog.payouts.bank.balances == {PLAYER_ID: 30}


@pytest.mark.asyncio
async def test_conversions_only_work_in_a_server(cog):
    await turn_on(cog)
    await farmer(cog, 500)
    dm = ctx_for(PLAYER_ID, server=False)
    assert await cog.act_offer(dm, {"coins": 10}) == {"offer": None, "reason": IN_A_SERVER}
    assert await cog.act_convert(dm, {"coins": 10}) == {"error": IN_A_SERVER}
    assert await coins_of(cog) == 500
    # The farm itself plays in a DM
    assert (await cog.act_open(dm, {}))["can_set_payouts"] is False


@pytest.mark.asyncio
async def test_only_server_admins_see_and_change_the_payout_settings(cog):
    player, admin = ctx_for(PLAYER_ID), ctx_for(ADMIN_ID)
    assert (await cog.act_open(player, {}))["can_set_payouts"] is False
    assert (await cog.act_open(admin, {}))["can_set_payouts"] is True
    assert await cog.act_payouts(player, {}) == {"settings": None}
    assert await cog.act_save_payouts(player, {"settings": ON}) == {"error": NOT_AN_ADMIN}
    shown = await cog.act_payouts(admin, {})
    assert shown == {"settings": DEFAULTS, "defaults": DEFAULTS, "global": False, "currency": "credits"}
    saved = await cog.act_save_payouts(admin, {"settings": ON})
    assert saved["settings"] == ON and await cog.config.guild_from_id(GUILD_ID).payouts() == ON
    refused = await cog.act_save_payouts(admin, {"settings": {**ON, "rate": 0}})
    assert refused["error"].startswith("Credits per FarmCoin")
    refused = await cog.act_save_payouts(admin, {"settings": {**ON, "plays": 0}})
    assert "Cash-ins a day" in refused["error"] and await cog.config.guild_from_id(GUILD_ID).payouts() == ON


@pytest.mark.asyncio
async def test_with_a_global_bank_only_the_owner_sets_payouts_and_cash_ins_count_everywhere(cog):
    cog.payouts.bank.global_bank = True
    assert await cog.act_payouts(ctx_for(ADMIN_ID), {}) == {"settings": None}
    assert await cog.act_save_payouts(ctx_for(ADMIN_ID), {"settings": ON}) == {"error": NOT_AN_ADMIN}
    owner = ctx_for(OWNER_ID)
    assert (await cog.act_open(owner, {}))["can_set_payouts"] is True
    assert (await cog.act_save_payouts(owner, {"settings": ON}))["global"] is True
    assert await cog.config.payouts() == ON
    await farmer(cog, 500)
    assert (await cog.act_convert(ctx_for(PLAYER_ID), {"coins": 10}))["result"]["paid"] == 10
    assert (await cog.config.user_from_id(PLAYER_ID).cashed())["count"] == 1
