from collections.abc import Collection
from dataclasses import dataclass
from math import cos, floor, hypot, sin, sqrt
from random import Random

from .tuning import Tuning

S = 0.62
RINGS = 4
ICE, CRACK, SINK, GONE = 0, 1, 2, 3
CRACK_SECONDS = 1.3
SINK_SECONDS = 1.0
FIRST_CRACK_SECONDS = 3
SQ3 = sqrt(3)
# From a tile's middle to the middle of each of its sides
INRADIUS = S * SQ3 / 2
# The six tiles around a tile, as steps in (q, r)
NEIGHBORS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
# How far apart a seal's aim tries the ice, and how far out it looks
EDGE_STEP = 0.12
EDGE_LIMIT = 9


def js_round(value: float) -> int:
    return floor(value + 0.5)


def ring_of(q: int, r: int) -> int:
    return max(abs(q), abs(r), abs(q + r))


def center(q: int, r: int) -> tuple[float, float]:
    return S * SQ3 * (q + r / 2), S * 1.5 * r


def cells(low: int, high: int) -> list[tuple[int, int]]:
    """Every (q, r) from ring `low` to ring `high`, q first and then r: the order the wire's tile numbers count in"""
    span = range(-high, high + 1)
    return [(q, r) for q in span for r in span if low <= ring_of(q, r) <= high]


def edge_marks() -> list[float]:
    """The distances a seal's aim tries, counted up one step at a time the way the page counts them"""
    marks = [0.0]
    while marks[-1] < EDGE_LIMIT:
        marks.append(marks[-1] + EDGE_STEP)
    return marks


CELLS = cells(0, RINGS)
# The middles of the water tiles that ring the whole grid
RIM = [center(q, r) for q, r in cells(RINGS + 1, RINGS + 1)]
EDGE_MARKS = edge_marks()


def depths(gone: Collection[int]) -> list[int]:
    """How many tiles each tile is from the nearest open water when the round begins: 1 on an edge, more further in,
    and 0 for a tile in `gone`. The full hexagon gives its outer ring 1 and its middle tile 5"""
    ice = {cell for number, cell in enumerate(CELLS) if number not in gone}
    found: dict[tuple[int, int], int] = {}
    level = 1
    layer = [(q, r) for q, r in ice if any((q + dq, r + dr) not in ice for dq, dr in NEIGHBORS)]
    while layer:
        found.update((cell, level) for cell in layer)
        level += 1
        layer = [
            (q, r)
            for q, r in ice
            if (q, r) not in found and any(found.get((q + dq, r + dr)) == level - 1 for dq, dr in NEIGHBORS)
        ]
    return [found.get(cell, 0) for cell in CELLS]


def pieces(ice: Collection[tuple[int, int]]) -> int:
    """How many separate pieces these tiles make. Tiles that share a side are one piece"""
    left = set(ice)
    count = 0
    while left:
        count += 1
        front = [left.pop()]
        while front:
            q, r = front.pop()
            for dq, dr in NEIGHBORS:
                if (q + dq, r + dr) in left:
                    left.remove((q + dq, r + dr))
                    front.append((q + dq, r + dr))
    return count


@dataclass
class Tile:
    q: int
    r: int
    ring: int
    x: float
    z: float
    state: int = ICE
    t: float = 0.0
    # Tiles from the nearest water when the round began. The ice sinks in this order, lowest first
    depth: int = 1
    # Its number on the wire
    number: int = 0


