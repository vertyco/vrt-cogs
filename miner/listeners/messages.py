import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import ActiveChannel
from ..views.mining_view import RockView

log = logging.getLogger("red.vrt.miner.listeners.messages")


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if isinstance(message.channel, discord.DMChannel):
            return
        if not self.db_active():
            return
        if not await ActiveChannel.exists().where(ActiveChannel.id == message.channel.id):
            return
        self.activity.note(message.channel.id)
        if message.content and "reload" in message.content:
            return
        if self.active_guild_rocks[message.guild.id] >= constants.PER_GUILD_ROCK_CAP:
            return
        if message.channel.id in self.active_channel_rocks:
            return
        if not self.activity.should_spawn(message.channel.id):
            return

        self.active_guild_rocks[message.guild.id] += 1
        self.active_channel_rocks.add(message.channel.id)
        try:
            tier = self.activity.get_rock(message.channel.id)
            rocktype = constants.ROCK_TYPES[tier]
            view = RockView(self, rocktype)
            await view.start(message.channel)
            await view.wait()
        except Exception as e:
            log.error(f"Error spawning rock in {message.channel.id}: {e}")
        finally:
            self.active_guild_rocks[message.guild.id] -= 1
            self.active_channel_rocks.discard(message.channel.id)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not self.db_active():
            return
        # TODO: delete active rock if it exists for this channel
