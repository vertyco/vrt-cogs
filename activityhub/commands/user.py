import logging

import discord
from discord import app_commands
from discord.ext import commands as dpy_commands
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.discord_api import activities_enabled, launch_activity
from ..common.games import Game
from ..views.launch import (
    STYLES,
    LaunchButton,
    add_button,
    custom_id_for,
    editable_view,
    has_button,
    launch_view,
    remove_button,
    restyle_button,
)

log = logging.getLogger("red.vrt.activityhub.commands")
_ = Translator("ActivityHub", __file__)


# Phones type curly quotes
QUOTES = {'"': '"', "'": "'", "“": "”"}


def unquote(text: str) -> str:
    """Text without the quotes around it, since people quote names with spaces out of habit"""
    text = text.strip()
    if len(text) > 1 and QUOTES.get(text[0]) == text[-1]:
        return text[1:-1].strip()
    return text


class PinOptions(commands.FlagConverter, case_insensitive=True):
    label: str | None = commands.flag(default=None, positional=True, converter=unquote)
    game: str | None = commands.flag(default=None, converter=unquote)
    emoji: str | None = None
    color: str | None = None


def read_look(look: PinOptions) -> tuple[str | None, discord.PartialEmoji | None, discord.ButtonStyle | None]:
    """The parts of the look that were given. Raises ValueError with a message for the user when one is wrong"""
    if look.label is not None and len(look.label) > 80:
        raise ValueError(_("A button's label can be at most 80 characters."))
    emoji = None
    if look.emoji is not None:
        emoji = discord.PartialEmoji.from_str(look.emoji.strip())
        # Every emoji is outside plain ASCII, so plain text like "smile" is a typo, not an emoji
        if emoji.id is None and emoji.name.isascii():
            raise ValueError(_("`{}` isn't an emoji.").format(look.emoji))
    style = None
    if look.color is not None:
        style = STYLES.get(look.color.strip().lower())
        if style is None:
            raise ValueError(_("The color can be blurple, grey, green or red."))
    return look.label, emoji, style


