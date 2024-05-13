import logging
import typing as t

import discord
from discord import app_commands
from redbot.core import bank, commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common.models import CommandCost
from ..common.parser import SetParser
from ..views.confirm import ConfirmView
from ..views.cost_menu import CostMenu

log = logging.getLogger("red.vrt.extendedeconomy.admin")
_ = Translator("ExtendedEconomy", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(aliases=["ecoset", "exteco"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def extendedeconomy(self, ctx: commands.Context):
        """
        Extended Economy settings

        **NOTE**
        Although setting prices for pure slash commands works, there is no refund mechanism in place for them.

        Should a hybrid or text command fail due to an unhandled exception, the user will be refunded.
        """
        pass

    @extendedeconomy.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """
        View the current settings
        """
        is_global = await bank.is_global()
        if is_global and ctx.author.id not in self.bot.owner_ids:
            return await ctx.send(_("You must be a bot owner to view these settings when global bank is enabled."))
        view = CostMenu(ctx, self, is_global, self.cost_check)
        await view.refresh()

    @extendedeconomy.command(name="stackpaydays", aliases=["stackpayday"])
    async def stack_paydays(self, ctx: commands.Context):
        """Toggle whether payday roles stack or not"""
        is_global = await bank.is_global()
        if is_global:
            return await ctx.send(_("This setting is not available when global bank is enabled."))
        conf = self.db.get_conf(ctx.guild)
        conf.stack_paydays = not conf.stack_paydays
        if conf.stack_paydays:
            txt = _("Payday role amounts will now stack.")
        else:
            txt = _("Payday role amounts will no longer stack.")
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="autopaydayrole")
    async def autopayday_roles(self, ctx: commands.Context, *, role: discord.Role):
        """Add/Remove auto payday roles"""
        is_global = await bank.is_global()
        if is_global:
            txt = _("This setting is not available when global bank is enabled.")
            txt += _("\nUse {} to allow auto-claiming for for all users.").format(
                f"`{ctx.clean_prefix}ecoset autopayday`"
            )
            return await ctx.send(txt)
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.auto_claim_roles:
            conf.auto_claim_roles.remove(role.id)
            txt = _("This role will no longer recieve paydays automatically.")
        else:
            conf.auto_claim_roles.append(role.id)
            txt = _("This role will now recieve paydays automatically.")
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="autopayday")
    async def autopayday(self, ctx: commands.Context):
        """Toggle whether paydays are claimed automatically (Global bank)"""
        is_global = await bank.is_global()
        if not is_global:
            txt = _("This setting is only available when global bank is enabled.")
            txt += _("\nUse {} to allow auto-claiming for certain roles.").format(
                f"`{ctx.clean_prefix}ecoset autopaydayrole`"
            )
            return await ctx.send(txt)
        self.db.auto_payday_claim = not self.db.auto_payday_claim
        if self.db.auto_payday_claim:
            txt = _("Paydays will now be claimed automatically.")
        else:
            txt = _("Paydays will no longer be claimed automatically.")
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="disableautopayday")
    @commands.is_owner()
    async def disable_autopayday(self, ctx: commands.Context):
        """(Owner Only) Toggle auto payday claim globally"""
        self.db.auto_payday_disabled = not self.db.auto_payday_disabled
        if self.db.auto_payday_disabled:
            txt = _("Paydays can now be claimed automatically when set by guild or owner.")
        else:
            txt = _("Servers can no longer claim paydays automatically whether the bank is global or not.")
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="transfertax")
    async def set_transfertax(self, ctx: commands.Context, tax: float):
        """
        Set the transfer tax percentage as a decimal

        *Example: `0.05` is for 5% tax*

        - Set to 0 to disable
        - Default is 0
        """
        is_global = await bank.is_global()
        if is_global and ctx.author.id not in self.bot.owner_ids:
            return await ctx.send(_("You must be a bot owner to set the transfer tax when global bank is enabled."))
        if tax < 0 or tax >= 1:
            return await ctx.send(_("Invalid tax percentage. Must be between 0 and 1."))

        if is_global:
            self.db.transfer_tax = tax
        else:
            conf = self.db.get_conf(ctx.guild)
            conf.transfer_tax = tax
        await ctx.send(_("Transfer tax set to {}%").format(round(tax * 100, 2)))
        await self.save()

    @extendedeconomy.command(name="mainlog")
    async def set_mainlog(self, ctx: commands.Context, channel: t.Optional[discord.TextChannel] = None):
        """
        Set the main log channel
        """
        is_global = await bank.is_global()
        if is_global and ctx.author.id not in self.bot.owner_ids:
            return await ctx.send(_("You must be a bot owner to set the main log channel when global bank is enabled."))
        if is_global:
            current = self.db.logs.default_log_channel
        else:
            conf = self.db.get_conf(ctx.guild)
            current = conf.logs.default_log_channel
        if not channel and current:
            txt = _("Removing the main log channel.")
        elif not channel and not current:
            return await ctx.send_help()
        elif channel and current:
            if channel.id == current:
                return await ctx.send(_("That is already the main log channel."))
            txt = _("Main log channel changed to {}").format(channel.mention)
        else:
            txt = _("Main log channel set to {}").format(channel.mention)
        if is_global:
            self.db.logs.default_log_channel = channel.id if channel else 0
        else:
            conf = self.db.get_conf(ctx.guild)
            conf.logs.default_log_channel = channel.id if channel else 0
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="eventlog")
    async def set_eventlog(
        self,
        ctx: commands.Context,
        event: str,
        channel: t.Optional[discord.TextChannel] = None,
    ):
        """
        Set an event log channel

        **Events:**
        - set_balance
        - transfer_credits
        - bank_wipe
        - prune
        - set_global
        - payday_claim

        """
        is_global = await bank.is_global()
        if is_global and ctx.author.id not in self.bot.owner_ids:
            return await ctx.send(_("You must be a bot owner to set an event log channel when global bank is enabled."))
        if is_global:
            logs = self.db.logs
        else:
            conf = self.db.get_conf(ctx.guild)
            logs = conf.logs
        valid_events = [
            "set_balance",
            "transfer_credits",
            "bank_wipe",
            "prune",
            "set_global",
            "payday_claim",
        ]
        if event not in valid_events:
            return await ctx.send(_("Invalid event. Must be one of: {}").format(", ".join(valid_events)))
        current = getattr(logs, event)
        if not current and not channel:
            return await ctx.send(_("No channel set for this event."))
        if current and not channel:
            txt = _("Event log channel for {} removed.").format(event)
        elif current and channel:
            if channel.id == current:
                return await ctx.send(_("That is already the event log channel for {}.").format(event))
            txt = _("Event log channel for {} changed to {}").format(event, channel.mention)
        else:
            txt = _("Event log channel for {} set to {}").format(event, channel.mention)
        if is_global:
            setattr(self.db.logs, event, channel.id if channel else 0)
        else:
            conf = self.db.get_conf(ctx.guild)
            setattr(conf.logs, event, channel.id if channel else 0)
        await ctx.send(txt)
        await self.save()

    @extendedeconomy.command(name="deleteafter")
    @commands.is_owner()
    async def set_delete_after(self, ctx: commands.Context, seconds: int):
        """
        Set the delete after time for cost check messages

        - Set to 0 to disable (Recommended for public bots)
        - Default is 0 (disabled)
        """
        if not seconds:
            self.db.delete_after = None
            await ctx.send(_("Delete after time disabled."))
        else:
            self.db.delete_after = seconds
            await ctx.send(_("Delete after time set to {} seconds.").format(seconds))
        await self.save()

    @commands.command(name="addcost")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def add_cost(
        self,
        ctx: commands.Context,
        command: str = "",
        cost: int = 0,
        duration: int = 3600,
        level: t.Literal["admin", "mod", "all", "user", "global"] = "all",
        prompt: t.Literal["text", "reaction", "button", "silent", "notify"] = "notify",
        modifier: t.Literal["static", "percent", "exponential", "linear"] = "static",
        value: float = 0.0,
    ):
        """
        Add a cost to a command
        """
        if not command:
            help_txt = _(
                "- **cost**: The amount of currency to charge\n"
                "- **duration**(`default: 3600`): The time in seconds before the cost resets\n"
                "- **level**(`default: all`): The minimum permission level to apply the cost\n"
                " - admin: Admins and above can use the command for free\n"
                " - mod: Mods and above can use the command for free\n"
                " - all: Everyone must pay the cost to use the command\n"
                " - user: All users must pay the cost to use the command unless they are mod or admin\n"
                " - global: The cost is applied to all users globally\n"
                "- **prompt**(`default: notify`): How the user will be prompted to confirm the cost\n"
                " - text: The bot will send a text message asking the user to confirm the cost with yes or no\n"
                " - reaction: The bot will send a message with emoji reactions to confirm the cost\n"
                " - button: The bot will send a message with buttons to confirm the cost\n"
                " - silent: The bot will not prompt the user to confirm the cost\n"
                " - notify: The bot will simply notify the user of the cost without asking for confirmation\n"
                "- **modifier**(`default: static`): The type of cost modifier\n"
                " - static: The cost is a fixed amount\n"
                " - percent: The cost is a percentage of the user's balance on top of the base cost\n"
                " - exponential: The cost increases exponentially based on how frequently the command is used\n"
                "   - Ex: `Cost = cost + (value * uses over the duration^2)`\n"
                " - linear: The cost increases linearly based on how frequently the command is used\n"
                "   - Ex: `Cost = cost + (value * uses over the duration)`\n"
                "- **value**(`default: 0.0`): The value of the cost modifier depends on the modifier type\n"
                " - static: This will be 0 and does nothing\n"
                " - percent: Value will be the percentage of the user's balance to add to the base cost\n"
                " - exponential: Value will be the base cost multiplier\n"
                " - linear: Value will be multiplied by the number of uses in the last hour to get the cost increase\n"
            )
            await ctx.send_help()
            return await ctx.send(help_txt)

        if command == "addcost":
            return await ctx.send(_("You can't add a cost to the addcost command."))

        is_global = await bank.is_global()
        if is_global:
            if ctx.author.id not in ctx.bot.owner_ids:
                return await ctx.send(_("You must be a bot owner to use this command while global bank is active."))
            if level != "global":
                return await ctx.send(_("Global bank is active, you must use the global level."))
        else:
            if level == "global":
                if ctx.author.id not in ctx.bot.owner_ids:
                    return await ctx.send(_("You must be a bot owner to use the global level."))
                return await ctx.send(_("You must enable global bank to use the global level."))

        command_obj: commands.Command = self.bot.get_command(command)
        if not command_obj:
            command_obj: app_commands.Command = self.bot.tree.get_command(command)
            if not command_obj:
                return await ctx.send(_("Command not found."))
            if not isinstance(command_obj, app_commands.Command):
                return await ctx.send(_("That is not a valid app command"))

        if isinstance(command_obj, commands.commands._AlwaysAvailableCommand):
            return await ctx.send(_("You can't add costs to commands that are always available!"))
        if isinstance(command_obj, (commands.Command, commands.HybridCommand)):
            if (command_obj.requires.privilege_level or 0) > await commands.requires.PrivilegeLevel.from_ctx(ctx):
                return await ctx.send(_("You can't add costs to commands you don't have permission to run!"))

        cost_obj = CommandCost(
            cost=cost,
            duration=duration,
            level=level,
            prompt=prompt,
            modifier=modifier,
            value=value,
        )
        overwrite_warning = _("This will overwrite the existing cost for this command. Continue?")
        costs = self.db.command_costs if is_global else self.db.get_conf(ctx.guild).command_costs
        if command in costs:
            view = ConfirmView(ctx.author)
            msg = await ctx.send(overwrite_warning, view=view)
            await view.wait()
            if not view.value:
                return await msg.edit(content=_("Not adding cost."))
            await msg.edit(content=_("{} cost updated.", view=None).format(command))
        else:
            await ctx.send(_("{} cost added.").format(command))

        if is_global:
            self.db.command_costs[command] = cost_obj
        else:
            conf = self.db.get_conf(ctx.guild)
            conf.command_costs[command] = cost_obj
        await self.save()

    @commands.command(name="banksetrole")
    @bank.is_owner_if_bank_global()
    @commands.admin_or_permissions(manage_guild=True)
    async def bank_set_role(self, ctx: commands.Context, role: discord.Role, creds: SetParser):
        """Set the balance of all user accounts that have a specific role

        Putting + or - signs before the amount will add/remove currency on the user's bank account instead.

        Examples:
        - `[p]banksetrole @everyone 420` - Sets everyones balance to 420
        - `[p]banksetrole @role +69` - Increases balance by 69 for everyone with the role
        - `[p]banksetrole @role -42` - Decreases balance by 42 for everyone with the role

        **Arguments**

        - `<role>` The role to set the currency of for each user that has it.
        - `<creds>` The amount of currency to set their balance to.
        """
        async with ctx.typing():
            if await bank.is_global():
                group = bank._config._get_base_group(bank._config.USER)
            else:
                group = bank._config._get_base_group(bank._config.MEMBER, str(ctx.guild.id))

            currency = await bank.get_currency_name(ctx.guild)
            max_bal = await bank.get_max_balance(ctx.guild)
            try:
                default_balance = await bank.get_default_balance(ctx.guild)
            except AttributeError:
                default_balance = await bank.get_default_balance()
            members: t.List[discord.Member] = [user for user in ctx.guild.members if role in user.roles]
            if not members:
                return await ctx.send(_("No users found with that role."))

            users_affected = 0
            total = 0
            async with group.all() as accounts:
                for mem in members:
                    uid = str(mem.id)
                    if uid in accounts:
                        wallet = accounts[uid]
                    else:
                        wallet = {"name": mem.display_name, "balance": default_balance, "created_at": 0}
                        accounts[uid] = wallet

                    match creds.operation:
                        case "deposit":
                            amount = min(max_bal - wallet["balance"], creds.sum)
                        case "withdraw":
                            amount = -min(wallet["balance"], creds.sum)
                        case _:  # set
                            amount = creds.sum - wallet["balance"]

                    accounts[uid]["balance"] += amount
                    total += amount
                    users_affected += 1

            if not users_affected:
                return await ctx.send(_("No users were affected."))
            if not total:
                return await ctx.send(_("No balances were changed."))
            grammar = _("user was") if users_affected == 1 else _("users were")
            msg = _("Balances for {} updated, total change was {}.").format(
                f"{users_affected} {grammar}", f"{total} {currency}"
            )
            await ctx.send(msg)
