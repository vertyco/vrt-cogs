from types import SimpleNamespace

import pytest
import pytest_asyncio

from marblemunch.common.leaderboard import Result
from marblemunch.common.payouts import BALANCE_FULL, NONE_LEFT, NOTHING_EARNED, PAYOUTS_OFF
from marblemunch.main import NOT_AN_ADMIN, NOTHING_TO_CASH, MarbleMunch
from marblemunch.tests.fakes import ADMIN_ID, OWNER_ID, FakeBank, FakeBot, FakeConn, FakeRoom, Today, member_ctx


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(MarbleMunch(bot=None))
    assert game.key == "marblemunch" and game.name == "Marble Munch"
    assert set(game.socket) == {"join", "message", "leave"}
    assert set(game.actions) == {"leaderboard", "payouts", "save_payouts"}
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_deleting_a_players_data_takes_them_off_the_leaderboard():
    cog = MarbleMunch(bot=None)
    await cog.save_results([Result(1, "Maya", 3, True), Result(2, "Sam", 1, False)])
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    board = await cog.leaderboard(SimpleNamespace(author=SimpleNamespace(id=1)), {})
    assert [row["name"] for row in board["top"]] == ["Sam"] and board["you"] is None


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_match_on_the_new_room():
    # Reloading ActivityHub gives every window a fresh room, while the match and its kept seats live on
    cog = MarbleMunch(bot=None)
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    match = cog.match_for(FakeConn(old_room, 1))
    try:
        assert cog.match_for(FakeConn(new_room, 1)) is match
        assert match.room is new_room
    finally:
        await cog.cog_unload()


ON = {"on": True, "rate": 10, "cap": 1000, "plays": 2}


@pytest_asyncio.fixture
async def paying():
    cog = MarbleMunch(bot=FakeBot())
    # Red's Config keeps a cog's data in memory for the whole test run, so each test starts from nothing
    await cog.config.clear_all()
    cog.payouts.bank = FakeBank()
    cog.payouts.today = Today()
    return cog


async def turn_on(cog, **settings):
    await cog.config.guild_from_id(500).payouts.set({**ON, **settings})


def seated(cog, room, user_id, seat=0):
    conn = FakeConn(room, user_id)
    match = cog.match_for(conn)
    match.sit(conn, seat)
    return match, conn


# ---------- Cashing in ----------


@pytest.mark.asyncio
async def test_a_finished_round_offers_a_cash_in_that_pays_once(paying):
    cog = paying
    await turn_on(cog)
    match, conn = seated(cog, FakeRoom(), 1)
    try:
        await cog.after_round(match, [Result(1, "Global 1", 4, True)])
        assert conn.sent[-1] == {"offer": {"worth": 40, "left": 2, "plays": 2, "currency": "credits"}}
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert conn.sent[-1] == {"cashed": {"paid": 40, "left": 1, "balance": 40, "currency": "credits"}}
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert conn.sent[-1] == {"notice": NOTHING_TO_CASH} and cog.payouts.bank.balances == {1: 40}
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_no_offer_while_payouts_are_off(paying):
    cog = paying
    match, conn = seated(cog, FakeRoom(), 1)
    try:
        await cog.after_round(match, [Result(1, "Global 1", 4, True)])
        assert conn.sent[-1] == {"offer": None}
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert conn.sent[-1] == {"notice": PAYOUTS_OFF}
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_a_refused_cash_in_keeps_the_round(paying):
    cog = paying
    await turn_on(cog)
    cog.payouts.bank.max_balance = 0
    match, conn = seated(cog, FakeRoom(), 1)
    try:
        await cog.after_round(match, [Result(1, "Global 1", 4, True)])
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert conn.sent[-1] == {"notice": BALANCE_FULL}
        cog.payouts.bank.max_balance = 1000
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert conn.sent[-1]["cashed"]["left"] == 1
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_cash_ins_run_out_for_the_day_and_come_back(paying):
    cog = paying
    await turn_on(cog, plays=1)
    member = member_ctx(1).author
    assert await cog.payouts.cash_in(member, 0) == {"error": NOTHING_EARNED}
    assert (await cog.payouts.cash_in(member, 200))["paid"] == 1000
    assert await cog.payouts.cash_in(member, 5) == {"error": NONE_LEFT}
    cog.payouts.today.day = "2026-10-11"
    assert (await cog.payouts.cash_in(member, 5))["paid"] == 50


@pytest.mark.asyncio
async def test_the_next_round_replaces_the_offer_and_a_rejoin_gets_it_back(paying):
    cog = paying
    await turn_on(cog)
    match, conn = seated(cog, FakeRoom(), 1)
    try:
        await cog.after_round(match, [Result(1, "Global 1", 4, True)])
        await cog.after_round(match, [Result(1, "Global 1", 7, True)])
        await cog.join(conn.ctx, conn)
        assert conn.sent[-1] == {"offer": {"worth": 70, "left": 2, "plays": 2, "currency": "credits"}}
        await cog.message(conn.ctx, conn, {"cashin": True})
        assert cog.payouts.bank.balances == {1: 70}
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_a_player_who_left_before_the_end_gets_no_offer(paying):
    cog = paying
    await turn_on(cog)
    match, conn = seated(cog, FakeRoom(), 1)
    try:
        match.seats[0].conn = None
        await cog.after_round(match, [Result(1, "Global 1", 4, False)])
        assert cog.offers == {} and not any("offer" in sent for sent in conn.sent)
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_a_leaderboard_save_keeps_todays_cash_ins(paying):
    cog = paying
    cog.payouts.bank.global_bank = True
    await cog.config.payouts.set(ON)
    await cog.payouts.cash_in(member_ctx(1).author, 3)
    await cog.save_results([Result(1, "Global 1", 3, True)])
    assert (await cog.config.user_from_id(1).cashed())["count"] == 1


# ---------- Payout settings ----------


@pytest.mark.asyncio
async def test_only_server_admins_see_and_save_the_settings(paying):
    cog = paying
    player, admin = member_ctx(1), member_ctx(ADMIN_ID)
    assert await cog.payout_settings(player, {}) == {"settings": None}
    assert await cog.save_payouts(player, {"settings": ON}) == {"error": NOT_AN_ADMIN}
    state = await cog.payout_settings(admin, {})
    assert state["settings"] == {"on": False, "rate": 100, "cap": 1000, "plays": 3} and state["global"] is False
    saved = await cog.save_payouts(admin, {"settings": ON})
    assert saved["settings"] == ON and await cog.config.guild_from_id(500).payouts() == ON
    refused = await cog.save_payouts(admin, {"settings": {**ON, "plays": 0}})
    assert "Cash-ins a day" in refused["error"] and await cog.config.guild_from_id(500).payouts() == ON


@pytest.mark.asyncio
async def test_with_a_global_bank_only_the_owner_sets_payouts_for_every_server(paying):
    cog = paying
    cog.payouts.bank.global_bank = True
    assert await cog.payout_settings(member_ctx(ADMIN_ID), {}) == {"settings": None}
    owner = member_ctx(OWNER_ID)
    assert (await cog.save_payouts(owner, {"settings": ON}))["global"] is True
    assert await cog.config.payouts() == ON
    await cog.payouts.cash_in(member_ctx(1).author, 1)
    assert (await cog.config.user_from_id(1).cashed())["count"] == 1
