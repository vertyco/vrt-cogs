import asyncio
import logging

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

from .abc import CompositeMetaClass
from .common.listen import Listen
from .common.models import DB

log = logging.getLogger("red.vrt.nonuke")


class NoNuke(Listen, commands.Cog, metaclass=CompositeMetaClass):
    """
    Anti-Nuke System for lazy server owners!

    Monitors the following events:
    Kicks/Bans/Unbans/Prunes
    Channel Creation/Edit/Deletion
    Role Creation/Edit/Deletion
    Emoji Creation/Edit/Deletion
    Sticker Creation/Edit/Deletion
    Webhook Creation/Edit/Deletion
    Member role/nickname updates

    Set a cooldown(in seconds)
    Set an overload count(X events in X seconds)
    Set an action(kick, ban, strip, notify)

    If a user or bot exceeds X mod events within X seconds, the set action will be performed.

    - Any dangerous permissions added to a role will be logged.
    - If the vanity URL is changed, it will be logged.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.2.1"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving = False

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def save(self) -> None:
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

    async def initialize(self):
        await self.bot.wait_until_red_ready()
        data = await self.config.db()

        # Pre v1.0.0 migration
        save = False
        if not data:
            log.warning("PERFORMING MIGRATION")
            conf = await self.config.all_guilds()

            configs = {}
            for gid, settings in conf.items():
                if not settings:
                    continue
                configs[gid] = settings

            await self.config.clear_all_guilds()
            data["configs"] = configs
            save = True

        # Validate model
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        if save:
            await self.save()

    @commands.group()
    @commands.guildowner()
    @commands.guild_only()
    async def nonuke(self, ctx: commands.Context):
        """
        Anti-Nuke System for lazy guild owners!

        Monitors the following events:
        Kicks & Bans
        Channel Creation/Edit/Deletion
        Role Creation/Edit/Deletion

        Set a cooldown(in seconds)
        Set an overload count(X events in X seconds)
        Set an action(kick, ban, strip, notify)

        If a user or bot exceeds X mod events within X seconds, the set action will be performed
        """

    @nonuke.command()
    async def enable(self, ctx: commands.Context):
        """Enable/Disable the NoNuke system"""
        conf = self.db.get_conf(ctx.guild)
        if conf.enabled:
            conf.enabled = False
            await ctx.send("NoNuke system **Disabled**")
        else:
            conf.enabled = True
            await ctx.send("NoNuke system **Enabled**")
        await self.save()

    @nonuke.command()
    async def ignorebots(self, ctx: commands.Context):
        """
        Toggle whether other bots are ignored

        **NOTE:** Bot specific roles (the role created when the bot joins) cannot be removed.
        If NoNuke is set to strip roles, and a bot triggers it while having an integrated role, NoNuke will fail
        to remove the role from it.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.ignore_bots:
            conf.ignore_bots = False
            await ctx.send("Other bots will **not** be ignored")
        else:
            conf.ignore_bots = True
            await ctx.send("Other bots will be ignored")
        await self.save()

    @nonuke.command()
    async def dm(self, ctx: commands.Context):
        """Toggle whether the bot sends the user a DM when a kick or ban action is performed"""
        conf = self.db.get_conf(ctx.guild)
        if conf.dm:
            conf.dm = False
            await ctx.send("NoNuke trigger DM **Disabled**")
        else:
            conf.dm = True
            await ctx.send("NoNuke trigger DM **Enabled**")
        await self.save()

    @nonuke.command()
    async def logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the log channel for Anti-Nuke kicks"""
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send("I dont have permission to send embeds in that channel!")
        self.db.get_conf(ctx.guild).log = channel.id
        await ctx.tick()
        await self.save()

    @nonuke.command()
    async def cooldown(self, ctx: commands.Context, cooldown: int):
        """Cooldown (in seconds) for NoNuke to trigger"""
        self.db.get_conf(ctx.guild).cooldown = cooldown
        await ctx.tick()
        await self.save()

    @nonuke.command()
    async def overload(self, ctx: commands.Context, overload: int):
        """How many mod actions can be done within the set cooldown

        **Mod actions include:**
        Kicks & Bans
        Channel Creation/Edit/Deletion
        Role Creation/Edit/Deletion
        """
        if not ctx.guild.me.guild_permissions.view_audit_log:
            return await ctx.send("I do not have permission to view the audit log for this server!")
        conf = self.db.get_conf(ctx.guild)
        action = conf.action
        if action == "kick":
            if not ctx.guild.me.guild_permissions.kick_members:
                return await ctx.send("I do not have permission to kick members!")
        elif action == "ban":
            if not ctx.guild.me.guild_permissions.ban_members:
                return await ctx.send("I do not have permission to ban members!")
        elif action == "strip":
            if not ctx.guild.me.guild_permissions.manage_roles:
                return await ctx.send("I do not have permission to manage roles!")
        conf.overload = overload
        await ctx.tick()
        await self.save()

    @nonuke.command()
    async def action(self, ctx: commands.Context, action: str):
        """
        Set the action for the bot to take when NoNuke is triggered

        **Actions**
        `kick` - kick the user
        `ban` - ban the user
        `strip` - strip all roles with permissions from user
        `notify` - just sends a report to the log channel
        """
        if not ctx.guild.me.guild_permissions.view_audit_log:
            return await ctx.send("I do not have permission to view the audit log for this server!")
        action = action.lower()
        if action not in ["kick", "ban", "notify", "strip"]:
            return await ctx.send("That is not a valid action type!")
        if action == "kick":
            if not ctx.guild.me.guild_permissions.kick_members:
                return await ctx.send("I do not have permission to kick members!")
        elif action == "ban":
            if not ctx.guild.me.guild_permissions.ban_members:
                return await ctx.send("I do not have permission to ban members!")
        elif action == "strip":
            if not ctx.guild.me.guild_permissions.manage_roles:
                return await ctx.send("I do not have permission to manage roles!")
        self.db.get_conf(ctx.guild).action = action
        await ctx.tick()
        await self.save()

    @nonuke.command()
    async def whitelist(self, ctx: commands.Context, user: discord.Member):
        """Add/Remove users from the whitelist"""
        conf = self.db.get_conf(ctx.guild)
        if user.id in conf.whitelist:
            conf.whitelist.remove(user.id)
            await ctx.send(f"{user} has been removed from the whitelist!")
        else:
            conf.whitelist.append(user.id)
            await ctx.send(f"{user} has been added to the whitelist!")
        await self.save()

    @nonuke.command()
    @commands.bot_has_permissions(embed_links=True)
    async def view(self, ctx: commands.Context):
        """View the NoNuke settings"""
        conf = self.db.get_conf(ctx.guild)

        lchan = self.bot.get_channel(conf.log) if conf.log else "Not Set"
        em = discord.Embed(
            title="NoNuke Settings",
            description=f"`Enabled:    `{conf.enabled}\n"
            f"`Cooldown:   `{conf.cooldown}\n"
            f"`Overload:   `{conf.overload}\n"
            f"`DM:         `{conf.dm}\n"
            f"`Action:     `{conf.action}\n"
            f"`IgnoreBots: `{conf.ignore_bots}\n"
            f"`LogChannel: `{lchan}",
        )

        whitelisted_users = [f"<@{uid}>" for uid in conf.whitelist]
        em.add_field(name="Whitelisted Users", value=humanize_list(whitelisted_users) or "None")
        await ctx.send(embed=em)
        perms = {
            "manage_roles": ctx.guild.me.guild_permissions.manage_roles,
            "ban_members": ctx.guild.me.guild_permissions.ban_members,
            "kick_members": ctx.guild.me.guild_permissions.kick_members,
            "view_audit_log": ctx.guild.me.guild_permissions.view_audit_log,
        }
        missing = [k for k, v in perms.items() if not v]
        if missing:
            await ctx.send(f"Just a heads up, I do not have the following permissions\n{box(humanize_list(missing))}")
