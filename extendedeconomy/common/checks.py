import asyncio
import logging
import math
import typing as t

import discord
from redbot.core import bank, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..views.confirm import ConfirmView
from .utils import (
    confirm_msg,
    confirm_msg_reaction,
    ctx_to_dict,
    ctx_to_id,
    edit_delete_delay,
    get_cached_credits_name,
)

log = logging.getLogger("red.vrt.extendedeconomy.checks")
_ = Translator("ExtendedEconomy", __file__)


class Checks(MixinMeta):
    async def cost_check(self, ctx: t.Union[commands.Context, discord.Interaction]):
        return await self._cost_check(ctx, ctx.author if isinstance(ctx, commands.Context) else ctx.user)

    async def slash_cost_check(self, interaction: discord.Interaction):
        return await self._cost_check(interaction, interaction.user)

    async def _cost_check(
        self,
        ctx: t.Union[commands.Context, discord.Interaction],
        user: t.Union[discord.Member, discord.User],
    ):
        if isinstance(ctx, discord.Interaction):
            user = ctx.guild.get_member(ctx.user.id) if ctx.guild else ctx.user
        else:
            user = ctx.author
        command_name = ctx.command.qualified_name
        is_global = await bank.is_global()
        if not is_global and ctx.guild is None:
            # Command run in DMs and bank is not global, cant apply cost so just return
            return True

        if is_global:
            cost_obj = self.db.command_costs.get(command_name)
        elif ctx.guild is not None:
            conf = self.db.get_conf(ctx.guild)
            cost_obj = conf.command_costs.get(command_name)
        else:
            log.error(f"Unknown condition in '{command_name}' cost check for {user.name}: {ctx_to_dict(ctx)}")
            return True
        if not cost_obj:
            return True

        # At this point we know that the command has a cost associated with it
        log.debug(f"Priced command '{ctx.command.qualified_name}' invoked by {user.name} - ({type(ctx)})")

        cost = await cost_obj.get_cost(self.bot, user)
        if cost == 0:
            cost_obj.update_usage(user.id)
            return True

        currency = await get_cached_credits_name(ctx.guild)
        is_broke = _("You do not have enough {} to run that command! (Need {})").format(currency, humanize_number(cost))
        notify = _("{}, you spent {} to run this command").format(
            user.display_name, f"{humanize_number(cost)} {currency}"
        )
        del_delay = self.db.delete_after if self.db.delete_after else None

        interaction = ctx if isinstance(ctx, discord.Interaction) else ctx.interaction
        if interaction is None and cost_obj.prompt != "silent":
            # For text commands only
            if not await bank.can_spend(user, cost):
                raise commands.UserFeedbackCheckFailure(is_broke)
            message: discord.Message = None
            if cost_obj.prompt != "notify":
                txt = _("Do you want to spend {} {} to run this command?").format(humanize_number(cost), currency)
                if cost_obj.prompt == "text":
                    message = await ctx.send(txt)
                    yes = await confirm_msg(ctx)
                elif cost_obj.prompt == "reaction":
                    message = await ctx.send(txt)
                    yes = await confirm_msg_reaction(message, user, self.bot)
                elif cost_obj.prompt == "button":
                    view = ConfirmView(user)
                    message = await ctx.send(txt, view=view)
                    await view.wait()
                    yes = view.value
                else:
                    raise ValueError(f"Invalid prompt type: {cost_obj.prompt}")
                if not yes:
                    txt = _("Not running `{}`.").format(command_name)
                    asyncio.create_task(edit_delete_delay(message, txt, del_delay))
                    raise commands.UserFeedbackCheckFailure()
            if message:
                asyncio.create_task(edit_delete_delay(message, notify, del_delay))
            else:
                asyncio.create_task(ctx.send(notify, delete_after=del_delay))

        try:
            await bank.withdraw_credits(user, cost)
            cost_obj.update_usage(user.id)
            if isinstance(ctx, commands.Context):
                self.charged[ctx_to_id(ctx)] = cost
            elif cost_obj.prompt != "silent":
                asyncio.create_task(ctx.channel.send(notify, delete_after=del_delay))
            return True
        except ValueError:
            log.debug(f"Failed to charge {user.name} for '{command_name}' - cost: {cost} {currency}")
            if isinstance(ctx, commands.Context):
                self.charged.pop(ctx_to_id(ctx), None)
            if isinstance(ctx, discord.Interaction):
                await interaction.response.send_message(is_broke, ephemeral=True)
                return False
            # asyncio.create_task(ctx.send(is_broke, delete_after=del_delay, ephemeral=True))
            raise commands.UserFeedbackCheckFailure()

    async def transfer_tax_check(self, ctx: commands.Context):
        if ctx.command.qualified_name != "bank transfer":
            return True
        is_global = await bank.is_global()
        conf = self.db if is_global else self.db.get_conf(ctx.guild)
        tax = conf.transfer_tax
        if tax == 0:
            log.debug("No transfer tax set")
            return True

        if not is_global and getattr(conf, "transfer_tax_whitelist", None):
            whitelist = conf.transfer_tax_whitelist
            if any(r.id in whitelist for r in ctx.author.roles):
                # log.debug(f"{ctx.author} is in the transfer tax whitelist")
                return True

        # Args: EconomyCog, ctx, to, amount
        amount: int = ctx.args[-1]

        deduction = math.ceil(amount * tax)
        asyncio.create_task(bank.withdraw_credits(ctx.author, deduction))
        # Modify the amount to be transferred
        ctx.args[-1] = amount - deduction

        currency = await get_cached_credits_name(ctx.guild)
        txt = _("{}% transfer tax applied, {} deducted from transfer").format(
            f"{round(tax * 100)}", f"{humanize_number(deduction)} {currency}"
        )
        await ctx.send(txt)
        return True
