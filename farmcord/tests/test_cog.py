import asyncio
import json

import pytest
import pytest_asyncio

from farmcord.catalog import ANIMALS, CANS, CARE_WINDOW, CREDIT, CREDIT_URL, CROPS, PLOTS, STORAGE, catalog_payload
from farmcord.common.actions import (
    BAD_REQUEST,
    COINS,
    DIG,
    ID,
    NAME,
    OPENING,
    PLOT,
    QUANTITY,
    SHARE,
    SPOT,
    SWITCH,
    TEXT,
)
from farmcord.common.payload import GROWTH
from farmcord.game.calendar import DAY, HOUR
from farmcord.game.farm import NOT_YOURS
from farmcord.game.progress import xp_for_level
from farmcord.main import FarmCord
from farmcord.tests.fakes import GUILD_ID, OTHER_ID, PLAYER_ID, ctx_for, edit_farm, make_cog

ACTIONS = {
    "open",
    "state",
    "till",
    "plant",
    "water",
    "refill",
    "harvest",
    "feed",
    "water_animal",
    "breed",
    "move_baby",
    "buy_seeds",
    "buy_feed",
    "buy_animal",
    "buy_tool",
    "buy_storage",
    "buy_room",
    "buy_cosmetic",
    "sell_crops",
    "sell_animal",
    "unlock_plot",
    "switch_plot",
    "discard",
    "free_packet",
    "place",
    "pick_up",
    "wear",
    "describe",
    "prefs",
    "leaderboard",
    "offer",
    "convert",
    "payouts",
    "save_payouts",
}
STATE_KEYS = {
    "now",
    "player",
    "season",
    "weather",
    "tools",
    "storage",
    "items",
    "plots",
    "animals",
    "waiting",
    "achievements",
    "decorations",
    "rooms",
    "descriptions",
    "outfit",
    "outfits",
    "prefs",
    "switch_fee",
    "free_packet",
}
SPOT_0 = {"plot": 1, "spot": 0}
WILDFLOWER_STAGE = CROPS["wildflowers"].grow_time / 3


@pytest_asyncio.fixture
async def cog(store):
    return await make_cog(store)


def json_ready(reply: dict) -> dict:
    """The reply as the page gets it: JSON, with no NaN or Infinity"""
    return json.loads(json.dumps(reply, allow_nan=False))


async def sown(cog, ctx=None, spot=SPOT_0) -> dict:
    """A wildflower sown on a new farm's Plot 1, planted at the clock's moment"""
    ctx = ctx or ctx_for(PLAYER_ID)
    await cog.act_open(ctx, {})
    await cog.act_till(ctx, spot)
    return await cog.act_plant(ctx, {**spot, "crop": "wildflowers"})


def test_activityhub_registers_the_game():
    fakes = pytest.importorskip("activityhub.tests.fakes")
    hub = fakes.make_hub()
    game = fakes.register(hub, FarmCord(hub.bot))
    assert game is not None, hub.registry.failed
    assert game.key == "farmcord" and game.name == "FarmCord"
    assert game.description == "Grow crops, raise animals and build your farm"
    assert (game.icon, game.thumbnail) == ("icon.png", "thumb.png")
    assert set(game.actions) == ACTIONS


