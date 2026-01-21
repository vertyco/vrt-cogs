"""
Bot Arena - Bot Builder View

Interactive view for equipping parts to a chassis to create a battle-ready bot.
"""

import typing as t

import discord
from discord import ui
from redbot.core import commands

from ..common.image_utils import get_part_image_file
from ..common.models import (
    DB,
    EngagementRange,
    MovementStance,
    OwnedChassis,
    PartsRegistry,
    TacticalOrders,
    TargetPriority,
    get_weight_bar,
)
from . import get_agility_quirk
from .base import BotArenaView

# Tactical order icons and descriptions
STANCE_INFO = {
    MovementStance.AGGRESSIVE: ("⚔️", "Rush to close range, prioritize closing distance"),
    MovementStance.DEFENSIVE: ("🛡️", "Maintain max range, retreat if approached"),
    MovementStance.KITING: ("🏃", "Attack while backing away"),
    MovementStance.HOLD: ("🎯", "Minimal movement, rotate to track targets"),
    MovementStance.FLANKING: ("🔄", "Circle around targets, attack from sides"),
    MovementStance.PROTECTOR: ("💚", "Stay near low-health allies, shield them"),
}

TARGET_INFO = {
    TargetPriority.FOCUS_FIRE: ("🎯", "Attack same target as teammates"),
    TargetPriority.WEAKEST: ("💀", "Target lowest HP enemy (finish kills)"),
    TargetPriority.STRONGEST: ("👑", "Target highest HP enemy (biggest threat)"),
    TargetPriority.CLOSEST: ("📍", "Attack nearest enemy"),
    TargetPriority.FURTHEST: ("🔭", "Attack furthest enemy"),
}

RANGE_INFO = {
    EngagementRange.AUTO: ("🤖", "AI manages based on weapon stats"),
    EngagementRange.CLOSE: ("🔥", "Force close range engagement"),
    EngagementRange.OPTIMAL: ("⚖️", "Stay at weapon's optimal range"),
    EngagementRange.MAX: ("📏", "Force maximum range engagement"),
}


class ChassisSelectRow(ui.ActionRow["BotBuilderView"]):
    """Dropdown for selecting a chassis"""

    def __init__(self, player, registry: PartsRegistry, selected_chassis_id: t.Optional[str] = None):
        super().__init__()
        self.player = player
        self.registry = registry
        self._selected_chassis_id = selected_chassis_id
        self._setup_options()

    def _setup_options(self):
        chassis_options = []
        if self.player.owned_chassis:
            for owned in self.player.owned_chassis:
                chassis_def = self.registry.get_chassis(owned.chassis_name)
                if chassis_def:
                    status = "⚔️" if owned.is_battle_ready else "🔧"
                    chassis_options.append(
                        discord.SelectOption(
                            label=f"{status} {owned.display_name}",
                            description=f"{chassis_def.weight_class.value} | Cap: {chassis_def.weight_capacity}",
                            value=owned.id,
                            default=owned.id == self._selected_chassis_id,
                        )
                    )

        if chassis_options:
            self.chassis_select.options = chassis_options[:25]
        else:
            self.chassis_select.options = [discord.SelectOption(label="No chassis owned", value="none")]
            self.chassis_select.disabled = True

    @ui.select(row=0, placeholder="Select a Chassis (Bot)...")
    async def chassis_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            return

        self.view.selected_chassis_id = select.values[0]
        await self.view.refresh(interaction)


class PlatingSelectRow(ui.ActionRow["BotBuilderView"]):
    """Dropdown for selecting plating"""

    def __init__(self, player, registry: PartsRegistry, selected_plating: t.Optional[str] = None):
        super().__init__()
        self.player = player
        self.registry = registry
        self._selected_plating = selected_plating
        self._setup_options()

    def _setup_options(self):
        owned_plating = {}
        for part in self.player.equipment_inventory:
            if part.part_type == "plating" and part.quantity > 0:
                owned_plating[part.part_name] = part.quantity

        plating_options = []
        if owned_plating:
            for name, qty in owned_plating.items():
                plating = self.registry.get_plating(name)
                # Only add if it's a valid plating in the registry
                if plating:
                    desc = f"Shield: {plating.shielding} | Wt: {plating.weight}"
                    plating_options.append(
                        discord.SelectOption(
                            label=f"{name} (x{qty})",
                            description=desc,
                            value=name,
                            default=name == self._selected_plating,
                        )
                    )
                # Skip items that fail registry lookup - they're invalid/corrupted data

        if plating_options:
            self.plating_select.options = plating_options[:25]
        else:
            self.plating_select.options = [discord.SelectOption(label="No plating available", value="none")]
            self.plating_select.disabled = True

    @ui.select(row=1, placeholder="Select Plating...")
    async def plating_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            return

        self.view.selected_plating = select.values[0]
        await self.view.refresh(interaction)


