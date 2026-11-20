from dataclasses import dataclass
from math import atan2, cos, hypot, pi, sin
from random import Random

from .floe import CELLS, center, depths, pieces, ring_of

# One start spot for each seat
SPOTS = 6
START_RING = 2.7
# What every shape must pass, or the round is played on the classic ice
MIN_TILES = 34
MIN_SPOT_GAP = 1.4
MIN_SPOT_DEPTH = 2
SHAPE_TRIES = 12
# A round has no hazard this often. The rest of the time each hazard is as likely as the others
CALM_CHANCE = 0.4
THIN_TILES = (8, 12)
# No thin tile this close to a start spot. No start spot this close to the walrus, which keeps every penguin out of
# its first slam
THIN_CLEAR = 0.7
WALRUS_CLEAR = 1.7

# Each shape is the full hexagon with tiles taken out. `cut` says which, for one way round: the generator turns it in
# 60 degree steps and may mirror it. `holes` punches round holes at spots picked by chance: (fewest, most, how many
# tiles out from its middle each hole reaches, how far from the middle of the ice a hole may sit, how many tiles apart
# two holes stay). `line` tells players what the shape is
SHAPES: dict[str, dict] = {
    "classic": {"name": "Classic", "line": "The whole floe"},
    "donut": {"name": "Donut", "line": "A big hole in the middle", "holes": (1, 1, 1, 1, 9)},
    "islands": {
        "name": "Twin Islands",
        "line": "Two islands joined by a bridge",
        "cut": lambda q, r: abs(2 * q + r) <= 1 and abs(r) > 1,
    },
    "crescent": {
        "name": "Crescent",
        "line": "A bite is missing from one side",
        "cut": lambda q, r: ring_of(q - 3, r) <= 2,
    },
    "hourglass": {
        "name": "Hourglass",
        "line": "Wide ends and a narrow middle",
        "cut": lambda q, r: abs(2 * q + r) > 2 + 2 * abs(r),
    },
    "holes": {"name": "Swiss Cheese", "line": "Watch out for the holes", "holes": (3, 5, 0, 3, 2)},
}
# Each hazard warns before it acts. `line` tells players what to expect
HAZARDS: dict[str, dict] = {
    "wind": {"name": "Windy", "line": "Gusts push everyone across the ice. Brace to hold on"},
    "walrus": {"name": "Walrus", "line": "The walrus slams the ice. Back off or brace when it rears up"},
    "thin": {"name": "Thin ice", "line": "The marked tiles crack as soon as a penguin touches them"},
}


@dataclass(frozen=True)
class IceMap:
    """The ice one round is played on. `gone`, `thin` and `walrus` are tile numbers"""

    shape: str
    # The tiles that are open water from the start
    gone: tuple[int, ...]
    # Where each seat's penguin starts
    starts: tuple[tuple[float, float], ...]
    hazard: str = ""
    thin: tuple[int, ...] = ()
    walrus: int = -1


def classic_starts() -> tuple[tuple[float, float], ...]:
    angles = [pi / 2 + seat * pi * 2 / SPOTS for seat in range(SPOTS)]
    return tuple((cos(angle) * START_RING, sin(angle) * START_RING) for angle in angles)


def classic_map() -> IceMap:
    return IceMap("classic", (), classic_starts())


def turned(q: int, r: int, turns: int, mirror: bool) -> tuple[int, int]:
    """A tile's place after a mirror and some 60 degree turns"""
    if mirror:
        q = -q - r
    for _ in range(turns):
        q, r = -r, q + r
    return q, r


def punched(holes: tuple[int, int, int, int, int], rng: Random) -> set[int]:
    """The tiles a recipe's round holes take out"""
    fewest, most, size, within, apart = holes
    count = fewest + int(rng.random() * (most - fewest + 1))
    middles: list[tuple[int, int]] = []
    for _ in range(count):
        free = [
            (q, r)
            for q, r in CELLS
            if ring_of(q, r) <= within and all(ring_of(q - mq, r - mr) >= apart for mq, mr in middles)
        ]
        if not free:
            break
        middles.append(free[int(rng.random() * len(free))])
    return {n for n, (q, r) in enumerate(CELLS) if any(ring_of(q - mq, r - mr) <= size for mq, mr in middles)}


def cut_tiles(shape: str, rng: Random) -> set[int]:
    """The tiles this shape takes out of the full hexagon, for one roll of the dice"""
    recipe = SHAPES[shape]
    gone: set[int] = set()
    if "cut" in recipe:
        turns, mirror = int(rng.random() * 6), rng.random() < 0.5
        gone = {n for n, (q, r) in enumerate(CELLS) if recipe["cut"](*turned(q, r, turns, mirror))}
    if "holes" in recipe:
        gone |= punched(recipe["holes"], rng)
    return gone


def in_one_piece(gone: set[int]) -> bool:
    return pieces([cell for number, cell in enumerate(CELLS) if number not in gone]) <= 1


def smallest_gap(spots: list[tuple[float, float]]) -> float:
    return min(hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(spots) for b in spots[:i])


