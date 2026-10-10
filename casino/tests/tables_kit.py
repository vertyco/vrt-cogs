"""A small world for table tests: a host in place of the cog, rigged randomness, and a way to wait for a round"""

import asyncio
import random

from casino.common.money import Money
from casino.common.rounds import TABLE_TYPES
from casino.common.table import Floor
from casino.tests.fakes import Clock, FakeBank, FakeConn, FakeGuild, FakeRoom


class Rigged(random.Random):
    """Hands out the numbers and choices it was given, in order. Shuffles leave a list as it is"""

    def __init__(self, ints=(), picks=()):
        super().__init__(0)
        self.ints = list(ints)
        self.picks = list(picks)

    def randint(self, a, b):
        return self.ints.pop(0)

    def choice(self, seq):
        return self.picks.pop(0)

    def shuffle(self, x, random=None):
        pass


class Host:
    """Stands in for the cog: the parts a table uses"""

    def __init__(self, store, rng=None):
        self.store = store
        self.money = Money(store, FakeBank(start=1000), Clock())
        self.rng = rng or random.Random(1)
        self.table_types = TABLE_TYPES
        self.done = []

    async def send_me(self, floor, member):
        for conn in floor.conns_of(member.id):
            await conn.send({"t": "me", "balance": await self.money.bank.balance(member)})

    def floor_done(self, floor):
        self.done.append(floor)


async def until(check, seconds: float = 5.0) -> None:
    """Lets the round run until check() is true"""
    for _ in range(int(seconds / 0.005)):
        if check():
            return
        # The database answers from its own thread, so the wait must be real time, not just a turn of the loop
        await asyncio.sleep(0.005)
    raise AssertionError("The round never got there")


async def seat_players(store, game: str, *user_ids, rng=None, floors: list | None = None):
    """A floor with these players at one table, with animations skipped. floors collects it for closing"""
    host = Host(store, rng)
    guild = FakeGuild()
    room = FakeRoom()
    floor = Floor(host, room, guild)
    conns = []
    for user_id in user_ids:
        conn = FakeConn(room, guild.add(user_id), guild)
        await floor.arrive(conn)
        await floor.enter(conn, game)
        conns.append(conn)
    table = floor.table(game)
    table.speed = 0
    if floors is not None:
        floors.append(floor)
    return host, floor, table, conns


async def round_over(table) -> None:
    await until(lambda: table.task is None)
