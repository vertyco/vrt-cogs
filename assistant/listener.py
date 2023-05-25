import logging

import discord
from openai.error import InvalidRequestError
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .common.utils import get_attachments
from .models import READ_EXTENSIONS, GuildSettings

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

        for mention in message.mentions:
            message.content = message.content.replace(
                f"<@{mention.id}>", f"@{mention.display_name}"
            )
        for mention in message.channel_mentions:
            message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        for mention in message.role_mentions:
            message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        content = message.content
        mentions = [member.id for member in message.mentions]
        if (
            not content.endswith("?")
            and conf.endswith_questionmark
            and self.bot.user.id not in mentions
        ):
            return
        if attachments := get_attachments(message):
            for i in attachments:
                if not any(i.filename.lower().endswith(ext) for ext in READ_EXTENSIONS):
                    continue
                text = await i.read()
                content += f"\n\nUploaded [{i.filename}]: {text.decode()}"

        if len(content.strip()) < conf.min_length:
            return
        async with channel.typing():
            await self.try_replying(message, content, conf)

    async def try_replying(self, message: discord.Message, content: str, conf: GuildSettings):
        try:
            reply = await self.chat_async(
                content, message.author, message.author.guild, message.channel, conf
            )
            if len(reply) < 2000:
                return await message.reply(reply, mention_author=conf.mention)
            embeds = [
                discord.Embed(description=p)
                for p in pagify(reply, page_length=4000, delims=("```", "\n"))
            ]
            await message.reply(embeds=embeds, mention_author=conf.mention)
        except InvalidRequestError as e:
            if error := e.error:
                await message.reply(error["message"], mention_author=conf.mention)
            log.error("Invalid Request Error", exc_info=e)
        except Exception as e:
            await message.channel.send(f"**Error**\n```py\n{e}\n```")
            log.error("Listener Reply Error", exc_info=e)

    @commands.Cog.listener("on_guild_remove")
    async def cleanup(self, guild: discord.Guild):
        if guild.id in self.db.configs:
            log.info(f"Bot removed from {guild.name}, cleaning up...")
            del self.db.configs[guild.id]
            await self.save_conf()
