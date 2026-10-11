import pytest

from activityhub.bundled.games import bundled_games
from activityhub.common.payouts import (
    BALANCE_FULL,
    NONE_LEFT,
    NOT_AN_ADMIN,
    NOTHING_EARNED,
    PAYOUTS_OFF,
    worth,
)
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    GUILD_OWNER_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    context_for,
    register,
    session_headers,
)


SNAKE = {"on": True, "rate": 25, "cap": 1000, "plays": 3}
SNAKE_DEFAULTS = {"on": False, "rate": 25, "cap": 1000, "plays": 3}


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


# ---------- Each game's settings dialog ----------


async def dialog(client, hub, key="snake", **who):
    resp = await client.post(f"/games/{key}/api/payouts", json={}, headers=session_headers(hub, **who))
    assert resp.status == 200
    return await resp.json()


async def save(client, hub, settings, key="snake", **who):
    body = {"settings": settings}
    resp = await client.post(f"/games/{key}/api/save_payouts", json=body, headers=session_headers(hub, **who))
    return resp.status, await resp.json()


def saved_here(hub) -> dict:
    return hub.config.guilds.get(GUILD_ID, {}).get("payouts", {})


@pytest.mark.asyncio
async def test_a_manager_sees_the_games_own_settings(client, hub, games):
    assert await dialog(client, hub, user_id=MANAGER_ID) == {
        "settings": SNAKE_DEFAULTS,
        "defaults": SNAKE_DEFAULTS,
        "global": False,
        "currency": "credits",
        "unit": "apple",
        "name": "Snake",
    }
    state = await dialog(client, hub, key="2048", user_id=MANAGER_ID)
    assert state["unit"] == "point" and state["name"] == "2048" and state["defaults"]["rate"] == 0.1


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [MANAGER_ID, ADMIN_ID, GUILD_OWNER_ID, OWNER_ID])
async def test_server_admins_and_the_bot_owner_set_payouts(client, hub, games, user_id):
    assert (await dialog(client, hub, user_id=user_id))["settings"] == SNAKE_DEFAULTS
    status, state = await save(client, hub, {**SNAKE, "rate": 5}, user_id=user_id)
    assert status == 200 and state["settings"] == {**SNAKE, "rate": 5} and state["name"] == "Snake"
    assert saved_here(hub) == {"snake": {**SNAKE, "rate": 5}}


@pytest.mark.asyncio
async def test_the_server_owner_counts_without_the_member_cache(client, hub, games):
    del hub.bot.guilds[GUILD_ID].members[GUILD_OWNER_ID]
    assert (await dialog(client, hub, user_id=GUILD_OWNER_ID))["settings"] == SNAKE_DEFAULTS
    assert (await save(client, hub, SNAKE, user_id=GUILD_OWNER_ID))[0] == 200


@pytest.mark.asyncio
async def test_members_cant_see_or_save_payouts(client, hub, games):
    assert await dialog(client, hub) == {"settings": None}
    assert await save(client, hub, SNAKE) == (400, {"error": NOT_AN_ADMIN})
    assert saved_here(hub) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [MANAGER_ID, OWNER_ID])
async def test_nobody_sets_payouts_from_a_dm(client, hub, games, user_id):
    assert await dialog(client, hub, user_id=user_id, guild_id=None) == {"settings": None}
    assert await save(client, hub, SNAKE, user_id=user_id, guild_id=None) == (400, {"error": NOT_AN_ADMIN})


@pytest.mark.asyncio
async def test_with_a_global_bank_only_the_owner_sets_payouts(client, hub, games):
    hub.payouts.bank.global_bank = True
    assert await dialog(client, hub, user_id=MANAGER_ID) == {"settings": None}
    assert await save(client, hub, SNAKE, user_id=MANAGER_ID) == (400, {"error": NOT_AN_ADMIN})
    assert (await dialog(client, hub, user_id=OWNER_ID))["global"] is True
    status, state = await save(client, hub, SNAKE, user_id=OWNER_ID)
    assert status == 200 and state["settings"] == SNAKE and state["global"] is True
    assert hub.config.globals["payouts"] == {"snake": SNAKE} and saved_here(hub) == {}


