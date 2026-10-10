import asyncio

import pytest

from casino.common.catalog import GAMES
from casino.db.tables import GameSettings

GUILD = 500


@pytest.mark.asyncio
async def test_a_new_casino_has_the_originals_defaults(store):
    casino = await store.casino(GUILD)
    assert (casino.name, casino.is_open, casino.limit_on, casino.limit_amount) == ("Redjumpman's", True, False, 10000)
    games = await store.games(GUILD)
    assert list(games) == list(GAMES)
    assert (games["coin"].min_bet, games["coin"].max_bet, games["coin"].multiplier) == (10, 10, 1.5)
    assert (games["allin"].cooldown, games["allin"].min_bet, games["allin"].multiplier) == (43200, None, None)
    assert games["double"].multiplier is None and games["blackjack"].max_bet == 500


@pytest.mark.asyncio
async def test_rows_are_made_once_even_when_asked_for_at_the_same_time(store):
    await asyncio.gather(*(store.games(GUILD) for _ in range(5)), *(store.player(GUILD, 7) for _ in range(5)))
    assert len(await store.players(GUILD)) == 1
    assert await GameSettings.count().where(GameSettings.scope == GUILD) == len(GAMES)


@pytest.mark.asyncio
async def test_global_mode_reads_scope_zero_and_keeps_server_data(store):
    await store.save_casino(GUILD, name="Lucky")
    assert await store.scope_for(GUILD) == GUILD
    await store.set_global_mode(True)
    assert await store.scope_for(GUILD) == 0
    assert (await store.casino(0)).name == "Redjumpman's"
    await store.set_global_mode(False)
    assert (await store.casino(await store.scope_for(GUILD))).name == "Lucky"


@pytest.mark.asyncio
async def test_deleting_a_membership_makes_its_players_basic(store):
    gold = await store.save_membership(GUILD, {"name": "Gold", "color": "yellow", "access": 2})
    await store.set_membership(GUILD, 7, gold.id, by_hand=True)
    await store.delete_membership(GUILD, gold.id)
    player = await store.player(GUILD, 7)
    assert player.membership is None and player.by_hand is False
    assert await store.memberships(GUILD) == []


@pytest.mark.asyncio
async def test_player_resets_clear_only_what_was_asked(store):
    games = await store.player_games(GUILD, 7)
    games["dice"].played, games["dice"].won, games["dice"].ready_at = 4, 2, 999.0
    await games["dice"].save()
    await store.reset_player(GUILD, 7, "cooldowns")
    row = await store.player_game(GUILD, 7, "dice")
    assert (row.played, row.won, row.ready_at) == (4, 2, 0.0)
    await store.reset_player(GUILD, 7, "stats")
    row = await store.player_game(GUILD, 7, "dice")
    assert (row.played, row.won) == (0, 0)
    await store.add_pending(GUILD, 7, 50)
    await store.reset_player(GUILD, 7, "all")
    assert (await store.player(GUILD, 7)).pending == 0


@pytest.mark.asyncio
async def test_resetting_the_casino_keeps_player_stats(store):
    await store.save_casino(GUILD, name="Lucky")
    await store.save_game(GUILD, "dice", max_bet=900)
    row = await store.player_game(GUILD, 7, "dice")
    row.played, row.ready_at = 3, 999.0
    await row.save()
    await store.reset_casino(GUILD, "all")
    assert (await store.casino(GUILD)).name == "Redjumpman's"
    assert (await store.game(GUILD, "dice")).max_bet == 100
    row = await store.player_game(GUILD, 7, "dice")
    assert (row.played, row.ready_at) == (3, 0.0)


@pytest.mark.asyncio
async def test_wipe_and_delete_user(store):
    await store.set_global_mode(True)
    await store.add_pending(GUILD, 7, 50)
    await store.add_pending(GUILD, 8, 60)
    await store.delete_user(7)
    assert [p.user_id for p in await store.players(GUILD)] == [8]
    await store.wipe()
    assert await store.players(GUILD) == [] and await store.global_mode() is False


@pytest.mark.asyncio
async def test_assigning_a_membership_does_not_wait_on_its_own_lock(store):
    gold = await store.save_membership(GUILD, {"name": "Gold", "color": "yellow", "access": 2})
    # The row exists when the assignment starts and is gone by the time it gets the lock, so a helper that makes the
    # row again inside the lock would wait on the lock it already holds
    await store.player(GUILD, 99)
    await store.lock.acquire()
    assign = asyncio.create_task(store.assign_membership(GUILD, 99, gold.id))
    await asyncio.sleep(0.05)
    await store.reset_player(GUILD, 99, "all")
    store.lock.release()
    assert await asyncio.wait_for(assign, 5) is True
    assert (await asyncio.wait_for(store.player(GUILD, 99), 5)).membership == gold.id
