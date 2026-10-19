from types import SimpleNamespace

import discord
import pytest

from activityhub.commands.user import PinOptions, UserCommands
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID
from activityhub.views.launch import CUSTOM_ID, LaunchButton

SNAKE_ID = f"{CUSTOM_ID}:snake"

BOT_ID = 900


class HubCog(UserCommands):
    """Just enough of the cog to run the pin commands"""

    def __init__(self):
        self.bot = SimpleNamespace(user=SimpleNamespace(id=BOT_ID))
        games = [SimpleNamespace(key="snake", name="Snake"), SimpleNamespace(key="brickbreaker", name="Brick Breaker")]
        self.registry = SimpleNamespace(games={game.key: game for game in games})


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


async def pin(message, options: str | None = None) -> SimpleNamespace:
    """`options` is the text typed after the message, parsed the way the command parses it"""
    ctx = fake_ctx()
    if options is not None:
        options = await PinOptions.convert(SimpleNamespace(command=None, current_parameter=None), options)
    await UserCommands.pin_button.callback(HubCog(), ctx, message, options=options)
    return ctx


def pinned_button(message: FakeMessage, custom_id: str = CUSTOM_ID) -> discord.ui.Button:
    found = next(item for item in message.edits[-1].walk_children() if getattr(item, "custom_id", None) == custom_id)
    # A newly added button is a LaunchButton, which holds the real button
    return found.item if isinstance(found, LaunchButton) else found


async def unpin(message, game: str | None = None) -> SimpleNamespace:
    ctx = fake_ctx()
    await UserCommands.unpin_button.callback(HubCog(), ctx, message, game=game)
    return ctx


def test_buttons_posted_before_still_match():
    # Buttons posted by [p]activities before the button was dynamic use the same custom_id
    assert LaunchButton.__discord_ui_compiled_template__.fullmatch("activityhub:open")
    assert LaunchButton().custom_id == CUSTOM_ID


@pytest.mark.asyncio
async def test_pressing_the_button_opens_the_activity():
    launched = []

    async def launch(interaction, key=None):
        launched.append((interaction, key))

    cog = SimpleNamespace(launch=launch)
    interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: cog if name == "ActivityHub" else None))
    await LaunchButton().callback(interaction)
    assert launched == [(interaction, None)]


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
    assert ctx.sent == ["Added the Open Activity Hub button to that message."]
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
    message = FakeMessage([row(button(CUSTOM_ID, "Open Activity Hub"))])
    ctx = await pin(message)
    assert ctx.sent == ["That message already has the Open Activity Hub button."] and not message.edits


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
    message = FakeMessage([row(button("tickets:open"), button(CUSTOM_ID, "Open Activity Hub"))])
    ctx = await unpin(message)
    assert ctx.sent == ["Took the Open Activity Hub button off that message."]
    assert message.custom_ids() == ["tickets:open"]
    assert message.edits[0].is_finished()


@pytest.mark.asyncio
async def test_unpin_without_the_button_says_so():
    message = FakeMessage([row(button("tickets:open"))])
    ctx = await unpin(message)
    assert ctx.sent == ["That message doesn't have the Open Activity Hub button."] and not message.edits


@pytest.mark.asyncio
async def test_pin_and_unpin_on_a_components_v2_message():
    text = discord.components.TextDisplay({"type": 10, "id": 1, "content": "Welcome!"})
    message = FakeMessage([text], v2=True)
    await pin(message)
    pinned = message.edits[-1]
    assert isinstance(pinned, discord.ui.LayoutView)
    assert [type(item) for item in pinned.children] == [discord.ui.TextDisplay, discord.ui.ActionRow]
    # The next command reads the message as Discord now shows it
    message.components = [text, row(button(CUSTOM_ID, "Open Activity Hub"))]
    await unpin(message)
    # The row the button sat in goes too, since Discord refuses an empty one
    assert [type(item) for item in message.edits[-1].children] == [discord.ui.TextDisplay]


@pytest.mark.asyncio
async def test_pin_without_a_look_uses_the_default_button():
    message = FakeMessage()
    await pin(message)
    button = pinned_button(message)
    assert (button.label, button.emoji, button.style) == ("Open Activity Hub", None, discord.ButtonStyle.success)


@pytest.mark.asyncio
async def test_pin_with_a_label_emoji_and_color():
    message = FakeMessage([row(button("tickets:open"))])
    ctx = await pin(message, "Play games emoji: 🎮 color: Blurple")
    assert ctx.sent == ["Added the Open Activity Hub button to that message."]
    pinned = pinned_button(message)
    assert pinned.label == "Play games"
    assert str(pinned.emoji) == "🎮"
    assert pinned.style == discord.ButtonStyle.primary
    assert message.custom_ids() == ["tickets:open", CUSTOM_ID]


@pytest.mark.asyncio
async def test_pin_with_a_custom_server_emoji():
    message = FakeMessage()
    await pin(message, "emoji: <:pog:123456789012345678>")
    emoji = pinned_button(message).emoji
    assert (emoji.name, emoji.id) == ("pog", 123456789012345678)
    assert pinned_button(message).label == "Open Activity Hub"