def spread_spots(gone: set[int], walrus: int) -> list[tuple[float, float]]:
    """Six tile middles away from the edge and from the walrus's tile, spread out: after a first pick, each next one
    is the spot furthest from all those picked, and the first pick that leaves the widest smallest gap wins. In seat
    order, going round the ice from the top like the classic spots. Empty when the ice has too few such tiles"""
    depth = depths(gone)
    spots = [center(*CELLS[n]) for n in range(len(CELLS)) if depth[n] >= MIN_SPOT_DEPTH]
    if walrus >= 0:
        wx, wz = center(*CELLS[walrus])
        spots = [(x, z) for x, z in spots if hypot(x - wx, z - wz) >= WALRUS_CLEAR]
    if len(spots) < SPOTS:
        return []
    best: list[tuple[float, float]] = []
    for first in spots:
        picked = [first]
        while len(picked) < SPOTS:
            picked.append(max(spots, key=lambda spot: min(hypot(spot[0] - x, spot[1] - z) for x, z in picked)))
        if not best or smallest_gap(picked) > smallest_gap(best):
            best = picked
    mx, mz = sum(x for x, _ in best) / SPOTS, sum(z for _, z in best) / SPOTS
    return sorted(best, key=lambda spot: (atan2(spot[1] - mz, spot[0] - mx) - pi / 2) % (pi * 2))


def start_spots(gone: set[int], walrus: int) -> tuple[tuple[float, float], ...] | None:
    """Where the six penguins start on this shape, with the walrus on this tile or -1 for none. None for a shape that
    fails a check"""
    if not gone:
        return classic_starts()
    if len(CELLS) - len(gone) < MIN_TILES or not in_one_piece(gone):
        return None
    spots = spread_spots(gone, walrus)
    if not spots or smallest_gap(spots) < MIN_SPOT_GAP:
        return None
    return tuple(spots)


def clear_tiles(gone: set[int], starts: tuple[tuple[float, float], ...], clear: float) -> list[int]:
    """The ice tiles whose middles are at least `clear` from every start spot"""
    tiles = []
    for number, cell in enumerate(CELLS):
        x, z = center(*cell)
        if number not in gone and all(hypot(x - sx, z - sz) >= clear for sx, sz in starts):
            tiles.append(number)
    return tiles


def thin_tiles(gone: set[int], starts: tuple[tuple[float, float], ...], rng: Random) -> tuple[int, ...]:
    free = clear_tiles(gone, starts, THIN_CLEAR)
    low, high = THIN_TILES
    count = min(len(free), low + int(rng.random() * (high - low + 1)))
    picked = []
    for _ in range(count):
        picked.append(free.pop(int(rng.random() * len(free))))
    return tuple(sorted(picked))


def walrus_tile(gone: set[int], rng: Random) -> int:
    """A tile for the walrus, picked by chance from those furthest from the water"""
    depth = depths(gone)
    best = [number for number in range(len(CELLS)) if depth[number] == max(depth)]
    return best[int(rng.random() * len(best))]


def make_shape(shape: str, walrus: bool, rng: Random) -> tuple[str, set[int], tuple[tuple[float, float], ...], int]:
    """One shape by name, as (shape, tiles gone, start spots, the walrus's tile or -1 with no walrus). A roll that
    fails its checks is rolled again a few times, and after that the shape comes out classic"""
    for _ in range(SHAPE_TRIES):
        gone = cut_tiles(shape, rng)
        tile = walrus_tile(gone, rng) if walrus else -1
        starts = start_spots(gone, tile)
        if starts is not None:
            return shape, gone, starts, tile
    return "classic", set(), classic_starts(), walrus_tile(set(), rng) if walrus else -1


def make_map(shape: str, hazard: str, rng: Random) -> IceMap:
    """The map with this shape and hazard by name, with "" for no hazard"""
    if hazard and hazard not in HAZARDS:
        raise KeyError(hazard)
    shape, gone, starts, walrus = make_shape(shape, hazard == "walrus", rng)
    thin = thin_tiles(gone, starts, rng) if hazard == "thin" else ()
    return IceMap(shape, tuple(sorted(gone)), starts, hazard, thin, walrus)


def pick_map(rng: Random) -> IceMap:
    """A map picked by chance: every shape as likely as the others, and a hazard on most"""
    names = list(SHAPES)
    shape = names[int(rng.random() * len(names))]
    hazard = ""
    if rng.random() >= CALM_CHANCE:
        kinds = list(HAZARDS)
        hazard = kinds[int(rng.random() * len(kinds))]
    return make_map(shape, hazard, rng)


def describe(ice_map: IceMap) -> dict:
    """What the page shows about a map: its shape and hazard by name, and one line on what to expect"""
    shape, hazard = SHAPES[ice_map.shape], HAZARDS.get(ice_map.hazard)
    return {
        "shape": ice_map.shape,
        "name": shape["name"],
        "hazard": ice_map.hazard,
        "hazard_name": hazard["name"] if hazard else "",
        "line": hazard["line"] if hazard else shape["line"],
    }
