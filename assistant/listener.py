import logging

import discord
from redbot.core import commands

from .abc import MixinMeta
from .common.utils import can_use

log = logging.getLogger("red.vrt.assistant.listener")


class AssistantListener(MixinMeta):
    @commands.Cog.listener("on_message_without_command")
    async def handler(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Ignore messages without content
        if not message.content:
            return
        # Ignore if channel doesn't exist
        if not message.channel:
            return
        # Ignore references to other members
        if hasattr(message, "reference") and message.reference:
            ref = message.reference.resolved
            if ref and ref.author.id != self.bot.user.id:
                return

        conf = self.db.get_conf(message.guild)
        if not conf.enabled:
            return
        if not conf.api_key:
            return
        channel = message.channel
        if channel.id != conf.channel_id:
            return
        if not await can_use(message, conf.blacklist, respond=False):
            return
        mentions = [member.id for member in message.mentions]
        if (
            not message.content.endswith("?")
            and conf.endswith_questionmark
            and self.bot.user.id not in mentions
        ):
            return

        if len(message.content.strip()) < conf.min_length:
            return

        async with channel.typing():
            await self.handle_message(message, message.content, conf, listener=True)

    @commands.Cog.listener("on_guild_remove")
    async def cleanup(self, guild: discord.Guild):
        if guild.id in self.db.configs:
            log.info(f"Bot removed from {guild.name}, cleaning up...")
            del self.db.configs[guild.id]
            await self.save_conf()
