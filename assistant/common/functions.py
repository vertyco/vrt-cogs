import asyncio
import inspect
import logging
import typing as t
from base64 import b64decode
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from uuid import uuid4

import aiohttp
import discord
import openai
import pytz
from dateutil import parser as dateutil_parser
from duckduckgo_search import DDGS
from rapidfuzz import fuzz, process
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify

from ..abc import MixinMeta
from ..common import calls, reply
from ..views import SkillProposalView
from .command_index import (
    build_command_documents,
    collection_name_for_model,
    fuzzy_search_commands,
    get_privilege_hint,
    member_can_run,
)
from .command_ui import expand_command_ui_source
from .constants import MAX_SKILL_BODY
from .models import (
    Conversation,
    GuildSettings,
    Reminder,
    ScheduledTask,
    Skill,
    member_meets_level,
)
from .utils import find_similar_skill, normalize_skill_name

log = logging.getLogger("red.vrt.assistant.functions")
_ = Translator("Assistant", __file__)


def parse_time_input(time_str: str, timezone_str: str = "UTC") -> datetime | None:
    """Parse a time input string as either a relative duration or an absolute datetime.

    Supports:
    - Relative durations: '30m', '2h', '1d', '1w2d3h', '5 minutes'
    - ISO format: '2024-08-04T15:00:00', '2024-08-04'
    - Humanized datetimes: 'august 4th 3:00pm', '6pm', 'december 25 2024'

    Args:
        time_str: The time string to parse.
        timezone_str: IANA timezone name used to interpret naive datetimes (default: UTC).

    Returns a timezone-aware UTC datetime, or None if parsing fails.
    """
    now = datetime.now(tz=timezone.utc)

    # Try relative duration first (e.g., "30m", "2h", "1d3h")
    try:
        delta = commands.parse_timedelta(time_str)
        if delta is not None:
            return now + delta
    except commands.BadArgument:
        pass

    # Try absolute datetime parsing (e.g., "august 4th 3:00pm", "6pm", ISO format)
    try:
        parsed = dateutil_parser.parse(time_str, fuzzy=True)
        if parsed.tzinfo is None:
            # Interpret naive datetimes in the configured guild timezone
            try:
                tz = pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
            parsed = tz.localize(parsed)
        # Normalise to UTC
        parsed = parsed.astimezone(timezone.utc)
        # If parsed time is in the past and less than 24h ago, assume user meant next occurrence
        # This handles cases like "6pm" when it's already past 6pm today
        if parsed <= now and (now - parsed).total_seconds() < 86400:
            parsed += timedelta(days=1)
        return parsed
    except (ValueError, OverflowError, TypeError):
        pass

    return None


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
        try:
            image = await calls.request_image_edit_raw(
                prompt=prompt,
                api_key=self.get_api_key(conf),
                images=image_data,
                base_url=conf.endpoint_override or self.db.endpoint_override,
            )
        except (openai.NotFoundError, openai.BadRequestError):
            if conf.endpoint_override or self.db.endpoint_override:
                return calls.get_custom_endpoint_image_error()
            raise
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
        try:
            image = await calls.request_image_raw(
                prompt,
                self.get_api_key(conf),
                size,
                quality,
                style,
                model,
                base_url=conf.endpoint_override or self.db.endpoint_override,
            )
        except (openai.NotFoundError, openai.BadRequestError):
            if conf.endpoint_override or self.db.endpoint_override:
                return calls.get_custom_endpoint_image_error()
            raise

        desc = _("-# Size: {}\n-# Quality: {}\n-# Model: {}").format(size, quality, model)
        if model == "dall-e-3":
            desc += _("\n-# Style: {}").format(style)

        color = (await self.bot.get_embed_color(channel)) if channel else discord.Color.blue()
        embed = discord.Embed(description=desc, color=color).set_image(url="attachment://image.png")
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

    async def _search_brave(
        self,
        guild: discord.Guild,
        query: str,
        num_results: int = 5,
    ) -> str | None:
        """Search using Brave API. Returns None if API key is not set or request fails."""
        if not self.db.brave_api_key:
            return None

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        log.warning(f"Brave search failed with status {response.status}, falling back to DuckDuckGo")
                        return None

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

                    result = tmp.getvalue()
                    if not result:
                        return None
                    return result
        except Exception as e:
            log.warning(f"Brave search error: {e}, falling back to DuckDuckGo")
            return None

    async def _search_duckduckgo(self, query: str, num_results: int = 5) -> str:
        """Search using DuckDuckGo. Fallback option that doesn't require an API key."""

        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))

        try:
            res: list[dict] = await asyncio.to_thread(_search)
            if not res:
                return "No results found"

            tmp = StringIO()
            tmp.write("# Web Results\n")
            for result in res:
                tmp.write(
                    f"## {result.get('title', 'N/A')}\n"
                    f"- Description: {result.get('body', 'N/A')}\n"
                    f"- Link: {result.get('href', 'N/A')}\n"
                )
            return tmp.getvalue()
        except Exception as e:
            log.error(f"DuckDuckGo search error: {e}")
            return f"Error: Search failed - {e}"

    async def search_web_brave(
        self,
        guild: discord.Guild,
        query: str,
        num_results: int = 5,
        *args,
        **kwargs,
    ):
        """
        Search the web for information. Uses Brave Search API if configured,
        otherwise falls back to DuckDuckGo.
        """
        # Try Brave first if API key is set
        result = await self._search_brave(guild, query, num_results)
        if result:
            return result

        # Fallback to DuckDuckGo
        return await self._search_duckduckgo(query, num_results)

    async def search_commands(
        self,
        guild: discord.Guild,
        conf: GuildSettings,
        query: str,
        user: discord.Member = None,
        *args,
        **kwargs,
    ) -> str:
        try:
            return await self.semantic_command_search(conf, query, user)
        except Exception as e:
            log.warning(f"Semantic command search failed, using fuzzy fallback: {e}")
            hits = await asyncio.to_thread(fuzzy_search_commands, self.bot, query)
            return await self.format_command_search_results(hits, user, semantic=False)

    async def semantic_command_search(self, conf: GuildSettings, query: str, user: discord.Member) -> str:
        embedding = await self.request_embedding(query, conf)
        model = self.resolve_embedding_model(conf.embed_model, conf)
        collection = collection_name_for_model(model)
        if await self.command_index.count(collection) == 0:
            await self.build_command_index(conf, model)
        hits = await self.command_index.query(collection, embedding, top_k=8)
        return await self.format_command_search_results(hits, user, semantic=True)

    async def format_command_search_results(
        self,
        hits: list[tuple[str, str, float]],
        user: discord.Member,
        semantic: bool,
    ) -> str:
        if not hits:
            return "No matching commands found."
        buffer = StringIO()
        if not semantic:
            buffer.write("NOTE: Semantic search unavailable. Results are fuzzy name matches.\n\n")
        for qualified_name, text, score in hits:
            command = self.bot.get_command(qualified_name)
            if command is None:
                continue
            if isinstance(user, discord.Member):
                runnable = await member_can_run(self.bot, command, user)
                annotation = (
                    "the user CAN run this" if runnable else f"the user CANNOT run this ({get_privilege_hint(command)})"
                )
            else:
                annotation = get_privilege_hint(command)
            buffer.write(f"## {qualified_name} (relevance: {round(score, 3)})\n{text}\nPermission: {annotation}\n\n")
        return buffer.getvalue().strip() or "No matching commands found."

    async def get_command_source(self, command_name: str, follow_ui: bool = False, *args, **kwargs) -> str:
        command = self.bot.get_command(command_name)
        note = ""
        if command is None:
            names = [c.qualified_name for c in self.bot.walk_commands()]
            match = process.extractOne(command_name, names, scorer=fuzz.WRatio, score_cutoff=70)
            if not match:
                return f"No command found matching '{command_name}'"
            command = self.bot.get_command(match[0])
            if command is None:
                return f"No command found matching '{command_name}'"
            note = f"NOTE: No exact match for '{command_name}', showing closest match.\n"
        if follow_ui:
            expanded = await asyncio.to_thread(expand_command_ui_source, command)
            return f"{note}{expanded}"
        try:
            source = inspect.getsource(command.callback)
        except (OSError, TypeError) as e:
            return f"Could not fetch source for '{command.qualified_name}': {e}"
        if len(source) > 6000:
            source = source[:6000] + "\n# ... truncated ..."
        return f"{note}Source for [p]{command.qualified_name}:\n```python\n{source}\n```"

    async def build_command_index(self, conf: GuildSettings, model: str) -> None:
        """Full (re)build of one model's command index collection. Batched embedding calls."""
        documents = await asyncio.to_thread(build_command_documents, self.bot)
        names = list(documents)
        texts = [documents[name]["text"] for name in names]
        embeddings, observed = await self.request_embeddings_batch(texts, conf)
        collection = collection_name_for_model(model)
        entries = [{"qualified_name": name, **documents[name]} for name in names]
        await self.command_index.upsert(collection, entries, embeddings)
        log.info(f"Built command index {collection} with {len(entries)} commands (model: {observed})")

    def schedule_command_index_sync(self) -> None:
        """Debounce sync so startup cog-load bursts coalesce into one pass."""
        if self.cmdindex_task and not self.cmdindex_task.done():
            self.cmdindex_task.cancel()
        self.cmdindex_task = asyncio.create_task(self.command_index_sync_runner())

    async def command_index_sync_runner(self) -> None:
        try:
            await asyncio.sleep(30)
            await self.sync_command_index()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("Command index sync failed", exc_info=e)

    async def sync_command_index(self) -> None:
        documents = await asyncio.to_thread(build_command_documents, self.bot)
        for collection in await self.command_index.list_collections():
            await self.sync_command_index_collection(collection, documents)

    async def sync_command_index_collection(self, collection: str, documents: dict[str, dict]) -> None:
        existing = await self.command_index.get_hashes(collection)
        stale = [name for name in existing if name not in documents]
        changed = [name for name, data in documents.items() if existing.get(name) != data["hash"]]
        await self.command_index.delete_ids(collection, stale)
        if not changed:
            if stale:
                log.info(f"Command index {collection}: removed {len(stale)} stale entries")
            return
        conf = self.find_conf_for_collection(collection)
        if conf is None:
            log.info(f"No guild config matches {collection}, dropping it for lazy rebuild on next search")
            await self.command_index.drop(collection)
            return
        texts = [documents[name]["text"] for name in changed]
        embeddings, observed = await self.request_embeddings_batch(texts, conf)
        entries = [{"qualified_name": name, **documents[name]} for name in changed]
        await self.command_index.upsert(collection, entries, embeddings)
        log.info(f"Command index {collection}: updated {len(changed)}, removed {len(stale)} (model: {observed})")

    def find_conf_for_collection(self, collection: str) -> t.Optional[GuildSettings]:
        """Find a guild whose configured embedding model maps to this collection and has an API key."""
        for conf in self.db.configs.values():
            if not self.get_api_key(conf):
                continue
            model = self.resolve_embedding_model(conf.embed_model, conf)
            if collection_name_for_model(model) == collection:
                return conf
        return None

    async def respond_and_continue(
        self,
        conf: GuildSettings,
        channel: discord.TextChannel,
        content: str,
        message_obj: discord.Message,
        user: discord.Member = None,
        *args,
        **kwargs,
    ):
        allowed_mentions = await self.get_mention_permissions(user) if user else discord.AllowedMentions.none()
        if message_obj is not None:
            await reply.send_reply(
                message=message_obj,
                content=content,
                conf=conf,
                allowed_mentions=allowed_mentions,
                include_think_files=self.db.reasoning_as_files,
            )
        else:
            for p in pagify(content):
                await channel.send(p, allowed_mentions=allowed_mentions)
        return "Your message has been sent to the user! You can continue working."

    async def think_and_plan(
        self,
        task_summary: str,
        steps: list[str],
        considerations: str = None,
        *args,
        **kwargs,
    ) -> str:
        """
        Break down a complex task into smaller steps for planning purposes.
        This tool helps the model organize its approach before executing.

        Args:
            task_summary: Brief summary of the overall task
            steps: Ordered list of steps to complete the task
            considerations: Optional notes about edge cases or issues

        Returns:
            A short acknowledgment so the structured reasoning is captured
            in the tool call arguments without duplicating it in the result.
        """
        # Per-call gating instead of dynamic tool-list pruning so the advertised
        # tool schema stays byte-stable across requests (provider prompt caches
        # invalidate the cached prefix when tool definitions drift between
        # turns - see https://developers.openai.com/api/docs/guides/prompt-caching).
        conf: t.Optional[GuildSettings] = kwargs.get("conf")
        user: t.Optional[discord.Member] = kwargs.get("user")
        if conf and conf.planners and isinstance(user, discord.Member):
            allowed_ids = set(conf.planners)
            if user.id not in allowed_ids and not any(role.id in allowed_ids for role in user.roles):
                return (
                    "This tool is restricted to designated planners in this server. "
                    "Proceed without it - reason about the task in your own response."
                )
        return "Plan noted."

    async def create_reminder(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        conf: GuildSettings,
        message: str,
        remind_in: str,
        dm: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Create a reminder for the user."""
        remind_at = parse_time_input(remind_in, timezone_str=conf.timezone)
        if remind_at is None:
            return f"Could not parse time from: {remind_in}. Use a duration like '30m', '2h', '1d' or an ISO datetime like '2025-08-04T15:00:00'."
        now = datetime.now(tz=timezone.utc)
        if remind_at <= now:
            return "The specified time is in the past. Please provide a future time."

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
        time_until = humanize_timedelta(timedelta=(remind_at - now))
        response = f"Reminder created! (ID: {reminder_id}). Triggers in: {time_until}. Discord Format: <t:{timestamp}:R> (<t:{timestamp}:f>)"
        return response

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

    # -------------------------------------------------------
    # --------------- SCHEDULED TASKS -----------------------
    # -------------------------------------------------------
    async def schedule_task(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        conf: GuildSettings,
        instruction: str,
        execute_in: str,
        context: str = "",
        *args,
        **kwargs,
    ) -> str:
        """Schedule an autonomous task for future execution."""
        # Check user's task limit
        user_task_count = sum(
            1 for t in self.db.scheduled_tasks.values() if t.user_id == user.id and t.guild_id == guild.id
        )
        if user_task_count >= conf.max_scheduled_tasks:
            return f"You have reached the maximum of {conf.max_scheduled_tasks} scheduled tasks. Cancel some before scheduling more."

        execute_at = parse_time_input(execute_in, timezone_str=conf.timezone)
        if execute_at is None:
            return f"Could not parse time from: {execute_in}. Use a duration like '30m', '2h', '1d' or an ISO datetime like '2025-08-04T15:00:00'."

        now = datetime.now(tz=timezone.utc)
        if execute_at <= now:
            return "The specified time is in the past. Please provide a future time."

        task_id = str(uuid4())[:8]
        task = ScheduledTask(
            id=task_id,
            guild_id=guild.id,
            channel_id=channel.id,
            user_id=user.id,
            instruction=instruction,
            context=context,
            created_at=now,
            execute_at=execute_at,
        )
        self.db.scheduled_tasks[task_id] = task
        asyncio.create_task(self.save_conf())

        # Schedule with APScheduler
        self.scheduler.add_job(
            self._fire_scheduled_task,
            "date",
            run_date=execute_at,
            args=[task_id],
            id=f"task_{task_id}",
            replace_existing=True,
        )

        timestamp = int(execute_at.timestamp())
        return f"Task scheduled! ID: `{task_id}`. I'll execute it <t:{timestamp}:R> (<t:{timestamp}:f>)."

    async def cancel_scheduled_task(
        self,
        guild: discord.Guild,
        user: discord.Member,
        task_id: str,
        *args,
        **kwargs,
    ) -> str:
        """Cancel a scheduled task."""
        task = self.db.scheduled_tasks.get(task_id)
        if not task:
            return f"No scheduled task found with ID `{task_id}`."
        if task.user_id != user.id:
            return "You can only cancel your own scheduled tasks."
        if task.guild_id != guild.id:
            return "That task belongs to a different server."

        # Remove from scheduler
        job_id = f"task_{task_id}"
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()

        # Remove from storage
        del self.db.scheduled_tasks[task_id]
        asyncio.create_task(self.save_conf())
        return f"Scheduled task `{task_id}` has been cancelled."

    async def list_scheduled_tasks(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ) -> str:
        """List all pending scheduled tasks for the user."""
        user_tasks = [
            utask
            for utask in self.db.scheduled_tasks.values()
            if utask.user_id == user.id and utask.guild_id == guild.id
        ]
        if not user_tasks:
            return "You have no pending scheduled tasks."

        user_tasks.sort(key=lambda utask: utask.execute_at)
        lines = []
        for utask in user_tasks:
            timestamp = int(utask.execute_at.timestamp())
            instruction_preview = utask.instruction[:60] + ("..." if len(utask.instruction) > 60 else "")
            lines.append(f"- `{utask.id}`: <t:{timestamp}:R> - {instruction_preview}")

        return "**Your scheduled tasks:**\n" + "\n".join(lines)

    def bake_skill(
        self,
        conf: GuildSettings,
        name: str,
        description: str,
        body: str,
        permission_level: str = "user",
        source: str = "manual",
        author_id: int = 0,
        approver_id: int = 0,
        source_message: str = "",
        replaces: str = "",
    ) -> Skill:
        """Create or update an active skill. Caller is responsible for save_conf()."""
        key = replaces or name
        existing = conf.skills.get(key)
        if existing:
            existing.description = description
            existing.body = body
            existing.permission_level = permission_level
            existing.status = "active"
            existing.approver_id = approver_id or existing.approver_id
            if source_message:
                existing.source_message = source_message
            existing.touch()
            if replaces and name and name != replaces and name not in conf.skills:
                conf.skills[name] = conf.skills.pop(replaces)
            return existing
        skill = Skill(
            description=description,
            body=body,
            permission_level=permission_level,
            source=source,
            author_id=author_id,
            approver_id=approver_id,
            source_message=source_message,
        )
        conf.skills[key] = skill
        return skill

    async def load_skill(
        self,
        skill_name: str,
        guild: discord.Guild = None,
        conf: GuildSettings = None,
        user: discord.Member = None,
        *args,
        **kwargs,
    ) -> str:
        if not conf or not conf.skills_enabled:
            return "Skills are disabled in this server."
        skill_name = normalize_skill_name(skill_name)
        skill = conf.skills.get(skill_name)
        if not skill or skill.status != "active" or not skill.enabled:
            visible = [
                name
                for name, s in sorted(conf.skills.items())
                if s.enabled and s.status == "active" and await member_meets_level(self.bot, user, s.permission_level)
            ]
            names = ", ".join(visible) if visible else "none"
            return f"No active skill named '{skill_name}'. Available skills: {names}"
        if not await member_meets_level(self.bot, user, skill.permission_level):
            return f"The current user does not have permission to use the '{skill_name}' skill."
        skill.mark_used()
        await self.save_conf()
        return f"Skill '{skill_name}' loaded. Follow this procedure:\n\n{skill.body}"

    async def skill_proposal_allowed(self, conf: GuildSettings, user: discord.Member) -> t.Tuple[bool, bool]:
        """Returns (allowed, is_admin) for the proposing context."""
        is_admin = await member_meets_level(self.bot, user, "admin")
        if is_admin:
            return conf.skill_admin_mode in ("propose", "auto"), True
        return conf.skill_propose_users, False

    async def post_skill_proposal(
        self, guild: discord.Guild, conf: GuildSettings, proposal: dict, fallback_channel=None
    ) -> str:
        """Post the proposal panel. Routes to the configured review channel when set,
        otherwise falls back to the current chat channel so proposals work out of the box."""
        channel = guild.get_channel(conf.skill_channel) if conf.skill_channel else None
        if not isinstance(channel, discord.abc.Messageable):
            channel = fallback_channel
        if not isinstance(channel, discord.abc.Messageable):
            return (
                "There is nowhere to post the skill proposal (no review channel configured and no "
                "current channel available). Tell the user an admin can set one with the "
                "`assistant skills channel` command."
            )
        view = SkillProposalView(self, guild, proposal, ping_roles=conf.skill_ping_roles)
        allowed = discord.AllowedMentions(roles=True)
        view.message = await channel.send(view=view, allowed_mentions=allowed)
        return (
            f"Skill proposal '{proposal['name']}' submitted for staff review in {channel.mention}. "
            "It will not take effect unless approved."
        )

    async def propose_skill(
        self,
        skill_name: str,
        description: str,
        body: str,
        reason: str,
        replaces: str = "",
        guild: discord.Guild = None,
        conf: GuildSettings = None,
        user: discord.Member = None,
        channel: discord.abc.GuildChannel = None,
        message_obj: discord.Message = None,
        *args,
        **kwargs,
    ) -> str:
        skill_name = normalize_skill_name(skill_name)
        replaces = normalize_skill_name(replaces)
        if not conf or not conf.skills_enabled:
            return "Skills are disabled in this server."
        if len(body) > MAX_SKILL_BODY:
            return f"Skill body too long ({len(body)} chars, max {MAX_SKILL_BODY}). Shorten it."
        if replaces and replaces not in conf.skills:
            return f"No skill named '{replaces}' exists to replace. Check the Skills index for the exact name."
        if not replaces and len(conf.skills) >= conf.max_skills:
            return "This server has reached its skill limit. Propose an update to an existing skill instead."
        if not replaces:
            similar = find_similar_skill(description, conf.skills)
            if similar:
                return (
                    f"An existing skill '{similar}' covers similar ground. Call propose_skill again "
                    f"with replaces='{similar}' to propose an update to it instead."
                )
        allowed, is_admin = await self.skill_proposal_allowed(conf, user)
        if not allowed:
            return "Skill proposals are not enabled for this type of user. Do not retry."
        proposal = {
            "name": skill_name,
            "description": description.strip(),
            "body": body,
            "reason": reason,
            "replaces": replaces,
            "permission_level": conf.skills[replaces].permission_level if replaces else "user",
            "author_id": user.id if user else 0,
            "source_message": message_obj.jump_url if message_obj else "",
        }
        if is_admin and conf.skill_admin_mode == "auto":
            self.bake_skill(
                conf=conf,
                name=skill_name,
                description=proposal["description"],
                body=body,
                permission_level=proposal["permission_level"],
                source="correction",
                author_id=proposal["author_id"],
                approver_id=proposal["author_id"],
                source_message=proposal["source_message"],
                replaces=replaces,
            )
            await self.save_conf()
            return f"Skill '{replaces or skill_name}' saved and active immediately (admin auto mode)."
        return await self.post_skill_proposal(guild, conf, proposal, fallback_channel=channel)
