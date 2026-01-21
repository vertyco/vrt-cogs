"""
Bot Arena - Shop View

Interactive shop for purchasing parts with dropdowns and image display.
"""

import typing as t
from pathlib import Path

import discord
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

from ..common.image_utils import find_image_path
from ..common.models import DB, PartsRegistry
from ..constants import is_starter_part
from . import get_agility_quirk_detailed
from .base import BotArenaView


def _get_part_image_path(category: str, part_name: str) -> t.Optional[Path]:
    """Get the path to a part's image file using shared image_utils"""

    folder_map = {"chassis": "chassis", "plating": "plating", "component": "weapons"}
    folder = folder_map.get(category, category)
    return find_image_path(folder, part_name)


class ShopCategoryRow(ui.ActionRow["ShopView"]):
    """Row for changing shop category"""

    @ui.button(label="Chassis", style=discord.ButtonStyle.primary, custom_id="shop_chassis")
    async def chassis_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.category = "chassis"
        self.view.index = 0
        await self.view.refresh(interaction)

    @ui.button(label="Plating", style=discord.ButtonStyle.secondary, custom_id="shop_plating")
    async def plating_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.category = "plating"
        self.view.index = 0
        await self.view.refresh(interaction)

    @ui.button(label="Weapons", style=discord.ButtonStyle.secondary, custom_id="shop_component")
    async def component_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.category = "component"
        self.view.index = 0
        await self.view.refresh(interaction)

    def __init__(self, view: "ShopView"):
        super().__init__()
        # Set button styles based on active category
        for item in self.children:
            if isinstance(item, ui.Button):
                if item.custom_id == f"shop_{view.category}":
                    item.style = discord.ButtonStyle.primary
                    item.disabled = True
                else:
                    item.style = discord.ButtonStyle.secondary
                    item.disabled = False


class ShopItemSelectRow(ui.ActionRow["ShopView"]):
    """Dropdown for item selection"""

    def __init__(self, view: "ShopView"):
        super().__init__()

        items = view._get_items()
        player = view.db.get_player(view.ctx.author.id)

        options = []
        if items:
            for i, item in enumerate(items[:25]):
                owned_count = player.count_part(view.category, item.name)
                status = f"[x{owned_count}] " if owned_count > 0 else ""

                desc = ""
                if view.category == "chassis":
                    # Spd/Rot/Cap/Weight/Shield/AI - key chassis stats
                    desc = f"⚡{item.speed} 🔄{item.rotation_speed} 📦{item.weight_capacity} ⚖️{item.self_weight}wt 🛡️{item.shielding} 🧠{item.intelligence} | {humanize_number(item.cost)}💰"
                elif view.category == "plating":
                    # Shield/Weight/Cost - plating stats
                    desc = f"🛡️+{item.shielding} ⚖️{item.weight}wt | {humanize_number(item.cost)}💰"
                else:
                    # DMG/ROF/Range/Weight - weapon stats
                    desc = f"💥{item.damage_per_shot} 🔥{item.shots_per_minute:.0f}/m ↔️{item.min_range}-{item.max_range} ⚖️{item.weight}wt | {humanize_number(item.cost)}💰"

                options.append(
                    discord.SelectOption(
                        label=f"{status}{item.name}", description=desc[:100], value=str(i), default=(i == view.index)
                    )
                )

        if options:
            self.select_item.options = options
        else:
            self.select_item.options = [discord.SelectOption(label="No items found", value="0")]
            self.select_item.disabled = True

    @ui.select(placeholder="Select an item...")
    async def select_item(self, interaction: discord.Interaction, select: ui.Select):
        self.view.index = int(select.values[0])
        await self.view.refresh(interaction)


