from types import SimpleNamespace

import discord
import pytest

from activityhub.commands.user import UserCommands
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID
from activityhub.views.launch import CUSTOM_ID, LaunchButton

BOT_ID = 900


class HubCog(UserCommands):
    """Just enough of the cog to run the pin commands"""

    def __init__(self):
        self.bot = SimpleNamespace(user=SimpleNamespace(id=BOT_ID))


def button(custom_id: str, label: str = "Other") -> dict:
    return {"type": 2, "style": 1, "custom_id": custom_id, "label": label}


def row(*buttons: dict) -> discord.components.ActionRow:
    return discord.components.ActionRow({"type": 1, "components": list(buttons)})


class FakeMessage:
    def __init__(self, components=(), author_id=BOT_ID, guild_id=GUILD_ID, v2=False, fail=False):
        self.id = 42
        self.author = SimpleNamespace(id=author_id)
        self.guild = SimpleNamespace(id=guild_id)
        self.channel = SimpleNamespace(id=77)
        self.flags = SimpleNamespace(components_v2=v2)
        self.components = list(components)
        self.fail = fail
        self.edits = []

    async def edit(self, view):
        if self.fail:
            raise discord.HTTPException(SimpleNamespace(status=400, reason="Bad Request"), "nope")
        self.edits.append(view)

    def custom_ids(self) -> list[str | None]:
        return [getattr(item, "custom_id", None) for item in self.edits[-1].walk_children()]


def fake_ctx() -> SimpleNamespace:
    ctx = SimpleNamespace(sent=[], guild=SimpleNamespace(id=GUILD_ID))

    async def send(content):
        ctx.sent.append(content)

    ctx.send = send
    return ctx


async def pin(message) -> SimpleNamespace:
    ctx = fake_ctx()
    await UserCommands.pin_button.callback(HubCog(), ctx, message)
    return ctx


async def unpin(message) -> SimpleNamespace:
    ctx = fake_ctx()
    await UserCommands.unpin_button.callback(HubCog(), ctx, message)
    return ctx


def test_buttons_posted_before_still_match():
    # Buttons posted by [p]activities before the button was dynamic use the same custom_id
    assert LaunchButton.__discord_ui_compiled_template__.fullmatch("activityhub:open")
    assert LaunchButton().custom_id == CUSTOM_ID


@pytest.mark.asyncio
async def test_pressing_the_button_opens_the_activity():
    launched = []

    async def launch(interaction):
        launched.append(interaction)

    cog = SimpleNamespace(launch=launch)
    interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: cog if name == "ActivityHub" else None))
    await LaunchButton().callback(interaction)
    assert launched == [interaction]


@pytest.mark.asyncio
async def test_pressing_the_button_while_the_hub_is_unloaded_says_so():
    sent = []

    async def send_message(content, ephemeral=False):
        sent.append((content, ephemeral))

    interaction = SimpleNamespace(
        client=SimpleNamespace(get_cog=lambda name: None), response=SimpleNamespace(send_message=send_message)
    )
    await LaunchButton().callback(interaction)
    assert sent == [("Activities aren't loaded right now.", True)]


@pytest.mark.asyncio
async def test_pin_keeps_the_other_buttons():
    message = FakeMessage([row(button("tickets:open"), button("tickets:close"))])
    ctx = await pin(message)
    assert ctx.sent == ["Added the Open Activities button to that message."]
    assert message.custom_ids() == ["tickets:open", "tickets:close", CUSTOM_ID]
    # discord.py stores a view that isn't finished for the message, and its copied buttons would take the presses
    # meant for the cog that posted them
    assert message.edits[0].is_finished()


@pytest.mark.asyncio
async def test_pin_on_a_message_without_buttons():
    message = FakeMessage()
    await pin(message)
    assert message.custom_ids() == [CUSTOM_ID]


@pytest.mark.asyncio
async def test_pin_refuses_a_message_the_bot_did_not_send():
    message = FakeMessage(author_id=MEMBER_ID)
    ctx = await pin(message)
    assert ctx.sent == ["I can only change messages I sent."] and not message.edits


@pytest.mark.asyncio
async def test_pin_refuses_a_message_in_another_server():
    message = FakeMessage(guild_id=GUILD_ID + 1)
    ctx = await pin(message)
    assert ctx.sent == ["That message isn't in this server."] and not message.edits


@pytest.mark.asyncio
async def test_pin_twice_says_it_is_already_there():
    message = FakeMessage([row(button(CUSTOM_ID, "Open Activities"))])
    ctx = await pin(message)
    assert ctx.sent == ["That message already has the button."] and not message.edits


@pytest.mark.asyncio
async def test_pin_on_a_full_message_says_there_is_no_room():
    message = FakeMessage([row(*(button(f"other:{r}:{b}") for b in range(5))) for r in range(5)])
    ctx = await pin(message)
    assert ctx.sent == ["That message has no room for another button."] and not message.edits


@pytest.mark.asyncio
async def test_a_failed_edit_is_logged_and_reported(caplog):
    message = FakeMessage(fail=True)
    ctx = await pin(message)
    assert ctx.sent == ["Discord wouldn't let me change that message's buttons."]
    assert "Couldn't change the buttons on message 42" in caplog.text


@pytest.mark.asyncio
async def test_unpin_keeps_the_other_buttons():
    message = FakeMessage([row(button("tickets:open"), button(CUSTOM_ID, "Open Activities"))])
    ctx = await unpin(message)
    assert ctx.sent == ["Took the Open Activities button off that message."]
    assert message.custom_ids() == ["tickets:open"]
    assert message.edits[0].is_finished()


@pytest.mark.asyncio
async def test_unpin_without_the_button_says_so():
    message = FakeMessage([row(button("tickets:open"))])
    ctx = await unpin(message)
    assert ctx.sent == ["That message doesn't have the button."] and not message.edits


@pytest.mark.asyncio
async def test_pin_and_unpin_on_a_components_v2_message():
    text = discord.components.TextDisplay({"type": 10, "id": 1, "content": "Welcome!"})
    message = FakeMessage([text], v2=True)
    await pin(message)
    pinned = message.edits[-1]
    assert isinstance(pinned, discord.ui.LayoutView)
    assert [type(item) for item in pinned.children] == [discord.ui.TextDisplay, discord.ui.ActionRow]
    # The next command reads the message as Discord now shows it
    message.components = [text, row(button(CUSTOM_ID, "Open Activities"))]
    await unpin(message)
    # The row the button sat in goes too, since Discord refuses an empty one
    assert [type(item) for item in message.edits[-1].children] == [discord.ui.TextDisplay]
