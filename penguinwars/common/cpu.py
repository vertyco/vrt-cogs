from math import atan2, ceil, cos, hypot, sin
from random import Random

from .floe import CRACK, ICE
from .round import CALM, DIVE, DT, RADIUS, REAR, SWIM, WALRUS_REACH, WALRUS_TOUCH, Penguin, Round, speed_for, ticks

NAMES = ["Pebble", "Sleet", "Biscuit", "Captain Slick", "Gus", "Flurry"]

FIRST_THINK = (2.5, 4.0)
THINK_GAP = (2.0, 4.0)
SEAL_GAP = (4.0, 7.0)
# Water or cracked ice this close is too close, and a safer tile is looked for this far away
EDGE_FEAR = 0.9
REFUGE_SIGHT = 1.8
REFUGE_GAIN = 0.2
# A slide's path is tried this often along its length, and a slide shorter than MIN_RUN is not worth making
PATH_STEP = 0.3
MIN_RUN = 0.3
# The way round a hole or the walrus is a tile this close that is at least DETOUR_GAIN nearer the goal
DETOUR_SIGHT = 2.6
DETOUR_GAIN = 0.3
# A seal goes for penguins this close to where it would land
SEAL_EDGE_MARGIN = 1.0
# A warning of wind, or the tile underfoot cracking, makes a CPU think again this soon
NEWS_THINK = (0.2, 0.9)
# A CPU beside a reared-up walrus may brace this long before the slam
SLAM_WINDOW = 0.4
SETTLED_SPEED = 1.2
HUMAN_CHANCE = 0.25
AIM_WOBBLE = 0.22
SHORTEN_CHANCE = 0.85
SLOPPY_CHANCE = 0.06
SLOPPY_FACTOR = 1.35
MAX_POWER = 0.9
DEFEND_SIGHT = 2.6
DEFEND_CLOSING = 3
DEFEND_WINDOW = 0.35


def blocked(game: Round, x: float, z: float) -> bool:
    """Whether a CPU keeps off this spot: it is water or thin ice, or the walrus is in the way"""
    walrus = game.walrus
    if walrus is not None and hypot(x - walrus.x, z - walrus.z) < WALRUS_TOUCH:
        return True
    tile = game.floe.tile_at(x, z)
    return tile is None or tile.state not in (ICE, CRACK) or tile.number in game.thin


def rest_gap(game: Round, x: float, z: float) -> float:
    """Roughly how far from water a penguin stopped here stays. With wind warned of or blowing, that counts the
    whole way the gust will carry it"""
    gap = game.floe.safe_gap(x, z)
    lx, lz = game.wind_left()
    if lx or lz:
        gap = min(gap, game.floe.safe_gap(x + lx / 2, z + lz / 2), game.floe.safe_gap(x + lx, z + lz))
    return gap


