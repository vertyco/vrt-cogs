"""
One Starhold run as the bot keeps it, and the checks on what a page sends.

The page plays the run. The bot only keeps the seed it handed out, the moves the page made, how far the page says it
has played, and what the page says the run scored, so it can check the score later by replaying it. Each message is
checked against the bot's own clock as it arrives: steps never go backward, and a run can't be further along than
real time allows. A run that fails either check still plays on the page, but it can't be cashed in or saved.
"""

import asyncio
import secrets
import typing as t
from dataclasses import dataclass, field

STEPS_PER_SECOND = 30
# Two seconds of slack, for a page whose run started a moment before the bot noted the time
SLACK_STEPS = 60
# A run with its page closed and nothing sent about it for this long is dropped, with any score not cashed in
HOLD_SECONDS = 30 * 60
# A long honest run sends a few hundred moves. Past this the run is refused, so a flooding page can't grow the bot's
# memory or the check's time
MAX_MOVES = 10_000
# A run that ended within its first minute of play is never checked, saved or cashed in. An honest run that ends that
# fast has scored almost nothing, and the clock check makes every checked run cost a changed page a real minute, so
# it can't keep the bot checking run after run
SHORTEST_STEPS = 60 * STEPS_PER_SECOND
# Every whole number in a message stays below this, like the rules' own numbers
LIMIT = 2**31
# How long each move kind is, step and kind included: [step, kind, ...details]. The kinds are rules.js's
MOVE_SIZES = {0: 4, 1: 3, 2: 4, 3: 3, 4: 4, 5: 2, 6: 4, 7: 4}

BACKWARD = "This run's steps went backward, so it can't be cashed in or saved."
AHEAD = "This run went faster than real time, so it can't be cashed in or saved."
TOO_MANY = "This run sent too many moves, so it can't be cashed in or saved."


@dataclass
class Run:
    seed: int
    # When the bot handed out the seed, and when the page last sent anything, on the bot's clock in seconds
    started: float
    seen: float
    moves: list[list[int]] = field(default_factory=list)
    # The latest step the page reported with "at"
    at: int = 0
    # [step, score, wave] from the page's game over: what the page says the run scored, and where it ended
    claim: list[int] | None = None
    # Why the run can't be cashed in or saved, or None
    refused: str | None = None
    # The replay of this run, started at most once
    checking: asyncio.Task | None = None
    cashed: bool = False
    # Set once the deposit has been asked for: from then on an error can't prove the run wasn't paid
    paying: bool = False
    # Set when the player's data is deleted: work still in flight for this run then writes and sends nothing
    dropped: bool = False

    def latest(self) -> int:
        """The furthest step the bot knows the page reached"""
        return max(self.at, self.moves[-1][0] if self.moves else 0)


def whole(value: t.Any) -> bool:
    # bool is a kind of int in Python, and true must not pass for 1
    return type(value) is int and 0 <= value < LIMIT


def wholes(value: t.Any) -> bool:
    return isinstance(value, list) and all(whole(item) for item in value)


def read_message(data: t.Any) -> tuple[str, t.Any] | None:
    """A page message as (name, value), or None for anything not shaped exactly right"""
    if not isinstance(data, dict) or len(data) != 1:
        return None
    name, value = next(iter(data.items()))
    if name in ("start", "cashin"):
        return (name, value) if value is True else None
    if name == "at":
        return (name, value) if whole(value) else None
    # Lists are measured before their numbers are walked, so a huge one is refused cheaply
    if name == "over":
        return (name, value) if isinstance(value, list) and len(value) == 3 and wholes(value) else None
    if name == "move":
        sized = isinstance(value, list) and len(value) in MOVE_SIZES.values()
        shaped = sized and wholes(value) and MOVE_SIZES.get(value[1]) == len(value)
        return (name, value) if shaped else None
    return None


def clock_problem(run: Run, step: int, now: float) -> str | None:
    """Why a step can't be right, or None. Pausing only leaves the steps further behind real time, which is fine"""
    if step < run.latest():
        return BACKWARD
    if step > int((now - run.started) * STEPS_PER_SECOND) + SLACK_STEPS:
        return AHEAD
    return None


def new_seed() -> int:
    """A run's dice seed, from a secure source so nobody can guess the next one and practice it"""
    return secrets.randbelow(LIMIT)
