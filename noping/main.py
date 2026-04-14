import asyncio
import logging
import typing as t

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB
from .common.utils import get_noping_user_ids_at_now, sync_rules
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.vrt.noping")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class NoPing(Commands, Listeners, TaskLoops, commands.Cog, metaclass=CompositeMetaClass):
    """Let users opt out of being pinged using Discord's AutoMod system.

    Manages AutoMod keyword filter rules to block pings to opted-out users,
    with optional per-user availability schedules.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: DB = DB()
        self.saving = False
        self.config = Config.get_conf(self, 1170901, force_registration=True)
        self.config.register_global(db={})
        self.guild_locks: dict[int, asyncio.Lock] = {}
        self._schedule_cache: dict[int, set[int]] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        for gid, conf in self.db.configs.items():
            if conf.remove_user(user_id):
                await self.sync_automod_rules(gid)
        self.save()

    async def red_get_data_for_user(self, *, user_id: int) -> dict:
        data = {}
        for gid, conf in self.db.configs.items():
            if user_id in conf.users:
                data[str(gid)] = conf.users[user_id].model_dump()
        return data

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.schedule_loop.cancel()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

        for guild_id in list(self.db.configs.keys()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.me.guild_permissions.manage_guild:
                try:
                    await self.sync_automod_rules(guild_id)
                except Exception:
                    log.exception("Failed to sync automod rules for guild %s on startup", guild_id)

        self.schedule_loop.start()
        log.info("NoPing initialized")

    def save(self) -> None:
        async def _save():
            if self.saving:
                return
            try:
                self.saving = True
                dump = await asyncio.to_thread(self.db.model_dump, mode="json")
                await self.config.db.set(dump)
            except Exception as e:
                log.exception("Failed to save config", exc_info=e)
            finally:
                self.saving = False

        asyncio.create_task(_save())

    def get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        """Get or create an asyncio.Lock for a guild."""
        if guild_id not in self.guild_locks:
            self.guild_locks[guild_id] = asyncio.Lock()
        return self.guild_locks[guild_id]

    async def sync_automod_rules(self, guild_id: int) -> None:
        """Synchronize automod rules for a guild based on current schedules.

        Uses a per-guild lock to prevent race conditions from concurrent syncs.
        """
        lock = self.get_guild_lock(guild_id)
        async with lock:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            conf = self.db.get_conf(guild)

            # Per-user timezone aware: each user's schedule checked against their own timezone
            active_ids = get_noping_user_ids_at_now(conf)

            # Filter to only members still in the guild
            active_ids = [uid for uid in active_ids if guild.get_member(uid)]

            # Get mod roles to exempt
            mod_roles = await self.bot.get_mod_roles(guild)
            admin_roles = await self.bot.get_admin_roles(guild)
            exempt_roles = list(set(mod_roles + admin_roles))

            rule_ids = await sync_rules(guild, conf, active_ids, exempt_roles)
            conf.rule_ids = rule_ids
            self.save()
