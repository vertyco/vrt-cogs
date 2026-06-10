import asyncio
from abc import ABC, ABCMeta, abstractmethod
from multiprocessing.pool import Pool
from typing import Any, Callable, Dict, List, Optional, Union

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext.commands.cog import CogMeta
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import commands
from redbot.core.bot import Red

from .common.command_index import CommandIndexStore
from .common.embedding_store import EmbeddingStore
from .common.models import DB, Conversation, EndpointProfile, GuildSettings


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.mp_pool: Pool
        self.registry: Dict[str, Dict[str, dict]]
        self.context_registry: Dict[str, Dict[str, dict]]
        self.embedding_store: EmbeddingStore
        self.command_index: CommandIndexStore
        self.cmdindex_task: Optional[asyncio.Task]
        self.scheduler: AsyncIOScheduler
        # Keys: "cached", "cache_write", "total", "model".
        self.last_cache_stats: Dict[str, object]
        # Smartmod review state (actually assigned in SmartMod.__init__).
        self.smartmod_cooldowns: Dict[tuple[int, int], float]
        self.smartmod_tasks: set

    @abstractmethod
    async def _fire_reminder(self, reminder_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def _fire_scheduled_task(self, task_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_api_key(self, conf: GuildSettings) -> str:
        raise NotImplementedError

    @abstractmethod
    async def openai_status(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def request_response(
        self,
        messages: List[dict],
        conf: GuildSettings,
        functions: Optional[List[dict]] = None,
        member: discord.Member = None,
        response_token_override: int = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        session_id: Optional[str] = None,
        guild_id: Optional[int] = None,
        tool_choice: Optional[Union[str, dict]] = None,
    ) -> ChatCompletionMessage:
        raise NotImplementedError

    @abstractmethod
    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    async def request_embedding_with_info(self, text: str, conf: GuildSettings) -> tuple[List[float], str]:
        raise NotImplementedError

    @abstractmethod
    async def request_embeddings_batch(self, texts: List[str], conf: GuildSettings) -> tuple[List[List[float]], str]:
        raise NotImplementedError

    @abstractmethod
    def schedule_command_index_sync(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def resync_embeddings(self, conf: GuildSettings, guild_id: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_cached_endpoint_profile(self, conf: Optional[GuildSettings] = None) -> Optional[EndpointProfile]:
        raise NotImplementedError

    @abstractmethod
    def clear_endpoint_profile(self, conf: Optional[GuildSettings] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def resolve_chat_model(self, requested_model: str, conf: Optional[GuildSettings] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def resolve_embedding_model(self, requested_model: str, conf: Optional[GuildSettings] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_endpoint_chat_model_limit(
        self, requested_model: Optional[str] = None, conf: Optional[GuildSettings] = None
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def describe_endpoint_profile(self, profile: EndpointProfile) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_guild_endpoint_url(self, conf: GuildSettings) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    async def refresh_endpoint_profile(
        self, conf: Optional[GuildSettings] = None, force: bool = False, save: bool = False
    ) -> Optional[EndpointProfile]:
        raise NotImplementedError

    @abstractmethod
    async def endpoint_supports_vision(
        self,
        conf: GuildSettings,
        user: Optional[discord.Member] = None,
        requested_model: Optional[str] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def observe_embedding_runtime(self, model_id: str, dimensions: int, conf: Optional[GuildSettings] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_max_tokens(self, conf: GuildSettings, member: Optional[discord.Member]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, user: Optional[discord.Member] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    async def count_payload_tokens(self, messages: List[dict], model: str = "gpt-5.1") -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_function_tokens(self, functions: List[dict], model: str = "gpt-5.1") -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_tokens(self, text: str, model: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_tokens(self, text: str, model: str = "gpt-5.1") -> list[int]:
        raise NotImplementedError

    @abstractmethod
    async def get_text(self, tokens: list, model: str = "gpt-5.1") -> str:
        raise NotImplementedError

    @abstractmethod
    async def degrade_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def compact_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
        conversation: Optional[Conversation] = None,
        focus: str = "",
        force: bool = False,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_mention_permissions(self, member: discord.Member) -> discord.AllowedMentions:
        raise NotImplementedError

    @abstractmethod
    async def resolve_prompt_context_variables(
        self,
        guild: discord.Guild,
        channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]],
        author: Optional[discord.Member],
        conf: GuildSettings,
        conversation: Conversation,
        extras: dict,
        now: Any,
        prompt_templates: List[str],
    ) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_function_menu_embeds(self, user: discord.Member) -> List[discord.Embed]:
        raise NotImplementedError

    @abstractmethod
    async def get_embedding_menu_embeds(self, conf: GuildSettings, place: int) -> List[discord.Embed]:
        raise NotImplementedError

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- SMARTMOD -------------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    @abstractmethod
    def resolve_smartmod_key(self, conf: GuildSettings) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def smartmod_passes_filters(self, message: discord.Message, conf: GuildSettings) -> bool:
        raise NotImplementedError

    @abstractmethod
    def smartmod_match_triggers(self, content: str, conf: GuildSettings) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    async def smartmod_score(
        self,
        content: str,
        conf: GuildSettings,
        image_urls: Optional[List[str]] = None,
    ) -> Optional[Dict[str, float]]:
        raise NotImplementedError

    @abstractmethod
    async def run_smartmod(self, message: discord.Message, conf: GuildSettings) -> None:
        raise NotImplementedError

    @abstractmethod
    async def simulate_smartmod(
        self,
        message: discord.Message,
        conf: GuildSettings,
        tripped: Dict[str, float],
        content: str,
        output_channel: discord.abc.Messageable,
    ) -> tuple:
        raise NotImplementedError

    @abstractmethod
    async def execute_mod_action(
        self,
        action: str,
        *,
        guild: discord.Guild,
        flagged_message: discord.Message,
        target: Union[discord.Member, discord.User],
        reason: str,
        actor: Union[discord.Member, discord.ClientUser],
        duration_minutes: int = 0,
        delete_message: bool = False,
    ) -> tuple[str, bool]:
        raise NotImplementedError

    @abstractmethod
    async def smartmod_unban(self, guild_id: int, user_id: int, reason: str) -> None:
        raise NotImplementedError

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- 3rd Party ------------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    @abstractmethod
    async def add_embedding(
        self,
        guild: discord.Guild,
        name: str,
        text: str,
        overwrite: bool = False,
    ) -> Optional[List[float]]:
        raise NotImplementedError

    @abstractmethod
    async def get_chat_response(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conf: GuildSettings,
        function_calls: Optional[List[dict]] = None,
        function_map: Optional[Dict[str, Callable]] = None,
        extend_function_calls: bool = True,
        message_obj: Optional[discord.Message] = None,
    ) -> str:
        raise NotImplementedError

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- MAIN --------------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    @abstractmethod
    async def save_conf(self):
        raise NotImplementedError

    @abstractmethod
    def get_message_queue_key(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> tuple[int, int, int]:
        raise NotImplementedError

    @abstractmethod
    async def enqueue_message_request(self, handle_message_kwargs: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear_message_queue(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def cancel_message_queue(
        self,
        author_id: int,
        channel_id: int,
        guild_id: int,
        collaborative: bool,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def cancel_all_message_queues(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def handle_message(
        self,
        message: discord.Message,
        question: str,
        conf: GuildSettings,
        listener: bool = False,
        trigger_prompt: str = None,
    ) -> str:
        raise NotImplementedError
