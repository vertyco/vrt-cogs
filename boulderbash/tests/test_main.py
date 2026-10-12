from types import SimpleNamespace

import pytest
import pytest_asyncio

from boulderbash.common.game import Game
from boulderbash.common.payouts import BALANCE_FULL, NONE_LEFT, NOTHING_EARNED, PAYOUTS_OFF
from boulderbash.common.rules import EXTREME, NORMAL, ZEN
from boulderbash.common.scores import rank
from boulderbash.main import ELSEWHERE, HOLD_MS, NOT_AN_ADMIN, NOTHING_TO_CASH, STOPPED, BoulderBash
from boulderbash.tests.fakes import (
    ADMIN_ID,
    OWNER_ID,
    Clock,
    FakeBank,
    FakeBot,
    FakeConn,
    Today,
    dm_ctx,
    member_ctx,
)

ON = {"on": True, "rate": 0.2, "cap": 1000, "plays": 2}


@pytest_asyncio.fixture
async def cog():
    cog = BoulderBash(bot=FakeBot())
    # Red's Config keeps a cog's data in memory for the whole test run, so each test starts from nothing
    await cog.config.clear_all()
    cog.payouts.bank = FakeBank()
    cog.payouts.today = Today()
    cog.clock = Clock()
    yield cog
    await cog.cog_unload()


async def turn_on(cog, **settings):
    await cog.config.guild_from_id(500).payouts.set({**ON, **settings})


async def joined(cog, ctx):
    conn = FakeConn(ctx)
    await cog.join(ctx, conn)
    return conn


async def finish(cog, conn, score, mode=NORMAL):
    """Start a game, give it a score and end it, then let the save run"""
    await cog.message(conn.ctx, conn, {"start": mode})
    key = (conn.ctx.guild_id or 0, conn.ctx.author.id)
    cog.games[key].boards[0].score = score
    await cog.message(conn.ctx, conn, {"end": True})
    for task in list(cog.saving):
        await task
    return conn.last("result")


# Registering with the hub


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(BoulderBash(bot=None))
    assert game.key == "boulderbash" and game.name == "Boulder Bash"
    assert set(game.socket) == {"join", "message", "leave"}
    assert set(game.actions) == {"scores", "payouts", "save_payouts"}
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_the_hub_lists_the_game_once_the_cog_loads():
    games = pytest.importorskip("activityhub.common.games")
    registry = games.GameRegistry()
    await registry.add(BoulderBash(bot=None))
    assert "boulderbash" in registry.games and registry.failed == {}


# Connections


@pytest.mark.asyncio
async def test_a_player_starts_a_game_and_gets_its_snapshot(cog):
    conn = await joined(cog, member_ctx(1))
    assert conn.sent == [{"hello": {"game": None, "result": None}}]
    await cog.message(conn.ctx, conn, {"start": NORMAL})
    game = conn.last("game")
    assert game["mode"] == NORMAL and game["boards"][0]["rows"] == 12


@pytest.mark.asyncio
async def test_messages_of_the_wrong_shape_are_ignored(cog):
    conn = await joined(cog, member_ctx(1))
    for data in (
        {"start": 9},
        {"start": True},
        {"start": 1, "x": 2},
        {"tap": [0, 1]},
        {"tap": [0, 1, "2"]},
        {"undo": 1},
        [1],
        "start",
        None,
    ):
        await cog.message(conn.ctx, conn, data)
    assert conn.kinds() == ["hello"]


@pytest.mark.asyncio
async def test_a_second_connection_takes_the_game_over(cog):
    first = await joined(cog, member_ctx(1))
    await cog.message(first.ctx, first, {"start": NORMAL})
    second = await joined(cog, member_ctx(1))
    assert first.sent[-1] == {"elsewhere": ELSEWHERE} and first.closed == 4100
    assert second.last("hello")["game"]["mode"] == NORMAL
    # The old page's messages and its late leave no longer count
    await cog.message(first.ctx, first, {"end": True})
    await cog.leave(first.ctx, first)
    assert cog.games[(500, 1)].state == "play" and (500, 1) not in cog.away


@pytest.mark.asyncio
async def test_a_game_waits_ten_minutes_for_its_player_then_is_dropped(cog):
    conn = await joined(cog, member_ctx(1))
    await cog.message(conn.ctx, conn, {"start": NORMAL})
    await cog.leave(conn.ctx, conn)
    cog.clock.now = HOLD_MS - 1
    await cog.tick(cog.clock.now)
    back = await joined(cog, member_ctx(1))
    assert back.last("hello")["game"]["mode"] == NORMAL
    await cog.leave(back.ctx, back)
    cog.clock.now += HOLD_MS
    await cog.tick(cog.clock.now)
    assert (500, 1) not in cog.games
    again = await joined(cog, member_ctx(1))
    assert again.last("hello")["game"] is None


@pytest.mark.asyncio
async def test_unloading_stops_the_game_loop(cog):
    conn = await joined(cog, member_ctx(7))
    await cog.message(conn.ctx, conn, {"start": NORMAL})
    assert cog.loop_task is not None and not cog.loop_task.done()
    await cog.cog_unload()
    assert cog.loop_task.done()


