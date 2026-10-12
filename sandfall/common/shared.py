"""
One shared world on the bot: its seats and its batch clock.

Every screen in a shared world runs the same simulation with the same dice. The bot never runs it: it only says which
strokes happen at which step. Twenty times a second it sends a batch, "apply these strokes, then run N steps", to
every seated player. A newcomer gets a snapshot (the world after some batch, taken from a player's screen) plus every
batch since, and is then in step.
"""

import asyncio
import logging
import typing as t
from collections import deque
from dataclasses import dataclass

from .strokes import OWNER_ONLY, steps_for

log = logging.getLogger("red.vrt.sandfall.shared")

TICK = 1 / 20
# 20 seconds of batches, kept so a player who reconnects or needs a snapshot can catch up
HISTORY = 400
# A dropped player keeps their seat this long, and a world with nobody present lasts this long
GRACE_SECONDS = 15
# A player asked for a snapshot who hasn't answered by then is passed over for the next ask
ASK_SECONDS = 5
# After a freeze longer than this, the clock skips the batches it missed instead of sending them all at once
CATCH_UP_SECONDS = 0.25
MAX_PLAYERS = 10
HASHES_KEPT = 50
# More strokes than this in one batch are dropped. Far above what ten honest players can send in 50 ms
MAX_PENDING = 200
NORMAL = 3


@dataclass
class Member:
    conn: t.Any
    name: str
    color: int
    # When they took their seat, on the world's clock. The longest-present player becomes owner when the owner goes
    joined: float
    # When their connection dropped, while their seat is kept for them
    gone_at: float | None = None

    @property
    def present(self) -> bool:
        return self.gone_at is None


