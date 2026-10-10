"""Membership tiers: what a player's tier gives them, checking a new or changed tier, and the 5 minute updater"""

import asyncio
import logging
import re
import typing as t
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from redbot.core.i18n import Translator

from ..db.tables import Membership, Player
from .catalog import COLORS
from .edits import MAX_NUMBER
from .store import Store

_ = Translator("Casino", __file__)

log = logging.getLogger("red.vrt.casino.memberships")

NAME_PATTERN = re.compile(r"^[A-Za-z0-9 -]{1,32}$")
UPDATE_EVERY = 300


@dataclass
class Perks:
    name: str
    color: str
    access: int
    reduction: int
    bonus: float


BASIC = Perks(name="Basic", color="grey", access=0, reduction=0, bonus=1.0)


def perks_of(membership: Membership | None) -> Perks:
    if membership is None:
        return replace(BASIC, name=_("Basic"))
    return Perks(membership.name, membership.color, membership.access, membership.reduction, membership.bonus)


async def perks_for(store: Store, scope: int, user_id: int) -> Perks:
    player = await store.player(scope, user_id)
    if player.membership is None:
        return perks_of(None)
    return perks_of(await store.membership(scope, player.membership))


def clean_membership(data: dict, taken: list[str]) -> tuple[dict, str | None]:
    """Checks a tier sent by the page or a command. Returns the fields to save, or the problem.
    taken holds the names of the scope's other tiers"""
    try:
        name = str(data.get("name", "")).strip()
        fields = {
            "name": name,
            "color": str(data.get("color", "blue")).lower(),
            "access": int(data.get("access", 0)),
            "reduction": int(data.get("reduction", 0)),
            "bonus": float(data.get("bonus", 1.0)),
            "req_credits": optional_int(data.get("req_credits")),
            "req_role_id": optional_int(data.get("req_role_id")),
            "req_days": optional_int(data.get("req_days")),
        }
    except (TypeError, ValueError, OverflowError) as e:
        log.debug("Membership fields weren't numbers: %s", e)
        return {}, _("Access, reduction, bonus and requirements must be numbers.")
    # The database keeps whole numbers up to MAX_NUMBER
    if any(abs(value) > MAX_NUMBER for value in fields.values() if isinstance(value, int)):
        return {}, _("That number is too large.")
    if not NAME_PATTERN.match(name):
        return {}, _("Names are 1 to 32 letters, digits, spaces or hyphens.")
    if name.lower() in (other.lower() for other in taken):
        return {}, _("There's already a membership named {name}.").format(name=name)
    if fields["color"] not in COLORS:
        return {}, _("Pick a color from: {colors}.").format(colors=", ".join(COLORS))
    if fields["access"] < 0 or fields["reduction"] < 0:
        return {}, _("Access and cooldown reduction can't be below 0.")
    if not 0 < fields["bonus"] < 1000:
        return {}, _("The bonus multiplier must be above 0 and below 1000.")
    for key in ("req_credits", "req_days"):
        if fields[key] is not None and fields[key] < 0:
            return {}, _("Requirements can't be below 0.")
    return fields, None


def open_tier_warning() -> str:
    return _("This membership has no requirements, so every player gets it automatically.")


def has_requirements(tier: dict, global_mode: bool) -> bool:
    """Whether a shown tier asks anything of its players. Global mode ignores roles, like qualifies()"""
    keys = ("req_credits", "req_days") if global_mode else ("req_credits", "req_role_id", "req_days")
    return any(tier.get(key) for key in keys)


def optional_int(value: t.Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def qualifies(membership: Membership, balance: int, role_ids: set[int], days: int, global_mode: bool) -> bool:
    """Whether a player meets every requirement the tier sets. A tier with none is open to everyone"""
    if membership.req_credits and balance < membership.req_credits:
        return False
    if membership.req_role_id and not global_mode and membership.req_role_id not in role_ids:
        return False
    if membership.req_days and days < membership.req_days:
        return False
    return True


def best(tiers: list[Membership]) -> Membership | None:
    """The tier with the highest access level; the oldest wins a tie"""
    if not tiers:
        return None
    return max(tiers, key=lambda tier: (tier.access, -tier.id))


class Updater:
    """Every 5 minutes, gives each player the best tier they qualify for, skipping tiers given by hand"""

    def __init__(self, bot, store: Store, bank, on_change: t.Callable[[int, set[int]], t.Awaitable] | None = None):
        self.bot = bot
        self.store = store
        self.bank = bank
        # Called with a scope and the players whose membership a pass changed, so their open pages catch up
        self.on_change = on_change
        # Set when the cog unloads: the loop stops between passes, never in the middle of a database write
        self.stopping = asyncio.Event()

    async def run_forever(self) -> None:
        while not self.stopping.is_set():
            try:
                await asyncio.wait_for(self.stopping.wait(), UPDATE_EVERY)
                return
            except asyncio.TimeoutError as e:
                log.debug("Membership update interval elapsed: %r", e)
            try:
                await self.run_once()
            except Exception as e:
                # A failed pass is logged, and the loop carries on with the next one
                log.error("Membership update failed", exc_info=e)

    async def run_once(self) -> None:
        if await self.store.global_mode():
            await self.safe_update(0, True)
            return
        for scope in await self.store.scopes_with_memberships():
            if scope != 0:
                await self.safe_update(scope, False)

    async def safe_update(self, scope: int, global_mode: bool) -> None:
        """One scope failing is logged and doesn't stop the others"""
        try:
            await self.update_scope(scope, global_mode)
        except Exception as e:
            log.exception("Membership update failed for scope %s", scope, exc_info=e)

    async def update_scope(self, scope: int, global_mode: bool) -> None:
        tiers = await self.store.memberships(scope)
        guild = None if global_mode else self.bot.get_guild(scope)
        if not tiers or (guild is None and not global_mode):
            return
        changed = set()
        for player in await self.store.players(scope):
            if player.by_hand:
                continue
            facts = self.facts(guild, player.user_id)
            if facts is None:
                continue
            person, days, role_ids = facts
            balance = await self.bank.balance(person)
            chosen = best([tier for tier in tiers if qualifies(tier, balance, role_ids, days, global_mode)])
            if await self.move(scope, player.id, chosen.id if chosen else None):
                changed.add(player.user_id)
        if changed and self.on_change is not None:
            await self.on_change(scope, changed)

    async def move(self, scope: int, row_id: int, new_id: int | None) -> bool:
        """Gives the player the new tier unless an admin gave or took one by hand since the pass read them, or the tier
        was deleted. True when it changed"""
        # Nothing inside the lock may call a helper that takes the lock again, so the rows are read directly
        async with self.store.lock:
            row = await Player.objects().where(Player.id == row_id).first()
            if row is None or row.by_hand or row.membership == new_id:
                return False
            if new_id is not None and await self.store.membership(scope, new_id) is None:
                return False
            await Player.update({Player.membership: new_id}).where((Player.id == row_id) & (Player.by_hand.eq(False)))
            return True

    def facts(self, guild, user_id: int) -> tuple[t.Any, int, set[int]] | None:
        """The member (or, with no guild, the user), their days in the server (or on Discord), and their role ids.
        None when the bot can't see them"""
        person = guild.get_member(user_id) if guild is not None else self.bot.get_user(user_id)
        if person is None:
            return None
        # Discord's times carry a timezone, so now must too, or the subtraction raises
        start = person.joined_at if guild is not None else person.created_at
        days = (datetime.now(timezone.utc) - start).days if start else 0
        role_ids = {role.id for role in person.roles} if guild is not None else set()
        return person, days, role_ids
