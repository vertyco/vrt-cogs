import asyncio
import json
import logging
import typing as t

import discord
from aiocache import cached
from redbot.core import bank, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..views.confirm import ConfirmView
from .utils import confirm_msg, confirm_msg_reaction

log = logging.getLogger("red.vrt.extendedeconomy.checks")
_ = Translator("ExtendedEconomy", __file__)


class Checks(MixinMeta):
    def __init__(self):
        super().__init__()
        self.running = set()

    @cached(ttl=600)
    async def get_credits_name(self, guild: discord.Guild) -> str:
        return await bank.get_currency_name(guild)

    async def cost_check(self, ctx: t.Union[commands.Context, discord.Interaction]):
        if isinstance(ctx, discord.Interaction):
            ctx: discord.Interaction = ctx
            user = ctx.guild.get_member(ctx.user.id) if ctx.guild else ctx.user
            usage_id = f"{ctx.id}-{user.id}"
        else:
            ctx: commands.Context = ctx
            user = ctx.author
            usage_id = f"{ctx.message.id}"

        if usage_id in self.running:
            return True
        try:
            self.running.add(usage_id)
            return await self._cost_check(ctx, user)
        finally:
            self.running.remove(usage_id)

    async def _cost_check(
        self,
        ctx: t.Union[commands.Context, discord.Interaction],
        user: t.Union[discord.Member, discord.User],
    ):
        async def _edit_delete_delay(message: discord.Message, new_content: str):
            await message.edit(content=new_content, view=None)
            await message.clear_reactions()
            await message.delete(delay=self.db.delete_after)

        def ctx_to_dict(c: t.Union[commands.Context, discord.Interaction]):
            if isinstance(c, discord.Interaction):
                info = {
                    "type": "Interaction",
                    "id": c.id,
                    "user": c.user.id,
                    "guild": c.guild.id if c.guild else None,
                    "channel": c.channel.id,
                }
            else:
                info = {
                    "type": "Context",
                    "id": c.message.id,
                    "user": c.author.id,
                    "guild": c.guild.id if c.guild else None,
                    "channel": c.channel.id,
                }
            return json.dumps(info, indent=2)

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
            log.error(f"Unknown condition in cost check for {user.name}: {ctx_to_dict(ctx)}")
            return True

        if not cost_obj:
            return True

        cost = await cost_obj.get_cost(self.bot, user)
        if cost == 0:
            cost_obj.update_usage(user.id)
            return True

        is_broke = _("You can't afford to run the `{}` command! (Need {} credits)").format(
            command_name, humanize_number(cost)
        )
        is_slash = isinstance(ctx, discord.Interaction) or ctx.interaction is not None
        currency = await self.get_credits_name(ctx.guild)

        if not is_slash and cost_obj.prompt != "silent":
            is_broke = _("You do not have enough {} to run that command! (Need {})").format(
                currency, humanize_number(cost)
            )
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
                    asyncio.create_task(_edit_delete_delay(message, _("Not running `{}`.").format(command_name)))
                    return False
                asyncio.create_task(message.delete())

            if not await bank.can_spend(user, cost):
                if cost_obj.prompt != "notify":
                    asyncio.create_task(_edit_delete_delay(message, is_broke))
                else:
                    asyncio.create_task(ctx.send(is_broke, delete_after=self.db.delete_after))
                return False

            if cost_obj.prompt == "notify":
                asyncio.create_task(
                    ctx.send(
                        _("{}, You spent {} {} to run this command.").format(
                            user.display_name, humanize_number(cost), currency
                        ),
                        delete_after=self.db.delete_after,
                    )
                )

        try:
            await bank.withdraw_credits(user, cost)
            cost_obj.update_usage(user.id)
            if is_slash and cost_obj.prompt != "silent":
                asyncio.create_task(
                    ctx.channel.send(
                        _("{}, You spent {} {} to run the `{}` command.").format(
                            user.display_name, humanize_number(cost), currency, command_name
                        ),
                        delete_after=self.db.delete_after,
                    )
                )
            return True
        except ValueError:
            # Cant afford
            asyncio.create_task(ctx.channel.send(is_broke, delete_after=self.db.delete_after))
            return False
