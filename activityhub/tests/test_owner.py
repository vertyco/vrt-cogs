from types import SimpleNamespace

import discord
import pytest

from activityhub.bundled.games import Snake
from activityhub.commands.owner import OwnerCommands
from activityhub.common.setup_guide import README_URL
from activityhub.tests.fakes import OWNER_ID, DemoCog, make_hub, write_demo_web


class HubCog(OwnerCommands):
    """Just enough of the cog to run the owner commands"""

    def __init__(self, hub):
        self.bot = hub.bot
        self.config = hub.config
        self.registry = hub.registry
        self.server = SimpleNamespace(running=True)


def fake_ctx() -> SimpleNamespace:
    owner = SimpleNamespace(id=OWNER_ID)
    ctx = SimpleNamespace(sent=[], embeds=[], views=[], clean_prefix="[p]", author=owner, channel=None, guild=None)

    async def send(content=None, embed=None, view=None):
        if content:
            ctx.sent.append(content)
        if embed:
            ctx.embeds.append(embed)
        if view:
            ctx.views.append(view)

    async def embed_color():
        return discord.Color.blurple()

    ctx.send = send
    ctx.embed_color = embed_color
    return ctx


def field(embed: discord.Embed, name: str) -> str:
    return next(str(f.value) for f in embed.fields if f.name == name)


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


@pytest.mark.asyncio
async def test_view_shows_the_address_the_default_and_what_is_missing(tmp_path):
    hub = make_hub()
    await hub.registry.add(DemoCog(write_demo_web(tmp_path / "demo")))
    await hub.registry.add(Snake(hub.scores))
    await hub.config.host.set("0.0.0.0")
    await hub.config.port.set(9000)
    await hub.config.disabled.set(["demo", "gone"])
    hub.bot.tokens = {}
    cog = HubCog(hub)
    cog.server.running = False
    ctx = fake_ctx()
    await OwnerCommands.view_settings.callback(cog, ctx)
    embed = ctx.embeds[0]
    server = field(embed, "Web server")
    assert "Listens on `0.0.0.0:9000`" in server
    assert "**Not running.**" in server
    assert "The default is `127.0.0.1:8742`." in server
    assert field(embed, "Client secret") == "Not set. Run `[p]activityhub secret`."
    assert field(embed, "Activities").startswith("2 installed, 1 turned off for every server.")


@pytest.mark.asyncio
async def test_view_says_a_saved_secret_is_saved_without_showing_it():
    hub = make_hub()
    hub.bot.tokens = {"client_secret": "s3cr3t-value"}
    ctx = fake_ctx()
    await OwnerCommands.view_settings.callback(HubCog(hub), ctx)
    embed = ctx.embeds[0]
    assert field(embed, "Client secret") == "Saved"
    assert "Running" in field(embed, "Web server")
    assert not any("s3cr3t-value" in f.value for f in embed.fields)


@pytest.mark.asyncio
async def test_setup_sends_the_guide_with_page_buttons():
    hub = make_hub()
    ctx = fake_ctx()
    await OwnerCommands.setup_guide.callback(HubCog(hub), ctx)
    first = ctx.embeds[0]
    assert first.title == "ActivityHub setup"
    assert first.url == README_URL
    assert "`127.0.0.1:8742` and is running" in first.description
    assert first.footer.text.startswith("Page 1/")
    assert ctx.views and ctx.views[0].page_count == len(ctx.views[0].pages)
