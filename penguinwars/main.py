import asyncio
import logging
import typing as t
from dataclasses import asdict
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.leaderboard import MEMBER_DEFAULTS, Result, add_result, rank
from .common.match import NO_SNOWBALLS, Match
from .common.shop import (
    EXTRAS,
    GIVEN,
    ITEMS,
    KINDS,
    LINE_LIMIT,
    PRICED,
    Played,
    SOLD,
    SettingsError,
    Shop,
    ShopRefused,
    achievements,
    add_foe,
    add_round,
    clean_wear,
    earn_state,
    earned_items,
    nemesis_id,
    nemesis_of,
    stats_of,
    wear_to_save,
)
from .common.tuning import SLIDERS, TWISTS, Tuning, clean_tuning, load_tuning
from .common.tuning import SettingsError as TuningError

log = logging.getLogger("red.vrt.penguinwars")

KEY = "penguinwars"
NOT_AN_ADMIN = "Only server admins can change the shop."
NOT_THE_BANK_OWNER = "The bank is global, so only the bot owner can change the shop."
NOT_THE_OWNER = "Only the bot owner can change the game's numbers."
NOT_HERE = "That player isn't here."
# What a profile shows of a player's leaderboard row
SERVER_KEYS = ("rank", "wins", "knockouts", "rounds")


