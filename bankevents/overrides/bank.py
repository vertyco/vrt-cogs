from typing import Dict, NamedTuple, Optional, Union

import discord
from redbot.core import bank
from redbot.core.bank import _cache_is_global
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh, BankPruneError
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_number

_bot_ref: Optional[Red] = None


def init(bot: Red):
    global _bot_ref
    _bot_ref = bot


# Thanks to YamiKaitou for starting the work on this 2+ years ago
# Maybe one day it will be merged
# https://github.com/Cog-Creators/Red-DiscordBot/pull/5325
class BankTransferInformation(NamedTuple):
    transfer_amount: int
    sender_id: int
    recipient_id: int
    guild_id: int  # 0 if global bank
    sender_new_balance: int
    recipient_new_balance: int


class BankSetBalanceInformation(NamedTuple):
    recipient_id: int
    guild_id: int  # 0 if global bank
    recipient_old_balance: int
    recipient_new_balance: int


class BankWithdrawDepositInformation(NamedTuple):
    member_id: int
    guild_id: int  # 0 if global bank
    amount: int
    old_balance: int
    new_balance: int


class BankPruneInformation(NamedTuple):
    scope: int  # 1 for guild, 2 for global, 3 for user
    # {user_id: {name: str, balance: int, created_at: int}}
    pruned_users: Dict[str, Dict[str, Union[int, str]]]


async def set_balance(member: Union[discord.Member, discord.User], amount: int) -> int:
    if not isinstance(amount, int):
        raise TypeError("Amount must be of type int, not {}.".format(type(amount)))
    if amount < 0:
        raise ValueError("Not allowed to have negative balance.")
    guild = getattr(member, "guild", None)
    max_bal = await bank.get_max_balance(guild)
    if amount > max_bal:
        currency = await bank.get_currency_name(guild)
        raise BalanceTooHigh(user=member, max_balance=max_bal, currency_name=currency)
    if await bank.is_global():
        group = bank._config.user(member)
    else:
        group = bank._config.member(member)

    old_balance = await group.balance()
    await group.balance.set(amount)

    if await group.created_at() == 0:
        time = bank._encoded_current_time()
        await group.created_at.set(time)
    if await group.name() == "":
        await group.name.set(member.display_name)
    payload = BankSetBalanceInformation(member.id, (0 if _cache_is_global else guild.id), old_balance, amount)
    _bot_ref.dispatch("red_bank_set_balance", payload)
    return amount


async def transfer_credits(
    from_: Union[discord.Member, discord.User],
    to: Union[discord.Member, discord.User],
    amount: int,
) -> int:
    if not isinstance(amount, int):
        raise TypeError("Transfer amount must be of type int, not {}.".format(type(amount)))
    if bank._invalid_amount(amount):
        raise ValueError("Invalid transfer amount {} <= 0".format(humanize_number(amount, override_locale="en_US")))
    guild = getattr(to, "guild", None)

    max_bal = await bank.get_max_balance(guild)
    if await bank.get_balance(to) + amount > max_bal:
        currency = await bank.get_currency_name(guild)
        raise bank.errors.BalanceTooHigh(user=to.display_name, max_balance=max_bal, currency_name=currency)

    sender_new = await withdraw_credits(from_, amount)
    recipient_new = await deposit_credits(to, amount)
    payload = BankTransferInformation(
        amount, from_.id, to.id, (0 if _cache_is_global else guild.id), sender_new, recipient_new
    )
    _bot_ref.dispatch("red_bank_transfer_credits", payload)
    return recipient_new