class UserCommands(MixinMeta):
    async def launch(self, interaction: discord.Interaction | dpy_commands.Context, key: str | None = None) -> bool:
        """
        Open the Activity for whoever ran the command or pressed the button.

        With a game key, the menu opens that game right after login. Game cogs call this.
        Takes the discord.Interaction, or a hybrid command's ctx when it ran as a slash command.
        Returns True when the Activity opened, and False when it was refused or Discord failed.
        """
        if isinstance(interaction, dpy_commands.Context):
            if interaction.interaction is None:
                raise TypeError(
                    "hub.launch() needs the discord.Interaction from a button press or slash command. "
                    "A text command has none: post a button that calls launch instead (DEVELOPERS.md section 13)."
                )
            interaction = interaction.interaction
        # Opening the Activity is a reply to the interaction, and an interaction gets only one first reply
        if interaction.response.is_done():
            raise RuntimeError(
                "hub.launch() must be the first reply to this interaction. "
                "Remove the defer() or send_message() before it."
            )
        # Discord voids the interaction when a launch is refused, so everything is checked first
        if not await activities_enabled(self.bot):
            await interaction.response.send_message(
                _("Activities can't open yet. The bot owner needs to turn them on for this bot."), ephemeral=True
            )
            return False
        if key is not None and not await self.launch_allowed(interaction, key):
            return False
        try:
            await launch_activity(self.bot, interaction)
        except discord.HTTPException as e:
            log.error("Activity launch failed in %s", interaction.guild_id, exc_info=e)
            if key is not None:
                # Otherwise the game would open by itself the next time this player opens the menu
                self.launches.forget_user(interaction.user.id)
            return False
        return True

    async def launch_allowed(self, interaction: discord.Interaction, key: str) -> bool:
        if key not in self.registry.games:
            await interaction.response.send_message(_("That activity isn't installed on this bot."), ephemeral=True)
            return False
        if key in await self.config.disabled():
            await interaction.response.send_message(_("This activity is turned off on this bot."), ephemeral=True)
            return False
        if interaction.guild is not None and key in await self.config.guild(interaction.guild).disabled():
            await interaction.response.send_message(_("This activity is turned off in this server."), ephemeral=True)
            return False
        self.launches.remember(interaction.user.id, key)
        return True

    @app_commands.command(name="activities", description="Open the activities menu")
    @app_commands.guild_only()
    async def activities_slash(self, interaction: discord.Interaction):
        """Open the activities menu"""
        await self.launch(interaction)

    @commands.group(name="activities", invoke_without_command=True)
    @commands.guild_only()
    async def activities_text(self, ctx: commands.Context):
        """Post a button that opens the activities menu"""
        await ctx.send(_("Pick a game to play together."), view=launch_view())

    @activities_text.command(name="pin")
    @commands.admin_or_permissions(manage_guild=True)
    async def pin_button(self, ctx: commands.Context, message: discord.Message, *, options: PinOptions = None):
        """
        Add an activities button to a message the bot sent, or change how it looks

        `message` is a message link, or the message's ID when it is in this channel.
        The message keeps its text, embeds and other buttons.

        The button opens the activities menu. Add `game:` with a game's name to make a button that opens that game
        instead. A message can have the menu button and a button for each game.

        After the message, you can also give the button its own label, an `emoji:` and a `color:` (blurple, grey,
        green or red). Pin again with new ones to change a button that's already there.

        **Examples:**
        - `[p]activities pin <message link>`
        - `[p]activities pin <message link> Play games emoji: 🎮 color: blurple`
        - `[p]activities pin <message link> game: Snake`
        - `[p]activities pin <message link> Snake time! game: Snake color: red`
        """
        if not await self.check_editable(ctx, message):
            return
        try:
            game = self.find_game(options.game) if options and options.game else None
            look = read_look(options) if options else (None, None, None)
        except ValueError as e:
            await ctx.send(str(e))
            return
        name = game.name if game else _("Open Activities")
        custom_id = custom_id_for(game.key if game else None)
        view = editable_view(message)
        if has_button(view, custom_id):
            await self.restyle_pinned(ctx, message, view, custom_id, name, look)
            return
        label, emoji, style = look
        if game is not None and label is None:
            label = _("Play {}").format(game.name)[:80]
        try:
            add_button(view, LaunchButton(game.key if game else None, label, emoji, style))
        except ValueError:
            await ctx.send(_("That message has no room for another button."))
            return
        if await self.edit_buttons(ctx, message, view):
            await ctx.send(_("Added the {} button to that message.").format(name))

    async def restyle_pinned(
        self,
        ctx: commands.Context,
        message: discord.Message,
        view: discord.ui.View | discord.ui.LayoutView,
        custom_id: str,
        name: str,
        look: tuple[str | None, discord.PartialEmoji | None, discord.ButtonStyle | None],
    ) -> None:
        if look == (None, None, None):
            await ctx.send(_("That message already has the {} button.").format(name))
            return
        restyle_button(view, custom_id, *look)
        if await self.edit_buttons(ctx, message, view):
            await ctx.send(_("Changed the {} button on that message.").format(name))

    def find_game(self, text: str) -> Game:
        """A game by its key or name. Raises ValueError with a message for the user when none matches"""
        wanted = text.strip().casefold()
        for game in self.registry.games.values():
            if wanted in (game.key, game.name.casefold()):
                return game
        names = ", ".join(sorted(game.name for game in self.registry.games.values()))
        raise ValueError(_("No game called `{}` is installed. The games are: {}").format(text.strip(), names))

    @activities_text.command(name="unpin")
    @commands.admin_or_permissions(manage_guild=True)
    async def unpin_button(self, ctx: commands.Context, message: discord.Message, *, game: str = None):
        """
        Take an activities button off a message the bot sent

        `message` is a message link, or the message's ID when it is in this channel.
        Add a game's name to take off that game's button instead of the menu button.

        **Examples:**
        - `[p]activities unpin <message link>`
        - `[p]activities unpin <message link> Snake`
        """
        if not await self.check_editable(ctx, message):
            return
        if game is not None:
            game = unquote(game)
        if not game:
            key, name = None, _("Open Activities")
        else:
            try:
                found = self.find_game(game)
                key, name = found.key, found.name
            except ValueError:
                # The game's cog may be gone, and its button can still come off by the game's key
                key, name = game.strip().casefold(), game.strip()
        custom_id = custom_id_for(key)
        view = editable_view(message)
        if not has_button(view, custom_id):
            await ctx.send(_("That message doesn't have the {} button.").format(name))
            return
        remove_button(view, custom_id)
        if await self.edit_buttons(ctx, message, view):
            await ctx.send(_("Took the {} button off that message.").format(name))

    async def check_editable(self, ctx: commands.Context, message: discord.Message) -> bool:
        if message.author.id != self.bot.user.id:
            await ctx.send(_("I can only change messages I sent."))
            return False
        # A message link can point into any server the bot is in
        if message.guild is None or message.guild.id != ctx.guild.id:
            await ctx.send(_("That message isn't in this server."))
            return False
        return True

    async def edit_buttons(
        self, ctx: commands.Context, message: discord.Message, view: discord.ui.View | discord.ui.LayoutView
    ) -> bool:
        try:
            await message.edit(view=view)
        except discord.HTTPException as e:
            log.error("Couldn't change the buttons on message %s in %s", message.id, message.channel.id, exc_info=e)
            await ctx.send(_("Discord wouldn't let me change that message's buttons."))
            return False
        return True
