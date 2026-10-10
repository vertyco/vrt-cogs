"""
Score payouts for the included games, the way Neopets pays for its games.

After a round, a player may cash in its score. The score times the game's rate is paid in the bank's currency, up
to a most-per-cash-in, and each player gets a few cash-ins per game per day. Playing again first gives up the
unsent score, so players save their cash-ins for their best rounds. A cheater can't earn more than an honest
player, since every cash-in is capped.

With a per-server bank each server sets its own payouts. With a global bank one balance is shared by every
server, so only the bot owner sets them, once for everywhere, and the daily cash-ins count across servers.

Game cogs keep their own payout settings; this only covers the games that come with the hub.
"""

import asyncio
import math
import typing as t
from datetime import datetime, timezone

from redbot.core import bank
from redbot.core.errors import BalanceTooHigh

from .looks import SettingsError

DEFAULT_CAP = 1000
MAX_RATE = 1_000_000
DEFAULT_PLAYS = 3
MAX_CAP = 1_000_000_000
MAX_PLAYS = 100

PAYOUTS_OFF = "This game doesn't pay out here."
NO_SERVER = "Cash-ins only work in a server."
NONE_LEFT = "You've used every cash-in for this game today. They come back at midnight UTC."
NOTHING_EARNED = "That score isn't worth anything yet. Score more to earn some."
BALANCE_FULL = "Your balance is already at the maximum."


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_settings(game: t.Any) -> dict:
    return {"on": False, "rate": game.rate, "cap": DEFAULT_CAP, "plays": DEFAULT_PLAYS}


def game_settings(saved: dict, game: t.Any) -> dict:
    return {**default_settings(game), **saved.get(game.key, {})}


def check_score(score: t.Any) -> None:
    # A bug in a game, so it raises instead of telling the player
    if type(score) is not int or score < 0:
        raise ValueError(f"A payout score must be a whole number of 0 or more, got {score!r}")


def worth(score: int, settings: dict) -> int:
    # Rounded first, so a rate like 2.3 doesn't lose a credit to float error (2.3 * 100 = 229.99999999999997)
    return min(math.floor(round(score * settings["rate"], 6)), settings["cap"])


