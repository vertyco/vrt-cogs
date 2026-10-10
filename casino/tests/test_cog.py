import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from casino.common.memberships import Updater
from casino.common.money import Money
from casino.db.tables import PlayerGame
from casino.main import Casino
from casino.views.play import PlayView
from casino.tests.fakes import GUILD_ID, Clock, FakeBank, FakeBot, FakeConn, FakeGuild, FakeRoom, ctx_for
from casino.tests.tables_kit import Rigged, until

OWNER, PLAYER, MANAGER, ADMIN = 1, 7, 8, 9


@pytest_asyncio.fixture
async def cog(store):
    bot = FakeBot(owner_id=OWNER)
    guild = FakeGuild(GUILD_ID)
    bot.guilds[GUILD_ID] = guild
    for user_id in (OWNER, PLAYER, ADMIN):
        guild.add(user_id)
    guild.add(MANAGER, manage=True)
    bot.admins.add(ADMIN)
    casino = Casino(bot)
    casino.store = store
    casino.bank = FakeBank(start=1000)
    casino.money = Money(store, casino.bank, Clock())
    casino.updater = Updater(bot, store, casino.bank, casino.refresh_players)
    casino.ready.set()
    yield casino
    await casino.cog_unload()


def guild_of(cog):
    return cog.bot.get_guild(GUILD_ID)


def ctx(cog, user_id):
    return ctx_for(guild_of(cog).get_member(user_id), guild_of(cog))


async def joined(cog, user_id, room):
    conn = FakeConn(room, guild_of(cog).get_member(user_id), guild_of(cog))
    await cog.join(conn.ctx, conn)
    return conn


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game(cog):
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(cog)
    assert game.key == "casino" and game.name == "Casino"
    assert set(game.socket) == {"join", "message", "leave"}
    assert {"profile", "rules", "settings", "save_game", "wipe"} <= set(game.actions)
    assert game.icon == "icon.png" and game.thumbnail == "thumb.jpg"


