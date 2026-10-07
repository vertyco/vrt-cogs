"""
Bot Arena - Challenge Puzzle Views

Challenges loan the player a fixed squad; the player only picks each bot's orders.
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

from ..common.campaign import NPCBot
from ..common.challenge_mode import CHALLENGES, Challenge, grant_challenge_rewards, is_unlocked, succeeded
from ..common.models import Bot, MovementStance, PartsRegistry, TacticalOrders, TargetPriority
from ..constants import get_random_tip
from . import hub
from .base import BotArenaView
from .inventory import STANCE_INFO, TARGET_INFO

log = logging.getLogger("red.vrt.botarena.challenge_mode")

TARGET_TITLES = {
    TargetPriority.FOCUS_FIRE: "Focus Fire",
    TargetPriority.WEAKEST: "Weakest",
    TargetPriority.CLOSEST: "Closest",
}


def reward_text(challenge: Challenge) -> str:
    text = f"💰 {humanize_number(challenge.credit_reward)}"
    if challenge.prize_part:
        text += f" + 🏆 {challenge.prize_part}"
    return text


def bot_line(npc: NPCBot, registry: PartsRegistry) -> str:
    bot = npc.to_bot(registry)
    weapon = bot.component
    return (
        f"**{npc.name}** ❤️{bot.total_shielding} | {npc.chassis_name} | {npc.plating_name}\n"
        f"-# ⚔️ {weapon.name}: range {weapon.min_range}-{weapon.max_range}, 🎯 {weapon.accuracy_label}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHALLENGE LIST
# ─────────────────────────────────────────────────────────────────────────────


class ChallengeSelectRow(ui.ActionRow["ChallengeListLayout"]):
    def __init__(self, completed_missions: set[str], completed_challenges: list[str]):
        super().__init__()
        options = []
        for challenge in CHALLENGES:
            if not is_unlocked(challenge, completed_missions):
                continue
            options.append(
                discord.SelectOption(
                    label=challenge.name,
                    description=challenge.description[:100],
                    value=challenge.id,
                    emoji="✅" if challenge.id in completed_challenges else "🔓",
                )
            )
        self.challenge_select.options = options  # type: ignore[attr-defined]

    @ui.select(placeholder="Pick a challenge...")
    async def challenge_select(self, interaction: discord.Interaction, select: ui.Select):
        challenge = next(c for c in CHALLENGES if c.id == select.values[0])
        view = ChallengeBriefingLayout(self.view.ctx, self.view.cog, challenge, parent=self.view)
        self.view.navigate_to_child(view)
        await view.send(interaction)


class ChallengeListNavigationRow(ui.ActionRow["ChallengeListLayout"]):
    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.navigate_back(interaction)


class ChallengeListLayout(BotArenaView):
    """Every challenge with its status, reward and unlock requirement"""

    def __init__(self, ctx: commands.Context, cog: "BotArena", parent: t.Optional[ui.LayoutView] = None):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self._build_layout()

    def _build_layout(self):
        player = self.cog.db.get_player(self.ctx.author.id)
        completed_missions = set(player.completed_missions)
        done = len(player.completed_challenges)

        container = ui.Container(accent_colour=discord.Color.purple())
        container.add_item(
            ui.TextDisplay(
                f"# 🧩 Challenges ({done}/{len(CHALLENGES)})\n"
                "*Win with loaned bots. You only pick their orders.*\n"
                f"-# Player: {self.ctx.author.mention}"
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        lines = []
        for challenge in CHALLENGES:
            if challenge.id in player.completed_challenges:
                lines.append(f"**✅ {challenge.name}**\n-# {challenge.description}")
            elif is_unlocked(challenge, completed_missions):
                lines.append(f"**🔓 {challenge.name}** | {reward_text(challenge)}\n-# {challenge.description}")
            else:
                lines.append(
                    f"**🔒 {challenge.name}** | {reward_text(challenge)}\n"
                    f"-# Beat mission {challenge.required_mission} to unlock"
                )
        container.add_item(ui.TextDisplay("\n".join(lines)))

        self.add_item(container)
        self.add_item(ChallengeSelectRow(completed_missions, player.completed_challenges))
        self.add_item(ChallengeListNavigationRow())


# ─────────────────────────────────────────────────────────────────────────────
# CHALLENGE BRIEFING
# ─────────────────────────────────────────────────────────────────────────────


class StanceSelectRow(ui.ActionRow["ChallengeBriefingLayout"]):
    def __init__(self, index: int, bot_name: str, current: MovementStance):
        super().__init__()
        self.index = index
        self.stance_select.placeholder = f"{bot_name}: stance"  # type: ignore[attr-defined]
        self.stance_select.options = [  # type: ignore[attr-defined]
            discord.SelectOption(
                label=f"{bot_name}: {info['title']}",
                description=info["desc"][:100],
                value=stance.value,
                emoji=info["emoji"],
                default=stance == current,
            )
            for stance, info in STANCE_INFO.items()
        ]

    @ui.select()
    async def stance_select(self, interaction: discord.Interaction, select: ui.Select):
        orders = self.view.orders[self.index]
        self.view.orders[self.index] = orders.model_copy(update={"movement_stance": MovementStance(select.values[0])})
        await self.view.refresh(interaction)


class TargetSelectRow(ui.ActionRow["ChallengeBriefingLayout"]):
    def __init__(self, index: int, bot_name: str, current: TargetPriority):
        super().__init__()
        self.index = index
        self.target_select.placeholder = f"{bot_name}: target"  # type: ignore[attr-defined]
        self.target_select.options = [  # type: ignore[attr-defined]
            discord.SelectOption(
                label=f"{bot_name}: {TARGET_TITLES[target]}",
                description=desc[:100],
                value=target.value,
                emoji=emoji,
                default=target == current,
            )
            for target, (emoji, desc) in TARGET_INFO.items()
        ]

    @ui.select()
    async def target_select(self, interaction: discord.Interaction, select: ui.Select):
        orders = self.view.orders[self.index]
        self.view.orders[self.index] = orders.model_copy(update={"target_priority": TargetPriority(select.values[0])})
        await self.view.refresh(interaction)


class ChallengeActionRow(ui.ActionRow["ChallengeBriefingLayout"]):
    @ui.button(label="Start Challenge!", style=discord.ButtonStyle.success, emoji="⚔️")
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.run_battle(interaction)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.navigate_back(interaction)


class ChallengeBriefingLayout(BotArenaView):
    """Challenge briefing: see both squads, set each loaned bot's orders, then fight"""

    def __init__(
        self,
        ctx: commands.Context,
        cog: "BotArena",
        challenge: Challenge,
        parent: t.Optional[ui.LayoutView] = None,
        orders: t.Optional[list[TacticalOrders]] = None,
    ):
        super().__init__(ctx=ctx, cog=cog, timeout=300, parent=parent)
        self.challenge = challenge
        self.orders: list[TacticalOrders] = list(orders or [TacticalOrders() for _ in challenge.loaned_bots])
        self.battle_in_progress = False
        self._build_layout()

    def squad_bots(self) -> list[Bot]:
        """The loaned bots, each carrying the orders the player picked"""
        bots = [
            npc.model_copy(update={"tactical_orders": orders}).to_bot(self.cog.registry)
            for npc, orders in zip(self.challenge.loaned_bots, self.orders)
        ]
        return [bot for bot in bots if bot]

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()
        self._build_layout()
        await interaction.response.edit_message(view=self)

    def goal_text(self, already_cleared: bool) -> str:
        lines = ["**🎯 Goal**", "Destroy every enemy."]
        for name in self.challenge.must_survive:
            lines.append(f"**{name}** must survive, or you lose.")
        if already_cleared:
            lines.append("\n**🎁 Reward:** already claimed (replays pay nothing)")
        else:
            lines.append(f"\n**🎁 Reward:** {reward_text(self.challenge)}")
        return "\n".join(lines)

    def _build_layout(self):
        if self.battle_in_progress:
            container = ui.Container(accent_colour=discord.Color.orange())
            container.add_item(
                ui.TextDisplay(
                    f"# ⚔️ Challenge in Progress!\n"
                    f"**Challenge:** {self.challenge.name}\n"
                    f"**Player:** {self.ctx.author.mention}\n\n"
                    f"🎬 Simulating and rendering battle...\n\n"
                    f"{get_random_tip()}"
                )
            )
            self.add_item(container)
            return

        player = self.cog.db.get_player(self.ctx.author.id)
        registry = self.cog.registry
        container = ui.Container(accent_colour=discord.Color.purple())
        container.add_item(
            ui.TextDisplay(
                f"# 🧩 {self.challenge.name}\n*{self.challenge.briefing}*\n-# Player: {self.ctx.author.mention}"
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        squad = "\n".join(bot_line(npc, registry) for npc in self.challenge.loaned_bots)
        container.add_item(ui.TextDisplay(f"**🤖 Your loaned bots**\n{squad}"))
        enemies = "\n".join(bot_line(npc, registry) for npc in self.challenge.enemies)
        container.add_item(ui.TextDisplay(f"**👾 Enemies**\n{enemies}"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(ui.TextDisplay(self.goal_text(self.challenge.id in player.completed_challenges)))
        self.add_item(container)

        for index, (npc, orders) in enumerate(zip(self.challenge.loaned_bots, self.orders)):
            self.add_item(StanceSelectRow(index, npc.name, orders.movement_stance))
            self.add_item(TargetSelectRow(index, npc.name, orders.target_priority))
        self.add_item(ChallengeActionRow())

    async def run_battle(self, interaction: discord.Interaction):
        """Guarded entry point - one battle per user at a time, always released on exit."""
        user_id = self.ctx.author.id
        if user_id in self.cog.active_battles:
            await interaction.response.send_message("❌ You already have a battle in progress.", ephemeral=True)
            return
        self.cog.active_battles.add(user_id)
        try:
            await self.execute_battle(interaction)
        finally:
            self.cog.active_battles.discard(user_id)

    async def execute_battle(self, interaction: discord.Interaction):
        player = self.cog.db.get_player(self.ctx.author.id)
        squad = self.squad_bots()
        enemies = [npc.to_bot(self.cog.registry) for npc in self.challenge.enemies]

        self.battle_in_progress = True
        await self.refresh(interaction)

        video_path, result, error = await self.cog.run_battle_subprocess(
            team1=squad,
            team2=enemies,
            output_format="mp4",
            team1_color=player.team_color,
            chapter=self.challenge.chapter,
        )
        if not result or not video_path:
            log.error(f"Challenge {self.challenge.id} failed for user {self.ctx.author.id}: {error or 'Unknown error'}")
            self.battle_in_progress = False
            self.clear_items()
            self._build_layout()
            # Interaction already responded, use message.edit instead
            if self.message:
                await self.message.edit(view=self)
            await interaction.followup.send("❌ The battle failed to run. Please try again later.", ephemeral=True)
            return

        won = succeeded(self.challenge, result)
        first_clear = won and self.challenge.id not in player.completed_challenges
        prizes = grant_challenge_rewards(player, self.challenge) if first_clear else []
        if first_clear:
            self.cog.save(force=True)

        title, description, color, extra_fields = self.result_text(result, won, first_clear)
        await hub.send_battle_result(
            self.message,
            video_path,
            title=title,
            description=description,
            color=color,
            duration=result.get("duration", 0),
            battle_stats=hub.format_battle_stats(result, result.get("winner_team", 0)),
            extra_fields=extra_fields,
            ctx=self.ctx,
            cog=self.cog,
            user=self.ctx.author,
            mission_name=f"Challenge: {self.challenge.name}",
            actions_row=ChallengeBattleActionsRow(self.challenge, self.orders),
        )
        if prizes:
            await hub.send_unlock_notifications(interaction, self.cog.registry, prizes, "🏆 Prize won")
        self.stop()

    def result_text(
        self, result: dict, won: bool, first_clear: bool
    ) -> tuple[str, str, discord.Color, list[tuple[str, str]]]:
        """Title, description, colour and extra fields for the result screen"""
        if won and first_clear:
            return (
                "🏆 Challenge Complete!",
                self.challenge.victory_text,
                discord.Color.green(),
                [("🎁 Rewards", reward_text(self.challenge))],
            )
        if won:
            return "✅ Challenge Complete! (Replay)", self.challenge.victory_text, discord.Color.blue(), []
        winner_team = result.get("winner_team", 0)
        if winner_team == 1:
            lost = ", ".join(f"**{name}**" for name in self.challenge.must_survive)
            return "💀 Challenge Failed", f"You won the fight, but {lost} was destroyed.", discord.Color.red(), []
        if winner_team == 0:
            return "⚖️ Stalemate", "Time ran out before every enemy fell.", discord.Color.gold(), []
        return "💀 Challenge Failed", self.challenge.defeat_text, discord.Color.red(), []


# ─────────────────────────────────────────────────────────────────────────────
# RESULT BUTTONS
# ─────────────────────────────────────────────────────────────────────────────


class ChallengeBattleActionsRow(ui.ActionRow["hub.BattleResultLayout"]):
    """Result buttons for a challenge: Try Again keeps the same orders"""

    def __init__(self, challenge: Challenge, orders: list[TacticalOrders]):
        super().__init__()
        self.challenge = challenge
        self.orders = list(orders)

    async def finish(self):
        self.retry_button.disabled = True
        self.return_button.disabled = True
        await self.view.message.edit(view=self.view)
        self.view.stop()

    @ui.button(label="Try Again", style=discord.ButtonStyle.primary, emoji="🔄")
    async def retry_button(self, interaction: discord.Interaction, button: ui.Button):
        ctx, cog = self.view.ctx, self.view.cog
        # Back from the briefing goes to the challenge list, then the hub
        hub_view = hub.GameHubLayout(ctx, cog)
        list_view = ChallengeListLayout(ctx, cog, parent=hub_view)
        view = ChallengeBriefingLayout(ctx, cog, self.challenge, parent=list_view, orders=self.orders)
        await interaction.response.send_message(view=view)
        hub_view.message = await interaction.original_response()
        hub_view.navigate_to_child(list_view)
        list_view.navigate_to_child(view)
        await self.finish()

    @ui.button(label="Return to Hub", style=discord.ButtonStyle.secondary, emoji="🏠")
    async def return_button(self, interaction: discord.Interaction, button: ui.Button):
        hub_view = hub.GameHubLayout(self.view.ctx, self.view.cog)
        await interaction.response.send_message(view=hub_view)
        hub_view.message = await interaction.original_response()
        await self.finish()