@pytest.mark.asyncio
async def test_pages_closing_after_unload_dont_restart_the_loop(cog):
    conn = await joined(cog, member_ctx(7))
    await cog.message(conn.ctx, conn, {"start": NORMAL})
    await cog.cog_unload()
    # The hub closes every page once the cog is gone
    await cog.leave(conn.ctx, conn)
    assert cog.loop_task.done()


@pytest.mark.asyncio
async def test_a_game_keeps_running_while_its_player_is_away(cog):
    conn = await joined(cog, member_ctx(1))
    await cog.message(conn.ctx, conn, {"start": EXTREME})
    await cog.leave(conn.ctx, conn)
    for step in range(1, 120):
        cog.clock.now = step * 1000.0
        await cog.tick(cog.clock.now)
    assert cog.games[(500, 1)].state in ("popup", "over")


@pytest.mark.asyncio
async def test_an_error_in_a_move_stops_the_game(cog, monkeypatch):
    conn = await joined(cog, member_ctx(1))
    await cog.message(conn.ctx, conn, {"start": NORMAL})

    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(Game, "tap", broken)
    await cog.message(conn.ctx, conn, {"tap": [0, 0, 11]})
    assert conn.sent[-1] == {"stopped": STOPPED}
    assert (500, 1) not in cog.games


# Game over, high scores and cashing in


@pytest.mark.asyncio
async def test_every_finished_game_goes_on_the_servers_table(cog):
    conn = await joined(cog, member_ctx(1))
    result = await finish(cog, conn, 300)
    assert result["score"] == 300 and result["best"] == 300 and result["rank"] == 1 and result["newBest"]
    result = await finish(cog, conn, 120)
    assert result["best"] == 300 and not result["newBest"]
    other = await joined(cog, member_ctx(2))
    assert (await finish(cog, other, 500))["rank"] == 1
    table = await cog.scores(member_ctx(1), {})
    assert [row["best"] for row in table["top"]] == [500, 300] and table["you"] == {"rank": 2, "best": 300}


@pytest.mark.asyncio
async def test_high_score_tables_are_per_server(cog):
    await finish(cog, await joined(cog, member_ctx(1, guild_id=500)), 300)
    await finish(cog, await joined(cog, member_ctx(2, guild_id=600)), 900)
    assert [row["best"] for row in (await cog.scores(member_ctx(1, guild_id=500), {}))["top"]] == [300]
    assert [row["best"] for row in (await cog.scores(member_ctx(3, guild_id=600), {}))["top"]] == [900]


@pytest.mark.asyncio
async def test_a_finished_game_cashes_in_once(cog):
    await turn_on(cog)
    conn = await joined(cog, member_ctx(1))
    result = await finish(cog, conn, 4200)
    assert result["offer"] == {"worth": 840, "left": 2, "plays": 2, "currency": "credits"}
    await cog.message(conn.ctx, conn, {"cashin": True})
    cashed = conn.last("cashed")
    assert cashed["paid"] == 840 and cashed["left"] == 1 and cashed["best"] == 4200 and cashed["rank"] == 1
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.sent[-1] == {"notice": NOTHING_TO_CASH} and cog.payouts.bank.balances == {1: 840}


@pytest.mark.asyncio
async def test_payouts_are_off_until_an_admin_turns_them_on(cog):
    conn = await joined(cog, member_ctx(1))
    assert (await finish(cog, conn, 4200))["offer"] is None
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.sent[-1] == {"notice": PAYOUTS_OFF}


@pytest.mark.asyncio
async def test_zen_and_dm_games_never_cash_in(cog):
    await turn_on(cog)
    zen = await finish(cog, await joined(cog, member_ctx(1)), 0, mode=ZEN)
    assert zen["offer"] is None
    dm = await joined(cog, dm_ctx(2))
    result = await finish(cog, dm, 900)
    assert result["offer"] is None and result["best"] is None and result["dm"]


@pytest.mark.asyncio
async def test_restart_or_a_new_game_drops_the_unsent_score(cog):
    await turn_on(cog)
    conn = await joined(cog, member_ctx(1))
    await finish(cog, conn, 4200)
    await cog.message(conn.ctx, conn, {"restart": True})
    assert (500, 1) not in cog.games
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.sent[-1] == {"notice": NOTHING_TO_CASH}
    await finish(cog, conn, 1000)
    await cog.message(conn.ctx, conn, {"start": NORMAL})
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.sent[-1] == {"notice": NOTHING_TO_CASH}


@pytest.mark.asyncio
async def test_a_rejoin_gets_the_unsent_game_over_back(cog):
    await turn_on(cog)
    conn = await joined(cog, member_ctx(1))
    await finish(cog, conn, 4200)
    await cog.leave(conn.ctx, conn)
    back = await joined(cog, member_ctx(1))
    hello = back.last("hello")
    assert hello["game"]["state"] == "over" and hello["result"]["offer"]["worth"] == 840