@pytest.mark.asyncio
async def test_pin_again_changes_only_the_parts_given():
    pinned = {"type": 2, "style": 1, "custom_id": CUSTOM_ID, "label": "Play", "emoji": {"name": "🎮"}}
    message = FakeMessage([row(button("tickets:open"), pinned)])
    ctx = await pin(message, "color: red")
    assert ctx.sent == ["Changed the Open Activity Hub button on that message."]
    changed = pinned_button(message)
    assert (changed.label, str(changed.emoji), changed.style) == ("Play", "🎮", discord.ButtonStyle.danger)
    assert message.custom_ids() == ["tickets:open", CUSTOM_ID]
    assert message.edits[0].is_finished()


@pytest.mark.asyncio
async def test_pin_again_on_a_components_v2_message_changes_the_button():
    text = discord.components.TextDisplay({"type": 10, "id": 1, "content": "Welcome!"})
    message = FakeMessage([text, row(button(CUSTOM_ID, "Open Activity Hub"))], v2=True)
    await pin(message, "Join in")
    assert isinstance(message.edits[-1], discord.ui.LayoutView)
    assert pinned_button(message).label == "Join in"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("look", "reply"),
    [
        ("emoji: smile", "`smile` isn't an emoji."),
        ("color: pink", "The color can be blurple, grey, green or red."),
        ("x" * 81, "A button's label can be at most 80 characters."),
    ],
)
async def test_pin_with_a_bad_look_says_what_is_wrong(look, reply):
    message = FakeMessage()
    ctx = await pin(message, look)
    assert ctx.sent == [reply] and not message.edits


@pytest.mark.asyncio
async def test_a_game_button_opens_that_game_after_a_restart():
    template = LaunchButton.__discord_ui_compiled_template__
    match = template.fullmatch(SNAKE_ID)
    button = await LaunchButton.from_custom_id(None, None, match)
    assert button.key == "snake" and button.custom_id == SNAKE_ID
    assert template.fullmatch(f"{CUSTOM_ID}:Not A Key") is None
    launched = []

    async def launch(interaction, key=None):
        launched.append(key)

    cog = SimpleNamespace(launch=launch)
    await button.callback(SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: cog)))
    assert launched == ["snake"]


@pytest.mark.asyncio
async def test_pin_a_game_next_to_the_menu_button():
    message = FakeMessage([row(button(CUSTOM_ID, "Open Activity Hub"))])
    ctx = await pin(message, "game: snake")
    assert ctx.sent == ["Added the Snake button to that message."]
    assert message.custom_ids() == [CUSTOM_ID, SNAKE_ID]
    game = pinned_button(message, SNAKE_ID)
    assert (game.label, game.style) == ("Play Snake", discord.ButtonStyle.success)


@pytest.mark.asyncio
async def test_pin_a_game_by_its_name_with_a_look():
    message = FakeMessage()
    await pin(message, "Bricks! game: brick breaker color: grey")
    game = pinned_button(message, f"{CUSTOM_ID}:brickbreaker")
    assert (game.label, game.style) == ("Bricks!", discord.ButtonStyle.secondary)


@pytest.mark.asyncio
async def test_pin_a_game_that_is_not_installed_lists_the_games():
    message = FakeMessage()
    ctx = await pin(message, "game: tetris")
    assert ctx.sent == ["No game called `tetris` is installed. The games are: Brick Breaker, Snake"]
    assert not message.edits


@pytest.mark.asyncio
async def test_pin_a_game_twice_and_restyle_it():
    message = FakeMessage([row(button(SNAKE_ID, "Play Snake"))])
    ctx = await pin(message, "game: Snake")
    assert ctx.sent == ["That message already has the Snake button."] and not message.edits
    ctx = await pin(message, "game: Snake emoji: 🐍")
    assert ctx.sent == ["Changed the Snake button on that message."]
    assert str(pinned_button(message, SNAKE_ID).emoji) == "🐍"


@pytest.mark.asyncio
async def test_unpin_a_game_keeps_the_menu_button():
    message = FakeMessage([row(button(CUSTOM_ID, "Open Activity Hub"), button(SNAKE_ID, "Play Snake"))])
    ctx = await unpin(message, "Snake")
    assert ctx.sent == ["Took the Snake button off that message."]
    assert message.custom_ids() == [CUSTOM_ID]


@pytest.mark.asyncio
async def test_unpin_the_button_of_a_game_that_was_uninstalled():
    message = FakeMessage([row(button(f"{CUSTOM_ID}:tetris", "Play Tetris"))])
    ctx = await unpin(message, "tetris")
    assert ctx.sent == ["Took the tetris button off that message."]
    assert message.custom_ids() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["Brick Breaker", '"Brick Breaker"', "“Brick Breaker”", "'Brick Breaker'"])
async def test_a_game_name_works_with_or_without_quotes(typed):
    message = FakeMessage()
    await pin(message, f'"Bricks!" game: {typed}')
    assert pinned_button(message, f"{CUSTOM_ID}:brickbreaker").label == "Bricks!"
    message = FakeMessage([row(button(f"{CUSTOM_ID}:brickbreaker", "Play Brick Breaker"))])
    ctx = await unpin(message, typed)
    assert ctx.sent == ["Took the Brick Breaker button off that message."]
