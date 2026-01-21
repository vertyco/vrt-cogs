"""
Bot Arena - Leaderboard View

Dynamic leaderboard menu with mode selection and pagination.
"""

import math
import typing as t
from contextlib import suppress
from enum import Enum

import discord
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

if t.TYPE_CHECKING:
    from ..common.models import PlayerData
    from ..main import BotArena


class LeaderboardMode(Enum):
    """Available leaderboard categories"""

    WINS = "wins"
    PVP = "pvp"
    CAMPAIGN = "campaign"
    DAMAGE = "damage"
    CREDITS = "credits"
    BOTS = "bots"


LEADERBOARD_INFO: dict[LeaderboardMode, dict[str, t.Any]] = {
    LeaderboardMode.WINS: {
        "title": "🏆 Total Wins Leaderboard",
        "emoji": "🏆",
        "key": lambda p: p.wins,
        "format": lambda p: f"🏆 **{p.wins}** wins ({p.campaign_wins} campaign, {p.pvp_wins} PvP)",
        "description": "Players ranked by total wins (campaign + PvP)",
    },
    LeaderboardMode.PVP: {
        "title": "👊 PvP Wins Leaderboard",
        "emoji": "👊",
        "key": lambda p: p.pvp_wins,
        "format": lambda p: f"👊 **{p.pvp_wins}** PvP wins (W/L: {p.pvp_wins}/{p.pvp_losses})",
        "description": "Players ranked by PvP victories",
    },
    LeaderboardMode.CAMPAIGN: {
        "title": "📖 Campaign Wins Leaderboard",
        "emoji": "📖",
        "key": lambda p: p.campaign_wins,
        "format": lambda p: f"📖 **{p.campaign_wins}** campaign wins ({len(p.completed_missions)} missions done)",
        "description": "Players ranked by campaign victories",
    },
    LeaderboardMode.DAMAGE: {
        "title": "💥 Damage Dealt Leaderboard",
        "emoji": "💥",
        "key": lambda p: p.total_damage_dealt,
        "format": lambda p: f"💥 **{humanize_number(p.total_damage_dealt)}** damage dealt",
        "description": "Players ranked by total damage dealt",
    },
    LeaderboardMode.CREDITS: {
        "title": "💰 Credits Leaderboard",
        "emoji": "💰",
        "key": lambda p: p.credits,
        "format": lambda p: f"💰 **{humanize_number(p.credits)}** credits",
        "description": "Players ranked by current credit balance",
    },
    LeaderboardMode.BOTS: {
        "title": "🤖 Bots Destroyed Leaderboard",
        "emoji": "🤖",
        "key": lambda p: p.bots_destroyed,
        "format": lambda p: f"🤖 **{p.bots_destroyed}** bots destroyed",
        "description": "Players ranked by enemy bots destroyed",
    },
}


class ModeDropdown(ui.ActionRow["LeaderboardView"]):
    """Dropdown for selecting leaderboard mode"""

    options = [
        discord.SelectOption(label="Total Wins", value="wins", emoji="🏆", description="Campaign + PvP wins"),
        discord.SelectOption(label="PvP Wins", value="pvp", emoji="👊", description="Player vs Player victories"),
        discord.SelectOption(label="Campaign Wins", value="campaign", emoji="📖", description="Story mode victories"),
        discord.SelectOption(label="Damage Dealt", value="damage", emoji="💥", description="Total damage dealt"),
        discord.SelectOption(label="Credits", value="credits", emoji="💰", description="Current credit balance"),
        discord.SelectOption(label="Bots Destroyed", value="bots", emoji="🤖", description="Enemy bots destroyed"),
    ]

    def __init__(self, view: "LeaderboardView"):
        self._lb_view = view
        super().__init__()
        self._update_options()

    def _update_options(self):
        for option in self.options:
            option.default = self._lb_view.mode.value == option.value

    @ui.select(placeholder="Select Leaderboard", options=options)
    async def select_mode(self, interaction: discord.Interaction, select: ui.Select) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self._lb_view.mode = LeaderboardMode(select.values[0])
        self._lb_view.page = 0  # Reset to first page
        self._lb_view.update_containers()
        await self._lb_view.refresh(interaction, followup=True)