class ShopNavigationRow(ui.ActionRow["ShopView"]):
    """Navigation and actions"""

    @ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        items = self.view._get_items()
        if not items:
            return
        self.view.index = (self.view.index - 1) % len(items)
        await self.view.refresh(interaction)

    @ui.button(label="Buy", style=discord.ButtonStyle.success, emoji="💰")
    async def buy_button(self, interaction: discord.Interaction, button: ui.Button):
        item = self.view._get_current_item()
        if not item:
            await interaction.response.send_message("❌ No item selected!", ephemeral=True)
            return

        player = self.view.db.get_player(interaction.user.id)
        if player.credits < item.cost:
            await interaction.response.send_message(
                f"❌ You need **{humanize_number(item.cost)}** credits but only have **{humanize_number(player.credits)}**!",
                ephemeral=True,
            )
            return

        owned_count = player.count_part(self.view.category, item.name)
        confirm_view = PurchaseConfirmView(self.view, item, cog=self.view.cog)
        owned_msg = f"\n📦 Currently owned: {owned_count}" if owned_count > 0 else ""

        await interaction.response.send_message(
            f"**Confirm Purchase**\n\n"
            f"Are you sure you want to buy **{item.name}** for **{humanize_number(item.cost)}** credits?{owned_msg}\n\n"
            f"💰 Your balance: {humanize_number(player.credits)}\n"
            f"💰 After purchase: {humanize_number(player.credits - item.cost)}",
            view=confirm_view,
            ephemeral=True,
        )

    @ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        items = self.view._get_items()
        if not items:
            return
        self.view.index = (self.view.index + 1) % len(items)
        await self.view.refresh(interaction)

    @ui.button(label="Garage", style=discord.ButtonStyle.secondary, emoji="🏠")
    async def garage_button(self, interaction: discord.Interaction, button: ui.Button):
        from .inventory import GarageLayout

        view = await GarageLayout.create(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        files = view.get_image_files()
        if files:
            await interaction.response.edit_message(view=view, attachments=files)
        else:
            await interaction.response.edit_message(view=view)

    @ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="↩️")
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.view.parent:
            # Reset parent's navigated_away flag so it can handle timeouts again
            if hasattr(self.view.parent, "_navigated_away"):
                setattr(self.view.parent, "_navigated_away", False)

            if hasattr(self.view.parent, "get_embed"):
                # Traditional View with embed
                embed_method = getattr(self.view.parent, "get_embed")
                await interaction.response.edit_message(embed=embed_method(), view=self.view.parent, attachments=[])
            elif isinstance(self.view.parent, ui.LayoutView):
                # LayoutView parent - rebuild layout to reflect any changes
                build_layout = getattr(self.view.parent, "_build_layout", None)
                if build_layout:
                    self.view.parent.clear_items()
                    build_layout()
                await interaction.response.edit_message(view=self.view.parent, attachments=[])
            else:
                # Fallback
                await interaction.response.edit_message(view=self.view.parent, attachments=[])
        else:
            await interaction.response.defer()
            await self.view.message.delete()
        self.view.stop()


