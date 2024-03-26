import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import discord
from redbot.core import bank, commands, errors
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.bankevents")
_ = Translator("BankEvents", __file__)


class PayDayClaimInformation(NamedTuple):
    member_id: int
    guild_id: int
    amount_received: int
    is_global: bool


class PaydayOverride(MixinMeta):
    @commands.command(hidden=True)
    @commands.guild_only()
    async def payday_override(self, ctx: commands.Context):
        cog = ctx.bot.get_cog("Economy")
        if cog is None:
            raise commands.ExtensionError("Economy cog is not loaded.")

        author = ctx.author
        guild = ctx.guild

        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        credits_name = await bank.get_currency_name(guild)
        if await bank.is_global():
            next_payday = await cog.config.user(author).next_payday() + await cog.config.PAYDAY_TIME()
            if cur_time >= next_payday:
                credits_to_give = await cog.config.PAYDAY_CREDITS()
                try:
                    await bank.deposit_credits(author, credits_to_give)
                except errors.BalanceTooHigh as exc:
                    old_bal = await bank.get_balance(author)
                    await bank.set_balance(author, exc.max_balance)
                    await ctx.send(
                        _(
                            "You've reached the maximum amount of {currency}! "
                            "Please spend some more \N{GRIMACING FACE}\n\n"
                            "You currently have {new_balance} {currency}."
                        ).format(currency=credits_name, new_balance=humanize_number(exc.max_balance))
                    )
                    payload = PayDayClaimInformation(author.id, guild.id, exc.max_balance - old_bal, True)
                    ctx.bot.dispatch("red_economy_payday_claim", payload)
                    return

                await cog.config.user(author).next_payday.set(cur_time)

                pos = await bank.get_leaderboard_position(author)
                await ctx.send(
                    _(
                        "{author.mention} Here, take some {currency}. "
                        "Enjoy! (+{amount} {currency}!)\n\n"
                        "You currently have {new_balance} {currency}.\n\n"
                        "You are currently #{pos} on the global leaderboard!"
                    ).format(
                        author=author,
                        currency=credits_name,
                        amount=humanize_number(credits_to_give),
                        new_balance=humanize_number(await bank.get_balance(author)),
                        pos=humanize_number(pos) if pos else pos,
                    )
                )
                payload = PayDayClaimInformation(author.id, guild.id, credits_to_give, True)
                ctx.bot.dispatch("red_economy_payday_claim", payload)
            else:
                relative_time = discord.utils.format_dt(
                    datetime.now(timezone.utc) + timedelta(seconds=next_payday - cur_time), "R"
                )
                await ctx.send(
                    _("{author.mention} Too soon. Your next payday is {relative_time}.").format(
                        author=author, relative_time=relative_time
                    )
                )
        else:
            # Gets the users latest successfully payday and adds the guilds payday time
            next_payday = await cog.config.member(author).next_payday() + await cog.config.guild(guild).PAYDAY_TIME()
            if cur_time >= next_payday:
                credit_amount = await cog.config.guild(guild).PAYDAY_CREDITS()
                for role in author.roles:
                    role_credits = await cog.config.role(role).PAYDAY_CREDITS()  # Nice variable name
                    if role_credits > credit_amount:
                        credit_amount = role_credits
                try:
                    await bank.deposit_credits(author, credit_amount)
                except errors.BalanceTooHigh as exc:
                    old_bal = await bank.get_balance(author)
                    await bank.set_balance(author, exc.max_balance)
                    await ctx.send(
                        _(
                            "You've reached the maximum amount of {currency}! "
                            "Please spend some more \N{GRIMACING FACE}\n\n"
                            "You currently have {new_balance} {currency}."
                        ).format(currency=credits_name, new_balance=humanize_number(exc.max_balance))
                    )
                    payload = PayDayClaimInformation(author.id, guild.id, exc.max_balance - old_bal, True)
                    ctx.bot.dispatch("red_economy_payday_claim", payload)
                    return

                # Sets the latest payday time to the current time
                next_payday = cur_time

                await cog.config.member(author).next_payday.set(next_payday)
                pos = await bank.get_leaderboard_position(author)
                await ctx.send(
                    _(
                        "{author.mention} Here, take some {currency}. "
                        "Enjoy! (+{amount} {currency}!)\n\n"
                        "You currently have {new_balance} {currency}.\n\n"
                        "You are currently #{pos} on the global leaderboard!"
                    ).format(
                        author=author,
                        currency=credits_name,
                        amount=humanize_number(credit_amount),
                        new_balance=humanize_number(await bank.get_balance(author)),
                        pos=humanize_number(pos) if pos else pos,
                    )
                )
                payload = PayDayClaimInformation(author.id, guild.id, credit_amount, False)
                ctx.bot.dispatch("red_economy_payday_claim", payload)
            else:
                relative_time = discord.utils.format_dt(
                    datetime.now(timezone.utc) + timedelta(seconds=next_payday - cur_time), "R"
                )
                await ctx.send(
                    _("{author.mention} Too soon. Your next payday is {relative_time}.").format(
                        author=author, relative_time=relative_time
                    )
                )
