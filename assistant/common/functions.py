import asyncio
import json
import logging
import string
from typing import Union

import discord
from rapidfuzz import fuzz
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from .models import EmbeddingEntryExists
from .utils import clean_name

log = logging.getLogger("red.vrt.assistant.functions")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class AssistantFunctions(MixinMeta):
    async def create_memory(
        self,
        guild: discord.Guild,
        user: discord.Member,
        memory_name: str,
        memory_text: str,
        *args,
        **kwargs,
    ):
        if len(memory_name) > 100:
            return "Error: memory_name should be 100 characters or less!"
        conf = self.db.get_conf(guild)
        if not any([role.id in conf.tutors for role in user.roles]) and user.id not in conf.tutors:
            return f"User {user.display_name} is not recognized as a tutor!"
        try:
            embedding = await self.add_embedding(
                guild,
                memory_name,
                memory_text,
                overwrite=False,
                ai_created=True,
            )
            if embedding is None:
                return "Failed to create memory"
            return f"The memory '{memory_name}' has been created successfully"
        except EmbeddingEntryExists:
            return "That memory name already exists"

    async def search_memories(
        self,
        guild: discord.Guild,
        search_query: str,
        amount: int = 2,
        *args,
        **kwargs,
    ):
        try:
            amount = int(amount)
        except ValueError:
            return "Error: amount must be an integer"
        if amount < 1:
            return "Amount needs to be more than 1"

        conf = self.db.get_conf(guild)
        if not conf.embeddings:
            return "There are no memories saved!"

        if search_query in conf.embeddings:
            embed = conf.embeddings[search_query]
            return f"Found a memory name that matches exactly: {embed.text}"

        query_embedding = await self.request_embedding(search_query, conf)
        if not query_embedding:
            return f"Failed to get memory for your the query '{search_query}'"

        embeddings = await asyncio.to_thread(
            conf.get_related_embeddings,
            query_embedding=query_embedding,
            top_n_override=amount,
            relatedness_override=0.5,
        )
        if not embeddings:
            return f"No embeddings could be found related to the search query '{search_query}'"

        results = []
        for embed in embeddings:
            entry = {"memory name": embed[0], "relatedness": embed[2], "content": embed[1]}
            results.append(entry)

        return f"Memories related to `{search_query}`\n{json.dumps(results, indent=2)}"

    async def edit_memory(
        self,
        guild: discord.Guild,
        user: discord.Member,
        memory_name: str,
        memory_text: str,
        *args,
        **kwargs,
    ):
        conf = self.db.get_conf(guild)
        if not any([role.id in conf.tutors for role in user.roles]) and user.id not in conf.tutors:
            return f"User {user.display_name} is not recognized as a tutor!"

        if memory_name not in conf.embeddings:
            return "A memory with that name does not exist!"
        embedding = await self.request_embedding(memory_text, conf)
        if not embedding:
            return "Could not update the memory!"

        conf.embeddings[memory_name].text = memory_text
        conf.embeddings[memory_name].embedding = embedding
        conf.embeddings[memory_name].update()
        asyncio.create_task(self.save_conf())
        return "Your memory has been updated!"

    async def get_channel_name_from_id(
        self,
        guild: discord.Guild,
        channel_id: Union[str, int],
        user: discord.Member,
        *args,
        **kwargs,
    ):
        if isinstance(channel_id, str):
            if not channel_id.isdigit():
                return "channel_id must be a valid integer!"
        if channel := guild.get_channel_or_thread(int(channel_id)):
            if not channel.permissions_for(user).view_channel:
                return "The user you are chatting with doesnt have permission to view that channel"
            ctype = "voice" if isinstance(channel, discord.VoiceChannel) else "text"
            return f"the name of the {ctype} channel with ID {channel_id} is {channel.name}"
        return "a channel with that ID could not be found!"

    async def get_channel_id_from_name(
        self,
        guild: discord.Guild,
        channel_name: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        channels = list(guild.channels) + list(guild.threads) + list(guild.forums)
        valid_channels = [i for i in channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        matches = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name:
                return channel.mention
            if channel.name == channel_name:
                return channel.mention
            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

        if not matches:
            return "No channels found with that name or id!"

        matches.sort(key=lambda x: x[1], reverse=True)
        return str(matches[0][0].id)

    async def get_channel_mention(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        channels = list(guild.channels) + list(guild.threads) + list(guild.forums)
        valid_channels = [i for i in channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        matches = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name_or_id:
                return channel.mention
            if channel.name == channel_name_or_id:
                return channel.mention
            if str(channel.id) == channel_name_or_id:
                return channel.mention
            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name_or_id.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

            id_score = fuzz.ratio(str(channel.id), channel_name_or_id)
            if id_score > 90:
                matches.append((channel, id_score))

        if not matches:
            return "No channels found with that name or id!"

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0].mention

    async def get_channel_list(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = [i for i in guild.channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"
        txt = ""
        for channel in valid_channels:
            txt += f"{clean_name(channel.name)}\n"
        return txt

    async def get_channel_topic(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = [i for i in guild.channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        matches: list[discord.TextChannel] = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name_or_id:
                return channel.mention
            if channel.name == channel_name_or_id:
                return channel.mention
            if str(channel.id) == channel_name_or_id:
                return channel.mention
            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name_or_id.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

            id_score = fuzz.ratio(str(channel.id), channel_name_or_id)
            if id_score > 90:
                matches.append((channel, id_score))

        if not matches:
            return "No channels found with that name or id!"

        matches = [i for i in matches if i.topic]
        if not matches:
            return "No channels found with a topic!"

        matches.sort(key=lambda x: x[1], reverse=True)
        txt = ""
        for channel in valid_channels:
            txt += f"{clean_name(channel.name)}\n"
        return txt

    async def make_search_url(
        self,
        site: str,
        search_query: str,
        *args,
        **kwargs,
    ):
        site = site.lower()
        chars = string.ascii_letters + string.hexdigits
        for char in search_query:
            if char not in chars:
                search_query = search_query.replace(char, "")
        search_query = search_query.replace(" ", "+")
        if site == "youtube":
            return f"https://www.youtube.com/results?search_query={search_query}"
        return f"https://www.google.com/search?q={search_query}"

    async def get_user_from_id(
        self,
        guild: discord.Guild,
        discord_id: int,
        *args,
        **kwargs,
    ):
        member = guild.get_member(int(discord_id))
        if not member:
            return "A member with that ID does not exist!"
        return member.name
