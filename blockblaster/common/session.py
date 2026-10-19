"""One player's live level on the bot.

The bot keeps its own copy of the level's simulation and moves it forward only as far as the page's messages say,
so a level costs nothing while nobody taps. The page sends each tap stamped with its tick; the bot replays the level
to that tick, checks the tap is allowed there, and keeps it. The level's seed and accepted taps are its whole save:
replaying them from tick 0 gives the same state on the page and on the bot.
"""

import json
import logging
import typing as t
from pathlib import Path

from .sim import core
from .sim.level import Level
from .sim.mathx import idiv

log = logging.getLogger("red.vrt.blockblaster.session")

BOARD_PATH = Path(__file__).resolve().parent.parent / "web" / "board.json"
TICKS_PER_SECOND = 60
# How far a page's clock may run ahead of the bot's: half a second, for network jitter
SLACK_TICKS = 30
# Once the page says its level ended, how far the bot runs on to find the end itself
SETTLE_TICKS = 10 * TICKS_PER_SECOND

boards: list[dict] = []


def load_board() -> dict:
    """web/board.json (the belt table, camera and layout anchors), read once and kept."""
    if not boards:
        try:
            boards.append(json.loads(BOARD_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            log.warning("Couldn't read %s", BOARD_PATH, exc_info=e)
            raise
    return boards[0]


class Session:
    """A level in play: the simulation, the taps it accepted, and when it started on the bot's clock."""

    def __init__(self, level: Level, seed: int, board: dict, started_ms: float = 0.0, unicorn: bool = False):
        self.number = level.number
        self.seed = seed
        # The player has the Super Unicorn this level (decided when the level starts, from their progress)
        self.unicorn = unicorn
        self.state = core.new_state(level, seed, board, unicorn)
        # [tick, tap] for every tap the bot accepted, in order
        self.taps: list[list[t.Any]] = []
        self.started_ms = started_ms
        # Set once the result has been sent and saved, so a level is only paid once
        self.reported = False

    def start(self) -> dict:
        """The LevelStart the page rebuilds from: replaying `taps` from tick 0 brings it to the bot's tick `t`;
        `unicorn` says the player has the Super Unicorn this level."""
        return {
            "n": self.number,
            "seed": self.seed,
            "taps": [list(entry) for entry in self.taps],
            "t": self.state.tick,
            "unicorn": self.unicorn,
        }

    def clock_limit(self, now_ms: float) -> int:
        """The latest tick a page may be at now: 60 a second since the level started, plus the slack."""
        return idiv(int((now_ms - self.started_ms) * TICKS_PER_SECOND), 1000) + SLACK_TICKS

    def advance_to(self, tick: int) -> None:
        """Run the bot's copy forward to `tick`, or to the level's end if that comes first."""
        core.run_to(self.state, tick)

    def accept(self, tap: list, tick: int) -> dict:
        """Apply a tap stamped `tick`, the bot's copy already moved there. The page's answer: {"ok", "sum"}, or
        {"refused", "level"} with the LevelStart it jumps to."""
        if tick != self.state.tick:
            return self.refuse("out of step")
        reason = core.apply_tap(self.state, tap)
        if reason is not None:
            return self.refuse(reason)
        self.taps.append([tick, tap])
        return {"ok": tick, "sum": core.checksum(self.state)}

    def refuse(self, reason: str) -> dict:
        return {"refused": reason, "level": self.start()}

    def settle(self, ticks: int) -> None:
        """Run on at most `ticks` more ticks, stopping at the level's end or once nothing moves."""
        stop = self.state.tick + ticks
        while self.state.tick < stop and self.state.over is None and not core.still(self.state):
            core.step(self.state)

    def finish(self) -> dict | None:
        """The level's result once the bot's copy has ended: {"result", "tick", "kind", "name"}, else None."""
        return core.result(self.state)
