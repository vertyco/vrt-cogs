"""Stand-ins for ActivityHub's connections and Red's bank, shaped like the ones in DEVELOPERS.md's testing section"""

from types import SimpleNamespace

from redbot.core.errors import BalanceTooHigh

GUILD_ID = 500
OWNER_ID = 90  # the bot owner
ADMIN_ID = 91  # has Manage Server


def answer(value):
    """An async method that always answers value, like ctx.is_admin()"""

    async def ask():
        return value

    return ask


def member_ctx(user_id, guild_id=GUILD_ID, instance_id="window"):
    """ActivityHub's ctx for a member of a test server"""
    guild = SimpleNamespace(id=guild_id, owner_id=0)
    author = SimpleNamespace(id=user_id, name=f"user{user_id}", display_name=f"Player {user_id}")
    author.guild = guild
    author.guild_permissions = SimpleNamespace(manage_guild=user_id == ADMIN_ID)
    guild.get_member = lambda member_id: author if member_id == user_id else None
    return SimpleNamespace(
        author=author,
        guild=guild,
        guild_id=guild_id,
        instance_id=instance_id,
        # The bot owner and Manage Server count, like the hub's own check
        is_admin=answer(user_id in (OWNER_ID, ADMIN_ID)),
    )


def dm_ctx(user_id):
    author = SimpleNamespace(id=user_id, name=f"user{user_id}", display_name=f"Player {user_id}")
    return SimpleNamespace(author=author, guild=None, guild_id=None, instance_id="dm", is_admin=answer(False))


class FakeConn:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sent = []
        self.closed = None

    async def send(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = code

    def last(self, kind):
        """The newest message of one kind, like "hello" or "move\""""
        return next(message[kind] for message in reversed(self.sent) if kind in message)

    def kinds(self):
        return [next(iter(message)) for message in self.sent]


class FakeBot:
    async def is_owner(self, user):
        return user.id == OWNER_ID


class FakeBank:
    """Red's bank calls the payouts use, one balance per user id"""

    def __init__(self):
        self.global_bank = False
        self.balances = {}
        self.max_balance = 1_000_000

    async def is_global(self):
        return self.global_bank

    async def get_currency_name(self, guild=None):
        return "credits"

    async def get_balance(self, member):
        return self.balances.get(member.id, 0)

    async def deposit_credits(self, member, amount):
        balance = self.balances.get(member.id, 0) + amount
        if balance > self.max_balance:
            raise BalanceTooHigh(member, self.max_balance, "credits")
        self.balances[member.id] = balance
        return balance

    async def set_balance(self, member, amount):
        self.balances[member.id] = amount
        return amount


class Today:
    def __init__(self):
        self.day = "2026-10-10"

    def __call__(self):
        return self.day


class Clock:
    """Milliseconds, moved on by hand"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now
