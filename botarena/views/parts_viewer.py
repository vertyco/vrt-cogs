"""
Bot Arena - Parts Viewer View (Debug Tool)

A bot-owner only debug tool for previewing all part combinations.
Shows the fully rendered bot with selected chassis, plating, and weapon,
plus individual images of each selected part.
"""

from __future__ import annotations

import io
import typing as t

import discord
from discord import ui

if t.TYPE_CHECKING:
    from ..main import BotArena

from ..common.image_utils import load_image_bytes
from ..common.models import PartsRegistry, render_bot_image


def _load_part_preview(folder: str, name: str) -> t.Optional[bytes]:
    """Load a part image scaled up 2x for Discord preview visibility"""
    from PIL import Image

    img_bytes = load_image_bytes(folder, name)
    if not img_bytes:
        return None

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        # Scale up 2x for better visibility in Discord
        new_size = (img.width * 2, img.height * 2)
        img = img.resize(new_size, Image.Resampling.NEAREST)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except (OSError, ValueError):
        # OSError: corrupted image data
        # ValueError: invalid image mode conversion
        return None


class ChassisSelectRow(ui.ActionRow["PartsViewerLayout"]):
    """Dropdown for selecting chassis"""

    def __init__(self, registry: PartsRegistry, selected_chassis: str):
        super().__init__()
        self._registry = registry
        self._setup_options(selected_chassis)

    def _setup_options(self, selected_chassis: str):
        options = []
        for chassis in self._registry.all_chassis():
            options.append(
                discord.SelectOption(
                    label=chassis.name,
                    value=chassis.name,
                    default=chassis.name == selected_chassis,
                )
            )
        self.select_chassis.options = options[:25]

    @ui.select(placeholder="Select chassis...", options=[discord.SelectOption(label="Loading...", value="x")])
    async def select_chassis(self, interaction: discord.Interaction, select: ui.Select):
        view: PartsViewerLayout = self.view
        view.selected_chassis = select.values[0]
        await interaction.response.defer()
        await view.refresh_and_update(interaction)


class PlatingSelectRow(ui.ActionRow["PartsViewerLayout"]):
    """Dropdown for selecting plating"""

    def __init__(self, registry: PartsRegistry, selected_plating: t.Optional[str]):
        super().__init__()
        self._registry = registry
        self._setup_options(selected_plating)

    def _setup_options(self, selected_plating: t.Optional[str]):
        options = [
            discord.SelectOption(
                label="None",
                value="__none__",
                default=selected_plating is None,
            )
        ]
        for plating in self._registry.all_plating():
            options.append(
                discord.SelectOption(
                    label=plating.name,
                    value=plating.name,
                    default=plating.name == selected_plating,
                )
            )
        self.select_plating.options = options[:25]

    @ui.select(placeholder="Select plating...", options=[discord.SelectOption(label="Loading...", value="x")])
    async def select_plating(self, interaction: discord.Interaction, select: ui.Select):
        view: PartsViewerLayout = self.view
        value = select.values[0]
        view.selected_plating = None if value == "__none__" else value
        await interaction.response.defer()
        await view.refresh_and_update(interaction)


class WeaponSelectRow(ui.ActionRow["PartsViewerLayout"]):
    """Dropdown for selecting weapon"""

    def __init__(self, registry: PartsRegistry, selected_weapon: t.Optional[str]):
        super().__init__()
        self._registry = registry
        self._setup_options(selected_weapon)

    def _setup_options(self, selected_weapon: t.Optional[str]):
        options = [
            discord.SelectOption(
                label="None",
                value="__none__",
                default=selected_weapon is None,
            )
        ]
        for component in self._registry.all_components():
            options.append(
                discord.SelectOption(
                    label=component.name,
                    description=f"Mount: ({component.mount_x}, {component.mount_y})",
                    value=component.name,
                    default=component.name == selected_weapon,
                )
            )
        self.select_weapon.options = options[:25]

    @ui.select(placeholder="Select weapon...", options=[discord.SelectOption(label="Loading...", value="x")])
    async def select_weapon(self, interaction: discord.Interaction, select: ui.Select):
        view: PartsViewerLayout = self.view
        value = select.values[0]
        view.selected_weapon = None if value == "__none__" else value
        await interaction.response.defer()
        await view.refresh_and_update(interaction)


