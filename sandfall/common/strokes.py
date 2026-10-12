"""
Strokes as the bot sees them: arrays of whole numbers the pages apply between steps. The bot never applies them; it
only checks their shape and sizes, so a broken or giant message can't reach the other screens.
"""

from .worldfile import ELEMENT_COUNT, H, W

PAINT, LINE, BOX, FILL, HEAT, SHOVE, HAND, BOLT, SET, CLEAR, RESET = range(1, 12)
# Only a shared world's owner may change its settings, empty it or reset it
OWNER_ONLY = {SET, CLEAR, RESET}
# A path holds 1 to 64 points, two numbers each
MAX_PATH = 128

ZERO = range(0, 1)
ELEMENT = range(0, ELEMENT_COUNT)
SIZE = range(1, 41)
SHAPE = range(0, 3)
FLAGS = range(0, 4)
HUE = range(0, 256)

# Each kind's five fields after the kind, then the fewest and most coordinates it carries
LAYOUTS = {
    PAINT: ((ELEMENT, SIZE, SHAPE, FLAGS, HUE), 2, MAX_PATH),
    LINE: ((ELEMENT, SIZE, SHAPE, FLAGS, HUE), 4, 4),
    BOX: ((ELEMENT, ZERO, ZERO, FLAGS, HUE), 4, 4),
    FILL: ((ELEMENT, ZERO, ZERO, FLAGS, HUE), 2, 2),
    HEAT: (({25, -25}, SIZE, SHAPE, FLAGS, ZERO), 2, MAX_PATH),
    SHOVE: ((ZERO, SIZE, SHAPE, FLAGS, ZERO), 2, MAX_PATH),
    HAND: ((range(0, 3), ZERO, ZERO, ZERO, ZERO), 2, 2),
    BOLT: ((ZERO, ZERO, ZERO, ZERO, ZERO), 2, 2),
}

# SET's keys: 0-3 a spigot's element, 4-7 a spigot's size, 8 floor, 9 slug, 10 zombies, 11 backdrop
SETTINGS = [ELEMENT] * 4 + [range(0, 6)] * 4 + [range(0, 2), range(0, 3), {0, 10, 20, 30}, range(0, 4)]


def whole(value: object) -> bool:
    # JSON true and false arrive as bool, which Python counts as int
    return isinstance(value, int) and not isinstance(value, bool)


def coordinates_fit(points: list) -> bool:
    if len(points) % 2:
        return False
    return all(0 <= x < W for x in points[0::2]) and all(0 <= y < H for y in points[1::2])


def check_stroke(value: object) -> list | None:
    """A copy of the stroke when it is a well-formed stroke, or None"""
    if not isinstance(value, list) or not value or len(value) > 6 + MAX_PATH:
        return None
    if not all(whole(item) for item in value):
        return None
    kind = value[0]
    if kind in (CLEAR, RESET):
        return [kind] if len(value) == 1 else None
    if kind == SET:
        fits = len(value) == 3 and 0 <= value[1] < len(SETTINGS) and value[2] in SETTINGS[value[1]]
        return list(value) if fits else None
    layout = LAYOUTS.get(kind)
    if layout is None:
        return None
    fields, fewest, most = layout
    points = value[6:]
    if len(value) < 6 or not fewest <= len(points) <= most:
        return None
    if not all(item in allowed for item, allowed in zip(value[1:6], fields, strict=True)):
        return None
    return list(value) if coordinates_fit(points) else None


def steps_for(speed: int, batch: int) -> int:
    """How many steps batch number `batch` runs at speed 0 (paused) to 4 (double)"""
    even = batch % 2 == 0
    return [0, 1 if even else 0, 2 if even else 1, 3, 6][speed]
