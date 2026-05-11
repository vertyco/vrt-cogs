import logging
import math
import typing as t
from time import perf_counter

import discord
from redbot.core import bank, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common import achievements, constants
from ..db.tables import ActiveChannel, GuildSettings, Player, ensure_db_connection
from ..views.dynamic_menu import DynamicMenu
from ..views.leaderboard_menu import LeaderboardView
from ..views.mining_view import RockView
from ..views.trade_panel import TradePanel
from ..views.upgrade_view import UpgradeConfirmView

log = logging.getLogger("red.vrt.miner.commands.user")


class User(MixinMeta):
    @commands.hybrid_group(name="miner", invoke_without_command=True)
    @commands.guild_only()
    async def miner_group(self, ctx: commands.Context):
        """User commands"""
        await ctx.send_help()

    @miner_group.command(name="inventory", aliases=["inv"], description="View your stats.")
    @ensure_db_connection()
    async def miner_inventory(self, ctx: commands.Context, user: t.Optional[discord.User | discord.Member] = None):
        """View your stats."""
        if not user:
            user = ctx.author
        await self.sync_player_achievements(user)
        player = await self.db_utils.get_create_player(user)
        achievement_rows = await self.get_player_achievements(user)
        tool = constants.TOOLS[player.tool]
        # Show current/max durability with percentage (non-wood tools)
        if player.tool != "wood" and isinstance(tool.max_durability, int) and tool.max_durability > 0:
            pct = (player.durability / tool.max_durability) * 100
            dura_str = f"Durability: `{player.durability}` / `{tool.max_durability}` ({pct:.1f}%)"
        else:
            dura_str = ""

        embed = discord.Embed(
            title=f"{user.display_name}'s Inventory",
            color=discord.Color.blurple(),
            description=(
                f"**Current Tool:**\n{tool.display_name} {constants.PICKAXE_EMOJI}\n"
                f"Power: `{tool.power}`\n"
                f"Crit Chance: `{tool.crit_chance * 100:.1f}%`\n"
                f"Crit Multiplier: `x{tool.crit_multiplier:.2f}`\n"
                f"Shatter Resistance: `{tool.shatter_resistance * 100:.1f}%`\n"
                f"{dura_str}"
            ),
        )
        # Inventory
        inv_lines = []
        for resource in constants.RESOURCES:
            amount = getattr(player, resource, 0) or 0
            inv_lines.append(f"{constants.resource_emoji(resource)} {resource.title()}: `{humanize_number(amount)}`")
        embed.add_field(
            name="Inventory", value="\n".join(inv_lines) if inv_lines else "No resources yet.", inline=False
        )

        unlocked_count = len(achievement_rows)
        completion_pct = (
            (unlocked_count / achievements.TOTAL_ACHIEVEMENTS) * 100 if achievements.TOTAL_ACHIEVEMENTS else 0.0
        )
        achievement_lines = [
            f"Unlocked: `{unlocked_count}` / `{achievements.TOTAL_ACHIEVEMENTS}` ({completion_pct:.0f}%)",
        ]
        recent_unlocks = [row for row in achievement_rows if row.key in achievements.ACHIEVEMENTS_BY_KEY][:3]
        if recent_unlocks:
            achievement_lines.append("Recent unlocks:")
            achievement_lines.extend(f"• {achievements.ACHIEVEMENTS_BY_KEY[row.key].name}" for row in recent_unlocks)
        else:
            achievement_lines.append("No achievements unlocked yet.")
        achievement_lines.append(f"Use `{ctx.clean_prefix}miner achievements` to browse the full list.")
        embed.add_field(name="Achievements", value="\n".join(achievement_lines), inline=False)

        # Next upgrade info
        next_idx = constants.TOOL_ORDER.index(player.tool) + 1
        if len(constants.TOOL_ORDER) == next_idx:
            embed.add_field(
                name="Next Upgrade", value=f"You have the best tool! {constants.TROPHY_EMOJI}", inline=False
            )
        else:
            next_tool = constants.TOOLS[constants.TOOL_ORDER[next_idx]]
            txt = (
                f"Power: `{next_tool.power}`\n"
                f"Crit Chance: `{next_tool.crit_chance * 100:.1f}%`\n"
                f"Crit Multiplier: `x{next_tool.crit_multiplier:.2f}`\n"
                f"Shatter Resistance: `{next_tool.shatter_resistance * 100:.1f}%`\n"
                f"Durability: `{next_tool.max_durability}`"
            )
            if next_tool.upgrade_cost:
                txt += "\n**Cost:**\n"
                for resource, amount in next_tool.upgrade_cost.items():
                    txt += f"{constants.resource_emoji(resource)} {resource.title()}: `{amount}`\n"
            embed.add_field(name=f"Next Upgrade: {next_tool.display_name}", value=txt, inline=False)

        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        embed.add_field(
            name="Notifications",
            value=f"Rock Spawn Notifications: `{'Enabled' if player.id in settings.notify_players else 'Disabled'}`\nUse `{ctx.clean_prefix}miner notify` to toggle.",
            inline=False,
        )

        embed.set_thumbnail(url=user.display_avatar)
        await ctx.send(embed=embed)

    @miner_group.command(name="achievements", aliases=["achievement", "achs"], description="Browse Miner achievements.")
    @ensure_db_connection()
    async def miner_achievements(self, ctx: commands.Context, user: t.Optional[discord.User | discord.Member] = None):
        """Browse unlocked and locked achievements."""
        if not user:
            user = ctx.author

        await self.sync_player_achievements(user)
        unlocked_rows = await self.get_player_achievements(user)
        pages = await self.build_achievement_pages(ctx, user, unlocked_rows)
        await DynamicMenu(ctx.author, pages, ctx.channel).refresh()

    @miner_group.command(name="notify", description="Toggle rock spawn notifications.")
    @ensure_db_connection()
    async def miner_notify(self, ctx: commands.Context, enable: t.Optional[bool] = None):
        """Toggle rock spawn notifications."""
        player = await self.db_utils.get_create_player(ctx.author)
        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)

        if enable is not None:
            # In case user specifically wants to enable/disable
            if enable and player.id in settings.notify_players:
                return await ctx.send("Rock spawn notifications are already enabled.", ephemeral=True)
            elif not enable and player.id not in settings.notify_players:
                return await ctx.send("Rock spawn notifications are already disabled.", ephemeral=True)
            if enable:
                settings.notify_players.append(player.id)
            else:
                settings.notify_players.remove(player.id)
        else:
            if player.id in settings.notify_players:
                settings.notify_players.remove(player.id)
            else:
                settings.notify_players.append(player.id)

        await settings.save([GuildSettings.notify_players])
        status = "enabled" if player.id in settings.notify_players else "disabled"
        await ctx.send(f"Rock spawn notifications have been `{status}` for {ctx.author.name}.", ephemeral=True)

    @miner_group.command(name="repair", description="Repair your mining tool for a resource cost.")
    @ensure_db_connection()
    async def miner_repair(self, ctx: commands.Context, confirm: bool = False):
        """Repair your pickaxe."""
        player = await self.db_utils.get_create_player(ctx.author)
        tool = constants.TOOLS[player.tool]
        # Wood tool cannot be repaired
        if player.tool == "wood":
            await ctx.send("The Wooden Pickaxe does not require or support repairs.")
            return
        max_dura = tool.max_durability
        # Guard against None for static type checking and safety
        if not isinstance(max_dura, int):
            await ctx.send("This tool cannot be repaired.")
            return
        if player.durability >= max_dura:
            await ctx.send(f"Your {tool.display_name} is already at full durability! ({max_dura})")
            return

        critical_repair = max_dura > 0 and player.durability > 0 and (player.durability / max_dura) <= 0.10

        # Calculate repair cost dynamically based on missing durability percentage.
        # Base cost scales by tool tier, then by the missing durability ratio.
        missing_ratio = (max_dura - player.durability) / max_dura
        repair_cost = {}
        if tool.upgrade_cost:
            repair_pct = constants.TOOL_REPAIR_COST_PCTS[player.tool]
            for resource, amount in tool.upgrade_cost.items():
                base = amount * repair_pct
                scaled = base * missing_ratio
                cost = int(math.ceil(scaled))
                if cost > 0:
                    repair_cost[resource] = cost
        else:
            await ctx.send("This tool cannot be repaired.")
            return

        cost_str = "\n".join(f"{constants.resource_emoji(k)} {k.title()}: `{v}`" for k, v in repair_cost.items())

        if not confirm:
            embed = discord.Embed(
                title="Repair Tool?",
                description=f"Repairing your {tool.display_name} will restore durability to `{max_dura}`.\n\n**Cost:**\n{cost_str}\n\nTo confirm, run the command again with `true` as the argument.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        # Check if player has enough resources
        missing = []
        for resource, cost in repair_cost.items():
            have = getattr(player, resource, 0) or 0
            if have < cost:
                missing.append(f"`{cost - have}` **{resource.title()}**")
        if missing:
            embed = discord.Embed(
                title="Cannot Repair",
                description=f"You are missing resources to repair your {tool.display_name}.\n\n**Cost:**\n{cost_str}",
                color=discord.Color.red(),
            )
            embed.add_field(name=":warning: Missing Resources", value="\n".join(missing), inline=False)
            await ctx.send(embed=embed)
            return

        # Deduct resources and repair
        update_kwargs = {
            getattr(Player, resource): getattr(Player, resource) - cost for resource, cost in repair_cost.items()
        }
        update_kwargs[Player.durability] = max_dura
        await player.update_self(update_kwargs)
        self.reset_durability_warnings(player.id)

        embed = discord.Embed(
            title="Tool Repaired!",
            description=f"Your {tool.display_name} has been fully repaired!\nDurability: `{max_dura}`\n\n**Cost:**\n{cost_str}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
        unlocked = await self.sync_player_achievements(ctx.author)
        if critical_repair:
            unlocked.extend(
                await self.unlock_player_achievements(
                    ctx.author,
                    ["tool_repaired_from_critical"],
                )
            )
        if unlocked:
            await self.announce_achievement_unlocks(ctx.channel, ctx.author, unlocked)

    @miner_group.command(name="trade", description="Trade with another miner")
    @ensure_db_connection()
    async def miner_trade(self, ctx: commands.Context, user: discord.User | discord.Member):
        """Trade resources with another miner."""
        if user.bot:
            return await ctx.send("You cannot trade with a bot!", ephemeral=True)

        player = await self.db_utils.get_create_player(ctx.author)
        target = await self.db_utils.get_create_player(user)
        if player.id == target.id:
            return await ctx.send("You cannot trade with yourself!", ephemeral=True)
        mention = user.name if ctx.message.mentions else user.mention
        await ctx.send(f"{mention}, {ctx.author.name} would like to trade with you.")
        view = TradePanel(self.bot, player, target)
        await view.start(ctx.channel)

    @miner_group.command(name="transfer", description="Transfer resources to another miner")
    @ensure_db_connection()
    async def miner_transfer(
        self,
        ctx: commands.Context,
        user: discord.User | discord.Member,
        resource: constants.Resource,
        amount: commands.positive_int,
    ):
        """Transfer resources to another miner."""
        if user.bot:
            return await ctx.send("You cannot transfer resources to a bot!", ephemeral=True)

        player = await self.db_utils.get_create_player(ctx.author)
        target = await self.db_utils.get_create_player(user)

        if player.id == target.id:
            return await ctx.send("You cannot transfer resources to yourself!", ephemeral=True)

        balance = getattr(player, resource, 0) or 0
        if balance < amount:
            return await ctx.send(f"You do not have enough {resource.title()} to transfer.", ephemeral=True)

        # Re-fetch player to prevent race conditions and use atomic update
        await player.refresh()
        current_balance = getattr(player, resource, 0) or 0
        if current_balance < amount:
            return await ctx.send(f"You no longer have enough {resource.title()} to transfer.", ephemeral=True)

        await player.update_self({getattr(Player, resource): getattr(Player, resource) - amount})
        await target.update_self({getattr(Player, resource): getattr(Player, resource) + amount})
        await ctx.send(f"Successfully transferred `{humanize_number(amount)}` {resource.title()} to {user.mention}.")

    @miner_group.command(
        name="upgrade", description="Upgrade your mining tool if you have enough resources (with confirmation)."
    )
    @ensure_db_connection()
    async def miner_upgrade(self, ctx: commands.Context):
        """Upgrade your mining tool if you have enough resources (with confirmation)."""
        player = await self.db_utils.get_create_player(ctx.author)
        current_tool = player.tool
        try:
            idx = constants.TOOL_ORDER.index(current_tool)
        except ValueError:
            embed = discord.Embed(
                title="Tool Error",
                description="Your tool is invalid. Please contact an admin.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return
        if idx >= len(constants.TOOL_ORDER) - 1:
            embed = discord.Embed(
                title="Max Upgrade",
                description=f"You already have the best tool! {constants.TROPHY_EMOJI}",
                color=discord.Color.gold(),
            )
            await ctx.send(embed=embed)
            return

        next_tool_name = constants.TOOL_ORDER[idx + 1]
        next_tool = constants.TOOLS[next_tool_name]
        missing: list[str] = []
        for resource, cost in (next_tool.upgrade_cost or {}).items():
            have = getattr(player, resource, 0) or 0
            if have < cost:
                missing.append(f"`{cost - have}` **{resource.title()}**")

        cost_str = "\n".join(
            f"{constants.resource_emoji(k)} {k.title()}: `{v}`" for k, v in (next_tool.upgrade_cost or {}).items()
        )
        stats_str = (
            f"Power: `{next_tool.power}`\n"
            f"Crit Chance: `{next_tool.crit_chance * 100:.1f}%`\n"
            f"Crit Multiplier: `x{next_tool.crit_multiplier:.2f}`\n"
            f"Shatter Resistance: `{next_tool.shatter_resistance * 100:.1f}%`\n"
            f"Durability: `{next_tool.max_durability}`"
        )
        embed = discord.Embed(
            title=f"Upgrade to {next_tool.display_name}?",
            description=f"{stats_str}\n\n**Cost:**\n{cost_str}",
            color=discord.Color.orange(),
        )
        if missing:
            embed.add_field(name=":warning: Missing Resources", value="\n".join(missing), inline=False)
            await ctx.send(embed=embed)
            return

        view = UpgradeConfirmView(player)
        msg = await ctx.send(embed=embed, view=view)

        await view.wait()
        if not view.value:
            cancel_embed = discord.Embed(
                title="Upgrade Cancelled", description="You cancelled the upgrade.", color=discord.Color.red()
            )
            await msg.edit(content=None, embed=cancel_embed, view=None)
            return

        # Re-fetch player to validate resources haven't changed (Suggestion #2)
        await player.refresh()
        missing_after: list[str] = []
        for resource, cost in (next_tool.upgrade_cost or {}).items():
            have = getattr(player, resource, 0) or 0
            if have < cost:
                missing_after.append(f"`{cost - have}` **{resource.title()}**")
        if missing_after:
            fail_embed = discord.Embed(
                title="Upgrade Failed",
                description="You no longer have enough resources to complete this upgrade.",
                color=discord.Color.red(),
            )
            fail_embed.add_field(name=":warning: Missing Resources", value="\n".join(missing_after), inline=False)
            await msg.edit(content=None, embed=fail_embed, view=None)
            return

        # Deduct resources
        update_kwargs = {
            getattr(Player, resource): getattr(Player, resource) - cost
            for resource, cost in (next_tool.upgrade_cost or {}).items()
        }
        update_kwargs[Player.tool] = next_tool_name
        update_kwargs[Player.durability] = next_tool.max_durability
        await Player.update(update_kwargs).where(Player.id == ctx.author.id)
        self.reset_durability_warnings(player.id)
        done_embed = discord.Embed(
            title="Upgrade Successful!",
            description=f"{ctx.author.mention}, you have upgraded to the **{next_tool.display_name}**! {constants.PICKAXE_EMOJI}\nDurability restored to `{next_tool.max_durability}`.",
            color=discord.Color.green(),
        )
        await msg.edit(content=None, embed=done_embed, view=None)
        await self.db_utils.get_cached_player_tool.cache.delete(f"miner_player_tool:{player.id}")  # type: ignore
        unlocked = await self.sync_player_achievements(ctx.author)
        if unlocked:
            await self.announce_achievement_unlocks(ctx.channel, ctx.author, unlocked)

    @miner_group.command(name="leaderboard", aliases=["lb"], description="View the leaderboard.")
    @ensure_db_connection()
    async def miner_leaderboard_from_group(self, ctx: commands.Context, local: bool = True):
        """View the leaderboard."""
        await LeaderboardView(self.bot, ctx, local=local).start()

    @commands.hybrid_command(name="minerlb", description="View the leaderboard.")
    @ensure_db_connection()
    async def miner_leaderboard(self, ctx: commands.Context, local: bool = True):
        """View the leaderboard."""
        await LeaderboardView(self.bot, ctx, local=local).start()

    @miner_group.command(name="convert", description="Convert resources to economy credits (if enabled).")
    @ensure_db_connection()
    async def miner_convert_group(
        self,
        ctx: commands.Context,
        resource: constants.Resource,
        amount: commands.positive_int,
    ):
        """Convert resources to economy credits (if enabled).

        **Arguments:**
        `resource`: The type of resource to convert (stone, iron, gems).
        `amount`: The amount of the resource to convert.
        """
        if await bank.is_global():
            settings = await self.db_utils.get_create_global_settings()
        else:
            settings = await self.db_utils.get_create_guild_settings(ctx.guild)
        if not settings.conversion_enabled:
            return await ctx.send("Resource conversion is not enabled.", ephemeral=True)
        conversion_ratio: float = getattr(settings, f"{resource}_convert_rate")
        if not conversion_ratio or conversion_ratio <= 0:
            return await ctx.send("No conversion rate set for that resource.", ephemeral=True)

        player = await self.db_utils.get_create_player(ctx.author)
        resource_balance: int = getattr(player, resource, 0) or 0
        creditsname = await bank.get_currency_name(ctx.guild)
        if amount > resource_balance:
            grammar = "that many" if resource == "gems" else "that much"
            return await ctx.send(f"You do not have {grammar} {resource.title()}!", ephemeral=True)
        if conversion_ratio > amount:
            return await ctx.send(
                f"You need to convert at least `{conversion_ratio}` {resource.title()} to receive {creditsname}.",
                ephemeral=True,
            )
        # Conversion ratio can be a float between 0 and infinity
        credits_to_give = math.floor(amount / conversion_ratio)
        amount_to_deduct = round(credits_to_give * conversion_ratio)

        if credits_to_give == 0:
            return await ctx.send(
                f"You need to convert at least `{conversion_ratio}` {resource.title()} to receive 1 {creditsname}.",
                ephemeral=True,
            )

        try:
            await bank.deposit_credits(ctx.author, credits_to_give)
        except BalanceTooHigh as e:
            await bank.set_balance(ctx.author, e.max_balance)
        await player.update_self({getattr(Player, resource): max(0, getattr(player, resource) - amount_to_deduct)})

        return await ctx.send(
            f"{ctx.author.mention}, you have converted `{humanize_number(amount_to_deduct)}` {resource.title()} into `{humanize_number(credits_to_give)}` {creditsname}."
        )

    @miner_group.command(name="guide", description="Overview of how Miner works and core commands.")
    @ensure_db_connection()
    async def miner_guide(self, ctx: commands.Context):
        """Send an in-game guide covering the core loop, spawns, overswing, and repairs."""

        description = (
            "Chat in mining-enabled channels to track your recent activity, "
            "then use `/rock` to spawn a rock based on your group's average tool tier. Mine rocks to earn resources!"
        )
        embed = discord.Embed(
            title="Miner Guide",
            description=description,
            color=discord.Color.gold(),
        )

        spawn_text = (
            "• Use `/rock` to attempt to spawn a rock in a mining-enabled channel.\n"
            "• Each guild has a shared cooldown (default 5 minutes) between spawns.\n"
            "• Rock quality is determined by the average tool tier and number of recent active miners.\n"
            "• Chat in mining channels to be counted as an active miner for quality scaling."
        )
        embed.add_field(name="Spawning Rocks", value=spawn_text, inline=False)

        modifiers_text = (
            "Rocks can spawn with **modifiers** — special affixes that alter their stats:\n"
            f"• {constants.MODIFIERS['electrified'].emoji} **Electrified**: +20% loot, +50% volatility\n"
            f"• {constants.MODIFIERS['crystalline'].emoji} **Crystalline**: +30% loot, +15% HP\n"
            f"• {constants.MODIFIERS['volatile'].emoji} **Volatile**: +30% volatility, unpredictable\n"
            f"• {constants.MODIFIERS['enchanted'].emoji} **Enchanted**: +15% loot, -20% volatility, lucky\n"
            f"• {constants.MODIFIERS['fortified'].emoji} **Fortified**: +40% HP, -10% loot\n"
            f"• {constants.MODIFIERS['blessed'].emoji} **Blessed**: +25% loot, -50% volatility. Rare blessing!\n"
            "Use the **Inspect** button to see a rock's modifiers before mining!"
        )
        embed.add_field(name="Rock Modifiers", value=modifiers_text, inline=False)

        overswing_text = (
            "• Swinging faster than the cooldown causes slips (overswing).\n"
            "• Overswing can damage your tool and may shatter it if durability is low.\n"
            "• Use steady timing to avoid overswing penalties and protect durability."
        )
        embed.add_field(name="Mining & Overswing", value=overswing_text, inline=False)

        performance_text = (
            "Your payout now includes a **performance bonus** based on how well you mine each rock:\n"
            "• Score combines damage share, swing control (fewer overswings), and active hit count\n"
            "• Score 70+ = +3% loot bonus\n"
            "• Score 80+ = +5% loot bonus\n"
            "• Score 90+ = +8% loot bonus\n"
            "• Gem bonus is capped at +8% for economy safety"
        )
        embed.add_field(name="Loot Performance Bonuses", value=performance_text, inline=False)

        synergy_text = (
            "Mining with a balanced crew can activate **party synergy** bonuses:\n"
            "• **Breaker** brings strong damage share\n"
            "• **Stabilizer** keeps overswings low\n"
            "• **Finisher** dominates the last chunk of rock HP\n"
            "• 2 roles = +2% stone/iron for the crew\n"
            "• 3 roles = +4% stone/iron for the crew\n"
            "• Active role holders save 1 durability when wear is applied"
        )
        embed.add_field(name="Party Synergy", value=synergy_text, inline=False)

        durability_text = (
            "• Every hit reduces durability; breaking a tool downgrades it.\n"
            "• Repairs cost a fraction of the upgrade resources via `[p]miner repair true`.\n"
            "• Higher-tier pickaxes cost more to repair, so upkeep matters more later on.\n"
            "• Upgrade tools with `[p]miner upgrade` to increase power and max durability."
        )
        embed.add_field(name="Durability & Repairs", value=durability_text, inline=False)

        p = ctx.clean_prefix
        commands_text = (
            f"`{p}miner inventory` - view your tool, durability, and resources.\n"
            f"`{p}miner trade @user` - trade resources with others.\n"
            f"`{p}rock` - attempt to spawn a rock in this mining channel.\n"
            f"`{p}minerset view` - (admins) list enabled channels and cooldown settings."
        )
        embed.add_field(name="Helpful Commands", value=commands_text, inline=False)

        embed.set_footer(
            text="Need more help? Ask your admins to review `[p]minerset view` for server-specific settings."
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rock", description="Attempt to spawn a rock in this mining channel.")
    @commands.guild_only()
    @ensure_db_connection()
    async def spawn_rock(self, ctx: commands.Context):
        """Attempt to spawn a rock in this mining channel.

        Has a per-guild cooldown (default 5 minutes). Rock quality scales with
        the average tool tier and player count of recent chatters.
        """
        # Check if this is an active mining channel
        is_mining_channel = await ActiveChannel.exists().where(ActiveChannel.id == ctx.channel.id)
        if not is_mining_channel:
            return await ctx.send(
                "Rocks cannot spawn in this channel. Ask an admin to enable it with `/minerset toggle`.",
                ephemeral=True,
            )

        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        global_settings = await self.db_utils.get_create_global_settings()
        view = None

        try:
            async with self.get_guild_spawn_lock(ctx.guild.id):
                cooldown_remaining = self.get_guild_spawn_cooldown_remaining(
                    ctx.guild.id, global_settings.spawn_cooldown_seconds
                )

                if cooldown_remaining > 0:
                    ready_timestamp = int(discord.utils.utcnow().timestamp() + math.ceil(cooldown_remaining))
                    return await ctx.send(
                        f"Rock spawn cooldown is active. You can summon more rocks <t:{ready_timestamp}:R>.",
                        ephemeral=True,
                    )

                rock_type_result = self.choose_rock_type(ctx.channel.id)
                modifiers = self.choose_modifiers(rock_type_result)

                await self.notify_spawn_subscribers(ctx.guild, settings, ctx.send)

                rock: constants.RockType = constants.ROCK_TYPES[rock_type_result]
                view = RockView(self, rock, modifiers)
                await view.start(ctx.channel)
                # Consume cooldown only after the rock message is successfully posted.
                self.guild_spawn_cooldowns[ctx.guild.id] = perf_counter()

            if view is not None:
                await view.wait()
        except Exception as e:
            log.error(f"Error spawning rock in {ctx.channel.id}: {e}")
            await ctx.send("An error occurred while spawning the rock.", ephemeral=True)

    async def build_achievement_pages(
        self,
        ctx: commands.Context,
        user: discord.User | discord.Member,
        unlocked_rows: list,
    ) -> list[discord.Embed]:
        color = await self.bot.get_embed_color(ctx.channel)
        stats = await self.get_player_achievement_stats(user)
        resource_lower_bounds = await self.db_utils.get_player_resource_lower_bounds(user)
        unlocked_lookup = {row.key: row for row in unlocked_rows}
        pages: list[discord.Embed] = []

        summary = discord.Embed(
            title=f"{user.display_name}'s Miner Achievements",
            color=color,
            description=(
                f"Unlocked `{len(unlocked_lookup)}` / `{achievements.TOTAL_ACHIEVEMENTS}` achievements.\n"
                "Locked achievements show their full condition text.\n"
                "Retroactive sync currently awards only achievements provable from persisted miner data."
            ),
        )
        category_lines = []
        for category, items in achievements.iter_achievements_by_category():
            unlocked_count = sum(1 for item in items if item.key in unlocked_lookup)
            category_lines.append(f"• {category}: `{unlocked_count}/{len(items)}`")
        summary.add_field(name="Categories", value="\n".join(category_lines), inline=False)

        recent_lines = []
        for row in unlocked_rows[:5]:
            definition = achievements.ACHIEVEMENTS_BY_KEY.get(row.key)
            if definition is None:
                continue
            recent_lines.append(f"• {definition.name} ({discord.utils.format_dt(row.created_on, style='R')})")
        if recent_lines:
            summary.add_field(name="Recent Unlocks", value="\n".join(recent_lines), inline=False)
        else:
            summary.add_field(name="Recent Unlocks", value="No achievements unlocked yet.", inline=False)
        summary.set_thumbnail(url=user.display_avatar)
        pages.append(summary)

        for category, items in achievements.iter_achievements_by_category():
            unlocked_count = sum(1 for item in items if item.key in unlocked_lookup)
            lines: list[str] = []
            for item in items:
                unlocked = unlocked_lookup.get(item.key)
                if unlocked is not None:
                    lines.append(
                        f"✅ **{item.name}**\n"
                        f"-# {item.condition}\n"
                        f"-# Unlocked {discord.utils.format_dt(unlocked.created_on, style='R')}"
                    )
                else:
                    progress_line = self.format_achievement_progress(item, stats, resource_lower_bounds)
                    if progress_line:
                        lines.append(f"🔒 **{item.name}**\n-# {item.condition}\n-# {progress_line}")
                    else:
                        lines.append(f"🔒 **{item.name}**\n-# {item.condition}")

            embed = discord.Embed(
                title=f"{user.display_name} • {category}",
                color=color,
                description="\n\n".join(lines),
            )
            embed.add_field(name="Progress", value=f"Unlocked `{unlocked_count}` / `{len(items)}`", inline=False)
            embed.set_thumbnail(url=user.display_avatar)
            pages.append(embed)

        return pages

    def format_achievement_progress(
        self,
        item: achievements.AchievementDef,
        stats: t.Any,
        resource_lower_bounds: dict[constants.Resource, int],
    ) -> str | None:
        if item.key.startswith("clean_streak_") and item.threshold is None:
            threshold = int(item.key.split("_")[-1])
            current = int(stats.clean_streak_current or 0)
            return f"Current clean streak: `{min(current, threshold)}` / `{threshold}`"

        if item.key in achievements.SOLO_SPEED_THRESHOLDS:
            return None

        if item.key == "solo_speed_small":
            return self.format_solo_progress(stats.best_solo_small_seconds or 0.0, 20.0)
        if item.key == "solo_speed_medium":
            return self.format_solo_progress(stats.best_solo_medium_seconds or 0.0, 40.0)
        if item.key == "solo_speed_large":
            return self.format_solo_progress(stats.best_solo_large_seconds or 0.0, 60.0)
        if item.key == "solo_speed_meteor":
            return self.format_solo_progress(stats.best_solo_meteor_seconds or 0.0, 90.0)
        if item.key == "solo_speed_geode":
            return self.format_solo_progress(stats.best_solo_geode_seconds or 0.0, 130.0)

        if item.retroactive_rule == "tool_at_least_tier" and item.tool is not None:
            return f"Current tool milestone target: `{constants.TOOLS[item.tool].display_name}`"

        if item.key == "perf_max_streak_3":
            current = int(stats.perf_max_streak_current or 0)
            return f"Current 90+ streak: `{min(current, 3)}` / `3`"

        if item.key == "modifier_total_50":
            current = int(stats.modifier_rocks_mined_total or 0)
            return f"Modifier rocks mined: `{min(current, 50)}` / `50`"

        if item.retroactive_rule == "resource_any_positive":
            total = sum(resource_lower_bounds.values())
            return f"Tracked mined resources total: `{humanize_number(total)}`"

        if item.retroactive_rule == "resource_lower_bound" and item.resource and item.threshold is not None:
            current = int(resource_lower_bounds.get(item.resource, 0))
            return (
                f"Mined {item.resource}: `{humanize_number(min(current, item.threshold))}` / "
                f"`{humanize_number(item.threshold)}`"
            )

        if item.key == "party_role_breaker":
            current = int(stats.role_breaker_total or 0)
            return f"Breaker roles earned: `{current}`"
        if item.key == "party_role_stabilizer":
            current = int(stats.role_stabilizer_total or 0)
            return f"Stabilizer roles earned: `{current}`"
        if item.key == "party_role_finisher":
            current = int(stats.role_finisher_total or 0)
            return f"Finisher roles earned: `{current}`"
        if item.key == "party_group_sessions_25":
            current = int(stats.group_sessions_total or 0)
            return f"Group mining sessions: `{min(current, 25)}` / `25`"
        if item.key == "party_all_roles":
            earned_roles = [
                name
                for name, total in (
                    ("Breaker", int(stats.role_breaker_total or 0)),
                    ("Stabilizer", int(stats.role_stabilizer_total or 0)),
                    ("Finisher", int(stats.role_finisher_total or 0)),
                )
                if total > 0
            ]
            missing_roles = [name for name in ("Breaker", "Stabilizer", "Finisher") if name not in earned_roles]
            return (
                f"Roles earned: `{len(earned_roles)}` / `3`"
                if not missing_roles
                else f"Roles earned: `{len(earned_roles)}` / `3` | missing {', '.join(missing_roles)}"
            )

        if item.key == "rocks_mined_50":
            current = int(stats.rocks_mined_total or 0)
            return f"Rocks mined: `{min(current, 50)}` / `50`"
        if item.key == "rocks_mined_250":
            current = int(stats.rocks_mined_total or 0)
            return f"Rocks mined: `{min(current, 250)}` / `250`"
        if item.key == "rocks_mined_1000":
            current = int(stats.rocks_mined_total or 0)
            return f"Rocks mined: `{min(current, 1000)}` / `1000`"
        if item.key == "rock_variety_all":
            mined_types = [
                name
                for name, seen in (
                    ("Small", bool(stats.mined_small)),
                    ("Medium", bool(stats.mined_medium)),
                    ("Large", bool(stats.mined_large)),
                    ("Meteor", bool(stats.mined_meteor)),
                    ("Geode", bool(stats.mined_geode)),
                )
                if seen
            ]
            missing_types = [
                name for name in ("Small", "Medium", "Large", "Meteor", "Geode") if name not in mined_types
            ]
            return (
                f"Rock types mined: `{len(mined_types)}` / `5`"
                if not missing_types
                else f"Rock types mined: `{len(mined_types)}` / `5` | missing {', '.join(missing_types)}"
            )

        if item.key == "tool_shatter_comeback":
            if int(stats.shatter_recovery_stage or 0) > 0:
                return "Comeback is primed: successfully mine any later rock encounter."
            return "Shatter a tool first, then finish a later rock encounter."

        return None

    def format_solo_progress(self, best_time: float, target_time: float) -> str:
        if best_time <= 0:
            return f"Best solo clear: `none yet` | target `<= {target_time:.0f}s`"
        return f"Best solo clear: `{best_time:.1f}s` | target `<= {target_time:.0f}s`"
