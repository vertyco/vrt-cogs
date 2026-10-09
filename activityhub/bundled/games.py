import logging
import secrets
from pathlib import Path

from ..common.sessions import ActivityContext
from . import bricks, snake, twenty48
from .scores import Run, ScoreBoard

log = logging.getLogger("red.vrt.activityhub.bundled")

WEB_DIR = Path(__file__).parent / "web"
# The page's clock and the bot's clock start a moment apart, so a round may look slightly faster than it was
CLOCK_SLACK = 0.9

PRACTICE = "Scores are only saved when you play in a server."
NO_BOARD = "Leaderboards are kept per server. Open this in a server to see one."
NO_ROUND = "That round wasn't found, so it wasn't saved."
NOT_SAVED = "That round didn't add up, so it wasn't saved."


class BundledGame:
    """
    A game that comes with the hub. It plugs into the menu the same way a game cog does.

    Every bundled game keeps each server's best scores. The page starts a round on the bot's clock, then sends
    what it needs to prove the round when it ends, and the bot works out the score itself.
    """

    key = ""
    name = ""
    description = ""

    def __init__(self, scores: ScoreBoard):
        self.scores = scores

    @property
    def qualified_name(self) -> str:
        """Stands in for a cog's name in the game registry and in `[p]activityhub games`"""
        return f"ActivityHub {self.name}"

    async def activityhub_game(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "web_dir": WEB_DIR / self.key,
            "icon": "icon.svg",
            "thumbnail": "thumb.svg",
            "actions": {"start": self.start, "finish": self.finish, "board": self.board},
        }

    async def start(self, ctx: ActivityContext, data: dict) -> dict:
        seed = secrets.randbits(32)
        if ctx.guild is None:
            return {"seed": seed, "run": None}
        return {"seed": seed, "run": self.scores.open_run(ctx, self.key, seed)}

    async def finish(self, ctx: ActivityContext, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": PRACTICE}
        opened = self.scores.find_run(ctx, self.key, data.get("run"))
        if opened is None:
            return {"error": NO_ROUND}
        run, elapsed = opened
        # The page's Retry save after an answer that never arrived: the score was already saved
        if run.result is not None:
            return run.result
        score = self.score(run, data, elapsed)
        if score is None:
            self.scores.close_run(data["run"])
            log.warning("Refused a %s round from %s after %.0f seconds", self.key, ctx.author.id, elapsed)
            return {"error": NOT_SAVED}
        # A save that raises leaves the round open, so the page's Retry save can send it again
        best, new_best = await self.scores.save(ctx.author, self.key, score)
        board = await self.scores.board(ctx.guild, ctx.author, self.key)
        run.result = {"score": score, "best": best, "newBest": new_best, "board": board}
        return run.result

    async def board(self, ctx: ActivityContext, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": NO_BOARD}
        return await self.scores.board(ctx.guild, ctx.author, self.key)

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        """The round's real score, or None when what the page sent can't have happened"""
        raise NotImplementedError


class Snake(BundledGame):
    key = "snake"
    name = "Snake"
    description = "Eat apples, grow longer, and don't run into yourself"

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        ticks = data.get("ticks")
        # Even at top speed every step takes a while. This cheap check runs first, so a made-up round of a
        # million steps is refused without replaying it
        if type(ticks) is not int or elapsed < ticks * snake.FASTEST_TICK_MS / 1000 * CLOCK_SLACK:
            return None
        result = snake.replay(run.seed, data.get("moves"), ticks)
        if result is None:
            return None
        apples, seconds = result
        return apples if elapsed >= seconds * CLOCK_SLACK else None


class Twenty48(BundledGame):
    key = "2048"
    name = "2048"
    description = "Slide matching tiles together to build bigger numbers"

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        moves = data.get("moves")
        # The clock check is cheap, so it runs before the replay
        if not isinstance(moves, str) or elapsed < len(moves) * twenty48.MIN_SECONDS_PER_MOVE * CLOCK_SLACK:
            return None
        return twenty48.replay(run.seed, moves)


class BrickBreaker(BundledGame):
    key = "brickbreaker"
    name = "Brick Breaker"
    description = "Break every brick and clear as many levels as you can"

    def __init__(self, scores: ScoreBoard):
        super().__init__(scores)
        self.levels = bricks.load_levels(WEB_DIR / self.key / "levels.json")

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        broken, cleared = data.get("bricks"), data.get("levels_cleared")
        if not bricks.run_is_plausible(self.levels, broken, cleared, elapsed):
            return None
        return bricks.run_score(broken, cleared)


def bundled_games(scores: ScoreBoard) -> list[BundledGame]:
    return [Snake(scores), BrickBreaker(scores), Twenty48(scores)]
