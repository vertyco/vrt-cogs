import re

import discord
from redbot.core.i18n import Translator

_ = Translator("ActivityHub", __file__)

CUSTOM_ID = "activityhub:open"
STYLES = {
    "blurple": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "gray": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}


def custom_id_for(key: str | None) -> str:
    """The menu button's custom_id, or with a game key, the custom_id of a button that opens that game"""
    return CUSTOM_ID if key is None else f"{CUSTOM_ID}:{key}"


class LaunchButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"activityhub:open(?::(?P<key>[a-z0-9-]{2,32}))?"
):
    """
    The Open Activity Hub button, or with a game key, a button that opens that game. discord.py finds it by its
    custom_id on any message, so a button posted or pinned anywhere keeps working after restarts, and nothing records
    which messages have one. Its label, emoji and color live only on the message, so a pinned button keeps its own look
    """

    def __init__(
        self,
        key: str | None = None,
        label: str | None = None,
        emoji: discord.PartialEmoji | None = None,
        style: discord.ButtonStyle | None = None,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=label or _("Open Activity Hub"),
                emoji=emoji,
                style=style or discord.ButtonStyle.success,
                custom_id=custom_id_for(key),
            )
        )
        self.key = key

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):  # noqa: ARG003
        return cls(match["key"])

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ActivityHub")
        if cog is None:
            await interaction.response.send_message(_("Activities aren't loaded right now."), ephemeral=True)
            return
        # A game whose cog was unloaded since the button was pinned gets refused with a message by launch
        await cog.launch(interaction, self.key)


def launch_view() -> discord.ui.View:
    return discord.ui.View(timeout=None).add_item(LaunchButton())


def editable_view(message: discord.Message) -> discord.ui.View | discord.ui.LayoutView:
    """
    A copy of the message's buttons and menus, to edit it with. The copy is stopped so discord.py doesn't keep it
    for the message: its buttons do nothing, and kept, they would take the presses meant for the cog that posted them
    """
    view_cls = discord.ui.LayoutView if message.flags.components_v2 else discord.ui.View
    view = view_cls.from_message(message, timeout=None)
    view.stop()
    return view


def has_button(view: discord.ui.View | discord.ui.LayoutView, custom_id: str) -> bool:
    return any(getattr(item, "custom_id", None) == custom_id for item in view.walk_children())


def add_button(view: discord.ui.View | discord.ui.LayoutView, button: LaunchButton) -> None:
    """Raises ValueError when the message has no room left for a button"""
    if isinstance(view, discord.ui.LayoutView):
        view.add_item(discord.ui.ActionRow(button))
    else:
        view.add_item(button)


def restyle_button(
    view: discord.ui.View | discord.ui.LayoutView,
    custom_id: str,
    label: str | None,
    emoji: discord.PartialEmoji | None,
    style: discord.ButtonStyle | None,
) -> None:
    """Changes the parts of the button's look that were given, and keeps the rest"""
    for item in view.walk_children():
        if getattr(item, "custom_id", None) != custom_id:
            continue
        if label is not None:
            item.label = label
        if emoji is not None:
            item.emoji = emoji
        if style is not None:
            item.style = style


def remove_button(view: discord.ui.View | discord.ui.LayoutView, custom_id: str) -> None:
    for item in list(view.walk_children()):
        if getattr(item, "custom_id", None) == custom_id:
            (item.parent or view).remove_item(item)
    # Discord refuses a components V2 message with an empty row
    for item in list(view.walk_children()):
        if isinstance(item, discord.ui.ActionRow) and not item.children:
            (item.parent or view).remove_item(item)
