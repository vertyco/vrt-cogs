"""Marble Munch's rules: the board, the marbles and the hippos. No Discord and no asyncio, so tests drive it directly"""

import math
import random
from dataclasses import dataclass

TICK_RATE = 30
DT = 1 / TICK_RATE
SEATS = 4

# The board is 1000 x 1000 units. Marbles roll inside the pool, which is the board less its rim
POOL_MIN = 100
POOL_MAX = 900
MARBLE_RADIUS = 23
MARBLE_COUNT = 20
MARBLE_SPEED = (150, 250)
# Marbles roll out of the middle one after another over this long, so they spread out
RELEASE_SECONDS = 2.0
ROUND_SECONDS = 120

# How far a mouth is from its own wall at home, and how much further it stretches. The middle is 500 out
HOME_DEPTH = 250
MAX_REACH = 200
STRETCH_SECONDS = 0.6
RETRACT_SECONDS = 0.4
STRETCH_SPEED = MAX_REACH / STRETCH_SECONDS
RETRACT_SPEED = MAX_REACH / RETRACT_SECONDS
# A little wider than the drawn mouth, so a snap that looked right on a laggy screen still lands
MOUTH_RADIUS = 60
SNAP_COOLDOWN = 0.3


def mouth_position(seat: int, depth: float) -> tuple[float, float]:
    """Where a mouth `depth` units out from its wall is on the board. Seats are 0 bottom, 1 left, 2 top, 3 right"""
    if seat == 0:
        return 500.0, 1000.0 - depth
    if seat == 1:
        return depth, 500.0
    if seat == 2:
        return 500.0, depth
    return 1000.0 - depth, 500.0


def lane_position(seat: int, x: float, y: float) -> tuple[float, float]:
    """A board point as (how far it is to the side of the hippo's lane, how far out it is from the hippo's wall)"""
    if seat == 0:
        return x - 500, 1000 - y
    if seat == 1:
        return y - 500, x
    if seat == 2:
        return x - 500, y
    return y - 500, 1000 - x


def bounce(position: float, speed: float) -> tuple[float, float]:
    """Reflect a position that went past a pool wall back inside, turning its speed around"""
    low, high = POOL_MIN + MARBLE_RADIUS, POOL_MAX - MARBLE_RADIUS
    if position < low:
        return 2 * low - position, abs(speed)
    if position > high:
        return 2 * high - position, -abs(speed)
    return position, speed


@dataclass
class Marble:
    id: int
    x: float
    y: float
    vx: float
    vy: float

    def move(self, dt: float) -> None:
        self.x, self.vx = bounce(self.x + self.vx * dt, self.vx)
        self.y, self.vy = bounce(self.y + self.vy * dt, self.vy)


@dataclass
class Hippo:
    seat: int
    reach: float = 0.0
    open: bool = False
    holding: bool = False
    # A press during the wait after a snap opens the mouth once the wait is over, if it is still held
    queued: bool = False
    cooldown: float = 0.0
    score: int = 0

    @property
    def depth(self) -> float:
        return HOME_DEPTH + self.reach

    def press(self) -> None:
        self.holding = True
        if self.open:
            return
        if self.cooldown <= 0:
            self.open = True
        else:
            self.queued = True

    def release(self) -> None:
        self.holding = False
        self.queued = False

    def step(self, dt: float) -> bool:
        """Move one update forward. True when the mouth snapped shut in this update"""
        if self.open:
            self.reach = min(MAX_REACH, self.reach + STRETCH_SPEED * dt)
            # Letting go snaps it, and so does full reach, so nobody can park an open mouth mid-board
            if not self.holding or self.reach >= MAX_REACH:
                self.open = False
                self.cooldown = SNAP_COOLDOWN
                return True
            return False
        self.reach = max(0.0, self.reach - RETRACT_SPEED * dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.queued and self.holding and self.cooldown <= 0:
            self.queued = False
            self.open = True
        return False


def in_reach(hippo: Hippo, marble: Marble) -> bool:
    """Whether a snap catches this marble: in the mouth, or under the neck between the pool edge and the mouth"""
    x, y = mouth_position(hippo.seat, hippo.depth)
    if math.hypot(marble.x - x, marble.y - y) <= MOUTH_RADIUS:
        return True
    # Marbles roll under the head and neck too, where no other hippo can reach, so the snap sweeps them up
    side, depth = lane_position(hippo.seat, marble.x, marble.y)
    return abs(side) <= MOUTH_RADIUS and depth <= hippo.depth


class Board:
    """One round: the marbles still in play and the four hippos"""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.hippos = [Hippo(seat) for seat in range(SEATS)]
        self.marbles: list[Marble] = []
        self.released = 0
        self.elapsed = 0.0

    @property
    def marbles_left(self) -> int:
        return MARBLE_COUNT - self.released + len(self.marbles)

    @property
    def time_left(self) -> float:
        return max(0.0, ROUND_SECONDS - self.elapsed)

    @property
    def finished(self) -> bool:
        return self.marbles_left == 0 or self.elapsed >= ROUND_SECONDS

    def step(self, dt: float = DT) -> list[tuple[int, int]]:
        """Move everything one update forward. Returns (seat, marble id) for each marble eaten"""
        self.elapsed += dt
        self.release_marbles()
        for marble in self.marbles:
            marble.move(dt)
        eaten = []
        for hippo in self.hippos:
            if hippo.step(dt):
                eaten.extend((hippo.seat, marble_id) for marble_id in self.eat(hippo))
        return eaten

    def release_marbles(self) -> None:
        due = min(MARBLE_COUNT, math.floor(self.elapsed / RELEASE_SECONDS * MARBLE_COUNT) + 1)
        while self.released < due:
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(*MARBLE_SPEED)
            self.marbles.append(Marble(self.released, 500.0, 500.0, math.cos(angle) * speed, math.sin(angle) * speed))
            self.released += 1

    def eat(self, hippo: Hippo) -> list[int]:
        caught = [marble for marble in self.marbles if in_reach(hippo, marble)]
        for marble in caught:
            self.marbles.remove(marble)
        hippo.score += len(caught)
        return [marble.id for marble in caught]

    def frame(self) -> dict:
        """The board as the page draws it: whole numbers in short lists, to keep each update small"""
        return {
            "m": [[marble.id, round(marble.x), round(marble.y)] for marble in self.marbles],
            "r": [round(hippo.reach) for hippo in self.hippos],
            "o": [int(hippo.open) for hippo in self.hippos],
            "s": [hippo.score for hippo in self.hippos],
            "left": self.marbles_left,
            "time": math.ceil(self.time_left),
        }
