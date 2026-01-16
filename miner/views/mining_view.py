from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict, deque
from contextlib import suppress
from datetime import datetime, timedelta
from io import StringIO
from types import SimpleNamespace

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import Player, ResourceLedger

log = logging.getLogger("red.vrt.miner.views.mining_view")


def hp_bar(hp: int, max_hp: int) -> str:
    if max_hp <= 0:
        return f"{constants.HP_BAR_EMPTY * constants.HP_BAR_SEGMENTS} 0.0%"
    ratio = hp / max_hp
    width: int = constants.HP_BAR_SEGMENTS
    bar = constants.HP_BAR_FILLED * round(ratio * width) + constants.HP_BAR_EMPTY * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


class RockView(discord.ui.View):
    def __init__(self, cog: MixinMeta, rocktype: constants.RockType):
        super().__init__(timeout=None)
        self.cog = cog
        self.rocktype: constants.RockType = rocktype

        self.current_hp = rocktype.hp

        self.total_loot = rocktype.total_loot
        self.floor_loot = rocktype.floor_loot

        self.message: discord.Message | None = None

        # user_id -> total damage dealt
        self.participants: dict[int, int] = defaultdict(int)
        self.hits: dict[int, int] = defaultdict(int)
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
        decrement = int((255 / self.rocktype.hp) * self.current_hp)
        green = blue = decrement
        return discord.Color.from_rgb(255, green, blue)

    def embed(self):
        embed = discord.Embed(title=self.rocktype.display_name, color=self.color())

        if not self.current_hp:
            embed.set_thumbnail(url=constants.DEPLETED_ROCK_URL)
            embed.description = "The rock has been completely mined!"
        elif datetime.now() < self.end_time:
            embed.set_image(url=self.rocktype.image_url)
            ts = round(self.end_time.timestamp())
            embed.description = f"Mineshaft is unstable and will collapse <t:{ts}:R>"
            embed.add_field(name="HP", value=box(hp_bar(self.current_hp, self.rocktype.hp), lang="py"))
        else:
            embed.set_image(url=constants.COLLAPSED_MINESHAFT_URL)
            embed.description = "Mineshaft has collapsed!"
            embed.add_field(name="HP", value=box(hp_bar(self.current_hp, self.rocktype.hp), lang="py"))

        if self.action_window:
            embed.description += "\n\n**Recent Actions:**\n"
            embed.description += box("\n".join([i.strip() for i in self.action_window]))
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
            shatter_chance = self.rocktype.overswing_break_chance * (1 - current_tool.shatter_resistance)
            if allow_catastrophic and overswing_roll < shatter_chance:
                # Players tool shattered!
                txt = f"‼️{interaction.user.name} shattered their {current_tool.display_name}!"
                self.action_window.append(txt)
                await interaction.followup.send(shatter_txt, ephemeral=True)
                kwargs = {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability or 0}
                await player.update_self(kwargs)
                self.cog.reset_durability_warnings(player.id)
                # Clear the tool_name cache since they broke their tool
                await self.cog.db_utils.get_cached_player_tool.cache.delete(f"miner_player_tool:{player.id}")  # type: ignore
                return
            elif overswing_roll < self.rocktype.overswing_damage_chance:
                new_durability = max(0, player.durability - self.rocktype.overswing_damage)
                actual_damage_dealt = self.rocktype.overswing_damage if new_durability else player.durability
                txt = f"⚠️{interaction.user.name} did {actual_damage_dealt} damage to their pickaxe swinging too hastily"
                txt += "!" if new_durability else f" and their {current_tool.display_name} broke!"
                if not new_durability:
                    # Tool was shattered
                    await interaction.followup.send(shatter_txt, ephemeral=True)
                    kwargs = {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability or 0}
                    await player.update_self(kwargs)
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
            damage_dealt = power if power <= self.current_hp else self.current_hp
            txt = ("💥CRITICAL HIT! " if crit else "") + f"{interaction.user.name}: +{damage_dealt} damage!"
            self.action_window.append(txt)
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
        embed.add_field(name="Current HP", value=f"`{self.current_hp}`", inline=False)
        collapse_loot = [f"• {k.title()}: {v}" for k, v in self.floor_loot.items()]
        embed.add_field(name="Collapse Yield", value=box("\n".join(collapse_loot) or "None", lang="py"))
        full_loot = [f"• {k.title()}: {v}" for k, v in self.total_loot.items()]
        embed.add_field(name="Depletion Yield", value=box("\n".join(full_loot) or "None", lang="py"))
        volatility = f"• {self.rocktype.overswing_break_chance * 100:.0f}%"
        embed.add_field(name="Volatility", value=box(volatility, lang="py"))
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
        payouts: dict[int, dict[constants.Resource, int]] = self._compute_payouts()
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
                    loot = " ".join(lines)
                    buffer.write(f"<@{uid}> dealt `{round(dmg)}` damage in `{hits}` hits:\n{loot}\n")

                    player: Player = mapped_players[uid]
                    if player.tool != "wood":
                        current_tool = constants.TOOLS[player.tool]
                        downgraded_tool = constants.TOOLS[
                            constants.TOOL_ORDER[constants.TOOL_ORDER.index(player.tool) - 1]
                        ]
                        dura_deduction = max(1, hits // constants.HITS_PER_DURA_LOST)
                        new_durability = max(0, player.durability - dura_deduction)
                        if new_durability:
                            buffer.write(
                                f"-`{dura_deduction}` durability to {current_tool.display_name} (now `{new_durability}`)\n"
                            )
                            update_kwargs[Player.durability] = new_durability
                            warning_note = self._durability_warning_note(player.id, current_tool, new_durability)
                            if warning_note:
                                buffer.write(f"{warning_note}\n")
                        else:
                            buffer.write(
                                f"‼️{player.tool.title()} broke due to overuse, downgraded to {downgraded_tool.display_name}\n"
                            )
                            update_kwargs[Player.tool] = downgraded_tool.key
                            update_kwargs[Player.durability] = downgraded_tool.max_durability or 0
                            self.cog.reset_durability_warnings(player.id)
                    await player.update_self(update_kwargs)

            if ledgers:
                await ResourceLedger.insert(*ledgers)

        embed = self.embed()
        embed.set_footer(text='Run the "miner repair" command to repair your tools.')

        if buffer.getvalue():
            chunks = list(pagify(buffer.getvalue(), page_length=1000))
            for chunk in chunks:
                name = "Yield" if len(chunks) == 1 else "Yield (Continued)"
                embed.add_field(name=name, value=chunk)

        await self.message.edit(embed=embed, view=self)

    def _compute_payouts(self) -> dict[int, dict[constants.Resource, int]]:
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

        return payouts

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
