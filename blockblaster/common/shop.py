"""The credit shop: boosters bought with the server's Red currency.

Each of the five bar boosters can have a credit price. Prices start empty, which means the booster is not sold for
credits. A price buys the same pack of 3 that coins buy. The credits go to no one, so buying is a sink for the server's
economy and nothing is ever paid out.

With a per-server bank each server sets its own prices. With a global bank one balance is shared by every server, so
only the bot owner sets the prices, once for everywhere. The settings dialog also shows what was spent today.
"""

import asyncio
import typing as t
from datetime import datetime, timezone

import regex
from redbot.core import bank

from .progress import PRICES

MAX_PRICE = 1_000_000_000
# The menu card's currency line fits this many characters
LINE_LIMIT = 40

# What the settings refusals call each booster
NAMES = {"tray": "Add Tray", "hand": "Hand", "shuffle": "Shuffle", "super": "Super Cat", "bomb": "Demolish"}

NOT_SOLD = "That booster isn't sold for credits here."
NO_SERVER = "Credits only work in a server."


class SettingsError(ValueError):
    """A settings change refused, worded for the admin"""


class ShopRefused(Exception):
    """A purchase that can't go through, worded for the player"""


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def clean_prices(value: t.Any) -> dict[str, int]:
    """The prices the admin sent, as {booster: price} for the boosters that have one.

    Expected: an object with all five boosters, each a whole number from 1 to MAX_PRICE, or None (or an empty
    string) for a booster that is not sold for credits.
    """
    if not isinstance(value, dict) or set(value) != set(PRICES):
        raise SettingsError("Expected a price for each booster, or empty for none.")
    prices = {}
    for booster in PRICES:
        price = value[booster]
        if price is None or price == "":
            continue
        if type(price) is not int or not 1 <= price <= MAX_PRICE:
            raise SettingsError(
                f"The {NAMES[booster]} price must be a whole number from 1 to {MAX_PRICE:,}, or empty to not sell it."
            )
        prices[booster] = price
    return prices


def cut_line(line: str) -> str:
    """The line cut to LINE_LIMIT whole characters (an emoji with its joiners counts as one)"""
    return "".join(regex.findall(r"\X", line)[:LINE_LIMIT])


class Shop:
    """The credit prices where a player is, what was spent today, and taking the credits"""

    def __init__(self, config: t.Any, money: t.Any = bank, today: t.Callable[[], str] = utc_today):
        self.config = config
        self.bank = money
        self.today = today
        self.lock = asyncio.Lock()

    async def group(self, guild: t.Any) -> t.Any:
        """Where the prices live: the server's own, or the owner's for every server when the bank is global"""
        return self.config if await self.bank.is_global() else self.config.guild(guild)

    async def prices(self, guild: t.Any) -> dict[str, int]:
        """The credit price of each booster that is sold for credits. Nothing outside a server"""
        if guild is None:
            return {}
        saved = await (await self.group(guild)).prices()
        return {booster: saved[booster] for booster in PRICES if booster in saved}

    async def save(self, guild: t.Any, value: t.Any) -> dict[str, int]:
        prices = clean_prices(value)
        await (await self.group(guild)).prices.set(prices)
        return prices

    async def currency(self, guild: t.Any) -> str:
        return await self.bank.get_currency_name(guild)

    async def today_spent(self, guild: t.Any) -> dict:
        """What was spent today where these prices apply, and by how many players"""
        tally = await (await self.group(guild)).tally()
        if tally.get("day") != self.today():
            return {"spent": 0, "players": 0}
        return {"spent": tally.get("spent", 0), "players": len(tally.get("players", []))}

    async def buy(self, member: t.Any, booster: str) -> int:
        """Take the booster's credit price from the player's balance and count it. Returns the price. Raises
        ShopRefused, with nothing taken, when the player can't pay it here"""
        guild = getattr(member, "guild", None)
        if guild is None:
            raise ShopRefused(NO_SERVER)
        price = (await self.prices(guild)).get(booster)
        if price is None:
            raise ShopRefused(NOT_SOLD)
        if await self.bank.get_balance(member) < price:
            raise ShopRefused(f"You need {price:,} {await self.currency(guild)} for that.")
        try:
            await self.bank.withdraw_credits(member, price)
        except ValueError as e:
            raise ShopRefused(f"You need {price:,} {await self.currency(guild)} for that.") from e
        await self.add_to_tally(member, guild, price)
        return price

    async def refund(self, member: t.Any, price: int) -> None:
        """Give back a price taken by `buy` when the booster could not be saved"""
        await self.bank.deposit_credits(member, price)
        group = await self.group(member.guild)
        async with self.lock:
            tally = await group.tally()
            if tally.get("day") == self.today():
                tally["spent"] = max(0, tally.get("spent", 0) - price)
                await group.tally.set(tally)

    async def add_to_tally(self, member: t.Any, guild: t.Any, price: int) -> None:
        group = await self.group(guild)
        async with self.lock:
            tally, today = await group.tally(), self.today()
            if tally.get("day") != today:
                tally = {"day": today, "spent": 0, "players": []}
            tally["spent"] = tally.get("spent", 0) + price
            if member.id not in tally["players"]:
                tally["players"].append(member.id)
            await group.tally.set(tally)