class WeaponSelectRow(ui.ActionRow["BotBuilderView"]):
    """Dropdown for selecting weapon"""

    def __init__(self, player, registry: PartsRegistry, selected_component: t.Optional[str] = None):
        super().__init__()
        self.player = player
        self.registry = registry
        self._selected_component = selected_component
        self._setup_options()

    def _setup_options(self):
        owned_weapons = {}
        for part in self.player.equipment_inventory:
            if part.part_type == "component" and part.quantity > 0:
                owned_weapons[part.part_name] = part.quantity

        weapon_options = []
        if owned_weapons:
            for name, qty in owned_weapons.items():
                component = self.registry.get_component(name)
                # Only add if it's a valid component in the registry
                if component:
                    desc = f"DMG: {component.damage_per_shot} | Wt: {component.weight}"
                    weapon_options.append(
                        discord.SelectOption(
                            label=f"{name} (x{qty})",
                            description=desc,
                            value=name,
                            default=name == self._selected_component,
                        )
                    )
                # Skip items that fail registry lookup - they're invalid/corrupted data

        if weapon_options:
            self.component_select.options = weapon_options[:25]
        else:
            self.component_select.options = [discord.SelectOption(label="No weapons available", value="none")]
            self.component_select.disabled = True

    @ui.select(row=2, placeholder="Select Weapon...")
    async def component_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            return

        self.view.selected_component = select.values[0]
        await self.view.refresh(interaction)


class TacticsButtonRow(ui.ActionRow["BotBuilderView"]):
    """Button to open tactics configuration"""

    def __init__(self, tactical_orders: TacticalOrders):
        super().__init__()
        self._tactical_orders = tactical_orders

    @ui.button(label="⚔️ Configure Tactics", style=discord.ButtonStyle.primary, row=3, custom_id="builder_tactics")
    async def tactics_button(self, interaction: discord.Interaction, button: ui.Button):
        owned_chassis = self.view._get_selected_chassis()
        if not owned_chassis:
            await interaction.response.send_message("❌ Select a chassis first!", ephemeral=True)
            return

        # Show tactics configuration view
        tactics_view = TacticsConfigView(self.view, owned_chassis)
        await interaction.response.edit_message(view=tactics_view)


class TacticsConfigView(ui.LayoutView):
    """View for configuring tactical orders"""

    def __init__(self, builder_view: "BotBuilderView", chassis: OwnedChassis, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.builder_view = builder_view
        self.chassis = chassis
        self._build_layout()

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
        self.add_item(StanceSelectRow(orders.movement_stance))
        self.add_item(TargetSelectRow(orders.target_priority))
        self.add_item(RangeSelectRow(orders.engagement_range))
        self.add_item(TacticsControlsRow())

    async def refresh(self, interaction: discord.Interaction):
        """Rebuild and refresh the view"""
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)


class StanceSelectRow(ui.ActionRow["TacticsConfigView"]):
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


class TargetSelectRow(ui.ActionRow["TacticsConfigView"]):
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


class RangeSelectRow(ui.ActionRow["TacticsConfigView"]):
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


class TacticsControlsRow(ui.ActionRow["TacticsConfigView"]):
    """Control buttons for tactics view"""

    @ui.button(label="Save & Back", style=discord.ButtonStyle.success, row=3, custom_id="tactics_save")
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        # Save changes
        if self.view.builder_view.cog:
            self.view.builder_view.cog.save()

        # Return to builder
        self.view.builder_view.clear_items()
        self.view.builder_view._build_layout()
        await self.view.builder_view.send(interaction)
        self.view.stop()

    @ui.button(label="Reset to Default", style=discord.ButtonStyle.secondary, row=3, custom_id="tactics_reset")
    async def reset_button(self, interaction: discord.Interaction, button: ui.Button):
        # Reset to defaults
        self.view.chassis.tactical_orders = TacticalOrders()
        await self.view.refresh(interaction)


