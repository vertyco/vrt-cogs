import secrets
import time
import typing as t
from dataclasses import dataclass, field

import discord

SESSION_TTL = 12 * 3600
LAUNCH_TTL = 120


@dataclass
class ActivityContext:
    """Who is playing and where, as proven by the Discord login and Discord's activity instance lookup"""

    # The discord.Member in a server, the discord.User anywhere else (a DM, or a server the bot isn't in)
    author: discord.Member | discord.User
    guild: discord.Guild | None = None
    channel_id: int | None = None
    instance_id: str = ""
    # Everyone who plays a game together has the same one. The hub sets it from the game's "room" before
    # handing ctx to the game, and until then it is the window's own id
    room_id: str = ""
    # For is_admin and is_mod. Games use their own self.bot, so the docs leave it out
    bot: t.Any = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.room_id:
            self.room_id = self.instance_id

    @property
    def guild_id(self) -> int | None:
        return self.guild.id if self.guild is not None else None

    @property
    def channel(self) -> discord.abc.GuildChannel | discord.Thread | None:
        """The server channel or thread the Activity runs in, or None outside a server"""
        if self.guild is None or self.channel_id is None:
            return None
        return self.guild.get_channel_or_thread(self.channel_id)

    async def is_admin(self) -> bool:
        """
        The bot owner, the server's owner, and members with Manage Server or Red's admin role in the activity's
        server, checked fresh each time. Nobody outside a server. Anyone else who is no longer in the server (not in
        the member cache) has no rights there
        """
        if self.guild is None:
            return False
        # The server's owner can't leave without handing the server over, so neither owner needs a member cache lookup
        if self.author.id == self.guild.owner_id or await self.bot.is_owner(self.author):
            return True
        member = self.guild.get_member(self.author.id)
        if member is None:
            return False
        return member.guild_permissions.manage_guild or await self.bot.is_admin(member)

    async def is_mod(self) -> bool:
        """Everyone is_admin counts, and members with Red's mod role. No Discord permission counts on its own"""
        if await self.is_admin():
            return True
        member = self.guild.get_member(self.author.id) if self.guild is not None else None
        return member is not None and await self.bot.is_mod(member)


@dataclass
class Session:
    ctx: ActivityContext
    created: float


class SessionStore:
    """Session passes handed to logged-in pages. Memory only, so a bot restart logs everyone out"""

    def __init__(self, clock: t.Callable[[], float] = time.monotonic):
        self.clock = clock
        self.sessions: dict[str, Session] = {}

    def create(self, ctx: ActivityContext) -> str:
        self.prune()
        token = secrets.token_urlsafe(32)
        self.sessions[token] = Session(ctx, self.clock())
        return token

    def get(self, token: str | None) -> Session | None:
        session = self.sessions.get(token or "")
        if session is None:
            return None
        if self.clock() - session.created >= SESSION_TTL:
            del self.sessions[token]
            return None
        return session

    def prune(self) -> None:
        now = self.clock()
        self.sessions = {k: v for k, v in self.sessions.items() if now - v.created < SESSION_TTL}

    def forget_user(self, user_id: int) -> None:
        self.sessions = {k: v for k, v in self.sessions.items() if v.ctx.author.id != user_id}


class LaunchMemory:
    """Which game a player asked for from a command, so the menu can open it right after login"""

    def __init__(self, clock: t.Callable[[], float] = time.monotonic):
        self.clock = clock
        self.wanted: dict[int, tuple[str, float]] = {}

    def remember(self, user_id: int, key: str) -> None:
        self.wanted[user_id] = (key, self.clock())

    def take(self, user_id: int) -> str | None:
        entry = self.wanted.pop(user_id, None)
        if entry is None or self.clock() - entry[1] > LAUNCH_TTL:
            return None
        return entry[0]

    def forget_user(self, user_id: int) -> None:
        self.wanted.pop(user_id, None)
