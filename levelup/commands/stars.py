import asyncio
import typing as t
from datetime import datetime, timedelta

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common import formatter, utils
from ..views.dynamic_menu import DynamicMenu

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Stars(MixinMeta):
    @commands.hybrid_command(name="stars", aliases=["givestar", "addstar", "thanks"])
    @commands.guild_only()
    async def give_stars(self, ctx: commands.Context, *, user: t.Optional[discord.Member] = None):
        """Reward a good noodle"""
        if user and user.id == ctx.author.id:
            return await ctx.send(_("You can't give stars to yourself!"), ephemeral=True)
        if user and user.bot and self.db.ignore_bots:
            return await ctx.send(_("You can't give stars to bots!"), ephemeral=True)

        last_used = self.stars.setdefault(ctx.guild.id, {}).get(ctx.author.id)
        conf = self.db.get_conf(ctx.guild)
        now = datetime.now()

        if not user and not last_used:
            # User has not given a star yet, just send help
            return await ctx.send_help()

        elif not user and last_used:
            # User has given a star, but they didnt mention anyone
            can_use_after = last_used + timedelta(seconds=conf.starcooldown)
            if now > can_use_after:
                txt = _("You can give more stars now! Just mention a user in this command.")
            else:
                ts = f"<t:{int(can_use_after.timestamp())}:R>"
                txt = _("You can give more stars {}").format(ts)
            return await ctx.send(txt, ephemeral=True)

        elif not user:
            return await ctx.send(_("You need to mention a user to give them a star!"))
        elif last_used:
            can_use_after = last_used + timedelta(seconds=conf.starcooldown)
            if now < can_use_after:
                ts = f"<t:{int(can_use_after.timestamp())}:R>"
                return await ctx.send(
                    _("You can give more stars {}").format(ts),
                    ephemeral=True,
                )

        self.stars[ctx.guild.id][ctx.author.id] = now
        profile = conf.get_profile(user)
        profile.stars += 1
        if conf.weeklysettings.on:
            weekly = conf.get_weekly_profile(user)
            weekly.stars += 1
        self.save()
        name = user.mention if conf.starmention else f"**{user.display_name}**"
        kwargs = {"ephemeral": True}
        if conf.starmentionautodelete:
            kwargs["delete_after"] = conf.starmentionautodelete
        await ctx.send(_("You just gave a star to {}!").format(name), **kwargs)

    @commands.command(name="startop", aliases=["topstars", "starleaderboard", "starlb"])
    @commands.guild_only()
    async def startop(
        self,
        ctx: commands.Context,
        globalstats: bool = False,
        displayname: bool = True,
    ):
        """View the Star Leaderboard"""
        stat = "stars"
        pages = await asyncio.to_thread(
            formatter.get_leaderboard,
            bot=self.bot,
            guild=ctx.guild,
            db=self.db,
            stat=stat,
            lbtype="lb",
            is_global=globalstats,
            member=ctx.author,
            use_displayname=displayname,
            color=await self.bot.get_embed_color(ctx),
        )
        if isinstance(pages, str):
            return await ctx.send(pages)
        await DynamicMenu(ctx, pages).refresh()

    @commands.group(name="starset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def starset(self, ctx: commands.Context) -> None:
        """Configure LevelUp Star Settings"""
        pass

    @starset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def starset_view(self, ctx: commands.Context) -> None:
        """View Star Settings"""
        conf = self.db.get_conf(ctx.guild)
        embed = discord.Embed(
            title=_("Star Settings"),
            color=await self.bot.get_embed_color(ctx),
        )
        delta = utils.humanize_delta(conf.starcooldown)
        embed.add_field(
            name=_("Cooldown"),
            value=_("Users can give stars every {}").format(delta),
            inline=False,
        )
        embed.add_field(
            name=_("Star Mention"),
            value=_("The bot will{} send a message when someone gives a star").format(
                "" if conf.starmention else _(" **not**")
            ),
            inline=False,
        )
        if conf.starmentionautodelete:
            txt = _("The bot will delete the star message after {}").format(
                utils.humanize_delta(conf.starmentionautodelete)
            )
        else:
            txt = _("The bot will **not** delete the star message after sending it")
        embed.add_field(
            name=_("Star Mention Auto Delete"),
            value=txt,
            inline=False,
        )
        await ctx.send(embed=embed)

    @starset.command(name="cooldown")
    async def starset_cooldown(self, ctx: commands.Context, cooldown: int) -> None:
        """Set the star cooldown"""
        conf = self.db.get_conf(ctx.guild)
        conf.starcooldown = cooldown
        await ctx.send(_("Cooldown set to {}").format(utils.humanize_delta(cooldown)))
        self.save()

    @starset.command(name="mention")
    async def starset_mention(self, ctx: commands.Context) -> None:
        """Toggle star reaction mentions"""
        conf = self.db.get_conf(ctx.guild)
        if conf.starmention:
            conf.starmention = False
            await ctx.send(_("Star mention disabled"))
        else:
            conf.starmention = True
            await ctx.send(_("Star mention enabled"))
        self.save()

    @starset.command(name="mentiondelete")
    async def starset_mentionautodelete(self, ctx: commands.Context, delete_after: int) -> None:
        """Toggle whether the bot auto-deletes the star mentions

        Set to 0 to disable auto-delete
        """
        conf = self.db.get_conf(ctx.guild)
        conf.starmentionautodelete = delete_after
        if delete_after:
            await ctx.send(_("Star mention auto delete set to {}").format(delete_after))
        else:
            await ctx.send(_("Star mention auto delete disabled"))
        self.save()