class BuilderControlsRow(ui.ActionRow["BotBuilderView"]):
    """Action buttons for the builder"""

    @ui.button(label="Rename Bot", style=discord.ButtonStyle.secondary, row=4, custom_id="builder_rename")
    async def name_button(self, interaction: discord.Interaction, button: ui.Button):
        owned_chassis = self.view._get_selected_chassis()
        if not owned_chassis:
            await interaction.response.send_message("❌ Select a chassis first!", ephemeral=True)
            return
        modal = BotNameModal(self.view, owned_chassis)
        await interaction.response.send_modal(modal)

    @ui.button(label="Equip Parts", style=discord.ButtonStyle.success, row=4, custom_id="builder_equip")
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        view = self.view
        # Validate selections
        if not all([view.selected_chassis_id, view.selected_plating, view.selected_component]):
            await interaction.response.send_message("❌ Select all parts first!", ephemeral=True)
            return

        owned_chassis = view._get_selected_chassis()
        if not owned_chassis:
            await interaction.response.send_message("❌ Chassis not found!", ephemeral=True)
            return

        # Check weight
        chassis = view.registry.get_chassis(owned_chassis.chassis_name)
        plating = view.registry.get_plating(view.selected_plating)
        component = view.registry.get_component(view.selected_component)

        if not all([chassis, plating, component]):
            await interaction.response.send_message("❌ Invalid parts!", ephemeral=True)
            return

        total_weight = chassis.self_weight + plating.weight + component.weight
        if total_weight > chassis.weight_capacity:
            await interaction.response.send_message(
                f"❌ Bot is overweight! Weight: {total_weight}/{chassis.weight_capacity}", ephemeral=True
            )
            return

        # Equip parts to the chassis
        player = view.db.get_player(view.ctx.author.id)

        # Equip plating (this handles unequipping old plating and removing from inventory)
        success, msg = player.equip_plating(owned_chassis.id, view.selected_plating, registry=view.registry)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        # Equip weapon
        success, msg = player.equip_weapon(owned_chassis.id, view.selected_component, registry=view.registry)
        if not success:
            # Rollback plating equip
            player.unequip_plating(owned_chassis.id)
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        # Save changes
        if view.cog:
            view.cog.save()

        await interaction.response.send_message(
            f"✅ **{owned_chassis.display_name}** is now battle-ready!\n"
            f"🛡️ Equipped: {view.selected_plating}\n"
            f"⚔️ Equipped: {view.selected_component}",
            ephemeral=True,
        )

        # Close or return to parent
        if view.parent:
            # Reset parent's navigation flag
            if isinstance(view.parent, BotArenaView):
                view.parent._navigated_away = False
            # Rebuild parent and show it
            if hasattr(view.parent, "rebuild"):
                await view.parent.rebuild()
            attachments = view.parent.get_attachments() if hasattr(view.parent, "get_attachments") else []
            if attachments:
                await interaction.message.edit(view=view.parent, attachments=attachments)
            else:
                await interaction.message.edit(view=view.parent)
        else:
            self.view.stop()
            await interaction.message.delete()

    @ui.button(label="Back", style=discord.ButtonStyle.danger, row=4, custom_id="builder_back")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.navigate_back(interaction)