async def withdraw_credits(member: discord.Member, amount: int) -> int:
    if not isinstance(amount, int):
        raise TypeError("Withdrawal amount must be of type int, not {}.".format(type(amount)))
    if bank._invalid_amount(amount):
        raise ValueError("Invalid withdrawal amount {} < 0".format(humanize_number(amount, override_locale="en_US")))

    bal = await bank.get_balance(member)
    if amount > bal:
        raise ValueError(
            "Insufficient funds {} > {}".format(
                humanize_number(amount, override_locale="en_US"),
                humanize_number(bal, override_locale="en_US"),
            )
        )
    payload = BankWithdrawDepositInformation(
        member.id, (0 if _cache_is_global else member.guild.id), amount, bal, bal - amount
    )
    _bot_ref.dispatch("red_bank_withdraw_credits", payload)
    return await set_balance(member, bal - amount)


async def deposit_credits(member: discord.Member, amount: int) -> int:
    if not isinstance(amount, int):
        raise TypeError("Deposit amount must be of type int, not {}.".format(type(amount)))
    if bank._invalid_amount(amount):
        raise ValueError("Invalid deposit amount {} <= 0".format(humanize_number(amount, override_locale="en_US")))

    bal = await bank.get_balance(member)
    payload = BankWithdrawDepositInformation(
        member.id, (0 if _cache_is_global else member.guild.id), amount, bal, bal + amount
    )
    _bot_ref.dispatch("red_bank_deposit_credits", payload)
    return await set_balance(member, amount + bal)


async def wipe_bank(guild: Optional[discord.Guild] = None) -> None:
    if await bank.is_global():
        await bank._config.clear_all_users()
        _bot_ref.dispatch("red_bank_wipe", -1)
    else:
        await bank._config.clear_all_members(guild)
        _bot_ref.dispatch("red_bank_wipe", getattr(guild, "id", 0))


async def bank_prune(bot: Red, guild: discord.Guild = None, user_id: int = None) -> None:
    global_bank = await bank.is_global()
    if not global_bank and guild is None:
        raise BankPruneError("'guild' can't be None when pruning a local bank")

    _guilds = set()
    _uguilds = set()
    if global_bank:
        group = bank._config._get_base_group(bank._config.USER)
        if user_id is None:
            async for g in AsyncIter(bot.guilds, steps=100):
                if g.unavailable:
                    _uguilds.add(g)
                elif not g.chunked:
                    _guilds.add(g)
    else:
        group = bank._config._get_base_group(bank._config.MEMBER, str(guild.id))
        if guild is None:
            raise BankPruneError("'guild' can't be None when pruning a local bank")
        if user_id is None:
            if guild.unavailable:
                _uguilds.add(guild)
            else:
                _guilds.add(guild)

    if user_id is None:
        for _guild in _guilds:
            await _guild.chunk()
        members = bot.get_all_members() if global_bank else guild.members
        valid_users = {str(m.id) for m in members if m.guild not in _uguilds}
        accounts = await group.all()
        valid_accounts = {k: v for k, v in accounts.items() if k in valid_users}
        await group.set(valid_accounts)
        pruned = {k: v for k, v in accounts.items() if k not in valid_users}
    else:
        pruned = {}
        user_id = str(user_id)
        accounts = await group.all()
        if user_id in accounts:
            pruned = {user_id: accounts[user_id]}
            await group.clear_raw(user_id)

    if guild is None and user_id is None:
        scope = 1  # prune global
    if guild is not None and user_id is None:
        scope = 2  # prune server
    else:
        scope = 3  # prune user

    payload = BankPruneInformation(scope, pruned)

    _bot_ref.dispatch("red_bank_prune_accounts", payload)


async def set_global(global_: bool) -> bool:
    if (await bank.is_global()) is global_:
        return global_

    global _cache_is_global

    if await bank.is_global():
        await bank._config.clear_all_users()
        _bot_ref.dispatch("red_bank_wipe", -1)
    else:
        await bank._config.clear_all_members()
        _bot_ref.dispatch("red_bank_wipe", 0)

    await bank._config.is_global.set(global_)
    _cache_is_global = global_
    _bot_ref.dispatch("red_bank_set_global", global_)
    return global_
