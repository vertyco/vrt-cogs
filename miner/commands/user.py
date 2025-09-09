import math
import typing as t

import discord
from redbot.core import bank, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import Player, ensure_db_connection
from ..views.leaderboard_menu import LeaderboardView
from ..views.trade_panel import TradePanel
from ..views.upgrade_view import UpgradeConfirmView


class User(MixinMeta):
    @commands.hybrid_group(name="miner", invoke_without_command=True)
    async def miner_group(self, ctx: commands.Context):
        """User commands"""
        await ctx.send_help()

    @miner_group.command(name="inventory", aliases=["inv"])
    @ensure_db_connection()
    async def miner_inventory(self, ctx: commands.Context, user: t.Optional[discord.User | discord.Member] = None):
        """View your mining inventory and tool."""
        if not user:
            user = ctx.author
        player = await self.db_utils.get_create_player(user)
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

        embed.set_thumbnail(url=user.display_avatar)
        await ctx.send(embed=embed)

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

        # Calculate repair cost dynamically based on missing durability percentage
        # Base cost is TOOL_REPAIR_COST_PCT of upgrade cost, scaled by missing_ratio
        missing_ratio = (max_dura - player.durability) / max_dura
        repair_cost = {}
        if tool.upgrade_cost:
            for resource, amount in tool.upgrade_cost.items():
                base = amount * constants.TOOL_REPAIR_COST_PCT
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

        embed = discord.Embed(
            title="Tool Repaired!",
            description=f"Your {tool.display_name} has been fully repaired!\nDurability: `{max_dura}`\n\n**Cost:**\n{cost_str}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

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

        await player.update_self({getattr(Player, resource): balance - amount})
        await target.update_self({getattr(Player, resource): getattr(target, resource, 0) + amount})
        await ctx.send(f"Successfully transferred `{humanize_number(amount)}` {resource.title()} to {user.mention}.")

    @miner_group.command(name="upgrade")
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
        # Deduct resources
        update_kwargs = {
            getattr(Player, resource): getattr(Player, resource) - cost
            for resource, cost in (next_tool.upgrade_cost or {}).items()
        }
        update_kwargs[Player.tool] = next_tool_name
        update_kwargs[Player.durability] = next_tool.max_durability
        await Player.update(update_kwargs).where(Player.id == ctx.author.id)
        done_embed = discord.Embed(
            title="Upgrade Successful!",
            description=f"{ctx.author.mention}, you have upgraded to the **{next_tool.display_name}**! {constants.PICKAXE_EMOJI}\nDurability restored to `{next_tool.max_durability}`.",
            color=discord.Color.green(),
        )
        await msg.edit(content=None, embed=done_embed, view=None)

    @miner_group.command(name="leaderboard", aliases=["lb"])
    @ensure_db_connection()
    async def miner_leaderboard_from_group(self, ctx: commands.Context):
        """View the top players for a specific resource."""
        await LeaderboardView(self.bot, ctx).start()

    @commands.hybrid_command(name="minerlb")
    @ensure_db_connection()
    async def miner_leaderboard(self, ctx: commands.Context):
        """View the top players for a specific resource."""
        await LeaderboardView(self.bot, ctx).start()

    @miner_group.command(name="convert")
    async def miner_convert_group(
        self, ctx: commands.Context, resource: constants.Resource, amount: commands.positive_int
    ):
        """Convert resources to economy credits (if enabled)."""
        player = await self.db_utils.get_create_player(ctx.author)
        if await bank.is_global():
            settings = await self.db_utils.get_create_global_settings()
        else:
            settings = await self.db_utils.get_create_guild_settings(ctx.guild)

        if not settings.conversion_enabled:
            return await ctx.send("Resource conversion is not enabled.", ephemeral=True)

        if amount > getattr(player, resource):
            grammar = "that many" if resource == "gems" else "that much"
            return await ctx.send(f"You do not have {grammar} {resource.title()}!", ephemeral=True)

        rate: float = getattr(settings, f"{resource}_convert_rate")

        creditsname = await bank.get_currency_name(ctx.guild)

        credits, remainder = divmod(amount, rate)
        if credits == 0:
            return await ctx.send(
                f"You need to convert at least `{rate}` {resource.title()} to receive 1 {creditsname}.", ephemeral=True
            )

        amount_to_deduct = amount - remainder
        try:
            await bank.deposit_credits(ctx.author, credits)
        except BalanceTooHigh as e:
            await bank.set_balance(ctx.author, e.max_balance)
        await player.update_self({getattr(Player, resource): max(0, getattr(player, resource) - amount_to_deduct)})

        return await ctx.send(
            f"{ctx.author.mention}, you have converted `{humanize_number(amount_to_deduct)}` {resource.title()} into `{humanize_number(credits)}` {creditsname}."
        )
