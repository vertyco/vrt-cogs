from abc import ABCMeta, abstractmethod
from multiprocessing.pool import Pool
from typing import Callable, Dict, List, Optional, Tuple, Union

import discord
import tiktoken
from discord.ext.commands.cog import CogMeta
from redbot.core import commands
from redbot.core.bot import Red

from .common.models import DB, Conversation, GuildSettings


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    db: DB
    mp_pool: Pool
    registry: Dict[str, Dict[str, dict]]

    tokenizer: tiktoken.core.Encoding

    @abstractmethod
    async def request_response(
        self,
        messages: List[dict],
        conf: GuildSettings,
        functions: Optional[List[dict]] = None,
        member: discord.Member = None,
    ) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    async def can_call_llm(
        self, conf: GuildSettings, ctx: Optional[commands.Context] = None
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def resync_embeddings(self, conf: GuildSettings) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_max_tokens(self, conf: GuildSettings, member: Optional[discord.Member]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, max_tokens: int) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_token_count(self, text: str, conf: GuildSettings) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_tokens(self, text: str, conf: GuildSettings) -> list:
        raise NotImplementedError

    @abstractmethod
    async def get_text(self, tokens: list, conf: GuildSettings) -> str:
        raise NotImplementedError

    @abstractmethod
    async def convo_token_count(self, conf: GuildSettings, convo: Conversation) -> int:
        raise NotImplementedError

    @abstractmethod
    async def prompt_token_count(self, conf: GuildSettings) -> int:
        raise NotImplementedError

    @abstractmethod
    async def function_token_count(self, conf: GuildSettings, functions: List[dict]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def degrade_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
    ) -> Tuple[List[dict], List[dict], bool]:
        raise NotImplementedError

    @abstractmethod
    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_function_menu_embeds(self, user: discord.Member) -> List[discord.Embed]:
        raise NotImplementedError

    @abstractmethod
    async def get_embbedding_menu_embeds(
        self, conf: GuildSettings, place: int
    ) -> List[discord.Embed]:
        raise NotImplementedError

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- 3rd Partry -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

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
        self, message: discord.Message, question: str, conf: GuildSettings, listener: bool = False
    ) -> str:
        raise NotImplementedError
