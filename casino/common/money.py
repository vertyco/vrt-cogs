"""Bets, payouts and cooldowns, the same for every game: the original's GameEngine, with its fixes"""

import asyncio
import logging
import math
import time
import typing as t
from dataclasses import dataclass

from redbot.core import bank
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator

from ..db.tables import Player
from .catalog import GAME_NAMES, NO_BET_RANGE, NO_MULTIPLIER
from .memberships import perks_for
from .store import Store

_ = Translator("Casino", __file__)

log = logging.getLogger("red.vrt.casino.money")


class RedBank:
    """Red's bank, behind the few calls the casino makes, so tests can use a stand-in"""

    async def balance(self, who) -> int:
        return await bank.get_balance(who)

    async def can_spend(self, who, amount: int) -> bool:
        return await bank.can_spend(who, amount)

    async def withdraw(self, who, amount: int) -> None:
        await bank.withdraw_credits(who, amount)

    async def deposit(self, who, amount: int) -> int:
        """Adds the amount and returns the new balance. Over the bank's maximum, the balance becomes the maximum"""
        try:
            return await bank.deposit_credits(who, amount)
        except BalanceTooHigh as e:
            log.debug("Deposit hit the bank's maximum balance of %s", e.max_balance)
            return await bank.set_balance(who, e.max_balance)

    async def can_receive(self, who, amount: int) -> bool:
        guild = getattr(who, "guild", None)
        limit = await bank.get_max_balance(guild) if guild is not None else await bank.get_max_balance()
        return await bank.get_balance(who) + amount <= limit

    async def is_global(self) -> bool:
        return await bank.is_global()

    async def currency(self, guild) -> str:
        return await bank.get_currency_name(guild)


@dataclass
class Payout:
    total: int  # what the win paid, bonus included, or what was held
    bonus: int  # the part of total that came from the membership bonus
    held: bool  # the payout limit held total as pending credits
    returned: int  # a stake given back as it was, never multiplied (War's war bet)
    balance: int


@dataclass(frozen=True)
class Terms:
    """What a bet's payout follows, read when the stake is taken: settings changed mid-round wait for the next bet"""

    scope: int  # where the win is counted and a held win waits, even if the mode switches mid-round
    multiplier: float
    bonus: float  # the membership's bonus multiplier
    limit_on: bool
    limit_amount: int


def fmt_seconds(seconds: int) -> str:
    """12 hours, 1 minute and 5 seconds"""
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if hours:
        parts.append(_("1 hour") if hours == 1 else _("{count} hours").format(count=hours))
    if minutes:
        parts.append(_("1 minute") if minutes == 1 else _("{count} minutes").format(count=minutes))
    if seconds:
        parts.append(_("1 second") if seconds == 1 else _("{count} seconds").format(count=seconds))
    if not parts:
        return _("0 seconds")
    if len(parts) == 1:
        return parts[0]
    return _("{rest} and {last}").format(rest=", ".join(parts[:-1]), last=parts[-1])


def range_problem(key: str, min_bet: int | None, max_bet: int | None, amount: int) -> str | None:
    if key in NO_BET_RANGE:
        return _("You need some credits to go all in.") if amount <= 0 else None
    if min_bet is None or max_bet is None or min_bet <= amount <= max_bet:
        return None
    if min_bet == max_bet:
        return _("Bets here are exactly {amount}.").format(amount=min_bet)
    return _("Bets here are {low} to {high}.").format(low=min_bet, high=max_bet)