class Cpu:
    """Plays one seat. All timers advance in act, once per update, so a round replays from its seed."""

    def __init__(self, seat: int, rng: Random):
        self.seat = seat
        self.rng = rng
        self.think = rng.uniform(*FIRST_THINK)
        self.next_defend = 0.0
        self.seal_pause = 0.0
        # Whether wind was warned of or blowing, and whether the tile underfoot was cracked, at the last update
        self.news = (False, False)

    def act(self, game: Round, humans: list[int]) -> None:
        p = game.penguins[self.seat]
        if p.alive:
            self.think = max(0.0, self.think - DT)
            self.notice(game, p)
            self.think_step(game, p, humans)
            self.defend(game, p)
        else:
            self.seal_pause = max(0.0, self.seal_pause - DT)
            self.seal(game, p)

    def notice(self, game: Round, p: Penguin) -> None:
        """A warning of wind, or the tile underfoot cracking, is news: think again soon, without waiting out the
        usual gap"""
        tile = game.floe.tile_at(p.x, p.z)
        news = (game.wind is not None and game.wind.phase != CALM, tile is not None and tile.state == CRACK)
        if (news[0] and not self.news[0]) or (news[1] and not self.news[1]):
            self.think = min(self.think, self.rng.uniform(*NEWS_THINK))
        self.news = news

    def refuge(self, game: Round, p: Penguin) -> tuple[float, float, float] | None:
        """The safest whole tile close by, as a slide to it. None when nowhere near is any safer than here"""
        best = None
        top = rest_gap(game, p.x, p.z) + REFUGE_GAIN
        for tile in game.floe.tiles:
            dx, dz = tile.x - p.x, tile.z - p.z
            if tile.state != ICE or tile.number in game.thin or not MIN_RUN < hypot(dx, dz) <= REFUGE_SIGHT:
                continue
            gap = rest_gap(game, tile.x, tile.z)
            if gap > top:
                top, best = gap, (dx, dz, hypot(dx, dz))
        return best

    def goal(self, game: Round, p: Penguin, humans: list[int]) -> tuple[float, float, float] | None:
        rng = self.rng
        if rest_gap(game, p.x, p.z) < EDGE_FEAR and rng.random() < 0.75:
            refuge = self.refuge(game, p)
            if refuge is not None:
                return refuge
        fish = game.fish
        if fish and not p.fish and game.floe.solid(fish.x, fish.z):
            fd = hypot(fish.x - p.x, fish.z - p.z)
            if fd < 4.5 and rng.random() < 0.55:
                return fish.x - p.x, fish.z - p.z, fd + 0.2
        crate = game.crate
        if crate and crate.fall <= 0 and game.floe.solid(crate.x, crate.z):
            cd = hypot(crate.x - p.x, crate.z - p.z)
            if cd < 4.5 and rng.random() < 0.55:
                return crate.x - p.x, crate.z - p.z, cd + 0.2
        others = [(s, o) for s, o in enumerate(game.penguins) if s != self.seat and o.alive]
        if not others:
            return None
        others.sort(key=lambda item: hypot(item[1].x - p.x, item[1].z - p.z))
        target = others[0][1]
        living = [h for h in humans if h != self.seat and game.penguins[h].alive]
        if living and rng.random() < HUMAN_CHANCE:
            target = game.penguins[living[int(rng.random() * len(living))]]
        dx, dz = target.x - p.x, target.z - p.z
        return dx, dz, hypot(dx, dz) + 0.5

    def think_step(self, game: Round, p: Penguin, humans: list[int]) -> None:
        if self.think > 0 or p.cd > 0 or p.brace > 0 or hypot(p.vx, p.vz) > SETTLED_SPEED:
            return
        self.think = self.rng.uniform(*THINK_GAP)
        goal = self.goal(game, p, humans)
        if goal is None:
            return
        dx, dz, dist = goal
        angle = atan2(dx, dz) + self.rng.uniform(-AIM_WOBBLE, AIM_WOBBLE)
        ux, uz = sin(angle), cos(angle)
        gx, gz = p.x + ux * dist, p.z + uz * dist
        dist, crossing = self.run(game, p, ux, uz, dist, self.rng.random() < SHORTEN_CHANCE)
        if crossing:
            ux, uz, dist = self.detour(game, p, gx, gz) or (ux, uz, dist)
        if dist < MIN_RUN:
            return
        sloppy = SLOPPY_FACTOR if self.rng.random() < SLOPPY_CHANCE else 1.0
        speed = min(game.tuning.slide_speed * MAX_POWER, speed_for(dist, game.tuning) * sloppy)
        game.slide(self.seat, ux, uz, speed / game.tuning.slide_speed)

    def run(self, game: Round, p: Penguin, ux: float, uz: float, dist: float, careful: bool) -> tuple[float, bool]:
        """How far to slide this way, and whether something lies across the path with ice beyond it. A slide never
        crosses a hole or the walrus: it stops short. Sliding on past the last of the ice is the mistake only a
        careless CPU makes"""
        marks = [min(dist, PATH_STEP * n) for n in range(1, ceil(dist / PATH_STEP) + 1)]
        wet = [blocked(game, p.x + ux * mark, p.z + uz * mark) for mark in marks]
        if True not in wet:
            return dist, False
        first = wet.index(True)
        crossing = False in wet[first:]
        if crossing or careful:
            return (marks[first - 1] if first else 0.0), crossing
        return dist, False

    def detour(self, game: Round, p: Penguin, gx: float, gz: float) -> tuple[float, float, float] | None:
        """The way round a hole or the walrus: a slide to the whole tile close by that is nearest the goal, with
        nothing in the way. None when no tile is any nearer the goal than here"""
        best = None
        least = hypot(gx - p.x, gz - p.z) - DETOUR_GAIN
        for tile in game.floe.tiles:
            dx, dz = tile.x - p.x, tile.z - p.z
            d = hypot(dx, dz)
            left = hypot(gx - tile.x, gz - tile.z)
            if tile.state != ICE or not MIN_RUN < d <= DETOUR_SIGHT or left >= least:
                continue
            if self.run(game, p, dx / d, dz / d, d, True) == (d, False):
                best, least = (dx / d, dz / d, d), left
        return best

    def defend(self, game: Round, p: Penguin) -> None:
        if p.cd > 0 or p.brace > 0 or game.elapsed < self.next_defend:
            return
        for seat, o in enumerate(game.penguins):
            if seat == self.seat or not o.alive:
                continue
            dx, dz = p.x - o.x, p.z - o.z
            d = hypot(dx, dz)
            if d > DEFEND_SIGHT or d < 0.01:
                continue
            closing = (o.vx * dx + o.vz * dz) / d
            if closing > DEFEND_CLOSING and (d - RADIUS * 2) / closing < DEFEND_WINDOW:
                self.next_defend = game.elapsed + 0.6
                if self.rng.random() < 0.4:
                    game.brace(self.seat)
                return
        for o in game.penguins:
            seal = o.seal
            if seal.state == DIVE and hypot(seal.tx - p.x, seal.tz - p.z) < game.tuning.seal_reach:
                self.next_defend = game.elapsed + 0.8
                if self.rng.random() < 0.35:
                    game.brace(self.seat)
                return
        self.mind_walrus(game, p)

    def mind_walrus(self, game: Round, p: Penguin) -> None:
        """Beside a reared-up walrus that is about to slam, a CPU braces about half the time"""
        walrus = game.walrus
        if walrus is None or walrus.phase != REAR or walrus.left > ticks(SLAM_WINDOW):
            return
        if hypot(walrus.x - p.x, walrus.z - p.z) < WALRUS_REACH:
            self.next_defend = game.elapsed + 0.8
            if self.rng.random() < 0.5:
                game.brace(self.seat)

    def seal(self, game: Round, p: Penguin) -> None:
        if p.seal.state != SWIM or p.seal.cd > 0 or self.seal_pause > 0:
            return
        near = []
        for o in game.penguins:
            angle = atan2(o.z, o.x)
            x, z, _ = game.floe.edge_point(angle)
            if o.alive and hypot(x - o.x, z - o.z) < SEAL_EDGE_MARGIN:
                near.append(angle)
        self.seal_pause = self.rng.uniform(*SEAL_GAP)
        if near:
            game.dive(self.seat, near[int(self.rng.random() * len(near))], self.seal_pause)
