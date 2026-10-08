import asyncio
import gc
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from activityhub.common import sockets
from activityhub.common.games import Game
from activityhub.common.sessions import ActivityContext
from activityhub.common.sockets import PING, READY, Connection, Rooms


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False
        self.close_code = None

    async def send_str(self, text):
        if self.closed:
            raise ConnectionResetError("Cannot write to closing transport")
        self.sent.append(json.loads(text))

    async def close(self, code=1000, message=b"", drain=True):
        self.closed = True
        self.close_code = code
        return True


class StalledWebSocket(FakeWebSocket):
    """A player whose network stopped taking data, so a message to them never finishes sending"""

    def __init__(self):
        super().__init__()
        self.network = asyncio.get_running_loop().create_future()

    async def send_str(self, text):
        # aiohttp waits for the network like this, shielded, until the connection drains or drops
        await asyncio.shield(self.network)


class DroppedWebSocket(FakeWebSocket):
    """A player whose connection broke while a message waited for the network, the way aiohttp reports it"""

    async def send_str(self, text):
        raise ConnectionError("Connection lost")


def make_game(key="demo"):
    return Game(key=key, name=key.title(), web_dir=Path("."), cog=None)


def connect(rooms, game, user_id, instance="i-1", guild_id=9, ws=None):
    guild = SimpleNamespace(id=guild_id) if guild_id else None
    ctx = ActivityContext(author=SimpleNamespace(id=user_id), guild=guild, instance_id=instance)
    conn = Connection(ws or FakeWebSocket(), ctx, game, rooms)
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
    await conn.end(4003)
    assert conn.closing == 4003 and conn.ws.close_code == 4003


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [4000, 4001, 4004, 4099])
async def test_games_cannot_close_with_the_hubs_codes(code):
    conn = connect(Rooms(), make_game(), 1)
    with pytest.raises(ValueError) as caught:
        await conn.close(code)
    assert str(caught.value) == (
        f"Close code {code} is reserved for ActivityHub. Use 1000, or 4100-4999 for your game's own reasons."
    )
    assert not conn.ws.closed and conn.closing is None


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [1000, 4100, 4999])
async def test_games_close_with_their_own_codes(code):
    conn = connect(Rooms(), make_game(), 1)
    await conn.close(code)
    assert conn.closing == code and conn.ws.close_code == code


@pytest.mark.asyncio
async def test_only_finite_numbers_are_sent():
    # Python writes NaN and Infinity into JSON, but the page can't read them back
    rooms = Rooms()
    conn, peer = connect(rooms, make_game(), 1), connect(rooms, make_game(), 2)
    for value in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError):
            await conn.send({"x": value})
        with pytest.raises(ValueError):
            await conn.broadcast({"x": value})
    assert conn.ws.sent == [] and peer.ws.sent == []


@pytest.mark.asyncio
async def test_the_activityhub_field_is_the_hubs_own():
    rooms = Rooms()
    conn, peer = connect(rooms, make_game(), 1), connect(rooms, make_game(), 2)
    message = "The 'activityhub' field is reserved for the hub's own messages. Use another field name."
    # A copy of the hub's own message would be swallowed by sdk.js too, so only the hub's own objects pass
    for data in ({"activityhub": "x"}, {"activityhub": "ready"}, dict(PING)):
        with pytest.raises(ValueError) as caught:
            await conn.send(data)
        assert str(caught.value) == message
        with pytest.raises(ValueError):
            await conn.broadcast(data)
    await conn.send(READY)
    await conn.send(PING)
    await conn.send({"hub": 1})
    assert conn.ws.sent == [READY, PING, {"hub": 1}] and peer.ws.sent == []


@pytest.mark.asyncio
async def test_bad_messages_are_refused_even_with_no_one_to_send_to():
    # Otherwise the mistake would only show once a second player joins, or never for a closed connection
    rooms = Rooms()
    alone = connect(rooms, make_game(), 1)
    with pytest.raises(ValueError):
        await alone.broadcast({"x": math.nan})
    await alone.end(1000)
    with pytest.raises(ValueError):
        await alone.send({"activityhub": "x"})


@pytest.mark.asyncio
async def test_a_player_who_dropped_never_breaks_the_sender():
    rooms, demo = Rooms(), make_game()
    sender, dropped = connect(rooms, demo, 1), connect(rooms, demo, 2, ws=DroppedWebSocket())
    other = connect(rooms, demo, 3)
    await sender.broadcast({"hi": 1})
    await dropped.send({"hi": 2})
    assert other.ws.sent == [{"hi": 1}]
    # Their own pump sees the dropped connection and runs leave, so nothing is closed from here
    assert dropped.closer is None and not dropped.ws.closed


@pytest.mark.asyncio
async def test_a_stalled_player_is_closed_without_holding_up_the_rest(monkeypatch):
    monkeypatch.setattr(sockets, "SEND_SECONDS", 0.05)
    rooms, demo = Rooms(), make_game()
    sender, stalled = connect(rooms, demo, 1), connect(rooms, demo, 2, ws=StalledWebSocket())
    other = connect(rooms, demo, 3)
    await asyncio.wait_for(sender.broadcast({"hi": 1}), 1)
    assert other.ws.sent == [{"hi": 1}]
    await asyncio.wait_for(stalled.closer, 1)
    assert stalled.closing == 1001 and stalled.ws.close_code == 1001
    # Closed now, so the next message to them returns at once instead of waiting out SEND_SECONDS again
    monkeypatch.setattr(sockets, "SEND_SECONDS", 60)
    await asyncio.wait_for(sender.broadcast({"hi": 2}), 1)
    assert other.ws.sent == [{"hi": 1}, {"hi": 2}]


@pytest.mark.asyncio
async def test_a_stalled_player_dropping_later_logs_nothing(monkeypatch):
    # Red logs anything asyncio reports as never retrieved as a critical error
    monkeypatch.setattr(sockets, "SEND_SECONDS", 0.05)
    loop = asyncio.get_running_loop()
    reported = []
    monkeypatch.setattr(loop, "call_exception_handler", reported.append)
    rooms = Rooms()
    sender, stalled = connect(rooms, make_game(), 1), connect(rooms, make_game(), 2, ws=StalledWebSocket())
    await sender.broadcast({"hi": 1})
    await asyncio.wait_for(stalled.closer, 1)
    # Minutes later the phone's connection finally times out, and aiohttp lets go of its wait
    stalled.ws.network.set_exception(ConnectionError("Connection lost"))
    stalled.ws.network = None
    for attempt in range(3):
        await asyncio.sleep(0)
    gc.collect()
    assert reported == []


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
