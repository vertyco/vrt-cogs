import logging

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.views import SetApiView

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.taskr.commands.owner")
_ = Translator("Taskr", __file__)


@cog_i18n(_)
class Owner(MixinMeta):
    @commands.hybrid_group(name="taskrset")
    @commands.is_owner()
    async def taskrset(self, ctx: commands.Context):
        """Configure Taskr settings"""

    @taskrset.command(name="maxtasks")
    async def set_max_tasks(self, ctx: commands.Context, max_tasks: commands.positive_int):
        """Set the maximum number of tasks allowed per guild"""
        if max_tasks < 1:
            return await ctx.send(_("The maximum number of tasks must be at least 1."))
        self.db.max_tasks = max_tasks
        self.save()
        await ctx.send(_("The maximum number of tasks has been set to {}.").format(max_tasks))

    @taskrset.command(name="mininterval")
    async def set_minimum_interval(self, ctx: commands.Context, interval: commands.positive_int):
        """
        Set the minimum interval between tasks in seconds, default is 60 seconds.

        Be careful with this setting, setting it too low can cause performance issues.
        """
        if interval < 1:
            return await ctx.send(_("The minimum interval must be at least 1 second."))
        self.db.minimum_interval = interval
        self.save()
        await ctx.send(_("The minimum interval has been set to {} seconds.").format(interval))

    @taskrset.command(name="openai")
    async def set_ai(self, ctx: commands.Context):
        """Set an openai key for the AI helper"""
        tokens = await self.bot.get_shared_api_tokens("openai")
        message = _(
            "1. Go to [OpenAI](https://platform.openai.com/signup) and sign up for an account.\n"
            "2. Go to the [API keys](https://platform.openai.com/account/api-keys) page.\n"
            "3. Click the `+ Create new secret key` button to create a new API key.\n"
            "4. Copy the API key click the button below to set it."
        )
        await ctx.send(
            message,
            view=SetApiView(
                default_service="openai",
                default_keys={"api_key": tokens.get("api_key", "")},
            ),
        )

    @taskrset.group(name="premium")
    async def premium_group(self, ctx: commands.Context):
        """Premium settings"""

    @premium_group.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_premium(self, ctx: commands.Context):
        """View premium settings"""
        status = _("**Enabled**") if self.db.premium_enabled else _("**Disabled**")
        description = _("Premium settings are currently {}.").format(status)
        embed = discord.Embed(
            title=_("Premium settings"),
            description=description,
            color=await self.bot.get_embed_color(ctx.channel),
        )
        if self.db.main_guild and (main_guild := self.bot.get_guild(self.db.main_guild)):
            mainserver = f"{main_guild.name} ({main_guild.id})"
        elif self.db.main_guild and not self.bot.get_guild(self.db.main_guild):
            mainserver = _("Unknown server ID: {}").format(self.db.main_guild)
        else:
            mainserver = _("Not set")
        embed.add_field(
            name=_("Main Server"),
            value=mainserver,
            inline=False,
        )
        if self.db.premium_role and (role := main_guild.get_role(self.db.premium_role)):
            premiumrole = f"{role.mention} ({role.id})"
        elif self.db.premium_role and not main_guild.get_role(self.db.premium_role):
            premiumrole = _("Unknown role ID: {}").format(self.db.premium_role)
        else:
            premiumrole = _("Not set")
        embed.add_field(
            name=_("Premium Role"),
            value=premiumrole,
            inline=False,
        )
        embed.add_field(
            name=_("Maximum Free Tasks"),
            value=_("The max amount of tasks allowed per server for non-premium users is {}").format(
                f"**{self.db.free_tasks}**"
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Maximum Premium Tasks"),
            value=_(
                "The max amount of tasks allowed per server is {}\n"
                "If the premium system is disabled, then this is the limit applied to all servers."
            ).format(f"**{self.db.max_tasks}**"),
            inline=False,
        )
        embed.add_field(
            name=_("Minimum Interval"),
            value=_("The minimum interval between tasks is {} seconds").format(f"**{self.db.minimum_interval}**"),
            inline=False,
        )
        embed.add_field(
            name=_("Premium Interval"),
            value=_(
                "The minimum interval between tasks for premium users is {} seconds\n"
                "If the premium system is disabled, then this is the interval applied to all servers."
            ).format(f"**{self.db.premium_interval}**"),
            inline=False,
        )
        await ctx.send(embed=embed)

    @premium_group.command(name="toggle")
    async def toggle_premium(self, ctx: commands.Context):
        """Toggle premium system"""
        self.db.premium_enabled = not self.db.premium_enabled
        self.save()
        status = _("enabled") if self.db.premium_enabled else _("disabled")
        await ctx.send(_("Premium has been {}.").format(status))

    @premium_group.command(name="mainserver")
    async def set_main_server(self, ctx: commands.Context, server_id: int):
        """Set the main server for premium features"""
        if main_guild := self.bot.get_guild(server_id):
            self.db.main_guild = server_id
            self.save()
            await ctx.send(_("The main server has been set to {}.").format(main_guild.name))
        else:
            await ctx.send(_("I couldn't find that server."))

    @premium_group.command(name="role")
    async def set_premium_role(self, ctx: commands.Context, *, role: discord.Role):
        """Set the premium role for premium features"""
        self.db.premium_role = role.id
        self.save()
        await ctx.send(_("The premium role has been set to {}.").format(role.mention))

    @premium_group.command(name="mininterval")
    async def set_premium_interval(self, ctx: commands.Context, interval: commands.positive_int):
        """Set the minimum interval between tasks for premium users"""
        if interval < 1:
            return await ctx.send(_("The minimum interval must be at least 1 second."))
        self.db.premium_interval = interval
        self.save()
        await ctx.send(_("The minimum interval for premium users has been set to {} seconds.").format(interval))
