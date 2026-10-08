import asyncio
import socket
from types import SimpleNamespace

import pytest

from activityhub import main
from activityhub.main import ActivityHub
from activityhub.common.sockets import Rooms
from activityhub.tests.fakes import DemoCog, make_hub, write_demo_web


def hub_with_server(server):
    hub = make_hub()
    hub.server = server
    return hub


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,port",
    [("127.0.0.1", 99999), ("a" * 64 + ".example.com", 8742)],
    ids=["port past 65535", "host label over 63 characters"],
)
async def test_a_saved_address_that_cannot_be_used_does_not_block_loading(server, hub_web, host, port, caplog):
    hub = hub_with_server(server)
    await hub.config.host.set(host)
    await hub.config.port.set(port)
    await ActivityHub.start_server(hub)
    assert not server.running
    assert server.runner is None and server.http is None
    assert "could not listen" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_start_closes_the_http_session(server):
    with pytest.raises(OverflowError):
        await server.start("127.0.0.1", 99999)
    assert server.http is None and server.runner is None


class WaitingGame(DemoCog):
    """A game cog whose activityhub_game() waits, like one that waits for the bot to be ready"""

    def __init__(self, web_dir, **kwargs):
        super().__init__(web_dir, **kwargs)
        self.go = asyncio.Event()

    async def activityhub_game(self) -> dict:
        await self.go.wait()
        return await super().activityhub_game()


def loading_hub(monkeypatch, loaded: dict) -> SimpleNamespace:
    """Just enough of the cog to run cog_load and cog_unload, with `loaded` as the cogs already loaded"""
    hub = make_hub()
    hub.steps = []
    monkeypatch.setattr(main, "OpenView", lambda cog: SimpleNamespace(stop=lambda: hub.steps.append("view stopped")))
    monkeypatch.setattr(main, "keep_entry_point", lambda bot: hub.steps.append("sync hook"))
    monkeypatch.setattr(main, "drop_entry_point_hook", lambda bot, hook: hub.steps.append("sync hook dropped"))
    hub.bot = SimpleNamespace(cogs=loaded, add_view=lambda view: hub.steps.append("view"), get_cog=loaded.get)

    async def start_server():
        await asyncio.sleep(0)
        hub.steps.append("server")

    async def stop_server():
        hub.steps.append("server stopped")

    hub.start_server = start_server
    hub.server = SimpleNamespace(stop=stop_server)
    hub.add_game = lambda cog: ActivityHub.add_game(hub, cog)
    return hub


@pytest.mark.asyncio
async def test_cog_load_does_not_wait_for_game_cogs_describing_themselves(monkeypatch, tmp_path):
    waiting = WaitingGame(write_demo_web(tmp_path / "demo"))
    plain = SimpleNamespace(qualified_name="Plain")
    hub = loading_hub(monkeypatch, {"Plain": plain})
    starting = hub.start_server

    async def start_server():
        await starting()
        # Loaded while the server was starting, so the scan that comes last still sees it
        hub.bot.cogs["Demo"] = waiting

    hub.start_server = start_server
    await asyncio.wait_for(ActivityHub.cog_load(hub), 1)
    assert hub.steps == ["sync hook", "view", "server"]
    assert set(hub.registry.games) == {"snake", "2048", "brickbreaker"}
    # Only game cogs get a task
    assert len(hub.scans) == 1
    waiting.go.set()
    await asyncio.wait_for(hub.scans[0], 1)
    assert hub.registry.games["demo"].cog is waiting


@pytest.mark.asyncio
async def test_cog_unload_cancels_a_scan_still_waiting(monkeypatch, tmp_path):
    waiting = WaitingGame(write_demo_web(tmp_path / "demo"))
    hub = loading_hub(monkeypatch, {"Demo": waiting})
    await asyncio.wait_for(ActivityHub.cog_load(hub), 1)
    await ActivityHub.cog_unload(hub)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(hub.scans[0], 1)
    assert "demo" not in hub.registry.games
    assert hub.steps == ["sync hook", "view", "server", "sync hook dropped", "view stopped", "server stopped"]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("registry broke"), asyncio.CancelledError()])
async def test_a_failed_cog_load_releases_the_port(monkeypatch, hub, server, failure):
    stopped = []
    monkeypatch.setattr(main, "OpenView", lambda cog: SimpleNamespace(stop=lambda: stopped.append("view")))
    monkeypatch.setattr(main, "keep_entry_point", lambda bot: "hook")
    monkeypatch.setattr(main, "drop_entry_point_hook", lambda bot, hook: stopped.append(f"sync {hook}"))
    port = free_port()
    await hub.config.port.set(port)
    hub.bot.add_view = lambda view: None
    hub.server = server
    hub.start_server = lambda: ActivityHub.start_server(hub)

    async def add(cog):
        assert server.running
        raise failure

    hub.registry.add = add
    with pytest.raises(type(failure)):
        await ActivityHub.cog_load(hub)
    assert not server.running and stopped == ["sync hook", "view"]
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen()


class CountingCog(DemoCog):
    """Counts how often the hub asks it to describe itself"""

    def __init__(self, web_dir, **kwargs):
        super().__init__(web_dir, **kwargs)
        self.asked = 0

    async def activityhub_game(self) -> dict:
        self.asked += 1
        return await super().activityhub_game()


