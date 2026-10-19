import asyncio
import logging
import secrets
import time
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common import progress, watch
from .common.levels import LEVEL_COUNT, load_level
from .common.session import SETTLE_TICKS, Session, load_board
from .common.shop import SettingsError, Shop, ShopRefused, cut_line
from .common.sim.level import expand

log = logging.getLogger("red.vrt.blockblaster")

KEY = "blockblaster"
# A level left behind by a dropped connection keeps its place this long, then counts as abandoned (nothing is lost)
HOLD_MS = 10 * 60 * 1000
# The bot's copy catches up in slices this long, letting other work run between them
SLICE_TICKS = 600
ELSEWHERE = "Block Blaster was opened somewhere else."
STOPPED = "Something went wrong, so the level was stopped."
TAKEN_OVER = 4100
NOT_AN_ADMIN = "Only server admins can change the shop."
BAD_PAYMENT = "You can't pay that way."
# Booster taps, which need stock the bot checks
BOOSTER_TAPS = set(progress.PRICES)
# Taps the page may never send: the revive is the bot's own tap. The Super Unicorn's tap needs no stock: the level's
# copy refuses it unless the player has the Unicorn this level and its bar is full
BOT_ONLY_TAPS = {"revive"}
# {"at": tick} once a second while the page's clock runs; {"ended": tick} once when the page's level ends
TICK_COMMANDS = {"at", "ended"}
# {"start": n} opens a level, resuming the one held; {"restart": n} throws the held one away and opens it afresh
START_COMMANDS = {"start", "restart"}
# {"watch": "<user id>"} starts watching a friend's level; {"unwatch": true} stops
WATCH_COMMANDS = {"watch", "unwatch"}


def is_tick(value: t.Any) -> bool:
    return type(value) is int and 0 <= value < 2**31


def read_tap(data: dict) -> tuple[str, t.Any] | None:
    """{"tap": [what, which...], "t": tick} as ("tap", (tap, tick)), or None"""
    if set(data) != {"tap", "t"} or not is_tick(data["t"]):
        return None
    tap = data["tap"]
    if not isinstance(tap, list) or not 1 <= len(tap) <= 3 or type(tap[0]) is not str:
        return None
    if not all(type(v) is int and abs(v) < 2**31 for v in tap[1:]):
        return None
    return "tap", (tap, data["t"])


def read_command(data: t.Any) -> tuple[str, t.Any] | None:
    """A page message as (name, value), or None for anything not shaped exactly right"""
    if not isinstance(data, dict):
        return None
    if "tap" in data:
        return read_tap(data)
    if len(data) != 1:
        return None
    name, value = next(iter(data.items()))
    if name in START_COMMANDS and type(value) is int and 1 <= value <= LEVEL_COUNT:
        return name, value
    if name in TICK_COMMANDS and is_tick(value):
        return name, value
    if name in WATCH_COMMANDS:
        return watch.read_watch(name, value)
    return None


