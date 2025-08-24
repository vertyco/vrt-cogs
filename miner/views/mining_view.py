from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict, deque
from contextlib import suppress
from copy import copy
from datetime import datetime, timedelta
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import Player

log = logging.getLogger("red.vrt.miner.views.mining_view")


def hp_bar(hp: int, max_hp: int) -> str:
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
            1, constants.OVERSWING_THRESHOLD_SECONDS, commands.BucketType.user
        )

        # Respect discord rate limits, forcing a lower update frequency than documented by 1
        self.msg_update_cooldown = commands.CooldownMapping.from_cooldown(1, 2, commands.BucketType.user)

        self.end_time: datetime | None = None
        self.ttl_task: asyncio.Task | None = None

        self.action_window: deque[str] = deque(maxlen=10)
        self.finalizing: bool = False

        self._mine_lock = asyncio.Lock()

    async def start(self, channel: discord.TextChannel):
        """Start the rock session"""
        self.end_time = datetime.now() + timedelta(seconds=constants.ROCK_TTL_SECONDS)
        self.message = await channel.send(embed=self.embed(), view=self)
        self.ttl_task = asyncio.create_task(self.ttl())

    async def ttl(self):
        try:
            await asyncio.sleep(constants.ROCK_TTL_SECONDS)
            if self.finalizing:
                return
            log.info(f"Mine has collapsed in {self.message.channel}!")
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

        async with self._mine_lock:
            if self.finalizing:
                return
            fake_msg = copy(interaction.message)
            fake_msg.author = interaction.user
            bucket = self.mine_cooldown.get_bucket(fake_msg)
            player: Player = await Player.objects().get_or_create(
                (Player.id == interaction.user.id), defaults={Player.id: interaction.user.id}
            )

            if bucket.update_rate_limit():
                txt = f"🤕{interaction.user.name} slipped and fell from swinging too fast!"
                if player.tool == "wood":
                    self.action_window.append(txt)
                    return

                current_tool = constants.TOOLS[player.tool]
                downgraded_tool = constants.TOOLS[constants.TOOL_ORDER[constants.TOOL_ORDER.index(player.tool) - 1]]
                shatter_txt = f"You swing too hastily at the {self.rocktype.display_name} and your {current_tool.display_name} shatters!"

                # Player is swinging too fast so we're going to deduct from their durability
                # Tool break sets them back to previous tool tier
                if random.random() < self.rocktype.overswing_break_chance:
                    # Players tool shattered!
                    txt = f"‼️{interaction.user.name} shattered their {current_tool.display_name}!"
                    self.action_window.append(txt)
                    await interaction.followup.send(shatter_txt, ephemeral=True)
                    await player.update_self(
                        {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability}
                    )
                    return
                elif random.random() < self.rocktype.overswing_damage_chance:
                    new_durability = max(0, player.durability - self.rocktype.overswing_damage)
                    actual_damage_dealt = self.rocktype.overswing_damage if new_durability else player.durability
                    txt = f"⚠️{interaction.user.name} did {actual_damage_dealt} to their pickaxe swinging too hastily"
                    txt += "!" if new_durability else f" and their {current_tool.display_name} broke!"
                    if new_durability:
                        await player.update_self({Player.durability: new_durability})
                    else:
                        await interaction.followup.send(shatter_txt, ephemeral=True)
                        await player.update_self(
                            {Player.tool: downgraded_tool.key, Player.durability: downgraded_tool.max_durability}
                        )

                self.action_window.append(txt)
                return

            tool = constants.TOOLS[player.tool]
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

            bucket = self.msg_update_cooldown.get_bucket(self.message)
            if not bucket.update_rate_limit():
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
        payouts: dict[int, dict[str, int]] = self._compute_payouts()
        if payouts:
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
                if update_kwargs:
                    hits = self.hits[uid]
                    loot = "\n".join(lines)
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
                        else:
                            buffer.write(
                                f"‼️{player.tool.title()} broke due to overuse, downgraded to {downgraded_tool.display_name}\n"
                            )
                            update_kwargs[Player.tool] = downgraded_tool.key
                            update_kwargs[Player.durability] = downgraded_tool.max_durability
                    await player.update_self(update_kwargs)

        if not buffer.getvalue():
            buffer.write("No loot received :(")
        else:
            buffer.write("\n-# Run the `miner repair` command to repair your tools.")
        embed = discord.Embed(
            title=f"Yield From {self.rocktype.display_name}",
            color=discord.Color.green(),
            description=buffer.getvalue(),
        )
        await self.message.channel.send(embed=embed)
        await self.message.edit(embed=self.embed(), view=self)

    def _compute_payouts(self) -> dict[int, dict[str, int]]:
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
        payouts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
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
