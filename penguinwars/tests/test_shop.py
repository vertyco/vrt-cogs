import asyncio

import pytest
import pytest_asyncio
from redbot.core.config import Value

from penguinwars.common.shop import (
    ITEMS,
    KINDS,
    PRICED,
    SOLD,
    STATS,
    Played,
    SettingsError,
    add_round,
    clean_prices,
    clean_wear,
    earn_state,
    earned_items,
)
from penguinwars.main import PenguinWars
from penguinwars.tests.fakes import ADMIN_ID, GUILD_ID, OWNER_ID, FakeBank, FakeBot, FakeConn, FakeRoom, Today

USER = 1
START = 20_000
# What an admin saves to sell nothing
NOT_SOLD = {item: None for item in SOLD}
# What a player who never chose wears on their neck
SCARF = {"neck": "scarf"}


@pytest_asyncio.fixture
async def paying():
    cog = PenguinWars(bot=FakeBot())
    # Red's Config keeps a cog's data in memory for the whole test run, so each test starts from nothing
    await cog.config.clear_all()
    cog.shop.bank = FakeBank()
    cog.shop.today = Today()
    cog.shop.bank.balances[USER] = START
    yield cog
    await cog.cog_unload()


def ctx_of(user_id=USER, room="window", guild=True):
    ctx = FakeConn(FakeRoom(room), user_id).ctx
    if not guild:
        ctx.guild, ctx.author.guild = None, None
    return ctx


def balance(cog, user_id=USER):
    return cog.shop.bank.balances.get(user_id, 0)


def shown_prices(view):
    return {item["id"]: item["price"] for item in view["items"]}


def fail_saving(monkeypatch, *names):
    real = Value.set

    async def set_value(self, value):
        if self.identifier_data.identifiers[-1] in names:
            raise RuntimeError("disk full")
        await real(self, value)

    monkeypatch.setattr(Value, "set", set_value)


@pytest.mark.asyncio
async def test_buying_takes_the_price_once_and_keeps_the_item(paying):
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert answer == {"owned": ["crown", "scarf"], "wear": SCARF, "balance": START - 5000}
    assert balance(paying) == START - 5000
    assert await paying.shop.today_spent(ctx_of().guild) == {"spent": 5000, "players": 1}
    again = await paying.buy(ctx_of(), {"item": "crown"})
    assert "error" in again and balance(paying) == START - 5000


@pytest.mark.asyncio
async def test_tapping_buy_twice_charges_once(paying):
    ctx = ctx_of()
    first, second = await asyncio.gather(paying.buy(ctx, {"item": "crown"}), paying.buy(ctx, {"item": "crown"}))
    assert balance(paying) == START - 5000 and "error" in second and "error" not in first
    assert (await paying.config.user_from_id(USER).owned()) == ["crown"]


@pytest.mark.asyncio
async def test_two_devices_buying_different_items_keep_both(paying):
    answers = await asyncio.gather(
        paying.buy(ctx_of(room="phone"), {"item": "crown"}),
        paying.buy(ctx_of(room="desktop"), {"item": "tophat"}),
    )
    assert all("error" not in a for a in answers)
    assert sorted(await paying.config.user_from_id(USER).owned()) == ["crown", "tophat"]
    assert balance(paying) == START - 7500


