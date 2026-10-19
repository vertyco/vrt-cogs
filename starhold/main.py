import asyncio
import logging
import time
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.check import CHECK_FAILED, Checker, requirement_folder
from .common.payouts import DEFAULTS, NONE_LEFT, NOTHING_EARNED, PAYOUTS_OFF, Payouts, SettingsError
from .common.runs import (
    HOLD_SECONDS,
    MAX_MOVES,
    SHORTEST_STEPS,
    TOO_MANY,
    Run,
    clock_problem,
    new_seed,
    read_message,
)
from .common.scores import MEMBER_DEFAULTS, add_score, rank

log = logging.getLogger("red.vrt.starhold")

KEY = "starhold"
ELSEWHERE = "Starhold was opened somewhere else."
NOTHING_TO_CASH = "Nothing to cash in. Finish a run first."
CASH_FAILED = "Something went wrong while cashing in this run, so it can't be cashed in again."
CASH_RETRY = "Something went wrong while cashing in. Try again in a moment."
NOT_AN_ADMIN = "Only server admins can change payouts."
TAKEN_OVER = 4100

Key = tuple[int, int]


def player_key(ctx: t.Any) -> Key:
    """One run per player per server, and one for each player's DMs"""
    return ctx.guild_id or 0, ctx.author.id


def in_server(author: t.Any) -> bool:
    return author is not None and getattr(author, "guild", None) is not None


