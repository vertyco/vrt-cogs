import asyncio
import logging
import random
import typing as t

import discord
from redbot.core import bank
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from ..common import formatter, utils
from ..common.models import Profile

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
            if profile.background == path.stem:
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

    async def get_user_profile(self, member: discord.Member) -> t.Union[discord.Embed, discord.File]:
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

        if conf.use_embeds:
            txt = f"{level}｜" + _("Level {}\n").format(humanize_number(profile.level))
            if profile.prestige and profile.prestige in conf.prestigedata:
                pdata = conf.prestigedata[profile.prestige]
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
