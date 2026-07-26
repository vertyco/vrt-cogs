import asyncio
from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime

import discord
from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from redbot.core.bot import Red


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: PostgresEngine | None
        # server id -> {playerId: PalPlayer} last snapshot; absent key = no baseline yet
        self.snapshots: dict[int, dict]
        # server id -> bool reachability; absent key = unknown (no transition embed on first result)
        self.servers_online: dict[int, bool]
        # guild id -> the live status panel message, so the poll loop edits it without refetching
        self.status_messages: dict[int, discord.Message]
        # guild id -> (rendered at, attachment filename, png); the panel graph between re-renders
        self.status_graphs: dict[int, tuple[datetime, str | None, bytes | None]]
        # Held by the poll loop, connect(), and restore: each of those swaps or invalidates the
        # state the others are mid-way through reading
        self.init_lock: asyncio.Lock

    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError
