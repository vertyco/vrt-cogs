from abc import ABCMeta, abstractmethod
from typing import Optional

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
    async def prune_invalid_tickets(
        self, guild: discord.Guild, ctx: Optional[commands.Context] = None
    ) -> None:
        raise NotImplementedError
