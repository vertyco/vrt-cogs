"""One Activity window's match: seats and the host, setup, the shop, rounds of turns on a clock, shots that every
page plays back, results, and players dropping out and coming back"""

import asyncio
import logging
import math
import random
import typing as t
from dataclasses import dataclass

from .cpu import LEVELS, Brain
from .items import (
    AIR_STRIKE,
    EXTRAS,
    REPAIR,
    REPAIR_AMOUNT,
    SHIELDS,
    TELEPORT,
    WEAPONS,
    Kit,
)
from .leaderboard import Result
from .physics import STEP_RATE, Shot
from .tank import (
    MAX_X,
    MIN_X,
    Tank,
    check_death,
    drive_frame,
    land,
    place,
    settle_frame,
    start_settling,
)
from .terrain import HEIGHT, LANDSCAPES, Field, generate

log = logging.getLogger("red.vrt.tanks.match")

TICK_RATE = 20
DT = 1 / TICK_RATE
SEATS = 5
# How long the shop and each turn last, from the host's choices, or "off" for no clock
TIMER_CHOICES = (30, 60, 90, 120)
DEFAULT_TIMER = 60
# A breath between a shot's last frame and the next turn
SHOT_PAUSE_SECONDS = 0.6
CPU_THINK_SECONDS = (1.0, 2.0)
TAKEOVER_SECONDS = 60
SETUP_GRACE_SECONDS = 20
ROUND_CHOICES = (3, 5, 10)
DEFAULT_ROUNDS = 5
# After a freeze longer than this, the loop skips the updates it missed instead of running them all at once
CATCH_UP_SECONDS = 0.25
# A safety net: a round settles within this many frames
SETTLE_LIMIT = 2000
# The biggest whole number a page's JavaScript holds exactly. Bigger ones can't even become a float
MAX_WHOLE = 2**53 - 1

SETUP = "setup"
SHOP = "shop"
PLAYING = "playing"
RESULTS = "results"

SEAT_TAKEN = "That seat was just taken."
LOOP_FAILED = "Something went wrong, so the match was stopped."
EVERYONE_LEFT = "Every player left, so the match was stopped."


@dataclass
class Seat:
    """One tank's seat: a person sits in it, a computer plays it, or it is empty"""

    user_id: int | None = None
    name: str = ""
    # The name the global leaderboard shows: the Discord-wide one, since the board covers every server
    board_name: str = ""
    avatar: str = ""
    conn: t.Any = None
    # When the player's connection dropped, on the match's clock, while their seat is kept for them
    dropped_at: float | None = None
    # A computer seat's difficulty
    level: str | None = None
    brain: Brain | None = None
    # A normal computer playing a person's tank while they're away
    stand_in: Brain | None = None
    # A computer played this person's tank at some point this match, so it can't win
    taken: bool = False
    kit: Kit | None = None
    done: bool = False

    @property
    def human(self) -> bool:
        return self.user_id is not None

    @property
    def cpu(self) -> bool:
        return self.level is not None

    @property
    def filled(self) -> bool:
        return self.human or self.cpu

    @property
    def present(self) -> bool:
        return self.human and self.conn is not None

    def clear(self) -> None:
        self.user_id, self.name, self.board_name, self.avatar = None, "", "", ""
        self.conn, self.dropped_at, self.level, self.brain, self.stand_in = None, None, None, None, None
        self.taken, self.kit, self.done = False, None, False


