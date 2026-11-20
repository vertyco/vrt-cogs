"""One Activity window's game: seats, the countdown, rounds and the locked update loop"""

import asyncio
import logging
import math
import random
import typing as t
from dataclasses import asdict, dataclass, field

from .cpu import NAMES, Cpu
from .leaderboard import Result
from .maps import IceMap, pick_map
from .round import DT, SEATS, SNOWBALL_RANGE, TICK_RATE, Round
from .shop import GIVEN, Played
from .tuning import TWISTS, Tuning, fish_pace, twist_tuning

log = logging.getLogger("red.vrt.penguinwars.match")

COUNTDOWN_SECONDS = 10
STARTING_SECONDS = 3
RESULTS_SECONDS = 6
GRACE_SECONDS = 20
# After a freeze longer than this, the loop skips the updates it missed instead of sending them all at once
CATCH_UP_SECONDS = 0.25
# Biggest numbers taken from a page. Compared before any conversion, so NaN, infinity and 400-digit whole numbers
# all fail the check, and squaring a direction can't overflow
MAX_DIRECTION = 1e6
MAX_POWER = 100
MAX_ANGLE = 1e6

WAITING = "waiting"
STARTING = "starting"
PLAYING = "playing"
RESULTS = "results"
# Stages where players may sit down and stand up
OPEN_STAGES = (WAITING, RESULTS)
# Stages where a free spot can be taken: between rounds, and during the 3-2-1, when a CPU's penguin is taken over
SEATING_STAGES = (WAITING, STARTING, RESULTS)

LOOP_FAILED = "Something went wrong, so the round was stopped."

# One person throws at most one snowball in this many updates
SNOWBALL_WAIT = TICK_RATE
NO_SNOWBALLS = "Snowballs fly during a round."
# Why the round takes no snowball, worded for the thrower
SNOWBALL_REFUSALS = {
    "ended": NO_SNOWBALLS,
    "full": "Too many snowballs are in the air.",
    "far": "Aim at the ice.",
}


def number_ok(value: t.Any, limit: float) -> bool:
    return type(value) in (int, float) and abs(value) <= limit


@dataclass
class Seat:
    """One penguin's seat: a person sits in it, a CPU plays it, or it is empty"""

    user_id: int | None = None
    name: str = ""
    # What the person here wears, as {kind: item}. A CPU wears what everyone is given
    looks: dict[str, str] = field(default_factory=dict)
    conn: t.Any = None
    # When the player's connection dropped, on the match's clock, while their seat is kept for them
    dropped_at: float | None = None
    cpu: Cpu | None = None

    @property
    def human(self) -> bool:
        return self.user_id is not None

    def clear(self) -> None:
        self.user_id, self.name, self.looks = None, "", {}
        self.conn, self.dropped_at, self.cpu = None, None, None