class Money:
    def __init__(self, store: Store, bank_: t.Any, clock: t.Callable[[], float] = time.time):
        self.store = store
        self.bank = bank_
        self.clock = clock
        # One lock per player: Red's bank may be global while the casino runs per server, so the same account can
        # play in two servers at once
        self.locks: dict[int, asyncio.Lock] = {}

    def lock(self, scope: int, user_id: int) -> asyncio.Lock:
        return self.locks.setdefault(user_id, asyncio.Lock())

    async def ready_in(self, scope: int, user_id: int, key: str) -> int:
        """Whole seconds until the player may play the game again, after their membership's reduction"""
        row = await self.store.player_game(scope, user_id, key)
        perks = await perks_for(self.store, scope, user_id)
        return max(0, math.ceil(row.ready_at - perks.reduction - self.clock()))

    async def problem(self, scope: int, member, key: str, amount: int, choice_problem: str | None = None) -> str | None:
        """Why the bet can't be placed, checked in the original's order, or None when it can"""
        name = GAME_NAMES[key]
        casino = await self.store.casino(scope)
        game = await self.store.game(scope, key)
        perks = await perks_for(self.store, scope, member.id)
        if not casino.is_open:
            return _("The casino is closed.")
        if not game.is_open:
            return _("{game} is closed.").format(game=name)
        if game.access > perks.access:
            return _("{game} needs access level {needed}. Yours is {level}. A higher membership unlocks it.").format(
                game=name, needed=game.access, level=perks.access
            )
        if choice_problem:
            return choice_problem
        if out_of_range := range_problem(key, game.min_bet, game.max_bet, amount):
            return out_of_range
        if not await self.bank.can_spend(member, amount):
            return _("You don't have enough credits for that bet.")
        wait = await self.ready_in(scope, member.id, key)
        if wait > 0:
            return _("{game} is ready again in {time}.").format(game=name, time=fmt_seconds(wait))
        return None

    async def terms(self, scope: int, user_id: int, key: str) -> Terms:
        """The payout terms in force now, for a bet about to be placed"""
        game = await self.store.game(scope, key)
        casino = await self.store.casino(scope)
        perks = await perks_for(self.store, scope, user_id)
        return Terms(scope, game.multiplier or 0, perks.bonus, casino.limit_on, casino.limit_amount)

    async def stake(self, scope: int, member, key: str, amount: int, choice_problem: str | None = None) -> str | None:
        """Takes the bet when every check passes, counts the game as played and starts its cooldown.
        Returns the problem instead when one fails"""
        async with self.lock(scope, member.id):
            problem = await self.problem(scope, member, key, amount, choice_problem)
            if problem:
                return problem
            await self.bank.withdraw(member, amount)
            row = await self.store.player_game(scope, member.id, key)
            game = await self.store.game(scope, key)
            row.played += 1
            row.ready_at = self.clock() + game.cooldown
            await row.save()
        return None

    async def extra(self, scope: int, member, amount: int) -> bool:
        """A second stake mid-round (Blackjack's double, War's war bet). False when the player can't cover it"""
        async with self.lock(scope, member.id):
            if not await self.bank.can_spend(member, amount):
                return False
            await self.bank.withdraw(member, amount)
        return True

    async def give_back(self, scope: int, member, amount: int) -> int:
        """Returns a stake as it was: a push, a surrender's half, or a refund. Not a win"""
        async with self.lock(scope, member.id):
            if amount > 0:
                return await self.bank.deposit(member, amount)
            return await self.bank.balance(member)

    async def win(self, member, key: str, amount: int, terms: Terms, returned: int = 0) -> Payout:
        """Pays a win under the terms its bet was placed with. amount is what the original multiplied: the stake, or
        the stake times a game's factor"""
        async with self.lock(terms.scope, member.id):
            if key in NO_MULTIPLIER:
                total, bonus = amount, 0
            else:
                base = round(amount * terms.multiplier)
                total = round(base * terms.bonus)
                bonus = total - base
            row = await self.store.player_game(terms.scope, member.id, key)
            row.won += 1
            await row.save()
            held = terms.limit_on and total > terms.limit_amount
            if held:
                await self.store.add_pending(terms.scope, member.id, total)
                balance = await self.bank.balance(member)
            else:
                balance = await self.bank.deposit(member, total)
            if returned:
                balance = await self.bank.deposit(member, returned)
        return Payout(total=total, bonus=bonus, held=held, returned=returned, balance=balance)

    async def release(self, scope: int, member) -> tuple[int, str | None]:
        """Pays out a player's pending credits. Returns the amount, or a problem and leaves them pending"""
        async with self.lock(scope, member.id):
            player = await self.store.player(scope, member.id)
            amount = player.pending
            if amount <= 0:
                return 0, _("They don't have any credits pending.")
            if not await self.bank.can_receive(member, amount):
                return amount, _("That would put them over the bank's maximum balance, so it stays pending.")
            await self.bank.deposit(member, amount)
            await Player.update({Player.pending: Player.pending - amount}).where(Player.id == player.id)
        return amount, None
