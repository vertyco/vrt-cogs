import asyncio
import os
import random
import typing as t
from io import BytesIO, StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common import utils
from ..generator import imgtools, levelalert

_ = Translator("LevelUp", __file__)


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
            value=_("`Profile Cache Time: `{}\n`Cache Size:         `{}\n").format(
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

        # External API section
        txt = _(
            "*If an external API URL is specified, the bot will use that URL for image generation.*\n"
            "- **External API URL:** {}\n"
        ).format(
            self.db.external_api_url or _("Not Using"),
        )
        embed.add_field(
            name=_("External API Settings"),
            value=txt,
            inline=False,
        )

        # Managed API section
        if self.db.managed_api:
            api_status = _("Running") if self._managed_api_process else _("Stopped")
            workers = self.db.managed_api_workers or max(1, (os.cpu_count() or 4) // 2)
            workers_display = f"{workers} (auto)" if self.db.managed_api_workers == 0 else str(workers)
            txt = _(
                "*The bot manages a local uvicorn API process for high-performance image generation.*\n"
                "- **Status:** {}\n"
                "- **Port:** {}\n"
                "- **Workers:** {}\n"
            ).format(api_status, self.db.managed_api_port, workers_display)
        else:
            txt = _("*Managed local API is disabled. Using subprocess per request.*")
        embed.add_field(
            name=_("Managed Local API"),
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

    @lvlowner.command(name="externalapi")
    async def set_external_api(self, ctx: commands.Context, url: str):
        """
        Set the external API URL for image generation

        Set to `none` to disable the external API

        **Notes**
        - If the API fails, the cog will fall back to subprocess image generation.
        """
        if url == "none":
            self.db.external_api_url = ""
            self.save()
            return await ctx.send(_("External API disabled"))
        if not url.startswith("http"):
            return await ctx.send(_("Invalid URL"))

        self.db.external_api_url = url
        await ctx.send(_("External API URL set to `{}`").format(url))
        self.save()

    @lvlowner.command(name="managedapi")
    async def toggle_managed_api(self, ctx: commands.Context, port: t.Optional[int] = None):
        """
        Toggle the managed local API for high-performance image generation

        The managed API runs uvicorn locally, providing much higher throughput than
        the subprocess method while requiring no external setup.

        **Arguments**
        - `port`: Optional port number (default 6789). Only used when enabling.

        **Notes**
        - The managed API is automatically started on cog load and stopped on unload.
        - If the managed API fails, the cog falls back to subprocess generation.
        - This takes precedence over subprocess but not over an external API URL.
        """
        if self.db.managed_api:
            # Disable
            await self._stop_managed_api()
            self.db.managed_api = False
            await ctx.send(_("Managed local API disabled. Now using subprocess for image generation."))
        else:
            # Enable
            if port is not None:
                if not 1024 <= port <= 65535:
                    return await ctx.send(_("Port must be between 1024 and 65535."))
                self.db.managed_api_port = port

            self.db.managed_api = True
            self.save()

            async with ctx.typing():
                success = await self._start_managed_api()

            if success:
                await ctx.send(
                    _(
                        "Managed local API enabled on port {}. Image generation will use the persistent API process."
                    ).format(self.db.managed_api_port)
                )
            else:
                self.db.managed_api = False
                await ctx.send(_("Failed to start managed API. Check logs for details. Falling back to subprocess."))
        self.save()

    @lvlowner.command(name="apiworkers")
    async def set_api_workers(self, ctx: commands.Context, workers: int):
        """
        Set the number of workers for the managed API

        **Arguments**
        - `workers`: Number of uvicorn workers (1-32). Set to 0 for auto (cpu_count // 2).

        **Notes**
        - Changes take effect after restarting the managed API.
        - More workers = more concurrent requests, but more memory usage.
        - Recommended: 1 worker per 2 CPU cores.
        """
        if workers < 0 or workers > 32:
            return await ctx.send(_("Workers must be between 0 and 32. Use 0 for auto-detection."))

        self.db.managed_api_workers = workers
        self.save()

        if workers == 0:
            auto_workers = max(1, (os.cpu_count() or 4) // 2)
            await ctx.send(_("API workers set to auto ({} workers based on CPU count).").format(auto_workers))
        else:
            await ctx.send(_("API workers set to {}.").format(workers))

        if self.db.managed_api and self._managed_api_process is not None:
            await ctx.send(
                _("Restart the managed API with `{}lvlowner managedapi` (twice) for changes to take effect.").format(
                    ctx.clean_prefix
                )
            )

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
