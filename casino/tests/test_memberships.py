import pytest

from casino.common.memberships import BASIC, Updater, clean_membership, open_tier_warning, perks_for
from casino.tests.fakes import FakeBank, FakeBot, FakeGuild, member
from casino.views.tiers import open_warning

GUILD = 500


@pytest.fixture
def world(store):
    bot = FakeBot()
    guild = FakeGuild(GUILD)
    bot.guilds[GUILD] = guild
    bank = FakeBank(start=1000)
    return bot, guild, bank, Updater(bot, store, bank)


async def tier(store, name, access, scope=GUILD, **reqs):
    fields, problem = clean_membership({"name": name, "access": access, **reqs}, [])
    assert problem is None
    return await store.save_membership(scope, fields)


@pytest.mark.asyncio
async def test_the_highest_access_tier_a_player_meets_wins(store, world):
    bot, guild, bank, updater = world
    guild.add(7, roles=[900], days=40)
    await store.player(GUILD, 7)
    await tier(store, "Silver", 1, req_credits=500)
    gold = await tier(store, "Gold", 2, req_role_id=900, req_days=30)
    await tier(store, "Diamond", 3, req_credits=5000)
    await updater.run_once()
    assert (await perks_for(store, GUILD, 7)).name == "Gold"
    assert (await store.player(GUILD, 7)).membership == gold.id


@pytest.mark.asyncio
async def test_days_requirements_dont_crash_and_count_days_in_the_server(store, world):
    bot, guild, bank, updater = world
    guild.add(7, days=5)
    await store.player(GUILD, 7)
    await tier(store, "Regular", 1, req_days=10)
    await updater.run_once()
    assert await perks_for(store, GUILD, 7) == BASIC


@pytest.mark.asyncio
async def test_tiers_given_by_hand_are_left_alone(store, world):
    bot, guild, bank, updater = world
    guild.add(7)
    await tier(store, "Open", 1)
    vip = await tier(store, "VIP", 0, req_credits=10**9)
    await store.set_membership(GUILD, 7, vip.id, by_hand=True)
    await updater.run_once()
    assert (await perks_for(store, GUILD, 7)).name == "VIP"


@pytest.mark.asyncio
async def test_global_mode_ignores_roles_and_counts_account_age(store, world):
    bot, guild, bank, updater = world
    bot.users[7] = member(7, days=5)  # account made 105 days ago
    await store.set_global_mode(True)
    await store.player(0, 7)
    await tier(store, "Veteran", 1, scope=0, req_days=100, req_role_id=999)
    await updater.run_once()
    assert (await perks_for(store, 0, 7)).name == "Veteran"


@pytest.mark.asyncio
async def test_players_the_bot_cant_see_are_skipped(store, world):
    bot, guild, bank, updater = world
    await store.player(GUILD, 8)
    await tier(store, "Open", 1)
    await updater.run_once()
    assert (await store.player(GUILD, 8)).membership is None


def test_membership_fields_are_checked():
    assert clean_membership({"name": "Gold!"}, [])[1] == "Names are 1 to 32 letters, digits, spaces or hyphens."
    assert clean_membership({"name": "gold"}, ["Gold"])[1] == "There's already a membership named gold."
    assert clean_membership({"name": "Gold", "color": "beige"}, [])[1].startswith("Pick a color from: blue")
    assert clean_membership({"name": "Gold", "access": "x"}, [])[1].startswith("Access, reduction")
    assert clean_membership({"name": "Gold", "bonus": 0}, [])[1].startswith("The bonus multiplier")
    fields, problem = clean_membership({"name": "Gold", "access": 0, "reduction": 0, "req_credits": ""}, [])
    assert problem is None and fields["access"] == 0 and fields["req_credits"] is None


@pytest.mark.asyncio
async def test_one_failing_scope_doesnt_stop_the_others(store, world):
    bot, guild, bank, updater = world
    bot.guilds[600] = FakeGuild(600)
    bot.guilds[600].add(7)
    guild.add(7)
    for scope in (GUILD, 600):
        await store.player(scope, 7)
        await tier(store, "Open", 1, scope=scope)
    real = updater.update_scope

    async def flaky(scope, global_mode):
        if scope == GUILD:
            raise RuntimeError("boom")
        await real(scope, global_mode)

    updater.update_scope = flaky
    await updater.run_once()
    assert (await store.player(600, 7)).membership is not None


@pytest.mark.asyncio
async def test_a_membership_given_by_hand_during_an_update_is_kept(store, world):
    bot, guild, bank, updater = world
    guild.add(7)
    await store.player(GUILD, 7)
    await tier(store, "Open", 1)
    vip = await tier(store, "VIP", 0, req_credits=10**9)
    real = bank.balance

    async def balance_while_an_admin_assigns(who):
        # The admin gives VIP by hand while the updater is still checking the player
        await store.assign_membership(GUILD, 7, vip.id)
        return await real(who)

    bank.balance = balance_while_an_admin_assigns
    await updater.run_once()
    player = await store.player(GUILD, 7)
    assert player.membership == vip.id and player.by_hand is True


def test_the_designer_warns_only_about_memberships_everyone_gets():
    nothing = {"req_credits": None, "req_role_id": None, "req_days": 0}
    assert open_warning(nothing, GUILD) == open_tier_warning()
    assert open_warning({**nothing, "req_credits": 10}, GUILD) is None
    assert open_warning({**nothing, "req_role_id": "900"}, GUILD) is None
    # Global mode (scope 0) ignores roles, so a role alone still lets everyone in
    assert open_warning({**nothing, "req_role_id": "900"}, 0) == open_tier_warning()


def test_numbers_the_database_cant_hold_are_refused():
    assert clean_membership({"name": "Gold", "req_credits": 2**63}, [])[1] == "That number is too large."
    assert clean_membership({"name": "Gold", "req_role_id": -(2**64)}, [])[1] == "That number is too large."
    assert clean_membership({"name": "Gold", "req_days": float("inf")}, [])[1].startswith("Access, reduction")
    assert clean_membership({"name": "Gold", "req_credits": 2**63 - 1}, [])[1] is None
