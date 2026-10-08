import asyncio
from types import SimpleNamespace

import pytest

from activityhub import main
from activityhub.main import ActivityHub
from activityhub.bundled.scores import ScoreBoard
from activityhub.common.games import GameRegistry
from activityhub.tests.fakes import DemoCog, FakeConfig, make_hub, write_demo_web


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


@pytest.mark.asyncio
async def test_cog_load_adds_the_bundled_games_then_scans_loaded_cogs(monkeypatch):
    steps = []
    monkeypatch.setattr(main, "OpenView", lambda cog: SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(main, "keep_entry_point", lambda bot: steps.append("sync hook"))

    async def start_server():
        await asyncio.sleep(0)
        steps.append("server")

    async def add_game(cog):
        steps.append(f"scan {cog}")

    fake = SimpleNamespace(
        bot=SimpleNamespace(cogs={"a": "cog-a"}, add_view=lambda view: steps.append("view")),
        add_game=add_game,
        start_server=start_server,
        registry=GameRegistry(),
        scores=ScoreBoard(FakeConfig()),
    )
    await ActivityHub.cog_load(fake)
    assert steps == ["sync hook", "view", "server", "scan cog-a"]
    assert set(fake.registry.games) == {"snake", "2048", "brickbreaker"}


@pytest.mark.asyncio
@pytest.mark.parametrize("still_loaded", [True, False])
async def test_add_game_drops_a_cog_that_unloaded_while_describing_itself(tmp_path, still_loaded):
    cog = DemoCog(write_demo_web(tmp_path / "demo"))
    hub = make_hub()
    hub.bot = SimpleNamespace(get_cog=lambda name: cog if still_loaded else None)
    await ActivityHub.add_game(hub, cog)
    assert ("demo" in hub.registry.games) is still_loaded
