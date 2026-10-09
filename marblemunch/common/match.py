"""One Activity window's game: seats, the countdown, rounds and the locked update loop"""

import asyncio
import logging
import math
import random
import typing as t
from dataclasses import dataclass

from .leaderboard import Result
from .npc import NAMES, Npc
from .rules import DT, SEATS, TICK_RATE, Board

log = logging.getLogger("red.vrt.marblemunch.match")

COUNTDOWN_SECONDS = 10
STARTING_SECONDS = 3
RESULTS_SECONDS = 6
GRACE_SECONDS = 20
# After a freeze longer than this, the loop skips the updates it missed instead of sending them all at once
CATCH_UP_SECONDS = 0.25

WAITING = "waiting"
STARTING = "starting"
PLAYING = "playing"
RESULTS = "results"
# Stages where players may sit down and stand up
OPEN_STAGES = (WAITING, RESULTS)

SEAT_TAKEN = "That seat was just taken."
LOOP_FAILED = "Something went wrong, so the round was stopped."


@dataclass
class Seat:
    """One hippo's seat: a person sits in it, an NPC plays it, or it is empty"""

    user_id: int | None = None
    name: str = ""
    # The name the global leaderboard shows: the Discord-wide one, since the board covers every server
    board_name: str = ""
    avatar: str = ""
    conn: t.Any = None
    # When the player's connection dropped, on the match's clock, while their seat is kept for them
    dropped_at: float | None = None
    npc: Npc | None = None

    @property
    def human(self) -> bool:
        return self.user_id is not None

    def clear(self) -> None:
        self.user_id, self.name, self.board_name, self.avatar = None, "", "", ""
        self.conn, self.dropped_at, self.npc = None, None, None


