import re

import discord
from redbot.core.i18n import Translator

_ = Translator("ActivityHub", __file__)

CUSTOM_ID = "activityhub:open"


class LaunchButton(discord.ui.DynamicItem[discord.ui.Button], template=CUSTOM_ID):
    """
    The Open Activities button. discord.py finds it by its custom_id on any message, so a button posted or pinned
    anywhere keeps working after restarts, and nothing records which messages have one
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(label=_("Open Activities"), style=discord.ButtonStyle.success, custom_id=CUSTOM_ID)
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):  # noqa: ARG003
        return cls()

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ActivityHub")
        if cog is None:
            await interaction.response.send_message(_("Activities aren't loaded right now."), ephemeral=True)
            return
        await cog.launch(interaction)


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


def has_button(view: discord.ui.View | discord.ui.LayoutView) -> bool:
    return any(getattr(item, "custom_id", None) == CUSTOM_ID for item in view.walk_children())


def add_button(view: discord.ui.View | discord.ui.LayoutView) -> None:
    """Raises ValueError when the message has no room left for a button"""
    if isinstance(view, discord.ui.LayoutView):
        view.add_item(discord.ui.ActionRow(LaunchButton()))
    else:
        view.add_item(LaunchButton())


def remove_button(view: discord.ui.View | discord.ui.LayoutView) -> None:
    for item in list(view.walk_children()):
        if getattr(item, "custom_id", None) == CUSTOM_ID:
            (item.parent or view).remove_item(item)
    # Discord refuses a components V2 message with an empty row
    for item in list(view.walk_children()):
        if isinstance(item, discord.ui.ActionRow) and not item.children:
            (item.parent or view).remove_item(item)
