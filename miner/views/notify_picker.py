import logging

import discord
from discord import ui

from ..abc import MixinMeta
from ..common import constants, spawn_pings
from ..db.tables import GuildSettings, Player

log = logging.getLogger("red.vrt.miner.views.notify_picker")


class NotifyPicker(ui.LayoutView):
    """Rock ping panel: one container with the player's ping status and a dropdown of the rock types they have mined."""

    def __init__(
        self,
        cog: MixinMeta,
        user_id: int,
        guild_id: int,
        mined: list[constants.RockTierName],
        subscribed: bool,
        picks: list[str],
        color: discord.Colour,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.mined = mined
        self.subscribed = subscribed
        self.picks = picks
        self.color = color
        self.message: discord.Message | None = None

        self.pick_types = ui.Select(placeholder="Pick rock types", min_values=0, max_values=max(len(mined), 1))
        self.pick_types.callback = self.on_pick
        self.draw()

    def draw(self, dropdown: bool = True) -> None:
        """Rebuild the panel from the current state. The dropdown only shows when there is a mined type to pick."""
        self.clear_items()
        box = ui.Container(accent_colour=self.color)
        box.add_item(ui.TextDisplay(spawn_pings.panel_text(self.subscribed, self.picks, self.mined)))
        if dropdown and self.mined:
            ticked = spawn_pings.pinged_types(self.subscribed, self.picks, self.mined)
            self.pick_types.options = [
                discord.SelectOption(label=constants.ROCK_TYPES[key].display_name, value=key, default=key in ticked)
                for key in self.mined
            ]
            box.add_item(ui.ActionRow(self.pick_types))
        self.add_item(box)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.message:
            return
        self.draw(dropdown=False)
        try:
            await self.message.edit(view=self)
        except discord.HTTPException as e:
            log.warning("Could not remove the rock ping dropdown after it timed out", exc_info=e)

    async def on_pick(self, interaction: discord.Interaction) -> None:
        ticked = list(self.pick_types.values)
        # Read the list fresh: other players may have changed it while this panel was open
        settings = await self.cog.db_utils.get_create_guild_settings(self.guild_id)
        player = await self.cog.db_utils.get_create_player(self.user_id)
        subscribed = self.user_id in settings.notify_players
        if ticked and not subscribed:
            settings.notify_players.append(self.user_id)
        elif not ticked and subscribed:
            settings.notify_players.remove(self.user_id)
        if ticked:
            player.notify_rock_types = spawn_pings.picks_to_save(ticked, self.mined)
            await player.save([Player.notify_rock_types])
        await settings.save([GuildSettings.notify_players])
        await self.cog.db_utils.get_cached_guild_settings.cache.delete(f"miner_guild_settings:{self.guild_id}")  # type: ignore

        self.subscribed = bool(ticked)
        self.picks = player.notify_rock_types
        self.draw()
        await interaction.response.edit_message(view=self)
