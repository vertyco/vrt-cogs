import asyncio
import base64
import logging
import random
import typing as t
from contextlib import suppress
from io import BytesIO

import aiohttp
import discord
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common import utils
from ..common.models import GuildSettings, Profile
from ..generator import levelalert

log = logging.getLogger("red.vrt.levelup.shared.levelups")
_ = Translator("LevelUp", __file__)


class LevelUps(MixinMeta):
    async def check_levelups(
        self,
        guild: discord.Guild,
        member: discord.Member,
        profile: Profile,
        conf: GuildSettings,
        message: t.Optional[discord.Message] = None,
        channel: t.Optional[
            t.Union[discord.TextChannel, discord.VoiceChannel, discord.Thread, discord.ForumChannel]
        ] = None,
    ) -> bool:
        """Check if a user has leveled up and award roles if needed

        Args:
            guild (discord.Guild): The guild where the leveling up occurred.
            member (discord.Member): The member who leveled up.
            profile (Profile): The profile of the member.
            conf (GuildSettings): The guild settings.
            message (t.Optional[discord.Message], optional): The message that triggered the leveling up. Defaults to None.
            channel (t.Optional[t.Union[discord.TextChannel, discord.VoiceChannel, discord.Thread, discord.ForumChannel]], optional): The channel where the leveling up occurred. Defaults to None.

        Returns:
            bool: True if the user leveled up, False otherwise.
        """
        calculated_level = conf.algorithm.get_level(profile.xp)
        if calculated_level == profile.level:
            # No action needed, user hasn't leveled up
            return False
        if not calculated_level:
            # User hasnt reached level 1 yet
            return False
        log.debug(f"{member} has reached level {calculated_level} in {guild}")
        profile.level = calculated_level
        # User has reached a new level, time to log and award roles if needed
        await self.ensure_roles(member, conf)
        current_channel = channel or (message.channel if message else None)
        log_channel = guild.get_channel(conf.notifylog) if conf.notifylog else None

        role = None
        if calculated_level in conf.levelroles:
            role_id = conf.levelroles[calculated_level]
            role = guild.get_role(role_id)

        placeholders = {
            "username": member.name,
            "displayname": member.display_name,
            "mention": member.mention,
            "level": profile.level,
            "role": role.name if role else None,
            "server": guild.name,
        }
        username = member.display_name if profile.show_displayname else member.name
        mention = member.mention if conf.notifymention else username
        if role:
            if dm_txt_raw := conf.role_awarded_dm:
                dm_txt = dm_txt_raw.format(**placeholders)
            else:
                dm_txt = _("You just reached level {} in {} and obtained the {} role!").format(
                    profile.level, guild.name, role.mention
                )
            if msg_txt_raw := conf.role_awarded_msg:
                msg_txt = msg_txt_raw.format(**placeholders)
            else:
                msg_txt = _("{} just reached level {} and obtained the {} role!").format(
                    mention, profile.level, role.mention
                )
        else:
            placeholders.pop("role")
            if dm_txt_raw := conf.levelup_dm:
                dm_txt = dm_txt_raw.format(**placeholders)
            else:
                dm_txt = _("You just reached level {} in {}!").format(profile.level, guild.name)
            if msg_txt_raw := conf.levelup_msg:
                msg_txt = msg_txt_raw.format(**placeholders)
            else:
                msg_txt = _("{} just reached level {}!").format(mention, profile.level)

        if conf.use_embeds or self.db.force_embeds:
            if conf.notifydm:
                embed = discord.Embed(
                    description=dm_txt,
                    color=member.color,
                ).set_thumbnail(url=member.display_avatar)
                with suppress(discord.HTTPException):
                    await member.send(embed=embed)

            embed = discord.Embed(
                description=msg_txt,
                color=member.color,
            ).set_author(
                name=member.display_name if profile.show_displayname else member.name,
                icon_url=member.display_avatar,
            )
            if current_channel and conf.notify:
                with suppress(discord.HTTPException):
                    if conf.notifymention:
                        await current_channel.send(member.mention, embed=embed)
                    else:
                        await current_channel.send(embed=embed)

            current_channel_id = current_channel.id if current_channel else 0
            if log_channel and log_channel.id != current_channel_id:
                with suppress(discord.HTTPException):
                    if conf.notifymention:
                        await log_channel.send(member.mention, embed=embed)
                    else:
                        await log_channel.send(embed=embed)

        else:
            fonts = list(self.fonts.glob("*.ttf")) + list(self.custom_fonts.iterdir())
            font = str(random.choice(fonts))
            if profile.font:
                if (self.fonts / profile.font).exists():
                    font = str(self.fonts / profile.font)
                elif (self.custom_fonts / profile.font).exists():
                    font = str(self.custom_fonts / profile.font)

            color = utils.string_to_rgb(profile.statcolor) if profile.statcolor else member.color.to_rgb()
            if color == (0, 0, 0):
                color = utils.string_to_rgb(profile.namecolor) if profile.namecolor else None

            payload = aiohttp.FormData()
            if self.db.external_api_url or (self.db.internal_api_port and self.api_proc):
                banner = await self.get_profile_background(member.id, profile, try_return_url=True)
                avatar = member.display_avatar.url
                payload.add_field(
                    "background_bytes", BytesIO(banner) if isinstance(banner, bytes) else banner, filename="data"
                )
                payload.add_field("avatar_bytes", avatar)
                payload.add_field("level", str(profile.level))
                payload.add_field("color", str(color))
                payload.add_field("font_path", font)
                payload.add_field("render_gif", str(self.db.render_gifs))

            else:
                avatar = await member.display_avatar.read()
                banner = await self.get_profile_background(member.id, profile)

            img_bytes, animated = None, None
            if external_url := self.db.external_api_url:
                try:
                    url = f"{external_url}/levelup"
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, data=payload) as response:
                            if response.status == 200:
                                data = await response.json()
                                img_b64, animated = data["b64"], data["animated"]
                                img_bytes = base64.b64decode(img_b64)
                except Exception as e:
                    log.error("Failed to fetch levelup image from external API", exc_info=e)
            elif self.db.internal_api_port and self.api_proc:
                try:
                    url = f"http://127.0.0.1:{self.db.internal_api_port}/levelup"
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, data=payload) as response:
                            if response.status == 200:
                                data = await response.json()
                                img_b64, animated = data["b64"], data["animated"]
                                img_bytes = base64.b64decode(img_b64)
                except Exception as e:
                    log.error("Failed to fetch levelup image from internal API", exc_info=e)

            def _run() -> t.Tuple[bytes, bool]:
                img_bytes, animated = levelalert.generate_level_img(
                    background_bytes=banner,
                    avatar_bytes=avatar,
                    level=profile.level,
                    color=color,
                    font_path=font,
                    render_gif=self.db.render_gifs,
                )
                return img_bytes, animated

            if not img_bytes:
                img_bytes, animated = await asyncio.to_thread(_run)

            ext = "gif" if animated else "webp"
            if conf.notifydm:
                file = discord.File(BytesIO(img_bytes), filename=f"levelup.{ext}")
                with suppress(discord.HTTPException):
                    await member.send(dm_txt, file=file)

            if current_channel and conf.notify:
                file = discord.File(BytesIO(img_bytes), filename=f"levelup.{ext}")
                with suppress(discord.HTTPException):
                    if conf.notifymention and message is not None:
                        await message.reply(msg_txt, file=file, mention_author=True)
                    else:
                        await current_channel.send(msg_txt, file=file)

            current_channel_id = current_channel.id if current_channel else 0
            if log_channel and log_channel.id != current_channel_id:
                file = discord.File(BytesIO(img_bytes), filename=f"levelup.{ext}")
                with suppress(discord.HTTPException):
                    if conf.notifymention:
                        await current_channel.send(msg_txt, file=file)
                    else:
                        await log_channel.send(msg_txt, file=file)

        payload = {
            "guild": guild,  # discord.Guild
            "member": member,  # discord.Member
            "message": message,  # Optional[discord.Message] = None
            "channel": channel,  # Optional[TextChannel | VoiceChannel | Thread | ForumChannel] = None
            "new_level": profile.level,  # int
        }
        self.bot.dispatch("member_levelup", **payload)
        return True

    async def ensure_roles(
        self,
        member: discord.Member,
        conf: t.Optional[GuildSettings] = None,
        reason: t.Optional[str] = None,
    ) -> t.Tuple[t.List[discord.Role], t.List[discord.Role]]:
        """Ensure a user has the correct level roles based on their level and the guild's settings"""
        if conf is None:
            conf = self.db.get_conf(member.guild)
        if not conf.levelroles:
            return [], []
        if not member.guild.me.guild_permissions.manage_roles:
            return [], []
        if member.id not in conf.users:
            return [], []
        if reason is None:
            reason = _("Level Up")
        conf.levelroles = dict(sorted(conf.levelroles.items(), key=lambda x: x[0], reverse=True))
        to_add = set()
        to_remove = set()
        user_roles = member.roles
        user_role_ids = [role.id for role in user_roles]
        profile = conf.get_profile(member)

        using_prestige = all([profile.prestige, conf.prestigelevel, conf.prestigedata, conf.keep_level_roles])

        if using_prestige:
            # User has prestiges and thus must meet the requirements for any level role inherently
            valid_levels = conf.levelroles
        else:
            valid_levels = {k: v for k, v in conf.levelroles.items() if k <= profile.level}

        valid_levels = dict(sorted(valid_levels.items(), key=lambda x: x[0]))

        if conf.autoremove:
            # Add highest level role and remove the rest
            highest_role_id = 0
            if valid_levels:
                highest_role_id = valid_levels[max(list(valid_levels.keys()))]
                if highest_role_id not in user_role_ids:
                    to_add.add(highest_role_id)

            for role_id in conf.levelroles.values():
                if role_id != highest_role_id and role_id in user_role_ids:
                    to_remove.add(role_id)
        else:
            # Ensure user has all roles up to their level
            for level, role_id in conf.levelroles.items():
                if level <= profile.level or using_prestige:
                    if role_id not in user_role_ids:
                        to_add.add(role_id)
                elif role_id in user_role_ids:
                    to_remove.add(role_id)

        if profile.prestige and conf.prestigedata:
            # Assign prestige roles
            if conf.stackprestigeroles:
                for prestige_level, pdata in conf.prestigedata.items():
                    if profile.prestige < prestige_level:
                        continue
                    if pdata.role in user_role_ids:
                        continue
                    to_add.add(pdata.role)
            else:
                # Remove all prestige roles except the highest
                for prestige_level, pdata in conf.prestigedata.items():
                    if prestige_level == profile.prestige:
                        if pdata.role not in user_role_ids:
                            to_add.add(pdata.role)
                        continue
                    if pdata.role in user_role_ids:
                        to_remove.add(pdata.role)

        if weekly_role_id := conf.weeklysettings.role:
            role_winners = conf.weeklysettings.last_winners
            if not conf.weeklysettings.role_all and role_winners:
                role_winners = [role_winners[0]]

            if member.id in role_winners and weekly_role_id not in user_role_ids:
                to_add.add(weekly_role_id)
            elif member.id not in role_winners and weekly_role_id in user_role_ids:
                to_remove.add(weekly_role_id)

        add_roles: t.List[discord.Role] = []
        remove_roles: t.List[discord.Role] = []
        bad_roles = set()  # Roles that the bot can't manage or cant find
        for role_id in to_add:
            role = member.guild.get_role(role_id)
            if role and role.position < member.guild.me.top_role.position:
                add_roles.append(role)
            else:
                bad_roles.add(role_id)
        for role_id in to_remove:
            role = member.guild.get_role(role_id)
            if role and role.position < member.guild.me.top_role.position:
                remove_roles.append(role)
            else:
                bad_roles.add(role_id)

        if bad_roles:
            conf.levelroles = {k: v for k, v in conf.levelroles.items() if v not in bad_roles}
            self.save()

        try:
            if add_roles:
                await member.add_roles(*add_roles, reason=reason)
            if remove_roles:
                await member.remove_roles(*remove_roles, reason=reason)
        except discord.HTTPException:
            log.warning(f"Failed to add/remove roles for {member}")
            add_roles = []
            remove_roles = []
        return add_roles, remove_roles
