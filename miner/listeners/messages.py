import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..db.tables import ActiveChannel

log = logging.getLogger("red.vrt.miner.listeners.messages")


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if isinstance(message.channel, (discord.DMChannel, discord.ForumChannel, discord.CategoryChannel)):
            return
        if not self.db_active():
            return

        channel: discord.TextChannel | discord.Thread = message.channel

        # Check if this is an active mining channel
        is_mining_channel = await ActiveChannel.exists().where(ActiveChannel.id == channel.id)
        if not is_mining_channel:
            return

        # Track the user in the channel's chat cache for rock quality scaling
        # Get or create the user's player data to know their tool tier
        player = await self.db_utils.get_create_player(message.author)
        self.chat_cache.add_user(channel.id, message.author.id, player.tool)
