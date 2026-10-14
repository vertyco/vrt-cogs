"""
Stand-ins for ActivityHub's ctx, live connection and room, for testing your game's Python without Discord.

Copy this file into your cog's tests folder. Nothing here imports ActivityHub. hubtypes.py and ActivityHub's
REFERENCE.md describe the real objects.
"""

import json
from types import SimpleNamespace


class FakeContext:
    """Stands in for ctx. admin and mod set what is_admin() and is_mod() answer"""

    def __init__(
        self,
        author,
        guild=None,
        channel=None,
        channel_id=None,
        instance_id="test",
        room_id=None,
        admin=False,
        mod=False,
    ):
        self.author, self.guild, self.instance_id = author, guild, instance_id
        # The window's id unless the test puts the player in a wider room
        self.room_id = room_id or instance_id
        self.channel, self.channel_id = channel, channel_id
        self.admin, self.mod = admin, mod

    @property
    def guild_id(self):
        return self.guild.id if self.guild is not None else None

    async def is_admin(self):
        return self.admin

    async def is_mod(self):
        # Admins count as mods, like the real ctx
        return self.admin or self.mod


class FakeRoom:
    """Stands in for conn.room. A wider room spans windows: FakeRoom(None, room_id="server-1")"""

    def __init__(self, instance_id="test", room_id=None):
        self.instance_id, self.connections = instance_id, []
        self.id = room_id or instance_id

    async def broadcast(self, data):
        for conn in list(self.connections):
            await conn.send(data)


class FakeConn:
    """
    Stands in for a live connection. Keeps a copy of what was sent as JSON in `sent`, and raises ValueError for
    NaN, Infinity and a top-level "activityhub" field, which the hub refuses too. It writes JSON with the json
    module, not the hub's own writer, and checks nothing else about a message
    """

    def __init__(self, ctx, room, follow=None):
        self.ctx, self.room, self.sent, self.closed = ctx, room, [], None
        # The friend's user id when this player came in with Join, like the real conn.follow
        self.follow = follow
        room.connections.append(self)

    async def send(self, data):
        if isinstance(data, dict) and "activityhub" in data:
            raise ValueError("The 'activityhub' field is reserved for the hub's own messages. Use another field name.")
        self.sent.append(json.loads(json.dumps(data, allow_nan=False)))

    async def broadcast(self, data, include_self=False):
        for conn in list(self.room.connections):
            if include_self or conn is not self:
                await conn.send(data)

    def peers(self):
        return [conn for conn in self.room.connections if conn is not self]

    async def close(self, code=1000):
        if 4000 <= code <= 4099:
            raise ValueError(f"Close code {code} is reserved for ActivityHub")
        self.closed = code


def player(user_id, instance_id="test", guild=None, admin=False, mod=False, room_id=None):
    """A ctx for a made-up player, outside a server unless guild is given"""
    author = SimpleNamespace(id=user_id, name=f"player{user_id}", display_name=f"Player {user_id}")
    return FakeContext(author, guild=guild, instance_id=instance_id, room_id=room_id, admin=admin, mod=mod)
