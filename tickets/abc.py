from abc import ABCMeta, abstractmethod
from typing import List, Optional, Union

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    config: Config
    ticket_panel_schema: dict
    modal_schema: dict

    @abstractmethod
    async def initialize(self, target_guild: discord.Guild = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close_ticket(
        self,
        member: Union[discord.Member, discord.User],
        guild: discord.Guild,
        channel: discord.TextChannel,
        conf: dict,
        reason: str,
        closedby: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def fetch_channel_history(
        channel: discord.TextChannel, limit: int = None
    ) -> List[discord.Message]:
        raise NotImplementedError

    @abstractmethod
    async def ticket_owner_hastyped(
        channel: discord.TextChannel, user: discord.Member
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_ticket_owner(opened: dict, channel_id: str) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    async def prune_invalid_tickets(
        self, guild: discord.Guild, ctx: Optional[commands.Context] = None
    ) -> None:
        raise NotImplementedError
