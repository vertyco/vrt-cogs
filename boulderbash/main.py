import asyncio
import logging
import random
import secrets
import time
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.game import OVER, Game, payable
from .common.payouts import DEFAULTS, Payouts, SettingsError
from .common.rules import MODES
from .common.scores import MEMBER_DEFAULTS, add_score, rank

log = logging.getLogger("red.vrt.boulderbash")

KEY = "boulderbash"
# A player away this long has their game, and any score they haven't cashed in, dropped
HOLD_MS = 10 * 60 * 1000
LOOP_SECONDS = 0.05
ELSEWHERE = "Boulder Bash was opened somewhere else."
STOPPED = "Something went wrong, so the game was stopped."
NOTHING_TO_CASH = "Nothing to cash in. Finish a game first."
CASH_FAILED = "Couldn't cash in your score. Try again."
NOT_AN_ADMIN = "Only server admins can change payouts."
TAKEN_OVER = 4100
# Commands that carry nothing but true
FLAGS = {"undo", "shuffle", "end", "next", "restart", "cashin"}

Key = tuple[int, int]


def player_key(ctx: t.Any) -> Key:
    """One game per player per server, and one for each player's DMs"""
    return ctx.guild_id or 0, ctx.author.id


def read_command(data: t.Any) -> tuple[str, t.Any] | None:
    """A page message as (name, value), or None for anything not shaped exactly right"""
    if not isinstance(data, dict) or len(data) != 1:
        return None
    name, value = next(iter(data.items()))
    if name == "start" and type(value) is int and value in MODES:
        return name, value
    if name == "tap" and isinstance(value, list) and len(value) == 3 and all(type(v) is int for v in value):
        return name, value
    if name in FLAGS and value is True:
        return name, value
    return None