@pytest.mark.asyncio
async def test_a_refused_cash_in_keeps_the_score_for_another_try(cog):
    await turn_on(cog)
    cog.payouts.bank.max_balance = 0
    conn = await joined(cog, member_ctx(1))
    await finish(cog, conn, 4200)
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.sent[-1] == {"notice": BALANCE_FULL}
    cog.payouts.bank.max_balance = 10_000
    await cog.message(conn.ctx, conn, {"cashin": True})
    assert conn.last("cashed")["paid"] == 840


@pytest.mark.asyncio
async def test_cash_ins_are_capped_run_out_for_the_day_and_come_back(cog):
    await turn_on(cog, plays=1)
    member = member_ctx(1).author
    assert await cog.payouts.cash_in(member, 0) == {"error": NOTHING_EARNED}
    assert (await cog.payouts.cash_in(member, 99_999))["paid"] == 1000
    assert await cog.payouts.cash_in(member, 50) == {"error": NONE_LEFT}
    cog.payouts.today.day = "2026-10-11"
    assert (await cog.payouts.cash_in(member, 50))["paid"] == 10


@pytest.mark.asyncio
async def test_a_payout_fills_the_balance_to_the_banks_maximum(cog):
    await turn_on(cog)
    cog.payouts.bank.max_balance = 500
    cog.payouts.bank.balances[1] = 300
    result = await cog.payouts.cash_in(member_ctx(1).author, 4200)
    assert result["paid"] == 200 and result["balance"] == 500


# Settings


@pytest.mark.asyncio
async def test_only_server_admins_see_and_save_the_settings(cog):
    player, admin = member_ctx(1), member_ctx(ADMIN_ID)
    assert await cog.payout_settings(player, {}) == {"settings": None}
    assert await cog.save_payouts(player, {"settings": ON}) == {"error": NOT_AN_ADMIN}
    state = await cog.payout_settings(admin, {})
    assert state["settings"] == {"on": False, "rate": 0.2, "cap": 1000, "plays": 3} and state["global"] is False
    saved = await cog.save_payouts(admin, {"settings": ON})
    assert saved["settings"] == ON and await cog.config.guild_from_id(500).payouts() == ON
    refused = await cog.save_payouts(admin, {"settings": {**ON, "plays": 0}})
    assert "Cash-ins a day" in refused["error"] and await cog.config.guild_from_id(500).payouts() == ON


@pytest.mark.asyncio
async def test_the_settings_show_todays_payouts(cog):
    await turn_on(cog)
    for user_id, score in ((1, 4200), (2, 1000), (1, 500)):
        await cog.payouts.cash_in(member_ctx(user_id).author, score)
    today = (await cog.payout_settings(member_ctx(ADMIN_ID), {}))["today"]
    assert today == {"paid": 840 + 200 + 100, "players": 2}
    cog.payouts.today.day = "2026-10-11"
    assert (await cog.payout_settings(member_ctx(ADMIN_ID), {}))["today"] == {"paid": 0, "players": 0}


@pytest.mark.asyncio
async def test_with_a_global_bank_only_the_owner_sets_payouts_and_cash_ins_count_across_servers(cog):
    cog.payouts.bank.global_bank = True
    assert await cog.payout_settings(member_ctx(ADMIN_ID), {}) == {"settings": None}
    owner = member_ctx(OWNER_ID)
    assert (await cog.save_payouts(owner, {"settings": {**ON, "plays": 1}}))["global"] is True
    assert (await cog.payouts.cash_in(member_ctx(1, guild_id=500).author, 100))["paid"] == 20
    assert await cog.payouts.cash_in(member_ctx(1, guild_id=600).author, 100) == {"error": NONE_LEFT}


# Data deletion


@pytest.mark.asyncio
async def test_deleting_a_players_data_takes_them_off_the_table_and_todays_tally(cog):
    await turn_on(cog)
    await finish(cog, await joined(cog, member_ctx(1)), 4200)
    await finish(cog, await joined(cog, member_ctx(2)), 1000)
    await cog.payouts.cash_in(member_ctx(1).author, 4200)
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    table = await cog.scores(member_ctx(2), {})
    assert [row["id"] for row in table["top"]] == ["2"]
    assert 1 not in (await cog.config.guild_from_id(500).tally())["players"]
    assert (500, 1) not in cog.games


def test_ranking_orders_by_best_score_and_finds_your_place():
    members = {1: {"best": 50, "name": "A"}, 2: {"best": 90, "name": "B"}, 3: {"best": 0, "name": "C"}}
    table = rank(members, 1)
    assert [row["name"] for row in table["top"]] == ["B", "A"]
    assert table["you"] == {"rank": 2, "best": 50}
    assert rank(members, 3)["you"] is None


@pytest.mark.asyncio
async def test_the_menu_line_follows_the_payouts_switch(cog):
    guild = SimpleNamespace(id=500)
    game = await pytest.importorskip("activityhub.common.games").validate_game(cog)
    assert game.economy == cog.economy_line
    assert await cog.economy_line(guild) is None
    await turn_on(cog, cap=2500)
    assert await cog.economy_line(guild) == "Cash in up to 2,500 credits"
