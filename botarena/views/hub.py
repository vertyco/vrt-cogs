"""
Bot Arena - Main Game Hub View

The central UI that guides players through the game experience.
Handles tutorial, campaign access, bot building, and more.
"""

from __future__ import annotations

import asyncio
import io
import logging
import typing as t

import discord
from discord import ui
from PIL import Image
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

if t.TYPE_CHECKING:
    from ..common.campaign import Mission
    from ..common.models import PartsRegistry
    from ..main import BotArena

from ..common.campaign import (
    CAMPAIGN_CHAPTERS,
    get_available_missions,
    get_chapter_for_mission,
    get_chapter_progress,
    get_mission_by_id,
)
from ..common.image_utils import find_image_path, load_image
from ..common.models import TEAM_COLOR_EMOJIS, TEAM_COLORS, Chassis, Component, Plating
from ..constants import get_random_tip
from .base import BotArenaView
from .shop import _get_part_image_path

log = logging.getLogger("red.vrt.botarena.hub")


def _create_bot_preview_image_sync(chassis_name: str, plating_name: str, weapon_name: str) -> t.Optional[io.BytesIO]:
    """
    Create a composite preview image showing all 3 bot parts side by side.

    This is the sync version that does blocking IO - call via asyncio.to_thread.

    Returns BytesIO buffer with the PNG image, or None if parts not found.
    """
    images = []

    # Load images that exist using shared utility
    chassis_img = load_image("chassis", chassis_name)
    if chassis_img:
        images.append(("Chassis", chassis_img))

    plating_img = load_image("plating", plating_name)
    if plating_img:
        images.append(("Plating", plating_img))

    weapon_img = load_image("weapons", weapon_name)
    if weapon_img:
        images.append(("Weapon", weapon_img))

    if not images:
        return None

    # Calculate composite dimensions
    # Scale each image to 80x80 for consistency
    target_size = 80
    padding = 10

    # Total width = (images * target_size) + ((images - 1) * padding)
    total_width = len(images) * target_size + (len(images) - 1) * padding
    total_height = target_size

    # Create composite with transparent background
    composite = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 0))

    x_offset = 0
    for _, img in images:
        # Resize maintaining aspect ratio
        img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)

        # Center in target area
        paste_x = x_offset + (target_size - img.width) // 2
        paste_y = (target_size - img.height) // 2

        composite.paste(img, (paste_x, paste_y), img)
        x_offset += target_size + padding

    # Save to BytesIO
    buffer = io.BytesIO()
    composite.save(buffer, format="WEBP", quality=95)
    buffer.seek(0)
    return buffer


async def create_bot_preview_image(chassis_name: str, plating_name: str, weapon_name: str) -> t.Optional[io.BytesIO]:
    """
    Create a composite preview image showing all 3 bot parts side by side.

    Async wrapper that runs PIL operations in a thread to avoid blocking.

    Returns BytesIO buffer with the PNG image, or None if parts not found.
    """
    return await asyncio.to_thread(_create_bot_preview_image_sync, chassis_name, plating_name, weapon_name)


def format_battle_stats(result: dict, winner_team: int) -> str:
    """
    Format battle statistics for display in embeds.

    Args:
        result: The battle result dictionary from the engine
        winner_team: The winning team (1 or 2, or 0 for draw)

    Returns:
        Formatted string showing battle statistics
    """
    bot_stats = result.get("bot_stats", {})
    if not bot_stats:
        return ""

    lines = []

    # Find survivor(s)
    survivors = [(bid, s) for bid, s in bot_stats.items() if s.get("survived", False)]

    if survivors:
        lines.append("**Survivors:**")
        for _, stats in survivors:
            name = stats.get("name", "Unknown")
            health = stats.get("final_health", 0)
            max_hp = stats.get("max_health", 100)
            health_pct = (health / max_hp * 100) if max_hp > 0 else 0
            dmg_dealt = stats.get("damage_dealt", 0)

            # Health bar
            bar_len = 10
            filled = int(health_pct / 100 * bar_len)
            bar = "▰" * filled + "▱" * (bar_len - filled)

            lines.append(f"• **{name}** `{bar}` {health:.0f}/{max_hp:.0f} HP ({health_pct:.0f}%)")
            lines.append(f"  └ Dealt **{dmg_dealt:.0f}** damage")

    # Show destroyed bots
    destroyed = [(bid, s) for bid, s in bot_stats.items() if not s.get("survived", False)]
    if destroyed:
        lines.append("\n**Destroyed:**")
        for _, stats in destroyed:
            name = stats.get("name", "Unknown")
            dmg_dealt = stats.get("damage_dealt", 0)
            lines.append(f"• ~~{name}~~ (dealt {dmg_dealt:.0f} dmg before destruction)")

    return "\n".join(lines)