class PartsViewerLayout(ui.LayoutView):
    """Layout view for viewing rendered bot combinations (debug tool)"""

    def __init__(self, cog: "BotArena", owner_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.registry = cog.registry
        self.owner_id = owner_id
        self.message: t.Optional[discord.Message] = None

        # Image files for attachments
        self.bot_image_file: t.Optional[discord.File] = None
        self.chassis_image_file: t.Optional[discord.File] = None
        self.plating_image_file: t.Optional[discord.File] = None
        self.weapon_image_file: t.Optional[discord.File] = None

        # Default selections
        all_chassis = self.registry.all_chassis()
        self.selected_chassis = all_chassis[0].name if all_chassis else None
        self.selected_plating: t.Optional[str] = None
        self.selected_weapon: t.Optional[str] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This isn't your debug viewer!", ephemeral=True)
            return False
        return True

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

    def get_image_files(self) -> list[discord.File]:
        """Get the list of image files for attachment"""
        files = []
        if self.bot_image_file:
            files.append(self.bot_image_file)
        if self.chassis_image_file:
            files.append(self.chassis_image_file)
        if self.plating_image_file:
            files.append(self.plating_image_file)
        if self.weapon_image_file:
            files.append(self.weapon_image_file)
        return files

    async def refresh_and_update(self, interaction: discord.Interaction):
        """Refresh the view and update the message"""
        await self._generate_images()
        self._build_layout()
        files = self.get_image_files()
        await interaction.followup.edit_message(self.message.id, view=self, attachments=files)

    async def _generate_images(self):
        """Generate the combined bot image and individual part images"""
        import asyncio

        # Reset all files
        self.bot_image_file = None
        self.chassis_image_file = None
        self.plating_image_file = None
        self.weapon_image_file = None

        # Generate combined bot image (requires plating as the base layer)
        if self.selected_plating:
            try:
                bot_bytes = await render_bot_image(
                    plating_name=self.selected_plating,
                    weapon_name=self.selected_weapon,
                    orientation=0,  # Facing right
                )
                if bot_bytes:
                    self.bot_image_file = discord.File(io.BytesIO(bot_bytes), filename="bot_preview.png")
            except (OSError, ValueError, KeyError):
                # OSError: image file issues
                # ValueError: invalid image parameters
                # KeyError: part not found in registry
                pass

        # Generate individual part images in thread pool
        def load_parts():
            chassis_bytes = _load_part_preview("chassis", self.selected_chassis) if self.selected_chassis else None
            plating_bytes = _load_part_preview("plating", self.selected_plating) if self.selected_plating else None
            weapon_bytes = _load_part_preview("weapons", self.selected_weapon) if self.selected_weapon else None
            return chassis_bytes, plating_bytes, weapon_bytes

        chassis_bytes, plating_bytes, weapon_bytes = await asyncio.to_thread(load_parts)

        if chassis_bytes:
            self.chassis_image_file = discord.File(io.BytesIO(chassis_bytes), filename="chassis.png")
        if plating_bytes:
            self.plating_image_file = discord.File(io.BytesIO(plating_bytes), filename="plating.png")
        if weapon_bytes:
            self.weapon_image_file = discord.File(io.BytesIO(weapon_bytes), filename="weapon.png")

    def _build_layout(self):
        """Build the layout with current part selections"""
        self.clear_items()

        # Main container with combined bot preview
        container = ui.Container(accent_colour=discord.Colour.dark_gold())

        # Build simple part list
        chassis_name = self.selected_chassis or "None"
        plating_name = self.selected_plating or "None"
        weapon_name = self.selected_weapon or "None"

        # Get weapon mount point if selected
        mount_text = ""
        if self.selected_weapon:
            weapon = self.registry.get_component(self.selected_weapon)
            if weapon:
                mount_text = f" (mount: {weapon.mount_x}, {weapon.mount_y})"

        # Header with bot image thumbnail (like build menu)
        header_text = ui.TextDisplay("# 🔧 Parts Viewer\n**Combined Preview**")

        if self.bot_image_file:
            bot_thumbnail = ui.Thumbnail(media="attachment://bot_preview.png")
            header_section = ui.Section(header_text, accessory=bot_thumbnail)
            container.add_item(header_section)
        else:
            container.add_item(header_text)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Individual part sections with their images
        # Chassis section
        chassis_text = ui.TextDisplay(f"**Chassis:** {chassis_name}")
        if self.chassis_image_file:
            chassis_thumb = ui.Thumbnail(media="attachment://chassis.png")
            container.add_item(ui.Section(chassis_text, accessory=chassis_thumb))
        else:
            container.add_item(chassis_text)

        # Plating section
        plating_text = ui.TextDisplay(f"**Plating:** {plating_name}")
        if self.plating_image_file:
            plating_thumb = ui.Thumbnail(media="attachment://plating.png")
            container.add_item(ui.Section(plating_text, accessory=plating_thumb))
        else:
            container.add_item(plating_text)

        # Weapon section
        weapon_text = ui.TextDisplay(f"**Weapon:** {weapon_name}{mount_text}")
        if self.weapon_image_file:
            weapon_thumb = ui.Thumbnail(media="attachment://weapon.png")
            container.add_item(ui.Section(weapon_text, accessory=weapon_thumb))
        else:
            container.add_item(weapon_text)

        self.add_item(container)

        # Dropdowns for selection
        if self.selected_chassis:
            self.add_item(ChassisSelectRow(self.registry, self.selected_chassis))

        self.add_item(PlatingSelectRow(self.registry, self.selected_plating))
        self.add_item(WeaponSelectRow(self.registry, self.selected_weapon))

        # Close button row
        close_row = ui.ActionRow()
        close_btn = ui.Button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")

        async def close_callback(interaction: discord.Interaction):
            await interaction.response.defer()
            if self.message:
                try:
                    await self.message.delete()
                except discord.HTTPException:
                    pass
            self.stop()

        close_btn.callback = close_callback
        close_row.add_item(close_btn)
        self.add_item(close_row)

    @classmethod
    async def create(cls, cog: "BotArena", owner_id: int) -> "PartsViewerLayout":
        """Create and initialize the parts viewer with rendered bot image"""
        view = cls(cog, owner_id)
        await view._generate_images()
        view._build_layout()
        return view
