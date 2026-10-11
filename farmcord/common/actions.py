"""The page's requests (hub.api). Each one checks the values the page sent, then works on the player's farm under the
player's lock: load it (a first visit makes one), settle it up to now, apply the game rule, save it, and send the
state back with what happened. The game rules live in farmcord/game; nothing here decides an outcome"""

import logging
import typing as t

from ..abc import MixinMeta
from ..catalog import CREDIT, CREDIT_URL, PLOTS, SPOTS, catalog_payload
from ..game.farm import (
    breed,
    feed,
    harvest,
    move_baby,
    plant,
    refill,
    settle,
    till,
    water,
    water_animal,
)
from ..game.market import (
    buy_animal,
    buy_cosmetic,
    buy_feed,
    buy_room,
    buy_seeds,
    buy_storage,
    buy_tool,
    describe_room,
    discard,
    free_packet,
    pick_up_decoration,
    place_decoration,
    sell_animal,
    sell_crops,
    set_prefs,
    switch_plot,
    unlock_plot,
    wear,
)
from ..game.model import Farm, Refused, new_farm
from .payload import state
from .payouts import (
    DEFAULTS,
    MAX_COINS,
    NONE_LEFT,
    NOTHING_EARNED,
    PAYOUTS_OFF,
    SHAPE,
    SettingsError,
    most_coins,
    worth,
)

log = logging.getLogger("red.vrt.farmcord")

OPENING = "FarmCord is still opening. Try again in a moment."
BAD_REQUEST = "Something in that request isn't right."
IN_A_SERVER = "Converting FarmCoins only works in a server."
NOTHING_TO_CONVERT = "You have no FarmCoins to convert."
PICK_COINS = "Pick how many FarmCoins to convert."
NOT_AN_ADMIN = "Only server admins can change payouts."
MAX_QUANTITY = 10_000
# Catalog keys, choices like "male" or "yard", and animal and decoration ids are all short
NAME_LIMIT = 64
# The game keeps 200 characters of a description; anything far longer isn't from the page
TEXT_LIMIT = 1000
# A place in a room is a share of its width or height, and the game pulls it back inside the room. This only keeps
# a huge whole number from overflowing when the game turns it into a float
SHARE_LIMIT = 1_000_000
MISSING = object()

# A game rule run by an action: given the settled farm, the moment and the page's values, it returns its result and
# its events, or raises Refused before changing anything
Rule = t.Callable[..., tuple[dict, list[dict]]]


class Field(t.NamedTuple):
    """One value the page sends: its test, the refusal when the test fails, and the value used when the page leaves
    it out (MISSING makes it required)"""

    test: t.Callable[[t.Any], bool]
    error: str
    default: t.Any = MISSING


def whole(low: int, high: int) -> t.Callable[[t.Any], bool]:
    """A real int from low to high. True and 2.0 don't pass: as dict keys they would pass for 1 and 2"""
    return lambda value: type(value) is int and low <= value <= high


def text(limit: int) -> t.Callable[[t.Any], bool]:
    return lambda value: isinstance(value, str) and len(value) <= limit


def flag(value: t.Any) -> bool:
    return type(value) is bool


def share(value: t.Any) -> bool:
    # abs() of NaN or infinity fails the comparison, so those are refused too
    return type(value) in (int, float) and abs(value) <= SHARE_LIMIT


PLOT = Field(whole(1, max(PLOTS)), "There's no such plot")
SPOT = Field(whole(0, SPOTS - 1), "There's no such spot")
QUANTITY = Field(whole(1, MAX_QUANTITY), f"Pick a whole number from 1 to {MAX_QUANTITY:,}")
TIER = Field(whole(0, 9), "There's no such upgrade")
ROOM = Field(whole(0, 9), "There's no such room")
NAME = Field(text(NAME_LIMIT), "That isn't in FarmCord")
ID = Field(text(NAME_LIMIT), "That isn't on your farm.")
OUTFIT = Field(lambda value: value is None or text(NAME_LIMIT)(value), "You don't own that")
DIG = Field(flag, "Pick yes or no", default=False)
SWITCH = Field(flag, "Sound and music are either on or off")
SHARE = Field(share, "That isn't a spot in the room")
TEXT = Field(text(TEXT_LIMIT), "A description is text")
COINS = Field(whole(0, MAX_COINS), PICK_COINS)
SETTINGS = Field(lambda value: isinstance(value, dict), SHAPE)
AT_SPOT = {"plot": PLOT, "spot": SPOT}


