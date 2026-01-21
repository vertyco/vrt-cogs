"""
Bot Arena - User Commands

The main entry points for players to access Bot Arena.
"""

import typing as t

import discord
from discord import ui
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import PlayerData
from ..views.hub import GameHubLayout, ProfileLayout, TutorialLayout
from ..views.leaderboard import LeaderboardMode, LeaderboardView


class ResetConfirmLayout(ui.LayoutView):
    """Confirmation view for account reset"""

    def __init__(self, ctx: commands.Context, cog):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.cog = cog
        self.message: t.Optional[discord.Message] = None
        self._build_layout()

    def _build_layout(self):
        container = ui.Container(accent_colour=discord.Color.red())
        container.add_item(
            ui.TextDisplay(
                "# ⚠️ Reset Account?\n\n"
                "This will **permanently delete** all your Bot Arena progress:\n"
                "- All credits\n"
                "- All bots and parts\n"
                "- All campaign progress\n"
                "- All battle statistics\n\n"
                "You will start fresh with **8,200 credits** and the tutorial.\n\n"
                "**This cannot be undone!**"
            )
        )
        self.add_item(container)
        self.add_item(ResetConfirmButtonsRow())

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your reset confirmation!", ephemeral=True)
            return False
        return True


class ResetConfirmButtonsRow(ui.ActionRow["ResetConfirmLayout"]):
    """Buttons for reset confirmation"""

    @ui.button(label="Yes, Reset My Account", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        # Reset the player data to a fresh PlayerData instance
        self.view.cog.db.players[interaction.user.id] = PlayerData()
        self.view.cog.save()

        # Show success message
        self.view.clear_items()
        container = ui.Container(accent_colour=discord.Color.green())
        container.add_item(
            ui.TextDisplay(
                "# ✅ Account Reset!\n\n"
                "Your Bot Arena account has been reset.\n"
                "You now have **8,200 credits** to start fresh.\n\n"
                "Use `[p]botarena` to begin the tutorial!"
            )
        )
        self.view.add_item(container)
        await interaction.response.edit_message(view=self.view)
        self.view.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.clear_items()
        container = ui.Container(accent_colour=discord.Color.blue())
        container.add_item(ui.TextDisplay("# Reset Cancelled\n\nYour account is safe!"))
        self.view.add_item(container)
        await interaction.response.edit_message(view=self.view)
        self.view.stop()


class UserCommands(MixinMeta):
    """User-facing commands for Bot Arena"""

    @commands.command(name="botarena", aliases=["ba"])
    @commands.guild_only()
    async def botarena(self, ctx: commands.Context):
        """Bot Arena - Build and battle robots!

        Opens the main game hub where you can:
        - Play through the Campaign
        - Build and customize bots
        - Challenge other players
        - Browse the shop
        """
        player = self.db.get_player(ctx.author.id)

        # New player - show tutorial
        if not player.has_seen_tutorial:
            view = TutorialLayout(ctx, self)
            view.message = await ctx.send(view=view)
            return

        # Returning player - show hub
        view = GameHubLayout(ctx, self)
        view.message = await ctx.send(view=view)

    @commands.command(name="botprofile", aliases=["bp"])
    @commands.guild_only()
    async def botprofile(self, ctx: commands.Context, member: t.Optional[discord.Member] = None):
        """View a player's Bot Arena profile and stats.

        Shows campaign progress, battle record, combat stats, and owned bots.

        **Arguments:**
        - `member`: The player to view (defaults to yourself)

        **Examples:**
        - `[p]botprofile` - View your own profile
        - `[p]botprofile @User` - View another player's profile
        """
        target = member or ctx.author
        view = ProfileLayout(ctx, self, target_user=target)
        view.message = await ctx.send(view=view)

    @commands.command(name="botarenareset", aliases=["bareset"])
    @commands.guild_only()
    async def botarena_reset(self, ctx: commands.Context):
        """Reset your Bot Arena account.

        **⚠️ WARNING:** This permanently deletes ALL your progress!
        - All credits will be lost
        - All bots and parts will be deleted
        - All campaign progress will be reset
        - All battle statistics will be cleared

        You will start fresh with 8,200 credits.

        Use this if you're stuck and can't afford to continue.
        """
        view = ResetConfirmLayout(ctx, self)
        view.message = await ctx.send(view=view)

    @commands.command(name="botleaderboard", aliases=["botlb"])
    @commands.guild_only()
    async def botleaderboard(self, ctx: commands.Context, mode: str = "wins"):
        """View the Bot Arena leaderboard.

        **Modes:**
        - `wins` - Total wins (campaign + PvP) [default]
        - `pvp` - PvP wins
        - `campaign` - Campaign wins
        - `damage` - Total damage dealt
        - `credits` - Current credit balance
        - `bots` - Enemy bots destroyed

        **Examples:**
        - `[p]botleaderboard` - Show total wins leaderboard
        - `[p]botlb pvp` - Show PvP wins leaderboard
        - `[p]botlb damage` - Show damage dealt leaderboard
        """
        # Parse mode
        mode_lower = mode.lower()
        try:
            lb_mode = LeaderboardMode(mode_lower)
        except ValueError:
            valid_modes = ", ".join(f"`{m.value}`" for m in LeaderboardMode)
            await ctx.send(f"❌ Invalid mode `{mode}`. Valid modes: {valid_modes}")
            return

        view = LeaderboardView(ctx, self, mode=lb_mode)
        await view.start()
