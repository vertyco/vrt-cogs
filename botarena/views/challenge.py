"""
Bot Arena - Battle Challenge View

Handles PvP battle challenges with multi-bot selection, betting, and ready-up system.
"""

from __future__ import annotations

import logging
import typing as t

import discord
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

if t.TYPE_CHECKING:
    from ..main import BotArena

from ..common.models import Bot, PartsRegistry, PlayerData
from .base import BotArenaView
from .hub import create_battle_result_view, format_battle_stats

log = logging.getLogger("red.vrt.botarena.challenge")

MAX_BOTS_IN_BATTLE = 3  # Max bots each player can bring


# ═══════════════════════════════════════════════════════════════════════════════
# CHALLENGE BOT SELECT ROWS
# ═══════════════════════════════════════════════════════════════════════════════


class ChallengerBotSelectRow(ui.ActionRow["ChallengeLayout"]):
    """Dropdown for the challenger to select their bots"""

    def __init__(
        self,
        player: PlayerData,
        registry: PartsRegistry,
        selected_ids: list[str],
    ):
        super().__init__()
        self._build_options(player, registry, selected_ids)

    def _build_options(self, player: PlayerData, registry: PartsRegistry, selected_ids: list[str]):
        options = []
        for chassis in player.get_battle_ready_bots():
            bot = chassis.to_bot(registry)
            if bot:
                options.append(
                    discord.SelectOption(
                        label=chassis.display_name,
                        description=f"HP: {bot.total_shielding} | {bot.component.name}",
                        value=chassis.id,
                        default=chassis.id in selected_ids,
                    )
                )

        if options:
            self.bot_select.options = options
            self.bot_select.max_values = min(len(options), MAX_BOTS_IN_BATTLE)
        else:
            self.bot_select.options = [discord.SelectOption(label="No battle-ready bots", value="none")]
            self.bot_select.disabled = True

    @ui.select(placeholder="Select your bots (max 3)...", min_values=0, max_values=3, row=0)
    async def bot_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.view.challenger.id:
            await interaction.response.send_message("Only the challenger can select their bots!", ephemeral=True)
            return

        if "none" in select.values:
            await interaction.response.defer()
            return

        # Update selection and un-ready both players
        self.view.challenger_bot_ids = select.values
        self.view._unready_both()
        await self.view.refresh(interaction)


class OpponentBotSelectRow(ui.ActionRow["ChallengeLayout"]):
    """Dropdown for the opponent to select their bots"""

    def __init__(
        self,
        player: PlayerData,
        registry: PartsRegistry,
        selected_ids: list[str],
    ):
        super().__init__()
        self._build_options(player, registry, selected_ids)

    def _build_options(self, player: PlayerData, registry: PartsRegistry, selected_ids: list[str]):
        options = []
        for chassis in player.get_battle_ready_bots():
            bot = chassis.to_bot(registry)
            if bot:
                options.append(
                    discord.SelectOption(
                        label=chassis.display_name,
                        description=f"HP: {bot.total_shielding} | {bot.component.name}",
                        value=chassis.id,
                        default=chassis.id in selected_ids,
                    )
                )

        if options:
            self.bot_select.options = options
            self.bot_select.max_values = min(len(options), MAX_BOTS_IN_BATTLE)
        else:
            self.bot_select.options = [discord.SelectOption(label="No battle-ready bots", value="none")]
            self.bot_select.disabled = True

    @ui.select(placeholder="Select your bots (max 3)...", min_values=0, max_values=3, row=1)
    async def bot_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.view.opponent.id:
            await interaction.response.send_message("Only the opponent can select their bots!", ephemeral=True)
            return

        if "none" in select.values:
            await interaction.response.defer()
            return

        # Update selection and un-ready both players
        self.view.opponent_bot_ids = select.values
        self.view._unready_both()
        await self.view.refresh(interaction)


# ═══════════════════════════════════════════════════════════════════════════════
# BET BUTTONS ROW
# ═══════════════════════════════════════════════════════════════════════════════


class BetButtonsRow(ui.ActionRow["ChallengeLayout"]):
    """Row with a single bet button for both players"""

    @ui.button(label="Set Your Bet", style=discord.ButtonStyle.primary, emoji="💰", row=2)
    async def bet_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.view.challenger.id:
            await interaction.response.send_modal(BetModal(self.view, is_challenger=True))
        elif interaction.user.id == self.view.opponent.id:
            await interaction.response.send_modal(BetModal(self.view, is_challenger=False))
        else:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)


