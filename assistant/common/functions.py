import asyncio
import json
import logging
import typing as t
from base64 import b64decode
from datetime import datetime, timezone
from io import BytesIO, StringIO
from uuid import uuid4

import aiohttp
import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify, text_to_file

from ..abc import MixinMeta
from ..common import calls, constants, reply
from .models import (
    Conversation,
    EmbeddingEntryExists,
    GuildSettings,
    Reminder,
    UserMemory,
)

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
        model: t.Literal["dall-e-3", "gpt-image-1.5"] = "gpt-image-1.5",
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

        if not await self.embedding_store.has_embeddings(guild.id):
            return "There are no memories saved!"

        # Check for exact name match
        exact = await self.embedding_store.get(guild.id, search_query)
        if exact:
            return f"Found a memory name that matches exactly: {exact.get('text', '')}"

        query_embedding = await self.request_embedding(search_query, conf)
        if not query_embedding:
            return f"Failed to get memory for your the query '{search_query}'"

        embeddings = await self.embedding_store.get_related(
            guild_id=guild.id,
            query_embedding=query_embedding,
            top_n=amount,
            min_relatedness=0.5,
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

        if not await self.embedding_store.exists(guild.id, memory_name):
            return "A memory with that name does not exist!"
        embedding = await self.request_embedding(memory_text, conf)
        if not embedding:
            return "Could not update the memory!"

        await self.embedding_store.update(
            guild.id,
            memory_name,
            memory_text,
            embedding,
            conf.embed_model,
        )
        asyncio.create_task(self.save_conf())
        return "Your memory has been updated!"

    async def list_memories(
        self,
        conf: GuildSettings,
        guild: discord.Guild,
        *args,
        **kwargs,
    ):
        """List all embeddings"""
        metadata = await self.embedding_store.get_all_metadata(guild.id)
        if not metadata:
            return "You have no memories available!"
        joined = "\n".join(metadata.keys())
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

    async def fetch_url(self, url: str, *args, **kwargs) -> str:
        """
        Fetch the content of a URL and return the text.

        Args:
            url: The URL to fetch content from

        Returns:
            The text content of the page, or an error message
        """
        log.info(f"Fetching URL: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status not in (200, 201):
                        return f"Failed to fetch URL: HTTP {response.status}"

                    content_type = response.headers.get("Content-Type", "")

                    if "text/html" in content_type:
                        html = await response.text()
                        # Basic HTML to text conversion - strip tags
                        import re

                        # Remove script and style elements
                        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
                        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
                        # Remove HTML tags
                        text = re.sub(r"<[^>]+>", " ", html)
                        # Clean up whitespace
                        text = re.sub(r"\s+", " ", text).strip()
                        # Decode HTML entities
                        import html as html_module

                        text = html_module.unescape(text)
                        # Limit response size
                        if len(text) > 50000:
                            text = text[:50000] + "\n\n[Content truncated...]"
                        return text
                    elif "application/json" in content_type:
                        return await response.text()
                    elif "text/" in content_type:
                        return await response.text()
                    else:
                        return f"Unsupported content type: {content_type}"

        except asyncio.TimeoutError:
            return "Request timed out after 30 seconds"
        except Exception as e:
            log.error(f"Error fetching URL {url}", exc_info=e)
            return f"Failed to fetch URL: {str(e)}"

    async def create_and_send_file(
        self,
        filename: str,
        content: str,
        channel: discord.TextChannel,
        comment: str = None,
        *args,
        **kwargs,
    ) -> str:
        """
        Create a file with the provided content and send it to the Slack conversation.

        Args:
            filename: Name of the file including extension
            content: Content to write to the file
            comment: Optional comment to include when sending the file
            user_id: The ID of the user in the conversation (used for logging)
            channel_id: The ID of the channel where the file will be sent
            client: The Slack API client (passed from main.py)
            initial_response: The initial response message to update with status

        Returns:
            A message confirming the file was sent
        """
        file = text_to_file(content, filename=filename)
        await channel.send(content=comment, file=file)
        return "Success"

    async def create_reminder(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        message: str,
        remind_in: str,
        dm: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Create a reminder for the user."""
        try:
            delta = commands.parse_timedelta(remind_in)
        except commands.BadArgument:
            return f"Could not parse duration from: {remind_in}. Use formats like '30m', '2h', '1d', '1w2d3h'."
        now = datetime.now(tz=timezone.utc)
        remind_at = now + delta

        reminder_id = str(uuid4())[:8]
        reminder = Reminder(
            id=reminder_id,
            guild_id=guild.id,
            channel_id=channel.id,
            user_id=user.id,
            message=message,
            created_at=now,
            remind_at=remind_at,
            dm=dm,
        )
        self.db.reminders[reminder_id] = reminder
        asyncio.create_task(self.save_conf())

        # Schedule with APScheduler
        self.scheduler.add_job(
            self._fire_reminder,
            "date",
            run_date=remind_at,
            args=[reminder_id],
            id=f"reminder_{reminder_id}",
            replace_existing=True,
        )

        timestamp = int(remind_at.timestamp())
        return f"Reminder created! ID: `{reminder_id}`. I'll remind you <t:{timestamp}:R> (<t:{timestamp}:f>)."

    async def cancel_reminder(
        self,
        guild: discord.Guild,
        user: discord.Member,
        reminder_id: str,
        *args,
        **kwargs,
    ) -> str:
        """Cancel an existing reminder."""
        reminder = self.db.reminders.get(reminder_id)
        if not reminder:
            return f"No reminder found with ID `{reminder_id}`."
        if reminder.user_id != user.id:
            return "You can only cancel your own reminders."

        # Remove from scheduler
        job_id = f"reminder_{reminder_id}"
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()

        # Remove from storage
        del self.db.reminders[reminder_id]
        asyncio.create_task(self.save_conf())
        return f"Reminder `{reminder_id}` has been cancelled."

    async def list_reminders(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ) -> str:
        """List all pending reminders for the user."""
        user_reminders = [r for r in self.db.reminders.values() if r.user_id == user.id]
        if not user_reminders:
            return "You have no pending reminders."

        user_reminders.sort(key=lambda r: r.remind_at)
        lines = []
        for r in user_reminders:
            timestamp = int(r.remind_at.timestamp())
            dm_indicator = " (DM)" if r.dm else ""
            lines.append(
                f"- `{r.id}`: <t:{timestamp}:R> - {r.message[:50]}{'...' if len(r.message) > 50 else ''}{dm_indicator}"
            )

        return "**Your reminders:**\n" + "\n".join(lines)

    def _get_user_memory_key(self, guild_id: int, user_id: int) -> str:
        """Get the key for storing user memory."""
        return f"{guild_id}-{user_id}"

    async def remember_user(
        self,
        guild: discord.Guild,
        user: discord.Member,
        fact: str,
        *args,
        **kwargs,
    ) -> str:
        """Remember a fact about the user."""
        key = self._get_user_memory_key(guild.id, user.id)
        if key not in self.db.user_memories:
            self.db.user_memories[key] = UserMemory(
                user_id=user.id,
                guild_id=guild.id,
            )

        memory = self.db.user_memories[key]
        memory.facts.append(fact)
        memory.updated_at = datetime.now(tz=timezone.utc)
        asyncio.create_task(self.save_conf())
        return f"I'll remember that about {user.display_name}: {fact}"

    async def recall_user(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ) -> str:
        """Retrieve all remembered facts about the user."""
        key = self._get_user_memory_key(guild.id, user.id)
        memory = self.db.user_memories.get(key)
        if not memory or not memory.facts:
            return f"I don't have any stored facts about {user.display_name}."

        lines = [f"{i + 1}. {fact}" for i, fact in enumerate(memory.facts)]
        return f"**Known facts about {user.display_name}:**\n" + "\n".join(lines)

    async def forget_user(
        self,
        guild: discord.Guild,
        user: discord.Member,
        fact_index_or_text: str,
        *args,
        **kwargs,
    ) -> str:
        """Remove a specific fact from the user's memory."""
        key = self._get_user_memory_key(guild.id, user.id)
        memory = self.db.user_memories.get(key)
        if not memory or not memory.facts:
            return f"I don't have any stored facts about {user.display_name}."

        # Try to parse as an index first
        try:
            index = int(fact_index_or_text) - 1  # Convert to 0-based index
            if 0 <= index < len(memory.facts):
                removed_fact = memory.facts.pop(index)
                memory.updated_at = datetime.now(tz=timezone.utc)
                asyncio.create_task(self.save_conf())
                return f"Removed fact: {removed_fact}"
            return f"Invalid index. Please use a number between 1 and {len(memory.facts)}."
        except ValueError:
            pass

        # Try to match by text
        for i, fact in enumerate(memory.facts):
            if fact_index_or_text.lower() in fact.lower():
                removed_fact = memory.facts.pop(i)
                memory.updated_at = datetime.now(tz=timezone.utc)
                asyncio.create_task(self.save_conf())
                return f"Removed fact: {removed_fact}"

        return f"Could not find a fact matching '{fact_index_or_text}'."
