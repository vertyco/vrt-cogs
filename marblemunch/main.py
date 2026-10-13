import asyncio
import logging
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.leaderboard import USER_DEFAULTS, Result, add_result, rank
from .common.match import Match
from .common.payouts import DEFAULTS, Payouts, SettingsError

log = logging.getLogger("red.vrt.marblemunch")

KEY = "marblemunch"
NOTHING_TO_CASH = "Nothing to cash in. Finish a round first."
NOT_AN_ADMIN = "Only server admins can change payouts."


class MarbleMunch(commands.Cog):
    """
    A hungry-hippos style marble game for ActivityHub.

    Up to four players stretch their hippos out to munch the most marbles. Computer hippos fill empty seats.
    """

    __author__ = "Vertyco"
    __version__ = "0.5.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026100901, force_registration=True)
        self.config.register_global(payouts={}, tally={})
        self.config.register_guild(payouts={}, tally={})
        self.config.register_user(**USER_DEFAULTS, cashed={})
        self.config.register_member(cashed={})
        self.payouts = Payouts(self.config)
        # One match per Activity window, keyed by the window's instance id
        self.matches: dict[str, Match] = {}
        # Leaderboard saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # Two windows can finish a round for the same player at once
        self.save_lock = asyncio.Lock()
        # Each player's last finished round that can still be cashed in: user id to (server id, marbles). The
        # next round they finish replaces it, like playing again on Neopets gives up an unsent score
        self.offers: dict[int, tuple[int, int]] = {}

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
        self.offers.pop(user_id, None)

    async def forget_paid(self, value: t.Any, user_id: int) -> None:
        tally = await value()
        if user_id in tally.get("players", []):
            tally["players"].remove(user_id)
            await value.set(tally)

    async def cog_unload(self):
        for match in list(self.matches.values()):
            match.stop()

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Marble Munch",
            "description": "Stretch, snap and munch the most marbles",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.svg",
            "thumbnail": "thumb.png",
            "economy": self.economy_line,
            "actions": {
                "leaderboard": self.leaderboard,
                "payouts": self.payout_settings,
                "save_payouts": self.save_payouts,
            },
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.8.0",
        }

    async def economy_line(self, ctx: t.Any) -> str | None:
        """The ActivityHub menu card's currency line while payouts are on in the player's server"""
        settings = await self.payouts.settings(ctx.guild)
        if not settings["on"]:
            return None
        return f"Cash in up to {settings['cap']:,} {await self.payouts.bank.get_currency_name(ctx.guild)}"

    def match_for(self, conn: t.Any) -> Match:
        """The window's match, started when its first player arrives, or again after a round failed"""
        match = self.matches.get(conn.ctx.instance_id)
        if match is None:
            match = Match(conn.room, self.record_round, self.match_ended)
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
        await self.match_for(conn).join(conn)
        # Back from a drop or on another device: the round they haven't cashed in yet is still theirs
        pending = self.offers.get(ctx.author.id)
        if pending is not None and pending[0] == ctx.guild_id:
            await self.send_offer(conn, pending[1])

    async def message(self, ctx, conn, data) -> None:
        if data == {"cashin": True}:
            await self.cash_in(ctx, conn)
            return
        await self.match_for(conn).message(conn, data)

    async def leave(self, ctx, conn) -> None:
        # No await before this: the match must see the drop before its loop can decide the window is empty
        match = self.matches.get(ctx.instance_id)
        if match is not None:
            match.leave(conn)

    def record_round(self, match: Match, results: list[Result]) -> None:
        # Saved off the update loop, after the round, so Config never slows play
        task = asyncio.create_task(self.after_round(match, results))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def after_round(self, match: Match, results: list[Result]) -> None:
        await self.save_results(results)
        for result in results:
            seat = match.seat_of(result.user_id)
            conn = seat.conn if seat is not None else None
            # Someone who dropped before the round ended had their hippo taken over, so it isn't theirs to cash in
            if conn is None or conn.ctx.guild is None:
                self.offers.pop(result.user_id, None)
                continue
            self.offers[result.user_id] = (conn.ctx.guild_id, result.marbles)
            try:
                await self.send_offer(conn, result.marbles)
            except Exception as e:
                log.error("Couldn't send a Marble Munch payout offer to user %s", result.user_id, exc_info=e)

    async def send_offer(self, conn, marbles: int) -> None:
        """Tell the player what their last round is worth, or that this server doesn't pay (offer None)"""
        await conn.send({"offer": await self.payouts.offer(conn.ctx.author, marbles)})

    async def cash_in(self, ctx, conn) -> None:
        pending = self.offers.get(ctx.author.id)
        if pending is None or pending[0] != ctx.guild_id:
            await conn.send({"notice": NOTHING_TO_CASH})
            return
        # Taken before the wait, so a second click (or a second device) can't pay the same round twice
        del self.offers[ctx.author.id]
        result = None
        try:
            result = await self.payouts.cash_in(ctx.author, pending[1])
        finally:
            # Kept for another try when nothing was paid, unless a newer round replaced it meanwhile
            if result is None or "error" in result:
                self.offers.setdefault(ctx.author.id, pending)
        if "error" in result:
            await conn.send({"notice": result["error"]})
        else:
            await conn.send({"cashed": result})

    async def save_results(self, results: list[Result]) -> None:
        async with self.save_lock:
            for result in results:
                try:
                    group = self.config.user_from_id(result.user_id)
                    entry = await group.all()
                    # Merged, so the player's cash-ins today (kept on the same user) survive the save
                    await group.set({**entry, **add_result(entry, result)})
                except Exception as e:
                    log.error("Couldn't save a Marble Munch result for user %s", result.user_id, exc_info=e)

    async def leaderboard(self, ctx, data: dict) -> dict:
        return rank(await self.config.all_users(), ctx.author.id)

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
