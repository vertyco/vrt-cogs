from __future__ import annotations

import asyncio
import io
import logging
import random
import typing as t
from contextlib import suppress
from time import perf_counter, time
from types import SimpleNamespace

import discord
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common import achievements, constants, perks, rock_achievements, rock_picture
from ..common.rock_session import OverswingResult, Payouts, RockSession, Spot, downgraded_tool, redraw_interval
from ..db.tables import Player, PlayerAchievementStats, ResourceLedger
from . import rock_layout

log = logging.getLogger("red.vrt.miner.views.mining_view")

# Fixed custom IDs: a click sent from a client that hasn't seen the latest redraw still matches
MINE_ID = "miner-rock-mine"
INSPECT_ID = "miner-rock-inspect"
SPOT_ID = "miner-rock-spot"

# Private replies to spot clicks that did not win it
SPOT_REPLIES: dict[str, str] = {
    "beaten": "Someone beat you to it!",
    "gone": "That one is gone.",
    "not_mining": "Hit the rock first to claim this.",
}


class RockView(ui.LayoutView):
    """One live rock message. Game rules live in RockSession, drawing in rock_layout."""

    def __init__(
        self,
        cog: MixinMeta,
        rocktype: constants.RockType,
        modifiers: list[constants.Modifier] | None = None,
        ping: str | None = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = RockSession(rocktype, modifiers, ping)
        self.mine_button = ui.Button(
            emoji=constants.PICKAXE_EMOJI, label="Mine", style=discord.ButtonStyle.success, custom_id=MINE_ID
        )
        self.mine_button.callback = self.mine
        self.inspect_button = ui.Button(
            emoji=constants.INSPECT_EMOJI, label="Inspect", style=discord.ButtonStyle.secondary, custom_id=INSPECT_ID
        )
        self.inspect_button.callback = self.inspect
        # Label, emoji and color are set for each spot when it is drawn
        self.spot_button = ui.Button(custom_id=SPOT_ID)
        self.spot_button.callback = self.claim
        self.mine_cooldown = commands.CooldownMapping.from_cooldown(
            rate=constants.SWINGS_PER_THRESHOLD,
            per=constants.OVERSWING_THRESHOLD_SECONDS,
            type=commands.BucketType.user,
        )
        self.steady_cooldown = commands.CooldownMapping.from_cooldown(
            rate=constants.STEADY_SWINGS_PER_THRESHOLD,
            per=constants.OVERSWING_THRESHOLD_SECONDS,
            type=commands.BucketType.user,
        )
        self.message: discord.Message | None = None
        self.ttl_task: asyncio.Task | None = None
        self.flush_task: asyncio.Task | None = None
        self.spot_task: asyncio.Task | None = None  # Countdown of the spot on screen
        # Only one edit of the message may be in flight at a time
        self.edit_lock = asyncio.Lock()
        self.finalizing = False  # No more hits are accepted
        self.finished = False  # finish() has started
        self.dirty = False  # State changed since the last redraw
        self.last_redraw = 0.0
        self.last_text = ""

    async def start(self, destination: discord.abc.Messageable) -> None:
        """Post the rock and start its collapse timer."""
        self.session.start()
        self.last_text = self.render_active()
        self.message = await destination.send(view=self, file=await self.live_picture())
        self.last_redraw = perf_counter()
        self.ttl_task = asyncio.create_task(self.ttl(self.session.rocktype.ttl_seconds))

    async def live_picture(self) -> discord.File:
        """The rock's picture, with its modifier effects on it when it has any."""
        image = self.session.image_file
        if not self.session.modifiers:
            return discord.File(constants.ROCK_IMAGE_DIR / image)
        try:
            data = await asyncio.to_thread(rock_picture.with_effects, image, self.session.modifiers)
        except Exception as e:
            log.warning("Failed to draw modifier effects on %s", image, exc_info=e)
            return discord.File(constants.ROCK_IMAGE_DIR / image)
        # Same file name as the plain picture, so the layout's attachment link finds it
        return discord.File(io.BytesIO(data), filename=image)

    async def ttl(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            await self.finish()
        except asyncio.CancelledError:
            pass

    # ---------------------------- DRAWING ----------------------------

    def show_items(self, items: list[ui.Item]) -> str:
        """Replace the layout with `items` and return its text."""
        self.clear_items()
        for item in items:
            self.add_item(item)
        return rock_layout.layout_text(self)

    def render_active(self) -> str:
        spot = self.session.spot
        if self.session.spot_open and not spot.shown:
            # The end time drawn on screen counts from the redraw that first shows the spot
            spot.closes_at = time() + constants.WEAK_SPOT_OPEN_SECONDS
        synergy = self.session.party_synergy()
        buttons = (self.mine_button, self.inspect_button, self.spot_button)
        text = self.show_items(rock_layout.build_active(self.session, synergy, *buttons))
        # discord.py unhooks buttons that leave the layout and then drops their clicks. Late clicks on a
        # removed spot button must still reach claim() for their "beaten" or "gone" reply.
        self.spot_button._update_view(self)
        return text

    def redraw_due(self) -> bool:
        return perf_counter() - self.last_redraw >= redraw_interval(len(self.session.participants))

    async def redraw(self, interaction: discord.Interaction | None = None) -> None:
        """Draw the newest state. With `interaction`, that click is acknowledged first."""
        async with self.edit_lock:
            if interaction:
                # Clicks never carry the redraw itself: every edit goes through the message, the one path
                # proven to keep the uploaded picture
                await self.acknowledge(interaction)
            if self.finalizing:
                return
            self.dirty = False
            text = self.render_active()
            spot = self.session.spot if self.session.spot_open else None
            self.last_redraw = perf_counter()
            if text == self.last_text:
                return
            self.last_text = text
            try:
                # No `attachments`: leaving it out keeps the picture uploaded with the message. A Components V2
                # message lists no attachments, so passing its list would delete the picture the layout shows.
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.warning("Failed to redraw rock message %s", getattr(self.message, "id", None), exc_info=e)
                self.last_text = ""
                if interaction:
                    # Nothing else may click again, so the background redraw shows this state
                    self.mark_dirty()
                return
            self.spot_drawn(spot)

    def spot_drawn(self, spot: Spot | None) -> None:
        """A redraw showing `spot` has landed: from now on it can be claimed, and its countdown runs."""
        if spot is None or spot.shown:
            return
        spot.shown = True
        if self.spot_task:
            self.spot_task.cancel()
        self.spot_task = asyncio.create_task(self.spot_timer(spot))

    async def spot_timer(self, spot: Spot) -> None:
        """Take `spot` off the rock when its countdown ends, unless someone claimed it first."""
        try:
            await asyncio.sleep(constants.WEAK_SPOT_OPEN_SECONDS)
            if self.session.close_spot(spot):
                self.mark_dirty()
        except asyncio.CancelledError:
            pass

    def mark_dirty(self) -> None:
        if self.finalizing:
            return
        self.dirty = True
        if self.flush_task is None or self.flush_task.done():
            self.flush_task = asyncio.create_task(self.flush())

    async def flush(self) -> None:
        """Redraw once per window for as long as clicks keep changing the rock."""
        while self.dirty and not self.finalizing:
            wait = redraw_interval(len(self.session.participants)) - (perf_counter() - self.last_redraw)
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            await self.redraw()

    async def show(self, items: list[ui.Item], image: str | None = None) -> None:
        """Final edit of the message (results or the zero-hits line), uploading `image` for it to show."""
        async with self.edit_lock:
            # Stop listening only now, so clicks during the payout still get a reply. It must run before
            # show_items(): discord.py unregisters the buttons that are in the layout at stop() time.
            # The spot button may have left the layout already; without it there, discord.py would keep it,
            # and through it this whole view, registered forever.
            self.add_item(ui.ActionRow(self.spot_button))
            self.stop()
            self.show_items(items)
            try:
                # Replaces the live rock's picture, which the final layouts don't show
                files = [discord.File(constants.ROCK_IMAGE_DIR / image)] if image else []
                await self.message.edit(view=self, attachments=files)
            except discord.HTTPException as e:
                log.warning("Failed to show final rock message %s", getattr(self.message, "id", None), exc_info=e)

    # ---------------------------- CLICKS ----------------------------

    async def acknowledge(self, interaction: discord.Interaction) -> None:
        if interaction.response.is_done():
            return
        try:
            await interaction.response.defer()
        except discord.HTTPException as e:
            # The click still counts; a lost acknowledgement must not stop the rock from updating or finishing
            log.warning(
                "Failed to acknowledge a click on rock message %s", getattr(self.message, "id", None), exc_info=e
            )

    async def respond(self, interaction: discord.Interaction) -> None:
        """Acknowledge the click, and redraw now when one is due or later otherwise."""
        if self.finalizing:
            await self.acknowledge(interaction)
            return
        if interaction.response.is_done() or self.edit_lock.locked() or not self.redraw_due():
            await self.acknowledge(interaction)
            self.mark_dirty()
            return
        await self.redraw(interaction)

    async def loadout_is_cached(self, user_id: int) -> bool:
        cache = self.cog.db_utils.get_cached_loadout.cache  # type: ignore
        return await cache.exists(f"miner_loadout:{user_id}")

    def swinging_too_fast(self, user_id: int, steady: bool = False) -> bool:
        mapping = self.steady_cooldown if steady else self.mine_cooldown
        bucket = mapping.get_bucket(SimpleNamespace(author=SimpleNamespace(id=user_id)))
        return bool(bucket.update_rate_limit())

    async def mine(self, interaction: discord.Interaction) -> None:
        if not self.cog.db_active():
            await interaction.response.send_message("Database is not active.", ephemeral=True)
            return
        if self.finalizing:
            await interaction.response.send_message("This mining event is being finalized!", ephemeral=True)
            return
        user = interaction.user
        if not await self.loadout_is_cached(user.id):
            # The lookup will hit the database, so answer Discord first
            await self.acknowledge(interaction)
        loadout = await self.cog.db_utils.get_cached_loadout(user)
        tool = constants.TOOLS[loadout.tool]
        if self.swinging_too_fast(user.id, "steady" in loadout.perks):
            await self.overswing(interaction, tool)
        elif self.hit(user, tool, loadout.perks):
            await self.acknowledge(interaction)
            await self.finish()
            return
        await self.respond(interaction)

    def hit(self, user: discord.abc.User, tool: constants.ToolTier, perk_keys: frozenset[str] = frozenset()) -> bool:
        """Apply one hit. Return True when this hit broke the rock."""
        if self.finalizing:
            return False
        self.session.apply_hit(user.id, user.name, tool, perk_keys)
        if not self.session.depleted:
            return False
        self.finalizing = True
        return True

    async def claim(self, interaction: discord.Interaction) -> None:
        """A click on the spot button. Never counts as a swing, so it cannot overswing."""
        if not self.cog.db_active():
            await interaction.response.send_message("Database is not active.", ephemeral=True)
            return
        if self.finalizing:
            await interaction.response.send_message("This mining event is being finalized!", ephemeral=True)
            return
        outcome = self.session.claim_spot(interaction.user.id, interaction.user.name)
        if outcome != "won":
            await interaction.response.send_message(SPOT_REPLIES[outcome], ephemeral=True)
            return
        if self.session.depleted:
            # The weak spot broke the rock
            self.finalizing = True
            await self.acknowledge(interaction)
            await self.finish()
            return
        await self.respond(interaction)

    async def overswing(self, interaction: discord.Interaction, tool: constants.ToolTier) -> None:
        user = interaction.user
        if tool.key == "wood":
            self.session.record_overswing(user.id, user.name, tool, None)
            return
        await self.acknowledge(interaction)
        player = await self.cog.db_utils.get_create_player(user)
        current = constants.TOOLS[player.tool]
        result = self.session.judge_overswing(
            current, player.durability, random.uniform(0.0, 1.0), "sturdy" in perks.owned_perks(player.perks)
        )
        self.session.record_overswing(user.id, user.name, current, result)
        await self.apply_overswing(interaction, player, current, result)

    async def apply_overswing(
        self,
        interaction: discord.Interaction,
        player: Player,
        tool: constants.ToolTier,
        result: OverswingResult,
    ) -> None:
        if result.kind in ("shatter", "break"):
            rock = self.session.rocktype.display_name
            text = f"You swing too hastily at the {rock} and your {tool.display_name} shatters!"
            lost = perks.owned_perks(player.perks)
            if lost:
                text += f" Its perks are gone: {perks.summary(lost)}."
            await interaction.followup.send(text, ephemeral=True)
            await self.downgrade_player(player)
        elif result.kind == "damage":
            await player.update_self({Player.durability: result.durability})
            await self.send_durability_warning(interaction, player.id, tool, result.durability, tool.max_durability)

    async def downgrade_player(self, player: Player) -> None:
        lower = downgraded_tool(player.tool)
        await player.update_self(
            {Player.tool: lower.key, Player.durability: lower.max_durability or 0, Player.perks: []}
        )
        await self.set_shatter_stage(player.id, 1)
        self.cog.reset_durability_warnings(player.id)
        # The cached pickaxe just changed
        await self.cog.db_utils.clear_cached_loadout(player.id)

    async def inspect(self, interaction: discord.Interaction) -> None:
        if not self.cog.db_active():
            await interaction.response.send_message("Database is not active.", ephemeral=True)
            return
        session = self.session
        embed = discord.Embed(title="Rock Inspection")
        embed.add_field(name="Current HP", value=f"`{session.current_hp}` / `{session.max_hp}`", inline=False)
        collapse_loot = [f"• {k.title()}: {v}" for k, v in session.floor_loot.items()]
        embed.add_field(name="Collapse Yield", value=box("\n".join(collapse_loot) or "None", lang="py"))
        full_loot = [f"• {k.title()}: {v}" for k, v in session.total_loot.items()]
        embed.add_field(name="Depletion Yield", value=box("\n".join(full_loot) or "None", lang="py"))
        volatility = (
            f"• Shatter chance: {session.overswing_break_chance * 100:.0f}%\n"
            f"• Damage chance: {session.overswing_damage_chance * 100:.0f}%"
        )
        embed.add_field(name="Volatility", value=box(volatility, lang="py"))
        if session.modifiers:
            mod_text = "\n".join(f"{mod.emoji} **{mod.display_name}**: {mod.description}" for mod in session.modifiers)
            embed.add_field(name="Rock Modifiers", value=mod_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------- FINISHING ----------------------------

    async def finish(self) -> None:
        """End the rock once: pay everyone, show the results, then hand out achievements."""
        if self.finished:
            return
        self.finished = True
        self.finalizing = True
        if self.ttl_task and self.ttl_task is not asyncio.current_task():
            self.ttl_task.cancel()
        if self.spot_task:
            self.spot_task.cancel()
        # A redraw already in flight is left to land: show() waits for it on edit_lock, then the flush loop
        # sees `finalizing` and stops. Cancelling it could let the stale redraw arrive after the results.
        try:
            if not self.session.participants:
                await self.show(rock_layout.build_nobody(self.session))
                return
            duration = self.session.duration()
            payouts = self.session.compute_payouts()
            rows, players = await self.pay_out(payouts)
            results = rock_layout.build_results(self.session, payouts.synergy, rows, duration)
            await self.show(results, rock_layout.result_image(self.session))
            await self.finish_achievements(players, payouts, duration)
        finally:
            # Lets `[p]rock`'s view.wait() return even if paying out failed
            self.stop()

    async def pay_out(self, payouts: Payouts) -> tuple[list[rock_layout.MinerResult], dict[int, Player]]:
        """Write loot, ledger rows and tool wear. Return result rows (paid miners only) and every miner's Player."""
        ids = list(self.session.participants)
        players = {p.id: p for p in await Player.objects().where(Player.id.is_in(ids))}
        rows: list[rock_layout.MinerResult] = []
        ledgers: list[ResourceLedger] = []
        for uid, damage in self.session.ranked():
            loot = {res: amount for res, amount in payouts.loot.get(uid, {}).items() if amount > 0}
            if not loot:
                continue
            ledgers.extend(ResourceLedger(player=uid, resource=res, amount=amount) for res, amount in loot.items())
            tool_lines = await self.pay_player(players[uid], loot, payouts.synergy)
            rows.append(self.result_row(uid, damage, loot, tool_lines, payouts))
        if ledgers:
            await ResourceLedger.insert(*ledgers)
        return rows, players

    async def pay_player(
        self, player: Player, loot: dict[constants.Resource, int], synergy: dict[str, t.Any]
    ) -> list[str]:
        """Add the loot and wear the pickaxe. Return the pickaxe lines for the result row."""
        update: dict[t.Any, t.Any] = {
            getattr(Player, res): getattr(Player, res) + amount for res, amount in loot.items()
        }
        lines: list[str] = []
        tool = player.tool
        if tool != "wood":
            lines = self.wear_tool(player, synergy, update)
        await player.update_self(update)
        if player.tool != tool:
            # The pickaxe wore out; clear the cached tool so the next click doesn't hit at the old tier
            await self.cog.db_utils.clear_cached_loadout(player.id)
        return lines

    def wear_tool(self, player: Player, synergy: dict[str, t.Any], update: dict[t.Any, t.Any]) -> list[str]:
        tool = constants.TOOLS[player.tool]
        wear = self.session.tool_wear(player.id, synergy)
        durability = max(0, player.durability - wear)
        if not durability:
            lower = downgraded_tool(player.tool)
            update[Player.tool] = lower.key
            update[Player.durability] = lower.max_durability or 0
            update[Player.perks] = []
            self.cog.reset_durability_warnings(player.id)
            line = f"‼️{player.tool.title()} broke due to overuse, downgraded to {lower.display_name}"
            lost = perks.owned_perks(player.perks)
            return [f"{line}. Perks lost: {perks.summary(lost)}" if lost else line]
        update[Player.durability] = durability
        lines = [f"-`{wear}` durability to {tool.display_name} (now `{durability}`)"]
        note = self.durability_warning_note(player.id, tool, durability)
        if note:
            lines.append(note)
        return lines

    def result_row(
        self,
        uid: int,
        damage: int,
        loot: dict[constants.Resource, int],
        tool_lines: list[str],
        payouts: Payouts,
    ) -> rock_layout.MinerResult:
        guild = self.message.guild if self.message else None
        user = (guild.get_member(uid) if guild else None) or self.cog.bot.get_user(uid)
        roles = {holder: name for name, holder in payouts.synergy["roles"]}
        return rock_layout.MinerResult(
            name=user.display_name if user else "Unknown miner",
            avatar_url=user.display_avatar.url if user else None,
            role=roles.get(uid),
            damage=round(damage),
            hits=self.session.hits.get(uid, 0),
            score=payouts.scores.get(uid, 0),
            overswings=self.session.overswings.get(uid, 0),
            bonus_pct=payouts.bonus_pct.get(uid, 0.0),
            loot=loot,
            tool_lines=tool_lines,
        )

    async def finish_achievements(self, players: dict[int, Player], payouts: Payouts, duration: float) -> None:
        roles = {holder: name for name, holder in payouts.synergy["roles"]}
        role_count = len(payouts.synergy["roles"])
        for uid, player in players.items():
            score = payouts.scores.get(uid, 0)
            # pay_out's update_self already wrote the post-wear tool and durability onto `player`
            end_ratio = rock_achievements.end_durability_ratio(
                self.session.tools.get(uid), player.tool, player.durability
            )
            outcome = rock_achievements.outcome_for(
                self.session, uid, score, roles.get(uid), duration, role_count, end_ratio
            )
            stats = await self.cog.get_player_achievement_stats(uid)
            totals = rock_achievements.new_totals(stats, outcome)
            await stats.update_self(rock_achievements.stat_updates(stats, outcome, totals))
            exact_unlocks = await self.cog.sync_player_achievements(uid)
            live_unlocks = await self.cog.unlock_player_achievements(
                uid, rock_achievements.achievement_keys(outcome, totals)
            )
            # Last, so a collection completed by this rock's live unlocks arrives in the same announcement
            collection_unlocks = await self.cog.unlock_collections(uid)
            combined = achievements.dedupe_achievement_defs([*exact_unlocks, *live_unlocks, *collection_unlocks])
            if combined and self.message:
                await self.cog.announce_achievement_unlocks(self.message.channel, uid, combined)

    # ---------------------------- DURABILITY ----------------------------

    async def set_shatter_stage(self, user_id: int, stage: int) -> None:
        stats = await self.cog.get_player_achievement_stats(user_id)
        await stats.update_self({PlayerAchievementStats.shatter_recovery_stage: stage})

    async def send_durability_warning(
        self,
        interaction: discord.Interaction,
        player_id: int,
        tool: constants.ToolTier,
        durability: int,
        max_durability: int | None,
    ) -> None:
        if not isinstance(max_durability, int) or max_durability <= 0:
            return
        threshold = self.cog.register_durability_ratio(player_id, durability / max_durability)
        if threshold is None:
            return
        critical = min(constants.DURABILITY_WARNING_THRESHOLDS or (0.1,))
        severity = "critically low" if threshold <= critical else "running low"
        message = (
            f"⚠️ Your {tool.display_name} durability is {severity}"
            f" ({durability}/{max_durability}). Consider repairing soon."
        )
        with suppress(discord.HTTPException):
            await interaction.followup.send(message, ephemeral=True)

    def durability_warning_note(self, player_id: int, tool: constants.ToolTier, durability: int) -> str | None:
        max_durability = tool.max_durability
        if not isinstance(max_durability, int) or max_durability <= 0:
            return None
        threshold = self.cog.register_durability_ratio(player_id, durability / max_durability)
        if threshold is None:
            return None
        critical = min(constants.DURABILITY_WARNING_THRESHOLDS or (0.1,))
        if threshold <= critical:
            return f"⚠️ {tool.display_name} is critically low on durability ({durability}/{max_durability})."
        return f"⚠️ {tool.display_name} durability is running low ({durability}/{max_durability})."
