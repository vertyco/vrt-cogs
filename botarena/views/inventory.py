"""
Bot Arena - Inventory Views using Discord's LayoutView/Container system

Provides views for managing chassis (bots), equipment, and part sales.
"""

from __future__ import annotations

import asyncio
import io
import typing as t
import uuid

import discord
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

if t.TYPE_CHECKING:
    from ..main import BotArena

from ..common.image_utils import find_image_path
from ..common.models import (
    EngagementRange,
    MovementStance,
    OwnedChassis,
    PartsRegistry,
    TacticalOrders,
    TargetPriority,
)
from .base import BotArenaView

# Sell back percentage
SELL_PERCENTAGE = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# SELL CONFIRMATION VIEW
# ─────────────────────────────────────────────────────────────────────────────
class SellConfirmView(ui.View):
    """Ephemeral confirmation view for sell actions.

    Shows a confirmation prompt with item details before executing a sale.
    """

    def __init__(
        self,
        item_name: str,
        sell_price: int,
        confirm_callback: t.Callable[[discord.Interaction], t.Coroutine],
        timeout: float = 30.0,
    ):
        super().__init__(timeout=timeout)
        self.item_name = item_name
        self.sell_price = sell_price
        self.confirm_callback = confirm_callback

    @ui.button(label="Confirm Sell", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        """Execute the sale"""
        await self.confirm_callback(interaction)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Cancel the sale"""
        await interaction.response.edit_message(content="Sale cancelled.", view=None)
        self.stop()


# ─────────────────────────────────────────────────────────────────────────────
# CHASSIS (BOT) MANAGEMENT VIEW
# ─────────────────────────────────────────────────────────────────────────────


class EquipPlatingRow(ui.ActionRow["ChassisEditorLayout"]):
    """Dropdown for equipping plating"""

    def __init__(self, player, registry: PartsRegistry, current_plating: t.Optional[str]):
        super().__init__()
        self.player = player
        self.registry = registry
        self._setup_options(current_plating)

    def _setup_options(self, current_plating: t.Optional[str]):
        options = []

        # Option to unequip
        if current_plating:
            options.append(discord.SelectOption(label="❌ Unequip Plating", value="__unequip__"))

        # Available plating from inventory
        seen = set()
        for part in self.player.equipment_inventory:
            if part.part_type == "plating" and part.quantity > 0 and part.part_name not in seen:
                seen.add(part.part_name)
                p = self.registry.get_plating(part.part_name)
                # Only add if it's a valid plating in the registry
                if p:
                    desc = f"🛡️+{p.shielding} shield | ⚖️{p.weight} wt | x{part.quantity}"
                    options.append(
                        discord.SelectOption(
                            label=part.part_name,
                            description=desc[:100],
                            value=part.part_name,
                        )
                    )
                # Skip items that fail registry lookup - they're invalid/corrupted data

        if not options:
            options.append(discord.SelectOption(label="No plating available", value="none"))
            self.select_plating.disabled = True

        self.select_plating.options = options

    @ui.select(placeholder="Select plating to equip...", options=[discord.SelectOption(label="Loading...", value="x")])
    async def select_plating(self, interaction: discord.Interaction, select: ui.Select):
        view: ChassisEditorLayout = self.view
        value = select.values[0]

        if value == "none":
            await interaction.response.defer()
            return

        if value == "__unequip__":
            success, msg = view.player.unequip_plating(view.chassis.id)
        else:
            success, msg = view.player.equip_plating(view.chassis.id, value, registry=view.cog.registry)

        if success:
            view.cog.save()
            await view.refresh()
            files = view.get_image_files()
            await interaction.response.edit_message(view=view, attachments=files)
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


class EquipWeaponRow(ui.ActionRow["ChassisEditorLayout"]):
    """Dropdown for equipping weapons"""

    def __init__(self, player, registry: PartsRegistry, current_weapon: t.Optional[str]):
        super().__init__()
        self.player = player
        self.registry = registry
        self._setup_options(current_weapon)

    def _setup_options(self, current_weapon: t.Optional[str]):
        options = []

        # Option to unequip
        if current_weapon:
            options.append(discord.SelectOption(label="❌ Unequip Weapon", value="__unequip__"))

        # Available weapons from inventory
        seen = set()
        for part in self.player.equipment_inventory:
            if part.part_type == "component" and part.quantity > 0 and part.part_name not in seen:
                seen.add(part.part_name)
                c = self.registry.get_component(part.part_name)
                # Only add if it's a valid component in the registry
                if c:
                    desc = f"💥{c.damage_per_shot}dmg | 🔥{c.shots_per_minute:.0f}/m | ↔️{c.min_range}-{c.max_range} | x{part.quantity}"
                    options.append(
                        discord.SelectOption(
                            label=part.part_name,
                            description=desc[:100],
                            value=part.part_name,
                        )
                    )
                # Skip items that fail registry lookup - they're invalid/corrupted data

        if not options:
            options.append(discord.SelectOption(label="No weapons available", value="none"))
            self.select_weapon.disabled = True

        self.select_weapon.options = options

    @ui.select(placeholder="Select weapon to equip...", options=[discord.SelectOption(label="Loading...", value="x")])
    async def select_weapon(self, interaction: discord.Interaction, select: ui.Select):
        view: ChassisEditorLayout = self.view
        value = select.values[0]

        if value == "none":
            await interaction.response.defer()
            return

        if value == "__unequip__":
            success, msg = view.player.unequip_weapon(view.chassis.id)
        else:
            success, msg = view.player.equip_weapon(view.chassis.id, value, registry=view.cog.registry)

        if success:
            view.cog.save()
            await view.refresh()
            files = view.get_image_files()
            await interaction.response.edit_message(view=view, attachments=files)
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


class EditorBotSwitchRow(ui.ActionRow["ChassisEditorLayout"]):
    """Dropdown for quickly switching between bots in the editor"""

    def __init__(self, view: "ChassisEditorLayout"):
        super().__init__()
        self._view = view
        self._setup_options()

    def _setup_options(self):
        chassis_list = self._view.player.owned_chassis
        options = []
        for chassis in chassis_list[:25]:  # Discord select limit is 25
            status = "⚔️" if chassis.is_battle_ready else "🔧"
            is_current = chassis.id == self._view.chassis.id
            options.append(
                discord.SelectOption(
                    label=f"{status} {chassis.display_name[:50]}",
                    description=f"{chassis.chassis_name}",
                    value=chassis.id,
                    default=is_current,
                )
            )
        if not options:
            options.append(discord.SelectOption(label="No other bots", value="none"))
            self.select_bot.disabled = True
        self.select_bot.options = options

    @ui.select(placeholder="Switch to another bot...")
    async def select_bot(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            return

        chassis_id = select.values[0]
        if chassis_id == self._view.chassis.id:
            # Same bot, just defer
            await interaction.response.defer()
            return

        chassis = self._view.player.get_chassis_by_id(chassis_id)
        if not chassis:
            await interaction.response.send_message("❌ Bot not found!", ephemeral=True)
            return

        # Create new editor for the selected bot
        await interaction.response.defer()
        editor = await ChassisEditorLayout.create(self._view.ctx, self._view.cog, chassis, parent=self._view.parent)
        editor.message = self._view.message
        files = editor.get_image_files()
        await interaction.followup.edit_message(self._view.message.id, view=editor, attachments=files)
        self._view.stop()


class SpawnOrderRow(ui.ActionRow["ChassisEditorLayout"]):
    """Dropdown for setting bot spawn order priority"""

    def __init__(self, view: "ChassisEditorLayout"):
        super().__init__()
        self._view = view
        self._setup_options()

    def _setup_options(self):
        current_order = self._view.chassis.spawn_order
        options = [
            discord.SelectOption(
                label="Default (spawn last)",
                description="Bot spawns based on purchase order",
                value="0",
                default=current_order == 0,
            )
        ]
        for i in range(1, 4):  # 1-3 (max bots in a fight)
            options.append(
                discord.SelectOption(
                    label=f"Position {i}",
                    description=f"Spawn in position {i} on the battlefield",
                    value=str(i),
                    default=current_order == i,
                )
            )
        self.spawn_order_select.options = options

    @ui.select(placeholder="Set spawn order...")
    async def spawn_order_select(self, interaction: discord.Interaction, select: ui.Select):
        new_order = int(select.values[0])
        self._view.chassis.spawn_order = new_order
        self._view.cog.save()
        await self._view.refresh()
        files = self._view.get_image_files()
        await interaction.response.edit_message(view=self._view, attachments=files)


class ChassisEditorLayout(BotArenaView):
    """Layout view for editing a single chassis/bot"""

    def __init__(
        self, ctx: commands.Context, cog: "BotArena", chassis: OwnedChassis, parent: t.Optional[ui.LayoutView] = None
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=180, parent=parent)
        self.chassis = chassis
        self.player = cog.db.get_player(ctx.author.id)
        self.image_files: list[discord.File] = []

    @classmethod
    async def create(
        cls, ctx: commands.Context, cog: "BotArena", chassis: OwnedChassis, parent=None
    ) -> "ChassisEditorLayout":
        """Create a ChassisEditorLayout and wait for the layout to be built."""
        instance = cls(ctx, cog, chassis, parent)
        await instance._build_layout()
        return instance

    async def refresh(self):
        """Refresh the view after changes"""
        self.clear_items()
        await self._build_layout()

    def get_image_files(self) -> list[discord.File]:
        """Get the list of image files for attachment"""
        return self.image_files

    async def _build_layout(self):
        """Build the container layout with generated bot image"""
        # Reset image files
        self.image_files = []

        # Main container
        container = ui.Container(accent_colour=discord.Colour.blue())

        # Get chassis data
        c = self.cog.registry.get_chassis(self.chassis.chassis_name)
        assert c is not None, f"Chassis '{self.chassis.chassis_name}' not found in registry!"

        battle_status = "⚔️ Battle Ready" if self.chassis.is_battle_ready else "🔧 Needs Equipment"

        header_text = ui.TextDisplay(
            f"# 🤖 {self.chassis.display_name}\n-# {self.chassis.chassis_name} • {battle_status} • Player: {self.ctx.author.mention}"
        )

        # Generate full bot image for header (chassis + plating + weapon)
        try:
            bot_image_bytes = await self.chassis.get_bot_image_bytes(orientation=45)
            bot_filename = f"bot_{uuid.uuid4().hex[:8]}.webp"
            bot_file = discord.File(io.BytesIO(bot_image_bytes), filename=bot_filename)
            self.image_files.append(bot_file)

            # Header section with generated bot image
            bot_thumbnail = ui.Thumbnail(media=f"attachment://{bot_filename}")
            header_section = ui.Section(accessory=bot_thumbnail)
            header_section.add_item(header_text)
        except RuntimeError:
            # No image available, just show text
            header_section = ui.Section()
            header_section.add_item(header_text)
        container.add_item(header_section)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Chassis stats section with chassis-only image
        stats_text = (
            f"**📊 Chassis Stats**\n"
            f"├ Speed: {c.speed} | Rotation: {c.rotation_speed}\n"
            f"├ Capacity: {c.weight_capacity} | Base Shield: {c.shielding}\n"
            f"└ Agility: {c.agility:.0%} | AI Level: {c.intelligence}"
        )

        chassis_image_path = find_image_path("chassis", self.chassis.chassis_name)
        if chassis_image_path:
            chassis_filename = f"{self.chassis.chassis_name.lower().replace(' ', '_')}.webp"
            self.image_files.append(discord.File(chassis_image_path, filename=chassis_filename))
            chassis_thumbnail = ui.Thumbnail(media=f"attachment://{chassis_filename}")
            chassis_section = ui.Section(ui.TextDisplay(stats_text), accessory=chassis_thumbnail)
        else:
            # No image available, just add text directly
            chassis_section = ui.TextDisplay(stats_text)

        container.add_item(chassis_section)

        # Weight bar display
        weight_display = self.chassis.get_weight_display(self.cog.registry)
        container.add_item(ui.TextDisplay(f"**⚖️ Weight:** {weight_display}"))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Tactical orders and spawn order summary
        orders = self.chassis.tactical_orders
        spawn_order_text = f"Position {self.chassis.spawn_order}" if self.chassis.spawn_order > 0 else "Default"
        tactics_text = (
            f"**⚔️ Tactics:** {orders.movement_stance.value.title()} | "
            f"{orders.target_priority.value.replace('_', ' ').title()} | "
            f"{orders.engagement_range.value.title()}\n"
            f"**🎯 Spawn Order:** {spawn_order_text}"
        )
        container.add_item(ui.TextDisplay(tactics_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Equipment header
        container.add_item(ui.TextDisplay("**⚙️ Equipment**"))

        # Plating section with image
        if self.chassis.equipped_plating:
            p = self.cog.registry.get_plating(self.chassis.equipped_plating)
            plating_text = f"🛡️ **{self.chassis.equipped_plating}**"
            if p:
                plating_text += f"\n-# +{p.shielding} shield | Weight: {p.weight}"
            plating_display = ui.TextDisplay(plating_text)

            # Try to add image thumbnail
            image_path = find_image_path("plating", self.chassis.equipped_plating)
            if image_path:
                filename = f"{self.chassis.equipped_plating.lower().replace(' ', '_')}.webp"
                self.image_files.append(discord.File(image_path, filename=filename))
                thumbnail = ui.Thumbnail(media=f"attachment://{filename}")
                section = ui.Section(accessory=thumbnail)
                section.add_item(plating_display)
                container.add_item(section)
            else:
                container.add_item(plating_display)
        else:
            container.add_item(ui.TextDisplay("🛡️ **Plating:** *None equipped*"))

        # Weapon section with image
        if self.chassis.equipped_weapon:
            w = self.cog.registry.get_component(self.chassis.equipped_weapon)
            weapon_text = f"⚔️ **{self.chassis.equipped_weapon}**"
            if w:
                weapon_text += f"\n-# DMG: {w.damage_per_shot} | ROF: {w.shots_per_minute}/min"
                if w.description:
                    weapon_text += f"\n-# *{w.description}*"
            weapon_display = ui.TextDisplay(weapon_text)

            # Try to add image thumbnail
            image_path = find_image_path("weapons", self.chassis.equipped_weapon)
            if image_path:
                filename = f"{self.chassis.equipped_weapon.lower().replace(' ', '_')}.webp"
                self.image_files.append(discord.File(image_path, filename=filename))
                thumbnail = ui.Thumbnail(media=f"attachment://{filename}")
                section = ui.Section(accessory=thumbnail)
                section.add_item(weapon_display)
                container.add_item(section)
            else:
                container.add_item(weapon_display)
        else:
            container.add_item(ui.TextDisplay("⚔️ **Weapon:** *None equipped*"))
        self.add_item(container)

        # Bot switcher dropdown (if player has multiple bots)
        if len(self.player.owned_chassis) > 1:
            self.add_item(EditorBotSwitchRow(self))

        # Plating selection
        self.add_item(EquipPlatingRow(self.player, self.cog.registry, self.chassis.equipped_plating))

        # Weapon selection
        self.add_item(EquipWeaponRow(self.player, self.cog.registry, self.chassis.equipped_weapon))

        # Spawn order selection
        self.add_item(SpawnOrderRow(self))

        # Action buttons
        action_row = ui.ActionRow()

        # Configure Tactics button
        tactics_btn = ui.Button(label="Tactics", style=discord.ButtonStyle.primary, emoji="⚔️")

        async def tactics_callback(interaction: discord.Interaction):
            tactics_view = EditorTacticsView(self)
            await interaction.response.edit_message(view=tactics_view, attachments=[])

        tactics_btn.callback = tactics_callback
        action_row.add_item(tactics_btn)

        # Rename button
        rename_btn = ui.Button(label="Rename", style=discord.ButtonStyle.secondary, emoji="✏️")

        async def rename_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(RenameChassisModal(self))

        rename_btn.callback = rename_callback
        action_row.add_item(rename_btn)

        # Sell Bot button
        sell_btn = ui.Button(label="Sell Bot", style=discord.ButtonStyle.danger, emoji="💰")

        async def sell_callback(interaction: discord.Interaction):
            # Calculate sell value
            c = self.cog.registry.get_chassis(self.chassis.chassis_name)
            sell_value = int(c.cost * SELL_PERCENTAGE) if c else 0

            # Build equipment return message
            returns = []
            if self.chassis.equipped_plating:
                returns.append(f"🛡️ {self.chassis.equipped_plating}")
            if self.chassis.equipped_weapon:
                returns.append(f"⚔️ {self.chassis.equipped_weapon}")
            equipment_msg = "\n• ".join(returns) if returns else "None"

            async def confirm_sell(confirm_interaction: discord.Interaction):
                # Add equipped items back to inventory before selling
                if self.chassis.equipped_plating:
                    self.player.add_equipment("plating", self.chassis.equipped_plating)
                if self.chassis.equipped_weapon:
                    self.player.add_equipment("component", self.chassis.equipped_weapon)

                # Remove chassis and add credits
                self.player.remove_chassis(self.chassis.id)
                self.player.credits += sell_value
                self.cog.save()

                await confirm_interaction.response.edit_message(
                    content=f"💰 Sold **{self.chassis.display_name}** for **{humanize_number(sell_value)}** credits!",
                    view=None,
                )

                # Return to parent view
                if isinstance(self.parent, GarageLayout):
                    self.parent.update_display()
                    await self.message.edit(view=self.parent)
                self.stop()

            # Show confirmation prompt
            confirm_view = SellConfirmView(self.chassis.display_name, sell_value, confirm_sell)
            confirm_msg = (
                f"⚠️ **Confirm Sale**\n\n"
                f"Are you sure you want to sell **{self.chassis.display_name}**?\n\n"
                f"💰 **You will receive:** {humanize_number(sell_value)} credits\n"
                f"📦 **Equipment returned to inventory:**\n• {equipment_msg}\n\n"
                f"*This action cannot be undone!*"
            )
            await interaction.response.send_message(confirm_msg, view=confirm_view, ephemeral=True)

        sell_btn.callback = sell_callback
        action_row.add_item(sell_btn)

        # Back button
        back_btn = ui.Button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")

        async def back_callback(interaction: discord.Interaction):
            if isinstance(self.parent, GarageLayout):
                # Reset parent's navigated_away flag so it can handle timeouts again
                if hasattr(self.parent, "_navigated_away"):
                    self.parent._navigated_away = False
                # Rebuild parent layout and get its files
                self.parent.player = self.parent.cog.db.get_player(self.parent.ctx.author.id)
                self.parent.clear_items()
                await self.parent._build_layout()
                files = self.parent.get_image_files()
                if files:
                    await interaction.response.edit_message(view=self.parent, attachments=files)
                else:
                    await interaction.response.edit_message(view=self.parent, attachments=[])
            else:
                await interaction.response.defer()
            self.stop()

        back_btn.callback = back_callback
        action_row.add_item(back_btn)

        self.add_item(action_row)


class GarageSelectRow(ui.ActionRow["GarageLayout"]):
    """Dropdown row for selecting a bot to edit in the garage.

    This replaces individual edit buttons with a single dropdown,
    which scales better when users have many bots.
    """

    def __init__(self, chassis_list: list[OwnedChassis], registry):
        super().__init__()
        self._chassis_list = chassis_list
        self._registry = registry
        self._setup_options()

    def _setup_options(self):
        options = []
        for chassis in self._chassis_list[:25]:  # Discord select limit is 25
            status = "⚔️" if chassis.is_battle_ready else "🔧"
            options.append(
                discord.SelectOption(
                    label=f"{status} {chassis.display_name[:50]}",
                    description=f"{chassis.chassis_name}",
                    value=chassis.id,
                )
            )
        if not options:
            options.append(discord.SelectOption(label="No bots available", value="none"))
            self.select_bot.disabled = True
        self.select_bot.options = options

    @ui.select(placeholder="Select a bot to edit...")
    async def select_bot(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            return

        chassis_id = select.values[0]
        view: GarageLayout = self.view
        chassis = view.player.get_chassis_by_id(chassis_id)
        if not chassis:
            await interaction.response.send_message("❌ Bot not found!", ephemeral=True)
            return

        editor = await ChassisEditorLayout.create(view.ctx, view.cog, chassis, parent=view)
        view.navigate_to_child(editor)
        files = editor.get_image_files()
        await interaction.response.edit_message(view=editor, attachments=files)


class GarageControlsRow(ui.ActionRow["GarageLayout"]):
    """Control buttons for the garage view."""

    @ui.button(label="Inventory", style=discord.ButtonStyle.secondary, emoji="📦")
    async def inventory_button(self, interaction: discord.Interaction, button: ui.Button):
        view: GarageLayout = self.view
        inv_view = InventoryLayout(view.ctx, view.cog, parent=view)
        view.navigate_to_child(inv_view)
        files = inv_view.get_image_files()
        if files:
            await interaction.response.edit_message(view=inv_view, attachments=files)
        else:
            await interaction.response.edit_message(view=inv_view)

    @ui.button(label="Shop", style=discord.ButtonStyle.secondary, emoji="🛒")
    async def shop_button(self, interaction: discord.Interaction, button: ui.Button):
        from .shop import ShopView

        view: GarageLayout = self.view
        shop_view = ShopView(view.ctx, view.cog.db, view.cog.registry, cog=view.cog, parent=view)
        view.navigate_to_child(shop_view)
        image_file = shop_view.get_image_file()
        if image_file:
            await interaction.response.edit_message(view=shop_view, attachments=[image_file])
        else:
            await interaction.response.edit_message(view=shop_view, attachments=[])

    @ui.button(label="Campaign", style=discord.ButtonStyle.success, emoji="⚔️")
    async def campaign_button(self, interaction: discord.Interaction, button: ui.Button):
        from .hub import CampaignLayout

        view: GarageLayout = self.view
        player = view.cog.db.get_player(interaction.user.id)
        battle_ready = player.get_battle_ready_bots()
        if not battle_ready:
            await interaction.response.send_message(
                "❌ You need at least one **battle-ready bot** to enter the campaign!\n\n"
                "💡 A battle-ready bot needs a **chassis**, **plating**, and **weapon** equipped.\n"
                "Visit the **🛒 Shop** to buy parts, then equip them here in the **🏠 Garage**!",
                ephemeral=True,
            )
            return
        campaign_view = CampaignLayout(view.ctx, view.cog, parent=view)
        view.navigate_to_child(campaign_view)
        image_file = campaign_view.get_arena_image_file()
        if image_file:
            await interaction.response.edit_message(view=campaign_view, attachments=[image_file])
        else:
            await interaction.response.edit_message(view=campaign_view)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        view: GarageLayout = self.view
        if view.parent:
            # Reset parent's navigated_away flag so it can handle timeouts again
            if hasattr(view.parent, "_navigated_away"):
                view.parent._navigated_away = False

            # Check if parent is a LayoutView or traditional View
            if isinstance(view.parent, ui.LayoutView):
                # LayoutView - rebuild layout to reflect any changes
                build_layout = getattr(view.parent, "_build_layout", None)
                if build_layout:
                    view.parent.clear_items()
                    build_layout()
                await interaction.response.edit_message(view=view.parent, attachments=[])
            elif hasattr(view.parent, "get_embed"):
                # Traditional View with embed - need to resend
                await interaction.response.defer()
                try:
                    await view.message.delete()
                except discord.HTTPException:
                    pass
                new_msg = await view.ctx.send(embed=view.parent.get_embed(), view=view.parent)
                view.parent.message = new_msg
            else:
                # Simple View without get_embed
                await interaction.response.edit_message(view=view.parent, attachments=[])
        else:
            await interaction.response.defer()
        view.stop()


# ─────────────────────────────────────────────────────────────────────────────
# TACTICS CONFIGURATION FOR CHASSIS EDITOR
# ─────────────────────────────────────────────────────────────────────────────
# Info dicts for tactics display
STANCE_INFO = {
    MovementStance.AGGRESSIVE: ("⚔️", "Rush towards enemies, close distance quickly"),
    MovementStance.DEFENSIVE: ("🛡️", "Maintain distance, retreat when approached"),
    MovementStance.KITING: ("🏃", "Circle enemies, stay at optimal range"),
    MovementStance.HOLD: ("🚫", "Hold position, don't move towards enemies"),
    MovementStance.FLANKING: ("🔄", "Try to get behind enemy lines"),
    MovementStance.PROTECTOR: ("💚", "Stay near low-health allies, shield them"),
}

TARGET_INFO = {
    TargetPriority.FOCUS_FIRE: ("🎯", "Attack what your team is attacking"),
    TargetPriority.WEAKEST: ("💔", "Target enemies with lowest health"),
    TargetPriority.STRONGEST: ("💪", "Target enemies with highest health"),
    TargetPriority.CLOSEST: ("📍", "Target the nearest enemy"),
    TargetPriority.FURTHEST: ("📏", "Target the furthest enemy"),
}

RANGE_INFO = {
    EngagementRange.AUTO: ("🤖", "Let AI decide based on weapon type"),
    EngagementRange.CLOSE: ("🔥", "Get in close, minimum range"),
    EngagementRange.OPTIMAL: ("⚖️", "Maintain mid-range for balance"),
    EngagementRange.MAX: ("🎯", "Stay at maximum weapon range"),
}


class EditorTacticsView(ui.LayoutView):
    """View for configuring tactical orders from the chassis editor"""

    def __init__(self, editor: ChassisEditorLayout, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.editor = editor
        self.chassis = editor.chassis
        self.cog = editor.cog
        self.message: t.Optional[discord.Message] = None
        self._build_layout()

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            elif hasattr(child, "children"):
                for item in getattr(child, "children"):
                    if hasattr(item, "disabled"):
                        setattr(item, "disabled", True)
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.editor.ctx.author.id:
            await interaction.response.send_message("This isn't your tactics menu!", ephemeral=True)
            return False
        return True

    def _build_layout(self):
        orders = self.chassis.tactical_orders

        # Main container
        container = ui.Container(accent_colour=discord.Colour.orange())
        container.add_item(ui.TextDisplay(f"# ⚔️ Tactical Orders\n**Configuring: {self.chassis.display_name}**"))

        # Current orders summary
        stance_icon, stance_desc = STANCE_INFO.get(orders.movement_stance, ("?", "Unknown"))
        target_icon, target_desc = TARGET_INFO.get(orders.target_priority, ("?", "Unknown"))
        range_icon, range_desc = RANGE_INFO.get(orders.engagement_range, ("?", "Unknown"))

        current_orders = (
            f"**Movement Stance:** {stance_icon} {orders.movement_stance.value.replace('_', ' ').title()}\n"
            f"*{stance_desc}*\n\n"
            f"**Target Priority:** {target_icon} {orders.target_priority.value.replace('_', ' ').title()}\n"
            f"*{target_desc}*\n\n"
            f"**Engagement Range:** {range_icon} {orders.engagement_range.value.replace('_', ' ').title()}\n"
            f"*{range_desc}*"
        )
        container.add_item(ui.TextDisplay(current_orders))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(
            ui.TextDisplay(
                "💡 **Tip:** Tactics affect how your bot fights!\n"
                "• **Snipers** work best with Defensive + Furthest + Max Range\n"
                "• **Brawlers** excel with Aggressive + Closest + Close Range\n"
                "• **Team play** benefits from Focus Fire targeting"
            )
        )

        self.add_item(container)
        self.add_item(EditorStanceSelectRow(orders.movement_stance))
        self.add_item(EditorTargetSelectRow(orders.target_priority))
        self.add_item(EditorRangeSelectRow(orders.engagement_range))
        self.add_item(EditorTacticsControlsRow())

    async def refresh(self, interaction: discord.Interaction):
        """Rebuild and refresh the view"""
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)


class EditorStanceSelectRow(ui.ActionRow["EditorTacticsView"]):
    """Dropdown for selecting movement stance"""

    def __init__(self, current: MovementStance):
        super().__init__()
        self._current = current
        self._setup_options()

    def _setup_options(self):
        options = []
        for stance in MovementStance:
            icon, desc = STANCE_INFO.get(stance, ("?", stance.value))
            options.append(
                discord.SelectOption(
                    label=f"{icon} {stance.value.replace('_', ' ').title()}",
                    description=desc[:100],
                    value=stance.value,
                    default=stance == self._current,
                )
            )
        self.stance_select.options = options

    @ui.select(row=0, placeholder="Movement Stance...")
    async def stance_select(self, interaction: discord.Interaction, select: ui.Select):
        new_stance = MovementStance(select.values[0])
        self.view.chassis.tactical_orders.movement_stance = new_stance
        await self.view.refresh(interaction)


class EditorTargetSelectRow(ui.ActionRow["EditorTacticsView"]):
    """Dropdown for selecting target priority"""

    def __init__(self, current: TargetPriority):
        super().__init__()
        self._current = current
        self._setup_options()

    def _setup_options(self):
        options = []
        for priority in TargetPriority:
            icon, desc = TARGET_INFO.get(priority, ("?", priority.value))
            options.append(
                discord.SelectOption(
                    label=f"{icon} {priority.value.replace('_', ' ').title()}",
                    description=desc[:100],
                    value=priority.value,
                    default=priority == self._current,
                )
            )
        self.target_select.options = options

    @ui.select(row=1, placeholder="Target Priority...")
    async def target_select(self, interaction: discord.Interaction, select: ui.Select):
        new_priority = TargetPriority(select.values[0])
        self.view.chassis.tactical_orders.target_priority = new_priority
        await self.view.refresh(interaction)


class EditorRangeSelectRow(ui.ActionRow["EditorTacticsView"]):
    """Dropdown for selecting engagement range"""

    def __init__(self, current: EngagementRange):
        super().__init__()
        self._current = current
        self._setup_options()

    def _setup_options(self):
        options = []
        for eng_range in EngagementRange:
            icon, desc = RANGE_INFO.get(eng_range, ("?", eng_range.value))
            options.append(
                discord.SelectOption(
                    label=f"{icon} {eng_range.value.replace('_', ' ').title()}",
                    description=desc[:100],
                    value=eng_range.value,
                    default=eng_range == self._current,
                )
            )
        self.range_select.options = options

    @ui.select(row=2, placeholder="Engagement Range...")
    async def range_select(self, interaction: discord.Interaction, select: ui.Select):
        new_range = EngagementRange(select.values[0])
        self.view.chassis.tactical_orders.engagement_range = new_range
        await self.view.refresh(interaction)


class EditorTacticsControlsRow(ui.ActionRow["EditorTacticsView"]):
    """Control buttons for tactics view"""

    @ui.button(label="Save & Back", style=discord.ButtonStyle.success, row=3)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        # Save changes
        self.view.cog.save()

        # Return to editor
        await self.view.editor.refresh()
        files = self.view.editor.get_image_files()
        await interaction.response.edit_message(view=self.view.editor, attachments=files)
        self.view.stop()

    @ui.button(label="Reset to Default", style=discord.ButtonStyle.secondary, row=3)
    async def reset_button(self, interaction: discord.Interaction, button: ui.Button):
        # Reset to defaults
        self.view.chassis.tactical_orders = TacticalOrders()
        await self.view.refresh(interaction)


class RenameChassisModal(ui.Modal, title="Rename Bot"):
    name = ui.TextInput(label="New Name", style=discord.TextStyle.short, max_length=25, required=True)

    def __init__(self, view: ChassisEditorLayout):
        super().__init__()
        self.editor_view = view
        self.name.default = view.chassis.display_name

    async def on_submit(self, interaction: discord.Interaction):
        self.editor_view.chassis.custom_name = str(self.name.value)
        self.editor_view.cog.save()
        await self.editor_view.refresh()
        files = self.editor_view.get_image_files()
        await interaction.response.edit_message(view=self.editor_view, attachments=files)


class GarageLayout(BotArenaView):
    """Layout view for the Garage - shows ALL owned bots at once with Edit buttons.

    This is the main bot management interface. Each bot is displayed with its
    key stats, and users can click Edit to open the ChassisEditorLayout for
    that specific bot.
    """

    # Maximum bots to display (Discord has limits on components)
    MAX_BOTS_DISPLAY = 7

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=180, parent=parent)
        self.player = cog.db.get_player(ctx.author.id)
        self.bot_image_files: list[discord.File] = []
        self._layout_built = False

    @classmethod
    async def create(cls, ctx: commands.Context, cog: "BotArena", parent=None) -> "GarageLayout":
        """Create a GarageLayout and wait for the layout to be built."""
        instance = cls(ctx, cog, parent)
        await instance._build_layout()
        return instance

    def update_display(self):
        """Update the display after changes"""
        self.player = self.cog.db.get_player(self.ctx.author.id)
        self.clear_items()
        asyncio.create_task(self._build_layout())

    async def _build_layout(self):
        """Build the container layout showing all bots with images"""
        # Main container
        container = ui.Container(accent_colour=discord.Colour.gold())

        # Header
        total_bots = len(self.player.owned_chassis)
        battle_ready = len(self.player.get_battle_ready_bots())

        header = ui.TextDisplay(
            f"# 🏠 Garage\n-# You have **{total_bots}** bots • {battle_ready} battle ready • Player: {self.ctx.author.mention}"
        )
        container.add_item(header)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Bot list
        if not self.player.owned_chassis:
            container.add_item(
                ui.TextDisplay(
                    "**No bots yet!**\n"
                    "Visit the **Shop** to purchase a chassis.\n"
                    "Each chassis is a bot - equip it with plating and a weapon to battle!"
                )
            )
        else:
            # Show ALL bots with their stats and inline images
            display_bots = self.player.owned_chassis[: self.MAX_BOTS_DISPLAY]
            self.bot_image_files = []

            for idx, chassis in enumerate(display_bots):
                # Status icons
                ready_icon = "\n[✅ Battle Ready]" if chassis.is_battle_ready else "\n[⚠️ Needs Equipment]"

                # Equipment strings
                plating_str = chassis.equipped_plating if chassis.equipped_plating else "None"
                weapon_str = chassis.equipped_weapon if chassis.equipped_weapon else "None"

                # Weight bar
                weight_display = chassis.get_weight_display(self.cog.registry)

                # Tactics summary
                orders = chassis.tactical_orders
                tactics_str = (
                    f"{orders.movement_stance.value.title()} | "
                    f"{orders.target_priority.value.replace('_', ' ').title()} | "
                    f"{orders.engagement_range.value.title()}"
                )

                # Build bot card text
                bot_card = (
                    f"🤖 **{chassis.display_name}** ({chassis.chassis_name}) "
                    f"{ready_icon}\n"
                    f"🛡️ {plating_str} | ⚔️ {weapon_str}\n"
                    f"🎛️ {tactics_str}\n"
                    f"⚖️ {weight_display}"
                )

                if idx != 0:
                    container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

                # Generate bot image and create inline section
                try:
                    image_bytes = await chassis.get_bot_image_bytes(orientation=45)
                    filename = f"bot_{uuid.uuid4().hex[:8]}.webp"
                    bot_file = discord.File(io.BytesIO(image_bytes), filename=filename)
                    self.bot_image_files.append(bot_file)

                    # Create section with thumbnail accessory (inline image)
                    thumbnail = ui.Thumbnail(media=f"attachment://{filename}")
                    section = ui.Section(accessory=thumbnail)
                    section.add_item(ui.TextDisplay(bot_card))
                    container.add_item(section)
                except RuntimeError:
                    # No image available, just add text directly
                    container.add_item(ui.TextDisplay(bot_card))

        self.add_item(container)

        # Add bot selection dropdown (if user has bots)
        if self.player.owned_chassis:
            self.add_item(GarageSelectRow(self.player.owned_chassis, self.cog.registry))

        # Controls row (Inventory, Back)
        self.add_item(GarageControlsRow())

    def get_image_files(self) -> list[discord.File]:
        """Get the list of bot image files for attachment"""
        return self.bot_image_files


# Alias for backward compatibility
MyBotsLayout = GarageLayout


# ─────────────────────────────────────────────────────────────────────────────
# EQUIPMENT INVENTORY VIEW
# ─────────────────────────────────────────────────────────────────────────────
class InventoryLayout(BotArenaView):
    """Layout view for viewing equipment inventory and selling items"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=180, parent=parent)
        self.player = cog.db.get_player(ctx.author.id)
        self.category = "plating"  # "plating" or "component"
        self.selected_item: t.Optional[str] = None

        self._build_layout()

    def get_image_files(self) -> list[discord.File]:
        """Get discord.File objects for item images in current category"""
        files = []
        items = [p for p in self.player.equipment_inventory if p.part_type == self.category and p.quantity > 0]
        folder = "plating" if self.category == "plating" else "weapons"

        for item in items[:8]:
            image_path = find_image_path(folder, item.part_name)
            if image_path:
                filename = f"{item.part_name.lower().replace(' ', '_')}.webp"
                files.append(discord.File(image_path, filename=filename))

        return files

    def update_display(self):
        """Update the display after changes"""
        self.player = self.cog.db.get_player(self.ctx.author.id)
        self.clear_items()
        self._build_layout()

    def _build_layout(self):
        """Build the container layout"""
        # Main container
        container = ui.Container(accent_colour=discord.Colour.purple())

        # Header
        header = ui.TextDisplay(
            f"# 📦 Equipment Inventory\n-# Unequipped plating and weapons • Player: {self.ctx.author.mention}"
        )
        container.add_item(header)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Category tabs
        cat_display = "**Category:** "
        cat_display += "**[🛡️ Plating]**" if self.category == "plating" else "[🛡️ Plating]"
        cat_display += " | "
        cat_display += "**[⚔️ Weapons]**" if self.category == "component" else "[⚔️ Weapons]"
        container.add_item(ui.TextDisplay(cat_display))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Item list
        items = [p for p in self.player.equipment_inventory if p.part_type == self.category and p.quantity > 0]

        if not items:
            container.add_item(
                ui.TextDisplay(
                    f"*No {self.category} in inventory.*\nPurchase items from the Shop or unequip from your bots."
                )
            )
        else:
            folder = "plating" if self.category == "plating" else "weapons"
            for item in items[:8]:  # Limit displayed items (sections take more space)
                if self.category == "plating":
                    p = self.cog.registry.get_plating(item.part_name)
                    if p:
                        sell_price = int(p.cost * SELL_PERCENTAGE)
                        item_text = ui.TextDisplay(
                            f"**{item.part_name}** x{item.quantity}\n"
                            f"-# 🛡️ Shield: +{p.shielding}\n"
                            f"-# 💰 Sell: {humanize_number(sell_price)}"
                        )
                        # Try to add image thumbnail
                        image_path = find_image_path(folder, item.part_name)
                        if image_path:
                            thumbnail = ui.Thumbnail(
                                media=f"attachment://{item.part_name.lower().replace(' ', '_')}.webp"
                            )
                            section = ui.Section(accessory=thumbnail)
                            section.add_item(item_text)
                            container.add_item(section)
                        else:
                            container.add_item(item_text)
                else:
                    c = self.cog.registry.get_component(item.part_name)
                    if c:
                        sell_price = int(c.cost * SELL_PERCENTAGE)
                        item_text = ui.TextDisplay(
                            f"**{item.part_name}** x{item.quantity}\n"
                            f"-# ⚔️ DMG: {c.damage_per_shot} | ROF: {c.shots_per_minute}/min\n"
                            f"-# 💰 Sell: {humanize_number(sell_price)}"
                        )
                        # Try to add image thumbnail
                        image_path = find_image_path(folder, item.part_name)
                        if image_path:
                            thumbnail = ui.Thumbnail(
                                media=f"attachment://{item.part_name.lower().replace(' ', '_')}.webp"
                            )
                            section = ui.Section(accessory=thumbnail)
                            section.add_item(item_text)
                            container.add_item(section)
                        else:
                            container.add_item(item_text)

        self.add_item(container)

        # Item selection for selling
        if items:
            options = []
            for item in items[:25]:
                part = (
                    self.cog.registry.get_plating(item.part_name)
                    if self.category == "plating"
                    else self.cog.registry.get_component(item.part_name)
                )
                if part:
                    sell_price = int(part.cost * SELL_PERCENTAGE)
                    options.append(
                        discord.SelectOption(
                            label=item.part_name,
                            description=f"Qty: {item.quantity} | Sell: {humanize_number(sell_price)}💰",
                            value=item.part_name,
                        )
                    )

            if options:
                sell_row = ui.ActionRow()
                sell_select = ui.Select(placeholder="Select item to sell...", options=options)

                async def sell_select_callback(interaction: discord.Interaction):
                    self.selected_item = sell_select.values[0]
                    await interaction.response.defer()

                sell_select.callback = sell_select_callback
                sell_row.add_item(sell_select)
                self.add_item(sell_row)

        # Category and action buttons
        action_row = ui.ActionRow()

        # Plating button
        plating_btn = ui.Button(
            label="🛡️ Plating",
            style=discord.ButtonStyle.primary if self.category == "plating" else discord.ButtonStyle.secondary,
        )

        async def plating_callback(interaction: discord.Interaction):
            self.category = "plating"
            self.selected_item = None
            self.update_display()
            files = self.get_image_files()
            if files:
                await interaction.response.edit_message(view=self, attachments=files)
            else:
                await interaction.response.edit_message(view=self, attachments=[])

        plating_btn.callback = plating_callback
        action_row.add_item(plating_btn)

        # Weapons button
        weapons_btn = ui.Button(
            label="⚔️ Weapons",
            style=discord.ButtonStyle.primary if self.category == "component" else discord.ButtonStyle.secondary,
        )

        async def weapons_callback(interaction: discord.Interaction):
            self.category = "component"
            self.selected_item = None
            self.update_display()
            files = self.get_image_files()
            if files:
                await interaction.response.edit_message(view=self, attachments=files)
            else:
                await interaction.response.edit_message(view=self, attachments=[])

        weapons_btn.callback = weapons_callback
        action_row.add_item(weapons_btn)

        # Sell button
        sell_btn = ui.Button(label="Sell", style=discord.ButtonStyle.danger, emoji="💰")

        async def sell_callback(interaction: discord.Interaction):
            if not self.selected_item:
                await interaction.response.send_message("❌ Select an item to sell first!", ephemeral=True)
                return

            # Get item value
            if self.category == "plating":
                part = self.cog.registry.get_plating(self.selected_item)
            else:
                part = self.cog.registry.get_component(self.selected_item)

            if not part:
                await interaction.response.send_message("❌ Item not found!", ephemeral=True)
                return

            sell_price = int(part.cost * SELL_PERCENTAGE)
            item_name = self.selected_item  # Capture for closure
            category = self.category  # Capture for closure

            async def confirm_sell(confirm_interaction: discord.Interaction):
                # Re-fetch player in case state changed
                player = self.cog.db.get_player(self.ctx.author.id)

                # Remove from inventory and add credits
                if player.remove_equipment(category, item_name, 1):
                    player.credits += sell_price
                    self.cog.save()

                    await confirm_interaction.response.edit_message(
                        content=f"💰 Sold **{item_name}** for **{humanize_number(sell_price)}** credits!",
                        view=None,
                    )

                    self.selected_item = None
                    self.player = player  # Update reference
                    self.update_display()
                    await self.message.edit(view=self)
                else:
                    await confirm_interaction.response.edit_message(
                        content="❌ Item not in inventory!",
                        view=None,
                    )

            # Show confirmation prompt
            confirm_view = SellConfirmView(item_name, sell_price, confirm_sell)
            part_type = "plating" if category == "plating" else "weapon"
            confirm_msg = (
                f"⚠️ **Confirm Sale**\n\n"
                f"Are you sure you want to sell **{item_name}** ({part_type})?\n\n"
                f"💰 **You will receive:** {humanize_number(sell_price)} credits\n\n"
                f"*This action cannot be undone!*"
            )
            await interaction.response.send_message(confirm_msg, view=confirm_view, ephemeral=True)

        sell_btn.callback = sell_callback
        action_row.add_item(sell_btn)

        # Back button
        back_btn = ui.Button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")

        async def back_callback(interaction: discord.Interaction):
            if isinstance(self.parent, InventoryLayout):
                # Refresh the parent's data and rebuild its layout
                self.parent.player = self.parent.cog.db.get_player(self.parent.ctx.author.id)
                self.parent.clear_items()
                await self.parent._build_layout()
                files = self.parent.get_image_files()
                if files:
                    await interaction.response.edit_message(view=self.parent, attachments=files)
                else:
                    await interaction.response.edit_message(view=self.parent, attachments=[])
            else:
                await interaction.response.defer()
            self.stop()

        back_btn.callback = back_callback
        action_row.add_item(back_btn)

        self.add_item(action_row)
