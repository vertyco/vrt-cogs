import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

from .listen import Listen


class NoNuke(Listen, commands.Cog):
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
    __author__ = "Vertyco"
    __version__ = "0.1.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)

        default_guild = {
            "enabled": False,
            "log": 0,  # Log channel
            "cooldown": 10,  # Seconds in between actions
            "overload": 3,  # Actions within cooldown time
            "dm": False,  # Whether to DM the user the bot kicks
            "action": "notify",  # Valid types are 'kick', 'ban', 'strip', and 'notify'
            "whitelist": [],  # Whitelist of trusted users(or bots)
        }
        self.config.register_guild(**default_guild)

        self.settings = {}
        self.cache = {}
        self.first_run = True

    async def initialize(self, guild_id: int = 0):
        await self.bot.wait_until_red_ready()
        conf = await self.config.all_guilds()
        for gid, settings in conf.items():
            if not settings:
                continue
            if guild_id and gid != guild_id:
                continue
            self.settings[gid] = settings

    @commands.group()
    @commands.guildowner()
    @commands.guild_only()
    async def nonuke(self, ctx):
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
    async def enable(self, ctx):
        """Enable/Disable the NoNuke system"""
        toggle = await self.config.guild(ctx.guild).enabled()
        if toggle:
            await self.config.guild(ctx.guild).enabled.set(False)
            await ctx.send("NoNuke system **Disabled**")
        else:
            await self.config.guild(ctx.guild).enabled.set(True)
            await ctx.send("NoNuke system **Enabled**")
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def dm(self, ctx):
        """Toggle whether the bot sends the user a DM when a kick or ban action is performed"""
        toggle = await self.config.guild(ctx.guild).dm()
        if toggle:
            await self.config.guild(ctx.guild).dm.set(False)
            await ctx.send("NoNuke trigger DM **Disabled**")
        else:
            await self.config.guild(ctx.guild).dm.set(True)
            await ctx.send("NoNuke trigger DM **Enabled**")
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def logchannel(self, ctx, channel: discord.TextChannel):
        """Set the log channel for Anti-Nuke kicks"""
        await self.config.guild(ctx.guild).log.set(channel.id)
        await ctx.tick()
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def cooldown(self, ctx, cooldown: int):
        """Cooldown (in seconds) for NoNuke to trigger"""
        await self.config.guild(ctx.guild).cooldown.set(cooldown)
        await ctx.tick()
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def overload(self, ctx, overload: int):
        """How many mod actions can be done within the set cooldown

        **Mod actions include:**
        Kicks & Bans
        Channel Creation/Edit/Deletion
        Role Creation/Edit/Deletion
        """
        if not ctx.guild.me.guild_permissions.view_audit_log:
            return await ctx.send("I do not have permission to view the audit log for this server!")
        action = await self.config.guild(ctx.guild).action()
        if action == "kick":
            if not ctx.guild.me.guild_permissions.kick_members:
                return await ctx.send("I do not have permission to kick members!")
        elif action == "ban":
            if not ctx.guild.me.guild_permissions.ban_members:
                return await ctx.send("I do not have permission to ban members!")
        elif action == "strip":
            if not ctx.guild.me.guild_permissions.manage_roles:
                return await ctx.send("I do not have permission to manage roles!")
        await self.config.guild(ctx.guild).overload.set(overload)
        await ctx.tick()
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def action(self, ctx, action: str):
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
        await self.config.guild(ctx.guild).action.set(action)
        await ctx.tick()
        await ctx.send(f"Action has been set to `{action}`")
        await self.initialize(ctx.guild)

    @nonuke.command()
    async def whitelist(self, ctx, user: discord.Member):
        """Add/Remove users from the whitelist"""
        async with self.config.guild(ctx.guild).whitelist() as whitelist:
            if user.id in whitelist:
                whitelist.remove(user.id)
                await ctx.send(f"{user} has been removed from the whitelist!")
            else:
                whitelist.append(user.id)
                await ctx.send(f"{user} has been added to the whitelist!")

    @nonuke.command()
    async def view(self, ctx):
        """View the NoNuke settings"""
        conf = await self.config.guild(ctx.guild).all()
        lchan = self.bot.get_channel(conf['log']) if conf['log'] else "Not Set"
        em = discord.Embed(
            title="NoNuke Settings",
            description=f"`Enabled:    `{conf['enabled']}\n"
                        f"`Cooldown:   `{conf['cooldown']}\n"
                        f"`Overload:   `{conf['overload']}\n"
                        f"`DM:         `{conf['dm']}\n"
                        f"`Action:     `{conf['action']}\n"
                        f"`LogChannel: `{lchan}"
        )
        await ctx.send(embed=em)
        perms = {
            ctx.guild.me.guild_permissions.manage_roles: "manage_roles",
            ctx.guild.me.guild_permissions.ban_members: "ban_members",
            ctx.guild.me.guild_permissions.kick_members: "kick_members",
            ctx.guild.me.guild_permissions.view_audit_log: "view_audit_log"
        }
        missing = [v for k, v in perms.items() if k]
        if missing:
            await ctx.send(f"Just a heads up, I do not have the following permissions\n{box(humanize_list(missing))}")
