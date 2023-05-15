import asyncio
import logging
from datetime import datetime

import discord
from aiocache import cached
from redbot.core.utils.chat_formatting import humanize_list

from .abc import MixinMeta
from .common.utils import get_chat, get_embedding
from .models import Conversation, GuildSettings

log = logging.getLogger("red.vrt.assistant.api")


class API(MixinMeta):
    @cached(ttl=120)
    async def get_chat_response(
        self, message: str, author: discord.Member, conf: GuildSettings
    ) -> str:
        conversation = self.chats.get_conversation(author)
        try:
            reply = await asyncio.to_thread(self.prepare_call, message, author, conf, conversation)
        finally:
            conversation.cleanup(conf)
        return reply

    def prepare_call(
        self,
        message: str,
        author: discord.Member,
        conf: GuildSettings,
        conversation: Conversation,
    ) -> str:
        timestamp = f"<t:{round(datetime.now().timestamp())}:F>"
        created = f"<t:{round(author.guild.created_at.timestamp())}:F>"
        date = datetime.now().astimezone().strftime("%B %d, %Y")
        time = datetime.now().astimezone().strftime("%I:%M %p %Z")
        roles = [role.name for role in author.roles]
        params = {
            "botname": self.bot.user.name,
            "timestamp": timestamp,
            "date": date,
            "time": time,
            "members": author.guild.member_count,
            "user": author.display_name,
            "datetime": str(datetime.now()),
            "roles": humanize_list(roles),
            "avatar": author.avatar.url if author.avatar else "",
            "owner": author.guild.owner,
            "servercreated": created,
            "server": author.guild.name,
            "messages": len(conversation.messages),
            "tokens": conversation.token_count(conf, message),
            "retention": conf.max_retention,
            "retentiontime": conf.max_retention_time,
        }

        system_prompt = conf.system_prompt.format(**params)
        initial_prompt = conf.prompt.format(**params)

        query_embedding = get_embedding(text=message, key=conf.api_key)
        embeddings = conf.get_related_embeddings(query_embedding)
        if embeddings:
            initial_prompt += "\nContext:\n"
            for i in embeddings:
                initial_prompt += f"{i[0]}\n"

        conversation.update_messages(conf, message, "user")
        messages = conversation.prepare_chat(system_prompt, initial_prompt)
        reply = get_chat(model=conf.model, messages=messages, temperature=0, api_key=conf.api_key)
        conversation.update_messages(conf, reply, "assistant")
        return reply