@pytest.mark.asyncio
async def test_a_cog_refused_for_a_taken_key_gets_it_when_the_holder_unloads(tmp_path):
    holder = DemoCog(write_demo_web(tmp_path / "a"), key="tetris", cog_name="TetrisA")
    waiting = CountingCog(write_demo_web(tmp_path / "b"), key="tetris", cog_name="TetrisB")
    broken = CountingCog(write_demo_web(tmp_path / "c"), key="Not A Key", cog_name="Broken")
    other = DemoCog(write_demo_web(tmp_path / "d"), key="other", cog_name="Other")
    loaded = {cog.qualified_name: cog for cog in (holder, waiting, broken, other)}
    hub = make_hub()
    hub.bot = SimpleNamespace(get_cog=loaded.get)
    hub.server = SimpleNamespace(rooms=Rooms())
    hub.add_game = lambda cog: ActivityHub.add_game(hub, cog)
    for cog in loaded.values():
        await ActivityHub.add_game(hub, cog)
    assert hub.registry.games["tetris"].cog is holder and "TetrisB" in hub.registry.failed

    # A key that nobody was waiting for frees nothing
    del loaded["Other"]
    await ActivityHub.on_cog_remove(hub, other)
    assert waiting.asked == 1 and "TetrisB" in hub.registry.failed

    del loaded["TetrisA"]
    await ActivityHub.on_cog_remove(hub, holder)
    assert hub.registry.games["tetris"].cog is waiting
    assert "TetrisB" not in hub.registry.failed and hub.registry.clashes == {}
    # Refused for a reason that unloading another cog can't fix
    assert broken.asked == 1 and "Broken" in hub.registry.failed


@pytest.mark.asyncio
async def test_a_refused_cog_that_unloaded_is_not_retried(tmp_path):
    holder = DemoCog(write_demo_web(tmp_path / "a"), key="tetris", cog_name="TetrisA")
    waiting = CountingCog(write_demo_web(tmp_path / "b"), key="tetris", cog_name="TetrisB")
    hub = make_hub()
    hub.server = SimpleNamespace(rooms=Rooms())
    hub.add_game = lambda cog: ActivityHub.add_game(hub, cog)
    await hub.registry.add(holder)
    await hub.registry.add(waiting)
    # TetrisB's failure entry is kept until its own on_cog_remove runs, but it is no longer loaded
    hub.bot = SimpleNamespace(get_cog=lambda name: None)
    await ActivityHub.on_cog_remove(hub, holder)
    assert waiting.asked == 1 and hub.registry.games == {}


@pytest.mark.asyncio
async def test_the_holders_players_are_let_go_before_the_waiting_cog_takes_the_key(tmp_path):
    holder = DemoCog(write_demo_web(tmp_path / "a"), key="tetris", cog_name="TetrisA")
    waiting = WaitingGame(write_demo_web(tmp_path / "b"), key="tetris", cog_name="TetrisB")
    loaded = {"TetrisB": waiting}
    hub = make_hub()
    hub.bot = SimpleNamespace(get_cog=loaded.get)
    closed = []

    async def close_stale(games):
        closed.append(set(games))

    hub.server = SimpleNamespace(rooms=SimpleNamespace(close_stale=close_stale))
    hub.add_game = lambda cog: ActivityHub.add_game(hub, cog)
    await hub.registry.add(holder)
    waiting.go.set()
    await hub.registry.add(waiting)
    waiting.go.clear()
    removing = asyncio.create_task(ActivityHub.on_cog_remove(hub, holder))
    await asyncio.sleep(0)
    # TetrisB is still describing itself, and TetrisA's connections are already closed
    assert closed == [set()] and not removing.done()
    waiting.go.set()
    await asyncio.wait_for(removing, 1)
    assert hub.registry.games["tetris"].cog is waiting


@pytest.mark.asyncio
@pytest.mark.parametrize("still_loaded", [True, False])
async def test_add_game_drops_a_cog_that_unloaded_while_describing_itself(tmp_path, still_loaded):
    cog = DemoCog(write_demo_web(tmp_path / "demo"))
    hub = make_hub()
    hub.bot = SimpleNamespace(get_cog=lambda name: cog if still_loaded else None)
    await ActivityHub.add_game(hub, cog)
    assert ("demo" in hub.registry.games) is still_loaded


@pytest.mark.asyncio
async def test_an_old_copy_finishing_after_its_reload_keeps_the_new_game(tmp_path):
    web = write_demo_web(tmp_path / "demo")
    release = asyncio.Event()

    class SlowDemo(DemoCog):
        async def activityhub_game(self):
            await release.wait()
            return await super().activityhub_game()

    old, new = SlowDemo(web), DemoCog(web)
    loaded = {"cog": old}
    hub = make_hub()
    hub.bot = SimpleNamespace(get_cog=lambda name: loaded["cog"])
    describing = asyncio.create_task(ActivityHub.add_game(hub, old))
    await asyncio.sleep(0)
    # [p]reload: the new copy registers while the old one is still describing itself
    loaded["cog"] = new
    await ActivityHub.add_game(hub, new)
    release.set()
    await asyncio.wait_for(describing, 1)
    assert hub.registry.games["demo"].cog is new