class BoulderBash(commands.Cog):
    """
    Smash clumps of matching stone blocks, for ActivityHub.

    A remake of Neopets' Destruct-O-Match III with new art and sound. Each player plays their own game.
    """

    __author__ = "Vertyco"
    __version__ = "0.3.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101001, force_registration=True)
        self.config.register_global(payouts={}, tally={})
        self.config.register_guild(payouts={}, tally={})
        self.config.register_member(**MEMBER_DEFAULTS, cashed={})
        self.config.register_user(cashed={})
        self.payouts = Payouts(self.config)
        self.clock: t.Callable[[], float] = lambda: time.monotonic() * 1000
        self.games: dict[Key, Game] = {}
        # Each player's newest page. A newer one takes the game over
        self.conns: dict[Key, t.Any] = {}
        # The player behind each game, for saving a game that ends while they are away
        self.authors: dict[Key, t.Any] = {}
        # When each player's page closed, on the clock, while their game waits for them
        self.away: dict[Key, float] = {}
        # Finished scores that can still be cashed in. Starting another game gives one up
        self.results: dict[Key, int] = {}
        self.loop_task: asyncio.Task | None = None
        # Set on unload, so pages the hub closes afterwards don't start the loop again
        self.unloaded = False
        # Saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
        for guild_id in await self.config.all_guilds():
            await self.forget_paid(self.config.guild_from_id(guild_id).tally, user_id)
        await self.forget_paid(self.config.tally, user_id)
        for key in [key for key in self.games if key[1] == user_id]:
            self.drop(key)

    async def forget_paid(self, value: t.Any, user_id: int) -> None:
        tally = await value()
        if user_id in tally.get("players", []):
            tally["players"].remove(user_id)
            await value.set(tally)

    async def cog_unload(self):
        self.unloaded = True
        if self.loop_task is not None:
            self.loop_task.cancel()
            # Waited for, so the loop has really stopped once the cog is gone
            await asyncio.gather(self.loop_task, return_exceptions=True)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Boulder Bash",
            "description": "Smash clumps of matching stone blocks",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.svg",
            "thumbnail": "thumb.png",
            "economy": self.economy_line,
            "actions": {"scores": self.scores, "payouts": self.payout_settings, "save_payouts": self.save_payouts},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.8.0",
        }

    async def economy_line(self, ctx: t.Any) -> str | None:
        """The ActivityHub menu card's currency line while payouts are on in the player's server"""
        settings = await self.payouts.settings(ctx.guild)
        if not settings["on"]:
            return None
        return f"Cash in up to {settings['cap']:,} {await self.payouts.bank.get_currency_name(ctx.guild)}"

    # ---------- Connections ----------

    async def join(self, ctx, conn) -> None:
        key = player_key(ctx)
        old = self.conns.get(key)
        self.conns[key] = conn
        self.authors[key] = ctx.author
        self.away.pop(key, None)
        if old is not None and old is not conn:
            await old.send({"elsewhere": ELSEWHERE})
            await old.close(TAKEN_OVER)
        game = self.games.get(key)
        result = None
        if game is not None and game.state == OVER:
            result = await self.result_for(key, game)
        await conn.send({"hello": {"game": game.snapshot(self.clock()) if game else None, "result": result}})

    async def leave(self, ctx, conn) -> None:
        key = player_key(ctx)
        # A page that was taken over leaves after its replacement joined
        if self.conns.get(key) is not conn:
            return
        del self.conns[key]
        if key in self.games:
            self.away[key] = self.clock()
            self.start_loop()

    async def message(self, ctx, conn, data) -> None:
        key = player_key(ctx)
        command = read_command(data)
        if command is None or self.conns.get(key) is not conn:
            return
        try:
            await self.handle(key, conn, *command)
        except Exception as e:
            log.error("A Boulder Bash game failed for user %s", ctx.author.id, exc_info=e)
            self.drop(key)
            await conn.send({"stopped": STOPPED})

    async def handle(self, key: Key, conn: t.Any, name: str, value: t.Any) -> None:
        now = self.clock()
        game = self.games.get(key)
        if name == "start":
            if game is not None and game.state != OVER:
                return
            self.results.pop(key, None)
            game = Game(value, random.Random(secrets.randbits(64)), now)
            self.games[key] = game
            await conn.send({"game": game.snapshot(now)})
            self.start_loop()
            return
        if name == "cashin":
            await self.cash_in(key, conn)
            return
        if game is None:
            return
        if name == "restart":
            if game.state == OVER:
                self.games.pop(key, None)
                self.results.pop(key, None)
            return
        if name == "tap":
            messages = game.tap(*value, now)
        elif name == "undo":
            messages = game.use_undo(now)
        elif name == "shuffle":
            messages = game.use_shuffle(now)
        elif name == "end":
            messages = game.end(now)
        else:
            messages = game.next(now)
        await self.deliver(key, game, messages)

    async def deliver(self, key: Key, game: Game, messages: list[dict]) -> None:
        conn = self.conns.get(key)
        for message in messages:
            if conn is not None:
                await conn.send(message)
            if "over" in message:
                # Saved off the game loop, so Config never slows play
                task = asyncio.create_task(self.finish(key, game))
                self.saving.add(task)
                task.add_done_callback(self.saving.discard)

    def drop(self, key: Key) -> None:
        self.games.pop(key, None)
        self.results.pop(key, None)
        self.away.pop(key, None)

    # ---------- The game loop ----------

    def start_loop(self) -> None:
        if self.unloaded:
            return
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self.run())

    def needs_loop(self) -> bool:
        return bool(self.away) or any(game.state != OVER for game in self.games.values())

    async def run(self) -> None:
        """One loop for every game: rows rise, timers fire and levels end on the bot's clock, 20 times a second"""
        while self.needs_loop():
            await self.tick(self.clock())
            await asyncio.sleep(LOOP_SECONDS)

    async def tick(self, now: float) -> None:
        for key, game in list(self.games.items()):
            left = self.away.get(key)
            if left is not None and now - left >= HOLD_MS:
                self.drop(key)
                continue
            if game.state == OVER:
                continue
            try:
                messages = game.advance(now)
            except Exception as e:
                log.error("A Boulder Bash game's timers failed for user %s", key[1], exc_info=e)
                self.drop(key)
                conn = self.conns.get(key)
                if conn is not None:
                    await conn.send({"stopped": STOPPED})
                continue
            if messages:
                await self.deliver(key, game, messages)
        for key in [key for key in self.away if key not in self.games]:
            del self.away[key]

    # ---------- Game over, high scores and cashing in ----------

    async def finish(self, key: Key, game: Game) -> None:
        author = self.authors.get(key)
        result = await self.result_for(key, game, save=True)
        if author is not None and getattr(author, "guild", None) is not None and payable(game.mode, game.score):
            # Unless the player already started another game while this one was saving
            if self.games.get(key) is game:
                self.results[key] = game.score
                result["offer"] = await self.payouts.offer(author, game.score)
        conn = self.conns.get(key)
        if conn is not None:
            await conn.send({"result": result})

    async def result_for(self, key: Key, game: Game, save: bool = False) -> dict:
        """The game over screen: the score, the player's best and rank on this server, and what cashing in pays"""
        author = self.authors.get(key)
        result = {"score": game.score, "mode": game.mode, "best": None, "rank": None, "newBest": False, "offer": None}
        if author is None or getattr(author, "guild", None) is None:
            return {**result, "dm": True}
        group = self.config.member(author)
        if save and game.score > 0:
            try:
                entry, result["newBest"] = add_score(await group.all(), game.score, author.display_name)
                await group.set(entry)
            except Exception as e:
                log.error("Couldn't save a Boulder Bash score for user %s", author.id, exc_info=e)
        result.update(await self.standing(author))
        if key in self.results:
            result["offer"] = await self.payouts.offer(author, self.results[key])
        return result

    async def standing(self, author: t.Any) -> dict:
        table = rank(await self.config.all_members(author.guild), author.id)
        you = table["you"] or {"best": None, "rank": None}
        return {"best": you["best"], "rank": you["rank"]}

    async def cash_in(self, key: Key, conn: t.Any) -> None:
        score = self.results.get(key)
        author = self.authors.get(key)
        if score is None or author is None or getattr(author, "guild", None) is None:
            await conn.send({"notice": NOTHING_TO_CASH})
            return
        # Taken before the wait, so a second click (or a second device) can't pay the same game twice
        del self.results[key]
        result = None
        try:
            result = await self.payouts.cash_in(author, score)
        except Exception as e:
            log.error("Couldn't pay a Boulder Bash cash-in for user %s", author.id, exc_info=e)
        finally:
            # Kept for another try when nothing was paid, unless a newer game replaced it meanwhile
            if result is None or "error" in result:
                if self.games.get(key) is not None and self.games[key].state == OVER:
                    self.results.setdefault(key, score)
        if result is None:
            await conn.send({"notice": CASH_FAILED})
        elif "error" in result:
            await conn.send({"notice": result["error"]})
        else:
            await conn.send({"cashed": {**result, "score": score, **await self.standing(author)}})

    async def scores(self, ctx, data: dict) -> dict:
        """The server's high score table"""
        if ctx.guild is None:
            return {"top": [], "you": None, "dm": True}
        return rank(await self.config.all_members(ctx.guild), ctx.author.id)

    # ---------- Payout settings ----------

    async def can_set_payouts(self, ctx) -> bool:
        """
        Server admins set their server's payouts. With a global bank one balance is shared by every server, so
        only the bot owner does, for every server at once
        """
        if await self.payouts.bank.is_global():
            return await self.bot.is_owner(ctx.author)
        return await ctx.is_admin()

    async def payout_settings(self, ctx, data: dict) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.can_set_payouts(ctx):
            return {"settings": None}
        return {
            "settings": await self.payouts.settings(ctx.guild),
            "defaults": DEFAULTS,
            "global": await self.payouts.bank.is_global(),
            "currency": await self.payouts.bank.get_currency_name(ctx.guild),
            "today": await self.payouts.today_paid(ctx.guild),
        }

    async def save_payouts(self, ctx, data: dict) -> dict:
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.can_set_payouts(ctx):
            return {"error": NOT_AN_ADMIN}
        try:
            await self.payouts.save(ctx.guild, data.get("settings"))
        except SettingsError as e:
            return {"error": str(e)}
        return await self.payout_settings(ctx, {})
