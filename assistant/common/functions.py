import asyncio
import json
import logging
from io import StringIO

import aiohttp
import discord
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from .models import EmbeddingEntryExists, GuildSettings

log = logging.getLogger("red.vrt.assistant.functions")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class AssistantFunctions(MixinMeta):
    async def search_internet(
        self, guild: discord.Guild, search_query: str, search_result_amount: int = 10, *args, **kwargs
    ):
        if not self.db.brave_api_key:
            return "Error: Brave API key is not set!"
        url = "https://api.search.brave.com/res/v1/web/search"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.db.brave_api_key,
        }
        params = {
            "q": search_query,
            "country": str(guild.preferred_locale).split("-")[1].lower(),
            "search_lang": str(guild.preferred_locale).split("-")[0],
            "count": search_result_amount,
            "safesearch": "off",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    return f"Error: Unable to fetch results, status code {response.status}"

                data = await response.json()
                tmp = StringIO()

                web = data.get("web", {}).get("results", [])
                if web:
                    tmp.write("# Web Results\n")
                    for result in web:
                        tmp.write(
                            f"## {result.get('title', 'N/A')}\n"
                            f"- Description: {result.get('description', 'N/A')}\n"
                            f"- Link: {result.get('url', 'N/A')}\n"
                            f"- Age: {result.get('age', 'N/A')}\n"
                            f"- Page age: {result.get('page_age', 'N/A')}\n"
                            f"- Source: {result['profile']['long_name']}\n"
                        )

                videos = data.get("videos", {}).get("results", [])
                if videos:
                    tmp.write("# Video Results\n")
                    for video in videos:
                        tmp.write(
                            f"## {video.get('title', 'N/A')}\n"
                            f"- Description: {video.get('description', 'N/A')}\n"
                            f"- URL: {video.get('url', 'N/A')}\n"
                        )

                if not tmp.getvalue():
                    return "No results found"

                return tmp.getvalue()

    async def create_memory(
        self,
        conf: GuildSettings,
        guild: discord.Guild,
        user: discord.Member,
        memory_name: str,
        memory_text: str,
        *args,
        **kwargs,
    ):
        """Create an embedding"""
        if len(memory_name) > 100:
            return "Error: memory_name should be 100 characters or less!"
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
        conf: GuildSettings,
        search_query: str,
        amount: int = 2,
        *args,
        **kwargs,
    ):
        """Search for an embedding"""
        try:
            amount = int(amount)
        except ValueError:
            return "Error: amount must be an integer"
        if amount < 1:
            return "Amount needs to be more than 1"

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
            entry = {"memory name": embed[0], "relatedness": round(embed[2], 2), "content": embed[1]}
            results.append(entry)

        return f"Memories related to `{search_query}`\n{json.dumps(results, indent=2)}"

    async def edit_memory(
        self,
        conf: GuildSettings,
        user: discord.Member,
        memory_name: str,
        memory_text: str,
        *args,
        **kwargs,
    ):
        """Edit an embedding"""
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
        conf.embeddings[memory_name].model = conf.embed_model
        asyncio.create_task(self.save_conf())
        return "Your memory has been updated!"

    async def list_memories(
        self,
        conf: GuildSettings,
        *args,
        **kwargs,
    ):
        """List all embeddings"""
        if not conf.embeddings:
            return "You have no memories available!"
        joined = "\n".join([i for i in conf.embeddings])
        return joined
