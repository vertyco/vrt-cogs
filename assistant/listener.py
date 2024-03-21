import logging

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .common.constants import REACT_NAME_MESSAGE, REACT_SUMMARY_MESSAGE
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

        # Ignore channels that arent a dedicated assistant channel
        if channel.id != conf.channel_id:
            # Perform some preliminary checks
            if self.bot.user.id not in mention_ids:
                return
            # If here, bot was mentioned
            if not conf.mention_respond:
                return

        # Ignore references to other members unless bot is pinged
        if hasattr(message, "reference") and message.reference:
            ref = message.reference.resolved
            if ref and ref.author.id != self.bot.user.id and self.bot.user.id not in mention_ids:
                return
            # Ignore common prefixes from other bots
            ignore_prefixes = [",", ".", "+", "!", "-", ">"]
            if any(message.content.startswith(i) for i in ignore_prefixes):
                return
            if ref.author.id == self.bot.user.id and not conf.mention_respond:
                # Ignore mentions on reply if mention_respond is disabled
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

        initial_content = f"{message.author.name} said: {message.content}"
        if message.author.bot:
            initial_content = message.content

        success = True
        try:
            # Get embedding content first
            messages = [
                {"role": "system", "content": REACT_SUMMARY_MESSAGE.strip()},
                {"role": "user", "content": initial_content},
            ]
            embed_response = await self.request_response(messages=messages, conf=conf)
            if isinstance(embed_response, str):
                embed_response = {"role": "assistant", "content": embed_response}
            else:
                embed_response = embed_response.model_dump()
            messages.append(embed_response)
            messages.append({"role": "user", "content": REACT_NAME_MESSAGE})

            # Create a name for the embedding
            messages = [
                {"role": "system", "content": REACT_NAME_MESSAGE.strip()},
                {"role": "user", "content": embed_response["content"]},
            ]
            name_response = await self.request_response(messages=messages, conf=conf)
            if isinstance(name_response, str):
                name_response = {"role": "assistant", "content": name_response}
            else:
                name_response = name_response.model_dump()
            embedding = await self.add_embedding(guild, name_response["content"], embed_response["content"])
            if embedding is None:
                success = False
            else:
                log.info(
                    f"Created embedding in {guild.name}\nName: {name_response['content']}\nEntry: {embed_response['content']}"
                )
        except Exception as e:
            log.warning(f"Failed to save embed memory in {guild.name}", exc_info=e)
            success = False

        if success:
            await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        else:
            await message.add_reaction("\N{CROSS MARK}")
