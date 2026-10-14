"""
One player's Bloxorz run: the stage they are on, the current attempt, the run's counters and clock, and the messages
the page and the bot trade.

The counters follow the original's root frames: moves +1 when a roll starts, and a fall puts the moves back to what
they were when the stage began and adds a failed attempt (frame_53 lines 39-43). The clock is real time on the bot's
clock, counted from the moment a stage begins, through its splash, play and scatter alike (DefineSprite_6 counts every
frame past root frame 40).
"""

import typing as t

from .rules import DIRS, PIECES, Attempt
from .stages import STAGES

FLAGS = ("new", "continue", "swap", "quit")
# Rolls held while a bridge check is due. A page only starts a roll for a piece at rest, so a few is plenty
QUEUE_MAX = 3


def read_command(data: t.Any) -> tuple[str, t.Any] | None:
    """A page message as (name, value), or None for anything not shaped exactly right"""
    if not isinstance(data, dict) or len(data) != 1:
        return None
    name, value = next(iter(data.items()))
    if name in FLAGS and value is True:
        return name, value
    if name == "passcode" and isinstance(value, str) and len(value) == 6 and value.isascii() and value.isdigit():
        return name, value
    if name == "roll" and isinstance(value, dict) and set(value) == {"piece", "dir"}:
        piece, direction = value["piece"], value["dir"]
        if isinstance(piece, str) and piece in PIECES and isinstance(direction, str) and direction in DIRS:
            return name, value
        return None
    if name == "check" and isinstance(value, dict) and set(value) == {"rolling"}:
        rolling = value["rolling"]
        if isinstance(rolling, list) and len(rolling) <= len(PIECES):
            if all(isinstance(piece, str) and piece in PIECES for piece in rolling):
                return name, value
    return None


class Game:
    """One player's run. `clock` gives seconds (time.monotonic on the bot)."""

    def __init__(self, clock: t.Callable[[], float]):
        self.clock = clock
        self.stage = 1
        self.moves = 0
        self.falls = 0
        # The run's seconds when the current stage began, and when that was on the clock
        self.seconds = 0.0
        self.began = clock()
        # The run's moves when the current stage began: a fall goes back to this
        self.start_moves = 0
        self.attempt: Attempt | None = None
        self.queue: list[tuple[str, str]] = []
        # Set when an attempt ends and a new one replaces it. A roll the page sent for the old attempt can still
        # arrive (the other cube was rolling when one fell); until the new attempt takes a roll, refusals are stale
        self.restarted = False
        self.saved: dict | None = None
        self.cleared: list[tuple[int, int]] = []

    def elapsed(self) -> float:
        return self.seconds + self.clock() - self.began

    def start(self, stage: int, moves: int, falls: int, seconds: int, fresh: bool) -> list[dict]:
        """Begin `stage` with its "STAGE NN" splash. `fresh` starts a new run (Start New Game or a passcode): the
        counters begin at zero whatever is passed. Otherwise the run goes on with the counts given (Continue)."""
        if fresh:
            moves, falls, seconds = 0, 0, 0
        self.stage = stage
        self.moves = moves
        self.falls = falls
        self.seconds = float(seconds)
        self.began = self.clock()
        self.begin_stage()
        return [{"stage": self.stage_message(True, False)}]

    def begin_stage(self):
        self.start_moves = self.moves
        self.attempt = Attempt(STAGES[self.stage - 1])
        self.queue = []
        self.restarted = True
        self.saved = {"stage": self.stage, "moves": self.moves, "falls": self.falls, "seconds": int(self.seconds)}

    def stage_message(self, splash: bool, resume: bool) -> dict:
        stage = STAGES[self.stage - 1]
        snapshot = self.attempt.snapshot()
        return {
            "n": stage.number,
            "code": stage.code,
            "rows": list(stage.rows),
            "start": list(stage.start),
            "open": snapshot["open"],
            "piece": snapshot["piece"],
            "moves": self.moves,
            "falls": self.falls,
            "seconds": int(self.elapsed()),
            "start_moves": self.start_moves,
            "splash": splash,
            "resume": resume,
        }

    def resume(self) -> dict | None:
        """The stage message for a page that came back, or None when no attempt is live. A bridge check the old page
        never sent is run now, with nothing rolling, since the rebuilt page has every piece at rest."""
        if self.attempt is not None and self.attempt.awaiting_check:
            self.queue = []
            self.check(set())
        if self.attempt is None:
            return None
        return self.stage_message(False, True)

    def handle(self, name: str, value: t.Any) -> list[dict]:
        """Every page message except new, passcode and continue. The answers to send, in order."""
        if self.attempt is None:
            return []
        if name == "roll":
            if self.attempt.awaiting_check:
                if len(self.queue) < QUEUE_MAX:
                    self.queue.append((value["piece"], value["dir"]))
                return []
            return self.roll(value["piece"], value["dir"])
        if name == "check":
            return self.check(set(value["rolling"]))
        if name == "swap":
            self.attempt.swap()
        elif name == "quit":
            self.attempt = None
            self.queue = []
        return []

    def roll(self, piece: str, direction: str) -> list[dict]:
        steps = self.attempt.roll(piece, direction)
        if steps is None:
            if self.restarted:
                return []
            return [{"stage": self.stage_message(False, True)}]
        self.restarted = False
        self.moves += 1
        return [{"rolled": {"moves": self.moves, "steps": steps}}] + self.after()

    def check(self, rolling: set[str]) -> list[dict]:
        """The bridge check one frame after a closing landing, then the rolls that waited for it, in order."""
        out = [{"checked": {"steps": self.attempt.check(rolling)}}] + self.after()
        while self.queue and self.attempt is not None and not self.attempt.awaiting_check:
            piece, direction = self.queue.pop(0)
            out += self.roll(piece, direction)
        return out

    def after(self) -> list[dict]:
        """What follows a step that ended the attempt: the restart after a fall, or the next stage after a win."""
        if self.attempt.over == "fall":
            self.falls += 1
            self.moves = self.start_moves
            self.attempt = Attempt(STAGES[self.stage - 1])
            self.queue = []
            self.restarted = True
            return [{"stage": self.stage_message(False, False)}]
        if self.attempt.over != "win":
            return []
        self.cleared.append((self.stage, self.moves - self.start_moves))
        now = self.clock()
        self.seconds += now - self.began
        self.began = now
        if self.stage == len(STAGES):
            self.attempt = None
            self.queue = []
            self.saved = None
            return [{"done": {"moves": self.moves, "falls": self.falls, "seconds": int(self.seconds)}}]
        self.stage += 1
        self.begin_stage()
        return [{"stage": self.stage_message(True, False)}]
