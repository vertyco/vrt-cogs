import asyncio
import json
import logging
import typing as t
from base64 import b64decode
from io import BytesIO, StringIO

import aiohttp
import discord
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common import calls, constants, reply
from .models import Conversation, EmbeddingEntryExists, GuildSettings

log = logging.getLogger("red.vrt.assistant.functions")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class AssistantFunctions(MixinMeta):
    async def edit_image(
        self,
        channel: discord.TextChannel,
        conf: GuildSettings,
        prompt: str,
        conversation: Conversation,
        *args,
        **kwargs,
    ):
        """Edit an image using the provided base64 encoded image and prompt."""
        images: list[str] = conversation.get_images()
        if not images:
            return "This conversation has no images to edit!"

        # Each image is formatted like: data:image/jpeg;base64,... so we need to decode it
        if not all(isinstance(image, str) for image in images):
            return "All images must be base64 encoded strings."

        # Extract both the MIME type and image data from the data URI
        image_data = []
        for i, image in enumerate(images[-16:]):  # Limit to the last 16 images
            parts = image.split(",", 1)
            if len(parts) != 2 or not parts[0].startswith("data:"):
                return "Invalid image format. Expected data URI format."

            mime_type = parts[0].split(";")[0].split(":")[1]
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"

            if mime_type not in ["image/jpeg", "image/png", "image/webp"]:
                return f"Unsupported image format: {mime_type}. Supported formats are image/jpeg, image/png, and image/webp."

            # Get the file extension from the MIME type
            extension = mime_type.split("/")[1]
            image_bytes = BytesIO(b64decode(parts[1]))

            # Format as a tuple with (filename, file_data, mime_type)
            image_data.append((f"image{i}.{extension}", image_bytes, mime_type))

        # Pass the image data with the correct format
        image = await calls.request_image_edit_raw(
            prompt=prompt,
            api_key=conf.api_key,
            images=image_data,
            base_url=self.db.endpoint_override,
        )
        color = (await self.bot.get_embed_color(channel)) if channel else discord.Color.blue()
        embed = discord.Embed(color=color).set_image(url="attachment://image.png")

        content = [
            {
                "type": "text",
                "text": _("Here is the edited image, it has been sent to the user!"),
            },
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + image.b64_json, "detail": conf.vision_detail},
            },
        ]

        payload = {
            "embed": embed,
            "content": content,
            "return_null": True,  # The image will be sent and the model will not be re-queried
            "file": discord.File(BytesIO(b64decode(image.b64_json)), filename="image.png"),
        }
        return payload

    async def generate_image(
        self,
        channel: discord.TextChannel,
        conf: GuildSettings,
        prompt: str,
        size: t.Literal["1024x1024", "1792x1024", "1024x1792", "1024x1536", "1536x1024"] = "1024x1024",
        quality: t.Literal["standard", "hd", "low", "medium", "high"] = "medium",
        style: t.Optional[t.Literal["natural", "vivid"]] = "vivid",
        model: t.Literal["dall-e-3", "gpt-image-1"] = "gpt-image-1",
        *args,
        **kwargs,
    ):
        cost_key = f"{quality}{size}"
        cost = constants.IMAGE_COSTS.get(cost_key, 0)

        image = await calls.request_image_raw(
            prompt, conf.api_key, size, quality, style, model, base_url=self.db.endpoint_override
        )

        desc = _("-# Size: {}\n-# Quality: {}\n-# Model: {}").format(size, quality, model)
        if model == "dall-e-3":
            desc += _("\n-# Style: {}").format(style)

        color = (await self.bot.get_embed_color(channel)) if channel else discord.Color.blue()
        embed = (
            discord.Embed(description=desc, color=color)
            .set_image(url="attachment://image.png")
            .set_footer(text=_("Cost: ${}").format(f"{cost:.2f}"))
        )
        txt = "Image has been generated and sent to the user!"
        if hasattr(image, "revised_prompt") and image.revised_prompt:
            embed.add_field(name=_("Revised Prompt"), value=image.revised_prompt)
            txt += f"\n{_('Revised prompt:')} {image.revised_prompt}"

        content = [
            {
                "type": "text",
                "text": txt,
            },
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + image.b64_json, "detail": conf.vision_detail},
            },
        ]

        payload = {
            "embed": embed,
            "content": content,
            "return_null": True,  # The image will be sent and the model will not be re-queried
            "file": discord.File(BytesIO(b64decode(image.b64_json)), filename="image.png"),
        }
        return payload

    async def search_web_brave(
        self,
        guild: discord.Guild,
        query: str,
        num_results: int = 5,
        *args,
        **kwargs,
    ):
        if not self.db.brave_api_key:
            return "Error: Brave API key is not set!"
        url = "https://api.search.brave.com/res/v1/web/search"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.db.brave_api_key,
        }
        locale_parts = str(guild.preferred_locale).split("-")
        country = locale_parts[1].lower() if len(locale_parts) > 1 else "us"
        params = {
            "q": query,
            "country": country,
            "search_lang": str(guild.preferred_locale).split("-")[0],
            "count": num_results,
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
                        )
                        if profile := result.get("profile"):
                            tmp.write(f"- Source: {profile.get('long_name', 'N/A')}\n")

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
        guild: discord.Guild,
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
            guild_id=guild.id,
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
        guild: discord.Guild,
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
        conf.embeddings[memory_name].model = conf.get_embed_model(self.db.endpoint_override)
        await asyncio.to_thread(conf.sync_embeddings, guild.id)
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

    async def respond_and_continue(
        self,
        conf: GuildSettings,
        channel: discord.TextChannel,
        content: str,
        message_obj: discord.Message,
        *args,
        **kwargs,
    ):
        if message_obj is not None:
            await reply.send_reply(message=message_obj, content=content, conf=conf)
        else:
            for p in pagify(content):
                await channel.send(p)
        return "Your message has been sent to the user! You can continue working."
