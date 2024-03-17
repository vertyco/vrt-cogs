import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..vragepy import VRageClient

log = logging.getLogger("red.vrt.setools.listeners.messages")


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        settings = self.db.get_conf(message.guild)
        servers = [s for s in settings.servers if s.chat_channel == message.channel.id]
        if not servers:
            return
        server = servers[0]
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return

        # Reformat messages if containing mentions
        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@{mention.id}>", f"@{mention.display_name}")
        if message.channel_mentions:
            # noinspection PyTypeChecker
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        if message.role_mentions:
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        payload = f"{message.author.display_name}: {message.content}"
        client = VRageClient(base_url=server.address, token=server.token)
        try:
            await client.send_chat(payload)
        except Exception as e:
            log.exception(f"send_chat failed for {message.guild} in {message.channel}", exc_info=e)
            return