class BetModal(ui.Modal):
    """Modal for entering bet amount"""

    def __init__(self, view: "ChallengeLayout", is_challenger: bool):
        super().__init__(title="Set Your Bet")
        self.challenge_view = view
        self.is_challenger = is_challenger

        player = view.challenger_player if is_challenger else view.opponent_player
        current_bet = view.challenger_bet if is_challenger else view.opponent_bet

        self.amount_input = ui.TextInput(
            label=f"Bet Amount (Max: {humanize_number(player.credits)})",
            placeholder="Enter amount (0 for no bet)...",
            default=str(current_bet) if current_bet > 0 else "",
            required=True,
            max_length=15,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value.replace(",", "").strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount! Enter a number.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("❌ Bet cannot be negative!", ephemeral=True)
            return

        player = self.challenge_view.challenger_player if self.is_challenger else self.challenge_view.opponent_player
        if amount > player.credits:
            await interaction.response.send_message(
                f"❌ You only have **{humanize_number(player.credits)}** credits!", ephemeral=True
            )
            return

        # Update bet and un-ready both players
        if self.is_challenger:
            self.challenge_view.challenger_bet = amount
        else:
            self.challenge_view.opponent_bet = amount

        self.challenge_view._unready_both()
        await self.challenge_view.refresh(interaction)


# ═══════════════════════════════════════════════════════════════════════════════
# READY UP & ACTIONS ROW
# ═══════════════════════════════════════════════════════════════════════════════


class ReadyUpRow(ui.ActionRow["ChallengeLayout"]):
    """Row with ready buttons and cancel/decline"""

    def __init__(self, challenger_ready: bool, opponent_ready: bool):
        super().__init__()
        # Update ready button styles based on ready state
        self.ready_btn.style = (
            discord.ButtonStyle.success if (challenger_ready or opponent_ready) else discord.ButtonStyle.secondary
        )

        ready_count = sum([challenger_ready, opponent_ready])
        if ready_count == 2:
            self.ready_btn.label = "⚔️ FIGHT!"
            self.ready_btn.style = discord.ButtonStyle.success
        elif ready_count == 1:
            self.ready_btn.label = "Ready Up (1/2)"
        else:
            self.ready_btn.label = "Ready Up (0/2)"

    @ui.button(label="Ready Up (0/2)", style=discord.ButtonStyle.secondary, emoji="✅", row=3)
    async def ready_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.toggle_ready(interaction)

    @ui.button(label="Cancel/Decline", style=discord.ButtonStyle.danger, row=3)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.cancel_challenge(interaction)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CHALLENGE LAYOUT VIEW
# ═══════════════════════════════════════════════════════════════════════════════


class ChallengeLayout(BotArenaView):
    """
    Multi-bot PvP challenge view with betting and ready-up system.

    Flow:
    1. Challenger initiates challenge by selecting opponent from dropdown
    2. Opponent accepts by interacting with the view
    3. Both players select their bots (max 3 each)
    4. Both players optionally set their bets
    5. Both players click "Ready Up"
    6. When both ready, battle starts automatically

    If either player changes their selection or bet, both players are un-readied.
    """

    def __init__(
        self,
        ctx: commands.Context,
        cog: "BotArena",
        challenger: discord.Member,
        opponent: discord.Member,
        parent: t.Optional[ui.LayoutView] = None,
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)

        self.challenger = challenger
        self.opponent = opponent

        # Player data
        self.challenger_player = cog.db.get_player(challenger.id)
        self.opponent_player = cog.db.get_player(opponent.id)

        # Bot selections (list of chassis IDs)
        self.challenger_bot_ids: list[str] = []
        self.opponent_bot_ids: list[str] = []

        # Bets
        self.challenger_bet: int = 0
        self.opponent_bet: int = 0

        # Ready state
        self.challenger_ready: bool = False
        self.opponent_ready: bool = False

        # Battle state
        self.battle_in_progress: bool = False

        self._build_layout()

    def _unready_both(self):
        """Un-ready both players (called when selections change)"""
        self.challenger_ready = False
        self.opponent_ready = False

    def _get_selected_bots(self, is_challenger: bool) -> list[Bot]:
        """Convert selected chassis IDs to Bot objects"""
        player = self.challenger_player if is_challenger else self.opponent_player
        bot_ids = self.challenger_bot_ids if is_challenger else self.opponent_bot_ids

        bots = []
        for chassis_id in bot_ids:
            chassis = player.get_chassis_by_id(chassis_id)
            if chassis:
                bot = chassis.to_bot(self.cog.registry)
                if bot:
                    bots.append(bot)
        return bots

    async def refresh(self, interaction: discord.Interaction):
        # Re-fetch player data in case credits changed
        self.challenger_player = self.cog.db.get_player(self.challenger.id)
        self.opponent_player = self.cog.db.get_player(self.opponent.id)

        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def _build_layout(self):
        if self.battle_in_progress:
            from ..constants import get_random_tip

            challenger_bots = self._get_selected_bots(is_challenger=True)
            opponent_bots = self._get_selected_bots(is_challenger=False)

            container = ui.Container(accent_colour=discord.Color.orange())
            container.add_item(
                ui.TextDisplay(
                    f"# ⚔️ Battle Starting!\n"
                    f"**{self.challenger.display_name}** ({len(challenger_bots)} bots) vs "
                    f"**{self.opponent.display_name}** ({len(opponent_bots)} bots)\n\n"
                    f"🎬 Simulating and rendering battle...\n\n"
                    f"-# 💡 *{get_random_tip()}*"
                )
            )
            self.add_item(container)
            return

        # Main container
        container = ui.Container(accent_colour=discord.Color.red())

        # Title with bet info - ping the opponent
        total_pot = self.challenger_bet + self.opponent_bet
        pot_text = f"\n**💰 Pot:** {humanize_number(total_pot)} credits" if total_pot > 0 else ""
        container.add_item(
            ui.TextDisplay(
                f"# ⚔️ PvP Challenge!{pot_text}\n**{self.challenger.display_name}** vs {self.opponent.mention}"
            )
        )

        container.add_item(ui.Separator())

        # Challenger section
        challenger_bots = self._get_selected_bots(is_challenger=True)
        challenger_text = f"**⚔️ {self.challenger.display_name}**"
        if self.challenger_ready:
            challenger_text += " ✅ READY"
        challenger_text += "\n"

        if challenger_bots:
            for bot in challenger_bots:
                challenger_text += f"• {bot.name} (HP: {bot.total_shielding}, {bot.component.name})\n"
        else:
            challenger_text += "*Select your bots below...*\n"

        if self.challenger_bet > 0:
            challenger_text += f"**Bet:** {humanize_number(self.challenger_bet)} credits"

        container.add_item(ui.TextDisplay(challenger_text))

        container.add_item(ui.Separator())

        # Opponent section
        opponent_bots = self._get_selected_bots(is_challenger=False)
        opponent_text = f"**🛡️ {self.opponent.display_name}**"
        if self.opponent_ready:
            opponent_text += " ✅ READY"
        opponent_text += "\n"

        if opponent_bots:
            for bot in opponent_bots:
                opponent_text += f"• {bot.name} (HP: {bot.total_shielding}, {bot.component.name})\n"
        else:
            opponent_text += "*Select your bots below...*\n"

        if self.opponent_bet > 0:
            opponent_text += f"**Bet:** {humanize_number(self.opponent_bet)} credits"

        container.add_item(ui.TextDisplay(opponent_text))

        # Instructions
        container.add_item(ui.Separator())
        container.add_item(
            ui.TextDisplay("-# Select your bots, set optional bets, then both players click Ready Up to start!")
        )

        self.add_item(container)

        # Bot selection rows
        self.add_item(ChallengerBotSelectRow(self.challenger_player, self.cog.registry, self.challenger_bot_ids))
        self.add_item(OpponentBotSelectRow(self.opponent_player, self.cog.registry, self.opponent_bot_ids))

        # Bet button
        self.add_item(BetButtonsRow())

        # Ready up / cancel row
        self.add_item(ReadyUpRow(self.challenger_ready, self.opponent_ready))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Allow both challenger and opponent to interact
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return False
        return True

    async def toggle_ready(self, interaction: discord.Interaction):
        """Handle ready button clicks"""
        user_id = interaction.user.id

        # Validate that user has selected at least one bot
        if user_id == self.challenger.id:
            if not self.challenger_bot_ids:
                await interaction.response.send_message("❌ Select at least one bot first!", ephemeral=True)
                return

            # Verify bet is still affordable
            if self.challenger_bet > self.challenger_player.credits:
                await interaction.response.send_message(
                    f"❌ You no longer have enough credits for your bet! "
                    f"(Need {humanize_number(self.challenger_bet)}, have {humanize_number(self.challenger_player.credits)})",
                    ephemeral=True,
                )
                return

            self.challenger_ready = not self.challenger_ready

        elif user_id == self.opponent.id:
            if not self.opponent_bot_ids:
                await interaction.response.send_message("❌ Select at least one bot first!", ephemeral=True)
                return

            # Verify bet is still affordable
            if self.opponent_bet > self.opponent_player.credits:
                await interaction.response.send_message(
                    f"❌ You no longer have enough credits for your bet! "
                    f"(Need {humanize_number(self.opponent_bet)}, have {humanize_number(self.opponent_player.credits)})",
                    ephemeral=True,
                )
                return

            self.opponent_ready = not self.opponent_ready

        # Check if both are ready - start battle!
        if self.challenger_ready and self.opponent_ready:
            await self._start_battle(interaction)
        else:
            await self.refresh(interaction)

    async def cancel_challenge(self, interaction: discord.Interaction):
        """Handle cancel/decline"""
        user_id = interaction.user.id

        if user_id == self.challenger.id:
            message = f"# ❌ Challenge Cancelled\n{self.challenger.display_name} cancelled the challenge."
        elif user_id == self.opponent.id:
            message = f"# ❌ Challenge Declined\n{self.opponent.display_name} declined the challenge."
        else:
            await interaction.response.send_message("You can't cancel this!", ephemeral=True)
            return

        # Create a simple view with just the message (LayoutViews can't use embeds)
        final_view = ui.LayoutView()
        container = ui.Container(accent_colour=discord.Color.red())
        container.add_item(ui.TextDisplay(message))
        final_view.add_item(container)
        await interaction.response.edit_message(view=final_view)
        self.stop()

    async def _start_battle(self, interaction: discord.Interaction):
        """Start the battle once both players are ready"""
        # Final validation
        challenger_bots = self._get_selected_bots(is_challenger=True)
        opponent_bots = self._get_selected_bots(is_challenger=False)

        if not challenger_bots:
            await interaction.response.send_message(
                f"❌ {self.challenger.display_name} needs to select at least one bot!", ephemeral=True
            )
            self._unready_both()
            return

        if not opponent_bots:
            await interaction.response.send_message(
                f"❌ {self.opponent.display_name} needs to select at least one bot!", ephemeral=True
            )
            self._unready_both()
            return

        # Deduct bets upfront
        if self.challenger_bet > 0:
            if self.challenger_player.credits < self.challenger_bet:
                await interaction.response.send_message(
                    f"❌ {self.challenger.display_name} doesn't have enough credits for their bet!", ephemeral=True
                )
                self._unready_both()
                return

        if self.opponent_bet > 0:
            if self.opponent_player.credits < self.opponent_bet:
                await interaction.response.send_message(
                    f"❌ {self.opponent.display_name} doesn't have enough credits for their bet!", ephemeral=True
                )
                self._unready_both()
                return

        # Start battle
        self.battle_in_progress = True
        await self.refresh(interaction)

        # Run battle
        video_path, result = await self.cog.run_battle_subprocess(
            team1=challenger_bots,
            team2=opponent_bots,
            output_format="mp4",
            team1_color=self.challenger_player.team_color,
            team2_color=self.opponent_player.team_color,
        )

        self.battle_in_progress = False

        if not result or not video_path:
            await self.message.channel.send("❌ Battle Error: An error occurred.", delete_after=10)
            self._unready_both()
            await self.refresh(interaction)
            return

        # Process results
        winner_team = result.get("winner_team", 0)
        duration = result.get("duration", 0)
        battle_stats = format_battle_stats(result, winner_team)

        # Calculate total bets
        total_pot = self.challenger_bet + self.opponent_bet

        # Update stats and handle bets
        challenger_damage = sum(
            result.get("bot_stats", {}).get(bot.id, {}).get("damage_dealt", 0) for bot in challenger_bots
        )
        opponent_damage = sum(
            result.get("bot_stats", {}).get(bot.id, {}).get("damage_dealt", 0) for bot in opponent_bots
        )

        self.challenger_player.total_damage_dealt += challenger_damage
        self.opponent_player.total_damage_dealt += opponent_damage

        challenger_taken = sum(
            result.get("bot_stats", {}).get(bot.id, {}).get("damage_taken", 0) for bot in challenger_bots
        )
        opponent_taken = sum(
            result.get("bot_stats", {}).get(bot.id, {}).get("damage_taken", 0) for bot in opponent_bots
        )

        self.challenger_player.total_damage_taken += challenger_taken
        self.opponent_player.total_damage_taken += opponent_taken

        # Determine winner and handle rewards
        if winner_team == 1:
            # Challenger wins
            winner = self.challenger
            self.challenger_player.pvp_wins += 1
            self.opponent_player.pvp_losses += 1

            # Winner gets the entire pot
            if total_pot > 0:
                self.challenger_player.credits += total_pot
                self.opponent_player.credits -= self.opponent_bet
                # Challenger already "bet" their money, now they get it back plus opponent's bet

            result_text = f"🏆 **{self.challenger.display_name}** wins!"
            reward_text = f"Won **{humanize_number(total_pot)}** credits!" if total_pot > 0 else ""
            color = discord.Color.green()

        elif winner_team == 2:
            # Opponent wins
            winner = self.opponent
            self.opponent_player.pvp_wins += 1
            self.challenger_player.pvp_losses += 1

            # Winner gets the entire pot
            if total_pot > 0:
                self.opponent_player.credits += total_pot
                self.challenger_player.credits -= self.challenger_bet

            result_text = f"🏆 **{self.opponent.display_name}** wins!"
            reward_text = f"Won **{humanize_number(total_pot)}** credits!" if total_pot > 0 else ""
            color = discord.Color.green()

        else:
            # Draw - return bets
            winner = None
            self.challenger_player.pvp_draws += 1
            self.opponent_player.pvp_draws += 1

            result_text = "🤝 It's a draw!"
            reward_text = "Bets returned to both players." if total_pot > 0 else ""
            color = discord.Color.gold()

        # Count kills
        challenger_kills = sum(result.get("bot_stats", {}).get(bot.id, {}).get("kills", 0) for bot in challenger_bots)
        opponent_kills = sum(result.get("bot_stats", {}).get(bot.id, {}).get("kills", 0) for bot in opponent_bots)

        self.challenger_player.bots_destroyed += challenger_kills
        self.opponent_player.bots_destroyed += opponent_kills
        self.challenger_player.bots_lost += opponent_kills
        self.opponent_player.bots_lost += challenger_kills

        self.cog.save()

        # Build result view
        title = "⚔️ PvP Battle Results"
        pot_info = f"\n**💰 Pot:** {humanize_number(total_pot)} credits" if total_pot > 0 else ""
        description = f"{result_text}{pot_info}\n{reward_text}" if reward_text else result_text

        # Build team summaries
        challenger_bot_names = ", ".join(bot.name for bot in challenger_bots)
        opponent_bot_names = ", ".join(bot.name for bot in opponent_bots)

        challenger_stat_text = (
            f"**Bots:** {challenger_bot_names}\n"
            f"**Damage Dealt:** {humanize_number(challenger_damage)}\n"
            f"**Damage Taken:** {humanize_number(challenger_taken)}\n"
            f"**Kills:** {challenger_kills}"
        )
        opponent_stat_text = (
            f"**Bots:** {opponent_bot_names}\n"
            f"**Damage Dealt:** {humanize_number(opponent_damage)}\n"
            f"**Damage Taken:** {humanize_number(opponent_taken)}\n"
            f"**Kills:** {opponent_kills}"
        )

        extra_fields = [
            (f"⚔️ {self.challenger.display_name}", challenger_stat_text),
            (f"🛡️ {self.opponent.display_name}", opponent_stat_text),
        ]

        try:
            ext = video_path.suffix.lstrip(".")
            filename = f"battle.{ext}"
            file = discord.File(video_path, filename=filename)
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
                user=winner,
            )
            result_view.message = self.message
            await self.message.edit(view=result_view, embed=None, attachments=files)
        except Exception as e:
            log.error("Error attaching battle video", exc_info=e)
            result_view, _ = create_battle_result_view(
                title=title,
                description=description,
                color=color,
                duration=duration,
                battle_stats=battle_stats,
                extra_fields=extra_fields,
                ctx=self.ctx,
                cog=self.cog,
                user=winner,
            )
            result_view.message = self.message
            await self.message.edit(view=result_view, embed=None)
        finally:
            try:
                video_path.unlink(missing_ok=True)
            except Exception as e:
                log.debug("Failed to clean up video file %s: %s", video_path, e)

        self.stop()

    async def on_timeout(self):
        if self.message:
            # LayoutViews can't use embeds
            final_view = ui.LayoutView()
            container = ui.Container(accent_colour=discord.Color.dark_gray())
            container.add_item(ui.TextDisplay("# ⏰ Challenge Expired\nThe challenge timed out."))
            final_view.add_item(container)
            try:
                await self.message.edit(view=final_view)
            except discord.HTTPException:
                pass
