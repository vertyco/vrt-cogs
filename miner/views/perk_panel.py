import asyncio
import logging
from collections import defaultdict

import discord
from discord import ui

from ..abc import MixinMeta
from ..common import constants, perks
from ..db.tables import Player

log = logging.getLogger("red.vrt.miner.views.perk_panel")

# One purchase or removal at a time per player, across every perk panel they have open
PLAYER_LOCKS: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def perk_option(key: str) -> discord.SelectOption:
    perk = constants.PERKS[key]
    return discord.SelectOption(label=perk.display_name, value=key, emoji=perk.emoji, description=perk.description)


class PerkPanel(ui.LayoutView):
    """Perk panel: the pickaxe's perks, dropdowns to add or remove one, and a confirm step before any change."""

    def __init__(self, cog: MixinMeta, player: Player, color: discord.Colour):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = player.id
        self.player = player
        self.color = color
        self.message: discord.Message | None = None
        self.pending: perks.Pending | None = None  # The change waiting on the confirm button
        self.notice: str | None = None  # Why the last confirm did nothing
        self.shown_count = 0  # Perks held when the confirm step showed its price

        self.add_select = ui.Select(placeholder="Add a perk")
        self.add_select.callback = self.on_add_pick
        self.remove_select = ui.Select(placeholder="Remove a perk")
        self.remove_select.callback = self.on_remove_pick
        self.confirm_button = ui.Button(label="Buy", style=discord.ButtonStyle.success)
        self.confirm_button.callback = self.on_confirm
        self.cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        self.cancel_button.callback = self.on_cancel
        self.draw()

    def draw(self, controls: bool = True) -> None:
        """Rebuild the panel from the current state."""
        self.clear_items()
        tool = constants.TOOLS[self.player.tool]
        owned = perks.owned_perks(self.player.perks)
        footer = perks.footer_text(self.player, self.pending)
        if self.notice and self.notice != footer:
            footer = f"⚠️ {self.notice}\n{footer}"
        box = ui.Container(accent_colour=self.color)
        box.add_item(ui.TextDisplay(perks.header_text(tool, owned)))
        box.add_item(ui.Separator())
        box.add_item(ui.TextDisplay(perks.list_text(owned)))
        box.add_item(ui.Separator())
        box.add_item(ui.TextDisplay(footer))
        if controls:
            for row in self.control_rows(tool, owned):
                box.add_item(row)
        self.add_item(box)

    def control_rows(self, tool: constants.ToolTier, owned: list[str]) -> list[ui.ActionRow]:
        """The confirm buttons while a change is pending, otherwise the add and remove dropdowns."""
        if not tool.perk_slots:
            return []
        if self.pending:
            return [self.confirm_row()]
        rows: list[ui.ActionRow] = []
        unowned = [key for key in constants.PERKS if key not in owned]
        if len(owned) < tool.perk_slots and unowned:
            self.add_select.options = [perk_option(key) for key in unowned]
            rows.append(ui.ActionRow(self.add_select))
        if owned:
            self.remove_select.options = [perk_option(key) for key in owned]
            rows.append(ui.ActionRow(self.remove_select))
        return rows

    def confirm_row(self) -> ui.ActionRow:
        action, key = self.pending
        if action == "remove":
            self.confirm_button.label = "Remove"
            self.confirm_button.style = discord.ButtonStyle.danger
            return ui.ActionRow(self.confirm_button, self.cancel_button)
        if perks.buy_problem(self.player, key):
            return ui.ActionRow(self.cancel_button)
        self.confirm_button.label = "Buy"
        self.confirm_button.style = discord.ButtonStyle.success
        return ui.ActionRow(self.confirm_button, self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.message:
            return
        self.draw(controls=False)
        try:
            await self.message.edit(view=self)
        except discord.HTTPException as e:
            log.warning("Could not remove the perk panel controls after it timed out", exc_info=e)

    async def on_add_pick(self, interaction: discord.Interaction) -> None:
        await self.show_pending(interaction, ("add", self.add_select.values[0]))

    async def on_remove_pick(self, interaction: discord.Interaction) -> None:
        await self.show_pending(interaction, ("remove", self.remove_select.values[0]))

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        await self.show_pending(interaction, None)

    async def show_pending(self, interaction: discord.Interaction, pending: perks.Pending | None) -> None:
        self.pending = pending
        self.notice = None
        self.shown_count = len(perks.owned_perks(self.player.perks))
        self.draw()
        await interaction.response.edit_message(view=self)

    async def on_confirm(self, interaction: discord.Interaction) -> None:
        # Taken before any await, so a second click on the same button finds nothing to confirm
        pending, self.pending = self.pending, None
        self.notice = None
        if pending:
            async with PLAYER_LOCKS[self.user_id]:
                self.player = await self.cog.db_utils.get_create_player(self.user_id)
                self.notice = await self.apply(*pending)
        self.draw()
        await interaction.response.edit_message(view=self)

    async def apply(self, action: str, key: str) -> str | None:
        """Make the change on the fresh player row. Return why it could not happen, if it could not."""
        owned = perks.owned_perks(self.player.perks)
        if action == "remove":
            if key not in owned:
                return f"You no longer have {perks.perk_name(key)}."
            await self.cog.db_utils.save_perks(self.player, [k for k in owned if k != key])
        else:
            problem = perks.buy_problem(self.player, key)
            if problem:
                return problem
            if len(owned) > self.shown_count:
                # Never charge more than the price the player confirmed; show the new one instead
                self.pending = (action, key)
                self.shown_count = len(owned)
                return "The price went up. Confirm again to pay the new price."
            await self.cog.db_utils.save_perks(self.player, [*owned, key], perks.next_cost(len(owned)))
        await self.cog.db_utils.clear_cached_loadout(self.user_id)
        return None
