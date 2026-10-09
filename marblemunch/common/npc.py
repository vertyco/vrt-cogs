"""The NPC brain: when a computer-controlled hippo presses and lets go"""

import random

from .rules import HOME_DEPTH, MAX_REACH, MOUTH_RADIUS, POOL_MIN, STRETCH_SPEED, Board, lane_position

# NPCs run on the bot and see every marble perfectly, so they get a person's reaction time and aim
REACTION = (0.18, 0.35)
MISS_CHANCE = 0.2
MISS_BY = (70, 110)
# How close to the middle of its lane a marble must be heading for an NPC to go for it
AIM_WIDTH = MOUTH_RADIUS * 0.6
NAMES = ("Chompy", "Gulp", "Nibbles", "Munchkin")


class Npc:
    """Plays one seat by sending the same two inputs a person sends, under the same rules"""

    def __init__(self, seat: int, rng: random.Random):
        self.seat = seat
        self.rng = rng
        # Seconds until it presses, once it has picked a marble
        self.wait: float | None = None
        # How far out from its wall it lets go
        self.target = float(HOME_DEPTH)

    def decide(self, board: Board, dt: float) -> str | None:
        """This update's input: "press", "release" or None"""
        hippo = board.hippos[self.seat]
        if hippo.open:
            return "release" if hippo.depth >= self.target else None
        if self.wait is not None:
            self.wait -= dt
            if self.wait > 0:
                return None
            self.wait = None
            return "press"
        if hippo.reach == 0 and hippo.cooldown <= 0:
            self.aim(board)
        return None

    def aim(self, board: Board) -> None:
        """Pick a marble that will be in reach when the neck gets there, and plan where to let go"""
        reaction = self.rng.uniform(*REACTION)
        for marble in board.marbles:
            side, depth = lane_position(self.seat, marble.x, marble.y)
            ahead_side, ahead_depth = lane_position(self.seat, marble.x + marble.vx, marble.y + marble.vy)
            travel = reaction + max(0.0, depth - HOME_DEPTH) / STRETCH_SPEED
            side_then = side + (ahead_side - side) * travel
            depth_then = depth + (ahead_depth - depth) * travel
            if abs(side_then) <= AIM_WIDTH and POOL_MIN <= depth_then <= HOME_DEPTH + MAX_REACH:
                self.target = depth_then
                if self.rng.random() < MISS_CHANCE:
                    self.target += self.rng.choice((-1, 1)) * self.rng.uniform(*MISS_BY)
                self.wait = reaction
                return
