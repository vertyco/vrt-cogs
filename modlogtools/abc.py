import typing as t
from abc import ABC, ABCMeta, abstractmethod
from datetime import timedelta

import discord
from discord.ext.commands.cog import CogMeta
from redbot.cogs.warnings.warnings import Warnings
from redbot.core import modlog
from redbot.core.bot import Red

from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection."""


class MixinMeta(ABC):
    """Shared typing for mixins."""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.initialized: bool

    @abstractmethod
    async def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_warnings_cog(self) -> Warnings | None:
        raise NotImplementedError

    @abstractmethod
    async def sync_guild_records(
        self,
        guild: discord.Guild,
        *,
        full_scan: bool = False,
        save: bool = True,
    ) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    async def capture_warning_case(self, case: modlog.Case, *, save: bool = True) -> bool:
        raise NotImplementedError

    @abstractmethod
    def preview_warning_expiry_update(self, guild: discord.Guild, duration: timedelta | None) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    async def export_guild_config(self, guild: discord.Guild) -> dict[str, t.Any]:
        raise NotImplementedError

    @abstractmethod
    def summarize_guild_import(self, guild: discord.Guild, payload: dict[str, t.Any]) -> dict[str, t.Any]:
        raise NotImplementedError

    @abstractmethod
    async def import_guild_config(
        self,
        guild: discord.Guild,
        payload: dict[str, t.Any],
        *,
        save: bool = True,
    ) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    async def preview_guild_expiry(self, guild: discord.Guild) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    async def expire_guild_warnings(self, guild: discord.Guild, *, save: bool = True) -> dict[str, int]:
        raise NotImplementedError