@pytest.mark.asyncio
async def test_open_makes_a_new_farm_and_sends_everything_the_page_needs(cog):
    reply = json_ready(await cog.act_open(ctx_for(PLAYER_ID), {}))
    assert set(reply) == {"state", "events", "result", "catalog", "credit", "credit_url", "can_set_payouts"}
    assert reply["events"] == [] and reply["result"] == {}
    assert reply["catalog"] == json_ready(catalog_payload())
    assert reply["credit"] == CREDIT and reply["credit_url"] == CREDIT_URL
    assert reply["can_set_payouts"] is False
    state = reply["state"]
    assert set(state) == STATE_KEYS and state["now"] == cog.clock.now
    assert state["player"] == {
        "id": str(PLAYER_ID),
        "name": "Player 7",
        "coins": 0,
        "xp": 0,
        "level": 1,
        "level_xp": xp_for_level(1),
        "next_xp": xp_for_level(2),
    }
    assert state["tools"] == {"can": 0, "hoe": 0, "water": CANS[0].capacity, "capacity": CANS[0].capacity}
    assert state["storage"] == {"tier": 0, "limit": STORAGE[0].limit}
    assert state["items"] == {"seed:wildflowers": {"quantity": 5, "worth": 0}}
    assert [plot["number"] for plot in state["plots"]] == sorted(PLOTS)
    first, second = state["plots"][0], state["plots"][1]
    assert first["unlocked"] and first["kind"] == "crops" and first["animals"] == []
    # Plot 1 can't become a pen while it is the only plot
    assert first["switch"] is None and second["unlocked"] is False and second["switch"] is None
    assert first["spots"][0] == {"index": 0, "state": "untilled", "crop": None, "cycle": 0, **dict.fromkeys(GROWTH)}
    assert len(first["spots"]) == 9
    assert state["animals"] == state["waiting"] == state["decorations"] == state["outfits"] == []
    assert state["achievements"] == state["descriptions"] == {} and state["rooms"] == 0
    assert state["outfit"] == {"hat": None, "top": None, "bottom": None}
    assert state["prefs"] == {"sound": True, "music": True}
    assert state["switch_fee"] > 0 and state["free_packet"] is False
    assert state["season"]["name"] in CROPS["wildflowers"].seasons and state["season"]["ends_at"] > state["now"]
    assert state["weather"]["name"] == "sun" and state["weather"]["ends_at"] > state["now"]
    assert (await cog.store.load(PLAYER_ID)).name == "Player 7"


@pytest.mark.asyncio
async def test_a_crop_from_bare_ground_to_sold(cog):
    me = ctx_for(PLAYER_ID)
    replies = [await cog.act_open(me, {})]
    replies.append(await cog.act_till(me, SPOT_0))
    assert replies[-1]["result"] == {"spots": [0]}
    tilled = replies[-1]["state"]["plots"][0]["spots"][0]
    assert tilled == {"index": 0, "state": "tilled", "crop": None, "cycle": 0, **dict.fromkeys(GROWTH)}
    replies.append(await cog.act_plant(me, {**SPOT_0, "crop": "wildflowers"}))
    planted = cog.clock.now
    spot = replies[-1]["state"]["plots"][0]["spots"][0]
    assert spot["state"] == "growing" and spot["crop"] == "wildflowers" and spot["stage"] == 0
    assert spot["stage_ends_at"] == planted + WILDFLOWER_STAGE and spot["ripe_at"] == planted + 3 * WILDFLOWER_STAGE
    assert spot["watered"] is False and spot["dry"] == 0 and spot["spoil"] is None
    assert spot["spoil_ends_at"] == spot["ripe_at"] and spot["value"] == 1.0
    for stage in range(3):
        replies.append(await cog.act_water(me, SPOT_0))
        spot = replies[-1]["state"]["plots"][0]["spots"][0]
        assert spot["stage"] == stage and spot["watered"] is True
        cog.clock.move(WILDFLOWER_STAGE)
    replies.append(await cog.act_state(me, {}))
    ripe = replies[-1]["state"]["plots"][0]["spots"][0]
    assert ripe["stage"] == 3 and ripe["stage_ends_at"] is None and ripe["watered"] is None and ripe["spoil"] == "fresh"
    replies.append(await cog.act_harvest(me, SPOT_0))
    picked = replies[-1]["result"]
    assert picked["crop"] == "wildflowers" and picked["perfect"] is True
    assert replies[-1]["state"]["plots"][0]["spots"][0]["state"] == "untilled"
    item = "crop:wildflowers:x" if picked["exceptional"] else "crop:wildflowers"
    assert replies[-1]["state"]["items"][item] == {"quantity": picked["amount"], "worth": picked["worth"]}
    replies.append(await cog.act_sell_crops(me, {"item": item, "quantity": picked["amount"]}))
    assert replies[-1]["result"]["coins"] == picked["worth"]
    assert item not in replies[-1]["state"]["items"]
    # Every FarmCoin came from the sale, the level-ups and the achievements
    rewards = sum(event["coins"] for reply in replies for event in reply["events"] if "coins" in event)
    assert replies[-1]["state"]["player"]["coins"] == picked["worth"] + rewards
    assert {"first_crop", "perfect_crop", "sell_crop"} <= set(replies[-1]["state"]["achievements"])
    json_ready(replies[-1])