class BattleResultLayout(BotArenaView):
    """Battle result view with optional Return to Hub button"""

    def __init__(
        self,
        ctx: t.Optional[commands.Context] = None,
        cog: t.Optional["BotArena"] = None,
        parent: t.Optional[ui.LayoutView] = None,
    ):
        # BattleResultLayout has optional ctx/cog, so we handle None case
        if ctx is not None and cog is not None:
            super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        else:
            # Fallback for when ctx/cog not provided
            ui.LayoutView.__init__(self, timeout=300)
            self.ctx = ctx
            self.cog = cog
            self.parent = parent
            self.message: t.Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Override to handle optional ctx case."""
        # If ctx is None, allow all interactions (no restriction)
        if self.ctx is None:
            return True
        # Otherwise use parent class behavior
        return await super().interaction_check(interaction)


class BattleResultActionsRow(ui.ActionRow["BattleResultLayout"]):
    """Actions row for battle result view with Return to Hub button"""

    @ui.button(label="Return to Hub", style=discord.ButtonStyle.primary, emoji="🏠")
    async def return_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.view.ctx or not self.view.cog:
            await interaction.response.send_message("Cannot return to hub.", ephemeral=True)
            return

        hub = GameHubLayout(self.view.ctx, self.view.cog)

        # Send NEW message instead of editing to preserve the battle video
        await interaction.response.send_message(view=hub)
        msg = await interaction.original_response()
        hub.message = msg

        # Disable the button and stop the old view
        self.return_button.disabled = True
        self.return_button.label = "Returned"
        await self.view.message.edit(view=self.view)
        self.view.stop()


def create_battle_result_view(
    title: str,
    description: str,
    color: discord.Color,
    duration: float,
    battle_stats: str,
    extra_fields: list[tuple[str, str]] | None = None,
    video_file: discord.File | None = None,
    ctx: t.Optional[commands.Context] = None,
    cog: t.Optional["BotArena"] = None,
    user: t.Optional[discord.User | discord.Member] = None,
    mission_name: t.Optional[str] = None,
    chapter_name: t.Optional[str] = None,
) -> tuple[BattleResultLayout, list[discord.File]]:
    """
    Create a LayoutView for battle results with an embedded video.

    Args:
        title: The result title (e.g., "🏆 Victory!")
        description: Main result description
        color: Accent color for the container
        duration: Battle duration in seconds
        battle_stats: Formatted battle statistics string
        extra_fields: Optional list of (name, value) tuples for additional info
        video_file: The video file to embed in the gallery
        ctx: Optional context for Return to Hub button
        cog: Optional cog reference for Return to Hub button
        user: The user who initiated the battle (for display in results)
        mission_name: Optional mission name for campaign battles
        chapter_name: Optional chapter name for campaign battles

    Returns:
        Tuple of (LayoutView, list of files to attach)
    """
    layout = BattleResultLayout(ctx=ctx, cog=cog)
    container = ui.Container(accent_colour=color)

    # Title and description with user attribution and mission info
    header_parts = [f"# {title}"]
    if user:
        header_parts.append(f"**Player:** {user.mention}")
    if mission_name:
        header_parts.append(f"**Mission:** {mission_name}")
    if chapter_name:
        header_parts.append(f"**Chapter:** {chapter_name}")
    header_parts.append(description)
    container.add_item(ui.TextDisplay("\n".join(header_parts)))

    # Duration
    container.add_item(ui.TextDisplay(f"**⏱️ Duration:** {duration:.1f}s"))

    # Extra fields (rewards, combatants, etc.)
    if extra_fields:
        for name, value in extra_fields:
            container.add_item(ui.TextDisplay(f"**{name}**\n{value}"))

    # Battle stats
    if battle_stats:
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(ui.TextDisplay(f"**📊 Battle Stats**\n{battle_stats}"))

    # Video gallery
    files = []
    if video_file:
        gallery = ui.MediaGallery()
        gallery.add_item(media=video_file)
        container.add_item(gallery)
        files.append(video_file)

    layout.add_item(container)

    # Add Return to Hub button if ctx and cog are provided
    if ctx and cog:
        layout.add_item(BattleResultActionsRow())

    return layout, files


# ─────────────────────────────────────────────────────────────────────────────
# STEP-BY-STEP TUTORIAL SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

# Tutorial step definitions
TUTORIAL_STEPS = [
    {
        "id": "buy_chassis_1",
        "title": "Step 1: Buy Your First Chassis",
        "description": (
            "The **Chassis** is the foundation of your bot - it's the body that holds everything together!\n\n"
            "**What it determines:**\n"
            "• ⚡ **Speed** - How fast your bot moves\n"
            "• 📦 **Capacity** - How heavy your equipment can be\n"
            "• 🧠 **Intelligence** - How smart the AI is in battle\n\n"
            "**Your Goal:** Buy a **DLZ-100** chassis (3,000 credits)\n"
            "-# It's a great starter chassis with balanced stats!"
        ),
        "button_label": "Go to Shop",
        "button_emoji": "🛒",
        "target_category": "chassis",
    },
    {
        "id": "buy_plating_1",
        "title": "Step 2: Get Some Armor",
        "description": (
            "**Plating** is your bot's armor - it protects you from enemy attacks!\n\n"
            "**What it provides:**\n"
            "• 🛡️ **Shielding** - More = more health in battle\n"
            "• ⚖️ **Weight** - Heavier plating means slower movement\n\n"
            "**Your Goal:** Buy **Chromitrex** plating (550 credits)\n"
            "-# Superior deflector armor - you'll need it for the first mission!"
        ),
        "button_label": "Go to Shop",
        "button_emoji": "🛒",
        "target_category": "plating",
    },
    {
        "id": "buy_weapon_1",
        "title": "Step 3: Arm Your Bot",
        "description": (
            "**Weapons** let you deal damage to enemies!\n\n"
            "**What matters:**\n"
            "• 💥 **Damage** - How hard each shot hits\n"
            "• 🔥 **Fire Rate** - Shots per minute\n"
            "• ↔️ **Range** - How far you can shoot\n\n"
            "**Your Goal:** Buy a **Raptor DT-01** weapon (500 credits)\n"
            "-# A solid mid-range blaster - much stronger than the basic Zintek!"
        ),
        "button_label": "Go to Shop",
        "button_emoji": "🛒",
        "target_category": "component",
    },
    {
        "id": "equip_bot_1",
        "title": "Step 4: Assemble Your Bot",
        "description": (
            "Now you have all the parts! Time to put them together in the **Garage**.\n\n"
            "**In the Garage you can:**\n"
            "• Select your chassis from the dropdown\n"
            "• Equip your plating and weapon\n"
            "• Configure battle tactics\n\n"
            "**Your Goal:** Equip plating AND weapon on your chassis\n"
            "-# A bot with all 3 parts is marked ⚔️ Battle Ready!"
        ),
        "button_label": "Go to Garage",
        "button_emoji": "🏠",
        "target_category": None,
    },
    {
        "id": "buy_chassis_2",
        "title": "Step 5: Build a Second Bot",
        "description": (
            "**The first mission has 2 enemies!** You'll need 2 bots to have a fair fight.\n\n"
            "Repeat what you learned:\n"
            "1️⃣ Buy another **DLZ-100** chassis (3,000 credits)\n"
            "2️⃣ Buy **Chromitrex** plating (550 credits)\n"
            "3️⃣ Buy **Raptor DT-01** weapon (500 credits)\n"
            "4️⃣ Go to Garage and equip everything\n\n"
            "**Your Goal:** Have **2 battle-ready bots**\n"
            "-# Budget check: 8,100 total for 2 bots, you started with 8,200!"
        ),
        "button_label": "Go to Shop",
        "button_emoji": "🛒",
        "target_category": "chassis",
    },
    {
        "id": "start_campaign",
        "title": "Step 6: Start the Campaign!",
        "description": (
            "🎉 **You're ready for battle!**\n\n"
            "Your 2 bots are equipped and ready to fight. The **Campaign** is where you:\n"
            "• 💰 Earn credits from victories\n"
            "• 🔓 Unlock new parts and upgrades\n"
            "• 📈 Progress through increasingly difficult missions\n\n"
            "**Your Goal:** Start Mission 1-1 and WIN!\n"
            "-# Good luck, Commander! 🤖⚔️"
        ),
        "button_label": "Start Campaign",
        "button_emoji": "⚔️",
        "target_category": None,
    },
]


class TutorialActionRow(ui.ActionRow["TutorialLayout"]):
    """Action buttons for the step-by-step tutorial"""

    def __init__(self, step_data: dict, step_complete: bool, can_advance: bool, is_final_step: bool, current_step: int):
        super().__init__()
        self._step_data = step_data
        self._step_complete = step_complete
        self._can_advance = can_advance
        self._is_final_step = is_final_step
        self._current_step = current_step
        self._update_buttons()

    def _update_buttons(self):
        # Previous button - disabled on first step
        self.previous_button.disabled = self._current_step == 0

        # Main action button - "Do This Now"
        if self._step_complete:
            self.action_button.label = "✅ Complete!"
            self.action_button.style = discord.ButtonStyle.success
            self.action_button.disabled = True
        else:
            self.action_button.label = self._step_data.get("button_label", "Do This Now")
            self.action_button.style = discord.ButtonStyle.primary
            self.action_button.disabled = False
            self.action_button.emoji = self._step_data.get("button_emoji")

        # Next step button
        if self._is_final_step:
            self.next_button.label = "Finish Tutorial"
            self.next_button.emoji = "🏁"
        else:
            self.next_button.label = "Next Step"
            self.next_button.emoji = "➡️"

        self.next_button.disabled = not self._can_advance

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go back to the previous tutorial step"""
        if self._current_step > 0:
            self.view.current_step -= 1
            await self.view.refresh(interaction)
        else:
            # Already on first step, just acknowledge the interaction
            await interaction.response.defer()

    @ui.button(label="Do This Now", style=discord.ButtonStyle.primary)
    async def action_button(self, interaction: discord.Interaction, button: ui.Button):
        """Navigate to the relevant view for this step"""
        step_id = self._step_data["id"]
        target = self._step_data.get("target_category")

        if step_id == "equip_bot_1" or (step_id == "buy_chassis_2" and self._step_complete):
            # Go to Garage
            from .inventory import GarageLayout

            view = await GarageLayout.create(self.view.ctx, self.view.cog, parent=self.view)
            self.view.navigate_to_child(view)
            await view.send(interaction)

        elif step_id == "start_campaign":
            # Go to Campaign
            view = CampaignLayout(self.view.ctx, self.view.cog, parent=self.view)
            self.view.navigate_to_child(view)
            await view.send(interaction)

        else:
            # Go to Shop with the appropriate category
            from .shop import ShopView

            view = ShopView(
                self.view.ctx, self.view.cog.db, self.view.cog.registry, cog=self.view.cog, parent=self.view
            )
            if target:
                view.category = target
                view.index = 0
                view.clear_items()
                view._build_layout()

            self.view.navigate_to_child(view)
            await view.send(interaction)

    @ui.button(label="Next Step", style=discord.ButtonStyle.success, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        if self._is_final_step:
            # Complete tutorial
            player = self.view.cog.db.get_player(self.view.ctx.author.id)
            player.has_seen_tutorial = True
            self.view.cog.save()

            # Go to main hub
            view = GameHubLayout(self.view.ctx, self.view.cog)
            view.message = self.view.message
            await interaction.response.edit_message(view=view)
        else:
            # Advance to next step
            self.view.current_step += 1
            await self.view.refresh(interaction)


class TutorialQuickStartRow(ui.ActionRow["TutorialLayout"]):
    """Quick Start option for players who want to skip the tutorial"""

    @ui.button(label="📝 Skip (Build from Scratch)", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        """Skip the tutorial without buying anything"""
        player = self.view.cog.db.get_player(self.view.ctx.author.id)
        player.has_seen_tutorial = True
        self.view.cog.save()

        # Go to main hub
        view = GameHubLayout(self.view.ctx, self.view.cog)
        view.message = self.view.message
        await interaction.response.edit_message(view=view)

        await interaction.followup.send(
            "📝 **Tutorial Skipped!**\n\n"
            "You have your starting credits - time to build your bot army!\n\n"
            "**Getting Started:**\n"
            "1️⃣ Visit the **🛒 Shop** to buy a chassis, plating, and weapon\n"
            "2️⃣ Go to the **🏠 Garage** to equip your parts\n"
            "3️⃣ Hit **⚔️ Campaign** to start fighting!\n\n"
            "-# 💡 Tip: You'll need 2 battle-ready bots to beat the first mission!",
            ephemeral=True,
        )

    @ui.button(label="⚡ Quick Start (Pre-built Bots)", style=discord.ButtonStyle.secondary)
    async def quickstart_button(self, interaction: discord.Interaction, button: ui.Button):
        """Give the player TWO starter bots to tackle the first mission!"""
        player = self.view.cog.db.get_player(self.view.ctx.author.id)
        registry = self.view.cog.registry

        # Starter kit parts - competitive gear to beat the first mission!
        chassis_name = "DLZ-100"
        plating_name = "Chromitrex"
        weapon_name = "Raptor DT-01"

        chassis_def = registry.get_chassis(chassis_name)
        plating_def = registry.get_plating(plating_name)
        weapon_def = registry.get_component(weapon_name)

        if not all([chassis_def, plating_def, weapon_def]):
            await interaction.response.send_message("❌ Error setting up starter kit!", ephemeral=True)
            return

        # Cost for 2 complete bots
        cost_per_bot = chassis_def.cost + plating_def.cost + weapon_def.cost
        total_cost = cost_per_bot * 2

        if player.credits < total_cost:
            await interaction.response.send_message(
                f"❌ Not enough credits! Need {humanize_number(total_cost)} but you have {humanize_number(player.credits)}.",
                ephemeral=True,
            )
            return

        # Deduct credits
        player.credits -= total_cost

        # Create TWO bots with equipment already attached
        bot1 = player.add_chassis(chassis_name, custom_name="Alpha")
        bot1.equipped_plating = plating_name
        bot1.equipped_weapon = weapon_name

        bot2 = player.add_chassis(chassis_name, custom_name="Bravo")
        bot2.equipped_plating = plating_name
        bot2.equipped_weapon = weapon_name

        # Mark tutorial as seen
        player.has_seen_tutorial = True
        self.view.cog.save()

        # Show success and go to hub
        view = GameHubLayout(self.view.ctx, self.view.cog)
        view.message = self.view.message
        await interaction.response.edit_message(view=view)

        # Send a followup message about the starter kit
        await interaction.followup.send(
            f"🎉 **Starter Kit Acquired!**\n\n"
            f"You now have **2 battle-ready bots**:\n\n"
            f"**Alpha** & **Bravo**\n"
            f"• 🚗 **{chassis_name}** chassis\n"
            f"• 🛡️ **{plating_name}** plating\n"
            f"• ⚔️ **{weapon_name}** weapon\n\n"
            f"💰 Cost: **{humanize_number(total_cost)}** credits\n"
            f"💰 Remaining: **{humanize_number(player.credits)}** credits\n\n"
            f"-# 💡 You'll need both bots to beat the first mission!\n"
            f"Click **⚔️ Campaign** to start fighting!",
            ephemeral=True,
        )


class TutorialLayout(BotArenaView):
    """Interactive step-by-step tutorial for new players"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self.current_step = 0
        self._determine_current_step()
        self._build_layout()

    def _determine_current_step(self):
        """Check player's progress to determine which step they're on"""
        player = self.cog.db.get_player(self.ctx.author.id)
        battle_ready_count = len(player.get_battle_ready_bots())
        chassis_count = len(player.owned_chassis)

        # Count inventory items
        plating_count = sum(1 for p in player.equipment_inventory if p.part_type == "plating" and p.quantity > 0)
        weapon_count = sum(1 for p in player.equipment_inventory if p.part_type == "component" and p.quantity > 0)

        # Also count equipped items
        equipped_plating = sum(1 for c in player.owned_chassis if c.equipped_plating)
        equipped_weapon = sum(1 for c in player.owned_chassis if c.equipped_weapon)
        total_plating = plating_count + equipped_plating
        total_weapons = weapon_count + equipped_weapon

        # Determine step based on progress
        if battle_ready_count >= 2:
            # Ready for campaign!
            self.current_step = 5  # start_campaign
        elif battle_ready_count >= 1:
            # Has one battle-ready bot, need second
            self.current_step = 4  # buy_chassis_2
        elif chassis_count >= 1 and total_plating >= 1 and total_weapons >= 1:
            # Has parts but not assembled
            self.current_step = 3  # equip_bot_1
        elif chassis_count >= 1 and total_plating >= 1:
            # Has chassis and plating, needs weapon
            self.current_step = 2  # buy_weapon_1
        elif chassis_count >= 1:
            # Has chassis, needs plating
            self.current_step = 1  # buy_plating_1
        else:
            # Brand new - start from beginning
            self.current_step = 0  # buy_chassis_1

    def _check_step_complete(self, step_index: int) -> bool:
        """Check if a specific step is complete"""
        player = self.cog.db.get_player(self.ctx.author.id)
        step_id = TUTORIAL_STEPS[step_index]["id"]

        battle_ready_count = len(player.get_battle_ready_bots())
        chassis_count = len(player.owned_chassis)

        # Count inventory items
        plating_count = sum(1 for p in player.equipment_inventory if p.part_type == "plating" and p.quantity > 0)
        weapon_count = sum(1 for p in player.equipment_inventory if p.part_type == "component" and p.quantity > 0)

        # Also count equipped items
        equipped_plating = sum(1 for c in player.owned_chassis if c.equipped_plating)
        equipped_weapon = sum(1 for c in player.owned_chassis if c.equipped_weapon)
        total_plating = plating_count + equipped_plating
        total_weapons = weapon_count + equipped_weapon

        if step_id == "buy_chassis_1":
            return chassis_count >= 1
        elif step_id == "buy_plating_1":
            return total_plating >= 1
        elif step_id == "buy_weapon_1":
            return total_weapons >= 1
        elif step_id == "equip_bot_1":
            return battle_ready_count >= 1
        elif step_id == "buy_chassis_2":
            # Need 2 chassis, 2 plating, 2 weapons (or 2 battle ready)
            return battle_ready_count >= 2 or (chassis_count >= 2 and total_plating >= 2 and total_weapons >= 2)
        elif step_id == "start_campaign":
            return battle_ready_count >= 2
        return False

    def _get_progress_display(self) -> str:
        """Get a visual progress bar for the tutorial"""
        total = len(TUTORIAL_STEPS)
        completed = sum(1 for i in range(total) if self._check_step_complete(i))

        # Build progress bar
        bar = ""
        for i in range(total):
            if self._check_step_complete(i):
                bar += "✅"
            elif i == self.current_step:
                bar += "🔵"
            else:
                bar += "⚪"

        return f"{bar} ({completed}/{total})"

    def _get_inventory_summary(self) -> str:
        """Get a summary of what the player currently has"""
        player = self.cog.db.get_player(self.ctx.author.id)

        chassis_count = len(player.owned_chassis)
        battle_ready = len(player.get_battle_ready_bots())

        # Count inventory
        plating_inv = sum(p.quantity for p in player.equipment_inventory if p.part_type == "plating")
        weapon_inv = sum(p.quantity for p in player.equipment_inventory if p.part_type == "component")

        # Count equipped
        equipped_plating = sum(1 for c in player.owned_chassis if c.equipped_plating)
        equipped_weapon = sum(1 for c in player.owned_chassis if c.equipped_weapon)

        lines = [f"💰 **Credits:** {humanize_number(player.credits)}"]

        if chassis_count > 0:
            lines.append(f"🚗 **Chassis:** {chassis_count} ({battle_ready} battle ready)")
        if plating_inv > 0 or equipped_plating > 0:
            lines.append(f"🛡️ **Plating:** {plating_inv} in inventory, {equipped_plating} equipped")
        if weapon_inv > 0 or equipped_weapon > 0:
            lines.append(f"⚔️ **Weapons:** {weapon_inv} in inventory, {equipped_weapon} equipped")

        return "\n".join(lines)

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            elif hasattr(child, "children"):
                for item in getattr(child, "children"):
                    if hasattr(item, "disabled"):
                        setattr(item, "disabled", True)

    async def refresh(self, interaction: discord.Interaction):
        # Rebuild the view without auto-advancing - respect manual navigation
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def _build_layout(self):
        # Use current_step as-is - don't auto-advance (allows back button to work)
        step_data = TUTORIAL_STEPS[self.current_step]
        step_complete = self._check_step_complete(self.current_step)
        is_final_step = self.current_step == len(TUTORIAL_STEPS) - 1

        # Can advance if current step is complete
        can_advance = step_complete

        # Main container
        container = ui.Container(accent_colour=discord.Color.green() if step_complete else discord.Color.blue())

        # Header with progress
        progress = self._get_progress_display()
        container.add_item(ui.TextDisplay(f"# 🎓 Bot Arena Tutorial\n{progress}\n-# Player: {self.ctx.author.mention}"))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Step content
        status_icon = "✅" if step_complete else f"📍 {self.current_step + 1}/{len(TUTORIAL_STEPS)}"
        container.add_item(ui.TextDisplay(f"## {status_icon} {step_data['title']}"))
        container.add_item(ui.TextDisplay(step_data["description"]))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Inventory summary
        container.add_item(ui.TextDisplay(f"**📦 Your Inventory:**\n{self._get_inventory_summary()}"))

        self.add_item(container)

        # Action row for this step
        self.add_item(TutorialActionRow(step_data, step_complete, can_advance, is_final_step, self.current_step))

        # Quick start option (always available)
        self.add_item(TutorialQuickStartRow())


class MainMenuRow(ui.ActionRow["GameHubLayout"]):
    """Main menu navigation buttons"""

    def __init__(self, has_battle_ready_bots: bool = True):
        super().__init__()
        # Disable Campaign button if player has no battle-ready bots
        if not has_battle_ready_bots:
            self.campaign_button.disabled = True
            self.campaign_button.style = discord.ButtonStyle.secondary

    @ui.button(label="Campaign", style=discord.ButtonStyle.success, emoji="⚔️")
    async def campaign_button(self, interaction: discord.Interaction, button: ui.Button):
        player = self.view.cog.db.get_player(interaction.user.id)
        battle_ready = player.get_battle_ready_bots()
        if not battle_ready:
            await interaction.response.send_message(
                "❌ You need at least one **battle-ready bot** to enter the campaign!\n\n"
                "💡 A battle-ready bot needs a **chassis**, **plating**, and **weapon** equipped.\n"
                "Visit the **🛒 Shop** to buy parts, then go to the **🏠 Garage** to equip them!",
                ephemeral=True,
            )
            return
        view = CampaignLayout(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await view.send(interaction)

    @ui.button(label="Garage", style=discord.ButtonStyle.secondary, emoji="🏠")
    async def bots_button(self, interaction: discord.Interaction, button: ui.Button):
        from .inventory import GarageLayout

        view = await GarageLayout.create(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await view.send(interaction)

    @ui.button(label="Shop", style=discord.ButtonStyle.secondary, emoji="🛒")
    async def shop_button(self, interaction: discord.Interaction, button: ui.Button):
        from .shop import ShopView

        view = ShopView(self.view.ctx, self.view.cog.db, self.view.cog.registry, cog=self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await view.send(interaction)


class SecondaryMenuRow(ui.ActionRow["GameHubLayout"]):
    """Secondary menu actions"""

    def __init__(self, has_battle_ready_bots: bool = True):
        super().__init__()
        # Disable PvP button if player has no battle-ready bots
        if not has_battle_ready_bots:
            self.pvp_button.disabled = True
            self.pvp_button.style = discord.ButtonStyle.secondary

    @ui.button(label="Profile", style=discord.ButtonStyle.secondary, emoji="📊")
    async def profile_button(self, interaction: discord.Interaction, button: ui.Button):
        view = ProfileLayout(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await interaction.response.edit_message(view=view)

    @ui.button(label="PvP", style=discord.ButtonStyle.danger, emoji="👊")
    async def pvp_button(self, interaction: discord.Interaction, button: ui.Button):
        player = self.view.cog.db.get_player(self.view.ctx.author.id)
        battle_ready = player.get_battle_ready_bots()
        if not battle_ready:
            await interaction.response.send_message(
                "❌ You need at least one **battle-ready bot** to challenge players!\n\n"
                "💡 A battle-ready bot needs a **chassis**, **plating**, and **weapon** equipped.\n"
                "Visit the **🛒 Shop** to buy parts, then go to the **🏠 Garage** to equip them!",
                ephemeral=True,
            )
            return

        view = PvPLayout(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await interaction.response.edit_message(view=view)

    @ui.button(label="Tutorial", style=discord.ButtonStyle.secondary, emoji="❓")
    async def tutorial_button(self, interaction: discord.Interaction, button: ui.Button):
        view = TutorialLayout(self.view.ctx, self.view.cog, parent=self.view)
        self.view.navigate_to_child(view)
        await interaction.response.edit_message(view=view)


class GameHubLayout(BotArenaView):
    """Main game hub - central navigation for all features"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self._build_layout()

    def _build_layout(self):
        player = self.cog.db.get_player(self.ctx.author.id)
        completed, total = player.campaign_progress
        bot_count = len(player.owned_chassis)

        container = ui.Container(accent_colour=discord.Color.blue())
        container.add_item(
            ui.TextDisplay(
                f"# 🤖 Bot Arena\n*Build bots. Fight battles. Become champion.*\n-# Player: {self.ctx.author.mention}"
            )
        )

        # Stats display
        stats_text = (
            f"**📊 Your Progress** | **🎮 Battle Record**\n"
            f"💰 Credits: {humanize_number(player.credits)} | ⚔️ Battles: {player.total_battles}\n"
            f"🤖 Bots: {bot_count} | 🏆 Wins: {player.wins}\n"
            f"📈 Campaign: {completed}/{total} | 📉 Losses: {player.losses}"
        )
        container.add_item(ui.TextDisplay(stats_text))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Bot Overview - Quick view of all bots with loadouts
        if player.owned_chassis:
            bot_lines = []
            for chassis in player.owned_chassis:
                plating = chassis.equipped_plating or "*none*"
                weapon = chassis.equipped_weapon or "*none*"

                # Get chassis stats for HP display
                c = self.cog.registry.get_chassis(chassis.chassis_name)
                p = self.cog.registry.get_plating(chassis.equipped_plating) if chassis.equipped_plating else None
                total_hp = (c.shielding if c else 0) + (p.shielding if p else 0)

                bot_lines.append(f"**{chassis.display_name}** ❤️{total_hp}\n-# 🛡️ {plating} | ⚔️ {weapon}")

            battle_ready_count = len(player.get_battle_ready_bots())
            bot_overview = f"**🤖 Your Bots** ({battle_ready_count} battle ready)\n" + "\n".join(bot_lines)
            container.add_item(ui.TextDisplay(bot_overview))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Next Mission / Guidance
        available = get_available_missions(set(player.completed_missions))
        battle_ready = player.get_battle_ready_bots()
        if bot_count == 0:
            # Brand new player with no chassis at all
            guidance = (
                "## 🎉 Welcome to Bot Arena!\n"
                "*You'll need to build your first bot from scratch.*\n\n"
                "**Getting Started:**\n"
                "1️⃣ Visit the **🛒 Shop** to buy a **Chassis** (the body of your bot)\n"
                "2️⃣ Buy **Plating** (armor) and a **Weapon**\n"
                "3️⃣ Go to **🏠 Garage** to equip your parts\n"
                "4️⃣ Start the **⚔️ Campaign** to earn credits and unlock new parts!\n\n"
                f"💰 You have **{humanize_number(player.credits)} credits** to spend!"
            )
            container.add_item(ui.TextDisplay(guidance))
        elif not battle_ready:
            # Player has parts but no fully-equipped bots
            guidance = (
                "## 🔧 Almost Ready!\n"
                "You have chassis, but none are battle-ready yet.\n\n"
                "💡 A battle-ready bot needs:\n"
                "• A **Chassis** ✅\n"
                "• **Plating** (armor)\n"
                "• A **Weapon**\n\n"
                "Go to **🏠 Garage** to equip your chassis, or visit the **🛒 Shop** for more parts!"
            )
            container.add_item(ui.TextDisplay(guidance))
        elif available:
            next_mission = available[0]
            mission_text = (
                f"## 🎯 Next Mission: {next_mission.name}\n"
                f"**Difficulty:** {next_mission.difficulty.value}\n"
                f"*{next_mission.description}*"
            )
            container.add_item(ui.TextDisplay(mission_text))
        else:
            container.add_item(
                ui.TextDisplay(
                    "## 🎯 Campaign Complete!\nYou've conquered all missions! Challenge other players in PvP!"
                )
            )

        self.add_item(container)
        self.add_item(MainMenuRow(has_battle_ready_bots=len(battle_ready) > 0))
        self.add_item(SecondaryMenuRow(has_battle_ready_bots=len(battle_ready) > 0))

    async def refresh(self, interaction: discord.Interaction):
        """Rebuild layout and refresh the message"""
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)


class ChapterSelectRow(ui.ActionRow["CampaignLayout"]):
    """Dropdown for selecting a chapter"""

    def __init__(self, completed_set: set[str], selected_chapter: int):
        super().__init__()
        options = []
        for chapter in CAMPAIGN_CHAPTERS:
            completed, total = get_chapter_progress(chapter.id, completed_set)
            status = "✅" if completed == total else f"({completed}/{total})"
            options.append(
                discord.SelectOption(
                    label=f"Chapter {chapter.id}: {chapter.name}",
                    description=f"{status} - {chapter.description[:50]}...",
                    value=str(chapter.id),
                    default=chapter.id == selected_chapter,
                )
            )
        self.chapter_select.options = options

    @ui.select(placeholder="Select Chapter...")
    async def chapter_select(self, interaction: discord.Interaction, select: ui.Select):
        self.view.selected_chapter = int(select.values[0])
        await self.view.refresh(interaction)


class MissionSelectRow(ui.ActionRow["CampaignLayout"]):
    """Dropdown for selecting a mission"""

    def __init__(self, completed_set: set[str], selected_chapter: int, player_credits: int):
        super().__init__()
        chapter = CAMPAIGN_CHAPTERS[selected_chapter - 1]

        options = []
        for mission in chapter.missions:
            is_completed = mission.id in completed_set
            is_available = mission.required_mission is None or mission.required_mission in completed_set
            can_afford = player_credits >= mission.entry_fee

            if is_completed:
                status = "✅"
            elif not is_available:
                status = "🔒"
            elif not can_afford:
                status = "💸"  # Unlocked but can't afford
            else:
                status = "🔓"

            # Build description showing entry fee and reward
            if mission.entry_fee > 0:
                fee_text = f"Fee: {humanize_number(mission.entry_fee)}"
                if not can_afford and is_available and not is_completed:
                    fee_text += " (need more credits!)"
            else:
                fee_text = "Free entry"
            desc = f"{mission.difficulty.value} | {fee_text} | 🏆 {humanize_number(mission.credit_reward)}"

            options.append(
                discord.SelectOption(
                    label=f"{status} {mission.name}",
                    description=desc[:100],  # Discord limit
                    value=mission.id,
                    emoji=status,
                )
            )

        self.mission_select.options = options if options else [discord.SelectOption(label="No missions", value="none")]

    @ui.select(placeholder="Select Mission to Start...")
    async def mission_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            return

        mission_id = select.values[0]
        mission = get_mission_by_id(mission_id)
        player = self.view.cog.db.get_player(interaction.user.id)
        completed_set = set(player.completed_missions)

        # Check if available
        if mission.required_mission and mission.required_mission not in completed_set:
            await interaction.response.send_message("🔒 Complete the previous mission first!", ephemeral=True)
            return

        # Check if player has battle-ready bots
        battle_ready = player.get_battle_ready_bots()
        if not battle_ready:
            await interaction.response.send_message(
                "❌ You need at least one battle-ready bot! Build one first.", ephemeral=True
            )
            return

        # Show mission briefing and bot selection
        view = MissionBriefingLayout(self.view.ctx, self.view.cog, mission, parent=self.view)
        self.view.navigate_to_child(view)
        await interaction.response.edit_message(view=view)


class CampaignNavigationRow(ui.ActionRow["CampaignLayout"]):
    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.navigate_back(interaction)


class CampaignLayout(BotArenaView):
    """Campaign chapter and mission selection"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)

        # Pre-select the chapter containing the first uncompleted mission
        self.selected_chapter = self._get_current_chapter()

        self._build_layout()

    def _get_current_chapter(self) -> int:
        """Find the chapter that has the first uncompleted mission."""
        player = self.cog.db.get_player(self.ctx.author.id)
        completed_set = set(player.completed_missions)

        for chapter in CAMPAIGN_CHAPTERS:
            for mission in chapter.missions:
                # Check if this mission is uncompleted and available
                is_completed = mission.id in completed_set
                is_available = mission.required_mission is None or mission.required_mission in completed_set

                if not is_completed and is_available:
                    # Found the first uncompleted mission that's available
                    return chapter.id

        # All missions completed, or none available - default to chapter 1
        return 1

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()
        await self.send(interaction)

    def _build_layout(self):
        player = self.cog.db.get_player(self.ctx.author.id)
        completed_set = set(player.completed_missions)
        chapter = CAMPAIGN_CHAPTERS[self.selected_chapter - 1]
        completed, total = get_chapter_progress(chapter.id, completed_set)

        container = ui.Container(accent_colour=discord.Color.green() if completed == total else discord.Color.blue())

        # Chapter title section (no image)
        container.add_item(
            ui.TextDisplay(
                f"# 📖 Chapter {chapter.id}: {chapter.name}\n*{chapter.description}*\n-# Player: {self.ctx.author.mention}"
            )
        )

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Mission list
        mission_text = ""
        for mission in chapter.missions:
            is_completed = mission.id in completed_set
            is_available = mission.required_mission is None or mission.required_mission in completed_set
            can_afford = player.credits >= mission.entry_fee

            if is_completed:
                status = "✅"
            elif not is_available:
                status = "🔒"
            elif not can_afford:
                status = "💸"  # Unlocked but can't afford
            else:
                status = "🔓"

            diff_emoji = {"Tutorial": "🟢", "Easy": "🟢", "Medium": "🟡", "Hard": "🟠", "Extreme": "🔴", "Boss": "💀"}
            diff = diff_emoji.get(mission.difficulty.value, "⚪")

            # Show entry fee for non-completed missions
            fee_text = ""
            if not is_completed and mission.entry_fee > 0:
                fee_text = f" | 💰 {humanize_number(mission.entry_fee)}"

            mission_text += f"\n**{status} {mission.name}** {diff}{fee_text}\n-# {mission.description}\n"

        container.add_item(ui.TextDisplay(mission_text))

        self.add_item(container)
        self.add_item(ChapterSelectRow(completed_set, self.selected_chapter))
        self.add_item(MissionSelectRow(completed_set, self.selected_chapter, player.credits))
        self.add_item(CampaignNavigationRow())


class SelectBotRow(ui.ActionRow["MissionBriefingLayout"]):
    """Dropdown for selecting bots for the mission"""

    def __init__(self, player, selected_bots, registry: "PartsRegistry"):
        super().__init__()
        options = []

        # Build list with spawn order for position calculation
        selected_chassis = []
        for bot_id in selected_bots:
            chassis = player.get_chassis_by_id(bot_id)
            if chassis:
                order = chassis.spawn_order if chassis.spawn_order > 0 else 999
                selected_chassis.append((order, chassis))
        selected_chassis.sort(key=lambda x: x[0])

        # Calculate position labels
        position_labels = (
            ["Left", "Middle", "Right"]
            if len(selected_chassis) == 3
            else ["Left", "Right"]
            if len(selected_chassis) == 2
            else ["Center"]
        )
        position_map = {
            chassis.id: position_labels[idx]
            for idx, (_, chassis) in enumerate(selected_chassis)
            if idx < len(position_labels)
        }

        for chassis in player.get_battle_ready_bots():
            bot = chassis.to_bot(registry)
            if bot:
                is_selected = chassis.id in selected_bots
                # Add position label if this bot is selected
                pos_prefix = f"[{position_map[chassis.id]}] " if chassis.id in position_map else ""
                # Show HP, weight, weapon name, damage, and speed
                desc = f"⚖️{bot.total_weight}wt | ❤️{bot.total_shielding} | ⚔️{bot.component.name} ({bot.component.damage_per_shot}dmg)"
                options.append(
                    discord.SelectOption(
                        label=f"{pos_prefix}{chassis.display_name}",
                        description=desc[:100],
                        value=chassis.id,
                        default=is_selected,
                    )
                )

        if options:
            self.bot_select.options = options  # type: ignore[attr-defined]
            self.bot_select.max_values = min(3, len(options))  # type: ignore[attr-defined]  # Max 3 bots per mission
        else:
            self.bot_select.options = [discord.SelectOption(label="No bots available", value="none")]  # type: ignore[attr-defined]
            self.bot_select.disabled = True  # type: ignore[attr-defined]

    @ui.select(placeholder="Select bot(s) for this mission...", min_values=0, max_values=1)
    async def bot_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values and select.values[0] == "none":
            await interaction.response.defer()
            return
        self.view.selected_bots = list(select.values)
        await self.view.refresh(interaction)


class MissionActionRow(ui.ActionRow["MissionBriefingLayout"]):
    """Actions for mission briefing"""

    def __init__(self, can_start: bool = True, start_disabled_reason: str = ""):
        super().__init__()
        if not can_start:
            self.start_button.disabled = True
            self.start_button.style = discord.ButtonStyle.secondary
        self._start_disabled_reason = start_disabled_reason

    @ui.button(label="Start Battle!", style=discord.ButtonStyle.success, emoji="⚔️")
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        if self._start_disabled_reason:
            await interaction.response.send_message(self._start_disabled_reason, ephemeral=True)
            return
        await self.view.run_battle(interaction)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.navigate_back(interaction)


class MissionBriefingLayout(BotArenaView):
    """Mission briefing and bot selection before battle"""

    def __init__(
        self, ctx: commands.Context, cog: "BotArena", mission: "Mission", parent: t.Optional[ui.LayoutView] = None
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self.mission = mission
        self.battle_in_progress = False

        # Start with no bots selected - user must actively choose
        self.selected_bots: list[str] = []

        self._build_layout()

    def get_attachments(self) -> list[discord.File]:
        """Get the mission-specific arena background image file"""
        image_path = find_image_path("", f"arena_mission_{self.mission.id}")
        if image_path and image_path.exists():
            return [discord.File(image_path, filename="arena.webp")]
        return []

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def _build_layout(self):
        if self.battle_in_progress:
            container = ui.Container(accent_colour=discord.Color.orange())
            container.add_item(
                ui.TextDisplay(
                    f"# ⚔️ Battle in Progress!\n"
                    f"**Mission:** {self.mission.name}\n"
                    f"**Chapter:** {self.mission.chapter}\n"
                    f"**Player:** {self.ctx.author.mention}\n\n"
                    f"🎬 Simulating and rendering battle...\n\n"
                    f"{get_random_tip()}"
                )
            )
            self.add_item(container)
            return

        player = self.cog.db.get_player(self.ctx.author.id)

        # Calculate total team weight from selected bots
        total_team_weight = 0
        for bot_id in self.selected_bots:
            chassis = player.get_chassis_by_id(bot_id)
            if chassis:
                bot = chassis.to_bot(self.cog.registry)
                if bot:
                    total_team_weight += bot.total_weight

        weight_limit = self.mission.weight_limit
        is_overweight = weight_limit > 0 and total_team_weight > weight_limit
        can_afford = player.credits >= self.mission.entry_fee

        container = ui.Container(accent_colour=discord.Color.red() if is_overweight else discord.Color.orange())

        # Mission title with arena image thumbnail
        image_path = find_image_path("", f"arena_mission_{self.mission.id}")
        if image_path and image_path.exists():
            ext = image_path.suffix
            thumbnail = ui.Thumbnail(media=f"attachment://arena{ext}")
            title_section = ui.Section(
                ui.TextDisplay(f"# 📋 Mission: {self.mission.name}"),
                ui.TextDisplay(
                    f"{self.mission.briefing or self.mission.description}\n-# Player: {self.ctx.author.mention}"
                ),
                accessory=thumbnail,
            )
            container.add_item(title_section)
        else:
            container.add_item(
                ui.TextDisplay(
                    f"# 📋 Mission: {self.mission.name}\n{self.mission.briefing or self.mission.description}\n-# Player: {self.ctx.author.mention}"
                )
            )

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Mission Info Section - Weight, Entry Fee, Credits, Reward
        weight_display = f"{total_team_weight}/{weight_limit}" if weight_limit > 0 else "No limit"
        weight_status = "✅" if not is_overweight else "❌"
        fee_status = "✅" if can_afford else "❌"

        mission_info = (
            f"⚖️ **Weight Limit:** {weight_limit}\n"
            f"🤖 **Your Team's Weight:** {weight_status} {weight_display}\n"
            f"💰 **Entry Fee:** {humanize_number(self.mission.entry_fee)} credits\n"
            f"💳 **Your Credits:** {fee_status} {humanize_number(player.credits)}\n"
            f"🏆 **Reward:** {humanize_number(self.mission.credit_reward)} credits"
        )
        if self.mission.unlock_parts:
            mission_info += f"\n🔓 **Unlocks:** {', '.join(self.mission.unlock_parts)}"

        container.add_item(ui.TextDisplay(mission_info))

        # Weight exceeded warning
        if is_overweight:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
            overweight_warning = (
                f"⚠️ **Your team is too heavy!**\n"
                f"Your robots weigh **{total_team_weight}** but the limit is **{weight_limit}**.\n\n"
                f"💡 *Hint: Deselect some of your heavier bots from the dropdown below.*"
            )
            container.add_item(ui.TextDisplay(overweight_warning))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Enemy Info - hide details until mission has been attempted
        # After attempted: show plating + weapon only, never chassis type
        mission_attempted = player.has_attempted_mission(self.mission.id)
        enemy_text = ""
        for enemy in self.mission.enemies:
            if mission_attempted:
                # Show plating and weapon after first attempt (never chassis)
                bot = enemy.to_bot(self.cog.registry)
                if bot:
                    enemy_text += f"• **{enemy.name}** - 🛡️ {bot.plating.name} / ⚔️ {bot.component.name} (HP: {bot.total_shielding})\n"
                else:
                    enemy_text += f"• **{enemy.name}** - ???\n"
            else:
                # Before first attempt - only show name so player knows enemy count
                enemy_text += f"• **{enemy.name}**\n"

        enemy_header = f"**👾 Enemies ({len(self.mission.enemies)})**"
        if not mission_attempted:
            enemy_header += "\n-# *Enemy loadouts revealed after first attempt*"
        container.add_item(ui.TextDisplay(f"{enemy_header}\n{enemy_text or 'Unknown'}"))

        # Selected Squad Status
        if self.selected_bots:
            squad_lines = []

            # Build list with spawn order info for sorting
            bots_with_order = []
            for idx, bot_id in enumerate(self.selected_bots):
                chassis = player.get_chassis_by_id(bot_id)
                if chassis:
                    order = chassis.spawn_order if chassis.spawn_order > 0 else 999
                    bots_with_order.append((order, idx, chassis))

            # Sort by spawn_order, then by selection order
            bots_with_order.sort(key=lambda x: (x[0], x[1]))

            # Position labels based on sorted count
            position_labels = (
                ["Left", "Middle", "Right"]
                if len(bots_with_order) == 3
                else ["Left", "Right"]
                if len(bots_with_order) == 2
                else ["Center"]
            )

            for pos_idx, (_, _, chassis) in enumerate(bots_with_order):
                bot = chassis.to_bot(self.cog.registry)
                pos_label = position_labels[pos_idx] if pos_idx < len(position_labels) else f"Pos {pos_idx + 1}"
                if bot:
                    # Full loadout: Position, Name, HP, Weight bar, Plating, Weapon with stats
                    weight_display = chassis.get_weight_display(self.cog.registry)
                    squad_lines.append(
                        f"**[{pos_label}]** **{chassis.display_name}** ❤️{bot.total_shielding} | ⚡{bot.chassis.speed}\n"
                        f"-# ⚖️ {weight_display}\n"
                        f"-# 🛡️ {bot.plating.name} (+{bot.plating.shielding}) | "
                        f"⚔️ {bot.component.name} ({bot.component.damage_per_shot}dmg)"
                    )
                else:
                    squad_lines.append(f"**[{pos_label}]** {chassis.display_name}")

            squad_text = "\n".join(squad_lines)

            enemy_count = len(self.mission.enemies)
            player_count = len(self.selected_bots)
            if player_count < enemy_count:
                squad_text += f"\n⚠️ **Warning:** You're outnumbered {enemy_count} vs {player_count}!"

            container.add_item(ui.TextDisplay(f"**✅ Your Squad**\n{squad_text}"))
        else:
            container.add_item(
                ui.TextDisplay(
                    "**⚠️ Select Your Bot(s)**\nUse the dropdown below to choose which bot(s) to bring to battle!"
                )
            )

        container.add_item(ui.TextDisplay(f"-# Difficulty: {self.mission.difficulty.value}"))

        self.add_item(container)
        self.add_item(SelectBotRow(player, self.selected_bots, self.cog.registry))

        # Determine if start button should be disabled
        can_start = True
        start_disabled_reason = ""
        if not self.selected_bots:
            can_start = False
            start_disabled_reason = "❌ Select at least one bot!"
        elif is_overweight:
            can_start = False
            start_disabled_reason = (
                f"❌ **Team exceeds weight limit!**\n\n"
                f"Your team weighs **{total_team_weight}** but the limit is **{weight_limit}**.\n\n"
                f"💡 Deselect some of your heavier bots from the dropdown."
            )
        elif not can_afford:
            can_start = False
            start_disabled_reason = (
                f"❌ **Not enough credits!**\n\n"
                f"Entry fee: **{humanize_number(self.mission.entry_fee)}** credits\n"
                f"Your credits: **{humanize_number(player.credits)}**"
            )

        self.add_item(MissionActionRow(can_start=can_start, start_disabled_reason=start_disabled_reason))

    async def run_battle(self, interaction: discord.Interaction):
        if not self.selected_bots:
            await interaction.response.send_message("❌ Select at least one bot!", ephemeral=True)
            return

        player = self.cog.db.get_player(self.ctx.author.id)

        if self.mission.entry_fee > 0:
            if player.credits < self.mission.entry_fee:
                await interaction.response.send_message("❌ Not enough credits!", ephemeral=True)
                return

        my_bots = []
        my_bots_with_order = []  # (spawn_order, index, bot) tuples for sorting
        for idx, bot_id in enumerate(self.selected_bots):
            chassis = player.get_chassis_by_id(bot_id)
            if chassis:
                bot = chassis.to_bot(self.cog.registry)
                if bot:
                    # Store (spawn_order, purchase_order, bot) for sorting
                    # spawn_order: user-defined (1-7, 0=default)
                    # Use 999 for default (0) so they sort last
                    order = chassis.spawn_order if chassis.spawn_order > 0 else 999
                    my_bots_with_order.append((order, idx, bot))

        # Sort by spawn_order, then by original purchase/selection order
        my_bots_with_order.sort(key=lambda x: (x[0], x[1]))
        my_bots = [bot for _, _, bot in my_bots_with_order]

        if not my_bots:
            await interaction.response.send_message("❌ Could not load bots!", ephemeral=True)
            return

        # Weight check
        if self.mission.weight_limit > 0:
            total_weight = sum(bot.total_weight for bot in my_bots)
            if total_weight > self.mission.weight_limit:
                # Build helpful error message showing which bots to disable
                overweight_by = total_weight - self.mission.weight_limit
                bot_weights = []
                for bot in my_bots:
                    bot_weights.append(f"• **{bot.name}**: {bot.total_weight} wt")
                weight_details = "\n".join(bot_weights)
                await interaction.response.send_message(
                    f"❌ **Team exceeds weight limit!**\n\n"
                    f"⚖️ Total: **{total_weight}** / {self.mission.weight_limit} (over by {overweight_by})\n\n"
                    f"**Your selected bots:**\n{weight_details}\n\n"
                    f"💡 **Tip:** Deselect some of the heavier bots from the dropdown.",
                    ephemeral=True,
                )
                return

        enemy_bots = []
        for npc in self.mission.enemies:
            bot = npc.to_bot(self.cog.registry)
            if bot:
                enemy_bots.append(bot)

        if not enemy_bots:
            await interaction.response.send_message("❌ Could not load enemy bots!", ephemeral=True)
            return

        # Deduct fee
        entry_fee_paid = 0
        if self.mission.entry_fee > 0:
            entry_fee_paid = self.mission.entry_fee
            player.credits -= entry_fee_paid

        # Mark mission as attempted (reveals enemy info for future attempts)
        player.attempt_mission(self.mission.id)
        self.cog.save()

        # Update view to loading state
        self.battle_in_progress = True
        await self.refresh(interaction)

        # Run battle with player's team color and mission-specific arena
        video_path, result = await self.cog.run_battle_subprocess(
            team1=my_bots,
            team2=enemy_bots,
            output_format="mp4",
            team1_color=player.team_color,
            chapter=self.mission.chapter,
            mission_id=self.mission.id,
        )

        if not result or not video_path:
            # Revert state or show error
            self.battle_in_progress = False
            self.clear_items()
            self._build_layout()
            # Interaction already responded, use message.edit instead
            if self.message:
                await self.message.edit(view=self)
            await interaction.followup.send("❌ Battle Error: An error occurred.", ephemeral=True)
            return

        # Process result (same logic as before)
        winner_team = result.get("winner_team", 0)
        player_won = winner_team == 1
        is_stalemate = winner_team == 0

        # Track newly unlocked parts for separate notification
        newly_unlocked_parts = []
        is_first_completion = False  # Track if this is the first time completing this mission

        if player_won:
            is_first_completion = not player.has_completed_mission(self.mission.id)

            # Always award credits for winning
            player.credits += entry_fee_paid + self.mission.credit_reward

            # Always increment campaign_wins for leaderboard progression
            player.campaign_wins += 1

            if is_first_completion:
                # First completion - unlock mission and parts
                player.complete_mission(self.mission.id)
                for part_name in self.mission.unlock_parts:
                    player.unlock_part(part_name)
                    newly_unlocked_parts.append(part_name)
        elif is_stalemate:
            player.credits += entry_fee_paid
        else:
            player.campaign_losses += 1

        for bot_id, stats in result.get("bot_stats", {}).items():
            if bot_id in self.selected_bots:
                player.total_damage_dealt += stats.get("damage_dealt", 0)
                player.total_damage_taken += stats.get("damage_taken", 0)
                if not stats.get("survived", False):
                    player.bots_lost += 1
            else:
                if not stats.get("survived", False):
                    player.bots_destroyed += 1

        # Save immediately to persist mission completion
        self.cog.save(force=True)

        # Log telemetry for campaign battles
        # Calculate HP stats for player bots
        player_hp_remaining = 0
        player_max_hp = 0
        player_bots_survived = 0
        player_total_damage = 0
        player_taken_damage = 0
        enemy_bots_survived = 0

        for bot_id, stats in result.get("bot_stats", {}).items():
            if bot_id in self.selected_bots:
                # Player bot
                player_max_hp += stats.get("max_health", 0)
                if stats.get("survived", False):
                    player_bots_survived += 1
                    player_hp_remaining += stats.get("final_health", 0)
                player_total_damage += stats.get("damage_dealt", 0)
                player_taken_damage += stats.get("damage_taken", 0)
            else:
                # Enemy bot
                if stats.get("survived", False):
                    enemy_bots_survived += 1

        # Determine result string
        if player_won:
            result_str = "win"
        elif is_stalemate:
            result_str = "stalemate"
        else:
            result_str = "loss"

        self.cog.telemetry.log_campaign_battle(
            mission_id=self.mission.id,
            mission_name=self.mission.name,
            chapter_id=self.mission.chapter,
            player_id=self.ctx.author.id,
            result=result_str,
            duration=result.get("duration", 0),
            player_bots_count=len(my_bots),
            player_bots_survived=player_bots_survived,
            player_total_hp_remaining=player_hp_remaining,
            player_max_hp=player_max_hp,
            enemy_bots_count=len(enemy_bots),
            enemy_bots_survived=enemy_bots_survived,
            total_damage_dealt=player_total_damage,
            total_damage_taken=player_taken_damage,
            attempt_number=player.get_mission_attempts(self.mission.id),
            is_first_win=is_first_completion,
        )

        # Build final result using LayoutView with embedded video
        duration = result.get("duration", 0)
        battle_stats = format_battle_stats(result, winner_team)

        extra_fields = []
        if player_won:
            reward_text = f"💰 **+{self.mission.credit_reward}** credits"
            if is_first_completion:
                title = "🏆 Victory!"
                description = self.mission.victory_text or f"You completed **{self.mission.name}**!"
                color = discord.Color.green()
                extra_fields.append(("🎁 Rewards", reward_text))
            else:
                title = "✅ Victory! (Replay)"
                description = f"You replayed **{self.mission.name}**!"
                color = discord.Color.blue()
                extra_fields.append(("💰 Earned", reward_text))
        elif is_stalemate:
            title = "⚖️ Stalemate"
            description = "Time ran out!"
            color = discord.Color.gold()
            if entry_fee_paid > 0:
                extra_fields.append(("💰 Refunded", f"**+{entry_fee_paid}** credits"))
        else:
            title = "💀 Defeat"
            description = self.mission.defeat_text or "Defeat!"
            color = discord.Color.red()
            if entry_fee_paid > 0:
                extra_fields.append(("💸 Lost", f"**-{entry_fee_paid}** credits"))

        try:
            ext = video_path.suffix.lstrip(".")
            filename = f"battle.{ext}"
            file = discord.File(video_path, filename=filename)

            # Get chapter name for display
            chapter = get_chapter_for_mission(self.mission.id)
            chapter_name = f"Chapter {chapter.id}: {chapter.name}" if chapter else None

            result_view, files = create_battle_result_view(
                title=title,
                description=description,
                color=color,
                duration=duration,
                battle_stats=battle_stats,
                extra_fields=extra_fields,
                video_file=file,
                ctx=self.ctx,
                cog=self.cog,
                user=self.ctx.author,
                mission_name=self.mission.name,
                chapter_name=chapter_name,
            )
            result_view.message = self.message
            await self.message.edit(view=result_view, embed=None, attachments=files)
        except Exception as e:
            # Video attachment failed - still show result but without video
            # This is an acceptable degradation since the battle already happened
            log.exception("Failed to attach battle video to result message", exc_info=e)

            # Get chapter name for display
            chapter = get_chapter_for_mission(self.mission.id)
            chapter_name = f"Chapter {chapter.id}: {chapter.name}" if chapter else None

            result_view, _ = create_battle_result_view(
                title=title,
                description=description,
                color=color,
                duration=duration,
                battle_stats=battle_stats,
                extra_fields=extra_fields,
                ctx=self.ctx,
                cog=self.cog,
                user=self.ctx.author,
                mission_name=self.mission.name,
                chapter_name=chapter_name,
            )
            result_view.message = self.message
            await self.message.edit(view=result_view, embed=None)
        finally:
            # Clean up temp video file
            video_path.unlink(missing_ok=True)

        # Send separate ephemeral messages for each newly unlocked part
        if newly_unlocked_parts:
            await self._send_unlock_notifications(interaction, newly_unlocked_parts)

        self.stop()

    async def _send_unlock_notifications(self, interaction: discord.Interaction, part_names: list[str]):
        """Send ephemeral messages for each unlocked part with images"""
        for part_name in part_names:
            # Try to find the part in the registry
            part = None
            part_type = None
            image_folder = None

            # Check chassis
            chassis = self.cog.registry.get_chassis(part_name)
            if chassis:
                part = chassis
                part_type = "Chassis"
                image_folder = "chassis"

            # Check plating
            if not part:
                plating = self.cog.registry.get_plating(part_name)
                if plating:
                    part = plating
                    part_type = "Plating"
                    image_folder = "plating"

            # Check components (weapons)
            if not part:
                component = self.cog.registry.get_component(part_name)
                if component:
                    part = component
                    part_type = "Weapon"
                    image_folder = "weapons"

            if not part or not image_folder:
                # Part not found in registry - this is a bug in campaign data!
                raise ValueError(f"Part '{part_name}' not found in registry! Check campaign unlock_parts data.")

            # Build embed with part info
            embed = discord.Embed(
                title=f"🔓 Unlocked: {part.name}", description=part.description, color=discord.Color.gold()
            )
            embed.add_field(name="Type", value=part_type, inline=True)

            # Add type-specific stats
            if isinstance(part, Chassis):
                embed.add_field(name="Shielding", value=f"{part.shielding}", inline=True)
                embed.add_field(name="Weight", value=f"{part.self_weight}wt", inline=True)
                embed.add_field(name="Capacity", value=f"{part.weight_capacity}wt", inline=True)
            elif isinstance(part, Plating):
                embed.add_field(name="Shielding", value=f"{part.shielding}", inline=True)
                embed.add_field(name="Weight", value=f"{part.weight}wt", inline=True)
            elif isinstance(part, Component):
                embed.add_field(name="Damage", value=f"{part.damage_per_shot}", inline=True)
                embed.add_field(name="Weight", value=f"{part.weight}wt", inline=True)

            # Find image file using the same helper as shop
            image_path = _get_part_image_path(image_folder, part.name)

            if image_path and image_path.exists():
                ext = image_path.suffix.lstrip(".")
                safe_filename = part.name.lower().replace(" ", "_") + f".{ext}"
                file = discord.File(image_path, filename=safe_filename)
                embed.set_image(url=f"attachment://{safe_filename}")
                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            else:
                # Send without image if file not found
                await interaction.followup.send(embed=embed, ephemeral=True)


class ProfileColorSelectRow(ui.ActionRow["ProfileLayout"]):
    """Dropdown for selecting team color"""

    def __init__(self, current_color: str):
        super().__init__()
        # Fallback to blue if user has invalid color (e.g., removed cyan/pink)
        if current_color not in TEAM_COLORS:
            current_color = "blue"
        options = []
        for color_name in TEAM_COLORS.keys():
            emoji = TEAM_COLOR_EMOJIS.get(color_name, "")
            options.append(
                discord.SelectOption(
                    label=color_name.title(),
                    value=color_name,
                    emoji=emoji,
                    default=color_name == current_color,
                )
            )
        self.color_select.options = options

    @ui.select(placeholder="Select Team Color...")
    async def color_select(self, interaction: discord.Interaction, select: ui.Select):
        player = self.view.cog.db.get_player(interaction.user.id)
        player.team_color = select.values[0]
        self.view.cog.save()
        await self.view.refresh(interaction)


class ProfileNavigationRow(ui.ActionRow["ProfileLayout"]):
    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.view.parent:
            await self.view.navigate_back(interaction)
        else:
            view = GameHubLayout(self.view.ctx, self.view.cog)
            view.message = self.view.message
            await interaction.response.edit_message(view=view)
            self.view.stop()


class ProfileLayout(BotArenaView):
    """Detailed player profile - can view own or another player's profile"""

    def __init__(
        self,
        ctx: commands.Context,
        cog: "BotArena",
        parent: t.Optional[ui.LayoutView] = None,
        target_user: t.Optional[t.Union[discord.Member, discord.User]] = None,
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        # Target user defaults to command author
        self.target_user = target_user or ctx.author
        # Can only edit profile if viewing your own
        self.is_own_profile = self.target_user.id == ctx.author.id
        self._build_layout()

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def _build_layout(self):
        player = self.cog.db.get_player(self.target_user.id)
        completed, total = player.campaign_progress

        container = ui.Container(accent_colour=discord.Color.blue())
        container.add_item(ui.TextDisplay(f"# 📊 {self.target_user.display_name}'s Profile"))

        # Resources & Campaign
        inventory_count = sum(part.quantity for part in player.equipment_inventory)
        col1_text = (
            f"**💰 Resources**\n"
            f"Credits: {humanize_number(player.credits)}\n"
            f"Items: {inventory_count}\n"
            f"Bots: {len(player.owned_chassis)}\n\n"
            f"**📖 Campaign**\n"
            f"Progress: {completed}/{total}\n"
            f"Wins: {player.campaign_wins}\n"
            f"Losses: {player.campaign_losses}"
        )
        container.add_item(ui.TextDisplay(col1_text))

        # PvP & Combat
        col2_text = (
            f"**👊 PvP**\n"
            f"Wins: {player.pvp_wins}\n"
            f"Losses: {player.pvp_losses}\n"
            f"Draws: {player.pvp_draws}\n\n"
            f"**⚔️ Combat Stats**\n"
            f"Dmg Dealt: {humanize_number(player.total_damage_dealt)}\n"
            f"Dmg Taken: {humanize_number(player.total_damage_taken)}\n"
            f"Kills: {player.bots_destroyed}\n"
            f"Deaths: {player.bots_lost}"
        )
        container.add_item(ui.TextDisplay(col2_text))

        # Owned Bots Section
        if player.owned_chassis:
            bot_lines = []
            for chassis in player.owned_chassis[:5]:
                status = "✅" if chassis.is_battle_ready else "🛠️"
                bot_lines.append(f"{status} **{chassis.display_name}**")
            if len(player.owned_chassis) > 5:
                bot_lines.append(f"-# *+{len(player.owned_chassis) - 5} more bots*")
            bots_text = f"**🤖 Bots ({len(player.owned_chassis)})**\n" + "\n".join(bot_lines)
        else:
            bots_text = "**🤖 Bots**\n*No bots yet*"
        container.add_item(ui.TextDisplay(bots_text))

        # Team Color Section (only show editor for own profile)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        color_emoji = TEAM_COLOR_EMOJIS.get(player.team_color, "🔵")
        if self.is_own_profile:
            color_text = (
                f"**🎨 Team Color:** {color_emoji} {player.team_color.title()}\n"
                f"-# Your bots will use this color in battles"
            )
        else:
            color_text = f"**🎨 Team Color:** {color_emoji} {player.team_color.title()}"
        container.add_item(ui.TextDisplay(color_text))

        self.add_item(container)

        # Only show color selector and back button for own profile from hub
        if self.is_own_profile:
            self.add_item(ProfileColorSelectRow(player.team_color))
            if self.parent:
                self.add_item(ProfileNavigationRow())


class PvPUserSelectRow(ui.ActionRow["PvPLayout"]):
    @ui.select(cls=discord.ui.UserSelect, placeholder="Select opponent to challenge...", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        user = select.values[0]
        if user.id == self.view.ctx.author.id:
            await interaction.response.send_message("❌ You can't challenge yourself!", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("❌ You can't challenge a bot user!", ephemeral=True)
            return

        # Check opponent has battle-ready bots
        opponent_player = self.view.cog.db.get_player(user.id)
        opponent_bots = opponent_player.get_battle_ready_bots()
        if not opponent_bots:
            await interaction.response.send_message(
                f"❌ **{user.display_name}** doesn't have any battle-ready bots!", ephemeral=True
            )
            return

        self.view.selected_opponent = user
        await self.view.refresh(interaction)


class PvPActionsRow(ui.ActionRow["PvPLayout"]):
    @ui.button(label="Challenge!", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def challenge_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.start_challenge(interaction)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.view.parent:
            await self.view.navigate_back(interaction)
        else:
            view = GameHubLayout(self.view.ctx, self.view.cog)
            view.message = self.view.message
            await interaction.response.edit_message(view=view)
            self.view.stop()


class PvPLayout(BotArenaView):
    """PvP challenge interface - select an opponent and launch a challenge"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self.selected_opponent: t.Optional[t.Union[discord.Member, discord.User]] = None

        self._build_layout()

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def _build_layout(self):
        player = self.cog.db.get_player(self.ctx.author.id)

        container = ui.Container(accent_colour=discord.Color.red())
        container.add_item(
            ui.TextDisplay(
                f"# 👊 PvP Arena\n*Challenge other players to bot battles!*\n-# Player: {self.ctx.author.mention}"
            )
        )

        # Stats
        total_pvp = player.pvp_wins + player.pvp_losses + player.pvp_draws
        win_rate = player.pvp_wins / total_pvp if total_pvp > 0 else 0

        container.add_item(
            ui.TextDisplay(
                f"**🏆 Your Record** | Wins: {player.pvp_wins} | Losses: {player.pvp_losses} | "
                f"Draws: {player.pvp_draws} | Win Rate: {win_rate:.1%}"
            )
        )

        # How it works
        container.add_item(ui.Separator())
        container.add_item(
            ui.TextDisplay(
                "**⚔️ How it works:**\n"
                "1. Select an opponent below\n"
                "2. Both players select up to **3 bots** for battle\n"
                "3. Set optional credit bets\n"
                "4. Both click **Ready Up** to start!\n\n"
                "*Any changes un-ready both players to prevent cheating.*"
            )
        )

        # Selection status
        if self.selected_opponent:
            container.add_item(ui.Separator())
            container.add_item(
                ui.TextDisplay(f"**📋 Selected:** {self.selected_opponent.display_name} ✅\nClick **Challenge!** below")
            )
        else:
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay("**📋 Selected:** *Select an opponent below...*"))

        self.add_item(container)
        self.add_item(PvPUserSelectRow())
        self.add_item(PvPActionsRow())

    async def start_challenge(self, interaction: discord.Interaction):
        if not self.selected_opponent:
            await interaction.response.send_message("❌ Select an opponent first!", ephemeral=True)
            return

        if not isinstance(self.selected_opponent, discord.Member):
            await interaction.response.send_message("❌ Could not resolve opponent!", ephemeral=True)
            return

        # Launch the new ChallengeLayout
        from .challenge import ChallengeLayout

        view = ChallengeLayout(
            ctx=self.ctx,
            cog=self.cog,
            challenger=self.ctx.author,
            opponent=self.selected_opponent,
            parent=self,
        )
        view.message = self.message
        self.navigate_to_child(view)
        await interaction.response.edit_message(view=view)
