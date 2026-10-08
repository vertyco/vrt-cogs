from types import SimpleNamespace

import pytest

from activityhub.bundled.games import Snake
from activityhub.commands.owner import OwnerCommands
from activityhub.tests.fakes import DemoCog, make_hub, write_demo_web


class HubCog(OwnerCommands):
    """Just enough of the cog to run the owner commands"""

    def __init__(self, hub):
        self.bot = hub.bot
        self.config = hub.config
        self.registry = hub.registry


def fake_ctx() -> SimpleNamespace:
    ctx = SimpleNamespace(sent=[])

    async def send(content):
        ctx.sent.append(content)

    ctx.send = send
    return ctx


@pytest.mark.asyncio
async def test_games_lists_the_scopes_each_game_asks_for(tmp_path):
    hub = make_hub()
    await hub.registry.add(DemoCog(write_demo_web(tmp_path / "demo")))
    await hub.registry.add(Snake(hub.scores))
    await hub.config.disabled.set(["demo"])
    ctx = fake_ctx()
    await OwnerCommands.list_games.callback(HubCog(hub), ctx)
    lines = "".join(ctx.sent).splitlines()
    assert "demo: Demo (Demo) [turned off] scopes: guilds.members.read" in lines
    assert "snake: Snake (ActivityHub Snake)" in lines
