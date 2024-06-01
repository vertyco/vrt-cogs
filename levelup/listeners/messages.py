import random
from time import perf_counter

import discord
from redbot.core import commands

from ..abc import MixinMeta


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Check if guild is in the master ignore list
        if str(message.guild.id) in self.db.ignored_guilds:
            return
        # Ignore webhooks
        if not isinstance(message.author, discord.Member):
            return
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        try:
            roles = list(message.author.roles)
            role_ids = [role.id for role in roles]
        except AttributeError:
            # User sent messange and left immediately?
            return
        conf = self.db.get_conf(message.guild)
        if not conf.enabled:
            return

        user_id = message.author.id
        profile = conf.get_profile(user_id).add_message()
        weekly = None
        if conf.weeklysettings.on:
            weekly = conf.get_weekly_profile(message.author).add_message()
        if user_id in conf.ignoredusers:
            return
        if message.channel.id in conf.ignoredchannels:
            return
        if any(role in conf.ignoredroles for role in role_ids):
            return

        now = perf_counter()
        last_messages = self.lastmsg.setdefault(message.guild.id, {})
        addxp = False
        if user_id not in last_messages:
            addxp = True
        elif now - last_messages[user_id] > conf.cooldown:
            addxp = True

        if not addxp:
            return

        self.lastmsg[message.guild.id][user_id] = now

        xp_to_add = random.randint(conf.xp[0], conf.xp[1])
        # Add channel bonus if it exists
        channel_bonuses = conf.channelbonus.msg
        cat_id = getattr(message.channel.category, "id", 0)
        if message.channel.id in channel_bonuses:
            xp_to_add += random.randint(*channel_bonuses[message.channel.id])
        elif cat_id in channel_bonuses:
            xp_to_add += random.randint(*channel_bonuses[cat_id])
        # Stack all role bonuses
        for role_id, (bonus_min, bonus_max) in conf.rolebonus.msg.items():
            if role_id in role_ids:
                xp_to_add += random.randint(bonus_min, bonus_max)
        # Add the xp to the role groups
        for role_id in role_ids:
            if role_id in conf.role_groups:
                conf.role_groups[role_id] += xp_to_add
        # Add the xp to the user's profile
        profile.xp += xp_to_add
        if weekly:
            weekly.xp += xp_to_add
        # Check for levelups
        await self.check_levelups(
            guild=message.guild,
            member=message.author,
            profile=profile,
            conf=conf,
            message=message,
            channel=message.channel,
        )
