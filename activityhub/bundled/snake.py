import typing as t
from collections import deque

from .rng import Rng

# Rules mirrored in web/snake/rules.js. A round is replayed tick by tick from its seed and turns
SIZE = 20
START = ((10, 10), (9, 10), (8, 10))
DIRECTIONS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
OPPOSITE = {"U": "D", "D": "U", "L": "R", "R": "L"}
MAX_TICKS = 200_000
# A step takes 140 ms, 3 ms less per apple eaten, down to 60 ms
SLOWEST_TICK_MS = 140
FASTEST_TICK_MS = 60


def tick_seconds(apples: int) -> float:
    """How long one step takes: the snake speeds up as it eats"""
    return max(FASTEST_TICK_MS, SLOWEST_TICK_MS - 3 * apples) / 1000


class SnakeGame:
    def __init__(self, seed: int):
        self.rng = Rng(seed)
        self.body = deque(START)
        self.cells = set(START)
        self.heading = "R"
        self.apples = 0
        self.over = False
        self.food = self.place_food()

    def place_food(self) -> tuple[int, int] | None:
        free = [(x, y) for y in range(SIZE) for x in range(SIZE) if (x, y) not in self.cells]
        return free[self.rng.pick(len(free))] if free else None

    def turn(self, heading: str) -> bool:
        """Point the snake a new way. Going the same way or straight back is not a turn"""
        if heading == self.heading or heading == OPPOSITE[self.heading]:
            return False
        self.heading = heading
        return True

    def step(self) -> None:
        dx, dy = DIRECTIONS[self.heading]
        x, y = self.body[0]
        head = (x + dx, y + dy)
        eating = head == self.food
        # The tail moves out of the way first, so chasing your own tail is allowed
        if not eating:
            self.cells.discard(self.body.pop())
        if not (0 <= head[0] < SIZE and 0 <= head[1] < SIZE) or head in self.cells:
            self.over = True
            return
        self.body.appendleft(head)
        self.cells.add(head)
        if eating:
            self.apples += 1
            self.food = self.place_food()
            # A full board is a win, and the round ends there
            self.over = self.food is None


def parse_turns(moves: t.Any) -> dict[int, str] | None:
    """Turns as {tick: heading}, or None when they aren't a list of [tick, heading] in tick order"""
    if not isinstance(moves, list) or len(moves) > MAX_TICKS:
        return None
    turns, last = {}, -1
    for move in moves:
        if not isinstance(move, list) or len(move) != 2:
            return None
        tick, heading = move
        if type(tick) is not int or tick <= last or heading not in DIRECTIONS:
            return None
        turns[tick] = heading
        last = tick
    return turns


def replay(seed: int, moves: t.Any, ticks: t.Any) -> tuple[int, float] | None:
    """
    Play a round again from its seed and turns.

    Returns the apples eaten and the least time the round can have taken, or None when the turns don't make
    a real round (a turn that isn't one, or steps after the snake already crashed).
    """
    turns = parse_turns(moves)
    if turns is None or type(ticks) is not int or not 0 <= ticks <= MAX_TICKS:
        return None
    if turns and max(turns) >= ticks:
        return None
    game = SnakeGame(seed)
    seconds = 0.0
    for tick in range(ticks):
        if game.over:
            return None
        seconds += tick_seconds(game.apples)
        heading = turns.get(tick)
        if heading is not None and not game.turn(heading):
            return None
        game.step()
    return game.apples, seconds