class ShopView(BotArenaView):
    """Interactive shop for browsing and purchasing parts"""

    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        registry: PartsRegistry,
        cog: t.Any = None,
        timeout: float = 180.0,
        parent: t.Optional[ui.LayoutView] = None,
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=timeout, parent=parent)
        self.db = db
        self.registry = registry

        # Current state
        self.category = "chassis"  # chassis, plating, component
        self.index = 0  # Current item index within category

        self._build_layout()

    def _get_items(self) -> list:
        """Get available items for current category (starter parts + unlocked parts only)"""
        player = self.db.get_player(self.ctx.author.id)

        if self.category == "chassis":
            all_items = self.registry.all_chassis()
        elif self.category == "plating":
            all_items = self.registry.all_plating()
        else:
            all_items = self.registry.all_components()

        # Filter to only show starter parts and unlocked parts
        available = []
        for item in all_items:
            if is_starter_part(item.name) or player.has_unlocked_part(item.name):
                available.append(item)

        return available

    def _get_current_item(self):
        """Get the currently displayed item"""
        items = self._get_items()
        if items and 0 <= self.index < len(items):
            return items[self.index]
        return None

    def get_image_file(self) -> t.Optional[discord.File]:
        """Get a discord.File for the current item's image"""
        item = self._get_current_item()
        if not item:
            return None

        image_path = _get_part_image_path(self.category, item.name)
        if image_path and image_path.exists():
            # Use the actual file extension for the filename
            ext = image_path.suffix  # .webp or .png
            return discord.File(image_path, filename=f"part{ext}")
        return None

    def _get_first_time_tip(self, player) -> t.Optional[str]:
        """Get a helpful tip for first-time buyers based on what they own."""
        has_chassis = len(player.owned_chassis) > 0
        has_plating = player.get_equipment_quantity("plating", "") > 0 or any(
            c.equipped_plating for c in player.owned_chassis
        )
        has_weapon = player.get_equipment_quantity("component", "") > 0 or any(
            c.equipped_weapon for c in player.owned_chassis
        )

        # Check if they have any plating or weapon in inventory
        for part in player.equipment_inventory:
            if part.part_type == "plating" and part.quantity > 0:
                has_plating = True
            elif part.part_type == "component" and part.quantity > 0:
                has_weapon = True

        # Check if player has a battle-ready bot
        has_battle_ready = len(player.get_battle_ready_bots()) > 0

        if has_battle_ready:
            return None  # No tip needed for experienced players

        if not has_chassis:
            if self.category == "chassis":
                return (
                    "💡 **Tip:** Start here! The **Chassis** is the foundation of your bot. Buy one to begin building!"
                )
            else:
                return "💡 **Tip:** You need a **Chassis** first! Switch to the Chassis tab to buy your bot's body."

        if not has_plating:
            if self.category == "plating":
                return "💡 **Tip:** Great! Now buy **Plating** to give your bot armor and shielding."
            else:
                return "💡 **Tip:** You have a chassis! Now switch to **Plating** to buy armor for your bot."

        if not has_weapon:
            if self.category == "component":
                return "💡 **Tip:** Almost there! Buy a **Weapon** to complete your bot's loadout."
            else:
                return "💡 **Tip:** You need a weapon! Switch to **Weapons** to arm your bot."

        # Has all parts but hasn't assembled
        return "✅ **Ready to build!** You have all the parts. Use **🔧 Build Bot** from the hub to assemble your bot!"

    def _build_layout(self):
        player = self.db.get_player(self.ctx.author.id)
        item = self._get_current_item()
        items = self._get_items()

        category_emoji = {"chassis": "🚗", "plating": "🛡️", "component": "⚔️"}
        emoji = category_emoji.get(self.category, "📦")

        container = ui.Container(accent_colour=discord.Color.gold())
        container.add_item(
            ui.TextDisplay(f"# 🛒 Shop {emoji} {self.category.title()}\n-# Player: {self.ctx.author.mention}")
        )

        # Show first-time buyer tip
        tip = self._get_first_time_tip(player)
        if tip:
            container.add_item(ui.TextDisplay(tip))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        if not item:
            container.add_item(ui.TextDisplay("*No items available in this category*"))
            container.add_item(ui.TextDisplay(f"💰 Your Credits: {humanize_number(player.credits)}"))
            self.add_item(container)
            self.add_item(ShopCategoryRow(self))
            self.add_item(ShopNavigationRow())
            return

        # Build Item Details
        section_items = [ui.TextDisplay(f"## {item.name}")]

        owned_count = player.count_part(self.category, item.name)
        if owned_count > 0:
            section_items.append(ui.TextDisplay(f"*You own: {owned_count}*"))

        price_display = humanize_number(item.cost)
        if player.credits >= item.cost:
            section_items.append(ui.TextDisplay(f"**Price:** {price_display} 💰"))
        else:
            section_items.append(ui.TextDisplay(f"**Price:** ~~{price_display}~~ 💰 *(can't afford)*"))

        # Stats Display
        if self.category == "chassis":
            stats_text = (
                f"├ **Class:** {item.weight_class.value}\n"
                f"├ **Speed:** {item.speed} | **Rot:** {item.rotation_speed}\n"
                f"├ **Cap:** {item.weight_capacity} | **Wt:** {item.self_weight}\n"
                f"└ **Shield:** {item.shielding} | **AI:** {item.intelligence}"
            )
            section_items.append(ui.TextDisplay(f"**📊 Stats**\n{stats_text}"))

            quirk_name, quirk_desc = get_agility_quirk_detailed(item.agility)
            section_items.append(
                ui.TextDisplay(f"**🎯 Quirk:** Agility {item.agility:.0%}\n{quirk_name}\n*{quirk_desc}*")
            )

        elif self.category == "plating":
            stats_text = f"├ **Shielding:** +{item.shielding}\n└ **Weight:** {item.weight}"
            section_items.append(ui.TextDisplay(f"**📊 Stats:**\n{stats_text}"))

        else:
            stats_text = (
                f"├ **Type:** {item.component_type.value}\n"
                f"├ **Damage:** {item.damage_per_shot}\n"
                f"├ **Fire Rate:** {item.shots_per_minute}/min\n"
                f"├ **Range:** {item.min_range}-{item.max_range}\n"
                f"└ **Weight:** {item.weight}"
            )
            section_items.append(ui.TextDisplay(f"**📊 Stats:**\n{stats_text}"))

        section_items.append(ui.TextDisplay(f"*{item.description}*"))

        # Image - use Section with Thumbnail accessory if image exists
        image_path = _get_part_image_path(self.category, item.name)
        if image_path:
            # Use the actual file extension for the attachment URL
            ext = image_path.suffix  # .webp or .png
            thumbnail = ui.Thumbnail(media=f"attachment://part{ext}")
            item_section = ui.Section(*section_items[:3], accessory=thumbnail)  # Section can hold up to 3 TextDisplays
            container.add_item(item_section)
            # Add remaining items directly to container
            for item_display in section_items[3:]:
                container.add_item(item_display)
        else:
            for item_display in section_items:
                container.add_item(item_display)

        container.add_item(
            ui.TextDisplay(f"Item {self.index + 1}/{len(items)} • 💰 Credits: {humanize_number(player.credits)}")
        )

        self.add_item(container)
        self.add_item(ShopCategoryRow(self))
        self.add_item(ShopItemSelectRow(self))
        self.add_item(ShopNavigationRow())

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()

        image_file = self.get_image_file()
        if image_file:
            await interaction.response.edit_message(view=self, attachments=[image_file])
        else:
            await interaction.response.edit_message(view=self, attachments=[])


