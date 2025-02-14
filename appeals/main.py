import asyncio
import json
import logging
import typing as t
from io import BytesIO

import discord
from piccolo.engine.sqlite import SQLiteEngine
from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .db.tables import TABLES, AppealGuild, AppealQuestion, AppealSubmission
from .db.utils import DBUtils
from .engine import engine
from .listeners import Listeners
from .views.appeal import AppealView

log = logging.getLogger("red.vrt.appeals")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Appeals(Commands, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """Straightforward ban appeal system for Discord servers."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: SQLiteEngine = None
        self.db_utils: DBUtils = DBUtils()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int) -> dict[str, BytesIO]:
        submissions = (
            await AppealSubmission.select(AppealSubmission.all_columns())
            .where(AppealSubmission.user_id == user_id)
            .output(load_json=True)
        )
        data = {}
        for submission in submissions:
            data[str(submission.id)] = BytesIO(json.dumps(submission).encode())
        return data

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        # Nothing to delete, saved appeals are required for the appeal system to function
        pass

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        logging.getLogger("aiosqlite").setLevel(logging.INFO)
        try:
            self.db = await engine.register_cog(
                cog_instance=self,
                tables=TABLES,
                trace=True,
            )
        except Exception as e:
            log.error("Failed to initialize database", exc_info=e)
            res = await engine.diagnose_issues(self)
            log.error(res)
        appealguilds = await AppealGuild.objects()
        for appealguild in appealguilds:
            ready, __ = await self.conditions_met(appealguild)
            if not ready:
                continue
            view = AppealView(custom_id=f"{appealguild.id}")
            self.bot.add_view(view, message_id=appealguild.appeal_message)
        log.info("Cog initialized")

    async def conditions_met(self, guild: discord.Guild | AppealGuild) -> t.Tuple[bool, t.Optional[str]]:
        """Check if conditions are met for the current guild to use the appeal system."""
        if isinstance(guild, discord.Guild):
            appealguild = await AppealGuild.objects().get(AppealGuild.id == guild.id)

        else:
            appealguild = guild
            guild = self.bot.get_guild(guild.id)

        prefixes = await self.bot.get_valid_prefixes(guild)
        p = prefixes[0]

        if not appealguild:
            return (
                False,
                f"Appeal system is not setup for this guild, set with `{p}appeal server`",
            )
        if not appealguild.target_guild_id:
            return False, f"Target guild is not set, set with `{p}appeal server`"
        target_guild = self.bot.get_guild(appealguild.target_guild_id)
        if not target_guild:
            return (
                False,
                f"Target guild `{appealguild.target_guild_id}` was not found, set with `{p}appeal server`",
            )
        if not target_guild.me.guild_permissions.ban_members:
            return False, "Bot does not have ban members permission in target guild"
        if not appealguild.appeal_channel:
            return (
                False,
                f"Appeal message is not set, set with `{p}appeal createappealmessage`",
            )
        appeal_channel = guild.get_channel(appealguild.appeal_channel)
        if not appeal_channel:
            return (
                False,
                f"Appeal message channel is not found, please set a new one with `{p}appeal appealmessage",
            )
        if not appeal_channel.permissions_for(guild.me).view_channel:
            return (
                False,
                "Bot does not have view channel permission in appeal message channel",
            )
        if not appeal_channel.permissions_for(guild.me).send_messages:
            return (
                False,
                "Bot does not have send messages permission in appeal message channel",
            )
        if not appealguild.appeal_message:
            return (
                False,
                f"Appeal message is not set, you can quickly create one with `{p}appeal createappealmessage`",
            )
        try:
            await appeal_channel.fetch_message(appealguild.appeal_message)
        except discord.NotFound:
            return False, "Appeal message is not found"
        if not appealguild.pending_channel:
            return (
                False,
                f"Pending channel is not set, set with `{p}appeal channel pending <channel>`",
            )
        channel = guild.get_channel(appealguild.pending_channel)
        if not channel:
            return False, "Pending channel is not found"
        if not channel.permissions_for(guild.me).view_channel:
            return False, "Bot does not have view channel permission in pending channel"
        if not channel.permissions_for(guild.me).send_messages:
            return (
                False,
                "Bot does not have send messages permission in pending channel",
            )
        if not appealguild.approved_channel:
            return (
                False,
                f"Approved channel is not set, set with `{p}appeal channel approved <channel>`",
            )
        channel = guild.get_channel(appealguild.approved_channel)
        if not channel:
            return False, "Approved channel is not found"
        if not channel.permissions_for(guild.me).view_channel:
            return (
                False,
                "Bot does not have view channel permission in approved channel",
            )
        if not channel.permissions_for(guild.me).send_messages:
            return (
                False,
                "Bot does not have send messages permission in approved channel",
            )
        if not appealguild.denied_channel:
            return (
                False,
                f"Denied channel is not set, set with `{p}appeal channel denied <channel>`",
            )
        channel = guild.get_channel(appealguild.denied_channel)
        if not channel:
            return False, "Denied channel is not found"
        if not channel.permissions_for(guild.me).view_channel:
            return False, "Bot does not have view channel permission in denied channel"
        if not channel.permissions_for(guild.me).send_messages:
            return False, "Bot does not have send messages permission in denied channel"
        if not await AppealQuestion.exists().where(AppealQuestion.guild == guild.id):
            return (
                False,
                f"No questions are setup for this server, create one with `{p}appeal addquestion`",
            )
        return True, None
