import asyncio
import multiprocessing as mp
import typing as t
from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime
from pathlib import Path

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core import commands
from redbot.core.bot import Red

from .common.models import DB, GuildSettings, Profile, VoiceTracking
from .generator.tenor.converter import TenorAPI


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red

        # Cache
        self.db: DB
        self.lastmsg: t.Dict[int, t.Dict[int, float]]
        self.voice_tracking: t.Dict[int, t.Dict[int, VoiceTracking]]
        self.profile_cache: t.Dict[int, t.Dict[int, t.Tuple[str, bytes]]]
        self.stars: t.Dict[int, t.Dict[int, datetime]]

        self.cog_path: Path
        self.bundled_path: Path
        # Custom
        self.custom_fonts: Path
        self.custom_backgrounds: Path
        # Bundled
        self.stock: Path
        self.fonts: Path
        self.backgrounds: Path

        # Save state
        self.last_save: float

        # Tenor
        self.tenor: TenorAPI

        # Internal API
        self.api_proc: t.Union[asyncio.subprocess.Process, mp.Process]

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def start_api(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def stop_api(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def initialize_voice_states(self) -> int:
        raise NotImplementedError

    # -------------------------- levelups.py --------------------------
    @abstractmethod
    async def check_levelups(
        self,
        guild: discord.Guild,
        member: discord.Member,
        profile: Profile,
        conf: GuildSettings,
        message: t.Optional[discord.Message] = None,
        channel: t.Optional[
            t.Union[discord.TextChannel, discord.VoiceChannel, discord.Thread, discord.ForumChannel]
        ] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def ensure_roles(
        self,
        member: discord.Member,
        conf: t.Optional[GuildSettings] = None,
        reason: t.Optional[str] = None,
    ) -> t.Tuple[t.List[discord.Role], t.List[discord.Role]]:
        raise NotImplementedError

    # -------------------------- weeklyreset.py --------------------------
    @abstractmethod
    async def reset_weekly(self, guild: discord.Guild, ctx: commands.Context = None) -> bool:
        raise NotImplementedError

    # -------------------------- profile.py --------------------------
    @abstractmethod
    async def add_xp(self, member: discord.Member, xp: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def set_xp(self, member: discord.Member, xp: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def remove_xp(self, member: discord.Member, xp: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_profile_background(
        self, user_id: int, profile: Profile, try_return_url: bool = False
    ) -> t.Union[bytes, str]:
        raise NotImplementedError

    @abstractmethod
    async def get_banner(self, user_id: int) -> t.Optional[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_profile(
        self, member: discord.Member, reraise: bool = False
    ) -> t.Union[discord.Embed, discord.File]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_profile_cached(self, member: discord.Member) -> t.Union[discord.File, discord.Embed]:
        raise NotImplementedError
