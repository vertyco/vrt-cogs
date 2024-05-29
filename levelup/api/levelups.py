import asyncio
import logging
import random
import typing as t
from contextlib import suppress
from io import BytesIO

import discord
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.models import GuildSettings, Profile
from ..generator import levelalert

log = logging.getLogger("red.vrt.levelup.api.levelups")
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
    ):
        calculated_level = conf.algorithm.get_level(profile.xp)
        if calculated_level == profile.level:
            # No action needed, user hasn't leveled up
            return
        profile.level = calculated_level
        # User has reached a new level, time to log and award roles if needed
        added, __ = await self.ensure_roles(member, conf)
        if not conf.notify:
            return
        log_channel = guild.get_channel(conf.notifylog) if conf.notifylog else channel
        if not log_channel and message is not None:
            log_channel = message.channel
        placeholders = {
            "username": member.name,
            "displayname": member.display_name,
            "mention": member.mention,
            "level": profile.level,
            "role": added[0] if added else None,
            "server": guild.name,
        }
        if added:
            if dm_txt_raw := conf.role_awarded_dm:
                dm_txt = dm_txt_raw.format(**placeholders)
            else:
                dm_txt = _("You just reached level {} in {} and obtained the {} role!").format(
                    profile.level, guild.name, added[0].name
                )
            if msg_txt_raw := conf.role_awarded_msg:
                msg_txt = msg_txt_raw.format(**placeholders)
            else:
                msg_txt = _("{} just reached level {} and obtained the {} role!").format(
                    member.mention, profile.level, added[0].name
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
                msg_txt = _("{} just reached level {}!").format(
                    member.mention if conf.notifymention else member.display_name, profile.level
                )

        if conf.use_embeds:
            if conf.notifydm:
                embed = discord.Embed(
                    description=dm_txt,
                    color=member.color,
                ).set_thumbnail(url=member.avatar_url)
                with suppress(discord.HTTPException):
                    await member.send(embed=embed)
            if log_channel:
                embed = discord.Embed(
                    description=msg_txt,
                    color=member.color,
                ).set_author(name=member.display_name, icon_url=member.avatar_url)
                with suppress(discord.HTTPException):
                    if conf.notifymention:
                        await log_channel.send(member.mention, embed=embed)
                    else:
                        await log_channel.send(embed=embed)
            return

        banner = await self.get_profile_background(member.id, profile)
        avatar = await member.display_avatar.read()
        fonts = list(conf.fonts.glob("*.ttf")) + list(self.custom_fonts.iterdir())
        font = str(random.choice(fonts))
        if profile.font:
            if (conf.fonts / profile.font).exists():
                font = str(conf.fonts / profile.font)
            elif (self.custom_fonts / profile.font).exists():
                font = str(self.custom_fonts / profile.font)

        def _run() -> bytes:
            img_bytes = levelalert.generate_level_img(
                background=banner,
                avatar=avatar,
                level=profile.level,
                color=member.color.to_rgb(),
                font_path=font,
            )
            return img_bytes

        filebytes = await asyncio.to_thread(_run)
        if conf.notifydm:
            file = discord.File(BytesIO(filebytes), filename="levelup.webp")
            with suppress(discord.HTTPException):
                await member.send(dm_txt, file=file)
        if log_channel:
            file = discord.File(BytesIO(filebytes), filename="levelup.webp")
            with suppress(discord.HTTPException):
                await log_channel.send(msg_txt, file=file)

    async def ensure_roles(
        self, member: discord.Member, conf: GuildSettings
    ) -> t.Tuple[t.List[discord.Role], t.List[discord.Role]]:
        """Ensure a user has the correct level roles based on their level and the guild's settings"""
        if not conf.levelroles:
            return [], []
        if not member.guild.me.guild_permissions.manage_roles:
            return [], []
        if member.id not in conf.users:
            return [], []
        conf.levelroles = dict(sorted(conf.levelroles.items(), key=lambda x: x[0], reverse=True))
        to_add = set()
        to_remove = set()
        user_roles = member.roles
        user_role_ids = [role.id for role in user_roles]
        profile = conf.get_profile(member)
        valid_levels = {k: v for k, v in conf.levelroles.items() if k <= profile.level}
        if conf.autoremove:
            # Add highest level role and remove the rest
            highest_role_id = 0
            if valid_levels:
                highest_role_id = valid_levels[max(valid_levels)]
                to_add.add(highest_role_id)

            for role_id in conf.levelroles.values():
                if role_id != highest_role_id and role_id in user_role_ids:
                    to_remove.add(role_id)
        else:
            # Ensure user has all roles up to their level
            for level, role_id in conf.levelroles.items():
                if level <= profile.level:
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
                await member.add_roles(*add_roles, reason="Level up")
            if remove_roles:
                await member.remove_roles(*remove_roles, reason="Level up")
        except discord.HTTPException:
            log.warning(f"Failed to add/remove roles for {member}")
            add_roles = []
            remove_roles = []
        return add_roles, remove_roles