@pytest.mark.asyncio
async def test_with_a_global_bank_the_owner_sets_payouts_from_a_dm(client, hub, games):
    # The settings apply in every server, so the owner needs no server to change them
    hub.payouts.bank.global_bank = True
    state = await dialog(client, hub, user_id=OWNER_ID, guild_id=None)
    assert state["settings"] == SNAKE_DEFAULTS and state["global"] is True and state["currency"] == "credits"
    status, state = await save(client, hub, {**SNAKE, "cap": 400}, user_id=OWNER_ID, guild_id=None)
    assert status == 200 and state["settings"] == {**SNAKE, "cap": 400}
    assert hub.config.globals["payouts"] == {"snake": {**SNAKE, "cap": 400}}
    # Anyone else in a DM still gets nothing
    assert await dialog(client, hub, user_id=MANAGER_ID, guild_id=None) == {"settings": None}


@pytest.mark.asyncio
async def test_each_save_checks_again(client, hub, games):
    assert (await dialog(client, hub, user_id=MANAGER_ID))["settings"] is not None
    hub.bot.guilds[GUILD_ID].members[MANAGER_ID].guild_permissions.manage_guild = False
    assert await save(client, hub, SNAKE, user_id=MANAGER_ID) == (400, {"error": NOT_AN_ADMIN})
    assert saved_here(hub) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad, says",
    [
        ({**SNAKE, "rate": 0}, "the rate must be more than 0"),
        ({**SNAKE, "rate": None}, "the rate must be more than 0"),
        ({**SNAKE, "cap": 1.5}, "the most per cash-in must be a whole number"),
        ({**SNAKE, "plays": 0}, "cash-ins a day must be a whole number"),
        ({**SNAKE, "on": 1}, "on must be true or false"),
        ({"on": True}, "expected on, rate, cap and plays"),
        (["snake"], "expected on, rate, cap and plays"),
        (None, "expected on, rate, cap and plays"),
    ],
)
async def test_a_bad_number_is_refused_and_nothing_is_saved(client, hub, games, bad, says):
    status, body = await save(client, hub, bad, user_id=MANAGER_ID)
    assert status == 400 and body["error"].startswith("Snake: ") and says in body["error"]
    assert saved_here(hub) == {}


@pytest.mark.asyncio
async def test_saving_one_game_leaves_the_others_alone(client, hub, games):
    twenty48 = {"on": True, "rate": 0.5, "cap": 200, "plays": 5}
    await hub.config.guild_from_id(GUILD_ID).payouts.set({"2048": twenty48, "gone": SNAKE})
    assert (await save(client, hub, {**SNAKE, "plays": 9}, user_id=MANAGER_ID))[0] == 200
    assert saved_here(hub) == {"2048": twenty48, "gone": SNAKE, "snake": {**SNAKE, "plays": 9}}


@pytest.mark.asyncio
async def test_settings_saved_before_are_read_back_unchanged(client, hub, games):
    # Stored the same way since payouts began: per server, by game key, with on, rate, cap and plays
    earlier = {"snake": {"on": True, "rate": 2.5, "cap": 500, "plays": 7}}
    await hub.config.guild_from_id(GUILD_ID).payouts.set(earlier)
    assert (await dialog(client, hub, user_id=MANAGER_ID))["settings"] == earlier["snake"]
    assert (await dialog(client, hub, key="2048", user_id=MANAGER_ID))["settings"]["on"] is False
    hub.payouts.bank.global_bank = True
    await hub.config.payouts.set({"2048": {"on": True, "rate": 3, "cap": 90, "plays": 2}})
    owner = await dialog(client, hub, key="2048", user_id=OWNER_ID)
    assert owner["settings"] == {"on": True, "rate": 3, "cap": 90, "plays": 2}
