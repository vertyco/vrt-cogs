import asyncio
import random
from io import BytesIO, StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common import utils
from ..generator import imgtools, levelalert

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Owner(MixinMeta):
    @commands.group(name="levelowner", aliases=["lvlowner"])
    @commands.guild_only()
    @commands.is_owner()
    async def lvlowner(self, ctx: commands.Context) -> None:
        """Owner Only LevelUp Settings"""
        pass

    @lvlowner.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def lvlowner_view(self, ctx: commands.Context) -> None:
        """View Global LevelUp Settings"""
        embed = discord.Embed(color=await self.bot.get_embed_color(ctx))
        size_bytes = utils.deep_getsizeof(self.db)
        embed.add_field(
            name=_("Global Settings"),
            value=_("`Profile Cache Time: `{}\n`Cache Size:         `{}\n").format(
                utils.humanize_delta(self.db.cache_seconds),
                utils.humanize_size(size_bytes),
            ),
            inline=False,
        )
        if self.db.render_gifs:
            txt = _("Users with animated profiles will render as a GIF")
        else:
            txt = _("Profiles will always be static images")
        embed.add_field(
            name=_("GIF Profile Rendering"),
            value=txt,
            inline=False,
        )

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
            inline=False,
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
        self.save()

    @lvlowner.command(name="cache")
    async def set_cache(self, ctx: commands.Context, seconds: int) -> None:
        """Set the cache time for user profiles"""
        self.db.cache_seconds = seconds
        await ctx.send(_("Cache time set to {} seconds.").format(seconds))
        self.save()

    @commands.command(name="mocklvl", hidden=True)
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def test_levelup(self, ctx: commands.Context):
        """Test LevelUp Image Generation"""
        conf = self.db.get_conf(ctx.guild)
        profile = conf.get_profile(ctx.author)
        avatar = await ctx.author.display_avatar.read()

        banner = await ctx.author.banner.read() if ctx.author.banner else None
        if not banner:
            banner_url = await self.get_banner(ctx.author.id)
            if banner_url:
                banner = await utils.get_content_from_url(banner_url)

        level = random.randint(1, 10000)
        fonts = list(imgtools.FONTS.glob("*.ttf"))
        font = str(random.choice(fonts))
        if profile.font:
            if (self.fonts / profile.font).exists():
                font = str(self.fonts / profile.font)
            elif (self.custom_fonts / profile.font).exists():
                font = str(self.custom_fonts / profile.font)

        def _run() -> discord.File:
            img_bytes = levelalert.generate_level_img(
                background=banner,
                avatar=avatar,
                level=level,
                font=font,
                color=ctx.author.color.to_rgb(),
            )
            return discord.File(BytesIO(img_bytes), filename="levelup.webp")

        async with ctx.typing():
            file = await asyncio.to_thread(_run)
            await ctx.send(file=file)