class PaginationRow(ui.ActionRow["LeaderboardView"]):
    """Pagination buttons for navigating leaderboard pages"""

    def __init__(self, view: "LeaderboardView"):
        self._lb_view = view
        super().__init__()
        # Hide pagination buttons if only one page
        if self._lb_view.page_count <= 1:
            self.remove_item(self.left_btn)
            self.remove_item(self.right_btn)

    @ui.button(emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def left_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self._lb_view.page = (self._lb_view.page - 1) % self._lb_view.page_count
        await self._lb_view.refresh(interaction)

    @ui.button(emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self._lb_view.message:
            with suppress(discord.NotFound):
                await self._lb_view.message.delete()
        self._lb_view.stop()

    @ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def right_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self._lb_view.page = (self._lb_view.page + 1) % self._lb_view.page_count
        await self._lb_view.refresh(interaction)


class LeaderboardView(ui.LayoutView):
    """Dynamic leaderboard view with mode selection and pagination"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", mode: LeaderboardMode = LeaderboardMode.WINS):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.cog = cog
        self.author = ctx.author
        self.guild = ctx.guild
        self.channel = ctx.channel

        self.mode = mode
        self.page = 0
        self.page_count = 1
        self.pages: list[ui.Container] = []
        self.message: discord.Message | None = None

        # Leaderboard data: list of (stat_value, PlayerData, Member|None)
        self.data: list[tuple[int, "PlayerData", discord.Member | None]] = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your leaderboard!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message and self.pages:
            # Disable components in current page
            page = self.pages[self.page]
            for item in page.children:
                if hasattr(item, "disabled"):
                    setattr(item, "disabled", True)
                elif isinstance(item, ui.ActionRow):
                    for child in item.children:
                        if hasattr(child, "disabled"):
                            setattr(child, "disabled", True)
            await self.refresh()
        self.stop()

    def _gather_leaderboard_data(self):
        """Gather and sort leaderboard entries for the current mode"""
        info = LEADERBOARD_INFO[self.mode]
        entries: list[tuple[int, "PlayerData", discord.Member | None]] = []

        for user_id, player in self.cog.db.players.items():
            # Skip players who haven't started playing
            if not player.has_seen_tutorial:
                continue
            # Get the stat value
            stat_value = info["key"](player)
            # Skip players with 0 in the stat (except credits)
            if stat_value == 0 and self.mode != LeaderboardMode.CREDITS:
                continue
            # Try to get the member object
            member = self.guild.get_member(user_id) if self.guild else None
            entries.append((stat_value, player, member))

        # Sort by stat value (descending)
        entries.sort(key=lambda x: x[0], reverse=True)
        self.data = entries

    def update_containers(self):
        """Rebuild the pages list based on current data and mode"""
        self._gather_leaderboard_data()

        info = LEADERBOARD_INFO[self.mode]
        color = discord.Color.gold()

        # Find requester's position
        requester_position: int | None = None
        for i, (_, _, member) in enumerate(self.data):
            if member and member.id == self.author.id:
                requester_position = i
                break

        # Header
        header = ui.TextDisplay(f"# {info['title']}\n-# {info['description']}")

        # Handle empty leaderboard
        if not self.data:
            container = ui.Container(accent_colour=color)
            container.add_item(header)
            container.add_item(ui.TextDisplay("\n📊 No players found for this leaderboard yet!"))
            container.add_item(ModeDropdown(self))
            container.add_item(PaginationRow(self))
            self.page_count = 1
            self.pages = [container]
            return

        # Build pages
        pages: list[ui.Container] = []
        per_page = 10
        max_pages = math.ceil(len(self.data) / per_page)
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}

        for page_num in range(max_pages):
            start = page_num * per_page
            end = min(start + per_page, len(self.data))

            lines: list[str] = []
            for i in range(start, end):
                stat_value, player, member = self.data[i]
                rank = i + 1
                medal = medals.get(i, f"**{rank}.**")
                name = member.display_name if member else "Unknown User"
                stat_display = info["format"](player)
                is_requester = member and member.id == self.author.id
                highlight = " ⬅️" if is_requester else ""
                lines.append(f"{medal} **{name}**{highlight}\n-# {stat_display}")

            container = ui.Container(accent_colour=color)
            container.add_item(header)
            container.add_item(ui.TextDisplay("\n" + "\n".join(lines)))
            container.add_item(ModeDropdown(self))
            container.add_item(PaginationRow(self))

            # Footer with page info and requester rank
            footer_parts = [f"Page {page_num + 1}/{max_pages}"]
            if requester_position is not None:
                footer_parts.append(f"Your Rank: #{requester_position + 1}")
            elif self.author.id in self.cog.db.players:
                # Requester not in filtered list, find their actual rank
                player = self.cog.db.get_player(self.author.id)
                if player.has_seen_tutorial:
                    # Count how many are above them
                    user_stat = info["key"](player)
                    rank = sum(1 for v, _, _ in self.data if v > user_stat) + 1
                    footer_parts.append(f"Your Rank: #{rank}")

            container.add_item(ui.TextDisplay(f"-# {' | '.join(footer_parts)}"))
            pages.append(container)

        self.page_count = max_pages
        self.pages = pages

    async def refresh(self, interaction: discord.Interaction | None = None, followup: bool = False):
        """Refresh the view with current page"""
        self.page %= max(len(self.pages), 1)
        self.clear_items()
        if self.pages:
            self.add_item(self.pages[self.page])

        if interaction and followup:
            await interaction.edit_original_response(view=self)
        elif interaction:
            await interaction.response.edit_message(view=self)
        elif self.message:
            await self.message.edit(view=self)
        else:
            self.message = await self.channel.send(view=self)

    async def start(self):
        """Entry point - initialize and send the view"""
        self.update_containers()
        await self.refresh()
