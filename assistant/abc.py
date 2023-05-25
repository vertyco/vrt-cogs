from abc import ABCMeta, abstractmethod
from typing import Union

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
        self,
        message: str,
        author: discord.Member,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel],
        conf: GuildSettings,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def save_conf(self):
        raise NotImplementedError