class PurchaseConfirmView(discord.ui.View):
    """Confirmation view for purchasing items"""

    def __init__(self, shop_view: ShopView, item, cog: t.Any):
        super().__init__(timeout=60)
        self.shop_view = shop_view
        self.item = item
        self.cog = cog
        self.user_id = shop_view.ctx.author.id
        self.completed = False  # Prevent double-processing

    @discord.ui.button(label="Confirm Purchase", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the purchase"""
        # Prevent double-processing if user somehow clicks twice
        if self.completed:
            await interaction.response.edit_message(content="This purchase has already been processed.", view=None)
            return
        self.completed = True

        # Re-fetch player from database to get current state
        player = self.cog.db.get_player(self.user_id)

        # Re-check credits with fresh data
        if player.credits < self.item.cost:
            await interaction.response.edit_message(
                content="❌ You no longer have enough credits!",
                view=None,
            )
            return

        # Check if player could build BEFORE this purchase
        could_build_before = self._can_build_bot(player)

        # Check garage limit for chassis purchases
        if self.shop_view.category == "chassis" and len(player.owned_chassis) >= 7:
            await interaction.response.edit_message(
                content="❌ **Garage Full!**\nYou can only have 7 bots max. Sell one before buying another.",
                view=None,
            )
            return

        # Process purchase atomically - deduct credits and add item together
        player.credits -= self.item.cost
        success = player.add_part(self.shop_view.category, self.item.name)

        if not success:
            # Refund if add_part failed (shouldn't happen after our check, but be safe)
            player.credits += self.item.cost
            await interaction.response.edit_message(
                content="❌ Failed to add item to inventory!",
                view=None,
            )
            return

        new_count = player.count_part(self.shop_view.category, self.item.name)

        # Save the changes to persist
        self.cog.save()

        # Check if player can NOW build after this purchase
        can_build_now = self._can_build_bot(player)
        had_battle_ready = len(player.get_battle_ready_bots()) > 0

        # Build the response message
        response = (
            f"✅ Purchased **{self.item.name}** for **{humanize_number(self.item.cost)}** credits!\n"
            f"📦 You now own: {new_count}\n"
            f"💰 Remaining: {humanize_number(player.credits)} credits"
        )

        # If this purchase enables building for the first time AND they have no battle-ready bots, add instructions
        if can_build_now and not could_build_before and not had_battle_ready:
            response += (
                "\n\n🎉 **You can now build your first bot!**\n"
                "Go to the **🏠 Garage** from the hub, then click on a chassis to equip your plating and weapon!"
            )

        await interaction.response.edit_message(content=response, view=None)

        # Refresh the shop view
        self.shop_view.clear_items()
        self.shop_view._build_layout()
        image_file = self.shop_view.get_image_file()
        if image_file:
            await self.shop_view.message.edit(view=self.shop_view, attachments=[image_file])
        else:
            await self.shop_view.message.edit(view=self.shop_view, attachments=[])
        self.stop()

    def _can_build_bot(self, player) -> bool:
        """Check if player has all 3 part types needed to build a bot"""
        has_chassis = len(player.owned_chassis) > 0
        has_plating = any(p.part_type == "plating" and p.quantity > 0 for p in player.equipment_inventory)
        has_weapon = any(p.part_type == "component" and p.quantity > 0 for p in player.equipment_inventory)
        return has_chassis and has_plating and has_weapon

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the purchase"""
        await interaction.response.edit_message(content="Purchase cancelled.", view=None)
        self.stop()


class ItemSelect(discord.ui.Select):
    """Dropdown for quick item selection"""

    def __init__(self, options: list[discord.SelectOption]):
        super().__init__(
            placeholder="Select an item...",
            options=options,
            custom_id="shop_item_select",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view: ShopView = self.view
        view.index = int(self.values[0])
        await view.refresh(interaction)
