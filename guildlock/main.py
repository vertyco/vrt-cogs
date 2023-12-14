import asyncio
import logging
import typing as t

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .commands import BaseCommands
from .common import get_bot_percentage
from .common.abc import CompositeMetaClass
from .common.listener import Listener
from .common.models import DB

log = logging.getLogger("red.vrt.guildlock")
_ = Translator("GuildLock", __file__)
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


# redgettext -D main.py common/views.py commands/base.py --command-docstring


@cog_i18n(_)
class GuildLock(BaseCommands, Listener, commands.Cog, metaclass=CompositeMetaClass):
    """
    Tools for managing guild joins and leaves.
    """

    __author__ = "Vertyco#0117"
    __version__ = "0.1.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = DB.model_validate(data)
        log.info("Config loaded")

    async def save(self) -> None:
        dump = self.db.model_dump(mode="json")
        await self.config.db.set(dump)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = _("Version: {}\nAuthor: {}").format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """No data to delete"""

    def notify_reason(self, log_type: str, guild: discord.Guild) -> str:
        mapping = {
            "blacklist": _("I have left this server because it is blacklisted"),
            "whitelist": _("I have left this server because it is not whitelisted"),
            "limit": _("I have left this server because I am already at maximum capacity"),
            "minmembers": _("I have left this server because it has less than {} members").format(self.db.min_members),
            "botfarms": _("I have left this server because {}% of its members are bots").format(
                get_bot_percentage(guild)
            ),
        }
        return mapping[log_type]

    def log_reason(self, log_type: str, guild: discord.Guild) -> str:
        mapping = {
            "blacklist": _("Guild is in the blacklist"),
            "whitelist": _("Guild is not in the whitelist"),
            "limit": _("Cannot surpass guild limit of {}").format(f"**{self.db.limit}**"),
            "minmembers": _("Guild has less than {} members").format(f"**{self.db.min_members}**"),
            "botfarms": _("Guild exceeds bot threshold of {}% ({}%)").format(
                f"**{self.db.bot_ratio}**", get_bot_percentage(guild)
            ),
        }
        return mapping[log_type]

    async def notify_guild(self, log_type: str, guild: discord.Guild):
        message = await asyncio.to_thread(self.notify_reason(log_type, guild))
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            await guild.system_channel.send(message)
        else:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(message)
                    break

    async def log_leave(self, reason: str, guild: discord.Guild):
        if not self.db.log_channel:
            return
        log_guild = self.bot.get_guild(self.db.log_guild)
        if not log_guild:
            log.warning("Bot is no longer in main guild")
            return

        log_channel = log_guild.get_channel(self.db.log_channel)
        if not log_channel:
            return
        can_send = [
            log_channel.permissions_for(guild.me).send_messages,
            log_channel.permissions_for(guild.me).embed_links,
        ]
        if not all(can_send):
            log.warning(f"Missing permission to send log to {log_channel.name}\nMessage: {reason}")
            return

        embed = discord.Embed(description=_("Reason: {}").format(reason))
        embed.set_author(name=_("Left {}").format(guild.name), icon_url=guild.icon)

        footer = _("Owner: {}").format(f"{guild.owner.name} ({guild.owner_id})")
        embed.set_footer(text=footer, icon_url=guild.owner.display_icon)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            log.warning(f"Failed to send log to {log_channel.name}\nMessage: {reason}", exc_info=e)