BAD = [
    ("till", {}, BAD_REQUEST),
    ("till", {"plot": 1}, BAD_REQUEST),
    ("till", {"plot": 1, "spot": 0, "rake": True}, BAD_REQUEST),
    ("till", {"plot": "1", "spot": 0}, PLOT.error),
    ("till", {"plot": True, "spot": 0}, PLOT.error),
    ("till", {"plot": 1.0, "spot": 0}, PLOT.error),
    ("till", {"plot": 8, "spot": 0}, PLOT.error),
    ("till", {"plot": 1, "spot": 9}, SPOT.error),
    ("till", {"plot": 1, "spot": -1}, SPOT.error),
    ("till", {"plot": 1, "spot": 0, "dig": "yes"}, DIG.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": "2"}, QUANTITY.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": True}, QUANTITY.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": 0}, QUANTITY.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": -3}, QUANTITY.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": 10**30}, QUANTITY.error),
    ("buy_seeds", {"crop": "wildflowers", "quantity": 2.0}, QUANTITY.error),
    ("buy_seeds", {"crop": ["wildflowers"], "quantity": 1}, NAME.error),
    ("buy_seeds", {"crop": "gold", "quantity": 1}, "There's no such crop"),
    ("sell_crops", {"item": "seed:wildflowers", "quantity": 1}, "Only crops sell at the Market"),
    ("discard", {"item": "x" * 1000, "quantity": 1}, NAME.error),
    ("place", {"decoration": "d", "room": "yard", "x": 10**400, "y": 0}, SHARE.error),
    ("place", {"decoration": "d", "room": "yard", "x": float("inf"), "y": 0}, SHARE.error),
    ("place", {"decoration": "d", "room": "yard", "x": 0.5, "y": False}, SHARE.error),
    ("place", {"decoration": 5, "room": "yard", "x": 0.5, "y": 0.5}, ID.error),
    ("prefs", {"sound": 1, "music": True}, SWITCH.error),
    ("describe", {"room": 2, "text": 5}, TEXT.error),
    ("convert", {"coins": -1}, COINS.error),
    ("offer", {"coins": "all"}, COINS.error),
    ("feed", {"animal": "0" * 32, "item": "feed:chicken"}, NOT_YOURS),
    ("state", {"now": 0}, BAD_REQUEST),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("action, data, error", BAD)
async def test_bad_requests_get_a_plain_error_and_change_nothing(cog, action, data, error):
    me = ctx_for(PLAYER_ID)
    await cog.act_open(me, {})
    before = await cog.store.load(PLAYER_ID)
    assert await getattr(cog, f"act_{action}")(me, data) == {"error": error}
    assert await cog.store.load(PLAYER_ID) == before


@pytest.mark.asyncio
async def test_every_action_waits_for_the_database(cog):
    cog.ready.clear()
    for name, handler in cog.action_handlers().items():
        assert await handler(ctx_for(PLAYER_ID), {}) == {"error": OPENING}, name
    assert await cog.store.load(PLAYER_ID) is None


@pytest.mark.asyncio
async def test_a_refused_action_saves_nothing_and_the_next_one_reports_what_happened_meanwhile(cog):
    me = ctx_for(PLAYER_ID)
    await sown(cog)
    cog.clock.move(3 * WILDFLOWER_STAGE)
    before = await cog.store.load(PLAYER_ID)
    assert await cog.act_water(me, SPOT_0) == {"error": "It's ripe: harvest it"}
    assert await cog.store.load(PLAYER_ID) == before
    assert [event["kind"] for event in (await cog.act_state(me, {}))["events"]] == ["ripe"]