class Floe:
    def __init__(self, tuning: Tuning, rng: Random, gone: Collection[int] = ()):
        """`gone` holds the numbers of the tiles that are open water from the start, which gives the ice its shape"""
        self.tuning = tuning
        self.rng = rng
        depth = depths(gone)
        self.tiles: list[Tile] = []
        for number, (q, r) in enumerate(CELLS):
            x, z = center(q, r)
            state = GONE if number in gone else ICE
            self.tiles.append(Tile(q, r, ring_of(q, r), x, z, state, 0.0, depth[number], number))
        self.by_axial = {(t.q, t.r): t for t in self.tiles}
        self.crack_timer = float(FIRST_CRACK_SECONDS)

    def tile_at(self, x: float, z: float) -> Tile | None:
        q = (SQ3 / 3 * x - z / 3) / S
        r = (2 / 3 * z) / S
        s = -q - r
        rq, rr, rs = js_round(q), js_round(r), js_round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds:
            rq = -rr - rs
        elif dr > ds:
            rr = -rq - rs
        return self.by_axial.get((rq, rr))

    def solid(self, x: float, z: float) -> bool:
        tile = self.tile_at(x, z)
        return tile is not None and tile.state in (ICE, CRACK)

    def edge_point(self, angle: float) -> tuple[float, float, float]:
        """Where a seal coming in at `angle` lands: just past the outermost ice that way, found from the outside in, so
        a hole in the middle never hides the far side. Gives (x, z, how far the ice reaches), with 0 for no ice at all"""
        ux, uz = cos(angle), sin(angle)
        last = len(EDGE_MARKS) - 2
        while last >= 0 and not self.solid(ux * EDGE_MARKS[last], uz * EDGE_MARKS[last]):
            last -= 1
        r = EDGE_MARKS[last + 1]
        return ux * (r + 0.35), uz * (r + 0.35), r

    def safe_gap(self, x: float, z: float) -> float:
        """Roughly how far a point is from the nearest water or cracked tile. Zero or less on one"""
        near = min(hypot(x - rx, z - rz) for rx, rz in RIM)
        for tile in self.tiles:
            if tile.state != ICE:
                near = min(near, hypot(x - tile.x, z - tile.z))
        return near - INRADIUS

    def gap(self, elapsed: float) -> float:
        return max(0.6, 1.45 - elapsed * 0.012) / self.tuning.ice_speed

    def crack(self, index: int, events: list) -> None:
        self.tiles[index].state = CRACK
        self.tiles[index].t = 0.0
        events.append(["crack", index])

    def next_crack(self, events: list) -> None:
        """Crack one whole tile picked by chance from those nearest the water the round began with. A tile whose loss
        would break the whole ice into more pieces waits its turn, so the sinking never leaves penguins on pieces
        with no way across"""
        whole = [tile for tile in self.tiles if tile.state == ICE]
        cells = {(tile.q, tile.r) for tile in whole}
        count = pieces(cells)
        for depth in sorted({tile.depth for tile in whole}):
            best = [t.number for t in whole if t.depth == depth and pieces(cells - {(t.q, t.r)}) <= count]
            if best:
                self.crack(best[int(self.rng.random() * len(best))], events)
                return

    def within_reach(self, spots: Collection[tuple[float, float]]) -> set[int]:
        """The numbers of the tiles a penguin standing on any of these spots can get to without crossing water"""
        front = [tile for x, z in spots if (tile := self.tile_at(x, z)) is not None and tile.state in (ICE, CRACK)]
        found = {tile.number for tile in front}
        while front:
            tile = front.pop()
            for dq, dr in NEIGHBORS:
                near = self.by_axial.get((tile.q + dq, tile.r + dr))
                if near is not None and near.state in (ICE, CRACK) and near.number not in found:
                    found.add(near.number)
                    front.append(near)
        return found

    def step(self, dt: float, elapsed: float, events: list) -> None:
        self.crack_timer -= dt
        if self.crack_timer <= 0:
            self.next_crack(events)
            self.crack_timer = self.gap(elapsed)
        for index, tile in enumerate(self.tiles):
            if tile.state == CRACK:
                tile.t += dt
                if tile.t >= CRACK_SECONDS:
                    tile.state = SINK
                    tile.t = 0.0
                    events.append(["sink", index])
            elif tile.state == SINK:
                tile.t += dt
                if tile.t >= SINK_SECONDS:
                    tile.state = GONE
                    events.append(["gone", index])
