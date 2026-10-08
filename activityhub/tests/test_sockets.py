from pathlib import Path
from types import SimpleNamespace

import pytest

from activityhub.common.games import Game
from activityhub.common.sessions import ActivityContext
from activityhub.common.sockets import Connection, Rooms


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False
        self.close_code = None

    async def send_json(self, data):
        if self.closed:
            raise ConnectionResetError("Cannot write to closing transport")
        self.sent.append(data)

    async def close(self, code=1000, message=b""):
        self.closed = True
        self.close_code = code
        return True


def make_game(key="demo"):
    return Game(key=key, name=key.title(), web_dir=Path("."), cog=None)


def connect(rooms, game, user_id, instance="i-1", guild_id=9):
    guild = SimpleNamespace(id=guild_id) if guild_id else None
    ctx = ActivityContext(author=SimpleNamespace(id=user_id), guild=guild, instance_id=instance)
    conn = Connection(FakeWebSocket(), ctx, game, rooms)
    rooms.add(conn)
    return conn


@pytest.mark.asyncio
async def test_rooms_group_by_game_and_instance():
    rooms, demo, other = Rooms(), make_game(), make_game("other")
    a, b = connect(rooms, demo, 1), connect(rooms, demo, 2)
    elsewhere = connect(rooms, demo, 3, instance="i-2")
    other_game = connect(rooms, other, 4)
    assert a.peers() == [b]
    assert b.peers() == [a]
    assert elsewhere.peers() == [] and other_game.peers() == []
    assert len(rooms.all()) == 4


@pytest.mark.asyncio
async def test_broadcast_reaches_peers_and_optionally_self():
    rooms, demo = Rooms(), make_game()
    a, b, c = connect(rooms, demo, 1), connect(rooms, demo, 2), connect(rooms, demo, 3, instance="i-2")
    await a.broadcast({"hi": 1})
    assert b.ws.sent == [{"hi": 1}] and a.ws.sent == [] and c.ws.sent == []
    await a.broadcast({"hi": 2}, include_self=True)
    assert a.ws.sent == [{"hi": 2}]


@pytest.mark.asyncio
async def test_sending_to_a_closed_connection_does_nothing():
    rooms = Rooms()
    conn = connect(rooms, make_game(), 1)
    await conn.close(1000)
    await conn.send({"late": True})
    assert conn.ws.sent == []


@pytest.mark.asyncio
async def test_close_remembers_its_code():
    conn = connect(Rooms(), make_game(), 1)
    await conn.close(4003)
    assert conn.closing == 4003 and conn.ws.close_code == 4003


@pytest.mark.asyncio
async def test_discard_removes_empty_rooms():
    rooms = Rooms()
    conn = connect(rooms, make_game(), 1)
    rooms.discard(conn)
    rooms.discard(conn)
    assert rooms.all() == [] and rooms.rooms == {}


@pytest.mark.asyncio
async def test_close_stale_closes_unloaded_and_replaced_games():
    rooms, demo, kept = Rooms(), make_game(), make_game("kept")
    replaced = connect(rooms, demo, 1)
    unloaded = connect(rooms, make_game("gone"), 2)
    alive = connect(rooms, kept, 3)
    await rooms.close_stale({"demo": make_game(), "kept": kept})
    assert replaced.ws.close_code == 1001 and unloaded.ws.close_code == 1001
    assert not alive.ws.closed


@pytest.mark.asyncio
async def test_close_off_only_touches_that_server_and_those_games():
    rooms, demo, other = Rooms(), make_game(), make_game("other")
    here = connect(rooms, demo, 1, guild_id=9)
    other_server = connect(rooms, demo, 2, guild_id=8)
    dm = connect(rooms, demo, 3, guild_id=None)
    other_game = connect(rooms, other, 4, guild_id=9)
    await rooms.close_off(9, ["demo"])
    assert here.ws.close_code == 4003
    assert not other_server.ws.closed and not dm.ws.closed and not other_game.ws.closed


@pytest.mark.asyncio
async def test_close_games_touches_every_server():
    rooms, demo, other = Rooms(), make_game(), make_game("other")
    conns = [
        connect(rooms, demo, 1, guild_id=9),
        connect(rooms, demo, 2, guild_id=8),
        connect(rooms, demo, 3, guild_id=None),
    ]
    other_game = connect(rooms, other, 4, guild_id=9)
    await rooms.close_games(["demo"])
    assert [c.ws.close_code for c in conns] == [4003, 4003, 4003]
    assert not other_game.ws.closed


@pytest.mark.asyncio
async def test_close_all():
    rooms = Rooms()
    conns = [connect(rooms, make_game(), 1), connect(rooms, make_game("b"), 2)]
    await rooms.close_all()
    assert [c.ws.close_code for c in conns] == [1001, 1001]
