"""
Bot Arena - Base View Classes

Common base classes for all Bot Arena views to reduce code duplication.
"""

import logging
import typing as t

import discord
from discord import ui
from redbot.core import commands

if t.TYPE_CHECKING:
    from ..main import BotArena

log = logging.getLogger("red.vrt.botarena.views.base")


class BotArenaView(ui.LayoutView):
    """Base class for all Bot Arena views.

    Provides common functionality:
    - Timeout handling that disables all components
    - Permission checking to ensure only the command author can interact
    - Message tracking for editing on timeout
    - Navigation helpers that properly manage view lifecycles

    Subclasses should call super().__init__() and implement _build_layout().
    """

    def __init__(
        self,
        ctx: commands.Context,
        cog: "BotArena",
        timeout: float = 300.0,
        parent: t.Optional[ui.LayoutView] = None,
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog
        self.parent = parent
        self.message: t.Optional[discord.Message] = None
        self._navigated_away = False  # Tracks if we've navigated to a child view

    def navigate_to_child(self, child_view: "BotArenaView") -> None:
        """Mark this view as having navigated to a child.

        Call this before editing the message to show a child view.
        This prevents the parent's on_timeout from trying to edit the message.

        Args:
            child_view: The child view being navigated to
        """
        self._navigated_away = True
        child_view.message = self.message
        # Note: We do NOT stop the parent view here, because we may navigate back to it
        # The _navigated_away flag prevents the timeout from editing the message

    async def on_timeout(self) -> None:
        """Disable all interactive components when the view times out."""
        # Don't try to edit if we've navigated to a child view
        if self._navigated_away:
            return

        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            # Handle ActionRow children (buttons/selects inside rows)
            for item in getattr(child, "children", []):
                if hasattr(item, "disabled"):
                    setattr(item, "disabled", True)

        if self.message is not None:
            try:
                # Just update the view to disable items, don't clear attachments
                # (LayoutViews become empty if attachments are cleared)
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.warning("Failed to edit message on timeout", exc_info=e)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check that only the command author can interact with the view."""
        if interaction.user.id != self.ctx.author.id:
            try:
                await interaction.response.send_message("This is not your bot menu!", ephemeral=True)
            except discord.HTTPException as e:
                log.warning("Failed to send interaction check response", exc_info=e)
            return False
        return True
