from abc import ABC, ABCMeta, abstractmethod
from multiprocessing.pool import Pool
from typing import Callable, Dict, List, Optional, Union

import discord
from discord.ext.commands.cog import CogMeta
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import commands
from redbot.core.bot import Red

from .common.models import DB, GuildSettings


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.mp_pool: Pool
        self.registry: Dict[str, Dict[str, dict]]

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
    ) -> Union[ChatCompletionMessage, str]:
        raise NotImplementedError

    @abstractmethod
    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def resync_embeddings(self, conf: GuildSettings, guild_id: int) -> int:
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
    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_function_menu_embeds(self, user: discord.Member) -> List[discord.Embed]:
        raise NotImplementedError

    @abstractmethod
    async def get_embbedding_menu_embeds(self, conf: GuildSettings, place: int) -> List[discord.Embed]:
        raise NotImplementedError

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- 3rd Partry -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    @abstractmethod
    async def add_embedding(
        self,
        guild: discord.Guild,
        name: str,
        text: str,
        overwrite: bool = False,
        ai_created: bool = False,
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
    async def handle_message(
        self,
        message: discord.Message,
        question: str,
        conf: GuildSettings,
        listener: bool = False,
        trigger_prompt: str = None,
    ) -> str:
        raise NotImplementedError
