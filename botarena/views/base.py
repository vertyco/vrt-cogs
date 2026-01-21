"""
Bot Arena - Base View Classes

Common base classes for all Bot Arena views to reduce code duplication.
"""

from __future__ import annotations

import inspect
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

    Subclasses should:
    - Call super().__init__()
    - Implement `_build_layout()` (sync or async) to populate the view
    - Override `get_attachments()` if the view uses images/thumbnails
    """

    def __init__(
        self,
        ctx: commands.Context,
        cog: "BotArena",
        timeout: float = 300.0,
        parent: t.Optional[BotArenaView] = None,
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog
        self.parent = parent
        self.message: t.Optional[discord.Message] = None
        self._navigated_away = False

    # ─────────────────────────────────────────────────────────────────────────
    # SUBCLASS INTERFACE - Override these methods in subclasses
    # ─────────────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Build the view's layout. Override in subclasses.

        Can be sync or async - the base class handles both.
        """
        pass

    def get_attachments(self) -> list[discord.File]:
        """Return attachments needed for this view's thumbnails/images.

        Override in subclasses that use `attachment://` URLs in thumbnails.
        Default returns empty list (no attachments needed).
        """
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # NAVIGATION HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def navigate_to_child(self, child_view: "BotArenaView") -> None:
        """Prepare to navigate to a child view.

        Call this before editing the message to show the child.
        Prevents this view's timeout from interfering with the child.
        """
        self._navigated_away = True
        child_view.message = self.message

    async def rebuild(self) -> None:
        """Clear and rebuild this view's layout."""
        self.clear_items()
        result = self._build_layout()
        if inspect.isawaitable(result):
            await result

    async def send(self, interaction: discord.Interaction) -> None:
        """Edit the interaction response to show this view with attachments."""
        attachments = self.get_attachments()
        if attachments:
            await interaction.response.edit_message(view=self, attachments=attachments)
        else:
            await interaction.response.edit_message(view=self)

    async def navigate_back(self, interaction: discord.Interaction) -> None:
        """Navigate back to the parent view.

        Handles rebuilding the parent, resetting flags, and editing with attachments.
        """
        if not self.parent:
            await interaction.response.defer()
            self.stop()
            return

        # Reset parent's navigation flag so it can handle timeouts again
        self.parent._navigated_away = False

        # Rebuild parent and show it
        await self.parent.rebuild()
        await self.parent.send(interaction)
        self.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # DISCORD.PY OVERRIDES
    # ─────────────────────────────────────────────────────────────────────────

    async def on_timeout(self) -> None:
        """Disable all interactive components when the view times out."""
        if self._navigated_away:
            return

        # Disable all interactive components
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            # Handle ActionRow children (buttons/selects inside rows)
            for item in getattr(child, "children", []):
                if hasattr(item, "disabled"):
                    setattr(item, "disabled", True)

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.warning("Failed to edit message on timeout", exc_info=e)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can interact with this view."""
        if interaction.user.id != self.ctx.author.id:
            try:
                await interaction.response.send_message("This is not your bot menu!", ephemeral=True)
            except discord.HTTPException as e:
                log.warning("Failed to send interaction check response", exc_info=e)
            return False
        return True
