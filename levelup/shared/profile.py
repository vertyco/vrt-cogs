import asyncio
import base64
import logging
import random
import typing as t
from io import BytesIO
from time import perf_counter

import aiohttp
import discord
from discord.http import Route
from redbot.core import bank
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from ..common import formatter, utils
from ..common.models import Profile
from ..generator.styles import default, gaming, minimal, runescape

log = logging.getLogger("red.vrt.levelup.shared.profile")
_ = Translator("LevelUp", __file__)


class ProfileFormatting(MixinMeta):
    async def add_xp(self, member: discord.Member, xp: int) -> int:
        """Add XP to a user and check for level ups"""
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        conf = self.db.get_conf(member.guild)
        profile = conf.get_profile(member)
        profile.xp += xp
        self.save(False)
        return int(profile.xp)

    async def set_xp(self, member: discord.Member, xp: int) -> int:
        """Set a user's XP and check for level ups"""
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        conf = self.db.get_conf(member.guild)
        profile = conf.get_profile(member)
        profile.xp = xp
        self.save(False)
        return int(profile.xp)

    async def remove_xp(self, member: discord.Member, xp: int) -> int:
        """Remove XP from a user and check for level ups"""
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        conf = self.db.get_conf(member.guild)
        profile = conf.get_profile(member)
        profile.xp -= xp
        self.save(False)
        return int(profile.xp)

    async def get_xp(self, member: discord.Member) -> int:
        """Get the XP for a member"""
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        conf = self.db.get_conf(member.guild)
        profile = conf.get_profile(member)
        return int(profile.xp)

    async def get_level(self, member: discord.Member) -> int:
        """Get the level for a member"""
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        conf = self.db.get_conf(member.guild)
        profile = conf.get_profile(member)
        return profile.level

    async def get_profile_background(
        self, user_id: int, profile: Profile, try_return_url: bool = False, guild_id: int = None
    ) -> t.Union[bytes, str]:
        """
        Get a background for a user's profile in the following priority:
        - Stored background (base64 with b64: prefix)
        - Custom background selected by user
        - Banner of user's Discord profile
        - Guild default background
        - Random background
        """

        guild_conf = None
        if guild_id is not None:
            guild_conf = self.db.get_conf(guild_id)

        # Check for base64 stored background (prefixed with "b64:")
        if profile.background.startswith("b64:"):
            return base64.b64decode(profile.background[4:])

        if profile.background == "default":
            if banner_url := await self.get_banner(user_id):
                if try_return_url:
                    return banner_url
                if banner_bytes := await utils.get_content_from_url(banner_url):
                    return banner_bytes

        if profile.background.lower().startswith("http"):
            if try_return_url:
                return profile.background
            if content := await utils.get_content_from_url(profile.background):
                return content

        valid = list(self.backgrounds.glob("*.webp")) + list(self.custom_backgrounds.iterdir())
        if profile.background == "random":
            return random.choice(valid).read_bytes()

        # See if filename is specified
        for path in valid:
            if profile.background == path.stem or profile.background == path.name:
                return path.read_bytes()

        # If we're here then the profile's preference failed
        # Try banner first if not default
        if profile.background != "default":
            if banner_url := await self.get_banner(user_id):
                if try_return_url:
                    return banner_url
                if banner_bytes := await utils.get_content_from_url(banner_url):
                    return banner_bytes

        # Check guild default background if available
        if guild_conf and guild_conf.default_background != "default":
            if guild_conf.default_background.lower().startswith("http"):
                if try_return_url:
                    return guild_conf.default_background
                if content := await utils.get_content_from_url(guild_conf.default_background):
                    return content

            # Check if guild default is a filename
            for path in valid:
                if guild_conf.default_background == path.stem or guild_conf.default_background == path.name:
                    return path.read_bytes()

        # Fallback to random
        return random.choice(valid).read_bytes()

    async def get_banner(self, user_id: int) -> t.Optional[str]:
        """Fetch a user's banner from Discord's API

        Args:
            user_id (int): The ID of the user

        Returns:
            t.Optional[str]: The URL of the user's banner image, or None if no banner is found
        """
        req = await self.bot.http.request(Route("GET", "/users/{uid}", uid=user_id))
        if banner_id := req.get("banner"):
            return f"https://cdn.discordapp.com/banners/{user_id}/{banner_id}?size=1024"

    async def get_user_profile(
        self,
        member: discord.Member,
        reraise: bool = False,
    ) -> t.Union[discord.Embed, discord.File]:
        """
        Get a user's profile as an embed or file
        If embed profiles are disabled, a file will be returned, otherwise an embed will be returned

        Args:
            member (discord.Member): The member to get the profile for
            reraise (bool, optional): Fetching profiles will normally catch almost all exceptions and try to
            handle them silently, this will make them throw an exception. Defaults to False.

        Returns:
            t.Union[discord.Embed, discord.File]: An embed or file containing the user's profile
        """
        if not isinstance(member, discord.Member):
            raise TypeError("member must be a discord.Member")
        guild = member.guild
        conf = self.db.get_conf(guild)
        profile = conf.get_profile(member)

        last_level_xp = conf.algorithm.get_xp(profile.level)
        current_xp = int(profile.xp)
        next_level_xp = conf.algorithm.get_xp(profile.level + 1)
        log.debug(f"last_level_xp: {last_level_xp}, current_xp: {current_xp}, next_level_xp: {next_level_xp}")
        if current_xp >= next_level_xp:
            # Rare but possible
            log.warning(f"User {member} has more XP than needed for next level")
            await self.check_levelups(guild, member, profile, conf)
            return await self.get_user_profile(member)

        current_diff = next_level_xp - last_level_xp
        progress = current_diff - (next_level_xp - current_xp)

        stat = await asyncio.to_thread(
            formatter.get_user_position,
            guild=guild,
            conf=conf,
            lbtype="xp",
            target_user=member.id,
            key="xp",
        )
        bar = utils.get_bar(progress, current_diff)

        level = conf.emojis.get("level", self.bot)
        trophy = conf.emojis.get("trophy", self.bot)
        star = conf.emojis.get("star", self.bot)
        chat = conf.emojis.get("chat", self.bot)
        mic = conf.emojis.get("mic", self.bot)
        bulb = conf.emojis.get("bulb", self.bot)
        money = conf.emojis.get("money", self.bot)

        # Prestige data
        pdata = None
        if profile.prestige and profile.prestige in conf.prestigedata:
            pdata = conf.prestigedata[profile.prestige]

        if conf.use_embeds or self.db.force_embeds:
            txt = f"{level}｜" + _("Level {}\n").format(humanize_number(profile.level))
            if pdata:
                txt += f"{trophy}｜" + _("Prestige {}\n").format(
                    f"{humanize_number(profile.prestige)} {pdata.emoji_string}"
                )
            txt += f"{star}｜{humanize_number(profile.stars)}" + _(" stars\n")
            txt += f"{chat}｜{humanize_number(profile.messages)}" + _(" messages sent\n")
            txt += f"{mic}｜{utils.humanize_delta(profile.voice)}" + _(" in voice\n")
            progress_txt = f"{bulb}｜{humanize_number(progress)}/{humanize_number(current_diff)}"
            txt += progress_txt + _(" Exp ({} total)\n").format(humanize_number(current_xp))
            if conf.showbal:
                balance = await bank.get_balance(member)
                creditname = await bank.get_currency_name(guild)
                txt += f"{money}｜{humanize_number(balance)} {creditname}\n"
            color = member.color
            if profile.statcolor:
                color = discord.Color.from_rgb(*utils.string_to_rgb(profile.statcolor))
            elif profile.barcolor:
                color = discord.Color.from_rgb(*utils.string_to_rgb(profile.barcolor))
            elif profile.namecolor:
                color = discord.Color.from_rgb(*utils.string_to_rgb(profile.namecolor))
            embed = discord.Embed(description=txt, color=color)
            embed.set_author(
                name=_("{}'s Profile").format(member.display_name if profile.show_displayname else member.name),
                icon_url=member.display_avatar,
            )
            embed.set_footer(
                text=_("Rank {}, with {}% of the total server Exp").format(
                    humanize_number(stat["position"]), round(stat["percent"], 1)
                ),
                icon_url=guild.icon,
            )
            embed.add_field(name=_("Progress"), value=box(bar, lang="python"), inline=False)
            return embed

        profile_style = conf.style_override or profile.style

        # Build request data for image generation
        request_data = {
            "style": profile_style,
            "username": member.display_name if profile.show_displayname else member.name,
            "status": str(member.status).strip(),
            "level": profile.level,
            "messages": profile.messages,
            "voicetime": int(profile.voice),
            "stars": profile.stars,
            "prestige": profile.prestige,
            "previous_xp": last_level_xp,
            "current_xp": current_xp,
            "next_xp": next_level_xp,
            "position": stat["position"],
            "blur": profile.blur,
            "render_gif": self.db.render_gifs,
        }

        # Add colors
        if member.color.to_rgb() != (0, 0, 0):
            request_data["base_color"] = member.color.to_rgb()
        if profile.namecolor:
            request_data["user_color"] = utils.string_to_rgb(profile.namecolor)
        if profile.statcolor:
            request_data["stat_color"] = utils.string_to_rgb(profile.statcolor)
        if profile.barcolor:
            request_data["level_bar_color"] = utils.string_to_rgb(profile.barcolor)

        # Add font name and bytes if custom font
        if profile.font:
            request_data["font_name"] = profile.font
            # Check if it's a custom font (not bundled) and include bytes for external API
            custom_font_path = self.custom_fonts / profile.font
            if custom_font_path.exists():
                font_bytes = await asyncio.to_thread(custom_font_path.read_bytes)
                request_data["font_b64"] = base64.b64encode(font_bytes).decode("utf-8")

        # Add balance if enabled
        if conf.showbal:
            request_data["balance"] = await bank.get_balance(member)
            request_data["currency_name"] = await bank.get_currency_name(guild)

        # Prestige emoji
        if pdata and pdata.emoji_url:
            request_data["prestige_emoji_url"] = pdata.emoji_url

        # Role icon
        if profile_style != "runescape" and member.top_role.icon:
            request_data["role_icon_url"] = member.top_role.icon.url

        # Get background URL/bytes
        if profile_style != "runescape":
            background = await self.get_profile_background(member.id, profile, try_return_url=True, guild_id=guild.id)
            if isinstance(background, str):
                request_data["background_url"] = background
            elif isinstance(background, bytes):
                # Sometimes discord's CDN returns error message
                if b"This content is no longer available" in background:
                    profile.background = "default"
                    self.save(False)
                    log.warning(f"User {member.name} ({member.id}) has invalid background! Resetting to default")
                    background = await self.get_profile_background(member.id, profile, guild_id=guild.id)
                request_data["background_b64"] = base64.b64encode(background).decode("utf-8")

        # Always use avatar URL (external API and subprocess both support URL fetching)
        request_data["avatar_url"] = str(member.display_avatar.url)

        # Try API first if configured (external or managed local)
        if api_url := self.get_api_url():
            endpoints = {
                "default": "fullprofile",
                "minimal": "fullprofile",
                "gaming": "fullprofile",
                "runescape": "runescape",
            }
            try:
                # Build FormData payload for legacy endpoint compatibility
                payload = aiohttp.FormData()
                for key, value in request_data.items():
                    if value is None:
                        continue
                    if key.endswith("_b64"):
                        # Decode and send as file for legacy endpoints
                        payload.add_field(key.replace("_b64", "_bytes"), base64.b64decode(value), filename="data")
                    elif key.endswith("_url"):
                        # Send URL as the bytes field name for legacy endpoints
                        payload.add_field(key.replace("_url", "_bytes"), str(value))
                    else:
                        payload.add_field(key, str(value))

                url = f"{api_url}/{endpoints[profile_style]}"
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, data=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            img_b64, animated = data["b64"], data["animated"]
                            img_bytes = base64.b64decode(img_b64)
                            ext = "gif" if animated else "webp"
                            return discord.File(BytesIO(img_bytes), filename=f"profile.{ext}")
                        log.error(f"Failed to fetch profile from API: {response.status}")
            except Exception as e:
                log.error("Failed to fetch profile from API, falling back to subprocess", exc_info=e)

        # Use subprocess for image generation
        output_path, result = await self.run_profile_subprocess(request_data)

        if output_path and result:
            img_bytes = output_path.read_bytes()
            ext = result.get("format", "webp")
            # Clean up output file
            try:
                output_path.unlink()
            except Exception:
                pass
            return discord.File(BytesIO(img_bytes), filename=f"profile.{ext}")

        # Final fallback - run in-process (should rarely happen)
        log.warning("Subprocess failed, falling back to in-process generation")

        # Prepare kwargs for direct generator call
        kwargs = {
            "username": request_data["username"],
            "status": request_data["status"],
            "level": request_data["level"],
            "messages": request_data["messages"],
            "voicetime": request_data["voicetime"],
            "stars": request_data["stars"],
            "prestige": request_data["prestige"],
            "previous_xp": request_data["previous_xp"],
            "current_xp": request_data["current_xp"],
            "next_xp": request_data["next_xp"],
            "position": request_data["position"],
            "blur": request_data["blur"],
            "render_gif": request_data["render_gif"],
            "reraise": reraise,
        }

        if "base_color" in request_data:
            kwargs["base_color"] = request_data["base_color"]
        if "user_color" in request_data:
            kwargs["user_color"] = request_data["user_color"]
        if "stat_color" in request_data:
            kwargs["stat_color"] = request_data["stat_color"]
        if "level_bar_color" in request_data:
            kwargs["level_bar_color"] = request_data["level_bar_color"]
        if "balance" in request_data:
            kwargs["balance"] = request_data["balance"]
            kwargs["currency_name"] = request_data.get("currency_name", "Credits")

        # Fetch assets for in-process fallback
        kwargs["avatar_bytes"] = await member.display_avatar.read()
        if profile_style != "runescape":
            kwargs["background_bytes"] = await self.get_profile_background(member.id, profile, guild_id=guild.id)
            if pdata and pdata.emoji_url:
                kwargs["prestige_emoji"] = await utils.get_content_from_url(pdata.emoji_url)
            if member.top_role.icon:
                kwargs["role_icon"] = await member.top_role.icon.read()

        if profile.font:
            if (self.fonts / profile.font).exists():
                kwargs["font_path"] = str(self.fonts / profile.font)
            elif (self.custom_fonts / profile.font).exists():
                kwargs["font_path"] = str(self.custom_fonts / profile.font)

        funcs = {
            "default": default.generate_default_profile,
            "minimal": minimal.generate_minimal_profile,
            "gaming": gaming.generate_gaming_profile,
            "runescape": runescape.generate_runescape_profile,
        }

        def _run() -> discord.File:
            img_bytes, animated = funcs[profile_style](**kwargs)
            ext = "gif" if animated else "webp"
            return discord.File(BytesIO(img_bytes), filename=f"profile.{ext}")

        file = await asyncio.to_thread(_run)
        return file

    async def get_user_profile_cached(self, member: discord.Member) -> t.Union[discord.File, discord.Embed]:
        """Cached version of get_user_profile"""
        if not self.db.cache_seconds:
            return await self.get_user_profile(member)
        now = perf_counter()
        cachedata = self.profile_cache.setdefault(member.guild.id, {}).get(member.id)
        if cachedata is None:
            file = await self.get_user_profile(member)
            if not isinstance(file, discord.File):
                return file
            filebytes = file.fp.read()
            self.profile_cache[member.guild.id][member.id] = (now, filebytes)
            return discord.File(BytesIO(filebytes), filename="profile.webp")

        last_used, imgbytes = cachedata
        if last_used and now - last_used < self.db.cache_seconds:
            return discord.File(BytesIO(imgbytes), filename="profile.webp")

        file = await self.get_user_profile(member)
        if not isinstance(file, discord.File):
            return file
        filebytes = file.fp.read()
        self.profile_cache[member.guild.id][member.id] = (now, filebytes)
        return discord.File(BytesIO(filebytes), filename="profile.webp")
