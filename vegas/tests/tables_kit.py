"""A small world for table tests: a host in place of the cog, rigged randomness, and a way to wait for a round"""

import asyncio
import random

from vegas.common.games.cards import Deck
from vegas.common.money import Money
from vegas.common.rounds import TABLE_TYPES
from vegas.common.table import Floor
from vegas.tests.fakes import Clock, FakeBank, FakeConn, FakeGuild, FakeRoom


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


class ScriptedDeck(Deck):
    """Draws the given cards in order. Past the last one it carries on with a shuffled deck"""

    def __init__(self, cards, rng=None):
        super().__init__(rng or random.Random(0))
        self.cards = [tuple(card) for card in reversed(cards)]


class Host:
    """Stands in for the cog: the parts a table uses"""

    def __init__(self, store, rng=None):
        self.store = store
        self.money = Money(store, FakeBank(start=1000), Clock())
        self.rng = rng or random.Random(1)
        self.table_types = TABLE_TYPES
        self.done = []
        # Every jackpot amount told: (scope, whole credits, hit)
        self.jackpots: list[tuple[int, int, dict | None]] = []

    async def send_me(self, floor, member):
        for conn in floor.conns_of(member.id):
            await conn.send({"t": "me", "balance": await self.money.bank.balance(member)})

    async def send_jackpot(self, scope, amount, hit, floor) -> None:
        self.jackpots.append((scope, amount, hit))
        await floor.room.broadcast({"t": "jackpot", "amount": amount, "hit": hit})

    def floor_done(self, floor):
        self.done.append(floor)


async def until(check, seconds: float = 5.0) -> None:
    """Lets the round run until check() is true, for up to `seconds` of real time"""
    loop = asyncio.get_running_loop()
    # The database answers from its own thread, so the wait must be real time, not a count of loop turns: on Windows
    # a sleep this short can come back at once
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if check():
            return
        await asyncio.sleep(0.005)
    if not check():
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


def open_turn(table, user_id: int, answered) -> bool:
    """True when the table waits on this player for a turn that hasn't been answered yet"""
    future = table.decisions.get(user_id)
    return future is not None and future is not answered and not future.done()


async def autoplay(table, conn, moves: list[dict]) -> None:
    """Answers each turn the table asks this player for with the next move, then stops"""
    user_id = conn.ctx.author.id
    answered = None
    for move in moves:
        await until(lambda: open_turn(table, user_id, answered))
        answered = table.decisions[user_id]
        await table.move(conn, move)


def time_out(table, user_id: int) -> None:
    """Ends the player's open turn the way its clock running out does: with the default itself"""
    table.decisions[user_id].set_result(table.fallbacks[user_id])


async def keep_playing(table, conn) -> None:
    """Answers every Hold'em turn this player gets, until cancelled: a check when it's free, otherwise a fold. The same
    moves a timeout plays, but sent, so two in a row don't stand the player up"""
    user_id = conn.ctx.author.id
    answered = None
    while True:
        await until(lambda: open_turn(table, user_id, answered), 3600)
        answered = table.decisions[user_id]
        await table.move(conn, {"move": "check" if "check" in table.allowed[user_id] else "fold"})


async def hand_over(table, number: int, seconds: float = 10.0) -> None:
    """Waits until Hold'em hand `number` was dealt and its win event has gone out"""
    await until(lambda: table.hand_no > number or (table.hand_no == number and table.street is None), seconds)
