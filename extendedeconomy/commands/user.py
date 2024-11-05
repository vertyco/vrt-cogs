import asyncio
import logging

from redbot.core import bank, commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common.generator import generate_pie_chart

log = logging.getLogger("red.vrt.extendedeconomy.admin")
_ = Translator("ExtendedEconomy", __file__)


@cog_i18n(_)
class User(MixinMeta):
    @commands.command(name="idbalance")
    async def id_balance(self, ctx: commands.Context, user_id: int):
        """Get the balance of a user by ID.

        Helpful for checking a user's balance if they are not in the server.
        """
        if await bank.is_global():
            all_accounts = await bank._config.all_users()
        else:
            all_accounts = await bank._config.all_members(ctx.guild)

        if user_id in all_accounts:
            balance = all_accounts[user_id]["balance"]
            await ctx.send(f"User ID: {user_id} has a balance of `{balance}`")
        else:
            await ctx.send(_("User ID not found."))

    @commands.command(name="bankpie")
    @commands.bot_has_permissions(attach_files=True)
    async def bank_pie(self, ctx: commands.Context, amount: int = 10):
        """View a pie chart of the top X bank balances."""
        is_global = await bank.is_global()
        if is_global:
            members = await bank._config.all_users()
        else:
            members = await bank._config.all_members(ctx.guild)

        user_balances = []

        for user_id, wallet in members.items():
            user = ctx.guild.get_member(user_id)
            if user:
                user_balances.append((user.display_name, wallet["balance"]))

        if not user_balances:
            return await ctx.send(_("No users found."))

        # Sort users by balance in descending order and take the top X amount
        user_balances.sort(key=lambda x: x[1], reverse=True)
        top_users = user_balances[:amount]
        other_balance = sum(balance for _, balance in user_balances[amount:])

        labels = [user for user, _ in top_users]
        sizes = [balance for _, balance in top_users]

        if other_balance > 0:
            labels.append("Other")
            sizes.append(other_balance)

        file = await asyncio.to_thread(
            generate_pie_chart,
            labels,
            sizes,
            _("Bank Balances for {}").format(ctx.guild.name),
        )
        await ctx.send(file=file)
