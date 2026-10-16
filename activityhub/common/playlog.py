"""The play log: one row for each stretch of one person inside one game, kept in the hub's SQLite file"""

import asyncio
import logging
import time
import typing as t
from dataclasses import dataclass

from ..db.tables import Play

log = logging.getLogger("red.vrt.activityhub.playlog")

# After a play ends, the writer waits this long to gather more, then writes them together
GATHER_SECONDS = 5
# How long unloading waits for the last rows to be written
CLOSE_SECONDS = 5

# A person in one Activity window: (instance id, user id)
PlayKey = tuple[str, int]


@dataclass
class OpenPlay:
    """A play in progress, or ended and waiting to be written. Piccolo can only build a row once the database is
    set up, so the row is made at write time"""

    guild_id: int | None
    user_id: int
    game: str
    platform: str
    started_at: float
    seconds: float = 0.0
    # The clock's reading when this play's clock last started, or None while it's paused
    since: float | None = None

    def run(self, running: bool, now: float) -> None:
        if running and self.since is None:
            self.since = now
        elif not running and self.since is not None:
            self.seconds += now - self.since
            self.since = None

    def row(self) -> Play:
        return Play(
            guild_id=self.guild_id,
            user_id=self.user_id,
            game=self.game,
            platform=self.platform,
            started_at=self.started_at,
            seconds=self.seconds,
        )


class PlayLog:
    """Open plays in memory, ended plays written in batches. Nothing here raises into the people list"""

    def __init__(self, clock: t.Callable[[], float] = time.time, gather: float = GATHER_SECONDS):
        self.clock = clock
        self.gather = gather
        self.plays: dict[PlayKey, OpenPlay] = {}
        self.queue: list[OpenPlay] = []
        # Set once the database is open. The stats route and data deletion check it too
        self.ready = asyncio.Event()
        self.broken = False
        # Set by close, so the last rows go out without the gathering wait
        self.hurry = asyncio.Event()
        self.writer: asyncio.Task | None = None
        # Held while a batch is being written, so a data deletion can wait for rows already on their way
        self.writing = asyncio.Lock()

    def sync(
        self, key: PlayKey, guild_id: int | None, user_id: int, game: str | None, platform: str, running: bool
    ) -> None:
        """Bring a person's play up to date: another game ends the open play and starts a new one, otherwise the
        play's clock starts or pauses"""
        if self.broken:
            return
        now = self.clock()
        play = self.plays.get(key)
        if play is not None and play.game != game:
            self.finish(key, now)
            play = None
        if play is None and game is not None:
            play = self.plays[key] = OpenPlay(guild_id, user_id, game, platform, now)
        if play is not None:
            play.run(running, now)

    def end(self, key: PlayKey) -> None:
        if key in self.plays:
            self.finish(key, self.clock())

    def end_all(self) -> None:
        now = self.clock()
        for key in list(self.plays):
            self.finish(key, now)

    def finish(self, key: PlayKey, now: float) -> None:
        play = self.plays.pop(key)
        play.run(False, now)
        self.queue.append(play)
        self.wake()

    def forget_user(self, user_id: int) -> None:
        """Drop a user's open and unwritten plays, for a data deletion request"""
        self.plays = {key: play for key, play in self.plays.items() if play.user_id != user_id}
        self.queue = [play for play in self.queue if play.user_id != user_id]

    def opened(self) -> None:
        self.ready.set()
        self.wake()

    def failed(self) -> None:
        """The database can't open: drop what's waiting and keep no more plays"""
        self.broken = True
        if self.queue:
            log.error("Dropped %d plays because the play log's database couldn't open", len(self.queue))
        self.queue.clear()
        self.plays.clear()

    def wake(self) -> None:
        if self.ready.is_set() and self.queue and (self.writer is None or self.writer.done()):
            self.writer = asyncio.create_task(self.write_soon())

    async def write_soon(self) -> None:
        while self.queue:
            try:
                await asyncio.wait_for(self.hurry.wait(), self.gather)
            except asyncio.TimeoutError:
                # The usual way out of the wait: nobody hurried it, and the gathering time is over
                pass
            await self.flush()

    async def flush(self) -> None:
        async with self.writing:
            batch = list(self.queue)
            # A data deletion can empty the queue while the writer waits to gather more
            if not batch:
                return
            try:
                await Play.insert(*[play.row() for play in batch])
            except Exception as e:
                log.error("Couldn't write %d plays to the play log", len(batch), exc_info=e)
            # Written or failed, those rows are done. Rows queued meanwhile stay. A cancel stops before this line,
            # so close can count the rows it gave up on
            sent = {id(play) for play in batch}
            self.queue = [play for play in self.queue if id(play) not in sent]

    async def settle(self) -> None:
        """Wait for a batch already being written. Rows still queued are another matter: forget_user drops those"""
        async with self.writing:
            pass

    async def close(self) -> None:
        """Write what's queued, giving up after CLOSE_SECONDS so unloading never hangs"""
        self.hurry.set()
        self.wake()
        writer = self.writer
        if writer is not None and not writer.done():
            pending = (await asyncio.wait({writer}, timeout=CLOSE_SECONDS))[1]
            if pending:
                writer.cancel()
                await asyncio.wait({writer}, timeout=1)
        if self.queue:
            log.error("Gave up on %d plays not yet written to the play log", len(self.queue))
            self.queue.clear()