class BotBuilderView(BotArenaView):
    """Interactive bot builder - equip parts to a chassis to make it battle-ready"""

    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        registry: PartsRegistry,
        timeout: float = 300.0,
        parent: t.Optional[ui.LayoutView] = None,
        cog=None,
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=timeout, parent=parent)
        self.db = db
        self.registry = registry

        # Current selection state
        self.selected_chassis_id: t.Optional[str] = None  # ID of owned chassis
        self.selected_plating: t.Optional[str] = None
        self.selected_component: t.Optional[str] = None

        # Initial layout build
        self._build_layout()

    def _get_selected_chassis(self) -> t.Optional[OwnedChassis]:
        """Get the currently selected owned chassis"""
        if not self.selected_chassis_id:
            return None
        player = self.db.get_player(self.ctx.author.id)
        return player.get_chassis_by_id(self.selected_chassis_id)

    def _build_layout(self):
        player = self.db.get_player(self.ctx.author.id)

        # Main container
        container = ui.Container(accent_colour=discord.Colour.blue())
        container.add_item(ui.TextDisplay("# 🔧 Bot Builder"))

        # Check if player has parts
        has_chassis = bool(player.owned_chassis)
        has_plating = any(p.part_type == "plating" and p.quantity > 0 for p in player.equipment_inventory)
        has_weapons = any(p.part_type == "component" and p.quantity > 0 for p in player.equipment_inventory)

        if not has_chassis or not has_plating or not has_weapons:
            missing = []
            if not has_chassis:
                missing.append("🚗 Chassis")
            if not has_plating:
                missing.append("🛡️ Plating")
            if not has_weapons:
                missing.append("⚔️ Weapon")

            error_text = (
                "⚠️ **You need to purchase parts first!**\n\n"
                f"Missing: {', '.join(missing)}\n\n"
                "Visit the **🛒 Shop** to buy parts with your credits."
            )
            container.add_item(ui.TextDisplay(error_text))
            container.add_item(ui.TextDisplay(f"💰 Your Credits: **{player.credits:,}**"))

            self.add_item(container)
            self.add_item(BuilderControlsRow())  # Just for back button
            return

        # Prepare stats text
        owned_chassis = self._get_selected_chassis()

        chassis_weight = 0
        plating_weight = 0
        weapon_weight = 0
        weight_capacity = 0
        total_shielding = 0
        chassis_name = None

        chassis_text = "*Select a chassis*"
        if owned_chassis:
            chassis = self.registry.get_chassis(owned_chassis.chassis_name)
            if chassis:
                quirk = get_agility_quirk(chassis.agility)
                chassis_text = (
                    f"**{owned_chassis.display_name}** ({chassis.weight_class.value})\n"
                    f"Speed: {chassis.speed} | Intel: {chassis.intelligence}\n{quirk}"
                )
                chassis_weight = chassis.self_weight
                weight_capacity = chassis.weight_capacity
                total_shielding += chassis.shielding
                chassis_name = owned_chassis.chassis_name

        plating_text = "*Select plating*"
        plating_name = None
        if self.selected_plating:
            plating = self.registry.get_plating(self.selected_plating)
            if plating:
                plating_text = f"**{plating.name}**\nShield: +{plating.shielding} | Weight: {plating.weight}"
                plating_name = plating.name
                plating_weight = plating.weight
                total_shielding += plating.shielding

        component_text = "*Select a weapon*"
        component_name = None
        if self.selected_component:
            component = self.registry.get_component(self.selected_component)
            if component:
                # Calculate DPS: damage per shot * shots per second
                dps = component.damage_per_shot * component.shots_per_minute / 60
                # Format range display
                if component.min_range == component.max_range:
                    range_str = f"{component.max_range}"
                else:
                    range_str = f"{component.min_range}-{component.max_range}"
                component_text = (
                    f"**{component.name}**\n"
                    f"DMG: {component.damage_per_shot} | ROF: {component.shots_per_minute}/min\n"
                    f"Range: {range_str} | DPS: {dps:.1f} | Weight: {component.weight}"
                )
                component_name = component.name
                weapon_weight = component.weight

        total_weight = chassis_weight + plating_weight + weapon_weight

        # Weight status with visual bar
        if weight_capacity > 0:
            weight_bar = get_weight_bar(chassis_weight, plating_weight, weapon_weight, weight_capacity)
            weight_status = (
                f"{total_weight} ({chassis_weight}+{plating_weight}+{weapon_weight}/{weight_capacity})\n{weight_bar}"
            )
            if total_weight > weight_capacity:
                weight_status += " ⚠️ OVERWEIGHT!"
            elif total_weight == weight_capacity:
                weight_status += " ✅"
        else:
            weight_status = "Select a chassis first"

        # Build sections with individual thumbnails for each part
        # Chassis section
        if chassis_name:
            chassis_thumb = ui.Thumbnail(media="attachment://chassis.webp")
            chassis_section = ui.Section(ui.TextDisplay(f"**🚗 Chassis**\n{chassis_text}"), accessory=chassis_thumb)
            container.add_item(chassis_section)
        else:
            container.add_item(ui.TextDisplay(f"**🚗 Chassis**\n{chassis_text}"))

        # Plating section
        if plating_name:
            plating_thumb = ui.Thumbnail(media="attachment://plating.webp")
            plating_section = ui.Section(ui.TextDisplay(f"**🛡️ Plating**\n{plating_text}"), accessory=plating_thumb)
            container.add_item(plating_section)
        else:
            container.add_item(ui.TextDisplay(f"**🛡️ Plating**\n{plating_text}"))

        # Weapon section
        if component_name:
            weapon_thumb = ui.Thumbnail(media="attachment://weapon.webp")
            weapon_section = ui.Section(ui.TextDisplay(f"**⚔️ Weapon**\n{component_text}"), accessory=weapon_thumb)
            container.add_item(weapon_section)
        else:
            container.add_item(ui.TextDisplay(f"**⚔️ Weapon**\n{component_text}"))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        summary_text = f"**Weight:** {weight_status}\n**Total Shielding:** {total_shielding}"
        container.add_item(ui.TextDisplay(f"**Configuration**\n{summary_text}"))

        # Tactical orders summary (if chassis selected)
        if owned_chassis:
            orders = owned_chassis.tactical_orders
            stance_icon, _ = STANCE_INFO.get(orders.movement_stance, ("?", ""))
            target_icon, _ = TARGET_INFO.get(orders.target_priority, ("?", ""))
            range_icon, _ = RANGE_INFO.get(orders.engagement_range, ("?", ""))

            tactics_text = (
                f"**Tactics:** {stance_icon} {orders.movement_stance.value.title()} | "
                f"{target_icon} {orders.target_priority.value.replace('_', ' ').title()} | "
                f"{range_icon} {orders.engagement_range.value.title()}"
            )
            container.add_item(ui.TextDisplay(tactics_text))

        # Store part names for file generation
        self._chassis_name = chassis_name
        self._plating_name = plating_name
        self._component_name = component_name

        # Add items to the layout
        self.add_item(container)
        self.add_item(ChassisSelectRow(player, self.registry, self.selected_chassis_id))
        self.add_item(PlatingSelectRow(player, self.registry, self.selected_plating))
        self.add_item(WeaponSelectRow(player, self.registry, self.selected_component))

        # Tactics button (only if chassis selected)
        if owned_chassis:
            self.add_item(TacticsButtonRow(owned_chassis.tactical_orders))

        self.add_item(BuilderControlsRow())

    def get_attachments(self) -> list[discord.File]:
        """Get discord.File objects for all selected parts"""
        files = []

        chassis_name = getattr(self, "_chassis_name", None)
        plating_name = getattr(self, "_plating_name", None)
        component_name = getattr(self, "_component_name", None)

        if chassis_name:
            f = get_part_image_file("chassis", chassis_name, "chassis.webp")
            if f:
                files.append(f)

        if plating_name:
            f = get_part_image_file("plating", plating_name, "plating.webp")
            if f:
                files.append(f)

        if component_name:
            f = get_part_image_file("weapon", component_name, "weapon.webp")
            if f:
                files.append(f)

        return files

    async def refresh(self, interaction: discord.Interaction):
        """Rebuild layout and update message"""
        self.clear_items()
        self._build_layout()
        await self.send(interaction)


class BotNameModal(discord.ui.Modal, title="Rename Your Bot"):
    """Modal for renaming a bot (chassis)"""

    bot_name = discord.ui.TextInput(
        label="Bot Name",
        placeholder="Enter a name for your bot...",
        required=True,
        max_length=32,
        min_length=1,
    )

    def __init__(self, view: BotBuilderView, chassis: OwnedChassis):
        super().__init__()
        self.builder_view = view
        self.chassis = chassis
        self.bot_name.default = chassis.display_name

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.bot_name.value.strip()
        self.chassis.custom_name = new_name

        if self.builder_view.cog:
            self.builder_view.cog.save()

        await self.builder_view.refresh(interaction)