class BlockBlaster(commands.Cog):
    """
    Clear pixel pictures with a belt of hungry shooting kitties, for ActivityHub.

    A remake of the phone puzzle Pixel Flow! with all 2,600 levels. Each player's progress is kept across every server.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101701, force_registration=True)
        self.config.register_user(**progress.defaults())
        self.config.register_global(prices={}, tally={})
        self.config.register_guild(prices={}, tally={})
        self.clock: t.Callable[[], float] = lambda: time.monotonic() * 1000
        # One level per player across every server, keyed by user id
        self.sessions: dict[int, Session] = {}
        # Each player's newest page. A newer one takes the game over
        self.conns: dict[int, t.Any] = {}
        # When each player's page closed, on the clock, while their level waits for them
        self.away: dict[int, float] = {}
        # Saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # One lock per player for everything that changes their saved progress, so two changes never overwrite
        # each other
        self.locks: dict[int, asyncio.Lock] = {}
        # Who watches whose level
        self.watchers = watch.Watchers()
        self.shop = Shop(self.config)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()
        self.drop(user_id)

    async def cog_unload(self):
        # Waited for, so a win being saved isn't lost with the cog
        await asyncio.gather(*self.saving, return_exceptions=True)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Block Blaster",
            "description": "Clear pixel pictures with a belt of hungry shooting kitties",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "economy": self.economy_line,
            "actions": {
                "profile": self.profile,
                "claim": self.claim,
                "buy": self.buy,
                "credits": self.credits,
                "revive": self.revive,
                "shown": self.shown,
                "shop_settings": self.shop_settings,
                "save_shop": self.save_shop,
            },
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.8.0",
        }

    # ---------- Actions ----------

    async def profile(self, ctx: t.Any, data: dict) -> dict:
        """The player's progress for the page, from Config (one record per player, shared by every server)"""
        saved = await self.config.user(ctx.author).all()
        return progress.profile(saved, ctx.author.id)

    def lock(self, key: int) -> asyncio.Lock:
        return self.locks.setdefault(key, asyncio.Lock())

    async def change(self, key: int, change: t.Callable[[progress.Progress], progress.Progress]) -> progress.Progress:
        """Apply `change` (one of progress's functions, which raises Refused) to a player's saved progress and save
        it, one change at a time per player. Returns the new progress"""
        async with self.lock(key):
            group = self.config.user_from_id(key)
            saved = change(await group.all())
            await group.set(saved)
        return saved

    async def claim(self, ctx: t.Any, data: dict) -> dict:
        """The free booster in an unlock popup"""
        try:
            booster = progress.check_booster(data.get("booster"))
            saved = await self.change(ctx.author.id, lambda p: progress.claim(p, booster))
        except progress.Refused as e:
            return {"error": str(e)}
        return {"progress": progress.profile(saved, ctx.author.id)}

    async def buy(self, ctx: t.Any, data: dict) -> dict:
        """A pack of 3 of a booster, paid with coins or, where the server sells it, with credits"""
        try:
            booster = progress.check_booster(data.get("booster"))
            pay = data.get("pay")
            if pay == "coins":
                saved = await self.change(ctx.author.id, lambda p: progress.buy(p, booster))
            elif pay == "credits":
                saved = await self.buy_with_credits(ctx, booster)
            else:
                raise progress.Refused(BAD_PAYMENT)
        except (progress.Refused, ShopRefused) as e:
            return {"error": str(e)}
        return {"progress": progress.profile(saved, ctx.author.id)}

    async def buy_with_credits(self, ctx: t.Any, booster: str) -> progress.Progress:
        """Take the credit price and add the pack. The credits are given back when the pack can't be saved"""
        key = ctx.author.id
        async with self.lock(key):
            group = self.config.user_from_id(key)
            after = progress.add_pack(await group.all(), booster)
            price = await self.shop.buy(ctx.author, booster)
            try:
                await group.set(after)
            except Exception as e:
                log.error("Couldn't save a Block Blaster credit purchase for user %s", key, exc_info=e)
                await self.shop.refund(ctx.author, price)
                raise ShopRefused("That didn't go through, and nothing was taken.") from e
        return after

    async def credits(self, ctx: t.Any, data: dict) -> dict:
        """The credit price of each booster the player's server sells for credits, and the currency's name"""
        return {
            "prices": await self.shop.prices(ctx.guild),
            "currency": await self.shop.currency(ctx.guild) if ctx.guild is not None else "credits",
        }

    async def economy_line(self, ctx: t.Any) -> str | None:
        """The ActivityHub menu card's currency line while any booster has a credit price in the player's server"""
        if not await self.shop.prices(ctx.guild):
            return None
        return cut_line(f"Buy boosters with {await self.shop.currency(ctx.guild)}")

    async def shown(self, ctx: t.Any, data: dict) -> dict:
        """Remember that the player saw a popup or tutorial"""
        try:
            saved = await self.change(ctx.author.id, lambda p: progress.see(p, data.get("id")))
        except progress.Refused as e:
            return {"error": str(e)}
        return {"progress": progress.profile(saved, ctx.author.id)}

    async def revive(self, ctx: t.Any, data: dict) -> dict:
        """Take a failed level back for 900 coins: the bot's copy applies the revive tap at the tick it stopped, and
        the page applies the same tap at that tick. Nothing is charged unless the revive takes"""
        key = ctx.author.id
        session = self.sessions.get(key)
        result = session.finish() if session is not None else None
        if session is None or result is None or result["result"] != "failed":
            return {"error": "There is nothing to revive."}
        try:
            async with self.lock(key):
                group = self.config.user_from_id(key)
                saved = progress.revive(await group.all())
                tick = session.state.tick
                answer = session.accept(["revive"], tick)
                if "refused" in answer:
                    return {"error": "That level can't be revived."}
                await group.set(saved)
        except progress.Refused as e:
            return {"error": str(e)}
        # The level goes on, so its next end is reported afresh
        session.reported = False
        await self.relay(key, {watch.TAP: [tick, ["revive"]]})
        return {"tick": tick, "sum": answer["sum"], "progress": progress.profile(saved, key)}

    # ---------- Shop settings ----------

    async def can_set_shop(self, ctx: t.Any) -> bool:
        """
        Server admins set their server's prices. With a global bank one balance is shared by every server, so only
        the bot owner does, for every server at once. Nobody outside a server, where nothing is sold for credits
        """
        if ctx.guild is None:
            return False
        if await self.shop.bank.is_global():
            return await self.bot.is_owner(ctx.author)
        return await ctx.is_admin()

    async def shop_settings(self, ctx: t.Any, data: dict) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.can_set_shop(ctx):
            return {"settings": None}
        prices = await self.shop.prices(ctx.guild)
        return {
            "settings": {booster: prices.get(booster) for booster in progress.PRICES},
            "global": await self.shop.bank.is_global(),
            "currency": await self.shop.currency(ctx.guild),
            "today": await self.shop.today_spent(ctx.guild),
        }

    async def save_shop(self, ctx: t.Any, data: dict) -> dict:
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.can_set_shop(ctx):
            return {"error": NOT_AN_ADMIN}
        try:
            await self.shop.save(ctx.guild, data.get("settings"))
        except SettingsError as e:
            return {"error": str(e)}
        return await self.shop_settings(ctx, {})

    # ---------- Connections ----------

    async def join(self, ctx: t.Any, conn: t.Any) -> None:
        key = ctx.author.id
        # Before this player's own away time is cleared, so a level held too long is dropped, not resumed
        self.forget_old(self.clock())
        old = self.conns.get(key)
        self.conns[key] = conn
        self.away.pop(key, None)
        # A new page starts on its own game; it asks to watch again if it was watching
        self.watchers.remove(key)
        if old is not None and old is not conn:
            await old.send({"elsewhere": ELSEWHERE})
            await old.close(TAKEN_OVER)
        session = self.sessions.get(key)
        held = session.start() if session is not None and not session.reported else None
        saved = await self.config.user_from_id(key).all()
        await conn.send({"hello": {"progress": progress.profile(saved, key), "level": held}})

    async def leave(self, ctx: t.Any, conn: t.Any) -> None:
        key = ctx.author.id
        # A page that was taken over leaves after its replacement joined
        if self.conns.get(key) is not conn:
            return
        del self.conns[key]
        if key in self.sessions:
            self.away[key] = self.clock()
        self.watchers.remove(key)
        await self.friend_gone(key)

    async def message(self, ctx: t.Any, conn: t.Any, data: t.Any) -> None:
        key = ctx.author.id
        command = read_command(data)
        if command is None or self.conns.get(key) is not conn:
            return
        try:
            await self.handle(key, conn, *command)
        except Exception as e:
            log.error("A Block Blaster level failed for user %s", key, exc_info=e)
            self.drop(key)
            await conn.send({"stopped": STOPPED})
            await self.friend_gone(key)

    async def handle(self, key: int, conn: t.Any, name: str, value: t.Any) -> None:
        if name == "watch":
            await self.watch(key, conn, value)
            return
        if name == "unwatch":
            self.watchers.remove(key)
            return
        if name in START_COMMANDS:
            # Going back to their own game ends any watching
            self.watchers.remove(key)
            if name == "restart":
                await self.give_up(key, conn)
                self.drop(key)
            await self.start_level(key, conn, value)
            return
        session = self.sessions.get(key)
        if session is None:
            return
        if name == "tap":
            await self.tap(key, conn, session, *value)
        elif not session.reported:
            await self.page_at(key, conn, session, value, ended=name == "ended")

    def drop(self, key: int) -> None:
        self.sessions.pop(key, None)
        self.away.pop(key, None)

    def forget_old(self, now: float) -> None:
        """Drop every level whose player has been away longer than HOLD_MS"""
        for key, left in list(self.away.items()):
            if now - left >= HOLD_MS:
                self.drop(key)

    # ---------- Levels ----------

    async def start_level(self, key: int, conn: t.Any, n: int) -> None:
        """The player's current level, or any level once every level is cleared. A level still in play resumes"""
        now = self.clock()
        self.forget_old(now)
        saved = await self.config.user_from_id(key).all()
        if n != saved["level"] and not saved["cleared"]:
            return
        session = self.sessions.get(key)
        if session is None or session.reported or session.number != n:
            saved = await self.give_up(key, conn) or saved
            active = saved["unicorn"]["active"]
            session = Session(expand(load_level(n)), secrets.randbits(32), load_board(), now, active)
            self.sessions[key] = session
            await self.relay(key, {watch.LEVEL: session.start()})
        await conn.send({"level": session.start()})

    async def give_up(self, key: int, conn: t.Any) -> progress.Progress | None:
        """The player left their failed level without reviving it (Retry, or Play again after leaving the fail panel):
        the fail counts against the Super Unicorn. A level left unfinished, or one held past HOLD_MS, doesn't count.
        Returns the new progress, sent to the page too, or None when there was no such fail"""
        session = self.sessions.get(key)
        result = session.finish() if session is not None else None
        if session is None or not session.reported or result is None or result["result"] != "failed":
            return None
        saved = await self.change(key, progress.give_up)
        await conn.send({"progress": progress.profile(saved, key)})
        return saved

    async def catch_up(self, key: int, session: Session, tick: int) -> bool:
        """Move the bot's copy to `tick` in slices, so the event loop never waits long. False when the level was
        replaced or dropped meanwhile"""
        while session.state.tick < tick and session.finish() is None:
            session.advance_to(min(tick, session.state.tick + SLICE_TICKS))
            await asyncio.sleep(0)
            if self.sessions.get(key) is not session:
                return False
        return True

    async def tap(self, key: int, conn: t.Any, session: Session, tap: list, tick: int) -> None:
        """A tap stamped with the page's tick. Ticks never go backwards and never run ahead of the bot's clock"""
        if tap[0] in BOT_ONLY_TAPS:
            await conn.send(session.refuse("not available"))
            return
        if tick < session.state.tick or tick > session.clock_limit(self.clock()):
            await conn.send(session.refuse("clock"))
            return
        if not await self.catch_up(key, session, tick):
            return
        if session.finish() is not None:
            await conn.send(session.refuse("level over"))
            self.report(key, session)
            return
        if tap[0] in BOOSTER_TAPS:
            await self.booster_tap(key, conn, session, tap, tick)
            return
        answer = session.accept(tap, tick)
        await conn.send(answer)
        if "ok" in answer:
            await self.relay(key, {watch.TAP: [tick, tap]})

    async def booster_tap(self, key: int, conn: t.Any, session: Session, tap: list, tick: int) -> None:
        """A booster tap: allowed when the player has unlocked and claimed it and has stock or the free first use.
        The stock is only taken once the level's copy accepted the tap, and the page is sent its new stock"""
        booster = tap[0]
        async with self.lock(key):
            group = self.config.user_from_id(key)
            saved = await group.all()
            if not progress.can_use(saved, booster):
                await conn.send(session.refuse("no booster"))
                return
            answer = session.accept(tap, tick)
            if "ok" in answer:
                saved = progress.use(saved, booster)
                await group.set(saved)
        await conn.send(answer)
        if "ok" in answer:
            await conn.send({"progress": progress.profile(saved, key)})
            await self.relay(key, {watch.TAP: [tick, tap]})

    async def page_at(self, key: int, conn: t.Any, session: Session, tick: int, ended: bool) -> None:
        """The page's clock reached `tick` (`ended`: its level ended there). The bot follows, never past its own
        clock, and sends the result once its copy ends. When the page says it ended first, the bot runs on up to 10
        seconds to find the end itself; its verdict stands, so a level that is still going goes back to the page"""
        target = min(tick, session.clock_limit(self.clock()))
        if not await self.catch_up(key, session, target):
            return
        # No tap can come before the bot's copy's tick any more, so watchers may run up to it
        await self.relay(key, {watch.TICK: session.state.tick})
        if ended and session.finish() is None:
            session.settle(SETTLE_TICKS)
            await asyncio.sleep(0)
            if self.sessions.get(key) is not session:
                return
            if session.finish() is None:
                await conn.send({"level": session.start()})
                return
        if session.finish() is not None:
            self.report(key, session)

    def report(self, key: int, session: Session) -> None:
        """Pay and send the level's result once, saved off the message handler so Config never slows play"""
        result = session.finish()
        if session.reported or result is None:
            return
        session.reported = True
        task = asyncio.create_task(self.finish_level(key, session, result))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def finish_level(self, key: int, session: Session, result: dict) -> None:
        group = self.config.user_from_id(key)
        try:
            async with self.lock(key):
                saved = await group.all()
                coins = 0
                if result["result"] == "won":
                    saved = progress.win(saved, session.number)
                    await group.set(saved)
                    coins = progress.WIN_COINS
        except Exception as e:
            log.error("Couldn't save a Block Blaster level for user %s", key, exc_info=e)
            self.drop(key)
            conn = self.conns.get(key)
            if conn is not None:
                await conn.send({"stopped": STOPPED})
            await self.friend_gone(key)
            return
        # A won level is done; a failed one stays for a revive until the player starts again
        if result["result"] == "won" and self.sessions.get(key) is session:
            self.drop(key)
        conn = self.conns.get(key)
        if conn is not None:
            await conn.send({"over": {**result, "coins": coins, "progress": progress.profile(saved, key)}})
        await self.relay(key, {watch.OVER: result})

    # ---------- Watching ----------

    async def watch(self, key: int, conn: t.Any, friend: int) -> None:
        """Start watching a friend who has a level on the bot and plays in the same room. Their page gets the
        friend's LevelStart, and the result too when that level already ended"""
        friend_conn = self.conns.get(friend)
        session = self.sessions.get(friend)
        if friend == key or friend_conn is None or friend_conn not in conn.peers() or session is None:
            self.watchers.remove(key)
            await conn.send(watch.GONE)
            return
        self.watchers.add(key, friend)
        name = friend_conn.ctx.author.display_name
        await conn.send({"watching": {"user": str(friend), "name": name, "level": session.start()}})
        result = session.finish()
        if session.reported and result is not None:
            await conn.send({watch.OVER: result})

    async def relay(self, friend: int, message: dict) -> None:
        """Pass one of the friend's level messages to everyone watching them"""
        for watcher in self.watchers.of(friend):
            conn = self.conns.get(watcher)
            if conn is not None:
                await conn.send(message)

    async def friend_gone(self, friend: int) -> None:
        """The friend left or their level was stopped: everyone watching them goes back to their own game"""
        for watcher in self.watchers.drop_friend(friend):
            conn = self.conns.get(watcher)
            if conn is not None:
                await conn.send(watch.GONE)
