"""
Type hints for ActivityHub's ctx, live connection and room, for your editor.

Copy this file into your cog and import from it, like `from .hubtypes import HubContext`. Don't import from
activityhub itself: Red loads cogs by folder name, so that import fails whenever your cog loads before ActivityHub.
"""

from typing import Any, Protocol, Sequence

import discord


class HubContext(Protocol):
    """ActivityHub's ctx"""

    author: discord.Member | discord.User
    guild: discord.Guild | None
    channel_id: int | None
    instance_id: str
    room_id: str

    @property
    def guild_id(self) -> int | None: ...

    @property
    def channel(self) -> discord.abc.GuildChannel | discord.Thread | None: ...

    async def is_admin(self) -> bool: ...

    async def is_mod(self) -> bool: ...


class HubRoom(Protocol):
    """Everyone playing your game together: one Activity window, or more with the "room" field"""

    id: str
    instance_id: str | None

    @property
    def connections(self) -> Sequence["HubConnection"]: ...

    async def broadcast(self, data: Any) -> None: ...


class HubConnection(Protocol):
    """A live connection, as socket handlers get it"""

    @property
    def ctx(self) -> HubContext: ...

    @property
    def room(self) -> HubRoom: ...

    @property
    def follow(self) -> int | None: ...

    async def send(self, data: Any) -> None: ...

    async def broadcast(self, data: Any, include_self: bool = False) -> None: ...

    def peers(self) -> Sequence["HubConnection"]: ...

    async def close(self, code: int = 1000) -> None: ...
