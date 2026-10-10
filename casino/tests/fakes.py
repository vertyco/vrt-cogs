"""Stand-ins for Red's bank, Discord members and ActivityHub's connections"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

GUILD_ID = 500


class FakeBank:
    """A bank in a dict, with Red's maximum balance"""

    def __init__(self, start: int = 1000, maximum: int = 2**63 - 1):
        self.balances: dict[int, int] = {}
        self.start = start
        self.maximum = maximum
        self.global_bank = False

    async def balance(self, who) -> int:
        return self.balances.setdefault(who.id, self.start)

    async def can_spend(self, who, amount: int) -> bool:
        return amount >= 0 and await self.balance(who) >= amount

    async def withdraw(self, who, amount: int) -> None:
        assert await self.can_spend(who, amount)
        self.balances[who.id] -= amount

    async def deposit(self, who, amount: int) -> int:
        self.balances[who.id] = min(self.maximum, await self.balance(who) + amount)
        return self.balances[who.id]

    async def can_receive(self, who, amount: int) -> bool:
        return await self.balance(who) + amount <= self.maximum

    async def is_global(self) -> bool:
        return self.global_bank

    async def currency(self, guild) -> str:
        return "credits"


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def member(user_id: int, name: str | None = None, guild=None, roles=(), days: int = 30, manage: bool = False):
    name = name or f"player{user_id}"
    joined = datetime.now(timezone.utc) - timedelta(days=days)
    return SimpleNamespace(
        id=user_id,
        name=name,
        display_name=name.title(),
        global_name=None,
        display_avatar=SimpleNamespace(url=f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png"),
        guild=guild,
        roles=[SimpleNamespace(id=role_id, name=f"role{role_id}") for role_id in roles],
        joined_at=joined,
        created_at=joined - timedelta(days=100),
        guild_permissions=SimpleNamespace(manage_guild=manage),
        bot=False,
    )


class FakeGuild:
    def __init__(self, guild_id: int = GUILD_ID, name: str = "Test Server"):
        self.id = guild_id
        self.name = name
        self.by_id: dict[int, SimpleNamespace] = {}
        self.roles = [SimpleNamespace(id=900, name="VIP"), SimpleNamespace(id=901, name="Whale")]

    @property
    def members(self) -> list:
        return list(self.by_id.values())

    def add(self, user_id: int, **kwargs):
        self.by_id[user_id] = member(user_id, guild=self, **kwargs)
        return self.by_id[user_id]

    def get_member(self, user_id: int):
        return self.by_id.get(user_id)

    def get_role(self, role_id: int):
        return next((role for role in self.roles if role.id == role_id), None)


class FakeBot:
    def __init__(self, owner_id: int = 1):
        self.owner_id = owner_id
        self.admins: set[int] = set()
        self.guilds: dict[int, FakeGuild] = {}
        self.users: dict[int, SimpleNamespace] = {}

    def get_guild(self, guild_id: int):
        return self.guilds.get(guild_id)

    def get_user(self, user_id: int):
        return self.users.get(user_id)

    async def is_owner(self, user) -> bool:
        return user.id == self.owner_id

    async def is_admin(self, user) -> bool:
        return user.id in self.admins


def ctx_for(who, guild=None, instance_id: str = "window"):
    return SimpleNamespace(
        author=who,
        guild=guild,
        guild_id=guild.id if guild else None,
        channel=None,
        channel_id=77,
        instance_id=instance_id,
    )


class FakeRoom:
    def __init__(self, instance_id: str = "window"):
        self.instance_id = instance_id
        self.members: list["FakeConn"] = []

    @property
    def connections(self):
        return list(self.members)

    async def broadcast(self, data):
        for conn in list(self.members):
            await conn.send(data)


class FakeConn:
    """A live connection that keeps what it was sent, turned into JSON and back like the hub does"""

    def __init__(self, room: FakeRoom, who, guild=None):
        self.room = room
        self.ctx = ctx_for(who, guild, room.instance_id)
        self.sent: list = []
        self.closed: int | None = None
        room.members.append(self)

    async def send(self, data):
        self.sent.append(json.loads(json.dumps(data, allow_nan=False)))

    async def close(self, code: int = 1000):
        self.closed = code

    def peers(self):
        return [conn for conn in self.room.members if conn is not self]

    def drop(self):
        """The hub takes a closing connection out of its room before leave runs"""
        self.room.members.remove(self)

    def of(self, kind: str) -> list[dict]:
        return [message for message in self.sent if message.get("t") == kind]

    def last(self, kind: str) -> dict:
        return self.of(kind)[-1]
