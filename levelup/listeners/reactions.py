import logging
from datetime import datetime, timedelta

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.listeners.reactions")
_ = Translator("LevelUp", __file__)


class ReactionListener(MixinMeta):
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload:
            return
        if not payload.guild_id:
            return
        if not payload.member:
            return
        if payload.emoji.name != "\N{WHITE MEDIUM STAR}":
            return
        if not payload.member:
            return
        if payload.member.bot:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if guild.id in self.db.ignored_guilds:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return
        if not msg:
            return
        if msg.author.bot:
            return
        if msg.author.id == payload.member.id:
            return

        last_used = self.stars.setdefault(guild.id, {}).get(payload.member.id)
        conf = self.db.get_conf(guild)
        now = datetime.now()

        if last_used:
            can_use_after = last_used + timedelta(seconds=conf.starcooldown)
            if now < can_use_after:
                return

        self.stars[guild.id][payload.member.id] = now
        profile = conf.get_profile(msg.author)
        profile.stars += 1
        if conf.weeklysettings.on:
            weekly = conf.get_weekly_profile(msg.author)
            weekly.stars += 1
        self.save()
        txt = _("{} just gave a star to {}!").format(
            f"**{payload.member.display_name}**",
            f"**{msg.author.display_name}**",
        )
        if conf.starmention and channel.permissions_for(guild.me).send_messages:
            kwargs = {"content": txt}
            if conf.starmentionautodelete:
                kwargs["delete_after"] = conf.starmentionautodelete
            await channel.send(**kwargs)
