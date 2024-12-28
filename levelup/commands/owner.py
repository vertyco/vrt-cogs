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
    async def lvlowner(self, ctx: commands.Context):
        """Owner Only LevelUp Settings"""
        pass

    @lvlowner.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def lvlowner_view(self, ctx: commands.Context):
        """View Global LevelUp Settings"""

        def _size():
            size_bytes = utils.deep_getsizeof(self.db)
            size_bytes += utils.deep_getsizeof(self.lastmsg)
            size_bytes += utils.deep_getsizeof(self.voice_tracking)
            size_bytes += utils.deep_getsizeof(self.profile_cache)
            return size_bytes

        embed = discord.Embed(color=await self.bot.get_embed_color(ctx))
        size = await asyncio.to_thread(_size)
        embed.add_field(
            name=_("Global Settings"),
            value=_("`Profile Cache Time: `{}\n" "`Cache Size:         `{}\n").format(
                utils.humanize_delta(self.db.cache_seconds),
                utils.humanize_size(size),
            ),
            inline=False,
        )
        if self.db.ignore_bots:
            txt = _("Bots are ignored for all servers and cannot gain XP or have profiles")
        else:
            txt = _("Bots can gain XP and have profiles")
        embed.add_field(
            name=_("Ignore Bots"),
            value=txt,
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
        if self.db.force_embeds:
            txt = _("Profile embeds are enforced for all servers")
        else:
            txt = _("Profile embeds are optional for all servers")
        embed.add_field(
            name=_("Profile Embed Enforcement"),
            value=txt,
            inline=False,
        )
        tokens = await self.bot.get_shared_api_tokens("tenor")
        txt = _("*The Tenor API can be used to set gifs as profile backgrounds easier from within discord.*\n")
        if "api_key" in tokens:
            txt += _("Tenor API Key is set!")
        else:
            txt += _("Tenor API Key is not set! You can set it with {}").format(
                f"`{ctx.clean_prefix}set api tenor api_key YOUR_KEY`"
            )
        embed.add_field(
            name=_("Tenor API"),
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

        # Imgen API section
        txt = _(
            "*If an internal API port is specified, the bot will spin up subprocesses to handle image generation.*\n"
            "- **Internal API Port:** {}\n"
            "*If an external API URL is specified, the bot will use that URL for image generation.*\n"
            "- **External API URL:** {}\n"
        ).format(
            self.db.internal_api_port or _("Not Using"),
            self.db.external_api_url or _("Not Using"),
        )
        embed.add_field(
            name=_("API Settings"),
            value=txt,
            inline=False,
        )
        status = _("Enabled") if self.db.auto_cleanup else _("Disabled")
        embed.add_field(
            name=_("Auto-Cleanup ({})").format(status),
            value=_("If enabled, the bot will auto-purge configs of guilds that the bot is no longer in."),
            inline=False,
        )
        embed.add_field(
            name=_("Ignored Servers"),
            value=ignored_servers.getvalue() or _("None"),
            inline=False,
        )
        await ctx.send(embed=embed)

    @lvlowner.command(name="ignorebots")
    async def toggle_ignore_bots(self, ctx: commands.Context):
        """Toggle ignoring bots for XP and profiles

        **USE AT YOUR OWN RISK**
        Allowing your bot to listen to other bots is a BAD IDEA and should NEVER be enabled on public bots.
        """
        if self.db.ignore_bots:
            self.db.ignore_bots = False
            await ctx.send(_("Bots can now have profiles and gain XP like normal users. Proceed with caution..."))
        else:
            self.db.ignore_bots = True
            await ctx.send(_("Bots are now ignored entirely by LevelUp"))
        self.save()

    @lvlowner.command(name="autoclean")
    async def toggle_auto_cleanup(self, ctx: commands.Context):
        """Toggle purging of config data for guilds the bot is no longer in"""
        if self.db.auto_cleanup:
            self.db.auto_cleanup = False
            await ctx.send(_("Auto-Cleanup disabled."))
        else:
            self.db.auto_cleanup = True
            await ctx.send(_("Auto-Cleanup enabled."))
            bad_keys = [i for i in self.db.configs if not self.bot.get_guild(i)]
            for key in bad_keys:
                del self.db.configs[key]
            if bad_keys:
                await ctx.send(_("Purged {} guilds from the database.").format(len(bad_keys)))
        self.save()

    @lvlowner.command(name="internalapi")
    async def set_internal_api(self, ctx: commands.Context, port: int):
        """
        Enable internal API for parallel image generation

        Setting a port will spin up a detatched but cog-managed FastAPI server to handle image generation.
        The process ID will be attached to the bot object and persist through reloads.

        **USE AT YOUR OWN RISK!!!**
        Using the internal API will spin up multiple subprocesses to handle bulk image generation.
        If your bot crashes, the API subprocess will not be killed and will need to be manually terminated!
        It is HIGHLY reccommended to host the api separately!

        Set to 0 to disable the internal API

        **Notes**
        - This will spin up a 1 worker per core on the bot's cpu.
        - If the API fails, the cog will fall back to the default image generation method.
        """
        if port:
            if self.db.internal_api_port == port:
                return await ctx.send(_("Internal API port already set to {}, no change.").format(port))
            self.db.internal_api_port = port
            if self.api_proc:
                # Changing port so stop and start the server
                await ctx.send(_("Internal API port changed to {}, Restarting workers").format(port))
                await self.stop_api()
                await self.start_api()
            else:
                await ctx.send(_("Internal API port set to {}, Spinning up workers").format(port))
                await self.start_api()
        else:
            self.db.internal_api_port = port
            await ctx.send(_("Internal API disabled, shutting down workers."))
            await self.stop_api()
        self.save()

    @lvlowner.command(name="externalapi")
    async def set_external_api(self, ctx: commands.Context, url: str):
        """
        Set the external API URL for image generation

        Set to an `none` to disable the external API

        **Notes**
        - If the API fails, the cog will fall back to the default image generation method.
        """
        if url == "none":
            txt = _("External API disabled")
            self.db.external_api_url = ""
            self.save()
            # If interal api is set, start it up
            if self.db.internal_api_port:
                await self.start_api()
                txt += _("\nInternal API started since port was set.")
            return await ctx.send(txt)
        if not url.startswith("http"):
            return await ctx.send(_("Invalid URL"))

        self.db.external_api_url = url
        await ctx.send(_("External API URL set to `{}`").format(url))
        self.save()

    @lvlowner.command(name="rendergifs", aliases=["rendergif", "gif"])
    async def toggle_gif_rendering(self, ctx: commands.Context):
        """Toggle rendering of GIFs for animated profiles"""
        if self.db.render_gifs:
            self.db.render_gifs = False
            await ctx.send(_("GIF rendering disabled."))
        else:
            self.db.render_gifs = True
            await ctx.send(_("GIF rendering enabled."))
        self.save()

    @lvlowner.command(name="forceembeds", aliases=["forceembed"])
    async def toggle_force_embeds(self, ctx: commands.Context):
        """Toggle enforcing profile embeds

        If enabled, profiles will only use embeds on all servers.
        This disables image generation globally.
        """
        if self.db.force_embeds:
            self.db.force_embeds = False
            await ctx.send(_("Profile embeds are now optional for other servers."))
        else:
            self.db.force_embeds = True
            await ctx.send(_("Profile embeds are now enforced on all servers."))
        self.save()

    @lvlowner.command(name="ignore")
    async def ignore_server(self, ctx: commands.Context, guild_id: int):
        """Add/Remove a server from the ignore list"""
        if guild_id in self.db.ignored_guilds:
            self.db.ignored_guilds.remove(guild_id)
            await ctx.send(_("Server no longer ignored."))
        else:
            self.db.ignored_guilds.append(guild_id)
            await ctx.send(_("Server ignored."))
        self.save()

    @lvlowner.command(name="cache")
    async def set_cache(self, ctx: commands.Context, seconds: int):
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

        async with ctx.typing():
            avatar = await ctx.author.display_avatar.read()
            banner = await ctx.author.banner.read() if ctx.author.banner else None
            if not banner:
                banner_url = await self.get_banner(ctx.author.id)
                if banner_url:
                    banner = await utils.get_content_from_url(banner_url)

            level = random.randint(1, 100)
            fonts = list(imgtools.DEFAULT_FONTS.glob("*.ttf"))
            font = str(random.choice(fonts))
            if profile.font:
                if (self.fonts / profile.font).exists():
                    font = str(self.fonts / profile.font)
                elif (self.custom_fonts / profile.font).exists():
                    font = str(self.custom_fonts / profile.font)

            def _run() -> discord.File:
                img_bytes, animated = levelalert.generate_level_img(
                    background_bytes=banner,
                    avatar_bytes=avatar,
                    level=level,
                    font_path=font,
                    color=ctx.author.color.to_rgb(),
                    render_gif=self.db.render_gifs,
                )
                ext = "gif" if animated else "webp"
                return discord.File(BytesIO(img_bytes), filename=f"levelup.{ext}")

            file = await asyncio.to_thread(_run)
            await ctx.send(file=file)
