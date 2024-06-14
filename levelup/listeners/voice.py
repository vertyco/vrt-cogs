import asyncio
import logging
import random
from time import perf_counter

import discord
from redbot.core import commands

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.listeners.voice")


class VoiceListener(MixinMeta):
    async def initialize_voice_states(self) -> int:
        self.in_voice = {}

        def _init() -> int:
            initialized = 0
            perf = perf_counter()
            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.voice and member.voice.channel:
                        self.in_voice.setdefault(guild.id, {})[member.id] = perf
                        initialized += 1
            return initialized

        return await asyncio.to_thread(_init)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        in_voice = self.in_voice.setdefault(member.guild.id, {})
        if not before.channel and not after.channel:
            # False voice state update
            if member.id in in_voice:
                self.in_voice[member.guild.id].pop(member.id)
            return
        conf = self.db.get_conf(member.guild)
        if not conf.enabled:
            return

        channel = after.channel or before.channel
        addxp = True
        if conf.ignore_deafened and after.self_deaf:
            addxp = False
        elif conf.ignore_muted and after.self_mute:
            addxp = False
        elif conf.ignore_invisible and member.status.name == "offline":
            addxp = False
        elif any(role.id in conf.ignoredroles for role in member.roles):
            addxp = False
        elif member.id in conf.ignoredusers:
            addxp = False
        elif channel.id in conf.ignoredchannels:
            addxp = False
        elif conf.ignore_solo and len([i for i in channel.members if not i.bot]) <= 1:
            addxp = False

        if before.channel and after.channel:
            # User switched VC
            if member.id not in in_voice:
                log.error(f"User {member.name} switched VCs but isnt in voice cache in {member.guild}")
                self.in_voice[member.guild.id][member.id] = perf_counter()
            return

        if not before.channel and after.channel:
            # User joins VC, start tracking time
            self.in_voice[member.guild.id][member.id] = perf_counter()
            return

        if not (before.channel and not after.channel):
            log.error(
                f"Unknown voice state update for {member.name} in {member.guild} (before: {before.channel}, after: {after.channel})"
            )
            if member.id in in_voice:
                self.in_voice[member.guild.id].pop(member.id)
            return

        # If we're here, user left VC
        joined = in_voice.pop(member.id, None)
        if not joined:
            log.error(f"User {member.name} left a voice channel but wasn't in the cache in {member.guild}")
            return

        time_spent = perf_counter() - joined
        xp_to_add = conf.voicexp * (time_spent / 60)
        cat_id = getattr(channel.category, "id", 0)
        if channel.id in conf.channelbonus.voice:
            xp_to_add += random.randint(*conf.channelbonus.voice[channel.id])
        elif cat_id in conf.channelbonus.voice:
            xp_to_add += random.randint(*conf.channelbonus.voice[cat_id])

        # Stack all role bonuses
        role_ids = [role.id for role in member.roles]
        for role_id, (bonus_min, bonus_max) in conf.rolebonus.voice.items():
            if role_id in role_ids:
                xp_to_add += random.randint(bonus_min, bonus_max)

        profile = conf.get_profile(member)
        weekly = conf.get_weekly_profile(member) if conf.weeklysettings.on else None
        profile.voice += time_spent
        if addxp:
            profile.xp += xp_to_add
        if weekly:
            weekly.voice += time_spent
            if addxp:
                weekly.xp += xp_to_add

        for role_id in role_ids:
            if role_id in conf.role_groups:
                conf.role_groups[role_id] += xp_to_add

        self.save()
        log.debug(f"Added {round(xp_to_add, 2)} XP to {member.name} in {member.guild}")
        await self.check_levelups(member.guild, member, profile, conf, channel=channel)