@pytest.mark.asyncio
async def test_two_harvests_at_once_run_one_after_the_other(cog):
    me = ctx_for(PLAYER_ID)
    await sown(cog)
    cog.clock.move(3 * WILDFLOWER_STAGE)
    first, second = await asyncio.gather(cog.act_harvest(me, SPOT_0), cog.act_harvest(me, SPOT_0))
    assert second == {"error": "Nothing to harvest here"}
    picked = first["result"]
    item = "crop:wildflowers:x" if picked["exceptional"] else "crop:wildflowers"
    assert (await cog.store.load(PLAYER_ID)).items[item].quantity == picked["amount"]


@pytest.mark.asyncio
async def test_open_after_days_away_lists_what_happened(cog):
    me = ctx_for(PLAYER_ID)
    await sown(cog)
    cog.clock.move(3 * DAY)
    reply = await cog.act_open(me, {})
    crops = [(event["kind"], event["plot"], event["spot"], event["crop"]) for event in reply["events"]]
    assert crops == [(kind, 1, 0, "wildflowers") for kind in ("ripe", "dried", "withered", "rotted")]
    rotted = reply["state"]["plots"][0]["spots"][0]
    assert rotted == {"index": 0, "state": "rotted", "crop": "wildflowers", "cycle": 0, **dict.fromkeys(GROWTH)}
    # Opening again at once has nothing new to tell
    assert (await cog.act_open(me, {}))["events"] == []


async def chicken_farmer(cog, user_id: int = PLAYER_ID) -> str:
    """A player with Plot 2 as a pen, holding one female chick bought at the clock's moment. Returns its id"""
    me = ctx_for(user_id)
    await cog.act_open(me, {})
    chicken = ANIMALS["chicken"]
    level = max(chicken.level, PLOTS[2].level)
    coins = PLOTS[2].price + chicken.baby_price + chicken.feed_price
    await edit_farm(cog, user_id, level=level, xp=xp_for_level(level), coins=coins)
    assert "error" not in await cog.act_unlock_plot(me, {"plot": 2, "kind": "animals"})
    bought = await cog.act_buy_animal(me, {"kind": "chicken", "sex": "female", "plot": 2})
    return bought["result"]["animal"]


@pytest.mark.asyncio
async def test_an_animal_bought_fed_watered_and_grown_up_while_away(cog):
    me = ctx_for(PLAYER_ID)
    chick = await chicken_farmer(cog)
    arrived = cog.clock.now
    state = (await cog.act_state(me, {}))["state"]
    assert state["plots"][1]["kind"] == "animals" and state["plots"][1]["animals"] == [chick]
    assert state["plots"][1]["spots"] == []
    assert state["animals"] == [
        {
            "id": chick,
            "kind": "chicken",
            "sex": "female",
            "plot": 2,
            "adult": False,
            "exceptional": False,
            "grows_up_at": arrived + ANIMALS["chicken"].grow_time,
            "condition": "healthy",
            "feed_by": arrived + CARE_WINDOW,
            "water_by": arrived + CARE_WINDOW,
            "can_breed": False,
            "breed_refusal": "She's too young to have babies",
            "expecting_until": None,
            "price": None,
        }
    ]
    await cog.act_buy_feed(me, {"kind": "chicken", "quantity": 1})
    cog.clock.move(HOUR)
    fed = await cog.act_feed(me, {"animal": chick, "item": "feed:chicken"})
    assert fed["state"]["animals"][0]["feed_by"] == cog.clock.now + CARE_WINDOW
    water = fed["state"]["tools"]["water"]
    drank = await cog.act_water_animal(me, {"animal": chick})
    assert drank["state"]["animals"][0]["water_by"] == cog.clock.now + CARE_WINDOW
    assert drank["state"]["tools"]["water"] == water - 1
    cog.clock.move(ANIMALS["chicken"].grow_time)
    back = await cog.act_open(me, {})
    grown = [event for event in back["events"] if event["kind"] == "grown"]
    assert len(grown) == 1 and grown[0]["animal"] == chick and grown[0]["species"] == "chicken"
    hen = back["state"]["animals"][0]
    assert hen["adult"] is True and hen["grows_up_at"] is None and hen["price"] > 0
    json_ready(back)


