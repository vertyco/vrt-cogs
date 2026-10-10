"""One Activity window's match: two seats and the host, the difficulty, the battle on a 20 a second loop, pausing,
players dropping out and coming back, and the results"""

import asyncio
import logging
import random
import typing as t
from dataclasses import dataclass

from .battle import Battle
from .cpu import Computer
from .data import DIFFICULTIES, FPS
from .leaderboard import Result

log = logging.getLogger("red.vrt.ageofwar.match")

TICK_RATE = 20
DT = 1 / TICK_RATE
# The battle runs at the original's 40 frames a second: two frames per update
STEPS = FPS // TICK_RATE
SEATS = 2
# A dropped player keeps their seat this long before setup frees it
SETUP_GRACE_SECONDS = 20
# In a battle: the computer takes a dropped player's base after this long, or the match stops if nobody is left
TAKEOVER_SECONDS = 60
# After a freeze longer than this, the loop skips the updates it missed instead of running them all at once
CATCH_UP_SECONDS = 0.25
# The biggest whole number a page's JavaScript holds exactly
MAX_WHOLE = 2**53 - 1

SETUP = "setup"
PLAYING = "playing"
RESULTS = "results"

SEAT_TAKEN = "That seat was just taken."
LOOP_FAILED = "Something went wrong, so the match was stopped."
EVERYONE_LEFT = "Every player left, so the match was stopped."
YOU_LEFT = "You were away too long, so the match was stopped."
TOOK_BACK = "The computer played your base while you were away."


@dataclass
class Seat:
    """One base: a person sits there, or it is empty (the computer plays an empty seat in a battle)"""

    user_id: int | None = None
    name: str = ""
    # The name the global leaderboard shows: the Discord-wide one, since the board covers every server
    board_name: str = ""
    avatar: str = ""
    conn: t.Any = None
    dropped_at: float | None = None
    # The computer took this person's base over while they were away
    stand_in: bool = False

    @property
    def human(self) -> bool:
        return self.user_id is not None

    @property
    def present(self) -> bool:
        return self.human and self.conn is not None

    def clear(self) -> None:
        self.user_id, self.name, self.board_name, self.avatar = None, "", "", ""
        self.conn, self.dropped_at, self.stand_in = None, None, False