def is_number(value: t.Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_whole(value: t.Any) -> bool:
    return type(value) is int


def clean_game(value: t.Any, name: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"on", "rate", "cap", "plays"}:
        raise SettingsError(f"{name}: expected on, rate, cap and plays.")
    if not isinstance(value["on"], bool):
        raise SettingsError(f"{name}: on must be true or false.")
    if not is_number(value["rate"]) or not 0 < value["rate"] <= MAX_RATE:
        raise SettingsError(f"{name}: the rate must be more than 0 and at most {MAX_RATE:,}.")
    if not is_whole(value["cap"]) or not 1 <= value["cap"] <= MAX_CAP:
        raise SettingsError(f"{name}: the most per cash-in must be a whole number from 1 to {MAX_CAP:,}.")
    if not is_whole(value["plays"]) or not 1 <= value["plays"] <= MAX_PLAYS:
        raise SettingsError(f"{name}: cash-ins a day must be a whole number from 1 to {MAX_PLAYS}.")
    return {"on": value["on"], "rate": value["rate"], "cap": value["cap"], "plays": value["plays"]}


def merge_payouts(saved: dict, value: t.Any, games: list[t.Any]) -> dict:
    """The payouts to save: the sent games checked, plus the saved settings of games that weren't sent"""
    if not isinstance(value, dict):
        raise SettingsError("Expected payouts by activity key.")
    by_key = {game.key: game for game in games}
    merged = dict(saved)
    for key, settings in value.items():
        if key not in by_key:
            raise SettingsError(f"{key} doesn't pay out.")
        merged[key] = clean_game(settings, by_key[key].name)
    return merged


class Payouts:
    """
    Each scope's payout settings, each player's cash-ins today, and the bank deposits. `games` holds the included
    games by key, each with a key, name, unit (what one point is called) and rate (what one point pays by default)
    """

    def __init__(self, config: t.Any, money: t.Any = bank, today: t.Callable[[], str] = utc_today):
        self.config = config
        self.bank = money
        self.today = today
        self.games: dict[str, t.Any] = {}
        self.lock = asyncio.Lock()

    async def saved(self, guild: t.Any) -> dict:
        if await self.bank.is_global():
            return await self.config.payouts()
        return await self.config.guild(guild).payouts()

    async def save(self, guild: t.Any, value: t.Any) -> None:
        group = self.config if await self.bank.is_global() else self.config.guild(guild)
        await group.payouts.set(merge_payouts(await group.payouts(), value, list(self.games.values())))

    async def ledger(self, member: t.Any) -> t.Any:
        """Where a player's cash-ins today are counted: across servers when they share one balance"""
        if await self.bank.is_global():
            return self.config.user(member).cashed
        return self.config.member(member).cashed

    async def state(self, guild: t.Any, keys: t.Collection[str]) -> dict:
        """What the Payouts tab shows for the included games among these keys"""
        saved = await self.saved(guild)
        rows = [
            {
                "key": game.key,
                "name": game.name,
                "unit": game.unit,
                **game_settings(saved, game),
                "defaults": default_settings(game),
            }
            for game in self.games.values()
            if game.key in keys
        ]
        return {
            "global": await self.bank.is_global(),
            "currency": await self.bank.get_currency_name(guild),
            "games": rows,
        }

    async def used(self, member: t.Any, key: str) -> int:
        cashed = await (await self.ledger(member))()
        return cashed.get("counts", {}).get(key, 0) if cashed.get("day") == self.today() else 0

    async def settings_for(self, member: t.Any, key: str) -> dict | None:
        """The game's payout settings where the player is, or None when it doesn't pay out there"""
        game = self.games.get(key)
        if game is None or getattr(member, "guild", None) is None:
            return None
        settings = game_settings(await self.saved(member.guild), game)
        return settings if settings["on"] else None

    async def offer(self, member: t.Any, key: str, score: int) -> dict | None:
        """What cashing in this score would pay, or None when the game doesn't pay out where the player is"""
        check_score(score)
        settings = await self.settings_for(member, key)
        if settings is None:
            return None
        return {
            "worth": worth(score, settings),
            "left": max(0, settings["plays"] - await self.used(member, key)),
            "plays": settings["plays"],
            "currency": await self.bank.get_currency_name(member.guild),
        }

    async def cash_in(self, member: t.Any, key: str, score: int) -> dict:
        """Pay a score and count the cash-in. Returns {"error": text} without counting one when nothing is paid"""
        check_score(score)
        if getattr(member, "guild", None) is None:
            return {"error": NO_SERVER}
        async with self.lock:
            settings = await self.settings_for(member, key)
            if settings is None:
                return {"error": PAYOUTS_OFF}
            ledger = await self.ledger(member)
            cashed, today = await ledger(), self.today()
            counts = cashed.get("counts", {}) if cashed.get("day") == today else {}
            if counts.get(key, 0) >= settings["plays"]:
                return {"error": NONE_LEFT}
            amount = worth(score, settings)
            if amount <= 0:
                return {"error": NOTHING_EARNED}
            paid, balance = await self.deposit(member, amount)
            if paid <= 0:
                return {"error": BALANCE_FULL}
            counts[key] = counts.get(key, 0) + 1
            await ledger.set({"day": today, "counts": counts})
        return {
            "paid": paid,
            "left": settings["plays"] - counts[key],
            "balance": balance,
            "currency": await self.bank.get_currency_name(member.guild),
        }

    async def deposit(self, member: t.Any, amount: int) -> tuple[int, int]:
        """Pay up to the bank's maximum balance. Returns what was paid and the new balance"""
        before = await self.bank.get_balance(member)
        try:
            balance = await self.bank.deposit_credits(member, amount)
        except BalanceTooHigh as e:
            balance = await self.bank.set_balance(member, e.max_balance)
        return balance - before, balance