@pytest.mark.asyncio
async def test_another_players_animal_is_out_of_reach(cog):
    chick = await chicken_farmer(cog)
    stranger = ctx_for(OTHER_ID)
    await cog.act_open(stranger, {})
    for action, data in (
        ("water_animal", {"animal": chick}),
        ("sell_animal", {"animal": chick}),
        ("breed", {"animal": chick}),
        ("feed", {"animal": chick, "item": "feed:chicken"}),
    ):
        assert await getattr(cog, f"act_{action}")(stranger, data) == {"error": NOT_YOURS}, action
    assert len((await cog.store.load(PLAYER_ID)).animals) == 1


@pytest.mark.asyncio
async def test_the_farm_keeps_the_players_current_discord_name(cog):
    await cog.act_open(ctx_for(PLAYER_ID, name="Sam"), {})
    await cog.act_state(ctx_for(PLAYER_ID, name="Samuel"), {})
    assert (await cog.store.load(PLAYER_ID)).name == "Samuel"


@pytest.mark.asyncio
async def test_the_leaderboard_ranks_farms_with_ids_as_text(cog):
    await cog.act_open(ctx_for(PLAYER_ID), {})
    await cog.act_open(ctx_for(OTHER_ID), {})
    await edit_farm(cog, OTHER_ID, level=3, xp=xp_for_level(3))
    board = json_ready(await cog.act_leaderboard(ctx_for(PLAYER_ID), {}))
    assert board == {
        "top": [
            {"id": str(OTHER_ID), "name": "Player 8", "level": 3, "xp": xp_for_level(3)},
            {"id": str(PLAYER_ID), "name": "Player 7", "level": 1, "xp": 0},
        ],
        "rank": 2,
    }


@pytest.mark.asyncio
async def test_the_page_choices_reach_the_farm(cog):
    me = ctx_for(PLAYER_ID)
    await cog.act_open(me, {})
    prefs = await cog.act_prefs(me, {"sound": False, "music": True})
    assert prefs["state"]["prefs"] == {"sound": False, "music": True}
    await edit_farm(cog, PLAYER_ID, coins=0)
    await cog.act_discard(me, {"item": "seed:wildflowers", "quantity": 5})
    packet = await cog.act_free_packet(me, {})
    assert packet["result"] == {"item": "seed:wildflowers", "quantity": 1}
    assert packet["state"]["free_packet"] is False


@pytest.mark.asyncio
async def test_deleting_a_players_data_removes_the_farm_and_their_cash_ins(cog):
    await cog.act_open(ctx_for(PLAYER_ID), {})
    await cog.act_open(ctx_for(OTHER_ID), {})
    await cog.config.user_from_id(PLAYER_ID).cashed.set({"day": "2026-10-10", "count": 1})
    await cog.config.member_from_ids(GUILD_ID, PLAYER_ID).cashed.set({"day": "2026-10-10", "count": 1})
    await cog.red_delete_data_for_user(requester="user", user_id=PLAYER_ID)
    assert await cog.store.load(PLAYER_ID) is None
    assert await cog.store.load(OTHER_ID) is not None
    assert await cog.config.user_from_id(PLAYER_ID).cashed() == {}
    assert await cog.config.member_from_ids(GUILD_ID, PLAYER_ID).cashed() == {}


@pytest.mark.asyncio
async def test_deleting_waits_for_an_action_in_progress(cog):
    await cog.act_open(ctx_for(PLAYER_ID), {})
    async with cog.locks[PLAYER_ID]:
        deleting = asyncio.create_task(cog.red_delete_data_for_user(requester="user", user_id=PLAYER_ID))
        await asyncio.sleep(0.2)
        assert not deleting.done() and await cog.store.load(PLAYER_ID) is not None
    await deleting
    assert await cog.store.load(PLAYER_ID) is None


@pytest.mark.asyncio
async def test_deleting_gives_up_on_the_farm_when_the_database_never_opens(cog, monkeypatch):
    await cog.act_open(ctx_for(PLAYER_ID), {})
    cog.ready.clear()
    monkeypatch.setattr("farmcord.main.DELETE_WAIT", 0.05)
    await asyncio.wait_for(cog.red_delete_data_for_user(requester="user", user_id=PLAYER_ID), 5)
    assert await cog.store.load(PLAYER_ID) is not None
