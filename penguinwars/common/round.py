from dataclasses import dataclass, field
from math import cos, exp, hypot, isfinite, log, radians, sin
from random import Random
from typing import NamedTuple

from .floe import ICE, Floe, Tile, js_round
from .maps import IceMap, classic_map, describe
from .tuning import Tuning

TICK_RATE = 30
DT = 1 / TICK_RATE
SEATS = 6
RADIUS = 0.47
HEAVY_MASS = 2.2
BRACE_MASS = 50
MIN_POWER = 0.08
KO_SECONDS = 3
END_PAUSE = 1.3
START_COOLDOWN = 0.4
BRACE_DAMPING = 10
HIT_PUSH = 1.9
VICTIM_BOOST = 1.12
HIT_REL = 2
BOUNCE_REL = 1.5
ALIVE, BRACING, FISH, HEAVY, SHIELD, FROZEN = 1, 2, 4, 8, 16, 32
OFF, SWIM, DIVE, LEAP = 0, 1, 2, 3
SURFACE_SECONDS = 1.4
DIVE_SECONDS = 0.6
LEAP_SECONDS = 0.42
PLAYER_SEAL_COOLDOWN = 0.8
FIRST_FISH_SECONDS = 6
FISH_LIFE = 14
# A new fish or crate lands this far from every penguin, fish, crate and walrus. A shape too tight to have such a tile
# as its round begins uses the smaller gap, one tile away. Both are out of a penguin's reach
SPACINGS = (1.4, 1.0)
FISH_REACH = RADIUS + 0.3
FISH_SINK_SECONDS = 0.8
# A crate falls for a moment before it can be opened, so everyone sees where it will land
CRATE_FALL_SECONDS = 1.2
CRATE_REACH = RADIUS + 0.35
# What a crate can hold. Each is as likely as the others
POWERS = ("shield", "frost", "feast")
SHIELD_SECONDS = 8
FROST_SECONDS = 1.5
FEAST_SLIDES = 3
# Wind: calm for a while, then a warning that shows which way it will blow, then the gust. A gust slides every living
# penguin `wind_push` across the ice in a straight line at a steady speed, on top of however it is moving
CALM, WARN, BLOW = 0, 1, 2
WIND_CALM_SECONDS = (7, 11)
WIND_WARN_SECONDS = 1.5
WIND_GUST_SECONDS = 2
# The share of a gust that still moves a braced penguin
WIND_BRACE_SHARE = 0.1
# The walrus: a round body nothing moves. It sits, rears up as a warning, then slams the ice
SIT, REAR = 1, 2
WALRUS_RADIUS = 0.55
WALRUS_TOUCH = RADIUS + WALRUS_RADIUS
WALRUS_SIT_SECONDS = (6, 9)
WALRUS_REAR_SECONDS = 1
# A slam shoves penguins this close to the walrus's middle: `walrus_push` for one touching it, and this much weaker at
# the far end of that reach
WALRUS_REACH = 1.6
WALRUS_FADE = 0.5
# A snowball is in the air this long, then nudges penguins this close to where it lands
SNOWBALL_SECONDS = 0.7
SNOWBALL_REACH = 0.9
SNOWBALL_FADE = 0.6
SNOWBALLS = 6
# A snowball's target is at most this far from the middle of the ice
SNOWBALL_RANGE = 6


def ticks(seconds: float) -> int:
    return js_round(seconds * TICK_RATE)


def stop_distance(speed: float, tuning: Tuning) -> float:
    if speed <= 0:
        return 0.0
    k, c = tuning.friction_share, tuning.friction_fixed
    return (speed - (c / k) * log(1 + (k * speed) / c)) / k


def speed_for(distance: float, tuning: Tuning) -> float:
    low, high = 0.0, tuning.slide_speed * 1.6
    for _ in range(24):
        mid = (low + high) / 2
        if stop_distance(mid, tuning) < distance:
            low = mid
        else:
            high = mid
    return low


def friction(speed: float, dt: float, tuning: Tuning) -> float:
    return max(0.0, speed - (tuning.friction_share * speed + tuning.friction_fixed) * dt)


