import logging
import typing as t
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .common.calls import create_memory_call
from .common.constants import REACT_SUMMARY_MESSAGE
from .common.utils import can_use, embed_to_content

log = logging.getLogger("red.vrt.assistant.listener")
_ = Translator("Assistant", __file__)


class AssistantListener(MixinMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responding_to = set()

    @commands.Cog.listener("on_message_without_command")
    async def handler(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        if message.author.id in self.responding_to:
            return
        # If message was from a bot
        if message.author.bot and not self.db.listen_to_bots:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Ignore messages without content
        if not message.content:
            if not message.embeds:
                return
            # Replace message content with embed content
            embed_to_content(message)
        # Ignore if channel doesn't exist
        if not message.channel:
            return
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # Check permissions
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return
        if not message.channel.permissions_for(message.guild.me).embed_links:
            return

        conf = self.db.get_conf(message.guild)
        if not conf.enabled or not conf.api_key:
            return

        channel = message.channel
        mention_ids = [m.id for m in message.mentions]
        bot_mentioned = self.bot.user.id in mention_ids

        ref: discord.Message = None
        # If bot wasnt mentioned in the message, see if someone replied to it
        if not bot_mentioned and hasattr(message, "reference") and message.reference:
            ref = message.reference.resolved
            if not isinstance(ref, discord.Message):
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                except discord.HTTPException:
                    pass

        if ref and ref.author.id == self.bot.user.id:
            bot_mentioned = True

        if channel.id != conf.channel_id:
            # Message outside of assistant channel
            # The ONLY way we dont return is if the bot was mentioned and mention_respond is enabled
            if not bot_mentioned or not conf.mention_respond:
                return
        elif ref is not None:  # Message in assistant channel and user is replying to someone
            # If user is replying to anyone other than the bot, ignore
            if ref.author.id != self.bot.user.id:
                return
        elif mention_ids and self.bot.user.id not in mention_ids:
            # Message in the assistant channel and user mentioned someone other than the bot
            return

        # Ignore common prefixes from other bots
        if message.content.startswith((",", ".", "+", "!", "-", ">" "<", "?", "$", "%", "^", "&", "*", "_")):
            return
        if not await can_use(message, conf.blacklist, respond=False):
            return
        if not message.content.endswith("?") and conf.endswith_questionmark and self.bot.user.id not in mention_ids:
            return
        if len(message.content.strip()) < conf.min_length:
            return
        self.responding_to.add(message.author.id)
        try:
            async with channel.typing():
                await self.handle_message(message, message.content, conf, listener=True)
        finally:
            self.responding_to.remove(message.author.id)

    @commands.Cog.listener("on_guild_remove")
    async def cleanup(self, guild: discord.Guild):
        if guild.id in self.db.configs:
            log.info(f"Bot removed from {guild.name}, cleaning up...")
            del self.db.configs[guild.id]
            await self.save_conf()

    @commands.Cog.listener("on_raw_reaction_add")
    async def remember(self, payload: discord.RawReactionActionEvent):
        """Save messages as embeddings when reacted to with :brain: emoji"""
        emoji = str(payload.emoji)
        if emoji != "\N{BRAIN}":
            return
        if payload.user_id == self.bot.user.id:
            return
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        user = payload.member
        if not user:
            return
        # Ignore reactions added by other bots
        if user.bot:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        if not message:
            return
        if not message.content:
            return
        conf = self.db.get_conf(guild)
        if not conf.enabled:
            return
        if not conf.api_key:
            return
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if not any([role.id in conf.tutors for role in user.roles]) and user.id not in conf.tutors:
            return

        messages: t.List[discord.Message] = [message]

        # Set up the message chain
        tmp = message
        while True:
            if getattr(tmp, "reference", None) is not None:
                resolved = tmp.reference.resolved
                if resolved is None:
                    break
                messages.append(resolved)
                # If the message is a reply to another message, we want to keep going up the chain
                tmp = resolved

            else:
                break

        messages.reverse()

        content = StringIO()
        for idx, msg in enumerate(messages):
            if idx == 0:
                content.write(f"Original message from {msg.author.name}: {msg.content}\n")
            else:
                content.write(f"{msg.author.name} said: {msg.content}\n")

        for msg in messages:
            content.write(f"{msg.author.name} said: {msg.content}\n")

        success = True
        try:
            messages = [
                {"role": "system", "content": REACT_SUMMARY_MESSAGE.strip()},
                {"role": "user", "content": content.getvalue()},
            ]
            res = await create_memory_call(messages=messages, api_key=conf.api_key)
            if res:
                embedding = await self.add_embedding(guild, res.memory_name, res.memory_content)
                if embedding is None:
                    success = False
                else:
                    log.info(f"Created embedding in {guild.name}\nName: {res.memory_name}\nEntry: {res.memory_content}")
            else:
                success = False
        except Exception as e:
            log.warning(f"Failed to save embed memory in {guild.name}", exc_info=e)
            success = False

        if success:
            await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        else:
            await message.add_reaction("\N{CROSS MARK}")
