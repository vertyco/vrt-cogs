import pytest

from activityhub.bundled.games import bundled_games
from activityhub.common.looks import SettingsError
from activityhub.common.payouts import (
    BALANCE_FULL,
    NONE_LEFT,
    NOTHING_EARNED,
    PAYOUTS_OFF,
    merge_payouts,
    worth,
)
from activityhub.tests.fakes import GUILD_ID, MANAGER_ID, MEMBER_ID, OWNER_ID, context_for, register, session_headers


SNAKE = {"on": True, "rate": 25, "cap": 1000, "plays": 3}


@pytest.fixture
def games(hub):
    for game in bundled_games(hub.scores, hub.payouts):
        assert register(hub, game) is not None
    return hub.payouts.games


async def turn_on(hub, key="snake", **settings):
    saved = await hub.config.guild_from_id(GUILD_ID).payouts()
    saved[key] = {**SNAKE, **settings}
    await hub.config.guild_from_id(GUILD_ID).payouts.set(saved)


def member(hub, user_id=MEMBER_ID):
    return context_for(hub, user_id=user_id).author


# ---------- Rules ----------


def test_worth_is_score_times_rate_up_to_the_cap():
    assert worth(10, {"rate": 25, "cap": 1000}) == 250
    assert worth(100, {"rate": 25, "cap": 1000}) == 1000
    # 2.3 * 100 is 229.99999999999997 in floats
    assert worth(100, {"rate": 2.3, "cap": 1000}) == 230
    assert worth(9, {"rate": 0.1, "cap": 1000}) == 0


def test_saving_checks_every_number(hub, games):
    payout_games = list(hub.payouts.games.values())
    assert merge_payouts({"gone": SNAKE}, {"snake": SNAKE}, payout_games) == {"gone": SNAKE, "snake": SNAKE}
    for bad in (
        {"snake": {**SNAKE, "rate": 0}},
        {"snake": {**SNAKE, "rate": None}},
        {"snake": {**SNAKE, "cap": 1.5}},
        {"snake": {**SNAKE, "plays": 0}},
        {"snake": {**SNAKE, "on": 1}},
        {"snake": {"on": True}},
        {"nope": SNAKE},
        ["snake"],
    ):
        with pytest.raises(SettingsError):
            merge_payouts({}, bad, payout_games)


# ---------- Offers and cash-ins ----------


@pytest.mark.asyncio
async def test_no_offer_until_the_server_turns_payouts_on(hub, games):
    assert await hub.payouts.offer(member(hub), "snake", 10) is None
    assert await hub.payouts.cash_in(member(hub), "snake", 10) == {"error": PAYOUTS_OFF}
    await turn_on(hub)
    offer = await hub.payouts.offer(member(hub), "snake", 10)
    assert offer == {"worth": 250, "left": 3, "plays": 3, "currency": "credits"}


@pytest.mark.asyncio
async def test_each_game_pays_a_few_times_a_day(hub, games):
    await turn_on(hub, plays=2)
    paid = await hub.payouts.cash_in(member(hub), "snake", 10)
    assert paid == {"paid": 250, "left": 1, "balance": 250, "currency": "credits"}
    assert (await hub.payouts.cash_in(member(hub), "snake", 100))["paid"] == 1000
    assert await hub.payouts.cash_in(member(hub), "snake", 10) == {"error": NONE_LEFT}
    assert (await hub.payouts.offer(member(hub), "snake", 10))["left"] == 0
    # Another game has its own cash-ins, and they all come back the next day
    await turn_on(hub, "2048", rate=0.1)
    assert (await hub.payouts.cash_in(member(hub), "2048", 5000))["paid"] == 500
    hub.payouts.today.day = "2026-10-11"
    assert (await hub.payouts.cash_in(member(hub), "snake", 10))["left"] == 1