class SharedWorld:
    def __init__(self, window: t.Any, world_id: str, owner: int, batch: int, speed: int):
        """
        `window` is the Activity window holding this world (a `Window`), told when the world's seats change and when
        it ends. Batches start at number `batch`
        """
        self.window = window
        self.id = world_id
        self.instance_id = window.instance_id
        self.clock: t.Callable[[], float] = window.clock
        self.owner = owner
        self.members: dict[int, Member] = {}
        self.speed = speed
        # The number of the next batch to make
        self.batch = batch
        # The number of this world's first batch. A world reopened after a restart starts after its owner's last batch
        self.first = batch
        self.once = False
        self.pending: list[list] = []
        self.history: deque[list] = deque(maxlen=HISTORY)
        # Fingerprints players reported, by batch number, then by user id
        self.hashes: dict[int, dict[int, str]] = {}
        # Players who need a snapshot before they get batches
        self.waiting: set[int] = set()
        # Seated players who were away when the world was last replaced: their screens still hold the old world
        self.stale: set[int] = set()
        # Who was asked for a snapshot and when, or None while nobody is asked
        self.asked: int | None = None
        self.asked_at = 0.0
        self.task: asyncio.Task | None = None
        self.closed = False

    # Seats

    @property
    def name(self) -> str:
        member = self.members.get(self.owner)
        return member.name if member else ""

    @property
    def full(self) -> bool:
        return len(self.members) >= MAX_PLAYERS

    def present(self) -> list[tuple[int, Member]]:
        return [(user_id, member) for user_id, member in self.members.items() if member.present]

    def free_color(self) -> int:
        taken = {member.color for member in self.members.values()}
        return next(color for color in range(MAX_PLAYERS) if color not in taken)

    def add_member(self, user_id: int, conn: t.Any) -> bool:
        """Seats a player, or gives a returning player their seat back. False when the world is full"""
        member = self.members.get(user_id)
        if member is not None:
            member.conn, member.gone_at = conn, None
            return True
        if self.full:
            return False
        self.members[user_id] = Member(conn, conn.ctx.author.display_name, self.free_color(), self.clock())
        return True

    async def seat(self, user_id: int, conn: t.Any, since: int | None = None) -> bool:
        """
        Seats a player and brings their screen into step: with the batches after `since` when the page still has
        the world after that batch and the history covers it, otherwise with a snapshot. False when the world is full
        """
        # A player new to this world who ran batches past its first one ran them before a restart. The reopened world
        # numbers its own batches from there with other strokes in them, so only the batch it starts after is common
        if user_id not in self.members and since != self.first - 1:
            since = None
        if not self.add_member(user_id, conn):
            return False
        await self.want_snapshot(user_id, since)
        await self.changed()
        return True

    def drop(self, user_id: int, conn: t.Any) -> bool:
        """A player's connection closed. They keep their seat for a while. False when `conn` isn't their seat's"""
        member = self.members.get(user_id)
        if member is None or member.conn is not conn:
            return False
        member.gone_at = self.clock()
        self.waiting.discard(user_id)
        return True

    async def unseat(self, user_id: int) -> None:
        """Takes a player's seat away. The longest-present player takes over an owner's world; the last one out ends it"""
        if self.members.pop(user_id, None) is None:
            return
        self.waiting.discard(user_id)
        self.stale.discard(user_id)
        if not self.members:
            await self.end()
            return
        if user_id == self.owner:
            ranked = sorted(self.members.items(), key=lambda item: (not item[1].present, item[1].joined))
            self.owner = ranked[0][0]
        await self.changed()

    async def expire(self, now: float) -> None:
        for user_id, member in list(self.members.items()):
            if member.gone_at is not None and now - member.gone_at >= GRACE_SECONDS:
                await self.unseat(user_id)

    def players(self) -> list[dict]:
        return [{"id": str(user_id), "name": member.name, "color": member.color} for user_id, member in self.present()]

    def summary(self) -> dict:
        """The world as the Worlds panel lists it"""
        return {
            "id": self.id,
            "name": self.name,
            "owner": str(self.owner),
            "players": [{"id": str(user_id), "name": member.name} for user_id, member in self.present()],
            "full": self.full,
        }

    async def changed(self) -> None:
        """Tells the world's players who is in it, and the whole window what is open"""
        update = {"players": {"owner": str(self.owner), "list": self.players()}}
        for _, member in self.present():
            await member.conn.send(update)
        await self.window.send_worlds()

    async def send_present(self, data: dict, but: int | None = None) -> None:
        for user_id, member in self.present():
            if user_id != but:
                await member.conn.send(data)

    # The clock

    def start(self) -> None:
        self.task = asyncio.create_task(self.run())

    def stop(self) -> None:
        self.closed = True
        if self.task is not None and self.task is not asyncio.current_task():
            self.task.cancel()

    async def end(self) -> None:
        self.stop()
        await self.window.world_ended(self)

    async def run(self) -> None:
        """The batch clock: TICK batches a second, each timed from a fixed start so delays don't add up"""
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while not self.closed:
                await self.turn()
                next_tick += TICK
                if loop.time() - next_tick > CATCH_UP_SECONDS:
                    next_tick = loop.time()
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Logged once and ended, so a bug can't fill the log 20 times a second
            log.error("Sandfall stopped shared world %s in window %s", self.id, self.instance_id, exc_info=e)
            if not self.closed:
                await self.end()

    async def turn(self) -> None:
        """One batch: seats that ran out, a slow snapshot giver, then the strokes and steps for every screen"""
        now = self.clock()
        await self.expire(now)
        if self.closed:
            return
        if self.asked is not None and (now - self.asked_at >= ASK_SECONDS or not self.is_present(self.asked)):
            skipped, self.asked = self.asked, None
            await self.ask_supplier(skip=skipped)
        n = steps_for(self.speed, self.batch)
        if self.once:
            self.once = False
            n = 1 if self.speed == 0 else n
        # A running world makes a batch every turn, a paused one only for strokes. Batch numbers only skip at a
        # load, which takes a number of its own
        if n == 0 and self.speed == 0 and not self.pending:
            return
        batch = [self.batch, n, self.pending]
        self.pending = []
        self.batch += 1
        self.history.append(batch)
        # The receivers are picked with no await after the history append, so a player who gets a snapshot while
        # this batch goes out finds it in the history instead of getting it twice or never
        receivers = [member.conn for user_id, member in self.present() if user_id not in self.waiting]
        message = {"b": batch}
        for conn in receivers:
            await conn.send(message)

    def is_present(self, user_id: int) -> bool:
        member = self.members.get(user_id)
        return member is not None and member.present

    # What the players send

    def add_stroke(self, user_id: int, stroke: list) -> None:
        """A stroke checked by check_stroke, for the next batch"""
        if stroke[0] in OWNER_ONLY and user_id != self.owner:
            return
        if len(self.pending) < MAX_PENDING:
            self.pending.append([str(user_id), stroke])

    async def set_speed(self, speed: int) -> None:
        self.speed = speed
        await self.send_present({"speed": speed})

    def step_once(self) -> None:
        self.once = True

    async def load(self, text: str) -> None:
        """
        Replaces the world with a checked snapshot. The loaded world takes a batch number of its own, so a screen that
        missed the load can never mistake its old world for the new one and replay batches onto it
        """
        b = self.batch
        self.batch += 1
        self.hashes.clear()
        self.history.clear()
        here = self.present()
        self.stale = set(self.members) - {user_id for user_id, _ in here}
        for user_id, _ in here:
            await self.send_world(user_id, text, b)

    # Snapshots and catching up

    def covers(self, b: object) -> bool:
        """Whether the history holds every batch after batch `b`, so a screen at `b` can catch up from it alone"""
        if not isinstance(b, int) or isinstance(b, bool) or b > self.batch - 1:
            return False
        if b == self.batch - 1:
            return True
        return bool(self.history) and self.history[0][0] <= b + 1

    async def send_world(self, user_id: int, snap: str | None, b: int) -> None:
        """
        Sends a player the world after batch `b` and every batch since. `snap` None keeps the world their screen has.
        From here on they get the live batches
        """
        member = self.members.get(user_id)
        self.waiting.discard(user_id)
        if member is None or not member.present:
            return
        world = {
            "id": self.id,
            "name": self.name,
            "owner": str(self.owner),
            "players": self.players(),
            "speed": self.speed,
            "b": b,
            "snap": snap,
            "batches": [batch for batch in self.history if batch[0] > b],
        }
        await member.conn.send({"world": world})

    async def want_snapshot(self, user_id: int, since: int | None = None) -> None:
        """Brings a player's screen into step: from the history when it covers `since`, otherwise from a snapshot"""
        away = user_id in self.stale
        self.stale.discard(user_id)
        if since is not None and not away and self.covers(since):
            await self.send_world(user_id, None, since)
            return
        self.waiting.add(user_id)
        await self.ask_supplier()

    async def ask_supplier(self, skip: int | None = None) -> None:
        """Asks a screen for a snapshot: the owner's, else the longest-present player's, passing over `skip`"""
        if not self.waiting or self.asked is not None or self.closed:
            return
        ranked = sorted(self.present(), key=lambda item: (item[0] != self.owner, item[1].joined))
        able = [user_id for user_id, _ in ranked if user_id not in self.waiting]
        # A lone screen that fell behind is still the only copy of the world there is
        able = able or [user_id for user_id, _ in ranked]
        if len(able) > 1 and skip in able:
            able.remove(skip)
        if not able:
            return
        self.asked, self.asked_at = able[0], self.clock()
        await self.members[self.asked].conn.send({"snapask": True})

    async def got_snapshot(self, user_id: int, b: object, text: str) -> None:
        """A snapshot already checked by check_world, from the screen that was asked for it"""
        if user_id != self.asked:
            return
        self.asked = None
        if not self.covers(b):
            # Older than the history: the players waiting couldn't catch up from it
            await self.ask_supplier()
            return
        for waiter in list(self.waiting):
            await self.send_world(waiter, text, b)

    async def bad_snapshot(self, user_id: int) -> None:
        """The screen asked for a snapshot sent one that didn't check out"""
        if user_id == self.asked:
            self.asked = None
            await self.ask_supplier(skip=user_id)

    async def fingerprint(self, user_id: int, b: int, h: str) -> None:
        """A screen's fingerprint after batch `b`. A screen whose world differs from the owner's gets a snapshot"""
        if user_id not in self.members:
            return
        reports = self.hashes.setdefault(b, {})
        reports[user_id] = h
        while len(self.hashes) > HASHES_KEPT:
            del self.hashes[min(self.hashes)]
        expected = reports.get(self.owner)
        if expected is None:
            return
        for other, value in list(reports.items()):
            if value != expected and other not in self.waiting and other in self.members:
                del reports[other]
                log.info("Sandfall world %s: player %s drifted at batch %s, sending a snapshot", self.id, other, b)
                await self.want_snapshot(other)
