import asyncio

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common import formatter, utils
from ..views.dynamic_menu import DynamicMenu

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Weekly(MixinMeta):
    @commands.command(name="weekly", aliases=["week"])
    @commands.guild_only()
    async def weekly(
        self,
        ctx: commands.Context,
        stat: str = "exp",
        # globalstats: bool = False,
        displayname: bool = True,
    ):
        """View Weekly Leaderboard"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.weeklysettings.on:
            txt = _("Weekly stats are not enabled on this server")
            return await ctx.send(txt)
        stat = stat.lower()
        pages = await asyncio.to_thread(
            formatter.get_leaderboard,
            bot=self.bot,
            guild=ctx.guild,
            db=self.db,
            stat=stat,
            lbtype="weekly",
            is_global=False,
            member=ctx.author,
            use_displayname=displayname,
            color=await self.bot.get_embed_color(ctx),
        )
        if isinstance(pages, str):
            return await ctx.send(pages)
        await DynamicMenu(ctx, pages).refresh()

    @commands.command(name="lastweekly")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def lastweekly(self, ctx: commands.Context):
        """View Last Week's Leaderboard"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.weeklysettings.on:
            return await ctx.send(_("Weekly stats are not enabled on this server"))
        if not conf.weeklysettings.last_embed:
            return await ctx.send(_("There is no recorded weekly embed saved"))
        embed = discord.Embed.from_dict(conf.weeklysettings.last_embed)
        embed.title = _("Last Weekly Leaderboard")
        new_desc = _("{}\n`Last Reset:      `{}").format(embed.description, f"<t:{conf.weeklysettings.last_reset}:R>")
        embed.description = new_desc
        await ctx.send(embed=embed)

    @commands.group(name="weeklyset", aliases=["wset"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def weeklyset(self, ctx: commands.Context):
        """Configure Weekly LevelUp Settings"""

    @weeklyset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def weeklyset_view(self, ctx: commands.Context):
        """View the current weekly settings"""
        conf = self.db.get_conf(ctx.guild)
        status = _("Enabled") if conf.weeklysettings.on else _("Disabled")
        desc = _("Weekly stat tracking is currently {}").format(status)
        embed = discord.Embed(
            title=_("LevelUp Weekly Settings"),
            description=desc,
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name=_("Settings"),
            value=_(
                "`Winner Count:   `{}\n"
                "`Channel:        `{}\n"
                "`Ping Winners:   `{}\n"
                "`Role:           `{}\n"
                "`RoleAllWinners: `{}\n"
                "`Auto Remove:    `{}\n"
                "`Bonus Exp:      `{}\n"
            ).format(
                conf.weeklysettings.count,
                f"<#{conf.weeklysettings.channel}>" if conf.weeklysettings.channel else _("None"),
                conf.weeklysettings.ping_winners,
                f"<@&{conf.weeklysettings.role}>" if conf.weeklysettings.role else _("None"),
                conf.weeklysettings.role_all,
                conf.weeklysettings.remove,
                conf.weeklysettings.bonus,
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Last Winners"),
            value="\n".join(f"{i + 1}. <@{uid}>" for i, uid in enumerate(conf.weeklysettings.last_winners))
            if conf.weeklysettings.last_winners
            else _("No winners yet"),
            inline=False,
        )
        status = _(" (Enabled)") if conf.weeklysettings.autoreset else _(" (Disabled)")
        embed.add_field(
            name=_("Auto Reset") + status,
            value=_(
                "- Stats reset on day {} ({})\n"
                "- Reset occurs at hour {}\n"
                "- Last reset occured on {}\n"
                "- Next reset will happen on {}\n"
            ).format(
                conf.weeklysettings.reset_day,
                utils.get_day_name(conf.weeklysettings.reset_day),
                conf.weeklysettings.reset_hour,
                f"<t:{conf.weeklysettings.last_reset}:F>",
                f"<t:{conf.weeklysettings.next_reset}:F>",
            ),
        )
        await ctx.send(embed=embed)

    @weeklyset.command(name="ping")
    async def weeklyset_ping(self, ctx: commands.Context):
        """Toggle whether to ping winners in announcement"""
        conf = self.db.get_conf(ctx.guild)
        if conf.weeklysettings.ping_winners:
            conf.weeklysettings.ping_winners = False
            await ctx.send(_("Winners will no longer be pinged in announcements"))
        else:
            conf.weeklysettings.ping_winners = True
            await ctx.send(_("Winners will now be pinged in announcements"))
        self.save()

    @weeklyset.command(name="autoremove")
    async def weeklyset_autoremove(self, ctx: commands.Context):
        """Remove role from previous winner when new one is announced"""
        conf = self.db.get_conf(ctx.guild)
        if conf.weeklysettings.remove:
            conf.weeklysettings.remove = False
            await ctx.send(_("Roles will no longer be removed from the previous winners"))
        else:
            conf.weeklysettings.remove = True
            await ctx.send(_("Roles will now be removed from the previous winners"))
        self.save()

    @weeklyset.command(name="autoreset")
    async def weeklyset_autoreset(self, ctx: commands.Context):
        """Toggle auto reset of weekly stats"""
        conf = self.db.get_conf(ctx.guild)
        if conf.weeklysettings.autoreset:
            conf.weeklysettings.autoreset = False
            await ctx.send(_("Weekly stats will no longer auto reset"))
        else:
            conf.weeklysettings.autoreset = True
            await ctx.send(_("Weekly stats will now auto reset"))
        self.save()

    @weeklyset.command(name="bonus")
    async def weeklyset_bonus(self, ctx: commands.Context, bonus: int):
        """Set bonus exp for top weekly winners"""
        conf = self.db.get_conf(ctx.guild)
        conf.weeklysettings.bonus = bonus
        await ctx.send(_("Bonus exp for weekly winners set to {}").format(bonus))
        self.save()

    @weeklyset.command(name="channel")
    async def weeklyset_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Set channel to announce weekly winners"""
        conf = self.db.get_conf(ctx.guild)
        conf.weeklysettings.channel = channel.id
        await ctx.send(_("Weekly winners will now be announced in {}").format(channel.mention))
        self.save()

    @weeklyset.command(name="day")
    async def weeklyset_day(self, ctx: commands.Context, day: int):
        """Set day for weekly stats reset
        0 = Monday
        1 = Tuesday
        2 = Wednesday
        3 = Thursday
        4 = Friday
        5 = Saturday
        6 = Sunday
        """
        conf = self.db.get_conf(ctx.guild)
        if day < 0 or day > 6:
            return await ctx.send(_("Day must be between 0 and 6"))
        conf.weeklysettings.reset_day = day
        await ctx.send(_("Weekly stats will now reset on {}").format(utils.get_day_name(day)))
        self.save()

    @weeklyset.command(name="hour")
    async def weeklyset_hour(self, ctx: commands.Context, hour: int):
        """Set hour for weekly stats reset"""
        conf = self.db.get_conf(ctx.guild)
        if hour < 0 or hour > 23:
            return await ctx.send(_("Hour must be between 0 and 23"))
        conf.weeklysettings.reset_hour = hour
        txt = _("Hour set to {}, next reset will occur at {}").format(hour, f"<t:{conf.weeklysettings.next_reset}:F>")
        await ctx.send(txt)
        self.save()

    @weeklyset.command(name="reset")
    @commands.bot_has_permissions(embed_links=True)
    async def reset_weekly_data(self, ctx: commands.Context, yes_or_no: bool):
        """Reset the weekly leaderboard manually and announce winners"""
        if not yes_or_no:
            return await ctx.send(_("Not resetting weekly stats"))
        async with ctx.typing():
            await self.reset_weekly(ctx.guild, ctx)
            await ctx.tick()

    @weeklyset.command(name="role")
    async def weeklyset_role(self, ctx: commands.Context, *, role: discord.Role):
        """Set role to award top weekly winners"""
        conf = self.db.get_conf(ctx.guild)
        conf.weeklysettings.role = role.id
        await ctx.send(_("Role set to {}").format(role.mention))
        self.save()

    @weeklyset.command(name="roleall")
    async def weeklyset_roleall(self, ctx: commands.Context):
        """Toggle whether all winners get the role"""
        conf = self.db.get_conf(ctx.guild)
        if conf.weeklysettings.role_all:
            conf.weeklysettings.role_all = False
            await ctx.send(_("Only the top winner will get the role"))
        else:
            conf.weeklysettings.role_all = True
            await ctx.send(_("All winners will get the role"))
        self.save()

    @weeklyset.command(name="winners")
    async def weeklyset_winners(self, ctx: commands.Context, count: int):
        """
        Set number of winners to display

        Due to Discord limitations with max embed field count, the maximum number of winners is 25
        """
        conf = self.db.get_conf(ctx.guild)
        if count < 1 or count > 25:
            return await ctx.send(_("Number of winners must be between 1 and 25"))
        conf.weeklysettings.count = count
        await ctx.send(_("Number of winners to display set to {}").format(count))
        self.save()

    @weeklyset.command(name="toggle")
    async def weeklyset_toggle(self, ctx: commands.Context):
        """Toggle weekly stat tracking"""
        conf = self.db.get_conf(ctx.guild)
        if conf.weeklysettings.on:
            conf.weeklysettings.on = False
            await ctx.send(_("Weekly stat tracking disabled"))
        else:
            conf.weeklysettings.on = True
            await ctx.send(_("Weekly stat tracking enabled"))
        self.save()