@pytest.mark.asyncio
async def test_too_poor_changes_nothing(paying):
    paying.shop.bank.balances[USER] = 4999
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert "5,000" in answer["error"]
    assert balance(paying) == 4999 and await paying.config.user_from_id(USER).owned() == []
    assert await paying.shop.today_spent(ctx_of().guild) == {"spent": 0, "players": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("item", [None, 5, "nothing", ["crown"], {"a": 1}])
async def test_a_junk_item_is_refused_without_a_charge(paying, item):
    assert "error" in await paying.buy(ctx_of(), {"item": item})
    assert balance(paying) == START


@pytest.mark.asyncio
async def test_buying_outside_a_server_is_refused_but_wearing_works(paying):
    await paying.config.user_from_id(USER).owned.set(["crown"])
    dm = ctx_of(guild=False)
    assert "error" in await paying.buy(dm, {"item": "tophat"})
    assert balance(paying) == START
    worn = await paying.wear(dm, {"kind": "hat", "item": "crown"})
    assert worn["wear"] == {"hat": "crown", **SCARF}


@pytest.mark.asyncio
async def test_a_failed_save_gives_the_money_back(paying, monkeypatch):
    fail_saving(monkeypatch, "owned")
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert answer == {"error": "That didn't go through, and nothing was taken."}
    assert balance(paying) == START
    assert (await paying.shop.today_spent(ctx_of().guild))["spent"] == 0
    monkeypatch.undo()
    assert await paying.config.user_from_id(USER).owned() == []


@pytest.mark.asyncio
async def test_a_failed_save_and_a_failed_tally_still_gives_the_money_back(paying, monkeypatch):
    fail_saving(monkeypatch, "owned", "tally")
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert answer == {"error": "That didn't go through, and nothing was taken."}
    assert balance(paying) == START


@pytest.mark.asyncio
async def test_a_refund_that_fails_says_so_and_logs_who_and_what(paying, monkeypatch, caplog):
    fail_saving(monkeypatch, "owned")

    async def broken(member, amount):
        raise RuntimeError("bank down")

    monkeypatch.setattr(paying.shop.bank, "deposit_credits", broken)
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert "couldn't be returned" in answer["error"] and "admin" in answer["error"]
    assert balance(paying) == START - 5000
    assert "Couldn't refund 5000 credits to user 1 for Penguin Wars item crown" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_purchase_count_still_delivers_the_item(paying, monkeypatch, caplog):
    fail_saving(monkeypatch, "tally")
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert answer["owned"] == ["crown", "scarf"] and balance(paying) == START - 5000
    assert "Couldn't count a Penguin Wars purchase" in caplog.text


@pytest.mark.asyncio
async def test_deleting_a_player_during_a_buy_neither_revives_the_row_nor_charges_twice(paying):
    ctx = ctx_of()
    bought, _ = await asyncio.gather(
        paying.buy(ctx, {"item": "crown"}), paying.red_delete_data_for_user(requester="user", user_id=USER)
    )
    assert "error" not in bought and balance(paying) == START - 5000
    # The buy held the lock first, so the deletion ran after it and left nothing behind
    assert await paying.config.user_from_id(USER).owned() == []
    again = await paying.buy(ctx, {"item": "crown"})
    assert "error" not in again and balance(paying) == START - 10_000


@pytest.mark.asyncio
async def test_a_buy_after_deleting_while_the_lock_is_held_waits_its_turn(paying):
    lock = paying.lock(USER)
    async with lock:
        deleting = asyncio.create_task(paying.red_delete_data_for_user(requester="user", user_id=USER))
        buying = asyncio.create_task(paying.buy(ctx_of(), {"item": "crown"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not deleting.done() and not buying.done()
    await asyncio.gather(deleting, buying)
    assert paying.lock(USER) is lock
    assert balance(paying) == START - 5000


@pytest.mark.asyncio
async def test_wearing_needs_owning_and_shows_on_the_penguin_at_once(paying):
    ctx = ctx_of()
    conn = FakeConn(FakeRoom("window"), USER)
    await paying.join(conn.ctx, conn)
    await paying.message(conn.ctx, conn, {"sit": True})
    assert "error" in await paying.wear(ctx, {"kind": "hat", "item": "crown"})
    await paying.buy(ctx, {"item": "crown"})
    assert "error" in await paying.wear(ctx, {"kind": "trail", "item": "crown"})
    assert "error" in await paying.wear(ctx, {"kind": "hat", "item": "nothing"})
    assert (await paying.wear(ctx, {"kind": "hat", "item": "crown"}))["wear"] == {"hat": "crown", **SCARF}
    assert paying.matches["window"].seats[0].looks == {"hat": "crown", **SCARF}
    assert paying.matches["window"].state()["state"]["seats"][0]["looks"] == {"hat": "crown", **SCARF}


@pytest.mark.asyncio
async def test_a_player_joining_later_wears_what_they_saved(paying):
    worn = {"hat": "crown", "trail": "flames"}
    await paying.config.user_from_id(USER).set({"owned": ["crown", "flames"], "wear": worn})
    conn = FakeConn(FakeRoom("window"), USER)
    await paying.join(conn.ctx, conn)
    await paying.message(conn.ctx, conn, {"sit": True})
    assert paying.matches["window"].seats[0].looks == {**worn, **SCARF}


@pytest.mark.asyncio
async def test_clearing_a_hat(paying):
    ctx = ctx_of()
    await paying.buy(ctx, {"item": "crown"})
    await paying.wear(ctx, {"kind": "hat", "item": "crown"})
    cleared = await paying.wear(ctx, {"kind": "hat", "item": None})
    assert cleared == {"owned": ["crown", "scarf"], "wear": SCARF}
    assert (await paying.looks_of(USER)) == SCARF
    assert "error" in await paying.wear(ctx, {"kind": "cape", "item": None})


@pytest.mark.asyncio
async def test_purchases_follow_the_player_across_servers(paying):
    await paying.buy(ctx_of(), {"item": "crown"})
    elsewhere = ctx_of()
    elsewhere.guild.id = 777
    view = await paying.shop_view(elsewhere, {})
    assert view["owned"] == ["crown", "scarf"]
    assert (await paying.wear(elsewhere, {"kind": "hat", "item": "crown"}))["wear"] == {"hat": "crown", **SCARF}


@pytest.mark.asyncio
async def test_the_shop_lists_prices_and_what_is_owned(paying):
    view = await paying.shop_view(ctx_of(), {})
    assert shown_prices(view) == {item: info.get("price") for item, info in ITEMS.items()}
    assert view["currency"] == "credits" and view["owned"] == ["scarf"]
    dm =await paying.shop_view(ctx_of(guild=False), {})
    assert set(shown_prices(dm).values()) == {None}


@pytest.mark.asyncio
async def test_a_shop_re_read_waits_for_a_running_save(paying):
    async with paying.lock(USER):
        read = asyncio.ensure_future(paying.shop_view(ctx_of(), {}))
        await asyncio.sleep(0.05)
        assert not read.done()
    assert (await asyncio.wait_for(read, 2))["owned"] == ["scarf"]


@pytest.mark.asyncio
async def test_server_prices_change_only_that_server(paying):
    admin = ctx_of(ADMIN_ID)
    prices = NOT_SOLD | {"crown": 10}
    saved = await paying.save_shop(admin, {"settings": prices})
    assert saved["settings"]["crown"] == 10
    other = ctx_of(USER)
    other.guild.id = 777
    assert shown_prices(await paying.shop_view(other, {}))["crown"] == 5000
    paying.shop.bank.balances[ADMIN_ID] = 100
    await paying.buy(admin, {"item": "crown"})
    assert paying.shop.bank.balances[ADMIN_ID] == 90


@pytest.mark.asyncio
async def test_an_admin_can_stop_selling_an_item(paying):
    prices = NOT_SOLD | {"beanie": 50}
    await paying.save_shop(ctx_of(ADMIN_ID), {"settings": prices})
    answer = await paying.buy(ctx_of(), {"item": "crown"})
    assert "error" in answer and balance(paying) == START
    assert "error" not in await paying.buy(ctx_of(), {"item": "beanie"})
    assert balance(paying) == START - 50


@pytest.mark.asyncio
async def test_non_admins_get_no_settings_and_cant_save(paying):
    player = ctx_of(USER)
    assert await paying.shop_settings(player, {}) == {"settings": None}
    prices = {item: 1 for item in SOLD}
    assert "error" in await paying.save_shop(player, {"settings": prices})
    assert "error" in await paying.save_shop(ctx_of(ADMIN_ID, guild=False), {"settings": prices})
    assert shown_prices(await paying.shop_view(player, {}))["beanie"] == 1000


@pytest.mark.asyncio
async def test_a_global_bank_makes_prices_owner_only(paying):
    paying.shop.bank.global_bank = True
    prices = {item: 7 for item in SOLD}
    assert "error" in await paying.save_shop(ctx_of(ADMIN_ID), {"settings": prices})
    assert (await paying.save_shop(ctx_of(OWNER_ID), {"settings": prices}))["global"] is True
    other = ctx_of(USER)
    other.guild.id = 777
    assert (await paying.shop.prices(other.guild))["crown"] == 7


BAD_PRICES = [
    None,
    "x",
    {},
    {"crown": 5},
    {item: 0 for item in SOLD},
    {item: True for item in SOLD},
    {item: 1.5 for item in SOLD},
    {item: -5 for item in SOLD},
    {item: 1_000_000_001 for item in SOLD},
    {**{item: 5 for item in SOLD}, "unicorn": 5},
    {item: "5" for item in SOLD},
    # An earned item is never sold, so it takes no price
    {**{item: 5 for item in SOLD}, "monocle": 5},
    {item: 5 for item in ITEMS},
]


@pytest.mark.parametrize("bad", BAD_PRICES)
def test_bad_prices_are_refused(bad):
    with pytest.raises(SettingsError):
        clean_prices(bad)


async def currency_name(value):
    return value


@pytest.mark.asyncio
async def test_the_menu_line_fits_40_characters_and_names_the_currency(paying):
    assert await paying.economy_line(ctx_of()) == "Penguin looks for credits"
    paying.shop.bank.get_currency_name = lambda guild=None: currency_name("Extremely Long Currency Name Of Doom")
    assert len(await paying.economy_line(ctx_of())) == 40
    assert await paying.economy_line(ctx_of(guild=False)) is None
    await paying.save_shop(ctx_of(ADMIN_ID), {"settings": NOT_SOLD})
    assert await paying.economy_line(ctx_of()) is None


@pytest.mark.asyncio
async def test_deleting_a_player_clears_what_they_own_and_their_board_rows(paying):
    await paying.buy(ctx_of(), {"item": "crown"})
    await paying.wear(ctx_of(), {"kind": "hat", "item": "crown"})
    other_server = ctx_of()
    other_server.guild.id = 777
    await paying.buy(other_server, {"item": "tophat"})
    for guild_id in (GUILD_ID, 777):
        await paying.config.member_from_ids(guild_id, USER).set({"wins": 3, "knockouts": 1, "rounds": 4, "name": "A"})
        await paying.config.member_from_ids(guild_id, 2).set({"wins": 1, "knockouts": 1, "rounds": 1, "name": "B"})
    paying.shop.bank.global_bank = True
    await paying.buy(ctx_of(), {"item": "beanie"})
    await paying.config.user_from_id(USER).stats.set({"rounds": 9, "wins": 4})
    await paying.red_delete_data_for_user(requester="user", user_id=USER)
    assert await paying.config.user_from_id(USER).all() == {"owned": [], "wear": {}, "stats": {}, "foes": {}}
    members = await paying.config.all_members()
    for guild_id in (GUILD_ID, 777):
        assert USER not in members[guild_id] and 2 in members[guild_id]
    assert USER not in (await paying.config.tally())["players"]
    assert USER not in (await paying.config.guild_from_id(GUILD_ID).tally()).get("players", [])
    assert USER not in (await paying.config.guild_from_id(777).tally()).get("players", [])


@pytest.mark.asyncio
async def test_a_price_sent_by_the_page_is_ignored(paying):
    answer = await paying.buy(ctx_of(), {"item": "crown", "price": 1, "prices": {"crown": 1}})
    assert "error" not in answer and balance(paying) == START - 5000


@pytest.mark.asyncio
async def test_an_owned_hat_taken_off_sale_stays_wearable_in_a_server(paying):
    await paying.buy(ctx_of(), {"item": "crown"})
    await paying.save_shop(ctx_of(ADMIN_ID), {"settings": NOT_SOLD})
    assert set(shown_prices(await paying.shop_view(ctx_of(), {})).values()) == {None}
    assert (await paying.wear(ctx_of(), {"kind": "hat", "item": "crown"}))["wear"] == {"hat": "crown", **SCARF}


@pytest.mark.asyncio
async def test_the_shop_and_a_buy_report_the_balance_and_a_dm_has_none(paying):
    assert (await paying.shop_view(ctx_of(), {}))["balance"] == START
    assert (await paying.buy(ctx_of(), {"item": "crown"}))["balance"] == START - 5000
    assert (await paying.shop_view(ctx_of(), {}))["balance"] == START - 5000
    assert (await paying.shop_view(ctx_of(guild=False), {}))["balance"] is None


@pytest.mark.asyncio
async def test_the_settings_carry_the_catalog_prices_as_defaults(paying):
    answer = await paying.shop_settings(ctx_of(ADMIN_ID), {})
    assert answer["defaults"] == {item: info["price"] for item, info in SOLD.items()}


async def fail_round(cog, room_id="window"):
    failed = cog.matches[room_id]
    cog.match_ended(failed)
    failed.stop()


@pytest.mark.asyncio
async def test_a_match_restarted_by_a_message_keeps_everyones_hats_and_server(paying):
    await paying.config.user_from_id(USER).set({"owned": ["crown"], "wear": {"hat": "crown"}})
    await paying.config.user_from_id(2).set({"owned": ["tophat"], "wear": {"hat": "tophat"}})
    room = FakeRoom("window")
    first, second = FakeConn(room, USER), FakeConn(room, 2)
    await paying.join(first.ctx, first)
    await paying.join(second.ctx, second)
    await fail_round(paying)
    # Only player 2 speaks, so a reload of the sender alone would leave player 1 bare
    await paying.message(second.ctx, second, {"sit": True})
    match = paying.matches["window"]
    # Alone, player 2's Play starts a round, and player 1's Play during its 3-2-1 takes over a CPU's penguin
    await paying.message(first.ctx, first, {"sit": True})
    assert match.seat_of(2).looks == {"hat": "tophat", **SCARF}
    assert match.seat_of(USER).looks == {"hat": "crown", **SCARF}
    assert match.guild_id == GUILD_ID


@pytest.mark.asyncio
async def test_a_match_restarted_by_a_join_keeps_everyones_hats_and_server(paying):
    await paying.config.user_from_id(USER).set({"owned": ["crown"], "wear": {"hat": "crown"}})
    room = FakeRoom("window")
    first = FakeConn(room, USER)
    await paying.join(first.ctx, first)
    await paying.message(first.ctx, first, {"sit": True})
    await fail_round(paying)
    late = FakeConn(room, 2)
    await paying.join(late.ctx, late)
    await paying.message(first.ctx, first, {"sit": True})
    match = paying.matches["window"]
    assert match.seat_of(USER).looks == {"hat": "crown", **SCARF} and match.guild_id == GUILD_ID


@pytest.mark.asyncio
async def test_a_round_counted_after_a_message_restart_reaches_the_leaderboard(paying):
    room = FakeRoom("window")
    first, second = FakeConn(room, USER), FakeConn(room, 2)
    await paying.join(first.ctx, first)
    await paying.join(second.ctx, second)
    await fail_round(paying)
    await paying.message(first.ctx, first, {"sit": True})
    await paying.message(second.ctx, second, {"sit": True})
    match = paying.matches["window"]
    match.round_players = {0: USER, 1: 2}
    match.record_round({"knocked": [1, 0, 0, 0, 0, 0], "winner": 0})
    await asyncio.gather(*paying.saving)
    assert (await paying.config.member_from_ids(GUILD_ID, USER).all())["wins"] == 1


@pytest.mark.asyncio
async def test_a_refusal_names_the_servers_own_currency(paying):
    async def fish(guild=None):
        return "Fish"

    paying.shop.bank.get_currency_name = fish
    await paying.shop.save(ctx_of().guild, NOT_SOLD)
    assert (await paying.buy(ctx_of(), {"item": "crown"}))["error"] == "That isn't sold for Fish here."


@pytest.mark.asyncio
async def test_a_refusal_outside_a_server_names_no_currency(paying):
    answer = await paying.buy(ctx_of(guild=False), {"item": "crown"})
    assert "credits" not in answer["error"].lower() and "server" in answer["error"]


# ---------- What play earns ----------

# One item sold for credits in each slot
OUTFIT = {
    "skin": "emperor",
    "hat": "crown",
    "face": "shades",
    "neck": "bowtie",
    "back": "cape",
    "trail": "flames",
    "cheer": "twirl",
    "splash": "lovesplash",
    "title": "royalty",
    "name": "neon",
}
# Counts past every achievement's number
EVERYTHING = {name: 1000 for name in STATS}


def played(user_id=USER, won=False, knockouts=0, fish=0, seal=0, bounce=0, people=1):
    return Played(user_id, won, knockouts, fish, seal, bounce, people)


def counts_after(*rounds):
    """The play counts of someone new after these rounds, oldest first"""
    stats = {}
    for one in rounds:
        stats = add_round(stats, one)
    return stats


def test_a_rounds_numbers_add_to_the_play_counts():
    stats = counts_after(played(won=True, knockouts=2, fish=1, seal=1, bounce=1), played(knockouts=1, fish=2))
    assert stats == {
        "rounds": 2,
        "wins": 1,
        "knockouts": 3,
        "fish": 3,
        "seal": 1,
        "bounce": 1,
        "streak": 0,
        "best_streak": 1,
        "best_round": 2,
        "party_wins": 0,
    }


@pytest.mark.parametrize("saved", [None, {}, "junk"])
def test_play_counts_never_saved_start_from_zero(saved):
    assert add_round(saved, played()) == {**STATS, "rounds": 1}


def test_a_loss_ends_the_run_of_wins_but_not_the_best_run():
    stats = counts_after(played(won=True), played(won=True), played())
    assert (stats["streak"], stats["best_streak"]) == (0, 2)
    stats = add_round(stats, played(won=True))
    assert (stats["streak"], stats["best_streak"]) == (1, 2)


def test_the_best_round_is_the_most_knockouts_in_a_single_round():
    stats = counts_after(played(knockouts=2), played(knockouts=5), played(knockouts=3))
    assert (stats["best_round"], stats["knockouts"]) == (5, 10)


@pytest.mark.parametrize("won, people, party_wins", [(True, 3, 1), (True, 6, 1), (True, 2, 0), (False, 3, 0)])
def test_a_party_win_needs_a_win_and_three_people_at_the_start(won, people, party_wins):
    assert add_round({}, played(won=won, people=people))["party_wins"] == party_wins


def test_an_earned_item_says_what_to_do_for_one_and_for_many():
    assert earn_state("monocle", {})["text"] == "Win a round"
    assert earn_state("wizard", {})["text"] == "Win 15 rounds"
    assert earn_state("balloon", {})["text"] == "Win a round with 3 or more people playing"
    assert earn_state("wings", {})["text"] == "Win 3 rounds in a row"
    assert earn_state("gems", {})["text"] == "Knock out 3 penguins in one round"
    assert earn_state("snorkel", {})["text"] == "As a seal, splash 5 penguins in"


def test_progress_never_shows_more_than_is_needed():
    assert earn_state("midnight", {"wins": 2}) == {"text": "Win 5 rounds", "have": 2, "need": 5}
    assert earn_state("midnight", {"wins": 9}) == {"text": "Win 5 rounds", "have": 5, "need": 5}
    assert earn_state("midnight", None)["have"] == 0


def test_progress_reads_the_best_run_the_best_round_and_the_party_wins():
    stats = {"wins": 9, "knockouts": 50, "streak": 0, "best_streak": 2, "best_round": 1, "party_wins": 0}
    assert earn_state("wings", stats)["have"] == 2
    assert earn_state("gems", stats)["have"] == 1
    assert earn_state("balloon", stats)["have"] == 0


def test_an_item_sold_for_credits_has_nothing_to_earn():
    assert earn_state("crown", EVERYTHING) is None


def test_earned_items_come_in_catalog_order():
    assert earned_items({}) == []
    assert earned_items({"knockouts": 10, "rounds": 5, "wins": 5}) == [
        "midnight",
        "propeller",
        "monocle",
        "eyepatch",
        "medal",
    ]
    assert earned_items(EVERYTHING) == [item for item in ITEMS if "earn" in ITEMS[item]]


def test_half_the_catalog_is_sold_and_half_is_earned_and_the_scarf_is_given():
    assert len(ITEMS) == 73 and len(PRICED) == len(earned_items(EVERYTHING)) == 36
    assert {info["kind"] for info in ITEMS.values()} == set(KINDS)


def test_what_is_worn_drops_unknown_items_and_items_in_the_wrong_slot():
    saved = {"hat": "crown", "face": "unicorn", "back": "flames", "trail": "flames", "tail": "cape", "cheer": 5}
    assert clean_wear(saved) == {"hat": "crown", "trail": "flames", **SCARF}
    assert clean_wear({"skin": None}) == SCARF and clean_wear("junk") == SCARF and clean_wear(None) == SCARF


async def open_window(cog, *user_ids):
    """These people with the game open in one window: its match, then each one's connection"""
    room = FakeRoom("window")
    conns = [FakeConn(room, user_id) for user_id in user_ids]
    for conn in conns:
        await cog.join(conn.ctx, conn)
    return cog.matches["window"], *conns


async def finish_rounds(cog, match, count=1, **numbers):
    """Hand the cog this many finished rounds of one player's, as a match does, and wait for them to be saved"""
    for _ in range(count):
        cog.record_played(match, [played(**numbers)])
        await asyncio.gather(*cog.saving)


def unlocks(conn):
    return [message for message in conn.sent if "unlocked" in message]


async def set_counts(cog, user_id=USER, **counts):
    await cog.config.user_from_id(user_id).stats.set(counts)


@pytest.mark.asyncio
async def test_a_finished_round_is_added_to_each_players_saved_counts(paying):
    match, _, _ = await open_window(paying, USER, 2)
    rounds = [played(USER, won=True, knockouts=2, fish=1, people=2), played(2, seal=1, people=2)]
    paying.record_played(match, rounds)
    paying.record_played(match, rounds)
    await asyncio.gather(*paying.saving)
    assert await paying.config.user_from_id(USER).stats() == {
        **STATS,
        "rounds": 2,
        "wins": 2,
        "knockouts": 4,
        "fish": 2,
        "streak": 2,
        "best_streak": 2,
        "best_round": 2,
    }
    assert await paying.config.user_from_id(2).stats() == {**STATS, "rounds": 2, "seal": 2}


@pytest.mark.asyncio
async def test_reaching_a_count_unlocks_the_item_and_tells_only_that_player_once(paying):
    match, mine, theirs = await open_window(paying, USER, 2)
    await finish_rounds(paying, match, 4)
    assert unlocks(mine) == [] and (await paying.shop_view(mine.ctx, {}))["owned"] == ["scarf"]
    await finish_rounds(paying, match)
    assert unlocks(mine) == [{"unlocked": ["Propeller cap"]}] and unlocks(theirs) == []
    assert (await paying.shop_view(mine.ctx, {}))["owned"] == ["propeller", "scarf"]
    await finish_rounds(paying, match)
    assert unlocks(mine) == [{"unlocked": ["Propeller cap"]}] and unlocks(theirs) == []


@pytest.mark.asyncio
async def test_one_round_can_unlock_several_items_named_in_catalog_order(paying):
    match, mine = await open_window(paying, USER)
    await finish_rounds(paying, match, won=True, knockouts=10, people=3)
    assert unlocks(mine) == [{"unlocked": ["Monocle", "Eye patch", "Balloon", "Gem trail"]}]


@pytest.mark.asyncio
async def test_a_round_alone_against_cpus_reaches_the_play_counts(paying):
    match, conn = await open_window(paying, USER)
    await paying.message(conn.ctx, conn, {"sit": True})
    nothing = [0] * 6
    match.report_played(
        {
            "winner": 0,
            "knocked": [2, 0, 0, 0, 0, 0],
            "by": [-1, 0, 0, -1, -1, -1],
            "fish": nothing,
            "seal": nothing,
            "bounce": nothing,
        }
    )
    await asyncio.gather(*paying.saving)
    stats = await paying.config.user_from_id(USER).stats()
    assert (stats["rounds"], stats["wins"], stats["knockouts"]) == (1, 1, 2)
    assert unlocks(conn) == [{"unlocked": ["Monocle"]}]


@pytest.mark.asyncio
async def test_an_earned_item_is_worn_without_buying_it(paying):
    match, conn = await open_window(paying, USER)
    assert await paying.wear(conn.ctx, {"kind": "face", "item": "monocle"}) == {"error": "You don't have that yet."}
    await finish_rounds(paying, match, won=True)
    answer = await paying.wear(conn.ctx, {"kind": "face", "item": "monocle"})
    assert answer == {"owned": ["monocle", "scarf"], "wear": {"face": "monocle", **SCARF}}
    # Worked out from the counts each time, so nothing is saved as bought and nothing is paid
    assert await paying.config.user_from_id(USER).owned() == [] and balance(paying) == START


@pytest.mark.asyncio
async def test_an_earned_item_cant_be_bought(paying):
    for counts in ({}, EVERYTHING):
        await set_counts(paying, **counts)
        answer = await paying.buy(ctx_of(), {"item": "monocle"})
        assert "earned by playing" in answer["error"]
    assert balance(paying) == START and await paying.config.user_from_id(USER).owned() == []


@pytest.mark.asyncio
async def test_a_credit_item_that_isnt_owned_cant_be_worn_however_much_was_played(paying):
    await set_counts(paying, **EVERYTHING)
    assert await paying.wear(ctx_of(), {"kind": "hat", "item": "crown"}) == {"error": "You don't have that yet."}
    assert await paying.config.user_from_id(USER).wear() == {}
    assert "crown" not in (await paying.shop_view(ctx_of(), {}))["owned"]


@pytest.mark.asyncio
async def test_one_item_of_every_kind_is_worn_at_once_and_shows_on_the_penguin(paying):
    assert list(OUTFIT) == list(KINDS)
    await paying.config.user_from_id(USER).owned.set(list(OUTFIT.values()))
    _, conn = await open_window(paying, USER)
    await paying.message(conn.ctx, conn, {"sit": True})
    for kind, item in OUTFIT.items():
        answer = await paying.wear(conn.ctx, {"kind": kind, "item": item})
        assert answer["wear"][kind] == item
    assert answer["wear"] == OUTFIT
    assert paying.matches["window"].seats[0].looks == OUTFIT


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_every_kind_can_be_taken_off_and_the_rest_stays_on(paying, kind):
    await paying.config.user_from_id(USER).set({"owned": list(OUTFIT.values()), "wear": OUTFIT})
    _, conn = await open_window(paying, USER)
    await paying.message(conn.ctx, conn, {"sit": True})
    rest = {other: item for other, item in OUTFIT.items() if other != kind}
    assert (await paying.wear(conn.ctx, {"kind": kind, "item": None}))["wear"] == rest
    assert paying.matches["window"].seats[0].looks == rest
    # Taking off what isn't worn changes nothing
    assert (await paying.wear(conn.ctx, {"kind": kind, "item": None}))["wear"] == rest


@pytest.mark.asyncio
async def test_putting_on_another_item_of_a_kind_replaces_the_one_worn(paying):
    await paying.config.user_from_id(USER).owned.set(["crown", "beanie", "cape"])
    for item in ("crown", "cape", "beanie"):
        answer = await paying.wear(ctx_of(), {"kind": ITEMS[item]["kind"], "item": item})
    assert answer["wear"] == {"hat": "beanie", "back": "cape", **SCARF}


@pytest.mark.asyncio
async def test_the_shop_shows_how_each_earned_item_is_earned_and_how_far_the_player_is(paying):
    await set_counts(paying, wins=2)
    view = await paying.shop_view(ctx_of(), {})
    assert set(view) == {"items", "currency", "balance", "owned", "wear"}
    assert [item["id"] for item in view["items"]] == list(ITEMS)
    assert all(set(item) == {"id", "kind", "name", "price", "earn"} for item in view["items"])
    earn = {item["id"]: item["earn"] for item in view["items"]}
    assert earn["wizard"] == {"text": "Win 15 rounds", "have": 2, "need": 15}
    assert earn["monocle"] == {"text": "Win a round", "have": 1, "need": 1}
    assert earn["crown"] is None
    # Every item is either sold or earned, never both, but the scarf, which everyone has
    given = [item["id"] for item in view["items"] if (item["price"] is None) == (item["earn"] is None)]
    assert given == ["scarf"] and earn["scarf"] is None
    assert view["owned"] == ["monocle", "scarf"]


@pytest.mark.asyncio
async def test_the_owned_list_is_bought_and_earned_items_in_catalog_order(paying):
    await paying.config.user_from_id(USER).set({"owned": ["flames", "crown"], "stats": {"wins": 5}})
    owned = (await paying.shop_view(ctx_of(), {}))["owned"]
    assert owned == ["midnight", "crown", "monocle", "scarf", "medal", "flames"]


@pytest.mark.asyncio
async def test_the_settings_list_only_the_items_sold_for_credits(paying):
    answer = await paying.shop_settings(ctx_of(ADMIN_ID), {})
    assert list(answer["settings"]) == list(answer["defaults"]) == list(SOLD)
    assert "monocle" not in answer["settings"] and all(type(price) is int for price in answer["settings"].values())


@pytest.mark.asyncio
async def test_deleting_a_player_clears_their_play_counts_and_what_they_earned(paying):
    await set_counts(paying, wins=5)
    await paying.wear(ctx_of(), {"kind": "skin", "item": "midnight"})
    await paying.red_delete_data_for_user(requester="user", user_id=USER)
    assert await paying.config.user_from_id(USER).all() == {"owned": [], "wear": {}, "stats": {}, "foes": {}}
    view = await paying.shop_view(ctx_of(), {})
    assert view["owned"] == ["scarf"] and view["wear"] == SCARF
    assert "error" in await paying.wear(ctx_of(), {"kind": "skin", "item": "midnight"})
