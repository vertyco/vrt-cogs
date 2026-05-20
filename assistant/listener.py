import asyncio
import functools
import logging
import multiprocessing as mp
import re
import typing as t
from collections import deque
from dataclasses import dataclass, field

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .common.utils import can_use, embed_to_content, is_question

log = logging.getLogger("red.vrt.assistant.listener")
_ = Translator("Assistant", __file__)


@dataclass
class _ResponseState:
    """Tracks pending requests for a single conversation queue."""

    pending: deque[dict[str, t.Any]] = field(default_factory=deque)
    worker: asyncio.Task[None] | None = None

    MAX_QUEUE_DEPTH: int = 10  # Drop further messages beyond this depth


class AssistantListener(MixinMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # {(conversation_owner_id, channel_id, guild_id): _ResponseState}
        self._response_state: dict[tuple[int, int, int], _ResponseState] = {}

    async def safe_regex_search(self, pattern: str, content: str) -> bool:
        """Safely check if a regex pattern matches content using multiprocessing pool for timeout."""
        try:
            # Use re.findall which returns a list (picklable) instead of re.search which returns a Match (not picklable)
            process = self.mp_pool.apply_async(
                re.findall,
                args=(pattern, content, re.IGNORECASE),
            )
            task = functools.partial(process.get, timeout=2)
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
            result = await asyncio.wait_for(new_task, timeout=5)
            return len(result) > 0
        except (asyncio.TimeoutError, mp.TimeoutError):
            log.warning(f"Regex pattern '{pattern}' took too long to process")
            return False
        except Exception as e:
            log.error(f"Error checking regex pattern: {e}")
            return False

    async def matches_trigger(self, content: str, trigger_phrases: t.List[str]) -> bool:
        """Check if the message content matches any trigger phrase (regex patterns)."""
        for pattern in trigger_phrases:
            if await self.safe_regex_search(pattern, content):
                return True
        return False

    def get_message_queue_key(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> tuple[int, int, int]:
        conversation_owner_id = channel_id if collaborative else author_id
        return (conversation_owner_id, channel_id, guild_id)

    async def enqueue_message_request(self, handle_message_kwargs: dict[str, t.Any]) -> bool:
        message: discord.Message = handle_message_kwargs["message"]
        conf = handle_message_kwargs["conf"]
        state_key = self.get_message_queue_key(
            message.author.id,
            message.channel.id,
            message.guild.id,
            conf.collab_convos,
        )
        state = self._response_state.get(state_key)
        if state is None:
            state = _ResponseState()
            self._response_state[state_key] = state

        if len(state.pending) >= state.MAX_QUEUE_DEPTH:
            log.debug(
                f"Dropping message from {message.author} in {message.channel} "
                f"(queue full: {len(state.pending)}/{state.MAX_QUEUE_DEPTH})"
            )
            return False

        state.pending.append(handle_message_kwargs)
        if state.worker is None or state.worker.done():
            state.worker = asyncio.create_task(self._drain_message_queue(state_key))

        return True

    def clear_message_queue(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> int:
        state_key = self.get_message_queue_key(author_id, channel_id, guild_id, collaborative)
        state = self._response_state.get(state_key)
        if state is None:
            return 0

        purged = len(state.pending)
        state.pending.clear()
        if state.worker is None or state.worker.done():
            self._response_state.pop(state_key, None)

        if purged:
            log.debug(f"Cleared {purged} queued assistant message(s) for {state_key}")
        return purged

    def cancel_message_queue(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> bool:
        state_key = self.get_message_queue_key(author_id, channel_id, guild_id, collaborative)
        state = self._response_state.pop(state_key, None)
        if state is None:
            return False

        had_pending = bool(state.pending)
        state.pending.clear()
        had_active_worker = state.worker is not None and not state.worker.done()
        if had_active_worker:
            state.worker.cancel()

        return had_active_worker or had_pending

    def cancel_all_message_queues(self) -> None:
        states = list(self._response_state.values())
        self._response_state.clear()
        for state in states:
            if state.worker and not state.worker.done():
                state.worker.cancel()

    async def _drain_message_queue(self, state_key: tuple[int, int, int]) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                state = self._response_state.get(state_key)
                if state is None or not state.pending:
                    return

                handle_message_kwargs = state.pending.popleft()
                message: discord.Message = handle_message_kwargs["message"]
                try:
                    async with message.channel.typing():
                        await self.handle_message(**handle_message_kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(
                        f"Failed processing queued assistant message for {message.author} in {message.channel}",
                        exc_info=e,
                    )
        finally:
            state = self._response_state.get(state_key)
            if state is None:
                return
            if state.worker is current_task:
                state.worker = None
            if state.pending and state.worker is None:
                state.worker = asyncio.create_task(self._drain_message_queue(state_key))
            elif not state.pending and state.worker is None:
                self._response_state.pop(state_key, None)

    @commands.Cog.listener("on_message_without_command")
    async def handler(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # If message was from a bot
        if message.author.bot and not self.db.listen_to_bots:
            return
        # Ignore messages without content
        if not message.content:
            if message.embeds:
                embed_to_content(message)
            elif message.attachments:
                message.content = "[No Content]"
            else:
                return
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
        has_endpoint = bool(conf.endpoint_override or self.db.endpoint_override)
        if not conf.enabled or (not conf.api_key and not has_endpoint):
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

        # Ignore common prefixes from other bots
        if message.content.startswith((",", ".", "+", "!", "-", "><", "?", "$", "%", "^", "&", "*", "_")):
            return
        if not await can_use(message, conf.blacklist, respond=False):
            return
        if len(message.content.strip()) < conf.min_length:
            return

        handle_message_kwargs = {
            "message": message,
            "question": message.content,
            "conf": conf,
            "listener": True,
        }

        # Return under the following conditions
        if (ref is not None and ref.author.id != self.bot.user.id) or (
            mention_ids and self.bot.user.id not in mention_ids
        ):
            # Do not respond to messages that are replies to other messages or mention someone else
            return

        # Check for trigger word matches (this can override other conditions)
        trigger_matched = False
        check_trigger = [
            conf.trigger_enabled,
            conf.trigger_phrases,
            channel.id not in conf.trigger_ignore_channels,
            getattr(channel, "category_id", 0) not in conf.trigger_ignore_channels,
        ]
        if all(check_trigger):
            if await self.matches_trigger(message.content, conf.trigger_phrases):
                trigger_matched = True
                if conf.trigger_prompt:
                    handle_message_kwargs["trigger_prompt"] = conf.trigger_prompt

        conditions = [
            (channel.id != conf.channel_id and channel.id not in conf.listen_channels),
            (not bot_mentioned or not conf.mention_respond),
            not trigger_matched,  # If trigger matched, don't skip
        ]
        is_mod = await self.bot.is_mod(message.author)
        check_auto_answer = [
            conf.auto_answer,
            channel.id not in conf.auto_answer_ignored_channels,
            getattr(channel, "category_id", 0) not in conf.auto_answer_ignored_channels,
            not is_mod,
        ]
        if all(check_auto_answer):
            if is_question(message.content):
                # Check if any embeddings match above the threshold
                embedding = await self.request_embedding(message.content, conf)
                related = await self.embedding_store.get_related(
                    guild_id=message.guild.id,
                    query_embedding=embedding,
                    top_n=1,
                    min_relatedness=conf.auto_answer_threshold,
                )
                conditions.append(len(related) == 0)
                if len(related) > 0:
                    handle_message_kwargs["model_override"] = conf.auto_answer_model
                    handle_message_kwargs["auto_answer"] = True
        if all(conditions):
            # Message was not in the assistant channel and bot was not mentioned and auto answer is enabled and no related embeddings
            return

        conditions = [
            (channel.id == conf.channel_id or channel.id in conf.listen_channels),
            not message.content.endswith("?"),
            conf.endswith_questionmark,
            self.bot.user.id not in mention_ids,
            not trigger_matched,  # If trigger matched, don't skip
        ]
        if all(conditions):
            # Message was in the assistant channel and didn't end with a question mark while the config requires it
            return

        await self.enqueue_message_request(handle_message_kwargs)

    @commands.Cog.listener("on_guild_remove")
    async def cleanup(self, guild: discord.Guild):
        if guild.id in self.db.configs:
            log.info(f"Bot removed from {guild.name}, cleaning up...")
            del self.db.configs[guild.id]
            await self.save_conf()
