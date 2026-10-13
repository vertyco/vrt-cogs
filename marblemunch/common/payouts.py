"""
Marble payouts, the way Neopets pays for its games.

After a round, a player may cash in the marbles they munched. Each marble pays the rate in the bank's currency, up
to a most-per-cash-in, and each player gets a few cash-ins a day. The next round they finish replaces the unsent
one, so players save their cash-ins for their best rounds. A cheater can't earn more than an honest player, since
every cash-in is capped. The settings dialog also shows what was paid today.

With a per-server bank each server sets its own payouts. With a global bank one balance is shared by every server,
so only the bot owner sets them, once for everywhere, and the daily cash-ins count across servers.
"""

import asyncio
import math
import typing as t
from datetime import datetime, timezone

from redbot.core import bank
from redbot.core.errors import BalanceTooHigh

DEFAULTS = {"on": False, "rate": 100, "cap": 1000, "plays": 3}
MAX_RATE = 1_000_000
MAX_CAP = 1_000_000_000
MAX_PLAYS = 100

PAYOUTS_OFF = "Marble Munch doesn't pay out here."
NONE_LEFT = "You've used every cash-in for today. They come back at midnight UTC."
NOTHING_EARNED = "Munch some marbles first: that round isn't worth anything."
BALANCE_FULL = "Your balance is already at the maximum."


class SettingsError(ValueError):
    """A settings change refused, worded for the admin"""


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def worth(marbles: int, settings: dict) -> int:
    # Rounded first, so a rate like 2.3 doesn't lose a credit to float error (2.3 * 100 = 229.99999999999997)
    return min(math.floor(round(marbles * settings["rate"], 6)), settings["cap"])


def is_whole(value: t.Any) -> bool:
    return type(value) is int


def clean_settings(value: t.Any) -> dict:
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise SettingsError("Expected on, rate, cap and plays.")
    rate = value["rate"]
    if not isinstance(value["on"], bool):
        raise SettingsError("Payouts must be on or off.")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= MAX_RATE:
        raise SettingsError(f"Credits per marble must be more than 0 and at most {MAX_RATE:,}.")
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

    async def today_paid(self, guild: t.Any) -> dict:
        """What was paid today where these settings apply, and to how many players"""
        tally = await (await self.group(guild)).tally()
        if tally.get("day") != self.today():
            return {"paid": 0, "players": 0}
        return {"paid": tally.get("paid", 0), "players": len(tally.get("players", []))}

    async def offer(self, member: t.Any, marbles: int) -> dict | None:
        """What cashing in these marbles would pay, or None when payouts are off where the player is"""
        settings = await self.settings(member.guild)
        if not settings["on"]:
            return None
        return {
            "worth": worth(marbles, settings),
            "left": max(0, settings["plays"] - await self.used(member)),
            "plays": settings["plays"],
            "currency": await self.bank.get_currency_name(member.guild),
        }

    async def cash_in(self, member: t.Any, marbles: int) -> dict:
        """Pay the marbles and count the cash-in. Returns {"error": text} without counting one when nothing is paid"""
        async with self.lock:
            settings = await self.settings(member.guild)
            if not settings["on"]:
                return {"error": PAYOUTS_OFF}
            ledger = await self.ledger(member)
            cashed, today = await ledger(), self.today()
            count = cashed.get("count", 0) if cashed.get("day") == today else 0
            if count >= settings["plays"]:
                return {"error": NONE_LEFT}
            amount = worth(marbles, settings)
            if amount <= 0:
                return {"error": NOTHING_EARNED}
            paid, balance = await self.deposit(member, amount)
            if paid <= 0:
                return {"error": BALANCE_FULL}
            await ledger.set({"day": today, "count": count + 1})
            await self.add_to_tally(member, paid)
        return {
            "paid": paid,
            "left": settings["plays"] - count - 1,
            "balance": balance,
            "currency": await self.bank.get_currency_name(member.guild),
        }

    async def add_to_tally(self, member: t.Any, paid: int) -> None:
        group = await self.group(member.guild)
        tally, today = await group.tally(), self.today()
        if tally.get("day") != today:
            tally = {"day": today, "paid": 0, "players": []}
        tally["paid"] = tally.get("paid", 0) + paid
        if member.id not in tally["players"]:
            tally["players"].append(member.id)
        await group.tally.set(tally)

    async def deposit(self, member: t.Any, amount: int) -> tuple[int, int]:
        """Pay up to the bank's maximum balance. Returns what was paid and the new balance"""
        before = await self.bank.get_balance(member)
        try:
            balance = await self.bank.deposit_credits(member, amount)
        except BalanceTooHigh as e:
            balance = await self.bank.set_balance(member, e.max_balance)
        return balance - before, balance