class Match:
    def __init__(
        self,
        room: t.Any,
        tuning: Tuning,
        ended: t.Callable[["Match"], None],
        rng: random.Random | None = None,
        clock: t.Callable[[], float] | None = None,
        recorded: t.Callable[[t.Any, list[Result]], None] | None = None,
        played: t.Callable[["Match", list[Played]], None] | None = None,
    ):
        """
        `room` is the window's ActivityHub room, and `ended(match)` is called once the update loop has stopped.
        `recorded(guild_id, results)` is called when a round that counts for the leaderboard ends, and
        `played(match, people)` when any round ends, with the people who played it to its end
        """
        self.room = room
        self.recorded = recorded
        self.played = played
        # The server this window is in, None in a DM
        self.guild_id: int | None = None
        self.tuning = tuning
        self.ended = ended
        self.rng = rng or random.Random()
        self.clock = clock or asyncio.get_running_loop().time
        self.seats = [Seat() for _ in range(SEATS)]
        self.looks: dict[int, dict] = {}
        # Watchers waiting for a spot, first come first served, by user id
        self.line: list[int] = []
        # When someone in the line lost their last connection, on the match's clock. Their place is kept for the grace
        # period, as a seat is, so a moment's drop doesn't cost it
        self.line_drops: dict[int, float] = {}
        # Who the last swap sat out, so their card can say why
        self.sat_out: list[int] = []
        self.stage = WAITING
        # Timers count updates, so they end on an exact update
        self.countdown: int | None = None
        self.stage_left = 0
        self.round: Round | None = None
        # The ice every round here is played on. None picks a shape and a hazard by chance as each round begins
        self.fixed_map: IceMap | None = None
        # The update each watcher last threw a snowball on, by user id, for the round being played
        self.threw: dict[int, int] = {}
        # The party round being played, as {kind, by (the name of who paid), name, line}, and the one paid for
        # that the next round to begin will be
        self.twist: dict | None = None
        self.next_twist: dict | None = None
        self.round_number = 1
        # Who was seated when the round started: seat number to user id
        self.round_players: dict[int, int] = {}
        # Set while the results show: the round's results plus the winner's name, which outlives a seat swap
        self.results: dict | None = None
        # Set when a seated player pressed Play again during the results
        self.play_again = False
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
            log.error("Penguin Wars stopped a round in window %s", self.room.instance_id, exc_info=e)
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
            message = self.state()
            # Events the round holds now are drained here, so they ride this snapshot instead of a frame
            if self.round is not None and self.round.events:
                message["state"]["board"]["e"], self.round.events = self.round.events, []
            await self.room.broadcast(message)
        elif self.stage == PLAYING:
            await self.room.broadcast(self.round.frame())

    def count_down(self, ticks: int) -> int:
        """Take one update off a timer, and refresh the pages when the whole seconds they show change"""
        left = ticks - 1
        if math.ceil(left / TICK_RATE) != math.ceil(ticks / TICK_RATE):
            self.dirty = True
        return left

    # ---------- Stages ----------

    def people_seated(self) -> int:
        """Seats held by people, counting anyone in their grace period after a drop"""
        return sum(1 for seat in self.seats if seat.human)

    def someone_connected(self) -> bool:
        """A seated person whose page is open"""
        return any(seat.human and seat.conn is not None for seat in self.seats)

    def start_countdown(self) -> None:
        """Between rounds, the 10-second countdown runs only for two or more people. Someone alone starts with a tap"""
        if self.stage == WAITING and self.countdown is None and self.people_seated() >= 2:
            self.countdown = COUNTDOWN_SECONDS * TICK_RATE

    def results_held(self) -> bool:
        """One person alone at the results, with nobody in the line: the end card stays until they act"""
        return self.stage == RESULTS and self.people_seated() == 1 and not self.line

    def tick_waiting(self) -> None:
        if self.line and self.free_spot() is not None:
            self.fill_free_spots()
        if self.countdown is None:
            return
        if self.people_seated() < 2:
            self.countdown = None
            self.dirty = True
            return
        self.countdown = self.count_down(self.countdown)
        if self.countdown > 0:
            return
        if self.someone_connected():
            self.begin_round()
        else:
            # Only dropped players are seated: wait for one of them to come back
            self.countdown = None
            self.dirty = True

    def begin_round(self) -> None:
        self.twist, self.next_twist = self.next_twist, None
        kind = self.twist_kind()
        ice_map = self.fixed_map or pick_map(self.rng)
        self.round = Round(twist_tuning(self.tuning, kind), self.rng, fish_pace(kind), ice_map)
        self.results = None
        self.threw = {}
        self.play_again = False
        self.round_players = {}
        for number, seat in enumerate(self.seats):
            if seat.human:
                self.round_players[number] = seat.user_id
            else:
                self.seat_cpu(number, seat)
        self.countdown = None
        self.stage, self.stage_left, self.dirty = STARTING, STARTING_SECONDS * TICK_RATE, True

    def seat_cpu(self, number: int, seat: Seat) -> None:
        """A CPU plays this seat from now on"""
        seat.user_id, seat.conn, seat.dropped_at, seat.looks = None, None, None, dict(GIVEN)
        seat.cpu, seat.name = Cpu(number, self.rng), NAMES[number]
        if self.round is not None:
            self.round.cpus.add(number)

    def tick_starting(self) -> None:
        if self.line and self.free_spot() is not None:
            self.fill_free_spots()
        self.stage_left = self.count_down(self.stage_left)
        if self.stage_left <= 0:
            self.stage, self.dirty = PLAYING, True

    def tick_playing(self) -> None:
        humans = [number for number, seat in enumerate(self.seats) if seat.human]
        for seat in self.seats:
            if seat.cpu is not None:
                seat.cpu.act(self.round, humans)
        self.round.step()
        if self.round.finished:
            self.end_round()

    def end_round(self) -> None:
        results = self.round.results()
        winner = results["winner"]
        results["name"] = self.seats[winner].name if winner is not None else None
        self.results = results
        self.stage, self.stage_left, self.dirty = RESULTS, RESULTS_SECONDS * TICK_RATE, True
        if self.recorded is not None:
            self.record_round(results)
        if self.played is not None:
            self.report_played(results)

    def round_people(self) -> list[tuple[int, Seat]]:
        """The people who played this round and still hold their seats, as (seat number, seat). A seat taken over by
        a CPU, or by someone new, earns its first owner nothing"""
        seats = ((number, self.seats[number]) for number in self.round_players)
        return [(n, seat) for n, seat in seats if seat.human and seat.user_id == self.round_players[n]]

    def record_round(self, results: dict) -> None:
        """Hand the leaderboard the people who played this round and still hold their seats. Needs two people"""
        if len(self.round_players) < 2:
            return
        counted = []
        for number, seat in self.round_people():
            name = self.name_now(seat)
            counted.append(Result(seat.user_id, name, results["knocked"][number], results["winner"] == number))
        if counted:
            self.recorded(self.guild_id, counted)

    def name_now(self, seat: Seat) -> str:
        """The name of the person in a seat as it is now, since people rename mid-round"""
        return seat.conn.ctx.author.display_name if seat.conn is not None else seat.name

    def report_played(self, results: dict) -> None:
        """Hand the cog everyone's part in this round, for the play counts that unlock looks and for who knocked
        whom out. A round played alone against CPUs counts too. A knockout by a CPU, or by someone who did not play
        the round to its end, is nobody's"""
        seats = dict(self.round_people())
        people = []
        for number, seat in seats.items():
            foe = seats.get(results["by"][number])
            people.append(
                Played(
                    user_id=seat.user_id,
                    won=results["winner"] == number,
                    knockouts=results["knocked"][number],
                    fish=results["fish"][number],
                    seal=results["seal"][number],
                    bounce=results["bounce"][number],
                    people=len(self.round_players),
                    by=foe.user_id if foe is not None else None,
                    by_name=self.name_now(foe) if foe is not None else "",
                )
            )
        if people:
            self.played(self, people)

    async def tell(self, user_id: int, message: dict) -> None:
        """Send something to one person, on every device they have the game open on"""
        for conn in list(self.room.connections):
            if conn.ctx.author.id == user_id:
                await conn.send(message)

    def tick_results(self) -> None:
        if not self.play_again:
            if self.results_held():
                return
            self.stage_left = self.count_down(self.stage_left)
            if self.stage_left > 0:
                return
        self.swap_line()
        for seat in self.seats:
            if seat.cpu is not None:
                seat.clear()
        self.round, self.results, self.twist = None, None, None
        self.round_number += 1
        self.stage, self.dirty = WAITING, True
        if self.play_again and self.someone_connected():
            self.begin_round()
        else:
            self.start_countdown()
        self.play_again = False

    def stop_round(self) -> None:
        """The last person on the ice left it: the round ends with no end card and nothing saved. Every seat empties,
        so whoever comes back taps Play"""
        for seat in self.seats:
            seat.clear()
        self.round, self.results, self.round_players, self.twist = None, None, {}, None
        # The next round gets a number of its own, as pages tell rounds apart by it
        self.round_number += 1
        self.stage, self.countdown, self.dirty = WAITING, None, True

    def expire_drops(self) -> None:
        """Seats kept past the grace period: a CPU takes over mid-round, otherwise the seat empties. A place in the
        line kept that long is given up"""
        now = self.clock()
        for number, seat in enumerate(self.seats):
            if seat.dropped_at is None or now - seat.dropped_at < GRACE_SECONDS:
                continue
            if self.stage in (STARTING, PLAYING):
                self.seat_cpu(number, seat)
            else:
                seat.clear()
            self.dirty = True
        for user_id, dropped_at in list(self.line_drops.items()):
            if now - dropped_at >= GRACE_SECONDS:
                del self.line_drops[user_id]
                if user_id in self.line:
                    self.leave_line(user_id)
                    self.dirty = True

    # ---------- Players ----------

    def seat_of(self, user_id: int) -> Seat | None:
        return next((seat for seat in self.seats if seat.human and seat.user_id == user_id), None)

    def seat_driven_by(self, conn: t.Any) -> int | None:
        """The seat of the person behind this connection. With the game open on two devices, the one they use now
        drives their penguin from here on"""
        user_id = conn.ctx.author.id
        number = next((n for n, seat in enumerate(self.seats) if seat.human and seat.user_id == user_id), None)
        if number is not None:
            self.seats[number].conn = conn
        return number

    def set_tuning(self, tuning: Tuning) -> None:
        self.tuning = tuning
        if self.round is not None:
            self.round.set_tuning(twist_tuning(tuning, self.twist_kind()))
        self.dirty = True

    # ---------- Paid extras ----------

    def twist_kind(self) -> str | None:
        return self.twist["kind"] if self.twist is not None else None

    def twist_refusal(self) -> str | None:
        """Why a party round can't be bought right now, worded for the player, or None when it can"""
        return "A party round is already coming up." if self.next_twist is not None else None

    def queue_twist(self, kind: str, name: str) -> bool:
        """Make the next round to begin a party round. False while one is already waiting"""
        if self.next_twist is not None:
            return False
        self.next_twist = {"kind": kind, "by": name, "name": TWISTS[kind]["name"], "line": TWISTS[kind]["line"]}
        self.dirty = True
        return True

    def crate_refusal(self) -> str | None:
        """Why a crate can't be dropped right now, worded for the player, or None when it can"""
        if self.stage != PLAYING or self.round.ended:
            return "Crates drop during a round."
        if self.round.crate is not None:
            return "There is already a crate on the ice."
        if not self.round.free_tiles():
            return "The ice has no room for a crate."
        return None

    def drop_crate(self, name: str) -> bool:
        return self.stage == PLAYING and self.round.drop_crate(name)

    def snowball_refusal(self, user_id: int, x: t.Any, z: t.Any) -> str | None:
        """Why this person can't throw a snowball at this spot on the ice right now, worded for them, or None when
        they can. Snowballs are for people who hold no seat"""
        if self.stage != PLAYING:
            return NO_SNOWBALLS
        if self.seat_of(user_id) is not None:
            return "Only people watching can throw snowballs."
        if not (number_ok(x, SNOWBALL_RANGE) and number_ok(z, SNOWBALL_RANGE)):
            return SNOWBALL_REFUSALS["far"]
        if self.tick_count - self.threw.get(user_id, -SNOWBALL_WAIT) < SNOWBALL_WAIT:
            return "Wait a moment before your next snowball."
        why = self.round.snowball_refusal(x, z)
        return SNOWBALL_REFUSALS[why] if why is not None else None

    def throw_snowball(self, user_id: int, x: t.Any, z: t.Any, name: str) -> bool:
        """This person's snowball leaves for a spot on the ice. False, with nothing thrown, when they can't"""
        if self.snowball_refusal(user_id, x, z) is not None:
            return False
        self.threw[user_id] = self.tick_count
        return self.round.throw_snowball(x, z, name)

    def set_looks(self, user_id: int, looks: dict) -> None:
        self.looks[user_id] = looks
        seat = self.seat_of(user_id)
        if seat is not None:
            seat.looks = dict(looks)
        self.dirty = True

    async def join(self, conn: t.Any, looks: dict) -> None:
        self.guild_id = conn.ctx.guild_id
        self.set_looks(conn.ctx.author.id, looks)
        self.line_drops.pop(conn.ctx.author.id, None)
        seat = self.seat_of(conn.ctx.author.id)
        if seat is not None:
            # Back from a drop, or the same player on a second device: this connection drives their penguin now.
            # The old connection's leave finds it no longer holds the seat, and leaves it alone
            seat.conn, seat.dropped_at = conn, None
            self.start_countdown()
        self.dirty = True
        await conn.send(self.state())

    def leave(self, conn: t.Any) -> None:
        """A page closed, whether its player backed out or the connection dropped"""
        # The same player may still have the game open on another device, which carries on for them from now on
        user_id = conn.ctx.author.id
        still_open = next(
            (other for other in self.room.connections if other is not conn and other.ctx.author.id == user_id), None
        )
        for seat in self.seats:
            if seat.conn is conn:
                seat.conn = still_open
                if still_open is None:
                    seat.dropped_at = self.clock()
        if user_id in self.line and still_open is None:
            self.line_drops[user_id] = self.clock()
        self.dirty = True
        # With someone else still on the ice, a dropped player keeps their grace period
        if self.stage in (STARTING, PLAYING) and not self.someone_connected():
            self.stop_round()

    async def message(self, conn: t.Any, data: t.Any) -> None:
        """A message from a page. Anything but the seven exact messages is ignored"""
        if not isinstance(data, dict) or len(data) != 1:
            return
        kind, value = next(iter(data.items()))
        # The messages that only say "true"
        taps = {"sit": self.sit, "stand": self.stand, "start": self.start_now, "brace": self.brace}
        if kind == "slide":
            self.slide(conn, value)
        elif kind == "splash":
            self.splash(conn, value)
        elif kind == "line" and type(value) is bool:
            self.set_line(conn, value)
        elif kind in taps and value is True:
            taps[kind](conn)

    def player_seat(self, conn: t.Any) -> int | None:
        """The seat this person plays, while a round is being played"""
        if self.stage != PLAYING:
            return None
        return self.seat_driven_by(conn)

    def slide(self, conn: t.Any, value: t.Any) -> None:
        number = self.player_seat(conn)
        if number is None or not isinstance(value, (list, tuple)) or len(value) != 3:
            return
        dx, dz, power = value
        if not (number_ok(dx, MAX_DIRECTION) and number_ok(dz, MAX_DIRECTION) and number_ok(power, MAX_POWER)):
            return
        if math.hypot(dx, dz) < 1e-9:
            return
        self.round.slide(number, dx, dz, power)

    def splash(self, conn: t.Any, angle: t.Any) -> None:
        number = self.player_seat(conn)
        if number is not None and number_ok(angle, MAX_ANGLE):
            self.round.dive(number, angle, self.tuning.seal_wait)

    def brace(self, conn: t.Any) -> None:
        number = self.player_seat(conn)
        if number is not None:
            self.round.brace(number)

    def free_spot(self) -> int | None:
        """The first empty spot, otherwise the first spot a CPU holds. While the results show, a CPU that won keeps
        its spot to the last, so the winner's penguin keeps the winner's name"""
        free = next((n for n, seat in enumerate(self.seats) if not seat.human and seat.cpu is None), None)
        if free is not None:
            return free
        winner = self.results["winner"] if self.results is not None else None
        cpus = [n for n, seat in enumerate(self.seats) if seat.cpu is not None]
        return min(cpus, key=lambda n: (n == winner, n), default=None)

    def conn_of(self, user_id: int) -> t.Any:
        return next((conn for conn in self.room.connections if conn.ctx.author.id == user_id), None)

    def name_of(self, user_id: int) -> str | None:
        """The name of a person in this window: someone with the game open, or whose seat is kept for them. None
        for anyone else"""
        conn = self.conn_of(user_id)
        if conn is not None:
            return conn.ctx.author.display_name
        seat = self.seat_of(user_id)
        return seat.name if seat is not None else None

    def seat_person(self, number: int, conn: t.Any) -> None:
        """Put the person behind this connection in a spot, with their looks. During the 3-2-1 they take over a CPU's
        penguin and play the round as if seated from its start"""
        author = conn.ctx.author
        seat = self.seats[number]
        seat.clear()
        seat.user_id, seat.conn, seat.name = author.id, conn, author.display_name
        seat.looks = dict(self.looks.get(author.id, {}))
        if self.stage == STARTING:
            self.round.cpus.discard(number)
            self.round_players[number] = author.id
        self.sat_out = [user_id for user_id in self.sat_out if user_id != author.id]
        self.start_countdown()
        self.dirty = True

    def sit(self, conn: t.Any) -> None:
        """Seat a spectator in a spot, or put them in the line when no spot can be had"""
        user_id = conn.ctx.author.id
        if self.seat_of(user_id) is not None:
            return
        # A line that exists gets the spots first, so a newcomer never jumps it
        free = self.free_spot() if self.stage in SEATING_STAGES and not self.line else None
        if free is not None:
            self.seat_person(free, conn)
            # Alone, Play starts the round at once
            if self.people_seated() == 1:
                if self.stage == WAITING:
                    self.begin_round()
                elif self.stage == RESULTS and self.someone_connected():
                    # The next update ends the results and starts the round
                    self.play_again = True
        elif user_id not in self.line:
            self.line.append(user_id)
            self.dirty = True

    def set_line(self, conn: t.Any, join: bool) -> None:
        """Join the line, or leave it. The page says which, so a second tap sent before the first is answered
        changes nothing"""
        user_id = conn.ctx.author.id
        if join and self.seat_of(user_id) is None and user_id not in self.line:
            self.line.append(user_id)
            self.dirty = True
        elif not join and user_id in self.line:
            self.leave_line(user_id)
            self.dirty = True

    def leave_line(self, user_id: int) -> None:
        self.line.remove(user_id)
        self.sat_out = [out for out in self.sat_out if out != user_id]

    def prune_line(self) -> None:
        """Only people with a connection in the window can take a spot, so anyone still away loses their place"""
        self.line = [user_id for user_id in self.line if self.conn_of(user_id) is not None]

    def take_from_line(self, number: int) -> None:
        self.seat_person(number, self.conn_of(self.line.pop(0)))

    def fill_free_spots(self) -> None:
        self.prune_line()
        while self.line:
            number = self.free_spot()
            if number is None:
                return
            self.take_from_line(number)

    def knocked_out_order(self) -> list[int]:
        """Seats of the people who played the round that just ended, first out first, never the winner"""
        winner, places = self.results["winner"], self.results["places"]
        played = [
            number
            for number, seat in enumerate(self.seats)
            if seat.human and number != winner and self.round_players.get(number) == seat.user_id
        ]
        return sorted(played, key=lambda number: (-places[number], number))

    def swap_line(self) -> None:
        """Between rounds: the line takes empty and CPU spots, then the spots of whoever went out first"""
        self.sat_out = []
        if not self.line:
            return
        self.fill_free_spots()
        swapped = []
        for number in self.knocked_out_order():
            if not self.line:
                break
            swapped.append(self.seats[number].user_id)
            self.take_from_line(number)
        for user_id in swapped:
            if self.conn_of(user_id) is not None:
                self.line.append(user_id)
                self.sat_out.append(user_id)
        self.dirty = True

    def stand(self, conn: t.Any) -> None:
        """Give up a seat between rounds, and a place in the line at any time. Opening the shop sends it"""
        number = self.seat_driven_by(conn)
        if number is not None and self.stage in OPEN_STAGES:
            self.seats[number].clear()
            self.dirty = True
        user_id = conn.ctx.author.id
        if user_id in self.line:
            self.leave_line(user_id)
            self.dirty = True

    def start_now(self, conn: t.Any) -> None:
        if self.seat_driven_by(conn) is None:
            return
        if self.stage == WAITING and self.countdown is not None:
            # The next update finishes the countdown
            self.countdown = 1
        elif self.stage == WAITING:
            # Someone alone has no countdown, so their tap starts the round
            self.begin_round()
        elif self.stage == RESULTS:
            # The next update ends the results and starts the next round
            self.play_again = True

    # ---------- What the page sees ----------

    def state(self) -> dict:
        """Everything a page needs to draw the window from scratch. Never takes the round's pending events"""
        return {
            "state": {
                "stage": self.stage,
                "countdown": None if self.countdown is None else math.ceil(self.countdown / TICK_RATE),
                "left": self.seconds_left(),
                "round": self.round_number,
                "seats": [self.seat_state(number, seat) for number, seat in enumerate(self.seats)],
                "watching": self.watching(),
                "line": [str(user_id) for user_id in self.line],
                "out": [str(user_id) for user_id in self.sat_out],
                "board": self.round.snapshot() if self.round is not None else None,
                "results": self.results,
                "twist": self.twist,
                "next_twist": self.next_twist,
                # A party round is played with its own numbers
                "rules": asdict(self.round.tuning if self.round is not None else self.tuning),
            }
        }

    def seconds_left(self) -> int | None:
        """Whole seconds left of the 3-2-1, or while the results show, until the next round's 3-2-1: the rest of the
        results, then the countdown. None while nothing counts down"""
        if self.stage == STARTING:
            return math.ceil(self.stage_left / TICK_RATE)
        if self.stage == RESULTS and not self.results_held():
            return math.ceil(self.stage_left / TICK_RATE) + COUNTDOWN_SECONDS
        return None

    def seat_state(self, number: int, seat: Seat) -> dict:
        if seat.cpu is not None:
            kind = "cpu"
        elif seat.human:
            kind = "human"
        else:
            kind = "empty"
        # Whoever sits here now was seated when this round began. Someone who sat down in a seat a player stood up
        # from during the results didn't play the round
        played = self.round is not None and seat.human and self.round_players.get(number) == seat.user_id
        return {
            "kind": kind,
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(seat.user_id) if seat.human else None,
            "name": seat.name,
            "away": seat.dropped_at is not None,
            "looks": seat.looks,
            "played": played,
        }

    def watching(self) -> int:
        players = [seat.conn for seat in self.seats if seat.conn is not None]
        return sum(1 for conn in self.room.connections if not any(conn is player for player in players))
