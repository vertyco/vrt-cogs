import asyncio
import logging
import random
import typing as t
from io import BytesIO
from time import perf_counter

import discord
from redbot.core import bank
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from ..common import formatter, utils
from ..common.models import Profile
from ..generator import fullprofile, runescape

log = logging.getLogger("red.vrt.levelup.api.profile")
_ = Translator("LevelUp", __file__)


class ProfileFormatting(MixinMeta):
    async def get_profile_background(self, user_id: int, profile: Profile) -> bytes:
        """Get a background for a user's profile in the following priority:
        - Custom background selected by user
        - Banner of user's Discord profile
        - Random background
        """
        if profile.background == "default":
            if banner_url := await self.get_banner(user_id):
                if banner_bytes := await utils.get_content_from_url(banner_url):
                    return banner_bytes

        if profile.background.lower().startswith("http"):
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
                if banner_bytes := await utils.get_content_from_url(banner_url):
                    return banner_bytes

        return random.choice(valid).read_bytes()

    async def get_banner(self, user_id: int) -> t.Optional[str]:
        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user_id))
        if banner_id := req.get("banner"):
            return f"https://cdn.discordapp.com/banners/{user_id}/{banner_id}?size=1024"

    async def get_user_profile(
        self, member: discord.Member, reraise: bool = False
    ) -> t.Union[discord.Embed, discord.File]:
        """Get a user's profile as an embed or file
        If embed profiles are disabled, a file will be returned, otherwise an embed will be returned

        Args:
            member (discord.Member): The member to get the profile for
            reraise (bool, optional): Fetching profiles will normally catch almost all exceptions and try to
            handle them silently, this will make them throw an exception. Defaults to False.

        Returns:
            t.Union[discord.Embed, discord.File]: An embed or file containing the user's profile
        """
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
            conf,
            "lb",
            member.id,
            "xp",
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

        if conf.use_embeds:
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

        avatar = await member.display_avatar.read()
        background = await self.get_profile_background(member.id, profile)
        kwargs = {
            "background_bytes": background,
            "avatar_bytes": avatar,
            "username": member.display_name if profile.show_displayname else member.name,
            "status": str(member.status).strip(),
            "level": profile.level,
            "messages": profile.messages,
            "voicetime": profile.voice,
            "stars": profile.stars,
            "prestige": profile.prestige,
            "previous_xp": last_level_xp,
            "current_xp": current_xp,
            "next_xp": next_level_xp,
            "position": stat["position"],
            "blur": profile.blur,
            "base_color": member.color.to_rgb() if member.color.to_rgb() != (0, 0, 0) else None,
            "user_color": utils.string_to_rgb(profile.namecolor) if profile.namecolor else None,
            "stat_color": utils.string_to_rgb(profile.statcolor) if profile.statcolor else None,
            "level_bar_color": utils.string_to_rgb(profile.barcolor) if profile.barcolor else None,
            "render_gif": self.db.render_gifs,
            "reraise": reraise,
        }
        if pdata:
            emoji_bytes = await utils.get_content_from_url(pdata.emoji_url)
            kwargs["prestige_emoji"] = emoji_bytes
        if conf.showbal:
            kwargs["balance"] = await bank.get_balance(member)
            kwargs["currency_name"] = await bank.get_currency_name(guild)
        if role_icon := member.top_role.icon:
            kwargs["role_icon"] = await role_icon.read()
        if profile.font:
            if (self.fonts / profile.font).exists():
                kwargs["font_path"] = str(self.fonts / profile.font)
            elif (self.custom_fonts / profile.font).exists():
                kwargs["font_path"] = str(self.custom_fonts / profile.font)

        funcs = {
            "default": fullprofile.generate_full_profile,
            "runescape": runescape.generate_runescape_profile,
        }

        def _run() -> discord.File:
            img_bytes, animated = funcs[profile.style](**kwargs)
            ext = "gif" if animated else "webp"
            return discord.File(BytesIO(img_bytes), filename=f"profile.{ext}")

        file = await asyncio.to_thread(_run)
        return file

    async def get_user_profile_cached(self, member: discord.Member) -> discord.File:
        if not self.db.cache_seconds:
            return await self.get_user_profile(member)
        now = perf_counter()
        last_used, imgbytes = self.profiles.setdefault(member.guild.id, {}).get(member.id)
        if last_used and now - last_used < self.db.cache_seconds:
            return discord.File(BytesIO(imgbytes), filename="profile.webp")
        file = await self.get_user_profile(member)
        if not isinstance(file, discord.File):
            return file
        filebytes = await file.fp.read()
        self.profiles[member.guild.id][member.id] = (now, filebytes)
        return discord.File(BytesIO(filebytes), filename="profile.webp")