def whole(value: t.Any) -> bool:
    return type(value) is int and abs(value) <= MAX_WHOLE


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
        `room` is the window's ActivityHub room. `record(results)` gets each win against the computer for the
        leaderboard, and `ended(match)` is called once the update loop has stopped
        """
        self.room = room
        self.record = record
        self.ended = ended
        self.rng = rng or random.Random()
        self.clock = clock or asyncio.get_running_loop().time
        self.seats = [Seat() for _ in range(SEATS)]
        self.host: int | None = None
        self.difficulty = "normal"
        self.stage = SETUP
        self.battle: Battle | None = None
        # The battle's latest snapshot, for pages that join while it stands still
        self.last_frame: dict | None = None
        # Who played each base when the battle started: "human" or "cpu"
        self.players: list[str] = []
        self.paused = False
        self.results: dict | None = None
        self.dirty = True
        self.outbox: list[dict] = []
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
            # Logged once and stopped, so a bug can't fill the log 20 times a second
            log.error("Age of War stopped a match in window %s", self.room.instance_id, exc_info=e)
            # The pages go back to an empty setup, where the next message starts a new match, rather than staying
            # on a battle that no longer runs
            for seat in self.seats:
                seat.clear()
            self.back_to_setup()
            await self.room.broadcast(self.state())
            await self.room.broadcast({"notice": LOOP_FAILED})
        finally:
            self.ended(self)

    async def tick(self) -> None:
        self.expire_drops()
        frame = None
        if self.stage == PLAYING and self.running():
            for _ in range(STEPS):
                self.battle.step()
                if self.battle.winner is not None:
                    break
            frame = self.last_frame = self.battle.view()
            if self.battle.winner is not None:
                # The last frame goes out before the results, which clear the field
                await self.room.broadcast({"f": frame})
                frame = None
                self.finish()
        elif self.stage == PLAYING and self.paused and not self.waiting_for_solo():
            for _ in range(STEPS):
                self.battle.paused_step()
            frame = self.last_frame = self.battle.view()
        for message in self.outbox:
            await self.room.broadcast(message)
        self.outbox = []
        if self.dirty:
            self.dirty = False
            await self.room.broadcast(self.state())
        if frame is not None:
            await self.room.broadcast({"f": frame})

    def running(self) -> bool:
        """The battle stands still while paused, and while the only person playing is away"""
        return not self.paused and not self.waiting_for_solo()

    def waiting_for_solo(self) -> bool:
        people = [seat for seat in self.seats if seat.human and not seat.stand_in]
        return len(people) == 1 and self.players.count("human") == 1 and not people[0].present

    # ---------- Seats and the host ----------

    def seat_of(self, user_id: int) -> Seat | None:
        return next((seat for seat in self.seats if seat.human and seat.user_id == user_id), None)

    def number_of(self, conn: t.Any) -> int | None:
        return next((number for number, seat in enumerate(self.seats) if seat.conn is conn), None)

    def fix_host(self) -> None:
        """The host is the first person seated. When they stand up or leave, the other seated person takes over"""
        if self.host is not None and self.seats[self.host].present:
            return
        self.host = next((number for number, seat in enumerate(self.seats) if seat.present), None)

    def is_host(self, conn: t.Any) -> bool:
        return self.host is not None and self.number_of(conn) == self.host

    async def join(self, conn: t.Any) -> None:
        seat = self.seat_of(conn.ctx.author.id)
        if seat is not None:
            # Back from a drop, or the same player on a second device: this connection plays their base now
            seat.conn, seat.dropped_at = conn, None
            if seat.stand_in and self.battle is not None:
                self.take_back(self.seats.index(seat))
                await conn.send({"notice": TOOK_BACK})
            self.fix_host()
        self.dirty = True
        await conn.send(self.state())
        if self.stage == PLAYING and self.last_frame is not None:
            # The field as it stands, without the effects that already played
            await conn.send({"f": {**self.last_frame, "e": []}})

    def leave(self, conn: t.Any) -> None:
        number = self.number_of(conn)
        if number is not None:
            seat = self.seats[number]
            others = [other for other in self.room.connections if other is not conn]
            seat.conn = next((other for other in others if other.ctx.author.id == seat.user_id), None)
            if seat.conn is None:
                seat.dropped_at = self.clock()
            self.fix_host()
        self.dirty = True

    def expire_drops(self) -> None:
        now = self.clock()
        for number, seat in enumerate(self.seats):
            if seat.dropped_at is None:
                continue
            away = now - seat.dropped_at
            if self.stage != PLAYING:
                if away >= SETUP_GRACE_SECONDS:
                    seat.clear()
                    self.fix_host()
                    self.dirty = True
                    if self.stage == RESULTS and not any(other.human for other in self.seats):
                        self.back_to_setup()
            elif away >= TAKEOVER_SECONDS and not seat.stand_in:
                if self.players.count("human") == 1 or not any(other.present for other in self.seats):
                    self.stop_match(YOU_LEFT if self.players.count("human") == 1 else EVERYONE_LEFT)
                    return
                self.take_over(number)

    def take_over(self, number: int) -> None:
        """The computer plays an away player's base from now on, as the original's computer would"""
        seat = self.seats[number]
        seat.stand_in = True
        side = self.battle.sides[number + 1]
        side.cpu = Computer(side)
        self.dirty = True

    def take_back(self, number: int) -> None:
        self.seats[number].stand_in = False
        self.battle.sides[number + 1].cpu = None
        self.dirty = True

    def stop_match(self, notice: str) -> None:
        for seat in self.seats:
            if seat.human and seat.conn is None:
                seat.clear()
        self.back_to_setup()
        self.outbox.append({"notice": notice})

    def back_to_setup(self) -> None:
        for seat in self.seats:
            seat.stand_in = False
        self.stage, self.battle, self.players, self.paused, self.results = SETUP, None, [], False, None
        self.last_frame = None
        self.fix_host()
        self.dirty = True

    # ---------- Messages ----------

    async def message(self, conn: t.Any, data: t.Any) -> None:
        """A message from a page. Anything but the exact messages below, from the right player at the right time,
        is ignored"""
        if not isinstance(data, dict) or len(data) != 1:
            return
        kind, value = next(iter(data.items()))
        handler = self.handlers().get(kind)
        if handler is None:
            return
        notice = handler(conn, value)
        if notice:
            await conn.send({"notice": notice})

    def handlers(self) -> dict[str, t.Callable[[t.Any, t.Any], str | None]]:
        return {
            "sit": self.sit,
            "stand": self.stand,
            "difficulty": self.set_difficulty,
            "start": self.start_match,
            "continue": self.go_on,
            "pause": self.set_paused,
            "buy": self.buy,
            "build": self.build,
            "sell": self.sell,
            "spot": self.add_spot,
            "evolve": self.evolve,
            "special": self.special,
            "quit": self.give_up,
        }

    def sit(self, conn: t.Any, value: t.Any) -> str | None:
        author = conn.ctx.author
        if not whole(value) or not 0 <= value < SEATS or self.stage != SETUP or self.seat_of(author.id):
            return None
        seat = self.seats[value]
        if seat.human:
            return SEAT_TAKEN
        seat.user_id, seat.conn = author.id, conn
        seat.name = author.display_name
        seat.board_name = author.global_name or author.name
        seat.avatar = author.display_avatar.url
        self.fix_host()
        self.dirty = True
        return None

    def stand(self, conn: t.Any, value: t.Any) -> None:
        number = self.number_of(conn)
        if value is True and number is not None and self.stage == SETUP:
            self.seats[number].clear()
            self.fix_host()
            self.dirty = True

    def set_difficulty(self, conn: t.Any, value: t.Any) -> None:
        if self.stage == SETUP and self.is_host(conn) and isinstance(value, str) and value in DIFFICULTIES:
            self.difficulty = value
            self.dirty = True

    def start_match(self, conn: t.Any, value: t.Any) -> None:
        if value is not True or self.stage != SETUP or not self.is_host(conn):
            return
        self.battle = Battle(self.rng)
        self.last_frame = None
        self.players = []
        for number, seat in enumerate(self.seats):
            side = self.battle.sides[number + 1]
            if seat.human:
                self.players.append("human")
            else:
                self.players.append("cpu")
                side.cpu = Computer(side)
                side.strength = DIFFICULTIES[self.difficulty]
        self.stage, self.paused, self.results, self.dirty = PLAYING, False, None, True

    def go_on(self, conn: t.Any, value: t.Any) -> None:
        if value is True and self.stage == RESULTS and self.is_host(conn):
            self.back_to_setup()

    def set_paused(self, conn: t.Any, value: t.Any) -> None:
        """Only someone playing the computer alone can pause, as in the original. Two people can't stop each other"""
        number = self.number_of(conn)
        if self.stage != PLAYING or number is None or type(value) is not bool or self.players.count("human") != 1:
            return
        if value != self.paused:
            self.paused = value
            self.dirty = True

    def give_up(self, conn: t.Any, value: t.Any) -> None:
        """A player gives up: the other base wins"""
        number = self.number_of(conn)
        if value is True and self.stage == PLAYING and number is not None and not self.seats[number].stand_in:
            self.battle.winner = 2 - number
            self.finish()

    def finish(self) -> None:
        winner = self.battle.winner
        self.results = {
            "winner": winner,
            "frames": self.battle.frame,
            "seats": [
                {"name": seat.name if seat.human else "Computer", "kind": self.players[n], "standIn": seat.stand_in}
                for n, seat in enumerate(self.seats)
            ],
            "difficulty": self.difficulty if "cpu" in self.players else None,
        }
        if self.players.count("human") == 1:
            number = self.players.index("human")
            seat = self.seats[number]
            if winner == number + 1 and seat.human and not seat.stand_in:
                self.record([Result(seat.user_id, seat.board_name, self.difficulty, self.battle.frame)])
        self.stage, self.battle, self.paused, self.dirty = RESULTS, None, False, True
        self.last_frame = None

    # ---------- Orders from a player ----------

    def my_side(self, conn: t.Any) -> int | None:
        """The side this connection commands: its own base, while a person plays it. The menu works through a pause"""
        number = self.number_of(conn)
        if self.stage != PLAYING or number is None or self.seats[number].stand_in or self.waiting_for_solo():
            return None
        return number + 1

    def buy(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and whole(value):
            self.battle.buy_unit(side, value)

    def build(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and isinstance(value, list) and len(value) == 2 and all(whole(v) for v in value):
            self.battle.build_turret(side, value[0], value[1])

    def sell(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and whole(value):
            self.battle.sell_turret(side, value)

    def add_spot(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and value is True:
            self.battle.add_spot(side)

    def evolve(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and value is True:
            self.battle.evolve(side)

    def special(self, conn: t.Any, value: t.Any) -> None:
        side = self.my_side(conn)
        if side is not None and value is True:
            self.battle.special(side)

    # ---------- What the pages see ----------

    def state(self) -> dict:
        return {
            "state": {
                "stage": self.stage,
                "difficulty": self.difficulty,
                "host": self.host,
                "seats": [self.seat_state(number) for number in range(SEATS)],
                "players": self.players,
                "watching": self.watching(),
                "paused": self.paused,
                "waiting": self.stage == PLAYING and self.waiting_for_solo(),
                "results": self.results,
            }
        }

    def seat_state(self, number: int) -> dict:
        seat = self.seats[number]
        return {
            "kind": "human" if seat.human else "empty",
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(seat.user_id) if seat.human else None,
            "name": seat.name,
            "avatar": seat.avatar,
            "away": seat.dropped_at is not None,
            "standIn": seat.stand_in,
        }

    def watching(self) -> int:
        players = [seat.conn for seat in self.seats if seat.conn is not None]
        return sum(1 for conn in self.room.connections if not any(conn is player for player in players))
