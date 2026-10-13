"""Stand-ins for ActivityHub's room and connections, shaped like the ones in DEVELOPERS.md's testing section"""

from types import SimpleNamespace


class FakeRoom:
    def __init__(self, instance_id="window", room_id=None):
        """A room of one window by default. FakeRoom(None, "server-500") is a server's room, spanning its windows"""
        self.instance_id = instance_id
        self.id = room_id or instance_id
        self.members = []

    @property
    def connections(self):
        return list(self.members)

    async def broadcast(self, data):
        for conn in self.members:
            conn.sent.append(data)


class FakeConn:
    def __init__(self, room, user_id, instance_id=None):
        """`instance_id` is the window the page is in, which a room spanning windows doesn't say"""
        author = SimpleNamespace(
            id=user_id,
            name=f"user{user_id}",
            display_name=f"Player {user_id}",
            global_name=f"Global {user_id}",
            display_avatar=SimpleNamespace(url=f"https://cdn.discordapp.com/avatars/{user_id}/a.png"),
        )
        self.ctx = SimpleNamespace(author=author, instance_id=instance_id or room.instance_id, room_id=room.id)
        self.room = room
        self.sent = []
        # The friend a Join in the hub's people list followed, as the hub sets it
        self.follow = None
        room.members.append(self)

    async def send(self, data):
        self.sent.append(data)

    def drop(self):
        """The hub takes a closing connection out of its room before leave runs"""
        self.room.members.remove(self)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now