def hundredths(value: float) -> int:
    return js_round(value * 100)


@dataclass
class Fish:
    x: float
    z: float
    life: float


@dataclass
class Crate:
    x: float
    z: float
    # Who paid for it, shown over it
    name: str
    fall: float = CRATE_FALL_SECONDS


@dataclass
class Seal:
    state: int = OFF
    t: float = 0.0
    cd: float = 0.0
    wait: float = 0.0
    tx: float = 0.0
    tz: float = 0.0


@dataclass
class Wind:
    phase: int
    # Updates left in this phase
    left: int
    # The way the gust blows, in whole degrees: penguins move toward (cos, sin) of it in (x, z)
    deg: int = 0


@dataclass
class Walrus:
    tile: int
    x: float
    z: float
    left: int
    phase: int = SIT


@dataclass
class Snowball:
    x: float
    z: float
    # Who threw it
    name: str
    left: int


class Push(NamedTuple):
    """The last thing that pushed a penguin. `by` is the seat that gets the knockout if it falls soon after, or -1 for
    a push nobody is paid for: the wind, the walrus or a watcher's snowball, whose thrower is `name`"""

    by: int
    at: float
    how: str
    name: str = ""


@dataclass
class Penguin:
    x: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vz: float = 0.0
    cd: float = START_COOLDOWN
    brace: float = 0.0
    alive: bool = True
    fish: bool = False
    heavy: bool = False
    # Seconds left of a shield bubble, which takes one hit or one seal splash and bursts
    shield: float = 0.0
    # Seconds left frozen by someone's frost. Only for the page to show: the wait itself is in `cd`
    frost: float = 0.0
    # Power slides still to come after the fish held now
    feast: int = 0
    place: int = 0
    # The last player's push on this penguin, when, and how: "hit", "bounce" (off a brace), "shield" (off a shield
    # bubble) or "seal"
    last_hit: Push | None = None
    # The last push nobody gets a knockout for: "wind", "walrus" or "snowball". A fall is put down to it only when
    # no player's push is still inside the knockout window
    nudge: Push | None = None
    seal: Seal = field(default_factory=Seal)

    @property
    def mass(self) -> float:
        return BRACE_MASS if self.brace > 0 else HEAVY_MASS if self.heavy else 1.0