class Match:
    def __init__(
        self,
        room: t.Any,
        record: t.Callable[[list[Result]], None],
        ended: t.Callable[["Match"], None],
        rng: random.Random | None = None,
        clock: t.Callable[[], float] | None = None,
    ):
        """
        `room` is the window's ActivityHub room. `record(results)` gets each finished round's results for the
        leaderboard, and `ended(match)` is called once the update loop has stopped
        """
        self.room = room
        self.record = record
        self.ended = ended
        self.rng = rng or random.Random()
        self.clock = clock or asyncio.get_running_loop().time
        self.seats = [Seat() for _ in range(SEATS)]
        self.stage = WAITING
        # Timers count updates, so they end on an exact update
        self.countdown: int | None = None
        self.stage_left = 0
        self.board: Board | None = None
        # Who was seated when the round started: seat number to (user id, leaderboard name)
        self.round_players: dict[int, tuple[int, str]] = {}
        # A dropped player's score when an NPC took their hippo over, since only marbles they ate count for them
        self.taken_scores: dict[int, int] = {}
        self.winners: list[int] = []
        self.tick_count = 0
        # Set when the page needs a full snapshot instead of the usual small update
        self.dirty = True
        self.task: asyncio.Task | None = None

    # ---------- The loop ----------

    def start(self) -> None:
        self.task = asyncio.create_task(self.run())

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def alive(self) -> bool:
        """Anyone in the window, or a dropped player's seat still kept for them"""
        return bool(self.room.connections) or any(seat.dropped_at is not None for seat in self.seats)

    async def run(self) -> None:
        """The locked update loop: TICK_RATE updates a second, each timed from a fixed start so delays don't add up"""
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while self.alive():
                await self.tick()
                next_tick += DT
                if loop.time() - next_tick > CATCH_UP_SECONDS:
                    next_tick = loop.time()
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except Exception as e:
            # Logged once and stopped, so a bug can't fill the log 30 times a second
            log.error("Marble Munch stopped a round in window %s", self.room.instance_id, exc_info=e)
            await self.room.broadcast({"notice": LOOP_FAILED})
        finally:
            self.ended(self)

    async def tick(self) -> None:
        """One update: timers, the game, then what the pages need to see"""
        self.expire_drops()
        if self.stage == WAITING:
            self.tick_waiting()
        elif self.stage == STARTING:
            self.tick_starting()
        elif self.stage == PLAYING:
            self.tick_playing()
        else:
            self.tick_results()
        self.tick_count += 1
        if self.dirty:
            self.dirty = False
            await self.room.broadcast(self.state())
        elif self.stage == PLAYING:
            # One small update for the whole window, turned into JSON once. Every page gets every marble's
            # position because it has to draw them, so a script could press at the perfect moment. The reach
            # speed and the wait after a snap cap how well even a perfect script plays
            await self.room.broadcast({"f": self.tick_count, **self.board.frame()})

    def count_down(self, ticks: int) -> int:
        """Take one update off a timer, and refresh the pages when the whole seconds they show change"""
        left = ticks - 1
        if math.ceil(left / TICK_RATE) != math.ceil(ticks / TICK_RATE):
            self.dirty = True
        return left

    # ---------- Stages ----------

    def tick_waiting(self) -> None:
        if not any(seat.human for seat in self.seats):
            if self.countdown is not None:
                self.countdown = None
                self.dirty = True
            return
        if self.countdown is None:
            return
        self.countdown = self.count_down(self.countdown)
        if self.countdown > 0:
            return
        if any(seat.human and seat.conn is not None for seat in self.seats):
            self.begin_round()
        else:
            # Only dropped players are seated: wait for one of them to come back
            self.countdown = None
            self.dirty = True

    def begin_round(self) -> None:
        self.board = Board(self.rng)
        self.winners = []
        self.round_players = {}
        self.taken_scores = {}
        for number, seat in enumerate(self.seats):
            if seat.human:
                self.round_players[number] = (seat.user_id, seat.board_name)
            else:
                seat.npc = Npc(number, self.rng)
                seat.name = NAMES[number]
        self.countdown = None
        self.stage, self.stage_left, self.dirty = STARTING, STARTING_SECONDS * TICK_RATE, True

    def tick_starting(self) -> None:
        self.stage_left = self.count_down(self.stage_left)
        if self.stage_left <= 0:
            self.stage, self.dirty = PLAYING, True

    def tick_playing(self) -> None:
        for number, seat in enumerate(self.seats):
            if seat.npc is not None:
                self.apply(number, seat.npc.decide(self.board, DT))
        self.board.step()
        if self.board.finished:
            self.end_round()

    def apply(self, number: int, action: str | None) -> None:
        hippo = self.board.hippos[number]
        if action == "press":
            hippo.press()
        elif action == "release":
            hippo.release()

    def end_round(self) -> None:
        scores = [hippo.score for hippo in self.board.hippos]
        best = max(scores)
        # A win needs at least one marble, so a round where nobody ate anything has no winner
        self.winners = [number for number, score in enumerate(scores) if best > 0 and score == best]
        # Idle alt accounts in the other seats would hand one player every win. Fine with no credits paid;
        # an NPC taking over idle seats closes that gap if credits are ever added
        results = [
            Result(
                user_id,
                name,
                self.taken_scores.get(number, scores[number]),
                number in self.winners and self.seats[number].npc is None,
            )
            for number, (user_id, name) in self.round_players.items()
        ]
        if results:
            self.record(results)
        self.stage, self.stage_left, self.dirty = RESULTS, RESULTS_SECONDS * TICK_RATE, True

    def tick_results(self) -> None:
        self.stage_left = self.count_down(self.stage_left)
        if self.stage_left > 0:
            return
        for seat in self.seats:
            if seat.npc is not None:
                seat.clear()
        self.board = None
        self.stage, self.dirty = WAITING, True
        if any(seat.human for seat in self.seats):
            self.countdown = COUNTDOWN_SECONDS * TICK_RATE

    def expire_drops(self) -> None:
        """Seats kept past the grace period: an NPC takes over mid-round, otherwise the seat empties"""
        now = self.clock()
        for number, seat in enumerate(self.seats):
            if seat.dropped_at is None or now - seat.dropped_at < GRACE_SECONDS:
                continue
            if self.stage in (STARTING, PLAYING):
                self.taken_scores[number] = self.board.hippos[number].score
                seat.user_id, seat.conn, seat.dropped_at, seat.avatar = None, None, None, ""
                seat.npc, seat.name = Npc(number, self.rng), NAMES[number]
            else:
                seat.clear()
            self.dirty = True

    # ---------- Players ----------

    def seat_of(self, user_id: int) -> Seat | None:
        return next((seat for seat in self.seats if seat.human and seat.user_id == user_id), None)

    def seat_of_conn(self, conn: t.Any) -> Seat | None:
        return next((seat for seat in self.seats if seat.conn is conn), None)

    async def join(self, conn: t.Any) -> None:
        seat = self.seat_of(conn.ctx.author.id)
        if seat is not None:
            # Back from a drop, or the same player on a second device: this connection drives their hippo now.
            # The old connection's leave finds it no longer holds the seat, and leaves it alone
            seat.conn, seat.dropped_at = conn, None
            if self.stage == WAITING and self.countdown is None:
                self.countdown = COUNTDOWN_SECONDS * TICK_RATE
        self.dirty = True
        await conn.send(self.state())

    def leave(self, conn: t.Any) -> None:
        for number, seat in enumerate(self.seats):
            if seat.conn is not conn:
                continue
            if self.board is not None:
                # Their hippo sits still while the seat is kept
                self.board.hippos[number].release()
            # The same player may still have the game open on another device, which drives the hippo from now on
            others = [other for other in self.room.connections if other is not conn]
            seat.conn = next((other for other in others if other.ctx.author.id == seat.user_id), None)
            if seat.conn is None:
                seat.dropped_at = self.clock()
        self.dirty = True

    async def message(self, conn: t.Any, data: t.Any) -> None:
        """A message from a page. Anything but the five exact messages is ignored"""
        if not isinstance(data, dict) or len(data) != 1:
            return
        kind, value = next(iter(data.items()))
        if kind == "sit" and type(value) is int:
            notice = self.sit(conn, value)
            if notice:
                await conn.send({"notice": notice})
        elif value is not True:
            return
        elif kind == "stand":
            self.stand(conn)
        elif kind == "start":
            self.start_now(conn)
        elif kind in ("press", "release"):
            self.steer(conn, kind)

    def sit(self, conn: t.Any, number: int) -> str | None:
        """Seat a spectator. Returns a notice for them when the seat was already taken"""
        author = conn.ctx.author
        if not 0 <= number < SEATS or self.stage not in OPEN_STAGES or self.seat_of(author.id) is not None:
            return None
        seat = self.seats[number]
        if seat.human or seat.npc is not None:
            # Two players tapped this hippo at once, and the bot handled the other tap first
            return SEAT_TAKEN
        seat.user_id, seat.conn = author.id, conn
        seat.name = author.display_name
        seat.board_name = author.global_name or author.name
        seat.avatar = author.display_avatar.url
        if self.stage == WAITING and self.countdown is None:
            self.countdown = COUNTDOWN_SECONDS * TICK_RATE
        self.dirty = True
        return None

    def stand(self, conn: t.Any) -> None:
        seat = self.seat_of_conn(conn)
        if seat is not None and self.stage in OPEN_STAGES:
            seat.clear()
            self.dirty = True

    def start_now(self, conn: t.Any) -> None:
        if self.stage == WAITING and self.countdown is not None and self.seat_of_conn(conn) is not None:
            # The next update finishes the countdown
            self.countdown = 1

    def steer(self, conn: t.Any, kind: str) -> None:
        """Record a press or release for the player's own hippo. The next update applies it"""
        if self.stage != PLAYING:
            return
        for number, seat in enumerate(self.seats):
            if seat.conn is conn and seat.npc is None:
                self.apply(number, kind)

    # ---------- What the page sees ----------

    def state(self) -> dict:
        """Everything a page needs to draw the window from scratch"""
        board = None
        if self.board is not None:
            board = {"f": self.tick_count, **self.board.frame()}
        return {
            "state": {
                "stage": self.stage,
                "countdown": None if self.countdown is None else math.ceil(self.countdown / TICK_RATE),
                "left": math.ceil(self.stage_left / TICK_RATE) if self.stage in (STARTING, RESULTS) else None,
                "seats": [self.seat_state(seat) for seat in self.seats],
                "watching": self.watching(),
                "board": board,
                "winners": self.winners,
            }
        }

    @staticmethod
    def seat_state(seat: Seat) -> dict:
        if seat.npc is not None:
            kind = "npc"
        elif seat.human:
            kind = "human"
        else:
            kind = "empty"
        return {
            "kind": kind,
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(seat.user_id) if seat.human else None,
            "name": seat.name,
            "avatar": seat.avatar,
            "away": seat.dropped_at is not None,
        }

    def watching(self) -> int:
        players = [seat.conn for seat in self.seats if seat.conn is not None]
        return sum(1 for conn in self.room.connections if not any(conn is player for player in players))