@pytest.mark.asyncio
async def test_joining_says_hello_then_shows_the_lobby(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    hello = sam.sent[0]
    assert hello["t"] == "hello" and hello["me"]["balance"] == 1000 and hello["me"]["membership"]["name"] == "Basic"
    assert hello["casino"]["name"] == "Redjumpman's" and hello["casino"]["games"]["coin"]["min"] == 10
    assert hello["can_manage"] is False and hello["currency"] == "credits"
    assert sam.last("lobby") == {"t": "lobby", "counts": {}}


@pytest.mark.asyncio
async def test_the_casino_only_opens_in_a_server(cog):
    room = FakeRoom()
    conn = FakeConn(room, guild_of(cog).get_member(PLAYER), None)
    await cog.join(conn.ctx, conn)
    assert conn.last("notice")["text"] == "Open the casino in a server." and conn.closed == 4100


@pytest.mark.asyncio
async def test_a_round_played_over_the_connection(cog):
    cog.rng = Rigged(picks=["tails"])
    sam = await joined(cog, PLAYER, FakeRoom())
    await cog.message(sam.ctx, sam, {"t": "enter", "game": "coin"})
    assert sam.last("lobby")["counts"] == {"coin": 1}
    table = cog.floors["window"].tables["coin"]
    table.speed = 0
    await cog.message(sam.ctx, sam, {"t": "bet", "amount": 10, "choice": "tails"})
    await until(lambda: sam.of("result"))
    assert sam.last("result")["payout"] == 15 and sam.last("me")["ready"]["coin"] == 5


@pytest.mark.asyncio
async def test_odd_messages_are_ignored(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    before = len(sam.sent)
    for data in ("hi", ["bet"], {"t": "bet", "amount": 10}, {"t": "enter", "game": "poker"}, {"t": "sit", "seat": 0}):
        await cog.message(sam.ctx, sam, data)
    assert len(sam.sent) == before


@pytest.mark.asyncio
async def test_the_floor_goes_when_the_last_player_leaves(cog):
    room = FakeRoom()
    sam = await joined(cog, PLAYER, room)
    sam.drop()
    await cog.leave(sam.ctx, sam)
    assert cog.floors == {}


@pytest.mark.asyncio
async def test_only_admins_open_the_settings(cog):
    assert (await cog.act_settings(ctx(cog, PLAYER), {}))["error"] == "Only casino admins can do that."
    for user_id in (MANAGER, ADMIN, OWNER):
        assert "games" in await cog.act_settings(ctx(cog, user_id), {})
    assert (await cog.act_wipe(ctx(cog, MANAGER), {}))["error"] == "Only the bot owner can do that."


@pytest.mark.asyncio
async def test_in_global_mode_only_the_owner_edits(cog):
    cog.bank.global_bank = True
    assert await cog.act_set_mode(ctx(cog, OWNER), {"global": True}) == {"global": True}
    assert (await cog.act_save_game(ctx(cog, MANAGER), {"game": "dice", "max_bet": 5}))["error"]
    saved = await cog.act_save_game(ctx(cog, OWNER), {"game": "dice", "max_bet": 500})
    assert saved["games"]["dice"]["max"] == 500 and saved["global"] is True


@pytest.mark.asyncio
async def test_global_mode_needs_a_global_bank(cog):
    assert "bank is per server" in (await cog.act_set_mode(ctx(cog, OWNER), {"global": True}))["error"]


@pytest.mark.asyncio
async def test_saving_a_game_checks_it_and_updates_open_pages(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    boss = ctx(cog, MANAGER)
    assert (await cog.act_save_game(boss, {"game": "dice", "min_bet": 500}))["error"].startswith("The minimum bet")
    assert (await cog.act_save_game(boss, {"game": "allin", "max_bet": 5}))["error"].startswith("All In has no")
    assert (await cog.act_save_game(boss, {"game": "dice", "cooldown": "1:00:00"}))["games"]["dice"]["cooldown"] == 3600
    assert sam.last("casino")["casino"]["games"]["dice"]["cooldown"] == 3600


@pytest.mark.asyncio
async def test_saving_the_casino_name(cog):
    boss = ctx(cog, MANAGER)
    assert (await cog.act_save_casino(boss, {"name": ""}))["error"].startswith("The casino's name")
    assert (await cog.act_save_casino(boss, {"name": "Lucky", "limit_on": True}))["name"] == "Lucky"


@pytest.mark.asyncio
async def test_memberships_made_given_and_deleted_from_the_page(cog):
    boss = ctx(cog, MANAGER)
    made = await cog.act_save_membership(boss, {"name": "Gold", "color": "yellow", "access": 2, "req_role_id": "900"})
    gold = made["tiers"][0]
    assert gold["req_role"] == "VIP" and len(gold["games"]) == 9
    tiers = (await cog.act_memberships(ctx(cog, PLAYER), {}))["tiers"]
    assert tiers[0]["name"] == "Gold"
    card = await cog.act_player_update(boss, {"user_id": str(PLAYER), "op": "assign", "membership_id": gold["id"]})
    assert card["membership"]["name"] == "Gold" and card["by_hand"] is True
    await cog.act_delete_membership(boss, {"id": gold["id"]})
    assert (await cog.act_profile(ctx(cog, PLAYER), {}))["membership"]["name"] == "Basic"


@pytest.mark.asyncio
async def test_releasing_held_winnings_from_the_page(cog):
    await cog.store.add_pending(GUILD_ID, PLAYER, 400)
    card = await cog.act_player_update(ctx(cog, MANAGER), {"user_id": str(PLAYER), "op": "release"})
    assert card["pending"] == 0 and cog.bank.balances[PLAYER] == 1400


@pytest.mark.asyncio
async def test_finding_players_by_name(cog):
    found = await cog.act_find_players(ctx(cog, MANAGER), {"query": "PLAYER7"})
    assert [p["id"] for p in found["players"]] == [str(PLAYER)]


@pytest.mark.asyncio
async def test_deleting_a_users_data(cog):
    await cog.store.add_pending(GUILD_ID, PLAYER, 5)
    await cog.red_delete_data_for_user(requester="user", user_id=PLAYER)
    assert await cog.store.players(GUILD_ID) == []


@pytest.mark.asyncio
async def test_closing_a_game_mid_round_lets_the_round_finish(cog):
    room = FakeRoom()
    sam, ann = await joined(cog, PLAYER, room), await joined(cog, ADMIN, room)
    for conn in (sam, ann):
        await cog.message(conn.ctx, conn, {"t": "enter", "game": "dice"})
    table = cog.floors["window"].tables["dice"]
    table.speed = 0
    await cog.message(sam.ctx, sam, {"t": "bet", "amount": 25})
    assert (await cog.act_save_game(ctx(cog, MANAGER), {"game": "dice", "is_open": False}))["games"]["dice"][
        "open"
    ] is False
    await cog.message(sam.ctx, sam, {"t": "go"})
    await until(lambda: sam.of("result"))
    await until(lambda: table.task is None)
    await cog.message(ann.ctx, ann, {"t": "bet", "amount": 25})
    assert ann.last("notice")["text"] == "Dice is closed."


@pytest.mark.asyncio
async def test_set_mode_refuses_a_value_that_is_not_true_or_false(cog):
    assert await cog.act_set_mode(ctx(cog, OWNER), {"global": "yes"}) == {"error": "Pick global or server mode."}


@pytest.mark.asyncio
async def test_unloading_refunds_every_bet_and_refuses_new_arrivals(cog):
    room = FakeRoom()
    sam, ann = await joined(cog, PLAYER, room), await joined(cog, ADMIN, room)
    for conn, game, amount in ((sam, "dice", 25), (ann, "coin", 10)):
        await cog.message(conn.ctx, conn, {"t": "enter", "game": game})
        await cog.message(conn.ctx, conn, {"t": "bet", "amount": amount, "choice": "heads"})
    assert cog.bank.balances[PLAYER] == 975 and cog.bank.balances[ADMIN] == 990
    cog.play_view = PlayView(cog)
    await cog.cog_unload()
    assert cog.bank.balances[PLAYER] == 1000 and cog.bank.balances[ADMIN] == 1000
    floor = cog.floors["window"]
    await cog.message(sam.ctx, sam, {"t": "enter", "game": "hilo"})
    await floor.enter(sam, "hilo")
    assert "hilo" not in floor.tables
    late = FakeConn(FakeRoom("other"), guild_of(cog).get_member(OWNER), guild_of(cog))
    await cog.join(late.ctx, late)
    assert late.closed == 4101 and "other" not in cog.floors
    assert cog.play_view.is_finished()


@pytest.mark.asyncio
async def test_a_floor_is_not_kept_when_the_hello_fails(cog, monkeypatch):
    async def broken(ctx):
        raise RuntimeError("no hello")

    monkeypatch.setattr(cog, "hello", broken)
    conn = FakeConn(FakeRoom(), guild_of(cog).get_member(PLAYER), guild_of(cog))
    with pytest.raises(RuntimeError):
        await cog.join(conn.ctx, conn)
    assert cog.floors == {}


@pytest.mark.asyncio
async def test_server_mode_cannot_reach_people_outside_the_server(cog):
    cog.bot.users[99] = SimpleNamespace(id=99, name="stranger", display_name="stranger")
    boss = ctx(cog, MANAGER)
    for call in (cog.act_player_card, cog.act_player_stats, cog.act_player_update):
        assert (await call(boss, {"user_id": "99", "op": "release"}))["error"] == "That player isn't here."


@pytest.mark.asyncio
async def test_a_membership_id_that_is_not_a_number_is_refused(cog):
    boss = ctx(cog, MANAGER)
    for bad in ("abc", True, 1.5):
        assert (await cog.act_save_membership(boss, {"id": bad, "name": "Gold", "color": "yellow"}))["error"]
    assert (await cog.act_memberships(boss, {}))["tiers"] == []


@pytest.mark.asyncio
async def test_global_mode_tells_a_non_owner_it_is_the_owners_call(cog):
    cog.bank.global_bank = True
    await cog.act_set_mode(ctx(cog, OWNER), {"global": True})
    assert (await cog.act_settings(ctx(cog, MANAGER), {}))["error"] == "Only the bot owner can do that."


@pytest.mark.asyncio
async def test_bad_shapes_at_a_table_are_ignored(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    await cog.message(sam.ctx, sam, {"t": "enter", "game": "dice"})
    before = len(sam.sent)
    for data in (
        {"t": "bet", "amount": True},
        {"t": "enter", "game": ["dice"]},
        {"t": "move", "move": "nonsense"},
        {"t": "pull", "multiplier": 2},
        {"t": "sit", "seat": 0},
    ):
        await cog.message(sam.ctx, sam, data)
    assert [m for m in sam.sent[before:] if m.get("t") != "notice"] == []
    assert cog.bank.balances[PLAYER] == 1000


@pytest.mark.asyncio
async def test_bet_and_pull_belong_to_their_own_tables(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    await cog.message(sam.ctx, sam, {"t": "enter", "game": "allin"})
    await cog.message(sam.ctx, sam, {"t": "bet", "amount": 10, "multiplier": 2})
    assert cog.bank.balances[PLAYER] == 1000 and not cog.floors["window"].tables["allin"].pulls


@pytest.mark.asyncio
async def test_deleting_a_users_data_clears_every_scope_and_their_game_rows(cog):
    for scope in (GUILD_ID, 0):
        await cog.store.add_pending(scope, PLAYER, 5)
        await cog.store.player_games(scope, PLAYER)
    await cog.red_delete_data_for_user(requester="user", user_id=PLAYER)
    assert await cog.store.players(GUILD_ID) == [] and await cog.store.players(0) == []
    assert not await PlayerGame.objects().where(PlayerGame.user_id == PLAYER)


@pytest.mark.asyncio
async def test_players_with_19_digit_ids_are_found(cog):
    newer = 1234567890123456789
    guild_of(cog).add(newer)
    assert (await cog.act_player_stats(ctx(cog, PLAYER), {"user_id": str(newer)}))["id"] == str(newer)
    assert (await cog.act_player_card(ctx(cog, MANAGER), {"user_id": str(newer)}))["id"] == str(newer)
    for bad in ("12a", "-7", "", "1" * 21, True, None):
        assert (await cog.act_player_card(ctx(cog, MANAGER), {"user_id": bad}))["error"] == "That player isn't here."


@pytest.mark.asyncio
async def test_a_membership_the_updater_gives_reaches_the_players_open_page(cog):
    sam = await joined(cog, PLAYER, FakeRoom())
    await cog.act_save_membership(ctx(cog, MANAGER), {"name": "Open", "color": "green", "access": 1})
    assert sam.last("me")["membership"]["name"] == "Basic"
    await cog.updater.run_once()
    assert sam.last("me")["membership"]["name"] == "Open"


@pytest.mark.asyncio
async def test_too_large_membership_numbers_are_refused_with_a_reason(cog):
    boss = ctx(cog, MANAGER)
    for bad in ({"access": "1" * 30}, {"req_credits": 10**30}, {"bonus": "inf"}, {"req_days": float("inf")}):
        answer = await cog.act_save_membership(boss, {"name": "Gold", "color": "yellow", **bad})
        assert answer["error"], bad
    assert (await cog.act_memberships(boss, {}))["tiers"] == []


@pytest.mark.asyncio
async def test_the_settings_carry_the_open_membership_warning(cog):
    settings = await cog.act_settings(ctx(cog, MANAGER), {})
    assert settings["open_tier_warning"].startswith("This membership has no requirements")


@pytest.mark.asyncio
async def test_deleting_data_gives_up_when_the_database_never_opens(cog, monkeypatch):
    await cog.store.add_pending(GUILD_ID, PLAYER, 5)
    cog.ready.clear()
    monkeypatch.setattr("casino.main.DELETE_WAIT", 0.05)
    await asyncio.wait_for(cog.red_delete_data_for_user(requester="user", user_id=PLAYER), 5)
    assert len(await cog.store.players(GUILD_ID)) == 1
    cog.ready.set()


class Said:
    """A command's context: the author, the server, and what the command sent"""

    def __init__(self, cog, user_id):
        self.cog, self.bot, self.guild = cog, cog.bot, guild_of(cog)
        self.author = self.guild.get_member(user_id)
        self.sent = []

    async def send(self, text=None, **kwargs):
        self.sent.append(text)


@pytest.mark.asyncio
async def test_the_casino_command_says_when_the_casino_is_closed(cog):
    said = Said(cog, PLAYER)
    await Casino.casino_group.callback(cog, said)
    assert "is open" in said.sent[-1]
    await cog.store.save_casino(GUILD_ID, is_open=False)
    await Casino.casino_group.callback(cog, said)
    assert said.sent[-1] == "**Redjumpman's Casino** is closed right now."


@pytest.mark.asyncio
async def test_revoking_takes_back_any_membership(cog):
    gold = (await cog.act_save_membership(ctx(cog, MANAGER), {"name": "Gold", "color": "yellow"}))["tiers"][0]
    await cog.store.set_membership(GUILD_ID, PLAYER, gold["id"], by_hand=False)
    said = Said(cog, MANAGER)
    await Casino.casino_revokemem.callback(cog, said, player=said.guild.get_member(PLAYER))
    player = await cog.store.player(GUILD_ID, PLAYER)
    assert player.membership is None and player.by_hand is False
    assert said.sent[-1] == "Player7 is Basic until the next membership update."
