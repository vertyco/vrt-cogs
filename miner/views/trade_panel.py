from datetime import datetime
from typing import Dict

import discord
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number

from ..db.tables import Player


class TradeModal(discord.ui.Modal):
    def __init__(self, title: str, data: dict):
        super().__init__(title=title, timeout=120)
        self.fields = {}
        self.inputs: Dict[str, discord.ui.TextInput] = {}
        for k, v in data.items():
            field = discord.ui.TextInput(
                label=v.get("label", "UNSET"),
                style=v.get("style", discord.TextStyle.short),
                placeholder=v.get("placeholder"),
                default=v.get("default"),
                required=v.get("required", True),
                min_length=v.get("min_length"),
                max_length=v.get("max_length"),
            )
            self.add_item(field)
            self.inputs[k] = field

    async def on_submit(self, interaction: discord.Interaction):
        for k, v in self.inputs.items():
            self.fields[k] = v.value
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        self.stop()
        return await super().on_timeout()

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        self.stop()
        return await super().on_error(interaction, error)


class TradePanel(discord.ui.View):
    def __init__(self, bot: Red, trader: Player, target: Player):
        super().__init__(timeout=900)
        self.bot = bot
        self.trader = trader
        self.trader_user = bot.get_user(trader.id)
        self.target = target
        self.target_user = bot.get_user(target.id)

        self.complete = False
        self.cancelled = False

        self.trader_ready = False
        self.target_ready = False

        self.trader_items: dict[str, int] = {}
        self.target_items: dict[str, int] = {}

        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = [interaction.user.id == self.trader.id, interaction.user.id == self.target.id]
        if not any(allowed):
            await interaction.response.send_message("This isn't your trade window!", ephemeral=True)
        return any(allowed)

    async def start(self, channel: discord.TextChannel | discord.Thread):
        self.message = await channel.send(embed=self.embed(), view=self)

    def embed(self):
        if self.complete:
            desc = "**Trade Complete**\nThe trade has been settled by both miners for the items below."
            color = discord.Color.green()
        elif self.cancelled:
            desc = "The trade has been cancelled!"
            color = discord.Color.orange()
        else:
            desc = "Both miners update what items they want to trade and ready-up."
            color = discord.Color.blue()
        embed = discord.Embed(
            title=f"{self.trader_user.display_name} ↔ {self.target_user.display_name}",
            description=desc,
            color=color,
            timestamp=datetime.now(),
        )
        embed.set_footer(text="Last Updated")
        trader_offerings = "".join(
            [f"{k.title()}: {humanize_number(v)}\n" for k, v in self.trader_items.items() if v > 0]
        )
        target_offerings = "".join(
            [f"{k.title()}: {humanize_number(v)}\n" for k, v in self.target_items.items() if v > 0]
        )
        ready = "✅ (READY)"
        not_ready = "❌ (NOT READY)"
        embed.add_field(
            name=f"{self.trader_user.display_name} {ready if self.trader_ready else not_ready}",
            value=trader_offerings or "No items offered",
        )
        embed.add_field(
            name=f"{self.target_user.display_name} {ready if self.target_ready else not_ready}",
            value=target_offerings or "No items offered",
        )
        return embed

    async def refresh(self, reset: bool = False):
        await self.trader.refresh()
        await self.target.refresh()

        if reset:
            self.trader_ready = False
            self.target_ready = False

        if self.cancelled:
            self.trader_ready = False
            self.target_ready = False
            self.ready_up.disabled = True
            self.update_items.disabled = True
            self.cancel_trade.disabled = True
            self.stop()
        elif self.complete:
            self.ready_up.disabled = True
            self.update_items.disabled = True
            self.cancel_trade.disabled = True
            await self.complete_trade()
            self.stop()

        await self.message.edit(embed=self.embed(), view=self)

    async def complete_trade(self):
        trader_update_kwargs = {}
        target_update_kwargs = {}
        # Transfer items trader has put up
        for item, amount in self.trader_items.items():
            if not amount:
                continue
            column = getattr(Player, item)
            trader_update_kwargs[column] = column - amount
            target_update_kwargs[column] = column + amount

        # Transfer items target has put up
        for item, amount in self.target_items.items():
            if not amount:
                continue
            column = getattr(Player, item)
            trader_update_kwargs[column] = column + amount
            target_update_kwargs[column] = column - amount
        # Update trader in the database
        if trader_update_kwargs:
            await self.trader.update_self(trader_update_kwargs)
        # Update target in the database
        if target_update_kwargs:
            await self.target.update_self(target_update_kwargs)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{WHITE HEAVY CHECK MARK}", label="Ready")
    async def ready_up(self, interaction: discord.Interaction, button: discord.Button):
        if interaction.user.id == self.trader.id:
            self.trader_ready = not self.trader_ready
        else:
            self.target_ready = not self.target_ready

        if self.trader_ready and self.target_ready:
            self.complete = True
            await interaction.response.send_message("Trade completed successfully!")
        elif self.trader_ready or self.target_ready:
            await interaction.response.send_message("Trade will complete when both miners ready-up", ephemeral=True)
        else:
            await interaction.response.defer()

        await self.refresh()

    @discord.ui.button(style=discord.ButtonStyle.primary, label="Update Offer")
    async def update_items(self, interaction: discord.Interaction, button: discord.Button):
        player = self.trader if interaction.user.id == self.trader.id else self.target
        current = self.trader_items if interaction.user.id == self.trader.id else self.target_items

        title = "Update the resources you want to trade"
        modal_data = {
            "stone": {
                "label": f"Enter stone amount (Current: {player.stone})",
                "default": str(current.get("stone", 0)),
                "required": True,
            },
            "iron": {
                "label": f"Enter iron amount (Current: {player.iron})",
                "default": str(current.get("iron", 0)),
                "required": True,
            },
            "gems": {
                "label": f"Enter gem amount (Current: {player.gems})",
                "default": str(current.get("gems", 0)),
                "required": True,
            },
        }
        modal = TradeModal(title, modal_data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.fields:
            return
        for resource, amount in modal.fields.items():
            if not amount.isdigit():
                return await interaction.followup.send(f"Invalid {resource} amount.", ephemeral=True)
            if int(amount) > getattr(player, resource):
                return await interaction.followup.send(f"You don't have enough {resource}!", ephemeral=True)
            current[resource] = int(amount)

        await self.refresh(reset=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}", label="Cancel")
    async def cancel_trade(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.send_message(f"**{interaction.user.name}** has cancelled the trade!")
        self.cancelled = True
        await self.refresh()