def number(value: t.Any) -> bool:
    """A real JSON number: not a bool, not NaN or infinity, and not a whole number too big for a page to send"""
    if type(value) is int:
        return abs(value) <= MAX_WHOLE
    return type(value) is float and math.isfinite(value)


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
        `room` is the window's ActivityHub room. `record(results)` gets each finished match's results for the
        leaderboard, and `ended(match)` is called once the update loop has stopped
        """
        self.room = room
        self.record = record
        self.ended = ended
        self.rng = rng or random.Random()
        self.clock = clock or asyncio.get_running_loop().time
        self.seats = [Seat() for _ in range(SEATS)]
        self.host: int | None = None
        self.rounds = DEFAULT_ROUNDS
        self.landscape: str | int = "random"
        self.timer: int | str = DEFAULT_TIMER
        self.stage = SETUP
        self.round = 0
        self.field: Field | None = None
        self.tanks: dict[int, Tank] = {}
        self.turn: int | None = None
        # Timers count updates, so they end on an exact update
        # The shop's or the turn's clock, in updates. A turn with no clock has None
        self.stage_left: int | None = 0
        self.shot_left = 0
        self.think_left = 0
        self.think_total = 1
        self.think_from: tuple[int, float] = (90, 50.0)
        self.think_to: tuple[int, float] = (90, 50.0)
        self.drive = 0
        # Frames of the original's 25 a second still owed to the turn's tank, at 20 updates a second
        self.frames_owed = 0.0
        # A fire or teleport waiting for the next update: (kind, value)
        self.queued: tuple[str, t.Any] | None = None
        # Who plays the current turn: "human" or "cpu", fixed when the turn starts
        self.turn_by: str | None = None
        self.firing = False
        # Who was seated when the match started: seat number to (user id, leaderboard name)
        self.players: dict[int, tuple[int, str]] = {}
        self.results: list[dict] | None = None
        self.tick_count = 0
        # Set when the pages need a full snapshot. Held back while a shot plays, so it can't jump ahead of it
        self.dirty = True
        self.live_sent: list | None = None
        # Notices for everyone in the window, sent with the next update
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
        """The update loop: TICK_RATE updates a second, each timed from a fixed start so delays don't add up"""
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
            log.error("Tanks stopped a match in window %s", self.room.instance_id, exc_info=e)
            await self.room.broadcast({"notice": LOOP_FAILED})
        finally:
            self.ended(self)

    async def tick(self) -> None:
        """One update: drops, the stage's clocks and the turn, then what the pages need to see"""
        self.expire_drops()
        if self.stage == SHOP:
            self.tick_shop()
        elif self.stage == PLAYING:
            await self.tick_playing()
        self.tick_count += 1
        for message in self.outbox:
            await self.room.broadcast(message)
        self.outbox = []
        if self.firing:
            return
        if self.dirty:
            self.dirty = False
            self.live_sent = None
            await self.room.broadcast(self.state())
            return
        live = self.live()
        if live is not None and live != self.live_sent:
            self.live_sent = live
            await self.room.broadcast({"t": live})

    def seconds(self, ticks: int) -> int:
        return math.ceil(ticks / TICK_RATE)

    def count_down(self, ticks: int) -> int:
        """Take one update off a timer, and refresh the pages when the whole seconds they show change"""
        left = ticks - 1
        if self.seconds(left) != self.seconds(ticks):
            self.dirty = True
        return left

    # ---------- Seats and the host ----------

    def seat_of(self, user_id: int) -> Seat | None:
        return next((seat for seat in self.seats if seat.human and seat.user_id == user_id), None)

    def number_of(self, conn: t.Any) -> int | None:
        return next((number for number, seat in enumerate(self.seats) if seat.conn is conn), None)

    def fix_host(self) -> None:
        """The host is the first person seated. When they stand up or leave, the next seated person takes over"""
        if self.host is not None and self.seats[self.host].present:
            return
        self.host = next((number for number, seat in enumerate(self.seats) if seat.present), None)

    def is_host(self, conn: t.Any) -> bool:
        return self.host is not None and self.number_of(conn) == self.host

    async def join(self, conn: t.Any) -> None:
        seat = self.seat_of(conn.ctx.author.id)
        if seat is not None:
            # Back from a drop, or the same player on a second device: this connection drives their tank now.
            # The old connection's leave finds it no longer holds the seat, and leaves it alone
            seat.conn, seat.dropped_at = conn, None
            if self.seats.index(seat) == self.turn:
                # A key held down on the old connection can never be let go now
                self.drive = 0
            self.fix_host()
        self.dirty = True
        await conn.send(self.state())

    def leave(self, conn: t.Any) -> None:
        number = self.number_of(conn)
        if number is not None:
            seat = self.seats[number]
            # The same player may still have the game open on another device, which drives the tank from now on
            others = [other for other in self.room.connections if other is not conn]
            seat.conn = next((other for other in others if other.ctx.author.id == seat.user_id), None)
            if seat.conn is None:
                seat.dropped_at = self.clock()
                if number == self.turn:
                    self.drive = 0
            self.fix_host()
        self.dirty = True

    def expire_drops(self) -> None:
        """Seats kept past their grace period. Before and after a match the seat empties. During one, a normal
        computer takes the tank over, unless nobody is left, which stops the match"""
        now = self.clock()
        for seat in self.seats:
            if seat.dropped_at is None:
                continue
            away = now - seat.dropped_at
            if self.stage in (SETUP, RESULTS):
                if away >= SETUP_GRACE_SECONDS:
                    seat.clear()
                    self.fix_host()
                    self.dirty = True
                    if self.stage == RESULTS and not any(other.human for other in self.seats):
                        # Nobody is left to press Continue, so whoever is watching can sit down for the next one
                        self.back_to_setup()
            elif away >= TAKEOVER_SECONDS and seat.stand_in is None:
                if not any(other.present for other in self.seats):
                    self.stop_match()
                    return
                self.take_over(self.seats.index(seat))

    def take_over(self, number: int) -> None:
        """A normal computer plays an away player's tank for the rest of the match, from this moment"""
        seat = self.seats[number]
        seat.stand_in, seat.taken = Brain("normal"), True
        tank = self.tanks.get(number)
        if tank is not None:
            seat.stand_in.new_round(tank, list(self.tanks.values()))
            if number == self.turn and not self.firing:
                self.plan_cpu()
        self.dirty = True

    def stop_match(self) -> None:
        """Every player left mid-match: nothing is recorded, and the window goes back to setup"""
        for seat in self.seats:
            if seat.human and seat.conn is None:
                seat.clear()
        self.back_to_setup()
        self.outbox.append({"notice": EVERYONE_LEFT})

    def back_to_setup(self) -> None:
        for seat in self.seats:
            seat.kit, seat.done, seat.stand_in, seat.taken, seat.brain = None, False, None, False, None
        self.stage, self.round, self.field, self.tanks = SETUP, 0, None, {}
        self.turn, self.turn_by, self.results, self.firing, self.queued = None, None, None, False, None
        self.players = {}
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
            "cpu": self.set_cpu,
            "rounds": self.set_rounds,
            "landscape": self.set_landscape,
            "timer": self.set_timer,
            "start": self.start_match,
            "continue": self.go_on,
            "buy": self.buy,
            "done": self.shop_done,
            "aim": self.aim,
            "drive": self.steer,
            "weapon": self.pick_weapon,
            "use": self.use,
            "fire": self.fire,
        }

    # ---------- Setup ----------

    def sit(self, conn: t.Any, value: t.Any) -> str | None:
        """Seat a watcher. Returns a notice for them when the seat was already taken"""
        author = conn.ctx.author
        if type(value) is not int or not 0 <= value < SEATS or self.stage != SETUP or self.seat_of(author.id):
            return None
        seat = self.seats[value]
        if seat.filled:
            # Two players tapped this seat at once, and the bot handled the other tap first
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

    def set_cpu(self, conn: t.Any, value: t.Any) -> None:
        if self.stage != SETUP or not self.is_host(conn) or not isinstance(value, list) or len(value) != 2:
            return
        number, level = value
        if type(number) is not int or not 0 <= number < SEATS or self.seats[number].human:
            return
        if level is None:
            self.seats[number].clear()
        elif level in LEVELS:
            self.seats[number].level = level
            self.seats[number].name = f"CPU {number + 1}"
        else:
            return
        self.dirty = True

    def set_rounds(self, conn: t.Any, value: t.Any) -> None:
        if self.stage == SETUP and self.is_host(conn) and type(value) is int and value in ROUND_CHOICES:
            self.rounds = value
            self.dirty = True

    def set_landscape(self, conn: t.Any, value: t.Any) -> None:
        valid = value == "random" or (type(value) is int and value in LANDSCAPES)
        if self.stage == SETUP and self.is_host(conn) and valid:
            self.landscape = value
            self.dirty = True

    def set_timer(self, conn: t.Any, value: t.Any) -> None:
        valid = value == "off" or (type(value) is int and value in TIMER_CHOICES)
        if self.stage == SETUP and self.is_host(conn) and valid:
            self.timer = value
            self.dirty = True

    def start_match(self, conn: t.Any, value: t.Any) -> None:
        filled = [number for number, seat in enumerate(self.seats) if seat.filled]
        if value is not True or self.stage != SETUP or not self.is_host(conn) or len(filled) < 2:
            return
        for number in filled:
            seat = self.seats[number]
            seat.kit, seat.taken, seat.stand_in = Kit(), False, None
            seat.brain = Brain(seat.level) if seat.cpu else None
        self.players = {n: (seat.user_id, seat.board_name) for n, seat in enumerate(self.seats) if seat.human}
        self.round = 0
        self.open_shop()

    def go_on(self, conn: t.Any, value: t.Any) -> None:
        """Continue from the results back to setup, with the same seats and settings"""
        if value is True and self.stage == RESULTS and self.is_host(conn):
            self.back_to_setup()

    # ---------- The shop ----------

    def open_shop(self) -> None:
        self.stage, self.stage_left, self.dirty = SHOP, self.clock_ticks(), True
        self.turn, self.field, self.tanks = None, None, {}
        for seat in self.seats:
            seat.done = False

    def people(self) -> list[Seat]:
        """Seats a person plays, counting one whose connection just dropped until a computer takes their tank over.
        Computer tanks and away players' stand-ins aren't people"""
        return [
            seat
            for seat in self.seats
            if seat.human and seat.kit is not None and (seat.present or seat.stand_in is None)
        ]

    def tick_shop(self) -> None:
        if self.stage_left is not None:
            self.stage_left = self.count_down(self.stage_left)
        out_of_time = self.stage_left is not None and self.stage_left <= 0
        # Computer tanks never shop, as in the original. Someone who dropped is waited for, up to the shop's clock
        if out_of_time or all(seat.done for seat in self.people()):
            self.start_round()

    def buy(self, conn: t.Any, value: t.Any) -> str | None:
        number = self.number_of(conn)
        if self.stage != SHOP or number is None or self.seats[number].done or not isinstance(value, list):
            return None
        if len(value) != 2 or value[0] not in ("weapon", "item") or type(value[1]) is not int:
            return None
        kind, item = value
        items = WEAPONS if kind == "weapon" else EXTRAS
        if not 0 <= item < len(items) or (kind == "weapon" and item == 0):
            return None
        notice = self.seats[number].kit.buy("weapon" if kind == "weapon" else "extra", item)
        self.dirty = True
        return notice

    def shop_done(self, conn: t.Any, value: t.Any) -> None:
        number = self.number_of(conn)
        if value is True and self.stage == SHOP and number is not None and self.seats[number].kit is not None:
            self.seats[number].done = True
            self.dirty = True

    # ---------- Rounds ----------

    def start_round(self) -> None:
        self.round += 1
        landscape = self.rng.choice(LANDSCAPES) if self.landscape == "random" else self.landscape
        self.field = generate(landscape, self.rng)
        numbers = [number for number, seat in enumerate(self.seats) if seat.kit is not None]
        self.tanks = {}
        for number, x in zip(numbers, place(self.field, numbers, self.rng)):
            self.tanks[number] = Tank(number, self.seats[number].kit, x)
        for tank in self.tanks.values():
            land(tank, self.field, self.rng)
        self.settle_now()
        for number, tank in self.tanks.items():
            for brain in (self.seats[number].brain, self.seats[number].stand_in):
                if brain is not None:
                    brain.new_round(tank, list(self.tanks.values()))
        self.stage, self.turn, self.dirty = PLAYING, None, True
        self.next_turn()

    def settle_now(self) -> None:
        """Drop every new tank onto the ground before the round is shown"""
        for tank in self.tanks.values():
            start_settling(tank)
        for _ in range(SETTLE_LIMIT):
            settling = [tank for tank in self.tanks.values() if tank.settling]
            if not settling:
                break
            for tank in settling:
                settle_frame(tank, self.field)
        for tank in self.tanks.values():
            tank.settling = False
            if tank.y > HEIGHT:
                check_death(tank)

    def controller(self, number: int) -> str | None:
        """Who plays this seat's turn: "human", "cpu", or None when its player is away and the turn is skipped"""
        seat = self.seats[number]
        if seat.cpu:
            return "cpu"
        if seat.conn is not None:
            return "human"
        if seat.stand_in is not None:
            return "cpu"
        return None

    def next_turn(self) -> None:
        """The next living tank in seat order whose player is here. A round opens with the lowest total score"""
        numbers = sorted(self.tanks)
        if self.turn is None:
            first = min(numbers, key=lambda n: (self.seats[n].kit.score, n))
            order = numbers[numbers.index(first) :] + numbers[: numbers.index(first)]
        else:
            later = [n for n in numbers if n > self.turn]
            order = later + [n for n in numbers if n <= self.turn]
        previous = self.turn
        self.turn = next((n for n in order if self.tanks[n].alive and self.controller(n)), None)
        self.turn_by = None
        if self.turn is not None:
            self.begin_turn()
        if self.turn is not None or previous is not None:
            # While every remaining player is away this runs each update, and nothing changes
            self.dirty = True

    def begin_turn(self) -> None:
        tank = self.tanks[self.turn]
        seat = self.seats[self.turn]
        self.field.change_wind(self.rng)
        tank.start_turn()
        self.stage_left = self.clock_ticks()
        self.drive, self.frames_owed, self.queued = 0, 0.0, None
        if seat.human and seat.conn is not None:
            # Back in time for their turn: the person plays again, though the match still counts as taken over
            seat.stand_in = None
        if self.controller(self.turn) == "cpu":
            self.plan_cpu()
        else:
            self.turn_by = "human"

    def clock_ticks(self) -> int | None:
        """How long the shop or a turn lasts, in updates. One person against computers keeps nobody waiting, so they
        get no clock"""
        if self.timer == "off" or len(self.people()) <= 1:
            return None
        return self.timer * TICK_RATE

    def plan_cpu(self) -> None:
        """The computer picks its shot now, and takes 1 to 2 seconds to swing its barrel there"""
        tank = self.tanks[self.turn]
        target = self.brain_of(self.turn).plan(tank, list(self.tanks.values()), self.field.wind)
        self.turn_by = "cpu"
        self.drive = 0
        self.think_from, self.think_to = (tank.angle, tank.power), target
        self.think_total = max(1, round(self.rng.uniform(*CPU_THINK_SECONDS) * TICK_RATE))
        self.think_left = self.think_total

    def brain_of(self, number: int) -> Brain | None:
        seat = self.seats[number]
        return seat.brain if seat.cpu else seat.stand_in

    async def tick_playing(self) -> None:
        if self.firing:
            self.shot_left -= 1
            if self.shot_left <= 0:
                self.firing = False
                self.after_shot()
            return
        if self.turn is None:
            self.next_turn()
            return
        if self.stage_left is not None:
            # The clock's seconds reach the pages in the small live update, not a full snapshot
            self.stage_left -= 1
            if self.stage_left <= 0:
                # Out of time: the turn passes with no shot
                self.next_turn()
                return
        if self.turn_by == "cpu":
            await self.tick_cpu()
        else:
            await self.tick_person()

    async def tick_cpu(self) -> None:
        """The computer's barrel swings to its chosen angle while it thinks, then it fires"""
        tank = self.tanks[self.turn]
        self.think_left -= 1
        share = 1 - self.think_left / self.think_total
        (from_angle, from_power), (to_angle, to_power) = self.think_from, self.think_to
        tank.angle = round(from_angle + (to_angle - from_angle) * share)
        tank.power = from_power + (to_power - from_power) * share
        if self.think_left <= 0:
            tank.angle, tank.power = to_angle, to_power
            self.brain_of(self.turn).fired(self.field.wind)
            await self.shoot(Shot(self.field, list(self.tanks.values()), tank, self.rng), "fire", None)

    async def tick_person(self) -> None:
        tank = self.tanks[self.turn]
        if self.queued is not None:
            kind, value = self.queued
            self.queued = None
            await self.shoot(Shot(self.field, list(self.tanks.values()), tank, self.rng), kind, value)
            return
        self.frames_owed += STEP_RATE / TICK_RATE
        while self.frames_owed >= 1:
            self.frames_owed -= 1
            health = tank.energy
            drive_frame(tank, self.field, list(self.tanks.values()), self.drive)
            if tank.energy != health:
                # Hurt by driving off a ledge: the health bar is in the full snapshot, not the live update
                self.dirty = True
            if tank.energy <= 0 or tank.y > HEIGHT:
                # Drove off a cliff: the wreck blows up and everyone settles, like the end of a shot
                await self.shoot(Shot(self.field, list(self.tanks.values()), tank, self.rng), "fall", None)
                return

    async def shoot(self, shot: Shot, kind: str, value: t.Any) -> None:
        """Work the whole shot out now, send it to every page once, and wait while they play it"""
        tank = shot.shooter
        if kind == "fire":
            weapon = tank.kit.spend_shot()
            shot.fire(weapon, tuple(value) if value else (0.0, 1))
        elif kind == "teleport":
            tank.kit.extras[TELEPORT] -= 1
            shot.teleport(*value)
        script = shot.run()
        for each in self.tanks.values():
            each.settling = False
        self.firing = True
        self.shot_left = math.ceil((script["steps"] / STEP_RATE + SHOT_PAUSE_SECONDS) * TICK_RATE)
        await self.room.broadcast({"shot": script})

    def after_shot(self) -> None:
        alive = [tank for tank in self.tanks.values() if tank.alive]
        if len(alive) <= 1:
            self.end_round()
        else:
            self.next_turn()

    def end_round(self) -> None:
        if self.round >= self.rounds:
            self.finish()
        else:
            self.open_shop()

    def finish(self) -> None:
        """The highest total score wins the match, and everyone tied for it wins"""
        playing = [number for number, seat in enumerate(self.seats) if seat.kit is not None]
        best = max(self.seats[number].kit.score for number in playing)
        winners = [number for number in playing if self.seats[number].kit.score == best]
        self.results = [
            {
                "seat": number,
                "name": self.seats[number].name,
                "score": round(self.seats[number].kit.score),
                "kills": self.seats[number].kit.kills,
                "won": number in winners,
            }
            for number in playing
        ]
        # Idle alt accounts in spare seats would hand one player every win. Fine with no credits paid
        results = [
            Result(user_id, name, self.seats[n].kit.kills, n in winners and not self.seats[n].taken)
            for n, (user_id, name) in self.players.items()
        ]
        if results:
            self.record(results)
        self.stage, self.turn, self.field, self.tanks, self.dirty = RESULTS, None, None, {}, True

    # ---------- The turn's player ----------

    def my_turn(self, conn: t.Any) -> Tank | None:
        """The tank this connection may steer: it's their turn, they play it themselves, and no shot is waiting"""
        number = self.number_of(conn)
        if self.stage != PLAYING or self.firing or self.queued is not None or number is None or number != self.turn:
            return None
        if self.turn_by != "human":
            return None
        return self.tanks[number]

    def aim(self, conn: t.Any, value: t.Any) -> None:
        tank = self.my_turn(conn)
        if tank is None or not isinstance(value, list) or len(value) != 2 or not all(number(v) for v in value):
            return
        tank.angle = min(max(round(value[0]), 0), 180)
        tank.power = min(max(float(round(value[1])), 0.0), 100.0, tank.energy)

    def steer(self, conn: t.Any, value: t.Any) -> None:
        if self.my_turn(conn) is not None and type(value) is int and value in (-1, 0, 1):
            self.drive = value

    def pick_weapon(self, conn: t.Any, value: t.Any) -> None:
        tank = self.my_turn(conn)
        if tank is not None and type(value) is int and 0 <= value < len(WEAPONS) and tank.kit.owns(value):
            tank.kit.weapon = value
            self.dirty = True

    def use(self, conn: t.Any, value: t.Any) -> None:
        tank = self.my_turn(conn)
        if tank is None:
            return
        if value == "repair":
            self.repair(tank)
        elif isinstance(value, list) and len(value) == 2 and value[0] == "shield" and type(value[1]) is int:
            self.shield(tank, value[1])
        elif isinstance(value, list) and len(value) == 3 and value[0] == "teleport" and all(map(number, value[1:])):
            if tank.kit.extras[TELEPORT] > 0:
                x = min(max(float(value[1]), MIN_X), MAX_X)
                y = min(max(float(value[2]), 0.0), float(HEIGHT))
                self.queued = ("teleport", (x, y))

    def repair(self, tank: Tank) -> None:
        if tank.kit.extras[REPAIR] > 0 and tank.energy < tank.max_energy:
            tank.kit.extras[REPAIR] -= 1
            tank.energy = min(tank.max_energy, tank.energy + REPAIR_AMOUNT)
            self.dirty = True

    def shield(self, tank: Tank, which: int) -> None:
        if 1 <= which <= len(SHIELDS) and tank.shield is None and tank.kit.extras[SHIELDS[which - 1]] > 0:
            tank.raise_shield(SHIELDS[which - 1])
            self.dirty = True

    def fire(self, conn: t.Any, value: t.Any) -> None:
        tank = self.my_turn(conn)
        if tank is None:
            return
        if tank.kit.weapon == AIR_STRIKE:
            valid = isinstance(value, list) and len(value) == 2 and number(value[0]) and value[1] in (-1, 1)
            if valid and type(value[1]) is int:
                self.queued = ("fire", (min(max(float(value[0]), 0.0), 550.0), value[1]))
        elif value is True:
            self.queued = ("fire", None)

    # ---------- What the pages see ----------

    def live(self) -> list | None:
        """The turn's tank, sent whenever it changes: seat, position, barrel, power, fuel, weapon and the clock"""
        if self.stage != PLAYING or self.turn is None:
            return None
        tank = self.tanks[self.turn]
        return [
            self.turn,
            round(tank.x, 1),
            round(tank.y, 1),
            tank.angle,
            round(tank.power),
            max(0, round(tank.fuel)),
            tank.kit.weapon,
            None if self.stage_left is None else self.seconds(self.stage_left),
        ]

    def state(self) -> dict:
        """Everything a page needs to draw the window from scratch"""
        clock = None
        if self.stage_left is not None and (self.stage == SHOP or (self.stage == PLAYING and self.turn is not None)):
            clock = self.seconds(self.stage_left)
        return {
            "state": {
                "stage": self.stage,
                "rounds": self.rounds,
                "landscape": self.landscape,
                "timer": self.timer,
                "round": self.round,
                "host": self.host,
                "seats": [self.seat_state(number) for number in range(SEATS)],
                "watching": self.watching(),
                "clock": clock,
                "field": self.field_state(),
                "turn": self.turn,
                "tanks": [self.tanks[n].view() if n in self.tanks else None for n in range(SEATS)],
                "kits": [seat.kit.view() if seat.kit is not None else None for seat in self.seats],
                "done": [seat.done for seat in self.seats],
                "results": self.results,
            }
        }

    def field_state(self) -> dict | None:
        if self.field is None:
            return None
        return {
            "landscape": self.field.landscape,
            "ground": self.field.ground_view(),
            "trees": [list(tree) for tree in self.field.trees],
            "wind": round(self.field.wind, 1),
        }

    def seat_state(self, number: int) -> dict:
        seat = self.seats[number]
        kind = "human" if seat.human else "cpu" if seat.cpu else "empty"
        return {
            "kind": kind,
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(seat.user_id) if seat.human else None,
            "name": seat.name,
            "avatar": seat.avatar,
            "level": seat.level,
            "away": seat.dropped_at is not None,
            "standIn": seat.stand_in is not None,
        }

    def watching(self) -> int:
        players = [seat.conn for seat in self.seats if seat.conn is not None]
        return sum(1 for conn in self.room.connections if not any(conn is player for player in players))