def read(data: t.Any, fields: dict[str, Field]) -> tuple[dict, str | None]:
    """The page's values, or why they can't be used: exactly the keys named (optional ones may be left out), each
    passing its field's test"""
    if not isinstance(data, dict) or not set(data) <= set(fields):
        return {}, BAD_REQUEST
    values = {}
    for name, field in fields.items():
        if name not in data and field.default is MISSING:
            return {}, BAD_REQUEST
        value = data.get(name, field.default)
        if not field.test(value):
            return {}, field.error
        values[name] = value
    return values, None


def look(farm: Farm, now: float) -> tuple[dict, list[dict]]:
    """The rule of an action that only looks: the settle before it is all that happens"""
    return {}, []


class Actions(MixinMeta):
    def action_handlers(self) -> dict[str, t.Callable]:
        return {
            "open": self.act_open,
            "state": self.act_state,
            "till": self.act_till,
            "plant": self.act_plant,
            "water": self.act_water,
            "refill": self.act_refill,
            "harvest": self.act_harvest,
            "feed": self.act_feed,
            "water_animal": self.act_water_animal,
            "breed": self.act_breed,
            "move_baby": self.act_move_baby,
            "buy_seeds": self.act_buy_seeds,
            "buy_feed": self.act_buy_feed,
            "buy_animal": self.act_buy_animal,
            "buy_tool": self.act_buy_tool,
            "buy_storage": self.act_buy_storage,
            "buy_room": self.act_buy_room,
            "buy_cosmetic": self.act_buy_cosmetic,
            "sell_crops": self.act_sell_crops,
            "sell_animal": self.act_sell_animal,
            "unlock_plot": self.act_unlock_plot,
            "switch_plot": self.act_switch_plot,
            "discard": self.act_discard,
            "free_packet": self.act_free_packet,
            "place": self.act_place,
            "pick_up": self.act_pick_up,
            "wear": self.act_wear,
            "describe": self.act_describe,
            "prefs": self.act_prefs,
            "leaderboard": self.act_leaderboard,
            "offer": self.act_offer,
            "convert": self.act_convert,
            "payouts": self.act_payouts,
            "save_payouts": self.act_save_payouts,
        }

    def gate(self, data: t.Any, fields: dict[str, Field]) -> tuple[dict, str | None]:
        """The page's values, or why the request can't run"""
        if not self.ready.is_set():
            return {}, OPENING
        return read(data, fields)

    async def settled(self, ctx) -> tuple[Farm, float, list[dict]]:
        """The player's farm (a first visit makes one) with their current Discord name, settled up to now, plus that
        moment and the settle's events. The caller holds the player's lock"""
        now = self.clock()
        farm = await self.store.load(ctx.author.id) or new_farm(ctx.author.id, ctx.author.display_name, now)
        farm.name = ctx.author.display_name
        return farm, now, settle(farm, now, self.rng)

    async def play(self, ctx, data: t.Any, fields: dict[str, Field], rule: Rule) -> dict:
        """The steps every farm action shares. A refusal saves nothing, not even the settle before it, so whatever
        happened meanwhile is reported by the player's next action instead of being lost"""
        values, problem = self.gate(data, fields)
        if problem:
            return {"error": problem}
        async with self.locks[ctx.author.id]:
            farm, now, events = await self.settled(ctx)
            try:
                result, more = rule(farm, now, **values)
            except Refused as e:
                log.debug("Refused user %s: %s", ctx.author.id, e)
                return {"error": str(e)}
            await self.store.save(farm)
        return {"state": state(farm, now), "events": events + more, "result": result}

    # ---------- Looking ----------

    async def act_open(self, ctx, data: dict) -> dict:
        """The first request of a visit. Its events are the "while you were away" summary"""
        reply = await self.play(ctx, data, {}, look)
        if "error" in reply:
            return reply
        return {
            **reply,
            "catalog": catalog_payload(),
            "credit": CREDIT,
            "credit_url": CREDIT_URL,
            "can_set_payouts": await self.can_set_payouts(ctx),
        }

    async def act_state(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {}, look)

    async def act_leaderboard(self, ctx, data: dict) -> dict:
        """The top farms by level, then XP, and the player's own rank (None before their first visit)"""
        values, problem = self.gate(data, {})
        if problem:
            return {"error": problem}
        top, rank = await self.store.leaderboard(ctx.author.id)
        rows = [{"id": str(row["user_id"]), "name": row["name"], "level": row["level"], "xp": row["xp"]} for row in top]
        return {"top": rows, "rank": rank}

    # ---------- The fields and the pens ----------

    async def act_till(self, ctx, data: dict) -> dict:
        """A hoe tap. A growing crop is dug up only with dig: true, which the page sends once the player said yes"""
        fields = {**AT_SPOT, "dig": DIG}
        return await self.play(ctx, data, fields, lambda farm, now, plot, spot, dig: till(farm, plot, spot, now, dig))

    async def act_plant(self, ctx, data: dict) -> dict:
        fields = {**AT_SPOT, "crop": NAME}
        return await self.play(
            ctx, data, fields, lambda farm, now, plot, spot, crop: plant(farm, plot, spot, crop, now)
        )

    async def act_water(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, AT_SPOT, lambda farm, now, plot, spot: water(farm, plot, spot, now))

    async def act_refill(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {}, lambda farm, now: refill(farm))

    async def act_harvest(self, ctx, data: dict) -> dict:
        return await self.play(
            ctx, data, AT_SPOT, lambda farm, now, plot, spot: harvest(farm, plot, spot, now, self.rng)
        )

    async def act_feed(self, ctx, data: dict) -> dict:
        fields = {"animal": ID, "item": NAME}
        return await self.play(ctx, data, fields, lambda farm, now, animal, item: feed(farm, animal, item, now))

    async def act_water_animal(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {"animal": ID}, lambda farm, now, animal: water_animal(farm, animal, now))

    async def act_breed(self, ctx, data: dict) -> dict:
        """A try for babies. A try that fails is a result, not a refusal: it still counts toward her rest"""
        return await self.play(ctx, data, {"animal": ID}, lambda farm, now, animal: breed(farm, animal, now, self.rng))

    async def act_move_baby(self, ctx, data: dict) -> dict:
        fields = {"animal": ID, "plot": PLOT}
        return await self.play(ctx, data, fields, lambda farm, now, animal, plot: move_baby(farm, animal, plot, now))

    # ---------- The Market ----------

    async def act_buy_seeds(self, ctx, data: dict) -> dict:
        fields = {"crop": NAME, "quantity": QUANTITY}
        return await self.play(ctx, data, fields, lambda farm, now, crop, quantity: buy_seeds(farm, crop, quantity))

    async def act_buy_feed(self, ctx, data: dict) -> dict:
        fields = {"kind": NAME, "quantity": QUANTITY}
        return await self.play(ctx, data, fields, lambda farm, now, kind, quantity: buy_feed(farm, kind, quantity))

    async def act_buy_animal(self, ctx, data: dict) -> dict:
        fields = {"kind": NAME, "sex": NAME, "plot": PLOT}
        return await self.play(
            ctx, data, fields, lambda farm, now, kind, sex, plot: buy_animal(farm, kind, sex, plot, now)
        )

    async def act_buy_tool(self, ctx, data: dict) -> dict:
        fields = {"tool": NAME, "tier": TIER}
        return await self.play(ctx, data, fields, lambda farm, now, tool, tier: buy_tool(farm, tool, tier))

    async def act_buy_storage(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {"tier": TIER}, lambda farm, now, tier: buy_storage(farm, tier))

    async def act_buy_room(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {"room": ROOM}, lambda farm, now, room: buy_room(farm, room))

    async def act_buy_cosmetic(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {"item": NAME}, lambda farm, now, item: buy_cosmetic(farm, item))

    async def act_sell_crops(self, ctx, data: dict) -> dict:
        fields = {"item": NAME, "quantity": QUANTITY}
        return await self.play(
            ctx, data, fields, lambda farm, now, item, quantity: sell_crops(farm, item, quantity, now)
        )

    async def act_sell_animal(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {"animal": ID}, lambda farm, now, animal: sell_animal(farm, animal, now))

    async def act_free_packet(self, ctx, data: dict) -> dict:
        return await self.play(ctx, data, {}, lambda farm, now: free_packet(farm))

    # ---------- Plots ----------

    async def act_unlock_plot(self, ctx, data: dict) -> dict:
        fields = {"plot": PLOT, "kind": NAME}
        return await self.play(ctx, data, fields, lambda farm, now, plot, kind: unlock_plot(farm, plot, kind))

    async def act_switch_plot(self, ctx, data: dict) -> dict:
        fields = {"plot": PLOT, "kind": NAME}
        return await self.play(ctx, data, fields, lambda farm, now, plot, kind: switch_plot(farm, plot, kind))

    # ---------- The farmhouse ----------

    async def act_discard(self, ctx, data: dict) -> dict:
        fields = {"item": NAME, "quantity": QUANTITY}
        return await self.play(ctx, data, fields, lambda farm, now, item, quantity: discard(farm, item, quantity))

    async def act_place(self, ctx, data: dict) -> dict:
        """Put a decoration in the yard or an extra room, at x and y as shares (0 to 1) of the room's size"""
        fields = {"decoration": ID, "room": NAME, "x": SHARE, "y": SHARE}
        return await self.play(
            ctx,
            data,
            fields,
            lambda farm, now, decoration, room, x, y: place_decoration(farm, decoration, room, x, y),
        )

    async def act_pick_up(self, ctx, data: dict) -> dict:
        return await self.play(
            ctx, data, {"decoration": ID}, lambda farm, now, decoration: pick_up_decoration(farm, decoration)
        )

    async def act_wear(self, ctx, data: dict) -> dict:
        """Put an owned outfit piece on in its slot, or take the slot's piece off with outfit: null"""
        fields = {"slot": NAME, "outfit": OUTFIT}
        return await self.play(ctx, data, fields, lambda farm, now, slot, outfit: wear(farm, slot, outfit))

    async def act_describe(self, ctx, data: dict) -> dict:
        fields = {"room": ROOM, "text": TEXT}
        return await self.play(ctx, data, fields, lambda farm, now, room, text: describe_room(farm, room, text))

    async def act_prefs(self, ctx, data: dict) -> dict:
        fields = {"sound": SWITCH, "music": SWITCH}
        return await self.play(ctx, data, fields, lambda farm, now, sound, music: set_prefs(farm, sound, music))

    # ---------- The bank counter ----------

    async def act_offer(self, ctx, data: dict) -> dict:
        """What converting this many FarmCoins would pay here, or the reason conversions don't work here. The amount
        is cut to the FarmCoins the farm holds and to what one cash-in takes; the conversion checks it all again"""
        values, problem = self.gate(data, {"coins": COINS})
        if problem:
            return {"error": problem}
        if ctx.guild is None:
            return {"offer": None, "reason": IN_A_SERVER}
        most = most_coins(await self.payouts.settings(ctx.guild))
        farm = await self.store.load(ctx.author.id)
        coins = min(values["coins"], farm.coins if farm else 0, most)
        offer = await self.payouts.offer(ctx.author, coins)
        if offer is None:
            return {"offer": None, "reason": PAYOUTS_OFF}
        return {"offer": {**offer, "coins": coins, "most": most}, "reason": None}

    async def act_convert(self, ctx, data: dict) -> dict:
        """Turn FarmCoins into the server's credits, taking no more than the farm holds or one cash-in pays for"""
        values, problem = self.gate(data, {"coins": COINS})
        if problem:
            return {"error": problem}
        if ctx.guild is None:
            return {"error": IN_A_SERVER}
        async with self.locks[ctx.author.id]:
            farm, now, events = await self.settled(ctx)
            settings = await self.payouts.settings(ctx.guild)
            coins = min(values["coins"], farm.coins, most_coins(settings))
            problem = await self.convert_refusal(ctx, farm, coins, settings)
            if problem:
                return {"error": problem}
            paid = await self.cash_in(ctx, farm, coins)
        if "error" in paid:
            return paid
        return {"state": state(farm, now), "events": events, "result": {**paid, "coins": coins}}

    async def convert_refusal(self, ctx, farm: Farm, coins: int, settings: dict) -> str | None:
        """Why the bank would turn this conversion down, in its own words, or None. Asked before the FarmCoins leave
        the farm, so a refusal saves nothing, and what the settle found is still news for the player's next action"""
        if not settings["on"]:
            return PAYOUTS_OFF
        if coins < 1:
            return PICK_COINS if farm.coins else NOTHING_TO_CONVERT
        if await self.payouts.used(ctx.author) >= settings["plays"]:
            return NONE_LEFT
        if worth(coins, settings) < 1:
            return NOTHING_EARNED
        return None

    async def cash_in(self, ctx, farm: Farm, coins: int) -> dict:
        """The FarmCoins leave the farm, and are saved gone, before the bank is asked, so the same FarmCoins can never
        pay twice. They come back if nothing was paid, the bank's error included"""
        farm.coins -= coins
        await self.store.save(farm)
        paid: dict = {}
        try:
            paid = await self.payouts.cash_in(ctx.author, coins)
        finally:
            # A refusal has no "paid", and a bank that raised left this empty
            if "paid" not in paid:
                farm.coins += coins
                await self.store.save(farm)
        return paid

    # ---------- Payout settings ----------

    async def can_set_payouts(self, ctx) -> bool:
        """
        Server admins set their server's payouts. With a global bank one balance is shared by every server, so
        only the bot owner does, for every server at once
        """
        is_owner = await self.bot.is_owner(ctx.author)
        if await self.payouts.bank.is_global():
            return is_owner
        if ctx.guild is None:
            return False
        if is_owner or ctx.author.id == ctx.guild.owner_id:
            return True
        member = ctx.guild.get_member(ctx.author.id)
        return member is not None and (member.guild_permissions.manage_guild or await self.bot.is_admin(member))

    async def payout_settings(self, ctx) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.can_set_payouts(ctx):
            return {"settings": None}
        return {
            "settings": await self.payouts.settings(ctx.guild),
            "defaults": DEFAULTS,
            "global": await self.payouts.bank.is_global(),
            "currency": await self.payouts.bank.get_currency_name(ctx.guild),
        }

    async def act_payouts(self, ctx, data: dict) -> dict:
        values, problem = self.gate(data, {})
        if problem:
            return {"error": problem}
        return await self.payout_settings(ctx)

    async def act_save_payouts(self, ctx, data: dict) -> dict:
        values, problem = self.gate(data, {"settings": SETTINGS})
        if problem:
            return {"error": problem}
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.can_set_payouts(ctx):
            return {"error": NOT_AN_ADMIN}
        try:
            await self.payouts.save(ctx.guild, values["settings"])
        except SettingsError as e:
            log.debug("Refused payout settings from user %s: %s", ctx.author.id, e)
            return {"error": str(e)}
        return await self.payout_settings(ctx)
