import logging
import secrets
from pathlib import Path

from ..common.looks import SettingsError
from ..common.payouts import NOT_AN_ADMIN, Payouts
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
NOT_FINISHED = "That round isn't finished, or you already played another one."
ALREADY_CASHED = "That round was already cashed in."


class BundledGame:
    """
    A game that comes with the hub. It plugs into the menu the same way a game cog does.

    Every bundled game keeps each server's best scores. The page starts a round on the bot's clock, then sends
    what it needs to prove the round when it ends, and the bot works out the score itself. Where payouts are on,
    the finished round can then be cashed in once, until the player starts another round of that game. Server
    admins set the game's payouts from a settings dialog in its page.
    """

    key = ""
    name = ""
    description = ""
    # What one point is called, and what it pays until a server changes it
    unit = "point"
    rate = 1

    def __init__(self, scores: ScoreBoard, payouts: Payouts):
        self.scores = scores
        self.payouts = payouts

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
            "economy": self.economy_line,
            "actions": {
                "start": self.start,
                "finish": self.finish,
                "board": self.board,
                "cashin": self.cash_in,
                "payouts": self.payout_settings,
                "save_payouts": self.save_payouts,
            },
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
        offer = await self.payouts.offer(ctx.author, self.key, score)
        run.result = {"score": score, "best": best, "newBest": new_best, "board": board, "offer": offer}
        return run.result

    async def cash_in(self, ctx: ActivityContext, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": PRACTICE}
        opened = self.scores.find_run(ctx, self.key, data.get("run"))
        if opened is None or opened[0].result is None:
            return {"error": NOT_FINISHED}
        run = opened[0]
        if run.cashed:
            return {"error": ALREADY_CASHED}
        # Set before the wait, so a double click can't pay twice. Kept only when the cash-in paid
        run.cashed, paid = True, False
        try:
            result = await self.payouts.cash_in(ctx.author, self.key, run.result["score"])
            paid = "error" not in result
            return result
        finally:
            run.cashed = paid

    async def board(self, ctx: ActivityContext, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": NO_BOARD}
        return await self.scores.board(ctx.guild, ctx.author, self.key)

    async def payout_settings(self, ctx: ActivityContext, data: dict) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.payouts.can_change(ctx):
            return {"settings": None}
        return await self.payouts.dialog(ctx.guild, self)

    async def save_payouts(self, ctx: ActivityContext, data: dict) -> dict:
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.payouts.can_change(ctx):
            return {"error": NOT_AN_ADMIN}
        try:
            await self.payouts.save(ctx.guild, self, data.get("settings"))
        except SettingsError as e:
            log.debug("Refused a %s payout save: %s", self.key, e)
            return {"error": str(e)}
        return await self.payout_settings(ctx, {})

    async def economy_line(self, ctx: ActivityContext) -> str | None:
        """The menu card's currency line while this game pays out in the player's server"""
        settings = await self.payouts.guild_settings(ctx.guild, self.key)
        if settings is None:
            return None
        return f"Cash in up to {settings['cap']:,} {await self.payouts.bank.get_currency_name(ctx.guild)}"

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        """The round's real score, or None when what the page sent can't have happened"""
        raise NotImplementedError


class Snake(BundledGame):
    key = "snake"
    name = "Snake"
    description = "Eat apples, grow longer, and don't run into yourself"
    unit = "apple"
    rate = 25

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
    rate = 0.1

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
    rate = 0.5

    def __init__(self, scores: ScoreBoard, payouts: Payouts):
        super().__init__(scores, payouts)
        self.levels = bricks.load_levels(WEB_DIR / self.key / "levels.json")

    def score(self, run: Run, data: dict, elapsed: float) -> int | None:
        broken, cleared = data.get("bricks"), data.get("levels_cleared")
        if not bricks.run_is_plausible(self.levels, broken, cleared, elapsed):
            return None
        return bricks.run_score(broken, cleared)


def bundled_games(scores: ScoreBoard, payouts: Payouts) -> list[BundledGame]:
    games = [Snake(scores, payouts), BrickBreaker(scores, payouts), Twenty48(scores, payouts)]
    payouts.games = {game.key: game for game in games}
    return games