class Round:
    def __init__(self, tuning: Tuning, rng: Random, fish_pace: float = 1.0, ice_map: IceMap | None = None):
        """`fish_pace` multiplies the wait for each fish. A party round passes less than 1. `ice_map` is the shape of
        the ice and the hazard on it. With none, the round is on the classic ice with no hazard"""
        self.tuning = tuning
        self.rng = rng
        self.fish_pace = fish_pace
        self.map = ice_map or classic_map()
        self.floe = Floe(tuning, rng, self.map.gone)
        self.penguins = [Penguin() for _ in range(SEATS)]
        self.knocked = [0] * SEATS
        # Per seat: the seat that knocked it out, or -1
        self.by = [-1] * SEATS
        # Per seat: fish eaten, and the knockouts made as a seal and by a bounce off a brace
        self.tally: dict[str, list[int]] = {name: [0] * SEATS for name in ("fish", "seal", "bounce")}
        self.events: list = []
        self.cpus: set[int] = set()
        self.fish: Fish | None = None
        self.fish_timer = FIRST_FISH_SECONDS * fish_pace
        self.crate: Crate | None = None
        self.snowballs: list[Snowball] = []
        self.wind: Wind | None = None
        self.walrus: Walrus | None = None
        # The thin tiles nobody has stepped on yet
        self.thin: set[int] = set(self.map.thin)
        self.elapsed = 0.0
        self.tick = 0
        self.finished = False
        self.winner: int | None = None
        self.ended = False
        self.end_timer = 0.0
        for p, (x, z) in zip(self.penguins, self.map.starts, strict=True):
            p.x, p.z = x, z
        self.set_hazard()
        self.spacing = SPACINGS[0]
        self.fit_spacing()

    def fit_spacing(self) -> None:
        """Pick the gap a new fish or crate keeps from everything: the widest that leaves it a tile on this map"""
        for gap in SPACINGS:
            self.spacing = gap
            if self.free_tiles():
                return

    def set_hazard(self) -> None:
        if self.map.hazard == "wind":
            self.wind = Wind(CALM, ticks(self.pick(*WIND_CALM_SECONDS)))
        elif self.map.hazard == "walrus":
            tile = self.floe.tiles[self.map.walrus]
            self.walrus = Walrus(tile.number, tile.x, tile.z, ticks(self.pick(*WALRUS_SIT_SECONDS)))

    def set_tuning(self, tuning: Tuning) -> None:
        self.tuning = tuning
        self.floe.tuning = tuning

    def seat_ok(self, seat: object) -> bool:
        return type(seat) is int and 0 <= seat < SEATS

    def slide(self, seat: int, dx: float, dz: float, power: float) -> bool:
        if not self.seat_ok(seat) or self.ended:
            return False
        values = (dx, dz, power)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
            return False
        length = hypot(dx, dz)
        p = self.penguins[seat]
        if length < 1e-9 or not p.alive or p.cd > 0 or p.brace > 0:
            return False
        speed = min(1.0, max(MIN_POWER, power)) * self.tuning.slide_speed
        if p.fish:
            speed *= self.tuning.fish_boost
            p.fish = p.feast > 0
            p.feast = max(0, p.feast - 1)
            p.heavy = True
        p.vx, p.vz = dx / length * speed, dz / length * speed
        p.cd = self.tuning.slide_wait
        self.events.append(["slide", seat, int(p.heavy)])
        return True

    def brace(self, seat: int) -> bool:
        if not self.seat_ok(seat) or self.ended:
            return False
        p = self.penguins[seat]
        if not p.alive or p.cd > 0:
            return False
        p.brace = self.tuning.brace_seconds
        p.cd = self.tuning.brace_wait
        self.events.append(["brace", seat])
        return True

    def collide(self, a_seat: int, b_seat: int) -> None:
        a, b = self.penguins[a_seat], self.penguins[b_seat]
        dx, dz = b.x - a.x, b.z - a.z
        d = hypot(dx, dz)
        if d >= RADIUS * 2:
            return
        if d < 1e-4:
            dx, dz, d = 1.0, 0.0, 1e-4
        nx, nz = dx / d, dz / d
        a_in = a.vx * nx + a.vz * nz
        b_in = -(b.vx * nx + b.vz * nz)
        rel = a_in + b_in
        attacker, victim = (a_seat, b_seat) if a_in >= b_in else (b_seat, a_seat)
        atk, vic = self.penguins[attacker], self.penguins[victim]
        # A shield bubble takes one real hit the way a brace would, then bursts
        shielded = vic.shield > 0 and vic.brace <= 0 and rel > BOUNCE_REL
        overlap = RADIUS * 2 - d
        ia = 1 / (BRACE_MASS if shielded and vic is a else a.mass)
        ib = 1 / (BRACE_MASS if shielded and vic is b else b.mass)
        wa = ia / (ia + ib)
        a.x -= nx * overlap * wa
        a.z -= nz * overlap * wa
        b.x += nx * overlap * (1 - wa)
        b.z += nz * overlap * (1 - wa)
        if rel <= 0:
            return
        j = HIT_PUSH * rel / (ia + ib)
        a.vx -= j * ia * nx
        a.vz -= j * ia * nz
        b.vx += j * ib * nx
        b.vz += j * ib * nz
        cx, cz = hundredths((a.x + b.x) / 2), hundredths((a.z + b.z) / 2)
        strength = hundredths(min(1.0, max(0.2, rel / self.tuning.slide_speed)))
        if shielded:
            vic.shield = 0.0
            self.events.append(["pop", victim])
        if (vic.brace > 0 or shielded) and atk.brace <= 0:
            atk.last_hit = Push(victim, self.elapsed, "shield" if shielded else "bounce")
            if rel > BOUNCE_REL:
                self.events.append(["bounce", cx, cz, strength, attacker])
            return
        if vic.brace <= 0:
            vic.vx *= VICTIM_BOOST
            vic.vz *= VICTIM_BOOST
        vic.last_hit = Push(attacker, self.elapsed, "hit")
        if rel > HIT_REL:
            self.events.append(["hit", cx, cz, strength, victim])

    def blame(self, p: Penguin, how: str, name: str = "") -> None:
        """Note a push nobody gets a knockout for. It is kept apart from the players' pushes, so a hazard or a snowball
        never takes a knockout from a player"""
        p.nudge = Push(-1, self.elapsed, how, name)

    def pushed_by(self, p: Penguin) -> Push | None:
        """What a penguin falling now was pushed in by: a player's push inside the knockout window, or else a hazard's
        or a snowball's. None when nothing pushed it lately"""
        for push in (p.last_hit, p.nudge):
            if push is not None and self.elapsed - push.at < KO_SECONDS:
                return push
        return None

    def pop(self, seat: int) -> bool:
        """Burst this penguin's shield bubble, if it has one, in place of a shove"""
        p = self.penguins[seat]
        if p.shield <= 0:
            return False
        p.shield = 0.0
        self.events.append(["pop", seat])
        return True

    def timers(self) -> None:
        for p in self.penguins:
            p.cd = max(0.0, p.cd - DT)
            p.brace = max(0.0, p.brace - DT)
            p.shield = max(0.0, p.shield - DT)
            p.frost = max(0.0, p.frost - DT)

    def physics(self) -> None:
        for p in self.penguins:
            if not p.alive:
                continue
            speed = hypot(p.vx, p.vz)
            if speed > 0:
                scale = friction(speed, DT, self.tuning) / speed
                if p.brace > 0:
                    scale *= exp(-BRACE_DAMPING * DT)
                p.vx *= scale
                p.vz *= scale
            if p.heavy and speed < 1:
                p.heavy = False
            p.x += p.vx * DT
            p.z += p.vz * DT
        for a in range(SEATS):
            for b in range(a + 1, SEATS):
                if self.penguins[a].alive and self.penguins[b].alive:
                    self.collide(a, b)
        for seat, p in enumerate(self.penguins):
            self.bump(seat, p)

    def bump(self, seat: int, p: Penguin) -> None:
        """Keep a penguin out of the walrus, and throw one that slides into it back the way a brace would"""
        walrus = self.walrus
        if walrus is None or not p.alive:
            return
        dx, dz = p.x - walrus.x, p.z - walrus.z
        d = hypot(dx, dz)
        if d >= WALRUS_TOUCH:
            return
        if d < 1e-4:
            dx, dz, d = 1.0, 0.0, 1e-4
        nx, nz = dx / d, dz / d
        p.x, p.z = walrus.x + nx * WALRUS_TOUCH, walrus.z + nz * WALRUS_TOUCH
        closing = -(p.vx * nx + p.vz * nz)
        if closing <= 0:
            return
        p.vx += HIT_PUSH * closing * nx
        p.vz += HIT_PUSH * closing * nz
        self.blame(p, "walrus")
        if closing > BOUNCE_REL:
            cx, cz = hundredths((p.x + walrus.x) / 2), hundredths((p.z + walrus.z) / 2)
            strength = hundredths(min(1.0, max(0.2, closing / self.tuning.slide_speed)))
            self.events.append(["bounce", cx, cz, strength, seat])

    def falls(self) -> None:
        for seat, p in enumerate(self.penguins):
            if p.alive and not self.floe.solid(p.x, p.z):
                self.fall(seat)

    def fall(self, seat: int) -> None:
        p = self.penguins[seat]
        p.alive, p.brace, p.fish, p.heavy = False, 0.0, False, False
        p.shield, p.frost, p.feast = 0.0, 0.0, 0
        if not p.place:
            p.place = sum(o.alive for o in self.penguins) + 1
        # The seat that gets the knockout, or -1 when no player pushed this penguin lately, and what pushed it: "" when
        # nothing did. A snowball's thrower is named after that
        event = ["fall", seat, -1, ""]
        hit = self.pushed_by(p)
        if hit is not None:
            event = ["fall", seat, hit.by, hit.how] + ([hit.name] if hit.name else [])
            if hit.by >= 0:
                self.by[seat] = hit.by
                self.knocked[hit.by] += 1
                if hit.how in self.tally:
                    self.tally[hit.how][hit.by] += 1
        p.seal.t = SURFACE_SECONDS
        self.events.append(event)

    def check_end(self) -> None:
        if self.ended:
            return
        alive = [seat for seat, p in enumerate(self.penguins) if p.alive]
        if len(alive) > 1:
            return
        self.ended = True
        self.end_timer = END_PAUSE
        if alive:
            self.winner = alive[0]
            self.penguins[alive[0]].place = 1
        self.still_hazards()

    def still_hazards(self) -> None:
        """The round is decided, so the hazard stops where it stands and says so: the wind drops, and a reared-up
        walrus sits back down with no slam"""
        wind, walrus = self.wind, self.walrus
        if wind is not None and wind.phase != CALM:
            wind.phase = CALM
            self.events.append(["calm"])
        if walrus is not None and walrus.phase == REAR:
            walrus.phase = SIT
            self.events.append(["sit"])

    def step(self) -> None:
        """One update. Once one penguin is left the round is decided: for the short pause before it finishes, the ice
        stops sinking and no move or seal can put the winner in the sea"""
        if self.finished:
            return
        self.tick += 1
        self.elapsed += DT
        if not self.ended:
            self.floe.step(DT, self.elapsed, self.events)
            self.wind_step()
            self.walrus_step()
            self.thin_step()
        self.timers()
        self.snow_step()
        self.physics()
        self.falls()
        self.check_end()
        self.fish_step()
        self.crate_step()
        self.seals_step()
        if self.ended:
            self.end_timer -= DT
            self.finished = self.end_timer <= 0

    def pick(self, low: float, high: float) -> float:
        return low + self.rng.random() * (high - low)

    def wind_step(self) -> None:
        wind = self.wind
        if wind is None:
            return
        wind.left -= 1
        if wind.phase == BLOW:
            self.blow(wind)
        if wind.left > 0:
            return
        if wind.phase == CALM:
            wind.phase, wind.left, wind.deg = WARN, ticks(WIND_WARN_SECONDS), int(self.rng.random() * 360)
            self.events.append(["wind", wind.deg])
        elif wind.phase == WARN:
            wind.phase, wind.left = BLOW, ticks(WIND_GUST_SECONDS)
            self.events.append(["gust", wind.deg])
        else:
            wind.phase, wind.left = CALM, ticks(self.pick(*WIND_CALM_SECONDS))
            self.events.append(["calm"])

    def blow(self, wind: Wind) -> None:
        """One update of a gust: every living penguin is moved the same small step, whatever else it is doing"""
        step = self.tuning.wind_push / ticks(WIND_GUST_SECONDS)
        ux, uz = cos(radians(wind.deg)), sin(radians(wind.deg))
        for p in self.penguins:
            if not p.alive:
                continue
            share = WIND_BRACE_SHARE if p.brace > 0 else 1.0
            p.x += ux * step * share
            p.z += uz * step * share
            self.blame(p, "wind")

    def wind_left(self) -> tuple[float, float]:
        """How far the gust that is warned of or blowing has yet to move a penguin that doesn't brace, as (x, z)"""
        wind = self.wind
        if wind is None or wind.phase == CALM:
            return 0.0, 0.0
        share = wind.left / ticks(WIND_GUST_SECONDS) if wind.phase == BLOW else 1.0
        reach = self.tuning.wind_push * share
        return cos(radians(wind.deg)) * reach, sin(radians(wind.deg)) * reach

    def walrus_step(self) -> None:
        walrus = self.walrus
        if walrus is None:
            return
        if self.floe.tiles[walrus.tile].state != ICE:
            self.walrus = None
            self.events.append(["walrus_gone"])
            return
        walrus.left -= 1
        if walrus.left > 0:
            return
        if walrus.phase == SIT:
            walrus.phase, walrus.left = REAR, ticks(WALRUS_REAR_SECONDS)
            self.events.append(["rear"])
        else:
            walrus.phase, walrus.left = SIT, ticks(self.pick(*WALRUS_SIT_SECONDS))
            self.slam(walrus)

    def slam(self, walrus: Walrus) -> None:
        """The walrus comes down and shoves the penguins near it straight away from it. A brace holds, and a shield
        bubble bursts in place of the shove, as with a seal's splash"""
        self.events.append(["slam"])
        for seat, p in enumerate(self.penguins):
            dx, dz = p.x - walrus.x, p.z - walrus.z
            d = hypot(dx, dz)
            if not p.alive or p.brace > 0 or d > WALRUS_REACH or d < 0.05 or self.pop(seat):
                continue
            far = max(0.0, d - WALRUS_TOUCH) / (WALRUS_REACH - WALRUS_TOUCH)
            push = self.tuning.walrus_push * (1 - WALRUS_FADE * far)
            p.vx += dx / d * push
            p.vz += dz / d * push
            self.blame(p, "walrus")

    def thin_step(self) -> None:
        """A thin tile cracks the first time a living penguin is on it, then sinks like any cracked tile"""
        if not self.thin:
            return
        self.thin = {number for number in self.thin if self.floe.tiles[number].state == ICE}
        for p in self.penguins:
            tile = self.floe.tile_at(p.x, p.z) if p.alive else None
            if tile is not None and tile.number in self.thin:
                self.thin.discard(tile.number)
                self.floe.crack(tile.number, self.events)

    def snowball_refusal(self, x: float, z: float) -> str | None:
        """Why a snowball can't be thrown at this spot now: "ended" (the round is decided), "full" (too many in the
        air) or "far" (not a spot on or near the ice). None when it can"""
        if self.ended:
            return "ended"
        if len(self.snowballs) >= SNOWBALLS:
            return "full"
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (x, z)):
            return "far"
        return "far" if hypot(x, z) > SNOWBALL_RANGE else None

    def throw_snowball(self, x: float, z: float, name: str) -> bool:
        """A watcher named `name` throws a snowball at a spot on the ice. False, with nothing thrown, when
        `snowball_refusal` gives a reason"""
        if self.snowball_refusal(x, z) is not None:
            return False
        self.snowballs.append(Snowball(float(x), float(z), name, ticks(SNOWBALL_SECONDS)))
        self.events.append(["throw", hundredths(x), hundredths(z), name])
        return True

    def snow_step(self) -> None:
        for ball in self.snowballs:
            ball.left -= 1
            if ball.left <= 0:
                self.land_snowball(ball)
        self.snowballs = [ball for ball in self.snowballs if ball.left > 0]

    def land_snowball(self, ball: Snowball) -> None:
        """A snowball lands and nudges the penguins near it straight away from it, the near ones more. A brace holds,
        and a shield bubble bursts in place of the nudge, as with a seal's splash"""
        self.events.append(["snow", hundredths(ball.x), hundredths(ball.z)])
        if self.ended:
            return
        for seat, p in enumerate(self.penguins):
            dx, dz = p.x - ball.x, p.z - ball.z
            d = hypot(dx, dz)
            if not p.alive or p.brace > 0 or d > SNOWBALL_REACH or self.pop(seat):
                continue
            push = self.tuning.snowball_push * (1 - SNOWBALL_FADE * d / SNOWBALL_REACH)
            if d < 1e-4:
                dx, dz, d = 1.0, 0.0, 1.0
            p.vx += dx / d * push
            p.vz += dz / d * push
            self.blame(p, "snowball", ball.name)

    def free_tiles(self) -> list[Tile]:
        """Whole tiles off the edge with no penguin, fish, crate or walrus near, that a living penguin can get to
        without crossing water: where something new can be put. The edge is the tiles that sink next"""
        low = min((t.depth for t in self.floe.tiles if t.state == ICE), default=0)
        taken = [(p.x, p.z) for p in self.penguins if p.alive]
        reach = self.floe.within_reach(taken)
        taken += [(thing.x, thing.z) for thing in (self.fish, self.crate, self.walrus) if thing is not None]
        return [
            t
            for t in self.floe.tiles
            if t.state == ICE
            and t.depth > low
            and t.number in reach
            and all(hypot(x - t.x, z - t.z) > self.spacing for x, z in taken)
        ]

    def spawn_fish(self) -> None:
        spots = self.free_tiles()
        if not spots:
            self.fish_timer = 2.0
            return
        tile = spots[int(self.rng.random() * len(spots))]
        self.fish = Fish(tile.x, tile.z, float(FISH_LIFE))
        self.events.append(["fish", hundredths(tile.x), hundredths(tile.z)])

    def take_fish(self, fish: Fish) -> bool:
        for seat, p in enumerate(self.penguins):
            if p.alive and not p.fish and hypot(p.x - fish.x, p.z - fish.z) < FISH_REACH:
                p.fish = True
                self.tally["fish"][seat] += 1
                self.fish = None
                self.fish_timer = self.pick(8, 12) * self.fish_pace
                self.events.append(["gulp", seat])
                return True
        return False

    def fish_step(self) -> None:
        fish = self.fish
        if fish is None:
            self.fish_timer -= DT
            if self.fish_timer <= 0:
                self.spawn_fish()
            return
        fish.life -= DT
        if not self.floe.solid(fish.x, fish.z):
            self.fish = None
            self.fish_timer = FISH_SINK_SECONDS + self.pick(6, 9) * self.fish_pace
            self.events.append(["fish_gone", "sank"])
        elif fish.life <= 0:
            self.fish = None
            self.fish_timer = self.pick(5, 8) * self.fish_pace
            self.events.append(["fish_gone", "timeout"])
        else:
            self.take_fish(fish)

    def drop_crate(self, name: str) -> bool:
        """Drop a crate on a free tile picked by chance, so whoever paid for it can't place it. False, with nothing
        dropped, when the round is decided, a crate is already out, or the ice has no room"""
        if self.ended or self.crate is not None:
            return False
        spots = self.free_tiles()
        if not spots:
            return False
        tile = spots[int(self.rng.random() * len(spots))]
        self.crate = Crate(tile.x, tile.z, name)
        self.events.append(["crate", hundredths(tile.x), hundredths(tile.z), name])
        return True

    def open_crate(self, seat: int) -> None:
        """The penguin that reached the crate gets one power, picked by chance"""
        p = self.penguins[seat]
        power = POWERS[int(self.rng.random() * len(POWERS))]
        if power == "shield":
            p.shield = float(SHIELD_SECONDS)
        elif power == "feast":
            p.fish, p.feast = True, FEAST_SLIDES - 1
        else:
            for o in self.penguins:
                if o is not p and o.alive:
                    o.cd, o.frost = max(o.cd, FROST_SECONDS), FROST_SECONDS
        self.crate = None
        self.events.append(["open", seat, power])

    def crate_step(self) -> None:
        crate = self.crate
        if crate is None:
            return
        if not self.floe.solid(crate.x, crate.z):
            self.crate = None
            self.events.append(["crate_gone"])
        elif crate.fall > 0:
            crate.fall -= DT
            if crate.fall <= 0:
                self.events.append(["land"])
        else:
            for seat, p in enumerate(self.penguins):
                if p.alive and hypot(p.x - crate.x, p.z - crate.z) < CRATE_REACH:
                    self.open_crate(seat)
                    return

    def dive(self, seat: int, angle: float, wait: float) -> bool:
        if not self.seat_ok(seat) or self.ended:
            return False
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (angle, wait)):
            return False
        p = self.penguins[seat]
        seal = p.seal
        if p.alive or seal.state != SWIM or seal.cd > 0:
            return False
        x, z, reach = self.floe.edge_point(angle)
        if reach <= 0:
            return False
        seal.state, seal.t, seal.wait, seal.tx, seal.tz = DIVE, 0.0, float(wait), x, z
        self.events.append(["dive", seat, hundredths(x), hundredths(z)])
        return True

    def splash(self, seat: int) -> None:
        seal = self.penguins[seat].seal
        self.events.append(["splash", seat, hundredths(seal.tx), hundredths(seal.tz)])
        for number, o in enumerate(self.penguins):
            if not o.alive or o.brace > 0 or self.ended:
                continue
            dx, dz = seal.tx - o.x, seal.tz - o.z
            d = hypot(dx, dz)
            if d > self.tuning.seal_reach or d < 0.05:
                continue
            if self.pop(number):
                continue
            push = 2.6 + 3.6 * (1 - d / self.tuning.seal_reach)
            o.vx += dx / d * push
            o.vz += dz / d * push
            o.last_hit = Push(seat, self.elapsed, "seal")

    def seal_step(self, seat: int) -> None:
        seal = self.penguins[seat].seal
        if seal.state == OFF:
            if seal.t > 0:
                seal.t -= DT
                if seal.t <= 0:
                    seal.state = SWIM
                    seal.cd = self.pick(3, 5) if seat in self.cpus else PLAYER_SEAL_COOLDOWN
                    self.events.append(["seal", seat])
            return
        seal.cd = max(0.0, seal.cd - DT)
        if seal.state == DIVE:
            seal.t += DT
            if min(1.0, seal.t / DIVE_SECONDS) >= 1:
                seal.state, seal.t = LEAP, 0.0
        elif seal.state == LEAP:
            seal.t += DT
            if min(1.0, seal.t / LEAP_SECONDS) >= 1:
                self.splash(seat)
                seal.state, seal.cd = SWIM, seal.wait

    def seals_step(self) -> None:
        for seat in range(SEATS):
            self.seal_step(seat)

    def rows(self) -> list[list[int]]:
        rows = []
        for p in self.penguins:
            flags = ALIVE * p.alive + BRACING * (p.brace > 0) + FISH * p.fish + HEAVY * p.heavy
            flags += SHIELD * (p.shield > 0) + FROZEN * (p.frost > 0)
            rows.append([hundredths(p.x), hundredths(p.z), flags, hundredths(p.cd)])
        return rows

    def frame(self) -> dict:
        frame: dict = {"f": self.tick, "p": self.rows()}
        if self.events:
            frame["e"] = self.events
            self.events = []
        return frame

    def snapshot(self) -> dict:
        return {
            "f": self.tick,
            "p": self.rows(),
            "t": [tile.state for tile in self.floe.tiles],
            "fish": [hundredths(self.fish.x), hundredths(self.fish.z)] if self.fish else None,
            "crate": self.crate_row(),
            "seals": [p.seal.state for p in self.penguins],
            "snow": [[hundredths(b.x), hundredths(b.z), hundredths(b.left * DT), b.name] for b in self.snowballs],
            "map": self.map_row(),
        }

    def map_row(self) -> dict:
        """The map for a page joining now: its names, and where its hazard stands. A count of time is in hundredths
        of a second"""
        row = describe(self.map)
        if self.map.hazard == "wind":
            # The way the wind blows in degrees, its phase (1 warning, 2 blowing) and the time left in it. None in a calm
            wind = self.wind
            row["wind"] = None if wind.phase == CALM else [wind.deg, wind.phase, hundredths(wind.left * DT)]
        elif self.map.hazard == "walrus":
            # Its tile, its pose (1 sitting, 2 reared up) and the time left in the pose. None once it has dived away
            walrus = self.walrus
            row["walrus"] = None if walrus is None else [walrus.tile, walrus.phase, hundredths(walrus.left * DT)]
        elif self.map.hazard == "thin":
            row["thin"] = sorted(self.thin)
        return row

    def crate_row(self) -> list | None:
        """The crate for a page joining now: where it is, whether it has landed, and whose it is"""
        crate = self.crate
        if crate is None:
            return None
        return [hundredths(crate.x), hundredths(crate.z), int(crate.fall <= 0), crate.name]

    def results(self) -> dict:
        return {
            "winner": self.winner,
            "places": [p.place for p in self.penguins],
            "knocked": list(self.knocked),
            "by": list(self.by),
            **{name: list(counts) for name, counts in self.tally.items()},
            "seconds": js_round(self.elapsed),
        }
