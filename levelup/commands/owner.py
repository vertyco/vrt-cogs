from io import StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common import utils

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Owner(MixinMeta):
    @commands.group(name="lvlowner")
    @commands.guild_only()
    @commands.is_owner()
    async def lvlowner(self, ctx: commands.Context) -> None:
        """Owner Only LevelUp Settings"""
        pass

    @lvlowner.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def lvlowner_view(self, ctx: commands.Context) -> None:
        """View Global LevelUp Settings"""
        embed = discord.Embed(
            description="Global LevelUp Settings",
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name=_("Global Settings"),
            value=_("`Profile Cache Time: `{}\n`Cache Size:         `{}\n").format(
                utils.humanize_delta(self.db.cache_seconds),
                utils.humanize_size(self.db),
            ),
        )
        if self.db.render_gifs:
            txt = _("Users with animated profiles will render as a GIF")
        else:
            txt = _("Profiles will always be static images")
        embed.add_field(name=_("GIF Profile Rendering"), value=txt)

        ignored_servers = StringIO()
        for guild_id in self.db.ignored_guilds:
            guild = self.bot.get_guild(guild_id)
            if guild:
                ignored_servers.write(f"{guild_id} ({guild.name})\n")
            else:
                ignored_servers.write(_("{} (Bot not in server)\n").format(guild_id))
        embed.add_field(
            name=_("Ignored Servers"),
            value=ignored_servers.getvalue() or _("None"),
        )
        await ctx.send(embed=embed)

    @lvlowner.command(name="ignore")
    async def ignore_server(self, ctx: commands.Context, guild_id: int) -> None:
        """Add/Remove a server from the ignore list"""
        if guild_id in self.db.ignored_guilds:
            self.db.ignored_guilds.remove(guild_id)
            await ctx.send(_("Server no longer ignored."))
        else:
            self.db.ignored_guilds.append(guild_id)
            await ctx.send(_("Server ignored."))
