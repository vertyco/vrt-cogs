import asyncio
import logging
import random
from copy import copy
from time import perf_counter

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import GuildSettings, VoiceTracking

log = logging.getLogger("red.vrt.levelup.listeners.voice")


class VoiceListener(MixinMeta):
    async def initialize_voice_states(self) -> int:
        self.voice_tracking.clear()

        def _init() -> int:
            initialized = 0
            perf = perf_counter()
            for guild in self.bot.guilds:
                if guild.id not in self.db.configs:
                    continue
                conf = self.db.get_conf(guild)
                if not conf.enabled:
                    continue
                voice = self.voice_tracking[guild.id]
                for member in guild.members:
                    if member.voice and member.voice.channel:
                        earning_xp = self.can_gain_exp(conf, member, member.voice)
                        voice[member.id] = VoiceTracking(
                            joined=perf,
                            not_gaining_xp=not earning_xp,
                            not_gaining_xp_time=0.0,
                            stopped_gaining_xp_at=perf if not earning_xp else None,
                        )
                        initialized += 1
            return initialized

        return await asyncio.to_thread(_init)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        # If roles changed and user is in VC, we need to check if they can gain exp
        if before.roles != after.roles and (after.voice or before.voice):
            await self._on_voice_state_update(after, before.voice, after.voice)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        # If user goes offline/online and they're in VC, we need to check if they can gain exp
        if before.status != after.status and (after.voice or before.voice):
            await self._on_voice_state_update(after, before.voice, after.voice)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        await self._on_voice_state_update(member, before, after)

    async def _on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot and self.db.ignore_bots:
            return
        conf = self.db.get_conf(member.guild)
        if not conf.enabled:
            return
        voice = self.voice_tracking[member.guild.id]
        if not before.channel and not after.channel:
            log.error(f"False voice state update for {member.name} in {member.guild}")
            voice.pop(member.id, None)
            return
        perf = perf_counter()

        if before.channel == after.channel:
            # Voice state changed but user is still in the same VC
            log.debug(f"Voice state changed for {member.name} in {member.guild}")
            earning_xp = self.can_gain_exp(conf, member, after)
            data = voice[member.id]
            if data.not_gaining_xp and earning_xp:
                log.debug(f"{member.name} now earning xp in {after.channel.name} in {member.guild}")
                # User's state change means they can now earn exp again
                data.not_gaining_xp = False
                data.not_gaining_xp_time += perf - data.stopped_gaining_xp_at
                data.stopped_gaining_xp_at = None
            elif not data.not_gaining_xp and not earning_xp:
                log.debug(f"{member.name} no longer earning xp in {after.channel.name} in {member.guild}")
                # User's state change means they shouldnt earn exp
                data.not_gaining_xp = True
                data.stopped_gaining_xp_at = perf
            else:
                # No meaningful state change, just return
                pass
            return

        # Case 1: User joins VC
        if not before.channel and after.channel:
            log.debug(f"{member.name} joined VC {after.channel.name} in {member.guild}")
            earning_xp = self.can_gain_exp(conf, member, after)
            voice[member.id] = VoiceTracking(
                joined=perf,
                not_gaining_xp=not earning_xp,
                not_gaining_xp_time=0.0,
                stopped_gaining_xp_at=perf if not earning_xp else None,
            )
            # Go ahead and update other users in the channel
            for m in after.channel.members:
                if m.id == member.id:
                    continue
                earning_xp = self.can_gain_exp(conf, m, m.voice)
                user_data = voice.setdefault(
                    m.id,
                    VoiceTracking(
                        joined=perf,
                        not_gaining_xp=not earning_xp,
                        not_gaining_xp_time=0.0,
                        stopped_gaining_xp_at=perf if not earning_xp else None,
                    ),
                )
                if user_data.not_gaining_xp and earning_xp:
                    log.debug(f"{m.name} now earning xp in {after.channel.name} in {member.guild}")
                    user_data.not_gaining_xp = False
                    user_data.not_gaining_xp_time += perf - user_data.stopped_gaining_xp_at
                    user_data.stopped_gaining_xp_at = None
                elif not user_data.not_gaining_xp and not earning_xp:
                    log.debug(f"{m.name} no longer earning xp in {after.channel.name} in {member.guild}")
                    user_data.not_gaining_xp = True
                    user_data.stopped_gaining_xp_at = perf
            # No exp needs to be added here so just return
            return

        # Case 2: User switches VC
        if before.channel and after.channel:
            # Treat this as a the user leaving the VC and then joining the new one
            # We'll fire off two events, one for leaving and one for joining
            # This will also reduce the amount of code that needs to be duplicated

            # Simulate user leaving the VC
            mock_after_voice_state = copy(after)
            mock_after_voice_state.channel = None
            await self._on_voice_state_update(member, before, mock_after_voice_state)

            # Simulate user joining the new VC
            mock_before_voice_state = before
            mock_before_voice_state.channel = None
            await self._on_voice_state_update(member, mock_before_voice_state, after)

            # No exp needs to be added here so just return
            return

        # Case 3: If we're here, the user left the VC
        log.debug(f"{member.name} left VC {before.channel.name} in {member.guild}")
        # First lets add the time to the user, and exp if they were earning it
        data = voice.pop(member.id, None)
        if not data:
            # User wasnt in the voice cache, maybe cog was reloaded while user was in VC?
            log.warning(f"User {member.name} left VC but wasnt in voice cache in {member.guild}")
            return
        # Add whatever time is left that the user wasnt gaining exp to their total time not gaining exp
        if data.not_gaining_xp and data.stopped_gaining_xp_at:
            data.not_gaining_xp_time += perf - data.stopped_gaining_xp_at
        # Calculate the total time the user spent in the VC
        total_time_in_voice = perf - data.joined
        # Effective time is the total time minus the time they weren't earning exp
        effective_time = total_time_in_voice - data.not_gaining_xp_time
        profile = conf.get_profile(member)
        weekly = conf.get_weekly_profile(member) if conf.weeklysettings.on else None

        log.debug(f"{member.name} spent {round(total_time_in_voice, 2)}s in VC {before.channel.name} in {member.guild}")
        if effective_time > 0:
            log.debug(f"{round(effective_time, 2)}s of that was effective time")
        profile.voice += total_time_in_voice
        if weekly:
            weekly.voice += total_time_in_voice

        # Calculate the exp to add
        xp_to_add = conf.voicexp * (effective_time / 60)
        cat_id = getattr(before.channel.category, "id", 0)
        if before.channel.id in conf.channelbonus.voice:
            xp_to_add += random.randint(*conf.channelbonus.voice[before.channel.id]) * (effective_time / 60)
        elif cat_id in conf.channelbonus.voice:
            xp_to_add += random.randint(*conf.channelbonus.voice[cat_id]) * (effective_time / 60)

        # Stack all role bonuses
        role_ids = [role.id for role in member.roles]
        for role_id, (bonus_min, bonus_max) in conf.rolebonus.voice.items():
            if role_id in role_ids:
                xp_to_add += random.randint(bonus_min, bonus_max) * (effective_time / 60)

        # Add the exp to the user
        if xp_to_add:
            log.debug(f"Adding {round(xp_to_add, 2)} Voice XP to {member.name} in {member.guild}")
            profile.xp += xp_to_add
            if weekly:
                weekly.xp += xp_to_add

        # Now we need to update everyone else in the channel in case the exp gaining states have changed
        # Get the channel now that the user has left
        channel = member.guild.get_channel(before.channel.id)
        if not channel:
            # User left channel because it was deleted?
            log.warning(f"User {member.name} left VC {before.channel.name} but channel wasnt found in {member.guild}")
        else:
            for m in channel.members:
                if m.id == member.id:
                    continue
                earning_xp = self.can_gain_exp(conf, m, m.voice)
                user_data = voice.setdefault(
                    m.id,
                    VoiceTracking(
                        joined=perf,
                        not_gaining_xp=not earning_xp,
                        not_gaining_xp_time=0.0,
                        stopped_gaining_xp_at=perf if not earning_xp else None,
                    ),
                )
                if user_data.not_gaining_xp and earning_xp:
                    log.debug(f"{m.name} now earning xp in {channel.name} in {member.guild}")
                    user_data.not_gaining_xp = False
                    user_data.not_gaining_xp_time += perf - user_data.stopped_gaining_xp_at
                    user_data.stopped_gaining_xp_at = None
                elif not user_data.not_gaining_xp and not earning_xp:
                    log.debug(f"{m.name} no longer earning xp in {channel.name} in {member.guild}")
                    user_data.not_gaining_xp = True
                    user_data.stopped_gaining_xp_at = perf

        # Save the changes
        self.save()
        # Check for levelups
        await self.check_levelups(member.guild, member, profile, conf, channel=channel)

    def can_gain_exp(
        self,
        conf: GuildSettings,
        member: discord.Member,
        voice_state: discord.VoiceState,
    ) -> bool:
        """Determine whether a user can gain exp in the current voice state

        voice_state may be the before or after voice state, depending on the event

        Args:
            conf (GuildSettings): The guild settings
            member (discord.Member): The member to check
            voice_state (discord.VoiceState): The current state of the user in the VC

        Returns:
            bool: Whether the user can gain exp
        """
        addxp = True
        if conf.ignore_deafened and voice_state.self_deaf:
            addxp = False
        elif conf.ignore_muted and voice_state.self_mute:
            addxp = False
        elif conf.ignore_invisible and member.status.name == "offline":
            addxp = False
        elif any(role.id in conf.ignoredroles for role in member.roles):
            addxp = False
        elif member.id in conf.ignoredusers:
            addxp = False
        elif voice_state.channel.id in conf.ignoredchannels:
            addxp = False
        elif voice_state.channel.category_id and voice_state.channel.category_id in conf.ignoredchannels:
            addxp = False
        elif (
            conf.ignore_solo and len([i for i in voice_state.channel.members if (not i.bot and i.id != member.id)]) < 1
        ):
            addxp = False
        elif self.db.ignore_bots and member.bot:
            addxp = False
        elif conf.allowedchannels:
            if voice_state.channel.id not in conf.allowedchannels:
                if voice_state.channel.category_id:
                    if voice_state.channel.category_id not in conf.allowedchannels:
                        addxp = False
                else:
                    addxp = False

        return addxp
