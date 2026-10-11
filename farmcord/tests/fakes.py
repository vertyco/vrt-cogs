"""Stand-ins for Red's bank and bot, Discord members, ActivityHub's ctx and the clock, shaped like Vegas's and
Marble Munch's"""

import asyncio
import random
import typing as t
from types import SimpleNamespace

from redbot.core.errors import BalanceTooHigh

from farmcord.catalog import CROPS
from farmcord.game.calendar import DAY, EPOCH, HOUR, season_at, weather_at
from farmcord.main import FarmCord

GUILD_ID = 500
OWNER_ID = 90  # the bot owner
ADMIN_ID = 91  # has Manage Server
PLAYER_ID = 7
OTHER_ID = 8


def first_dry_morning(crop: str = "wildflowers") -> float:
    """1 a.m. UTC on the first dry day in the crop's season, so only the player waters it and it grows full speed"""
    for day in range(400):
        moment = EPOCH + day * DAY + HOUR
        if weather_at(moment) == "sun" and season_at(moment) in CROPS[crop].seasons:
            return moment
    raise AssertionError(f"No dry day in {crop}'s season")


START = first_dry_morning()


class Clock:
    """The bot's clock, moved by hand"""

    def __init__(self, now: float = START):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def move(self, seconds: float) -> None:
        self.now += seconds


class Today:
    """The UTC day the payout ledger counts cash-ins by"""

    def __init__(self):
        self.day = "2026-10-10"

    def __call__(self) -> str:
        return self.day


class FakeBank:
    """Red's bank calls the payouts use, one balance per user id. on_deposit, when set, is awaited before paying"""

    def __init__(self):
        self.global_bank = False
        self.balances: dict[int, int] = {}
        self.max_balance = 1_000_000
        self.on_deposit: t.Callable[..., t.Awaitable] | None = None

    async def is_global(self) -> bool:
        return self.global_bank

    async def get_currency_name(self, guild=None) -> str:
        return "credits"

    async def get_balance(self, member) -> int:
        return self.balances.get(member.id, 0)

    async def deposit_credits(self, member, amount: int) -> int:
        if self.on_deposit is not None:
            await self.on_deposit(member, amount)
        balance = self.balances.get(member.id, 0) + amount
        if balance > self.max_balance:
            raise BalanceTooHigh(member, self.max_balance, "credits")
        self.balances[member.id] = balance
        return balance

    async def set_balance(self, member, amount: int) -> int:
        self.balances[member.id] = amount
        return amount


class FakeBot:
    def __init__(self):
        self.admins: set[int] = set()
        self.cogs: dict[str, object] = {}
        self.views: list = []

    async def is_owner(self, user) -> bool:
        return user.id == OWNER_ID

    async def is_admin(self, member) -> bool:
        return member.id in self.admins

    def get_cog(self, name: str):
        return self.cogs.get(name)

    def add_view(self, view) -> None:
        self.views.append(view)

    async def wait_until_red_ready(self) -> None:
        # Tests open the database themselves, so the cog never gets past this
        await asyncio.Event().wait()


def ctx_for(user_id: int, name: str | None = None, server: bool = True) -> SimpleNamespace:
    """ActivityHub's ctx for a player, in the test server or (server=False) a DM"""
    guild = SimpleNamespace(id=GUILD_ID, owner_id=0) if server else None
    author = SimpleNamespace(
        id=user_id,
        name=f"user{user_id}",
        display_name=name or f"Player {user_id}",
        guild=guild,
        guild_permissions=SimpleNamespace(manage_guild=user_id == ADMIN_ID),
    )
    if guild is not None:
        guild.get_member = lambda member_id: author if member_id == user_id else None
    return SimpleNamespace(
        author=author,
        guild=guild,
        guild_id=guild.id if guild else None,
        channel=None,
        channel_id=77,
        instance_id="window",
    )


async def make_cog(store) -> FarmCord:
    """The cog on the test database, with a hand-moved clock, seeded rolls and a fake bank"""
    cog = FarmCord(FakeBot())
    # Red's Config keeps a cog's data in memory for the whole test run, so each test starts from nothing
    await cog.config.clear_all()
    cog.store = store
    cog.clock = Clock()
    cog.rng = random.Random(1)
    cog.payouts.bank = FakeBank()
    cog.payouts.today = Today()
    cog.ready.set()
    return cog


async def edit_farm(cog: FarmCord, user_id: int, **changes):
    """Change a saved farm directly, the way a test gives a player levels or FarmCoins"""
    farm = await cog.store.load(user_id)
    for name, value in changes.items():
        setattr(farm, name, value)
    await cog.store.save(farm)
    return farm


class Said:
    """A command's context: who ran it, and what the command sent"""

    def __init__(self, cog: FarmCord, user_id: int = PLAYER_ID):
        self.cog, self.bot = cog, cog.bot
        self.author = SimpleNamespace(id=user_id, display_name=f"Player {user_id}")
        self.guild = None
        self.sent: list[tuple] = []

    async def send(self, text=None, **kwargs):
        self.sent.append((text, kwargs.get("view")))


class FakeInteraction:
    """A slash command or button press, keeping its private replies"""

    def __init__(self):
        self.replies: list[tuple[str, bool]] = []
        self.response = SimpleNamespace(send_message=self.send_message)

    async def send_message(self, text: str, ephemeral: bool = False):
        self.replies.append((text, ephemeral))


class FakeHub:
    """ActivityHub, as far as opening a game goes"""

    def __init__(self):
        self.launched: list[tuple] = []

    async def launch(self, interaction, key: str) -> bool:
        self.launched.append((interaction, key))
        return True
