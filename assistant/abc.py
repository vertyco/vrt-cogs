from abc import ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .models import DB, Conversations, GuildSettings


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    db: DB
    chats: Conversations

    @abstractmethod
    async def get_chat_response(
        self, message: str, author: discord.Member, conf: GuildSettings
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_training_response(
        self, prompt: str, conf: GuildSettings
    ) -> tuple:
        raise NotImplementedError
