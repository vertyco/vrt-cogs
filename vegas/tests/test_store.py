import asyncio
import sqlite3

import pytest

from vegas.common.catalog import GAMES
from vegas.common.info import casino_info
from vegas.db.tables import GameSettings, HoldemStack

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
    games["dice"].played, games["dice"].won, games["dice"].played_at = 4, 2, 999.0
    await games["dice"].save()
    await store.reset_player(GUILD, 7, "cooldowns")
    row = await store.player_game(GUILD, 7, "dice")
    assert (row.played, row.won, row.played_at) == (4, 2, 0.0)
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
    row.played, row.played_at = 3, 999.0
    await row.save()
    await store.reset_casino(GUILD, "all")
    assert (await store.casino(GUILD)).name == "Redjumpman's"
    assert (await store.game(GUILD, "dice")).max_bet == 100
    row = await store.player_game(GUILD, 7, "dice")
    assert (row.played, row.played_at) == (3, 0.0)


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


@pytest.mark.asyncio
async def test_stacks_save_update_and_clear(store):
    await store.save_stack(GUILD, GUILD, 7, 400)
    await store.save_stack(GUILD, GUILD, 7, 900)
    assert await store.stacked(GUILD, 7) == 900
    assert await HoldemStack.count() == 1
    assert [(row.scope, row.user_id, row.amount) for row in await store.stacks()] == [(GUILD, 7, 900)]
    await store.save_stack(GUILD, GUILD, 7, 0)
    assert await store.stacked(GUILD, 7) == 0 and await HoldemStack.count() == 0


@pytest.mark.asyncio
async def test_stacks_saved_together_are_all_written_or_none_are(store):
    await store.save_stack(GUILD, GUILD, 7, 400)
    await store.save_stacks([(GUILD, GUILD, 7, 0), (GUILD, GUILD, 8, 900), (GUILD, GUILD, 9, 300)])
    assert sorted((row.user_id, row.amount) for row in await store.stacks()) == [(8, 900), (9, 300)]
    # The second row can't be written, so the first one isn't either
    with pytest.raises(sqlite3.IntegrityError):
        await store.save_stacks([(GUILD, GUILD, 8, 100), (GUILD, GUILD, None, 5)])
    assert sorted((row.user_id, row.amount) for row in await store.stacks()) == [(8, 900), (9, 300)]


@pytest.mark.asyncio
async def test_deleting_a_user_deletes_their_stacks(store):
    await store.save_stack(GUILD, GUILD, 7, 400)
    await store.save_stack(GUILD, GUILD, 8, 500)
    await store.delete_user(7)
    assert [row.user_id for row in await store.stacks()] == [8]


@pytest.mark.asyncio
async def test_wipe_and_reset_casino_leave_stacks_alone(store):
    await store.save_stack(GUILD, GUILD, 7, 400)
    await store.reset_casino(GUILD, "all")
    assert await store.stacked(GUILD, 7) == 400
    await store.wipe()
    assert await store.stacked(GUILD, 7) == 400


@pytest.mark.asyncio
async def test_a_new_scope_gets_holdem_with_its_defaults(store):
    holdem = (await store.games(GUILD))["holdem"]
    assert (holdem.cut, holdem.min_bet, holdem.max_bet, holdem.cooldown) == (5.0, 400, 2000, 0)
    assert holdem.multiplier is None and "holdem" in await store.games(GUILD)


@pytest.mark.asyncio
async def test_a_new_scope_gets_slots_with_its_defaults(store):
    games = await store.games(GUILD)
    slots = games["slots"]
    assert (slots.min_bet, slots.max_bet, slots.cooldown, slots.access, slots.multiplier) == (10, 500, 0, 0, None)
    assert list(games)[-1] == "slots"


@pytest.mark.asyncio
async def test_the_jackpot_starts_at_its_seed_and_grows_by_2_percent_of_each_bet(store):
    assert await store.jackpot(GUILD, 500) == 3_000_000
    assert await store.spin_jackpot(GUILD, 10, 500, False) == (3_000_020, 0)
    assert await store.jackpot(GUILD, 500) == 3_000_020


@pytest.mark.asyncio
async def test_a_jackpot_pays_the_bet_share_and_tops_the_pot_back_up(store):
    assert await store.spin_jackpot(GUILD, 250, 500, True) == (3_000_000, 15_002)
    assert await store.spin_jackpot(GUILD, 500, 500, True) == (3_000_000, 30_010)


@pytest.mark.asyncio
async def test_a_raised_max_bet_reads_the_pot_at_its_new_seed_and_only_a_spin_keeps_it(store):
    assert await store.jackpot(GUILD, 500) == 3_000_000
    assert await store.jackpot(GUILD, 1000) == 6_000_000
    assert await store.jackpot(GUILD, 500) == 3_000_000
    await store.spin_jackpot(GUILD, 10, 1000, False)
    assert await store.jackpot(GUILD, 500) == 6_000_020


@pytest.mark.asyncio
async def test_a_max_bet_typo_shows_a_big_pot_but_never_saves_it(store):
    await store.save_game(GUILD, "slots", max_bet=50_000)
    assert (await casino_info(store, GUILD))["games"]["slots"]["jackpot"] == 3_000_000
    await store.save_game(GUILD, "slots", max_bet=500)
    assert (await casino_info(store, GUILD))["games"]["slots"]["jackpot"] == 30_000
    assert await store.saved_jackpot(GUILD) != 300_000_000


@pytest.mark.asyncio
async def test_resetting_games_keeps_the_jackpot_and_a_full_reset_or_wipe_reseeds_it(store):
    assert await store.spin_jackpot(GUILD, 100, 500, False) == (3_000_200, 0)
    await store.save_game(GUILD, "slots", max_bet=900)
    await store.reset_casino(GUILD, "games")
    assert (await store.game(GUILD, "slots")).max_bet == 500
    assert await store.jackpot(GUILD, 500) == 3_000_200
    await store.reset_casino(GUILD, "all")
    assert await store.jackpot(GUILD, 500) == 3_000_000
    await store.spin_jackpot(GUILD, 100, 500, False)
    await store.wipe()
    assert await store.jackpot(GUILD, 500) == 3_000_000


@pytest.mark.asyncio
async def test_spins_at_the_same_time_lose_no_credit(store):
    await asyncio.gather(*(store.spin_jackpot(GUILD, 10, 500, False) for _ in range(20)))
    assert await store.jackpot(GUILD, 500) == 3_000_400
    both = await asyncio.gather(*(store.spin_jackpot(GUILD, 500, 500, True) for _ in range(2)))
    assert sorted(paid for _, paid in both) == [30_010, 30_014]
    assert await store.jackpot(GUILD, 500) == 3_000_000


@pytest.mark.asyncio
async def test_saving_a_game_setting_never_undoes_a_spin_paid_meanwhile(store, monkeypatch):
    await store.spin_jackpot(GUILD, 500, 500, False)
    read = store.game
    armed = [True]
    spun = []

    async def read_then_spin(scope, key):
        row = await read(scope, key)
        if key == "slots" and armed[0]:
            armed[0] = False
            # A 7-7-7 at the max bet pays between save_game's read and its write
            spun.append(await store.spin_jackpot(scope, 500, 500, True))
        return row

    monkeypatch.setattr(store, "game", read_then_spin)
    await store.save_game(GUILD, "slots", min_bet=20)
    monkeypatch.undo()
    assert spun == [(3_000_000, 30_020)]
    assert await store.jackpot(GUILD, 500) == 3_000_000
    assert (await store.game(GUILD, "slots")).min_bet == 20