@pytest.mark.asyncio
async def test_a_worthless_score_or_a_full_balance_keeps_the_cash_in(hub, games):
    await turn_on(hub, plays=1)
    assert await hub.payouts.cash_in(member(hub), "snake", 0) == {"error": NOTHING_EARNED}
    hub.payouts.bank.max_balance = 100
    assert (await hub.payouts.cash_in(member(hub), "snake", 10))["paid"] == 100
    hub.payouts.today.day = "2026-10-11"
    assert await hub.payouts.cash_in(member(hub), "snake", 10) == {"error": BALANCE_FULL}
    assert (await hub.payouts.offer(member(hub), "snake", 10))["left"] == 1


@pytest.mark.asyncio
async def test_a_global_bank_uses_the_owners_settings_and_counts_across_servers(hub, games):
    hub.payouts.bank.global_bank = True
    await turn_on(hub)
    assert await hub.payouts.offer(member(hub), "snake", 10) is None
    await hub.config.payouts.set({"snake": {**SNAKE, "plays": 1}})
    assert (await hub.payouts.cash_in(member(hub), "snake", 10))["paid"] == 250
    assert hub.config.users[MEMBER_ID]["cashed"] == {"day": "2026-10-10", "counts": {"snake": 1}}
    assert GUILD_ID not in hub.config.members


@pytest.mark.asyncio
async def test_a_game_cog_must_send_a_real_score(hub, games):
    with pytest.raises(ValueError):
        await hub.payouts.cash_in(member(hub), "snake", -1)
    with pytest.raises(ValueError):
        await hub.payouts.offer(member(hub), "snake", 1.5)


# ---------- The Payouts tab ----------


async def menu(client, headers):
    resp = await client.get("/hub/api/menu", headers=headers)
    return await resp.json()


async def save(client, headers, payouts):
    resp = await client.post("/hub/api/settings", json={"tab": "payouts", "payouts": payouts}, headers=headers)
    return resp.status, await resp.json()


@pytest.mark.asyncio
async def test_a_manager_sees_and_saves_this_servers_payouts(client, hub, games):
    headers = session_headers(hub, user_id=MANAGER_ID)
    state = await menu(client, headers)
    rows = {row["key"]: row for row in state["payouts"]["games"]}
    assert set(rows) == {"snake", "2048", "brickbreaker"} and state["payouts"]["global"] is False
    assert rows["snake"] == {
        "key": "snake",
        "name": "Snake",
        "unit": "apple",
        "on": False,
        "rate": 25,
        "cap": 1000,
        "plays": 3,
        "defaults": {"on": False, "rate": 25, "cap": 1000, "plays": 3},
    }
    status, state = await save(client, headers, {"snake": {**SNAKE, "rate": 5}})
    assert status == 200
    assert hub.config.guilds[GUILD_ID]["payouts"] == {"snake": {**SNAKE, "rate": 5}}
    assert next(row for row in state["payouts"]["games"] if row["key"] == "snake")["rate"] == 5


@pytest.mark.asyncio
async def test_a_bad_payout_save_changes_nothing(client, hub, games):
    headers = session_headers(hub, user_id=MANAGER_ID)
    status, body = await save(client, headers, {"snake": SNAKE, "2048": {**SNAKE, "plays": 0}})
    assert status == 400 and "cash-ins a day" in body["error"]
    assert hub.config.guilds.get(GUILD_ID, {}).get("payouts", {}) == {}


@pytest.mark.asyncio
async def test_members_cant_set_payouts(client, hub, games):
    headers = session_headers(hub)
    assert (await menu(client, headers))["payouts"] is None
    assert (await save(client, headers, {"snake": SNAKE}))[0] == 403


@pytest.mark.asyncio
async def test_with_a_global_bank_only_the_owner_sets_payouts(client, hub, games):
    hub.payouts.bank.global_bank = True
    manager = session_headers(hub, user_id=MANAGER_ID)
    assert "payouts" not in (await menu(client, manager))["tabs"]
    assert (await save(client, manager, {"snake": SNAKE}))[0] == 403
    owner = session_headers(hub, user_id=OWNER_ID)
    assert (await menu(client, owner))["payouts"]["global"] is True
    assert (await save(client, owner, {"snake": SNAKE}))[0] == 200
    assert hub.config.globals["payouts"] == {"snake": SNAKE}
