from types import SimpleNamespace

import discord
import pytest
from redbot.core import commands

from activityhub.commands import user as user_commands
from activityhub.commands.user import UserCommands
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, DemoCog, make_hub, register, write_demo_web


class HubCog(UserCommands):
    """Just enough of the cog to run launch()"""

    def __init__(self, hub):
        self.bot = hub.bot
        self.config = hub.config
        self.registry = hub.registry
        self.launches = hub.launches


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.deferred = False

    async def send_message(self, content, ephemeral=False):
        self.sent.append((content, ephemeral))

    async def defer(self):
        self.deferred = True

    def is_done(self):
        return self.deferred or bool(self.sent)


def interaction(in_guild=True):
    return SimpleNamespace(
        id=1,
        token="token",
        user=SimpleNamespace(id=MEMBER_ID),
        guild=SimpleNamespace(id=GUILD_ID) if in_guild else None,
        guild_id=GUILD_ID if in_guild else None,
        response=FakeResponse(),
    )


@pytest.fixture
def discord_calls(monkeypatch):
    calls = {"enabled": True, "launched": [], "fail": False}

    async def activities_enabled(bot):
        return calls["enabled"]

    async def launch_activity(bot, inter):
        if calls["fail"]:
            raise discord.HTTPException(SimpleNamespace(status=400, reason="Bad Request"), "nope")
        calls["launched"].append(inter)

    monkeypatch.setattr(user_commands, "activities_enabled", activities_enabled)
    monkeypatch.setattr(user_commands, "launch_activity", launch_activity)
    return calls


@pytest.fixture
def cog(tmp_path):
    hub = make_hub()
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    return HubCog(hub)


@pytest.mark.asyncio
async def test_activities_off_for_the_bot(cog, discord_calls):
    discord_calls["enabled"] = False
    inter = interaction()
    await cog.launch(inter, "demo")
    assert discord_calls["launched"] == []
    assert inter.response.sent and inter.response.sent[0][1] is True
    assert cog.launches.take(MEMBER_ID) is None


@pytest.mark.asyncio
async def test_menu_launch_remembers_nothing(cog, discord_calls):
    inter = interaction()
    assert await cog.launch(inter) is True
    assert discord_calls["launched"] == [inter]
    assert cog.launches.take(MEMBER_ID) is None


@pytest.mark.asyncio
async def test_game_launch_remembers_the_game(cog, discord_calls):
    assert await cog.launch(interaction(), "demo") is True
    assert len(discord_calls["launched"]) == 1
    assert cog.launches.take(MEMBER_ID) == "demo"


@pytest.mark.asyncio
async def test_unknown_game_is_refused(cog, discord_calls):
    inter = interaction()
    assert await cog.launch(inter, "nope") is False
    assert discord_calls["launched"] == [] and "isn't installed" in inter.response.sent[0][0]


@pytest.mark.asyncio
async def test_turned_off_game_is_refused(cog, discord_calls):
    await cog.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    inter = interaction()
    assert await cog.launch(inter, "demo") is False
    assert discord_calls["launched"] == [] and "turned off" in inter.response.sent[0][0]
    assert cog.launches.take(MEMBER_ID) is None


@pytest.mark.asyncio
async def test_dms_ignore_server_switches(cog, discord_calls):
    await cog.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    await cog.launch(interaction(in_guild=False), "demo")
    assert len(discord_calls["launched"]) == 1


@pytest.mark.asyncio
async def test_game_off_everywhere_is_refused_in_dms_too(cog, discord_calls):
    await cog.config.disabled.set(["demo"])
    for in_guild in (True, False):
        inter = interaction(in_guild)
        await cog.launch(inter, "demo")
        assert "turned off on this bot" in inter.response.sent[0][0]
    assert discord_calls["launched"] == [] and cog.launches.take(MEMBER_ID) is None


@pytest.mark.asyncio
async def test_a_refused_launch_is_logged_not_raised(cog, discord_calls, caplog):
    discord_calls["fail"] = True
    assert await cog.launch(interaction(), "demo") is False
    assert "Activity launch failed" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_launch_forgets_the_game(cog, discord_calls):
    # Remembered, it would open by itself the next time the player opens the menu, maybe much later
    discord_calls["fail"] = True
    await cog.launch(interaction(), "demo")
    assert cog.launches.wanted == {}


@pytest.mark.asyncio
async def test_activities_off_returns_false(cog, discord_calls):
    discord_calls["enabled"] = False
    assert await cog.launch(interaction()) is False


def command_context(inter) -> commands.Context:
    """A Red command context, as a hybrid command gets: inter is None when it ran as a text command"""
    ctx = commands.Context.__new__(commands.Context)
    ctx.interaction = inter
    return ctx


@pytest.mark.asyncio
async def test_a_text_command_context_is_refused_with_a_fix(cog, discord_calls):
    with pytest.raises(TypeError) as caught:
        await cog.launch(command_context(None), "demo")
    assert str(caught.value) == (
        "hub.launch() needs the discord.Interaction from a button press or slash command. "
        "A text command has none: post a button that calls launch instead (DEVELOPERS.md section 13)."
    )
    assert discord_calls["launched"] == [] and cog.launches.wanted == {}


@pytest.mark.asyncio
async def test_a_hybrid_command_run_as_a_slash_command_launches(cog, discord_calls):
    inter = interaction()
    assert await cog.launch(command_context(inter), "demo") is True
    assert discord_calls["launched"] == [inter]
    assert cog.launches.take(MEMBER_ID) == "demo"


@pytest.mark.asyncio
async def test_a_hybrid_command_refusal_answers_its_interaction(cog, discord_calls):
    inter = interaction()
    assert await cog.launch(command_context(inter), "nope") is False
    assert "isn't installed" in inter.response.sent[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_reply", ["defer", "send_message"])
async def test_launch_must_be_the_first_reply(cog, discord_calls, first_reply):
    inter = interaction()
    if first_reply == "defer":
        await inter.response.defer()
    else:
        await inter.response.send_message("Opening...")
    with pytest.raises(RuntimeError) as caught:
        await cog.launch(inter, "demo")
    assert str(caught.value) == (
        "hub.launch() must be the first reply to this interaction. Remove the defer() or send_message() before it."
    )
    assert discord_calls["launched"] == [] and cog.launches.wanted == {}