class Starhold(commands.Cog):
    """
    Hold a moon base against endless waves of scrap-built mechs, for ActivityHub.

    A tower defense game for phones first. Each player plays their own run on their own device; the bot checks a
    score by replaying the run's moves before it pays credits or enters the high score table.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101501, force_registration=True)
        self.config.register_global(payouts={}, tally={})
        self.config.register_guild(payouts={}, tally={})
        self.config.register_member(**MEMBER_DEFAULTS, cashed={})
        self.config.register_user(cashed={})
        self.payouts = Payouts(self.config)
        self.checker = Checker()
        # Seconds, on a clock that never jumps
        self.clock: t.Callable[[], float] = time.monotonic
        # Runs live in memory only: a restart loses them, and the page can finish a run but not cash it in
        self.runs: dict[Key, Run] = {}
        # Each player's newest page. A newer one takes the run over
        self.conns: dict[Key, t.Any] = {}
        # The player behind each run, for a game over that finishes while they are away
        self.authors: dict[Key, t.Any] = {}
        # Game overs being finished, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # The runs each player has a cash-in working on, whatever has become of the run since. A list, as Run
        # instances can't be hashed
        self.cashing: dict[int, list[Run]] = {}
        # Every replay in flight, including those of runs since replaced, so unloading can stop them all
        self.checks: set[asyncio.Task] = set()
        # The player each game over or replay task works for, so deleting their data can stop it first
        self.owners: dict[asyncio.Task, int] = {}
        # Held while a score is saved or a player's data is deleted, so a save never lands after the deletion
        self.writes = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Runs go first and without waiting, so a cash-in or save that hasn't started yet finds nothing to write for
        for run in self.cashing.get(user_id, []):
            run.dropped = True
        for key in [key for key in {*self.runs, *self.authors} if key[1] == user_id]:
            run = self.runs.pop(key, None)
            if run is not None:
                run.dropped = True
            self.authors.pop(key, None)
        tasks = [task for task, owner in self.owners.items() if owner == user_id]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # The payout lock too, so a cash-in already paying finishes its counts before they are cleared
        async with self.writes, self.payouts.lock:
            await self.config.user_from_id(user_id).clear()
            for guild_id, members in (await self.config.all_members()).items():
                if user_id in members:
                    await self.config.member_from_ids(guild_id, user_id).clear()
            for guild_id in await self.config.all_guilds():
                await self.forget_paid(self.config.guild_from_id(guild_id).tally, user_id)
            await self.forget_paid(self.config.tally, user_id)

    async def forget_paid(self, value: t.Any, user_id: int) -> None:
        tally = await value()
        if user_id in tally.get("players", []):
            tally["players"].remove(user_id)
            await value.set(tally)

    async def cog_load(self):
        if requirement_folder() is None:
            log.error("Starhold can't check scores, so nothing can be cashed in or saved: install mini-racer")

    async def cog_unload(self):
        tasks = [*self.saving, *self.checks]
        for task in tasks:
            task.cancel()
        # Waited for, so nothing of the cog is still running once it is gone
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.checker.close()

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Starhold",
            "description": "Hold a moon base against a horde of scrap mechs",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "economy": self.economy_line,
            "actions": {"scores": self.scores, "payouts": self.payout_settings, "save_payouts": self.save_payouts},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.8.0",
        }

    async def economy_line(self, ctx: t.Any) -> str | None:
        """The ActivityHub menu card's currency line while payouts are on in the player's server"""
        settings = await self.payouts.settings(ctx.guild)
        if not settings["on"]:
            return None
        return f"Cash in up to {settings['cap']:,} {await self.payouts.bank.get_currency_name(ctx.guild)}"

    # ---------- Connections ----------

    async def join(self, ctx, conn) -> None:
        key = player_key(ctx)
        self.sweep()
        old = self.conns.get(key)
        self.conns[key] = conn
        self.authors[key] = ctx.author
        if old is not None and old is not conn:
            await old.send({"elsewhere": ELSEWHERE})
            await old.close(TAKEN_OVER)
        run = self.runs.get(key)
        if run is None:
            await conn.send({"hello": {"run": None, "result": None}})
            return
        # Coming back counts as being seen, so the run waits another 30 minutes from here
        run.seen = self.clock()
        if run.claim is None:
            # A copy, so moves arriving later can't change a message still waiting to go out
            opened = {"seed": run.seed, "moves": list(run.moves), "at": run.latest()}
            await conn.send({"hello": {"run": opened, "result": None}})
            return
        # A new best not checked yet (the bot couldn't check when the run ended) is checked now
        await conn.send({"hello": {"run": None, "result": await self.result_for(key, run, check_best=True)}})

    async def leave(self, ctx, conn) -> None:
        key = player_key(ctx)
        # A page that was taken over leaves after its replacement joined. The run itself waits for its player
        if self.conns.get(key) is conn:
            del self.conns[key]
            run = self.runs.get(key)
            if run is not None:
                # The 30 minutes the run is held start now, however long the page sat paused
                run.seen = self.clock()

    def sweep(self) -> None:
        """
        Drops runs whose page is closed and that nothing was sent about for 30 minutes, with any score not cashed
        in. A player who paused with the page still open keeps their run. Players left with neither a run nor a page
        are forgotten too
        """
        now = self.clock()
        stale = [key for key, run in self.runs.items() if key not in self.conns and now - run.seen >= HOLD_SECONDS]
        for key in stale:
            del self.runs[key]
        for key in [key for key in self.authors if key not in self.runs and key not in self.conns]:
            del self.authors[key]

    async def message(self, ctx, conn, data) -> None:
        key = player_key(ctx)
        command = read_message(data)
        if command is None or self.conns.get(key) is not conn:
            return
        try:
            await self.handle(key, conn, *command)
        except Exception as e:
            log.error("A Starhold message failed for user %s", ctx.author.id, exc_info=e)

    async def handle(self, key: Key, conn: t.Any, name: str, value: t.Any) -> None:
        if name == "start":
            await self.start(key, conn)
        elif name == "cashin":
            await self.cash_in(key, conn)
        else:
            run = self.runs.get(key)
            # Moves, progress and game over only count for an open run that isn't over yet
            if run is not None and run.claim is None:
                self.record(key, run, name, value)

    async def start(self, key: Key, conn: t.Any) -> None:
        self.sweep()
        now = self.clock()
        # Replaces any earlier run of this player here, giving up a score not yet cashed in
        run = Run(seed=new_seed(), started=now, seen=now)
        self.runs[key] = run
        await conn.send({"run": {"seed": run.seed}})

    def record(self, key: Key, run: Run, name: str, value: t.Any) -> None:
        """Keeps a move, a progress report or the game over, after the clock check"""
        now = self.clock()
        run.seen = now
        step = value if name == "at" else value[0]
        problem = clock_problem(run, step, now)
        if problem is None and name == "move" and len(run.moves) >= MAX_MOVES:
            problem = TOO_MANY
        if problem is not None:
            # The first reason is the one the player sees
            run.refused = run.refused or problem
        elif name == "move":
            run.moves.append(value)
        elif name == "at":
            run.at = value
        if name == "over":
            run.claim = value
            # Finished off the message handler, so a check never holds up the player's next message
            task = asyncio.create_task(self.finish(key, run))
            self.track(task, self.saving, key[1])

    def track(self, task: asyncio.Task, group: set[asyncio.Task], user_id: int) -> None:
        group.add(task)
        self.owners[task] = user_id

        def forget(done: asyncio.Task) -> None:
            group.discard(done)
            self.owners.pop(done, None)

        task.add_done_callback(forget)

    # ---------- Checking, game over and high scores ----------

    async def checked(self, key: Key, run: Run) -> dict:
        """The run's replay, started once however many ask for it. The claim's step is where the replay stops"""
        if run.checking is None:
            run.checking = asyncio.create_task(self.checker.check(run.seed, list(run.moves), run.claim[0]))
            self.track(run.checking, self.checks, key[1])
        # Waiting never cancels the check, so one waiter giving up doesn't stop what another waits on. Only a waiter
        # that is cancelled itself raises here
        await asyncio.wait({run.checking})
        if run.checking.cancelled():
            # The check itself was stopped (unloading, or its player's data deleted): its waiters end quietly
            return {"error": CHECK_FAILED}
        try:
            checked = run.checking.result()
        except Exception as e:
            log.error("A Starhold check failed for seed %s", run.seed, exc_info=e)
            return {"error": CHECK_FAILED}
        if checked.get("retry"):
            # The bot couldn't check anything, which says nothing about this run: the next ask checks it again
            run.checking = None
            return {"error": CHECK_FAILED}
        return checked

    async def check_and_save(self, key: Key, author: t.Any, run: Run) -> tuple[dict, bool]:
        """
        Replays the run and saves its checked score when it beats the player's best. Returns the check, and whether
        it was a new best
        """
        checked = await self.checked(key, run)
        if "error" in checked:
            return checked, False
        return checked, await self.save_best(run, author, checked["score"])

    async def save_best(self, run: Run, author: t.Any, score: int) -> bool:
        group = self.config.member(author)
        try:
            async with self.writes:
                # Their data was deleted meanwhile: nothing of theirs is written again
                if run.dropped:
                    return False
                entry, better = add_score({"best": await group.best()}, score, author.display_name)
                if better:
                    # Field by field, so a cash-in counted meanwhile is never written over
                    await group.best.set(entry["best"])
                    await group.name.set(entry["name"])
                return better
        except Exception as e:
            log.error("Couldn't save a Starhold score for user %s", author.id, exc_info=e)
            return False

    async def known_check(self, key: Key, author: t.Any, run: Run, check_best: bool) -> tuple[dict | None, bool]:
        """
        The run's check, if one finished, and whether it was a new best. With check_best, a claim that beats the
        player's saved best is checked on the spot. Other runs are only checked when cashed in
        """
        if run.checking is not None and run.checking.done():
            return await self.checked(key, run), False
        if check_best and run.claim[1] > await self.config.member(author).best():
            return await self.check_and_save(key, author, run)
        return None, False

    async def finish(self, key: Key, run: Run) -> None:
        try:
            result = await self.result_for(key, run, check_best=True)
        except Exception as e:
            log.error("Couldn't finish a Starhold run for user %s", key[1], exc_info=e)
            return
        conn = self.conns.get(key)
        # Unless the player already started another run while this one was being checked
        if conn is not None and self.runs.get(key) is run:
            await conn.send({"result": result})

    async def result_for(self, key: Key, run: Run, check_best: bool = False) -> dict:
        """The game over screen: the score, the player's best and rank on this server, and what cashing in pays"""
        author = self.authors.get(key)
        result = {
            "score": run.claim[1],
            "wave": run.claim[2],
            "best": None,
            "rank": None,
            "newBest": False,
            "checked": False,
            "offer": None,
            "refused": run.refused,
        }
        if not in_server(author):
            return {**result, "dm": True}
        if run.refused is None and run.claim[0] >= SHORTEST_STEPS:
            checked, result["newBest"] = await self.known_check(key, author, run, check_best)
            if checked is not None and "error" in checked:
                # A run is checked once, so a failed check stays failed
                result["refused"] = checked["error"]
            else:
                if checked is not None:
                    result.update(score=checked["score"], checked=True)
                if not run.cashed and result["score"] > 0:
                    result["offer"] = await self.payouts.offer(author, result["score"])
        result.update(await self.standing(author))
        return result

    async def standing(self, author: t.Any) -> dict:
        table = rank(await self.config.all_members(author.guild), author.id)
        you = table["you"] or {"best": None, "rank": None}
        return {"best": you["best"], "rank": you["rank"]}

    # ---------- Cashing in ----------

    def cashable(self, run: Run | None, author: t.Any) -> bool:
        if run is None or run.claim is None or run.refused is not None or run.cashed or not in_server(author):
            return False
        return run.claim[0] >= SHORTEST_STEPS and run.claim[1] > 0

    async def cash_in(self, key: Key, conn: t.Any) -> None:
        run = self.runs.get(key)
        author = self.authors.get(key)
        if not self.cashable(run, author):
            await conn.send({"notice": NOTHING_TO_CASH})
            return
        # Taken before any wait, so a second press (or a second device) can't pay the same run twice
        run.cashed = True
        # Listed before any wait too, so deleting the player's data reaches this cash-in however the run is replaced
        self.cashing.setdefault(key[1], []).append(run)
        try:
            await self.cash_in_run(key, author, run, conn)
        except Exception as e:
            log.error("A Starhold cash-in failed for user %s", key[1], exc_info=e)
            if run.dropped:
                return
            if run.paying:
                # The deposit may have gone through, so the run is never paid again
                await conn.send({"notice": CASH_FAILED})
            else:
                run.cashed = False
                await conn.send({"notice": CASH_RETRY})
        finally:
            # Only this cash-in's own entry: a newer page can cash the same run in again meanwhile, listing it twice.
            # Found by identity, as two runs with the same fields compare equal
            runs = self.cashing.get(key[1], [])
            index = next((index for index, other in enumerate(runs) if other is run), None)
            if index is not None:
                runs.pop(index)
            if not runs:
                self.cashing.pop(key[1], None)

    async def send_card(self, key: Key, run: Run, conn: t.Any) -> None:
        """A fresh game over card, unless the player has since started another run"""
        if self.runs.get(key) is run:
            await conn.send({"result": await self.result_for(key, run)})

    async def cash_in_run(self, key: Key, author: t.Any, run: Run, conn: t.Any) -> None:
        # Asked before the check, so a cash-in that can't pay never starts a side program
        offer = await self.payouts.offer(author, run.claim[1])
        if run.dropped:
            return
        if offer is None or offer["left"] <= 0:
            run.cashed = False
            if offer is None:
                await conn.send({"notice": PAYOUTS_OFF})
            else:
                # A fresh game over card says none are left, with no cash-in button to press again
                await self.send_card(key, run, conn)
            return
        checked, _ = await self.check_and_save(key, author, run)
        if run.dropped:
            return
        if "error" in checked:
            # Final, as a run is checked at most once: a fresh game over card says why, with no cash-in button
            await self.send_card(key, run, conn)
            return
        await self.pay(key, author, run, checked, conn)

    async def pay(self, key: Key, author: t.Any, run: Run, checked: dict, conn: t.Any) -> None:
        # Their data was deleted while the check ran: nothing is paid or counted
        if run.dropped:
            return
        run.paying = True
        try:
            result = await self.payouts.cash_in(author, checked["score"])
        except Exception as e:
            log.error("Couldn't pay a Starhold cash-in for user %s", author.id, exc_info=e)
            # The deposit may already have gone through, so the run stays cashed and is never paid twice
            await self.send_card(key, run, conn)
            await conn.send({"notice": CASH_FAILED})
            return
        if "error" in result:
            # Nothing was paid, so the run can be cashed in again, on the same check
            run.cashed = False
            run.paying = False
            if result["error"] in (NONE_LEFT, NOTHING_EARNED):
                # Final for this run: a fresh game over card says why, with no cash-in button
                await self.send_card(key, run, conn)
            else:
                await conn.send({"notice": result["error"]})
            return
        paid = {**result, "score": checked["score"], "claim": run.claim[1], **await self.standing(author)}
        await conn.send({"cashed": paid})

    async def scores(self, ctx, data: dict) -> dict:
        """The server's high score table"""
        if ctx.guild is None:
            return {"top": [], "you": None, "dm": True}
        return rank(await self.config.all_members(ctx.guild), ctx.author.id)

    # ---------- Payout settings ----------

    async def can_set_payouts(self, ctx) -> bool:
        """
        Server admins set their server's payouts. With a global bank one balance is shared by every server, so
        only the bot owner does, for every server at once
        """
        if await self.payouts.bank.is_global():
            return await self.bot.is_owner(ctx.author)
        return await ctx.is_admin()

    async def payout_settings(self, ctx, data: dict) -> dict:
        """The settings dialog's numbers, or {"settings": None} for players who can't change them"""
        if not await self.can_set_payouts(ctx):
            return {"settings": None}
        return {
            "settings": await self.payouts.settings(ctx.guild),
            "defaults": DEFAULTS,
            "global": await self.payouts.bank.is_global(),
            "currency": await self.payouts.bank.get_currency_name(ctx.guild),
            "today": await self.payouts.today_paid(ctx.guild),
        }

    async def save_payouts(self, ctx, data: dict) -> dict:
        # Checked on every save: a hidden button in the page is not the only lock
        if not await self.can_set_payouts(ctx):
            return {"error": NOT_AN_ADMIN}
        try:
            await self.payouts.save(ctx.guild, data.get("settings"))
        except SettingsError as e:
            return {"error": str(e)}
        return await self.payout_settings(ctx, {})
