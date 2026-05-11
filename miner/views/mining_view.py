from __future__ import annotations

import asyncio
import logging
import random
import typing as t
from collections import defaultdict, deque
from contextlib import suppress
from datetime import datetime, timedelta
from io import StringIO
from time import perf_counter
from types import SimpleNamespace

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common import achievements, constants
from ..db.tables import Player, PlayerAchievementStats, ResourceLedger

log = logging.getLogger("red.vrt.miner.views.mining_view")


def hp_bar(hp: int, max_hp: int) -> str:
    if max_hp <= 0:
        return f"{constants.HP_BAR_EMPTY * constants.HP_BAR_SEGMENTS} 0.0%"
    ratio = hp / max_hp
    width: int = constants.HP_BAR_SEGMENTS
    bar = constants.HP_BAR_FILLED * round(ratio * width) + constants.HP_BAR_EMPTY * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


class RockView(discord.ui.View):
    def __init__(self, cog: MixinMeta, rocktype: constants.RockType, modifiers: list[constants.Modifier] | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.rocktype: constants.RockType = rocktype
        self.modifiers = modifiers or []

        # Apply modifier stat multipliers
        hp_mult = 1.0
        loot_mult = 1.0
        volatility_mult = 1.0
        for mod in self.modifiers:
            hp_mult *= mod.hp_multiplier
            loot_mult *= mod.loot_multiplier
            volatility_mult *= mod.volatility_multiplier

        self.max_hp = max(1, int(round(rocktype.hp * hp_mult)))
        self.current_hp = self.max_hp

        # Apply loot multipliers
        self.total_loot = {k: max(1, int(round(v * loot_mult))) for k, v in rocktype.total_loot.items() if v > 0}
        self.floor_loot = {k: max(1, int(round(v * loot_mult))) for k, v in rocktype.floor_loot.items() if v > 0}

        # Store original volatility for later use
        self.volatility_multiplier = volatility_mult
        self.overswing_break_chance = min(1.0, rocktype.overswing_break_chance * volatility_mult)
        self.overswing_damage_chance = min(1.0, rocktype.overswing_damage_chance * volatility_mult)

        self.message: discord.Message | None = None
        self.started_at_perf: float = 0.0

        # user_id -> total damage dealt
        self.participants: dict[int, int] = defaultdict(int)
        self.hits: dict[int, int] = defaultdict(int)
        self.overswings: dict[int, int] = defaultdict(int)
        self.crit_hits: dict[int, int] = defaultdict(int)
        self.low_hp_damage: dict[int, int] = defaultdict(int)
        self.shatter_resist_survivors: set[int] = set()
        self.shattered_users: set[int] = set()
        self.mine_cooldown = commands.CooldownMapping.from_cooldown(
            rate=constants.SWINGS_PER_THRESHOLD,
            per=constants.OVERSWING_THRESHOLD_SECONDS,
            type=commands.BucketType.user,
        )
        self.msg_update_cooldown = commands.CooldownMapping.from_cooldown(
            rate=1,
            per=1.5,
            type=commands.BucketType.channel,
        )

        self.end_time: datetime | None = None
        self.ttl_task: asyncio.Task | None = None

        self.action_window: deque[str] = deque(maxlen=10)
        self.finalizing: bool = False

        self._mine_lock = asyncio.Lock()

    async def start(self, channel: discord.TextChannel | discord.Thread):
        """Start the rock session"""
        ttl_seconds = self.rocktype.ttl_seconds
        self.started_at_perf = perf_counter()
        self.end_time = datetime.now() + timedelta(seconds=ttl_seconds)
        self.message = await channel.send(embed=self.embed(), view=self)
        self.ttl_task = asyncio.create_task(self.ttl(ttl_seconds))

    async def ttl(self, ttl_seconds: int):
        try:
            await asyncio.sleep(ttl_seconds)
            if self.finalizing:
                return
            await self.finalize()
        except asyncio.CancelledError:
            pass

    def color(self) -> discord.Color:
        """Progressively go from white to red as the health gets closer to 0"""
        decrement = int((255 / self.max_hp) * self.current_hp)
        decrement = max(0, min(255, decrement))
        green = blue = decrement
        return discord.Color.from_rgb(255, green, blue)

    def embed(self):
        title = self.rocktype.display_name
        # Add modifier emojis to title if modifiers exist
        if self.modifiers:
            mod_emojis = " ".join(f"{mod.emoji}" for mod in self.modifiers)
            title = f"{mod_emojis} {title}"

        synergy_context = self.compute_party_synergy_context()

        embed = discord.Embed(title=title, color=self.color())

        if not self.current_hp:
            embed.set_thumbnail(url=constants.DEPLETED_ROCK_URL)
            embed.description = "The rock has been completely mined!"
        elif datetime.now() < self.end_time:
            embed.set_image(url=self.rocktype.image_url)
            ts = round(self.end_time.timestamp())
            embed.description = f"Mineshaft is unstable and will collapse <t:{ts}:R>"
            embed.add_field(name="HP", value=box(hp_bar(self.current_hp, self.max_hp), lang="py"))
        else:
            embed.set_image(url=constants.COLLAPSED_MINESHAFT_URL)
            embed.description = "Mineshaft has collapsed!"
            embed.add_field(name="HP", value=box(hp_bar(self.current_hp, self.max_hp), lang="py"))

        if self.action_window:
            embed.description += "\n\n**Recent Actions:**\n"
            embed.description += "\n".join(f"-# {i.strip()}" for i in self.action_window)

        if synergy_context["roles"]:
            embed.add_field(
                name="Party Synergy",
                value=self.format_party_synergy_field(synergy_context),
                inline=False,
            )
        return embed

    @discord.ui.button(emoji=constants.PICKAXE_EMOJI, style=discord.ButtonStyle.success)
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mine rock"""
        if not self.cog.db_active():
            return await interaction.response.send_message("Database is not active.", ephemeral=True)
        if self.finalizing:
            return await interaction.response.send_message("This mining event is being finalized!", ephemeral=True)

        with suppress(discord.HTTPException):
            await interaction.response.defer()

        tool_name = await self.cog.db_utils.get_cached_player_tool(interaction.user)

        fake_msg = SimpleNamespace(author=SimpleNamespace(id=interaction.user.id))
        bucket = self.mine_cooldown.get_bucket(fake_msg)
        if bucket.update_rate_limit():
            self.overswings[interaction.user.id] += 1
            txt = f"🤕{interaction.user.name} slipped and fell from swinging too fast!"
            if tool_name == "wood":
                self.action_window.append(txt)
                return

            player = await self.cog.db_utils.get_create_player(interaction.user)
            current_tool = constants.TOOLS[player.tool]
            downgraded_tool = constants.TOOLS[constants.TOOL_ORDER[constants.TOOL_ORDER.index(player.tool) - 1]]
            shatter_txt = f"You swing too hastily at the {self.rocktype.display_name} and your {current_tool.display_name} shatters!"
            max_durability = current_tool.max_durability or 0
            dura_ratio = (player.durability / max_durability) if max_durability else None
            allow_catastrophic = dura_ratio is None or dura_ratio <= constants.OVERSWING_SHATTER_DURA_THRESHOLD
            # Player is swinging too fast so we're going to deduct from their durability
            # Tool break sets them back to previous tool tier
            overswing_roll = random.uniform(0.0, 1.0)
            # Apply tool shatter resistance to overswing shatter chance
            shatter_chance = self.overswing_break_chance * (1 - current_tool.shatter_resistance)
            resisted_catastrophic = (
                allow_catastrophic
                and current_tool.shatter_resistance > 0
                and shatter_chance <= overswing_roll < self.overswing_break_chance
            )
            if allow_catastrophic and overswing_roll < shatter_chance:
                # Players tool shattered!
                txt = f"‼️{interaction.user.name} shattered their {current_tool.display_name}!"
                self.action_window.append(txt)
                await interaction.followup.send(shatter_txt, ephemeral=True)
                kwargs = {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability or 0}
                await player.update_self(kwargs)
                self.shattered_users.add(interaction.user.id)
                await self._set_shatter_recovery_stage(interaction.user.id, 1)
                self.cog.reset_durability_warnings(player.id)
                # Clear the tool_name cache since they broke their tool
                await self.cog.db_utils.get_cached_player_tool.cache.delete(f"miner_player_tool:{player.id}")  # type: ignore
                return
            elif overswing_roll < self.overswing_damage_chance:
                new_durability = max(0, player.durability - self.rocktype.overswing_damage)
                actual_damage_dealt = self.rocktype.overswing_damage if new_durability else player.durability
                txt = f"⚠️{interaction.user.name} did {actual_damage_dealt} damage to their pickaxe swinging too hastily"
                txt += "!" if new_durability else f" and their {current_tool.display_name} broke!"
                if not new_durability:
                    # Tool was shattered
                    await interaction.followup.send(shatter_txt, ephemeral=True)
                    kwargs = {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability or 0}
                    await player.update_self(kwargs)
                    self.shattered_users.add(interaction.user.id)
                    await self._set_shatter_recovery_stage(interaction.user.id, 1)
                    self.cog.reset_durability_warnings(player.id)

                    # Clear the tool_name cache since they broke their tool
                    await self.cog.db_utils.get_cached_player_tool.cache.delete(f"miner_player_tool:{player.id}")  # type: ignore
                    return

                await player.update_self({Player.durability: new_durability})
                await self._maybe_send_durability_warning(
                    interaction,
                    player.id,
                    current_tool,
                    new_durability,
                    max_durability,
                )
            elif resisted_catastrophic:
                self.shatter_resist_survivors.add(interaction.user.id)
            self.action_window.append(txt)
            return

        async with self._mine_lock:
            if self.finalizing:
                return
            tool = constants.TOOLS[tool_name]
            power = tool.power
            crit = False
            if random.random() < tool.crit_chance:
                power = round(power * tool.crit_multiplier)
                crit = True
                self.crit_hits[interaction.user.id] += 1
            damage_dealt = power if power <= self.current_hp else self.current_hp
            txt = ("💥CRITICAL HIT! " if crit else "") + f"{interaction.user.name}: +{damage_dealt} damage!"
            self.action_window.append(txt)
            low_hp_threshold = self.max_hp * constants.PARTY_FINISHER_HP_THRESHOLD
            if self.current_hp <= low_hp_threshold:
                self.low_hp_damage[interaction.user.id] += damage_dealt
            self.current_hp -= damage_dealt
            self.participants[interaction.user.id] += damage_dealt
            self.hits[interaction.user.id] += 1
            if self.current_hp <= 0:
                if self.ttl_task:
                    self.ttl_task.cancel()
                return await self.finalize()

        await self.maybe_update_message()

    async def maybe_update_message(self):
        if not self.message:
            return
        if self.finalizing:
            return
        bucket = self.msg_update_cooldown.get_bucket(self.message)
        if bucket.update_rate_limit():
            # Update the "per" dynamically based on participants
            bucket.per = 1 + (len(self.participants) - 1) * 0.5
            return
        await self.message.edit(embed=self.embed(), view=self)

    @discord.ui.button(emoji=constants.INSPECT_EMOJI, style=discord.ButtonStyle.primary)
    async def inspect(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Inspect rock"""
        if not self.cog.db_active():
            return await interaction.response.send_message("Database is not active.", ephemeral=True)
        embed = discord.Embed(title="Rock Inspection")
        embed.add_field(name="Current HP", value=f"`{self.current_hp}` / `{self.max_hp}`", inline=False)
        collapse_loot = [f"• {k.title()}: {v}" for k, v in self.floor_loot.items()]
        embed.add_field(name="Collapse Yield", value=box("\n".join(collapse_loot) or "None", lang="py"))
        full_loot = [f"• {k.title()}: {v}" for k, v in self.total_loot.items()]
        embed.add_field(name="Depletion Yield", value=box("\n".join(full_loot) or "None", lang="py"))
        volatility = (
            f"• Shatter chance: {self.overswing_break_chance * 100:.0f}%\n"
            f"• Damage chance: {self.overswing_damage_chance * 100:.0f}%"
        )
        embed.add_field(name="Volatility", value=box(volatility, lang="py"))

        # Add modifier info if present
        if self.modifiers:
            mod_text = "\n".join([f"{mod.emoji} **{mod.display_name}**: {mod.description}" for mod in self.modifiers])
            embed.add_field(name="Rock Modifiers", value=mod_text, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def finalize(self):
        if self.finalizing:
            return
        self.finalizing = True

        self.mine.disabled = True
        self.mine.style = discord.ButtonStyle.secondary
        self.inspect.disabled = True
        self.inspect.style = discord.ButtonStyle.secondary
        self.stop()

        if self.participants:
            players = await Player.objects().where(Player.id.is_in(list(self.participants.keys())))
            mapped_players: dict[int, Player] = {p.id: p for p in players}
        else:
            mapped_players = {}

        buffer = StringIO()
        # {user_id: {resource: amount}}
        payouts, performance_scores, performance_bonus_pct, synergy_context = self._compute_payouts()
        if payouts:
            ledgers: list[ResourceLedger] = []
            sorted_participants = sorted(self.participants.items(), key=lambda x: x[1], reverse=True)
            for uid, dmg in sorted_participants:
                payout = payouts.get(uid, {})
                if not payout:
                    continue
                update_kwargs = {}
                lines: list[str] = []
                for resource, to_add in payout.items():
                    if to_add <= 0:
                        continue
                    column = getattr(Player, resource)
                    update_kwargs[column] = column + to_add
                    emoji = constants.resource_emoji(resource)
                    lines.append(f"+`{to_add}` {emoji}")
                    ledgers.append(
                        ResourceLedger(
                            player=uid,
                            resource=resource,
                            amount=to_add,
                        )
                    )

                if update_kwargs:
                    hits = self.hits[uid]
                    overswings = self.overswings.get(uid, 0)
                    score = performance_scores.get(uid, 0)
                    bonus_pct = performance_bonus_pct.get(uid, 0.0)
                    loot = " ".join(lines)
                    buffer.write(f"-# <@{uid}> dealt `{round(dmg)}` damage in `{hits}` hits\n")
                    buffer.write(f"-# Yield: {loot}\n")
                    buffer.write(
                        f"-# Performance: `{score}` | overswings `{overswings}` | bonus `+{bonus_pct * 100:.0f}%`\n"
                    )

                    player: Player = mapped_players[uid]
                    if player.tool != "wood":
                        current_tool = constants.TOOLS[player.tool]
                        downgraded_tool = constants.TOOLS[
                            constants.TOOL_ORDER[constants.TOOL_ORDER.index(player.tool) - 1]
                        ]
                        dura_deduction = max(1, hits // constants.HITS_PER_DURA_LOST)
                        if uid in synergy_context["durability_bonus_participants"]:
                            dura_deduction = max(1, dura_deduction - synergy_context["durability_discount"])
                        new_durability = max(0, player.durability - dura_deduction)
                        if new_durability:
                            buffer.write(
                                f"-# -`{dura_deduction}` durability to {current_tool.display_name} (now `{new_durability}`)\n"
                            )
                            update_kwargs[Player.durability] = new_durability
                            warning_note = self._durability_warning_note(player.id, current_tool, new_durability)
                            if warning_note:
                                buffer.write(f"-# {warning_note}\n")
                        else:
                            buffer.write(
                                f"-# ‼️{player.tool.title()} broke due to overuse, downgraded to {downgraded_tool.display_name}\n"
                            )
                            update_kwargs[Player.tool] = downgraded_tool.key
                            update_kwargs[Player.durability] = downgraded_tool.max_durability or 0
                            self.cog.reset_durability_warnings(player.id)
                    await player.update_self(update_kwargs)

            if ledgers:
                await ResourceLedger.insert(*ledgers)

        if mapped_players:
            await self._finalize_achievements(mapped_players, performance_scores, synergy_context)

        embed = self.embed()
        collapsed = self.current_hp > 0
        outcome = "Collapsed" if collapsed else "Depleted"
        modifier_summary = ", ".join(mod.display_name for mod in self.modifiers) if self.modifiers else "None"
        summary_lines = [
            f"-# Outcome: `{outcome}`",
            f"-# Miners: `{len(self.participants)}`",
            f"-# Modifiers: `{modifier_summary}`",
        ]
        embed.add_field(name="Summary", value="\n".join(summary_lines), inline=False)
        embed.set_footer(text='Run the "miner repair" command to repair your tools.')

        if buffer.getvalue():
            chunks = list(pagify(buffer.getvalue(), page_length=1000))
            for chunk in chunks:
                name = "Yield" if len(chunks) == 1 else "Yield (Continued)"
                embed.add_field(name=name, value=chunk)

        await self.message.edit(embed=embed, view=self)

    async def _finalize_achievements(
        self,
        mapped_players: dict[int, Player],
        performance_scores: dict[int, int],
        synergy_context: dict[str, t.Any],
    ) -> None:
        duration_seconds = max(0.0, perf_counter() - self.started_at_perf)
        participant_count = len(self.participants)
        depleted = self.current_hp <= 0
        role_by_user = {uid: role_name for role_name, uid in synergy_context.get("roles", [])}

        for uid in mapped_players:
            live_keys = await self._update_stats_and_collect_achievement_keys(
                uid=uid,
                performance_scores=performance_scores,
                role_by_user=role_by_user,
                participant_count=participant_count,
                duration_seconds=duration_seconds,
                depleted=depleted,
                full_synergy=len(synergy_context.get("roles", [])) >= 3,
            )
            exact_unlocks = await self.cog.sync_player_achievements(uid)
            live_unlocks = await self.cog.unlock_player_achievements(uid, live_keys)
            combined = achievements.dedupe_achievement_defs([*exact_unlocks, *live_unlocks])
            if combined and self.message:
                await self.cog.announce_achievement_unlocks(self.message.channel, uid, combined)

    async def _update_stats_and_collect_achievement_keys(
        self,
        uid: int,
        performance_scores: dict[int, int],
        role_by_user: dict[int, str],
        participant_count: int,
        duration_seconds: float,
        depleted: bool,
        full_synergy: bool,
    ) -> list[str]:
        stats = await self.cog.get_player_achievement_stats(uid)
        keys: list[str] = []

        overswings = self.overswings.get(uid, 0)
        score = performance_scores.get(uid, 0)
        crit_hits = self.crit_hits.get(uid, 0)
        role_name = role_by_user.get(uid)
        shatter_recovery_stage = int(stats.shatter_recovery_stage or 0)

        rocks_mined_total = (stats.rocks_mined_total or 0) + 1
        group_sessions_total = (stats.group_sessions_total or 0) + (1 if participant_count >= 2 else 0)
        modifier_rocks_total = (stats.modifier_rocks_mined_total or 0) + (1 if self.modifiers else 0)
        rock_variety_seen = {
            "small": bool(stats.mined_small) or self.rocktype.key == "small",
            "medium": bool(stats.mined_medium) or self.rocktype.key == "medium",
            "large": bool(stats.mined_large) or self.rocktype.key == "large",
            "meteor": bool(stats.mined_meteor) or self.rocktype.key == "meteor",
            "volatile geode": bool(stats.mined_geode) or self.rocktype.key == "volatile geode",
        }

        clean_streak_current = (stats.clean_streak_current or 0) + 1 if overswings == 0 else 0
        clean_streak_best = max(stats.clean_streak_best or 0, clean_streak_current)

        perf_max_streak_current = (
            (stats.perf_max_streak_current or 0) + 1 if score >= achievements.PERFORMANCE_MAX_THRESHOLD else 0
        )
        perf_max_streak_best = max(stats.perf_max_streak_best or 0, perf_max_streak_current)

        role_breaker_total = (stats.role_breaker_total or 0) + (1 if role_name == "Breaker" else 0)
        role_stabilizer_total = (stats.role_stabilizer_total or 0) + (1 if role_name == "Stabilizer" else 0)
        role_finisher_total = (stats.role_finisher_total or 0) + (1 if role_name == "Finisher" else 0)

        update_kwargs: dict[t.Any, t.Any] = {
            PlayerAchievementStats.rocks_mined_total: rocks_mined_total,
            PlayerAchievementStats.group_sessions_total: group_sessions_total,
            PlayerAchievementStats.modifier_rocks_mined_total: modifier_rocks_total,
            PlayerAchievementStats.mined_small: rock_variety_seen["small"],
            PlayerAchievementStats.mined_medium: rock_variety_seen["medium"],
            PlayerAchievementStats.mined_large: rock_variety_seen["large"],
            PlayerAchievementStats.mined_meteor: rock_variety_seen["meteor"],
            PlayerAchievementStats.mined_geode: rock_variety_seen["volatile geode"],
            PlayerAchievementStats.clean_streak_current: clean_streak_current,
            PlayerAchievementStats.clean_streak_best: clean_streak_best,
            PlayerAchievementStats.perf_max_streak_current: perf_max_streak_current,
            PlayerAchievementStats.perf_max_streak_best: perf_max_streak_best,
            PlayerAchievementStats.role_breaker_total: role_breaker_total,
            PlayerAchievementStats.role_stabilizer_total: role_stabilizer_total,
            PlayerAchievementStats.role_finisher_total: role_finisher_total,
        }
        if shatter_recovery_stage and uid not in self.shattered_users:
            update_kwargs[PlayerAchievementStats.shatter_recovery_stage] = 0

        if depleted and participant_count == 1:
            solo_columns = {
                "small": (PlayerAchievementStats.best_solo_small_seconds, stats.best_solo_small_seconds or 0.0),
                "medium": (PlayerAchievementStats.best_solo_medium_seconds, stats.best_solo_medium_seconds or 0.0),
                "large": (PlayerAchievementStats.best_solo_large_seconds, stats.best_solo_large_seconds or 0.0),
                "meteor": (PlayerAchievementStats.best_solo_meteor_seconds, stats.best_solo_meteor_seconds or 0.0),
                "volatile geode": (
                    PlayerAchievementStats.best_solo_geode_seconds,
                    stats.best_solo_geode_seconds or 0.0,
                ),
            }
            solo_column, current_best = solo_columns[self.rocktype.key]
            if current_best <= 0 or duration_seconds < current_best:
                update_kwargs[solo_column] = duration_seconds

        await stats.update_self(update_kwargs)

        for threshold, key in achievements.CLEAN_STREAK_THRESHOLDS:
            if clean_streak_current >= threshold:
                keys.append(key)

        if depleted and participant_count == 1:
            solo_key, solo_limit = achievements.SOLO_SPEED_THRESHOLDS[self.rocktype.key]
            if duration_seconds <= solo_limit:
                keys.append(solo_key)

        if score >= achievements.PERFORMANCE_ANY_THRESHOLD:
            keys.append("perf_any_bonus")
        if score >= achievements.PERFORMANCE_MAX_THRESHOLD:
            keys.append("perf_max_any")
            if self.rocktype.key == "meteor":
                keys.append("perf_max_meteor")
            elif self.rocktype.key == "volatile geode":
                keys.append("perf_max_geode")
            if depleted and overswings == 0:
                keys.append("clean_and_perf_max")
        if perf_max_streak_current >= 3:
            keys.append("perf_max_streak_3")

        if crit_hits > 0:
            keys.append("crit_first")
        if crit_hits >= 5:
            keys.append("crit_five_single_rock")

        for modifier in self.modifiers:
            modifier_key = achievements.MODIFIER_ACHIEVEMENT_KEYS.get(modifier.key)
            if modifier_key:
                keys.append(modifier_key)
        if len(self.modifiers) >= 2:
            keys.append("modifier_double")
        if modifier_rocks_total >= 50:
            keys.append("modifier_total_50")

        if participant_count >= 3:
            keys.append("party_three_players")
        if role_name == "Breaker":
            keys.append("party_role_breaker")
        elif role_name == "Stabilizer":
            keys.append("party_role_stabilizer")
        elif role_name == "Finisher":
            keys.append("party_role_finisher")
        if full_synergy:
            keys.append("party_full_synergy")
        if group_sessions_total >= 25:
            keys.append("party_group_sessions_25")
        if role_breaker_total > 0 and role_stabilizer_total > 0 and role_finisher_total > 0:
            keys.append("party_all_roles")

        for threshold, key in achievements.ROCK_COUNT_THRESHOLDS:
            if rocks_mined_total >= threshold:
                keys.append(key)
        if all(rock_variety_seen.values()):
            keys.append("rock_variety_all")

        if self.rocktype.key == "meteor":
            keys.append("rare_first_meteor")
        elif self.rocktype.key == "volatile geode":
            keys.append("rare_first_geode")

        if uid in self.shatter_resist_survivors:
            keys.append("tool_shatter_survived")
        if shatter_recovery_stage and uid not in self.shattered_users:
            keys.append("tool_shatter_comeback")

        return keys

    async def _set_shatter_recovery_stage(self, user_id: int, stage: int) -> None:
        stats = await self.cog.get_player_achievement_stats(user_id)
        await stats.update_self({PlayerAchievementStats.shatter_recovery_stage: stage})

    def _compute_payouts(
        self,
    ) -> tuple[
        dict[int, dict[constants.Resource, int]],
        dict[int, int],
        dict[int, float],
        dict[str, t.Any],
    ]:
        """Evenly distribute loot pool among participants"""
        # Select pool: collapse -> floor_loot pool; depletion -> total_loot pool
        collapsed = self.current_hp > 0
        pool = self.floor_loot if collapsed else self.total_loot
        valid_participants = {k: v for k, v in self.participants.items() if v > 0}
        sorted_participants: list[tuple[int, int]] = sorted(
            valid_participants.items(), key=lambda x: x[1], reverse=True
        )
        total_damage = sum(d for __, d in sorted_participants)

        # {user_id: {resource: amount}}
        payouts: dict[int, dict[constants.Resource, int]] = defaultdict(lambda: defaultdict(int))
        performance_scores: dict[int, int] = {}
        performance_bonus_pct: dict[int, float] = {}
        synergy_context = self.compute_party_synergy_context(sorted_participants, total_damage)

        for uid, dmg in sorted_participants:
            hits = self.hits.get(uid, 0)
            overswings = self.overswings.get(uid, 0)
            total_swings = hits + overswings

            damage_ratio = (dmg / total_damage) if total_damage else 0.0
            control_ratio = (hits / total_swings) if total_swings else 1.0
            activity_ratio = min(1.0, hits / constants.PERFORMANCE_HIT_TARGET)

            score = round(
                (damage_ratio * constants.PERFORMANCE_DAMAGE_SCORE_MAX)
                + (control_ratio * constants.PERFORMANCE_CONTROL_SCORE_MAX)
                + (activity_ratio * constants.PERFORMANCE_ACTIVITY_SCORE_MAX)
            )
            performance_scores[uid] = score

            bonus_pct = 0.0
            for threshold, pct in constants.PERFORMANCE_BONUS_TIERS:
                if score >= threshold:
                    bonus_pct = pct
                    break
            performance_bonus_pct[uid] = bonus_pct

        for resource, total_amount in pool.items():
            assigned_sum = 0  # How much to award the user

            # [(uid, remainder)]
            remainders: list[tuple[int, int]] = []

            for uid, dmg in sorted_participants:
                exact = (total_amount * dmg) / total_damage if total_damage else 0
                base = int(exact)  # Round down
                assigned_sum += base
                payouts[uid][resource] = base

                if base < exact:
                    # If there is a remainder, store it for later
                    remainders.append((uid, exact - base))

            # Now we want to see if there is any leftover and give it to whoever didn't get any
            leftover = total_amount - assigned_sum
            if leftover > 0:
                # Hand +1 to whoever had the highest remainders
                remainders.sort(key=lambda x: x[1], reverse=True)
                for uid, __ in remainders:
                    if leftover <= 0:
                        break
                    payouts[uid][resource] += 1
                    leftover -= 1

            for uid, __ in sorted_participants:
                base_amount = payouts[uid][resource]
                if base_amount <= 0:
                    continue
                bonus_pct = performance_bonus_pct.get(uid, 0.0)
                if resource == "gems":
                    bonus_pct = min(bonus_pct, constants.PERFORMANCE_GEM_BONUS_CAP)
                bonus_amount = int(base_amount * bonus_pct)
                if bonus_amount > 0:
                    payouts[uid][resource] += bonus_amount

                if resource in ("stone", "iron") and uid in synergy_context["bonus_participants"]:
                    synergy_bonus = int(base_amount * synergy_context["loot_bonus_pct"])
                    if synergy_bonus > 0:
                        payouts[uid][resource] += synergy_bonus

        return payouts, performance_scores, performance_bonus_pct, synergy_context

    def compute_party_synergy_context(
        self,
        sorted_participants: list[tuple[int, int]] | None = None,
        total_damage: int | None = None,
    ) -> dict[str, t.Any]:
        if sorted_participants is None:
            sorted_participants = sorted(self.participants.items(), key=lambda item: item[1], reverse=True)
        if total_damage is None:
            total_damage = sum(damage for __, damage in sorted_participants)

        eligible: list[int] = []
        for uid, damage in sorted_participants:
            hits = self.hits.get(uid, 0)
            damage_share = (damage / total_damage) if total_damage else 0.0
            if hits >= constants.PARTY_SYNERGY_MIN_HITS and damage_share >= constants.PARTY_SYNERGY_MIN_DAMAGE_SHARE:
                eligible.append(uid)

        if len(eligible) < 2:
            return {
                "active": False,
                "roles": [],
                "eligible_participants": eligible,
                "bonus_participants": set(),
                "durability_bonus_participants": set(),
                "loot_bonus_pct": 0.0,
                "durability_discount": 0,
            }

        roles: list[tuple[str, int]] = []
        used: set[int] = set()

        for uid, damage in sorted_participants:
            damage_share = (damage / total_damage) if total_damage else 0.0
            if uid in eligible and damage_share >= constants.PARTY_BREAKER_MIN_DAMAGE_SHARE:
                roles.append(("Breaker", uid))
                used.add(uid)
                break

        stabilizer_candidates = sorted(
            eligible,
            key=lambda uid: (
                self.overswings.get(uid, 0),
                -(self.hits.get(uid, 0)),
                -(self.participants.get(uid, 0)),
            ),
        )
        for uid in stabilizer_candidates:
            if uid in used:
                continue
            hits = self.hits.get(uid, 0)
            overswings = self.overswings.get(uid, 0)
            total_swings = hits + overswings
            overswing_rate = (overswings / total_swings) if total_swings else 0.0
            if overswing_rate <= constants.PARTY_STABILIZER_MAX_OVERSWING_RATE:
                roles.append(("Stabilizer", uid))
                used.add(uid)
                break

        total_low_hp_damage = sum(self.low_hp_damage.values())
        finisher_candidates = sorted(eligible, key=lambda uid: self.low_hp_damage.get(uid, 0), reverse=True)
        for uid in finisher_candidates:
            if uid in used:
                continue
            low_hp_damage = self.low_hp_damage.get(uid, 0)
            low_hp_share = (low_hp_damage / total_low_hp_damage) if total_low_hp_damage else 0.0
            if low_hp_damage and low_hp_share >= constants.PARTY_FINISHER_MIN_DAMAGE_SHARE:
                roles.append(("Finisher", uid))
                used.add(uid)
                break

        loot_bonus_pct = 0.0
        durability_discount = 0
        if len(roles) >= 3:
            loot_bonus_pct = constants.PARTY_SYNERGY_THREE_ROLE_LOOT_BONUS
            durability_discount = constants.PARTY_SYNERGY_DURABILITY_DISCOUNT
        elif len(roles) >= 2:
            loot_bonus_pct = constants.PARTY_SYNERGY_TWO_ROLE_LOOT_BONUS
            durability_discount = constants.PARTY_SYNERGY_DURABILITY_DISCOUNT

        role_holders = {uid for __, uid in roles}

        return {
            "active": len(roles) >= 2,
            "roles": roles,
            "eligible_participants": eligible,
            "bonus_participants": set(eligible),
            "durability_bonus_participants": role_holders,
            "loot_bonus_pct": loot_bonus_pct,
            "durability_discount": durability_discount,
        }

    def format_party_synergy_field(self, synergy_context: dict[str, t.Any]) -> str:
        if not synergy_context["roles"]:
            return "-# Forming crew bonus... mix damage, control, and finisher play styles."

        role_labels = [name for name, __ in synergy_context["roles"]]
        lines = [f"-# Roles: {' + '.join(role_labels)}"]
        if synergy_context["active"]:
            lines.append(f"-# Stone/Iron bonus: `+{synergy_context['loot_bonus_pct'] * 100:.0f}%`")
            lines.append(f"-# Durability savings: `-{synergy_context['durability_discount']}`")
        else:
            lines.append("-# Need one more distinct role to activate.")
        return "\n".join(lines)

    async def _maybe_send_durability_warning(
        self,
        interaction: discord.Interaction,
        player_id: int,
        tool: constants.ToolTier,
        durability: int,
        max_durability: int | None,
    ) -> None:
        if not isinstance(max_durability, int) or max_durability <= 0:
            return
        ratio = durability / max_durability
        threshold = self.cog.register_durability_ratio(player_id, ratio)
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

    def _durability_warning_note(
        self,
        player_id: int,
        tool: constants.ToolTier,
        durability: int,
    ) -> str | None:
        max_durability = tool.max_durability
        if not isinstance(max_durability, int) or max_durability <= 0:
            return None
        ratio = durability / max_durability
        threshold = self.cog.register_durability_ratio(player_id, ratio)
        if threshold is None:
            return None
        critical = min(constants.DURABILITY_WARNING_THRESHOLDS or (0.1,))
        if threshold <= critical:
            return f"⚠️ {tool.display_name} is critically low on durability ({durability}/{max_durability})."
        return f"⚠️ {tool.display_name} durability is running low ({durability}/{max_durability})."
