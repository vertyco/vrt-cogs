import asyncio
import logging

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .bundled.games import bundled_games
from .bundled.scores import ScoreBoard
from .commands import Commands
from .common.discord_api import drop_entry_point_hook, keep_entry_point
from .common.games import GameRegistry
from .common.server import HubServer
from .common.sessions import LaunchMemory, SessionStore
from .views.launch import OpenView

log = logging.getLogger("red.vrt.activityhub")


class ActivityHub(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """
    One Discord Activity, a menu of games.

    Game cogs plug into the menu by themselves. The hub runs the web server, the Discord login and launching.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.4b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=117, force_registration=True)
        self.config.register_global(host="127.0.0.1", port=8742, look={}, disabled=[])
        self.config.register_guild(look={}, disabled=[])
        self.config.register_user(look={}, order=[])
        self.config.register_member(best={})
        self.registry = GameRegistry()
        self.sessions = SessionStore()
        self.launches = LaunchMemory()
        self.scores = ScoreBoard(self.config)
        self.server = HubServer(self)
        # The game cogs cog_load found already loaded, each describing itself in its own task
        self.scans: list[asyncio.Task] = []

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
        self.sessions.forget_user(user_id)
        self.launches.forget_user(user_id)

    async def cog_load(self) -> None:
        self.entry_point_hook = keep_entry_point(self.bot)
        self.open_view = OpenView(self)
        self.bot.add_view(self.open_view)
        await self.start_server()
        try:
            for game in bundled_games(self.scores):
                await self.registry.add(game)
            # Last, so a cog added during the server start isn't missed. This cog isn't in bot.cogs yet while it
            # loads, so this sees every other cog that is already loaded. Each game cog describes itself in its own
            # task. Its activityhub_game() may wait on something (even the bot being ready, which happens only after
            # every cog has loaded), and that must never hold up loading this cog or the other games
            self.scans = [
                asyncio.create_task(self.add_game(cog))
                for cog in list(self.bot.cogs.values())
                if hasattr(cog, "activityhub_game")
            ]
        except BaseException:
            # discord.py never calls cog_unload when cog_load fails or is cancelled (at startup Red cancels a load
            # that takes over 30 seconds), so without this the port would stay taken until the bot restarts, and
            # slash syncs would keep going through this copy's hook
            drop_entry_point_hook(self.bot, self.entry_point_hook)
            self.open_view.stop()
            await self.server.stop()
            raise

    async def cog_unload(self) -> None:
        for task in self.scans:
            task.cancel()
        drop_entry_point_hook(self.bot, self.entry_point_hook)
        self.open_view.stop()
        await self.server.stop()

    async def start_server(self) -> None:
        await self.server.stop()
        host, port = await self.config.host(), await self.config.port()
        try:
            await self.server.start(host, port)
        except Exception as e:
            # A saved address that can't be used must never stop the cog from loading, since the command that
            # fixes the address lives in this cog
            log.error("ActivityHub web server could not listen on %s:%s", host, port, exc_info=e)

    async def add_game(self, cog: commands.Cog) -> None:
        # The cog may unload, or be replaced by a reloaded copy, while its activityhub_game() runs
        await self.registry.add(cog, still_loaded=lambda: self.bot.get_cog(cog.qualified_name) is cog)
        if self.bot.get_cog(cog.qualified_name) is not cog:
            # Also drops a refusal recorded for a copy that is gone
            self.registry.remove(cog)

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        await self.add_game(cog)
        await self.server.rooms.close_stale(self.registry.games)

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog):
        freed = [game.key for game in self.registry.games.values() if game.cog is cog]
        self.registry.remove(cog)
        # First, so this game's players aren't kept waiting on another cog's activityhub_game() below
        await self.server.rooms.close_stale(self.registry.games)
        # A loaded cog refused because this one held its key gets the key now, without needing a reload
        for name, key in list(self.registry.clashes.items()):
            refused = self.registry.failed.get(name)
            if key in freed and refused is not None and self.bot.get_cog(name) is refused[0]:
                await self.add_game(refused[0])
