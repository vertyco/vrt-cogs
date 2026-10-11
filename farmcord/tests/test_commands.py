from types import SimpleNamespace

import pytest
import pytest_asyncio

from farmcord.main import FarmCord
from farmcord.tests.fakes import FakeHub, FakeInteraction, Said, make_cog
from farmcord.views.play import PlayView

CREDIT_LINE = "Game design by Vainne: https://github.com/Atuelliss"


@pytest_asyncio.fixture
async def cog(store):
    return await make_cog(store)


def test_the_commands_are_farmcord_its_version_and_the_slash_command():
    cog = FarmCord(bot=None)
    assert {command.qualified_name for command in cog.walk_commands()} == {"farmcord", "farmcord version"}
    assert [command.name for command in cog.get_app_commands()] == ["farmcord"]
    # The farm is global, so the commands work in DMs too
    assert not any("guild_only" in check.__qualname__ for command in cog.walk_commands() for check in command.checks)
    assert cog.get_app_commands()[0].guild_only is False


@pytest.mark.asyncio
async def test_farmcord_posts_the_play_button(cog):
    cog.play_view = PlayView(cog)
    said = Said(cog)
    await FarmCord.farmcord_group.callback(cog, said)
    assert said.sent == [("Press to play:", cog.play_view)]


@pytest.mark.asyncio
async def test_the_version_command_shows_the_credit(cog):
    said = Said(cog)
    await FarmCord.farmcord_version.callback(cog, said)
    assert said.sent == [(f"FarmCord is running version {FarmCord.__version__}.\n{CREDIT_LINE}", None)]


def test_the_help_text_carries_the_version_author_and_credit():
    ctx = SimpleNamespace(clean_prefix="[p]", me=SimpleNamespace(display_name="Bot"))
    text = FarmCord(bot=None).format_help_for_context(ctx)
    assert CREDIT_LINE in FarmCord.__doc__
    assert text.endswith(f"Version: 0.1.0\nAuthor: Vertyco\n{CREDIT_LINE}")


@pytest.mark.asyncio
async def test_the_slash_command_opens_the_game_or_says_activityhub_is_missing(cog):
    alone = FakeInteraction()
    await FarmCord.farmcord_slash.callback(cog, alone)
    assert alone.replies == [("FarmCord needs the ActivityHub cog.", True)]
    hub = cog.bot.cogs["ActivityHub"] = FakeHub()
    pressed = FakeInteraction()
    await FarmCord.farmcord_slash.callback(cog, pressed)
    assert hub.launched == [(pressed, "farmcord")] and pressed.replies == []


@pytest.mark.asyncio
async def test_the_play_button_opens_the_game(cog):
    view = PlayView(cog)
    alone = FakeInteraction()
    await view.play.callback(alone)
    assert alone.replies == [("FarmCord needs the ActivityHub cog.", True)]
    hub = cog.bot.cogs["ActivityHub"] = FakeHub()
    pressed = FakeInteraction()
    await view.play.callback(pressed)
    assert hub.launched == [(pressed, "farmcord")]


@pytest.mark.asyncio
async def test_the_play_button_keeps_working_after_a_restart(cog):
    await cog.cog_load()
    view = cog.play_view
    assert cog.bot.views == [view] and view.timeout is None
    assert [item.custom_id for item in view.children] == ["farmcord:play"]
    await cog.cog_unload()
    assert view.is_finished() and cog.starting.done() and not cog.ready.is_set()