class PenguinWars(commands.Cog):
    """
    A penguin knockout game for ActivityHub.

    Up to six penguins slide into each other on a shrinking ice floe. Computer penguins fill empty seats.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026110401, force_registration=True)
        self.config.register_global(tuning={}, prices=None, tally={})
        self.config.register_guild(prices=None, tally={})
        # What a player bought, what they wear as {kind: item} (None for a given item they took off), the play counts
        # that unlock the earned looks, and who knocked them out how often
        self.config.register_user(owned=[], wear={}, stats={}, foes={})
        self.config.register_member(**MEMBER_DEFAULTS)
        self.shop = Shop(self.config)
        # One lock per player for everything that changes what they own, so two devices never overwrite each other
        self.locks: dict[int, asyncio.Lock] = {}
        self.tuning = Tuning()
        self.tuning_lock = asyncio.Lock()
        # One match per Activity window, keyed by the window's instance id
        self.matches: dict[str, Match] = {}
        # Saves of finished rounds still running, and the lock that keeps the leaderboard's in order
        self.saving: set[asyncio.Task] = set()
        self.save_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        saved = await self.config.tuning()
        self.tuning = load_tuning(saved if isinstance(saved, dict) else {})

    async def cog_unload(self):
        for match in list(self.matches.values()):
            match.stop()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Each clear waits for the saves that could bring the row back: a buy in flight, a leaderboard save, a
        # tally count. The saves of rounds that already ended go first, as one still waiting its turn would write
        # this player back into their own counts or into someone else's foes
        await asyncio.gather(*self.saving, return_exceptions=True)
        async with self.lock(user_id):
            await self.config.user_from_id(user_id).clear()
        await self.forget_foe(user_id)
        async with self.save_lock:
            for guild_id, members in (await self.config.all_members()).items():
                if user_id in members:
                    await self.config.member_from_ids(guild_id, user_id).clear()
        async with self.shop.lock:
            for guild_id in await self.config.all_guilds():
                await self.forget_paid(self.config.guild_from_id(guild_id).tally, user_id)
            await self.forget_paid(self.config.tally, user_id)

    async def forget_foe(self, user_id: int) -> None:
        """Take a deleted player, and their name, out of everyone else's count of who knocked them out"""
        key = str(user_id)
        for other_id, saved in (await self.config.all_users()).items():
            if key not in saved["foes"]:
                continue
            async with self.lock(other_id):
                async with self.config.user_from_id(other_id).foes() as foes:
                    foes.pop(key, None)

    async def forget_paid(self, value: t.Any, user_id: int) -> None:
        tally = await value()
        if user_id in tally.get("players", []):
            tally["players"].remove(user_id)
            await value.set(tally)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Penguin Wars",
            "description": "Slide your penguin and knock the others off the ice",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.svg",
            "thumbnail": "thumb.png",
            "economy": self.economy_line,
            "actions": {
                "leaderboard": self.leaderboard,
                "shop": self.shop_view,
                "buy": self.buy,
                "wear": self.wear,
                "extras": self.extras_view,
                "crate": self.drop_crate,
                "party": self.party_round,
                "snowball": self.throw_snowball,
                "profile": self.profile,
                "shop_settings": self.shop_settings,
                "save_shop": self.save_shop,
                "tuning": self.tuning_view,
                "save_tuning": self.save_tuning,
            },
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.8.0",
        }

    async def looks_of(self, user_id: int) -> dict:
        return clean_wear(await self.config.user_from_id(user_id).wear())

    def match_for(self, conn: t.Any) -> Match:
        """The window's match, started when its first player arrives, or again after a round failed"""
        match = self.matches.get(conn.ctx.instance_id)
        if match is None:
            match = Match(
                conn.room, self.tuning, self.match_ended, recorded=self.record_round, played=self.record_played
            )
            self.matches[conn.ctx.instance_id] = match
            match.start()
        elif match.room is not conn.room:
            # Reloading ActivityHub gives the window a new room, while the match keeps seats for its dropped players
            match.room = conn.room
        return match

    def match_ended(self, match: Match) -> None:
        if self.matches.get(match.room.instance_id) is match:
            del self.matches[match.room.instance_id]

    async def join(self, ctx, conn) -> None:
        looks = await self.looks_of(ctx.author.id)
        nemesis = nemesis_id(await self.config.user_from_id(ctx.author.id).foes())
        match = await self.window_match(conn)
        # Sent ahead of the window's state, so the first name tags a page draws already carry the mark
        await conn.send({"nemesis": nemesis})
        await match.join(conn, looks)

    async def message(self, ctx, conn, data) -> None:
        match = await self.window_match(conn)
        await match.message(conn, data)

    async def window_match(self, conn: t.Any) -> Match:
        """The window's match. One started now, after a failed round, has forgotten its server and everyone's looks"""
        fresh = conn.ctx.instance_id not in self.matches
        match = self.match_for(conn)
        if fresh:
            match.guild_id = conn.ctx.guild_id
            for other in conn.room.connections:
                match.set_looks(other.ctx.author.id, await self.looks_of(other.ctx.author.id))
        return match

    async def leave(self, ctx, conn) -> None:
        # No await before this: the match must see the drop before its loop can decide the window is empty
        match = self.matches.get(ctx.instance_id)
        if match is not None:
            match.leave(conn)

    def record_round(self, guild_id: int | None, results: list[Result]) -> None:
        # Saved off the update loop, after the round, so Config never slows play. A window with no server saves nothing
        if guild_id is None:
            return
        task = asyncio.create_task(self.save_results(guild_id, results))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def save_results(self, guild_id: int, results: list[Result]) -> None:
        async with self.save_lock:
            for result in results:
                try:
                    group = self.config.member_from_ids(guild_id, result.user_id)
                    await group.set(add_result(await group.all(), result))
                except Exception as e:
                    log.error("Couldn't save a Penguin Wars result for user %s", result.user_id, exc_info=e)

    def record_played(self, match: Match, people: list[Played]) -> None:
        # Saved off the update loop, like the leaderboard
        task = asyncio.create_task(self.save_played(match, people))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def save_played(self, match: Match, people: list[Played]) -> None:
        """Add a finished round to each player's play counts and to who knocked them out, and tell them what it
        unlocked and who their nemesis is when that changed"""
        for played in people:
            try:
                async with self.lock(played.user_id):
                    group = self.config.user_from_id(played.user_id)
                    before = await group.stats()
                    after = add_round(before, played)
                    await group.stats.set(after)
                    was, nemesis = await self.count_foe(group, played)
                had = set(earned_items(before))
                unlocked = [ITEMS[item]["name"] for item in earned_items(after) if item not in had]
                if unlocked:
                    await match.tell(played.user_id, {"unlocked": unlocked})
                if nemesis != was:
                    await match.tell(played.user_id, {"nemesis": nemesis})
            except Exception as e:
                log.error("Couldn't save a Penguin Wars round for user %s", played.user_id, exc_info=e)

    async def count_foe(self, group: t.Any, played: Played) -> tuple[str | None, str | None]:
        """Add the person who knocked this player out to the player's count of them. Returns the id of the player's
        nemesis before and after"""
        foes = await group.foes()
        was = nemesis_id(foes)
        if played.by is None:
            return was, was
        foes = add_foe(foes, played.by, played.by_name)
        await group.foes.set(foes)
        return was, nemesis_id(foes)

    async def leaderboard(self, ctx, data: dict) -> dict:
        """The server's top 10"""
        if ctx.guild is None:
            return {"top": [], "you": None, "dm": True}
        return rank(await self.config.all_members(ctx.guild), ctx.author.id)

    # ---------- Profile ----------

    def profile_id(self, ctx, value: t.Any) -> int | None:
        """The player a profile was asked for: the asker when no id came, otherwise the id sent as text. None for
        anything that isn't an id"""
        if value is None:
            return ctx.author.id
        if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 20:
            return None
        return int(value)

    def name_here(self, ctx, user_id: int) -> str | None:
        """The name of the asker, or of someone else in the asker's window. None for anyone else"""
        if user_id == ctx.author.id:
            return ctx.author.display_name
        match = self.matches.get(ctx.instance_id)
        return match.name_of(user_id) if match is not None else None

    async def profile(self, ctx, data: dict) -> dict:
        """One player's card: what they wear, their play counts, where they stand in this server, their achievements
        and their nemesis. Only for the asker, someone in their window, or someone on this server's leaderboard"""
        user_id = self.profile_id(ctx, data.get("id"))
        if user_id is None:
            return {"error": NOT_HERE}
        members = await self.config.all_members(ctx.guild) if ctx.guild is not None else {}
        standing = rank(members, user_id)["you"]
        name = self.name_here(ctx, user_id) or (standing["name"] if standing is not None else None)
        if name is None:
            return {"error": NOT_HERE}
        # Waits for a running save of theirs to finish, so the card never shows half of a finished round
        async with self.lock(user_id):
            saved = await self.config.user_from_id(user_id).all()
        looks = clean_wear(saved["wear"])
        return {
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(user_id),
            "name": name,
            "you": user_id == ctx.author.id,
            "looks": looks,
            "title": ITEMS[looks["title"]]["name"] if "title" in looks else None,
            "style": looks.get("name"),
            "stats": stats_of(saved["stats"]),
            "server": {key: standing[key] for key in SERVER_KEYS} if standing is not None else None,
            "achievements": achievements(saved["stats"]),
            "nemesis": nemesis_of(saved["foes"]),
        }

    # ---------- Shop ----------

    def lock(self, key: int) -> asyncio.Lock:
        return self.locks.setdefault(key, asyncio.Lock())

    def can_wear(self, saved: dict) -> list[str]:
        """Every item the player may put on: what everyone is given, what they bought and what their play counts
        have earned"""
        mine = {*GIVEN.values(), *saved["owned"], *earned_items(saved["stats"])}
        return [item for item in ITEMS if item in mine]

    def owned_state(self, saved: dict) -> dict:
        return {"owned": self.can_wear(saved), "wear": clean_wear(saved["wear"])}

    async def balance_of(self, ctx) -> int | None:
        return await self.shop.bank.get_balance(ctx.author) if ctx.guild is not None else None

    async def give_back(self, member, item: str, price: int) -> str:
        """Return a price after the item couldn't be saved, and say truthfully what happened"""
        try:
            await self.shop.refund(member, price)
        except Exception as e:
            log.error(
                "Couldn't refund %s credits to user %s for Penguin Wars item %s", price, member.id, item, exc_info=e
            )
            return "That didn't go through and your payment couldn't be returned. Tell a server admin."
        return "That didn't go through, and nothing was taken."

    async def shop_view(self, ctx, data: dict) -> dict:
        """Every look, with its price where the player is or how it is earned, and what they own and wear"""
        prices = await self.shop.prices(ctx.guild)
        # Waits for a running buy or wear to finish saving, so a re-read never shows the old state
        async with self.lock(ctx.author.id):
            saved = await self.config.user(ctx.author).all()
        return {
            "items": [
                {
                    "id": item,
                    "kind": info["kind"],
                    "name": info["name"],
                    "price": prices.get(item),
                    "earn": earn_state(item, saved["stats"]),
                }
                for item, info in ITEMS.items()
            ],
            "currency": await self.shop.currency(ctx.guild) if ctx.guild is not None else "credits",
            "balance": await self.balance_of(ctx),
            **self.owned_state(saved),
        }

    async def buy(self, ctx, data: dict) -> dict:
        """One item paid with credits, once. The credits are given back when the item can't be saved"""
        item = data.get("item")
        if type(item) is not str or item not in ITEMS:
            return {"error": "That item doesn't exist."}
        if item in GIVEN.values():
            return {"error": "You already own that."}
        if item not in PRICED:
            return {"error": "That one can't be bought. It is earned by playing."}
        key = ctx.author.id
        try:
            # One buy at a time per player: a second tap or second device waits, then finds the item already owned
            async with self.lock(key):
                group = self.config.user_from_id(key)
                owned = await group.owned()
                if item in owned:
                    return {"error": "You already own that."}
                price = await self.shop.buy(ctx.author, item)
                try:
                    await group.owned.set([*owned, item])
                except Exception as e:
                    log.error("Couldn't save a Penguin Wars purchase for user %s", key, exc_info=e)
                    raise ShopRefused(await self.give_back(ctx.author, item, price)) from e
                await self.shop.count(ctx.author, price)
                saved = await group.all()
        except ShopRefused as e:
            return {"error": str(e)}
        return {**self.owned_state(saved), "balance": await self.balance_of(ctx)}

    async def wear(self, ctx, data: dict) -> dict:
        """Put on an item the player has, or take one off with {"kind": ..., "item": None}. Needs no server. A given
        item that was taken off stays off, as that is saved too"""
        item, kind = data.get("item"), data.get("kind")
        if kind not in KINDS:
            return {"error": "That isn't something a penguin wears."}
        if item is not None and (type(item) is not str or item not in ITEMS or ITEMS[item]["kind"] != kind):
            return {"error": "That doesn't go there."}
        key = ctx.author.id
        async with self.lock(key):
            group = self.config.user_from_id(key)
            saved = await group.all()
            if item is not None and item not in self.can_wear(saved):
                return {"error": "You don't have that yet."}
            wear = clean_wear(saved["wear"])
            if item is None:
                wear.pop(kind, None)
            else:
                wear[kind] = item
            saved["wear"] = wear_to_save(wear)
            await group.wear.set(saved["wear"])
        match = self.matches.get(ctx.instance_id)
        if match is not None:
            match.set_looks(key, wear)
        return self.owned_state(saved)

    # ---------- Paid extras ----------

    async def extras_view(self, ctx, data: dict) -> dict:
        """What a crate, a party round and a snowball cost where the player is, and the party rounds there are"""
        prices = await self.shop.prices(ctx.guild)
        return {
            "prices": {extra: prices.get(extra) for extra in EXTRAS},
            "twists": [{"id": kind, "name": info["name"], "line": info["line"]} for kind, info in TWISTS.items()],
            "currency": await self.shop.currency(ctx.guild) if ctx.guild is not None else "credits",
            "balance": await self.balance_of(ctx),
        }

    async def paid_extra(
        self, ctx, extra: str, refusal: t.Callable[[], str | None], deliver: t.Callable[[], bool]
    ) -> dict:
        """Take an extra's price, then deliver it. `refusal()` says why it can't happen right now, or None, and is
        asked before anything is taken. `deliver()` gives False when the moment passed while the credits were being
        taken, which returns them"""
        why = refusal()
        if why is not None:
            return {"error": why}
        try:
            async with self.lock(ctx.author.id):
                price = await self.shop.buy(ctx.author, extra)
        except ShopRefused as e:
            return {"error": str(e)}
        if not deliver():
            return {"error": await self.give_back(ctx.author, extra, price)}
        await self.shop.count(ctx.author, price)
        return {"balance": await self.balance_of(ctx)}

    async def drop_crate(self, ctx, data: dict) -> dict:
        """Pay to drop a crate on the ice of the round being played. Anyone in the window can, playing or watching"""
        match = self.matches.get(ctx.instance_id)
        if match is None:
            return {"error": "Crates drop during a round."}
        name = ctx.author.display_name
        return await self.paid_extra(ctx, "crate", match.crate_refusal, lambda: match.drop_crate(name))

    async def party_round(self, ctx, data: dict) -> dict:
        """Pay to make the next round to begin a party round of the chosen kind, for everyone in the window"""
        kind = data.get("kind")
        if type(kind) is not str or kind not in TWISTS:
            return {"error": "That party round doesn't exist."}
        match = self.matches.get(ctx.instance_id)
        if match is None:
            return {"error": "Open the game first."}
        name = ctx.author.display_name
        return await self.paid_extra(ctx, "twist", match.twist_refusal, lambda: match.queue_twist(kind, name))

    async def throw_snowball(self, ctx, data: dict) -> dict:
        """Pay to throw a snowball at a spot on the ice, as {"x": ..., "z": ...} in ice coordinates. Only for people
        in the window who hold no seat"""
        match = self.matches.get(ctx.instance_id)
        if match is None:
            return {"error": NO_SNOWBALLS}
        user_id, name = ctx.author.id, ctx.author.display_name
        x, z = data.get("x"), data.get("z")
        return await self.paid_extra(
            ctx,
            "snowball",
            lambda: match.snowball_refusal(user_id, x, z),
            lambda: match.throw_snowball(user_id, x, z, name),
        )

    async def economy_line(self, ctx) -> str | None:
        """The ActivityHub menu card's currency line while anything is sold for credits in the player's server"""
        if not await self.shop.prices(ctx.guild):
            return None
        return f"Penguin looks for {await self.shop.currency(ctx.guild)}"[:LINE_LIMIT]

    async def can_set_shop(self, ctx) -> bool:
        """
        Server admins set their server's prices. With a global bank one balance is shared by every server, so only
        the bot owner does, for every server at once. Nobody outside a server, where nothing is sold for credits
        """
        if ctx.guild is None:
            return False
        if await self.shop.bank.is_global():
            return await self.bot.is_owner(ctx.author)
        return await ctx.is_admin()

    async def shop_settings(self, ctx, data: dict) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.can_set_shop(ctx):
            return {"settings": None}
        prices = await self.shop.prices(ctx.guild)
        return {
            "settings": {item: prices.get(item) for item in SOLD},
            "defaults": {item: info["price"] for item, info in SOLD.items()},
            "names": {item: info["name"] for item, info in SOLD.items()},
            "global": await self.shop.bank.is_global(),
            "currency": await self.shop.currency(ctx.guild),
            "today": await self.shop.today_spent(ctx.guild),
        }

    async def save_shop(self, ctx, data: dict) -> dict:
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.can_set_shop(ctx):
            return {"error": NOT_THE_BANK_OWNER if await self.shop.bank.is_global() else NOT_AN_ADMIN}
        try:
            await self.shop.save(ctx.guild, data.get("settings"))
        except SettingsError as e:
            return {"error": str(e)}
        return await self.shop_settings(ctx, {})

    # ---------- Tuning ----------

    async def tuning_view(self, ctx, data: dict) -> dict:
        """The sliders' numbers, or {"tuning": None} for everyone but the bot owner"""
        if not await self.bot.is_owner(ctx.author):
            return {"tuning": None}
        return {"tuning": asdict(self.tuning), "sliders": SLIDERS, "defaults": asdict(Tuning())}

    async def save_tuning(self, ctx, data: dict) -> dict:
        """One set of numbers for every window at once. Saved first, so a failed save changes nothing"""
        if not await self.bot.is_owner(ctx.author):
            return {"error": NOT_THE_OWNER}
        try:
            tuning = clean_tuning(data.get("tuning"))
        except TuningError as e:
            return {"error": str(e)}
        async with self.tuning_lock:
            await self.config.tuning.set(asdict(tuning))
            self.tuning = tuning
            for match in self.matches.values():
                match.set_tuning(tuning)
        return await self.tuning_view(ctx, {})
