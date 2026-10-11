"""
FarmCoin payouts, the way Neopets pays for its games.

At the Market's bank counter a player may turn FarmCoins into the server's credits. Each FarmCoin pays the rate in
the bank's currency, up to a most-per-cash-in, and each player gets a few cash-ins a day. A player can't earn more
than the cap from one cash-in, however many FarmCoins they hold, so admins know the most FarmCord can pay a day.

With a per-server bank each server sets its own payouts. With a global bank one balance is shared by every server,
so only the bot owner sets them, once for everywhere, and the daily cash-ins count across servers.
"""

import asyncio
import logging
import math
import typing as t
from datetime import datetime, timezone

from redbot.core import bank
from redbot.core.errors import BalanceTooHigh

log = logging.getLogger("red.vrt.farmcord")

DEFAULTS = {"on": False, "rate": 1, "cap": 1000, "plays": 3}
MAX_RATE = 1_000_000
MAX_CAP = 1_000_000_000
MAX_PLAYS = 100
# The most FarmCoins the bot takes in one request. A rate tiny enough makes the cap worth endless FarmCoins, and the
# most one cash-in takes stops here instead
MAX_COINS = 10**12

PAYOUTS_OFF = "FarmCord doesn't pay out here."
NONE_LEFT = "You've used every cash-in for today. They come back at midnight UTC."
NOTHING_EARNED = "That many FarmCoins aren't worth a credit yet. Convert more."
BALANCE_FULL = "Your balance is already at the maximum."
SHAPE = "Expected on, rate, cap and plays."


class SettingsError(ValueError):
    """A settings change refused, worded for the admin"""


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def worth(coins: int, settings: dict) -> int:
    # Rounded first, so a rate like 2.3 doesn't lose a credit to float error (2.3 * 100 = 229.99999999999997)
    return min(math.floor(round(coins * settings["rate"], 6)), settings["cap"])


def most_coins(settings: dict) -> int:
    """The most FarmCoins one cash-in takes. Any more would pay nothing past the cap, so they stay on the farm"""
    return math.ceil(min(round(settings["cap"] / settings["rate"], 6), MAX_COINS))


def is_whole(value: t.Any) -> bool:
    return type(value) is int


def clean_settings(value: t.Any) -> dict:
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise SettingsError(SHAPE)
    rate = value["rate"]
    if not isinstance(value["on"], bool):
        raise SettingsError("Payouts must be on or off.")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= MAX_RATE:
        raise SettingsError(f"Credits per FarmCoin must be more than 0 and at most {MAX_RATE:,}.")
    if not is_whole(value["cap"]) or not 1 <= value["cap"] <= MAX_CAP:
        raise SettingsError(f"The most per cash-in must be a whole number from 1 to {MAX_CAP:,}.")
    if not is_whole(value["plays"]) or not 1 <= value["plays"] <= MAX_PLAYS:
        raise SettingsError(f"Cash-ins a day must be a whole number from 1 to {MAX_PLAYS}.")
    return {name: value[name] for name in DEFAULTS}


class Payouts:
    """The payout settings where a player is, their cash-ins today, and the bank deposits"""

    def __init__(self, config: t.Any, money: t.Any = bank, today: t.Callable[[], str] = utc_today):
        self.config = config
        self.bank = money
        self.today = today
        self.lock = asyncio.Lock()

    async def group(self, guild: t.Any) -> t.Any:
        """Where the settings live: the server's own, or the owner's for every server when the bank is global"""
        return self.config if await self.bank.is_global() else self.config.guild(guild)

    async def settings(self, guild: t.Any) -> dict:
        return {**DEFAULTS, **await (await self.group(guild)).payouts()}

    async def save(self, guild: t.Any, value: t.Any) -> dict:
        settings = clean_settings(value)
        await (await self.group(guild)).payouts.set(settings)
        return settings

    async def ledger(self, member: t.Any) -> t.Any:
        """Where a player's cash-ins today are counted: across servers when they share one balance"""
        if await self.bank.is_global():
            return self.config.user(member).cashed
        return self.config.member(member).cashed

    async def used(self, member: t.Any) -> int:
        cashed = await (await self.ledger(member))()
        return cashed.get("count", 0) if cashed.get("day") == self.today() else 0

    async def offer(self, member: t.Any, coins: int) -> dict | None:
        """What converting these FarmCoins would pay, or None when payouts are off where the player is"""
        settings = await self.settings(member.guild)
        if not settings["on"]:
            return None
        return {
            "worth": worth(coins, settings),
            "left": max(0, settings["plays"] - await self.used(member)),
            "plays": settings["plays"],
            "currency": await self.bank.get_currency_name(member.guild),
        }

    async def cash_in(self, member: t.Any, coins: int) -> dict:
        """Pay for the FarmCoins and count the cash-in. Returns {"error": text} without counting one when nothing is
        paid. Once the bank has paid, nothing here raises: the caller gives the FarmCoins back when this raises, and
        the player would be paid twice"""
        async with self.lock:
            settings = await self.settings(member.guild)
            if not settings["on"]:
                return {"error": PAYOUTS_OFF}
            ledger = await self.ledger(member)
            cashed, today = await ledger(), self.today()
            count = cashed.get("count", 0) if cashed.get("day") == today else 0
            if count >= settings["plays"]:
                return {"error": NONE_LEFT}
            amount = worth(coins, settings)
            if amount <= 0:
                return {"error": NOTHING_EARNED}
            currency = await self.bank.get_currency_name(member.guild)
            paid, balance = await self.deposit(member, amount)
            if paid <= 0:
                return {"error": BALANCE_FULL}
            try:
                await ledger.set({"day": today, "count": count + 1})
            except Exception as e:
                log.error("Paid user %s for a cash-in but couldn't count it", member.id, exc_info=e)
        return {"paid": paid, "left": settings["plays"] - count - 1, "balance": balance, "currency": currency}

    async def deposit(self, member: t.Any, amount: int) -> tuple[int, int]:
        """Pay up to the bank's maximum balance. Returns what was paid and the new balance"""
        before = await self.bank.get_balance(member)
        try:
            balance = await self.bank.deposit_credits(member, amount)
        except BalanceTooHigh as e:
            balance = await self.bank.set_balance(member, e.max_balance)
        return balance - before, balance
