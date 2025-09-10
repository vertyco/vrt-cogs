import logging

import discord
from piccolo.query import OrderByRaw
from redbot.core import commands

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import ActiveChannel, GuildSettings
from ..views.mining_view import RockView

log = logging.getLogger("red.vrt.miner.listeners.messages")


class MessageListener(MixinMeta):
    def __init__(self):
        super().__init__()
        self.last_user_message: dict[int, int] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if isinstance(message.channel, discord.DMChannel):
            return
        if message.content and "reload" in message.content:
            return
        if self.active_guild_rocks[message.guild.id] >= constants.PER_GUILD_ROCK_CAP:
            return
        if not self.db_active():
            return

        if message.guild.id not in self.last_user_message:
            self.last_user_message[message.guild.id] = message.author.id
        elif self.last_user_message[message.guild.id] == message.author.id:
            # Same user cannot spam messages to increase activity
            return

        settings: GuildSettings = await self.db_utils.get_cached_guild_settings(message.guild.id)
        key = message.channel.id if settings.per_channel_activity_trigger else message.guild.id
        self.activity.update(key)
        rock_type: constants.RockTierName | None = self.activity.maybe_get_rock(key)
        if not rock_type:
            return

        if settings.per_channel_activity_trigger:
            channel = message.channel
            if not await ActiveChannel.exists(ActiveChannel.id == channel.id):
                return
        else:
            query = ActiveChannel.select(ActiveChannel.id).where(ActiveChannel.guild == message.guild.id)
            if self.active_channel_rocks:
                query = query.where(ActiveChannel.id.not_in(list(self.active_channel_rocks)))
            query = query.order_by(OrderByRaw("RANDOM()")).first()
            active_channel = await query
            if not active_channel:
                return
            channel = message.guild.get_channel_or_thread(active_channel["id"])
            if not channel:
                # Delete stale active channel entry
                await ActiveChannel.delete().where(ActiveChannel.id == active_channel["id"])
                log.warning(f"Deleted stale active channel {active_channel['id']}")
                return

        if message.channel.id in self.active_channel_rocks:
            return
        self.active_guild_rocks[message.guild.id] += 1
        self.active_channel_rocks.add(message.channel.id)
        try:
            rock: constants.RockType = constants.ROCK_TYPES[rock_type]
            view = RockView(self, rock)
            await view.start(message.channel)
            await view.wait()
        except Exception as e:
            log.error(f"Error spawning rock in {message.channel.id}: {e}")
        finally:
            self.active_guild_rocks[message.guild.id] = max(0, self.active_guild_rocks[message.guild.id] - 1)
            self.active_channel_rocks.discard(message.channel.id)
