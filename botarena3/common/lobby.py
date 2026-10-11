"""One Activity window's battles: every battle running in it, who watches each, and the open PvP fights. One loop
steps them all at the original's 33 steps a second, 3 steps at a time, and sends each battle's update after each"""

import asyncio
import itertools
import logging
import random
import typing as t
from dataclasses import dataclass, field

from .battle import DRAW_STEPS, FPS, Battle

log = logging.getLogger("red.vrt.botarena3.lobby")

STEPS = 3
TICK_SECONDS = STEPS / FPS
# After a freeze longer than this, the loop skips the steps it missed instead of running them all at once
CATCH_UP_SECONDS = 0.25
LOOP_FAILED = "Something went wrong, so the battles in this window were stopped."
# Farther than this from the stage (about 700 pixels wide) is no place a drag can end
FAR = 10_000
# One count for every window, after a prefix drawn each time the cog loads, so no two battles or fights share an id,
# even across a reload while a page still shows an old one
IDS = itertools.count(1)
PREFIX = f"{random.getrandbits(24):06x}"


def new_id(letter: str) -> str:
    return f"{letter}{PREFIX}-{next(IDS)}"


@dataclass(eq=False)
class Run:
    """One battle running in the window"""

    id: str
    kind: str  # "arena", "challenge" or "pvp"
    index: int  # the arena's or challenge's place in the original's list. 0 for PvP
    title: str
    background: int
    battle: Battle
    players: dict[int, int]  # user id: the side they command
    names: list[str | None]  # each side's player, None for the computer
    boards: dict[int, str]  # user id: the Discord-wide name the leaderboard shows
    seed: int
    beats_game: bool = False  # winning this arena beats the game for its career
    reported: bool = False  # its result went to the cog
    watchers: list = field(default_factory=list)
    faces: list = field(default_factory=list)  # the watchers its audience was last told of


@dataclass(eq=False)
class Fight:
    """An open PvP fight waiting for someone to join"""

    id: str
    user_id: int
    name: str
    board: str
    background: int
    weight: str | None


class Window:
    def __init__(
        self,
        room: t.Any,
        result: t.Callable[[Run], None],
        closed: t.Callable[["Window"], None],
        windows: t.Callable[[], t.Iterable["Window"]] | None = None,
    ):
        """`result(run)` is called once, on the step a battle gets its result (it keeps playing its banner after).
        `closed(window)` is called when the loop has stopped. `windows()` gives every live window, since a player who
        reopens the Activity lands in a new window while their battle carries on in the old one"""
        self.room = room
        self.result = result
        self.closed = closed
        self.windows = windows or (lambda: [self])
        self.runs: dict[str, Run] = {}
        self.fights: dict[str, Fight] = {}
        self.dirty = True
        self.task: asyncio.Task | None = None

    # ---------- The loop ----------

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop())

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def alive(self) -> bool:
        return bool(self.room.connections) or bool(self.runs)

    async def loop(self) -> None:
        clock = asyncio.get_running_loop()
        next_tick = clock.time()
        try:
            while self.alive():
                await self.tick()
                next_tick += TICK_SECONDS
                if clock.time() - next_tick > CATCH_UP_SECONDS:
                    next_tick = clock.time()
                await asyncio.sleep(max(0.0, next_tick - clock.time()))
        except Exception as e:
            # Logged once and stopped, so a bug can't fill the log 11 times a second. Held entry fees come back the
            # next time each player opens the game
            log.error("Bot Arena 3 stopped the battles in window %s", self.room.instance_id, exc_info=e)
            stopped = list(self.runs.values())
            self.runs.clear()
            self.fights.clear()
            await self.room.broadcast(self.lobby())
            await self.room.broadcast({"notice": LOOP_FAILED})
            await self.tell_away(stopped)
        finally:
            self.closed(self)

    async def tell_away(self, stopped: list[Run]) -> None:
        """Players seeing a stopped battle from another window never get this window's list, so they are told it ended"""
        here = self.room.connections
        for run in stopped:
            for conn in self.audience(run):
                if not any(conn is other for other in here):
                    await conn.send({"over": {"id": run.id, "next": self.next_screen(run, conn)}})
                    await conn.send({"notice": LOOP_FAILED})

    async def tick(self) -> None:
        for run in list(self.runs.values()):
            await self.advance(run)
        if self.dirty:
            self.dirty = False
            await self.room.broadcast(self.lobby())

    async def advance(self, run: Run) -> None:
        battle = run.battle
        for _ in range(STEPS):
            battle.tick()
        if battle.ended is not None and not run.reported:
            run.reported = True
            self.result(run)
        update = {"u": {"id": run.id, "step": battle.step, "r": battle.view(), "e": battle.take_events()}}
        faces = self.faces(run)
        changed = faces != run.faces
        run.faces = faces
        for conn in self.audience(run):
            if changed:
                await conn.send({"watchers": {"id": run.id, "people": faces}})
            await conn.send(update)
        if battle.done():
            await self.finish(run)
        elif self.abandoned(run):
            # Nobody to see it end, and it has stalled. A career battle's fee comes back when its player returns
            del self.runs[run.id]
            self.dirty = True

    def abandoned(self, run: Run) -> bool:
        if run.kind == "pvp" or run.battle.ended is not None or self.audience(run):
            return False
        return run.battle.step - run.battle.last_damage >= DRAW_STEPS

    async def finish(self, run: Run) -> None:
        del self.runs[run.id]
        self.dirty = True
        for conn in self.audience(run):
            await conn.send({"over": {"id": run.id, "next": self.next_screen(run, conn)}})
        run.watchers.clear()

    def next_screen(self, run: Run, conn: t.Any) -> str:
        team = run.players.get(conn.ctx.author.id)
        if team is None:
            return "watch"
        if run.kind == "pvp":
            return "pvp"
        if run.kind == "challenge":
            return "challenges"
        return "wingame" if run.beats_game and run.battle.winner == team else "shop"

    # ---------- Battles ----------

    async def add_run(
        self,
        kind: str,
        index: int,
        title: str,
        background: int,
        teams: t.Sequence[t.Sequence[dict]],
        colors: t.Sequence[int],
        players: dict[int, int],
        names: list[str | None],
        boards: dict[int, str],
        *,
        owned: t.Sequence[bool],
        draws: bool,
        beats_game: bool = False,
    ) -> Run:
        """Starts a battle and shows it to its players. Everything up to the first await runs at once, so a caller
        that checked nobody is busy can't be overtaken by another start"""
        seed = random.getrandbits(63)
        battle = Battle(teams, colors, owned=owned, draws=draws, rng=random.Random(seed))
        run = Run(new_id("b"), kind, index, title, background, battle, players, names, boards, seed, beats_game)
        self.runs[run.id] = run
        self.dirty = True
        everywhere = self.everywhere()
        for conn in self.audience(run):
            for window in everywhere:
                window.unwatch(conn)
            await conn.send(self.full(run, conn))
        return run

    def run_of(self, user_id: int) -> Run | None:
        """The player's battle in this window"""
        return next((run for run in self.runs.values() if user_id in run.players), None)

    def everywhere(self) -> list["Window"]:
        """This window and every other live one"""
        return [self, *(window for window in self.windows() if window is not self)]

    def mine(self, user_id: int) -> Run | None:
        """The player's battle in any window"""
        return next((run for window in self.everywhere() if (run := window.run_of(user_id)) is not None), None)

    def pages(self, user_id: int) -> list:
        """The player's open pages in every window"""
        rooms = [window.room.connections for window in self.everywhere()]
        return [conn for conns in rooms for conn in conns if conn.ctx.author.id == user_id]

    def audience(self, run: Run) -> list:
        """Everyone seeing the battle: its players on every page they have open, in any window, and its watchers"""
        players = [conn for user_id in run.players for conn in self.pages(user_id)]
        return players + [conn for conn in run.watchers if not any(conn is p for p in players)]

    @staticmethod
    def faces(run: Run) -> list[dict]:
        """Who watches the battle, once each however many devices they watch on, in the order they came"""
        people = {}
        for conn in run.watchers:
            author = conn.ctx.author
            if author.id not in people:
                people[author.id] = {
                    "id": str(author.id),
                    "name": author.display_name,
                    "avatar": author.display_avatar.url,
                }
        return list(people.values())

    def full(self, run: Run, conn: t.Any) -> dict:
        battle = run.battle
        return {
            "battle": {
                "id": run.id,
                "kind": run.kind,
                "index": run.index,
                "title": run.title,
                "background": run.background,
                "you": run.players.get(conn.ctx.author.id),
                "names": run.names,
                "colors": battle.colors,
                "robots": battle.setup(),
                "step": battle.step,
                "r": battle.view(),
                "flames": battle.wrecks(),
                "ended": battle.ended,
                "winner": battle.winner,
                "watchers": self.faces(run),
            }
        }

    def lobby(self) -> dict:
        battles = [{"id": r.id, "kind": r.kind, "title": r.title, "names": r.names} for r in self.runs.values()]
        fights = [
            {"id": f.id, "user": str(f.user_id), "name": f.name, "background": f.background, "weight": f.weight}
            for f in self.fights.values()
        ]
        return {"lobby": {"battles": battles, "fights": fights}}

    # ---------- PvP fights waiting for a second player ----------

    def open_fight(self, user_id: int, name: str, board: str, background: int, weight: str | None) -> Fight:
        self.cancel(user_id)
        fight = Fight(new_id("f"), user_id, name, board, background, weight)
        self.fights[fight.id] = fight
        self.dirty = True
        return fight

    def cancel(self, user_id: int) -> None:
        for fight_id, fight in list(self.fights.items()):
            if fight.user_id == user_id:
                del self.fights[fight_id]
                self.dirty = True

    def take_fight(self, fight_id: str) -> Fight | None:
        fight = self.fights.pop(fight_id, None)
        if fight is not None:
            self.dirty = True
        return fight

    # ---------- People ----------

    async def join(self, conn: t.Any, follow: int | None = None) -> None:
        """A page arriving. `follow` is the friend whose Join in the hub's people list opened it, if any"""
        await conn.send(self.lobby())
        # A player who reopened the Activity lands in a new window, while their battle runs on in the old one
        run = self.mine(conn.ctx.author.id)
        if run is not None:
            await conn.send(self.full(run, conn))
        elif follow is not None:
            await self.follow(conn, follow)

    async def follow(self, conn: t.Any, friend: int) -> None:
        """Puts the player with their friend: watching the battle the friend fights or watches, or on the PvP screen
        when the friend has a fight open. Anywhere else, the page opens on its menu as usual"""
        run = self.run_of(friend) or next(
            (run for run in self.runs.values() if any(w.ctx.author.id == friend for w in run.watchers)), None
        )
        if run is not None:
            await self.watch(conn, run.id)
        elif any(fight.user_id == friend for fight in self.fights.values()):
            await conn.send({"follow": "pvp"})

    def leave(self, conn: t.Any) -> None:
        self.unwatch(conn)
        user_id = conn.ctx.author.id
        # The hub takes a closing connection out of the room before leave runs
        if not any(other.ctx.author.id == user_id for other in self.room.connections if other is not conn):
            self.cancel(user_id)
        self.dirty = True

    async def watch(self, conn: t.Any, run_id: t.Any) -> None:
        run = self.runs.get(run_id) if isinstance(run_id, str) else None
        if run is None or conn.ctx.author.id in run.players:
            return
        self.unwatch(conn)
        run.watchers.append(conn)
        await conn.send(self.full(run, conn))

    def unwatch(self, conn: t.Any) -> None:
        for run in self.runs.values():
            run.watchers[:] = [watcher for watcher in run.watchers if watcher is not conn]

    def order(self, conn: t.Any, value: t.Any) -> None:
        """An order for the player's own battle, wherever it runs"""
        run = self.mine(conn.ctx.author.id)
        if run is None or not isinstance(value, list) or len(value) != 3:
            return
        robot_id, x, y = value
        # Not a number and infinity both fail the comparison too
        numbers = all(type(v) in (int, float) and abs(v) <= FAR for v in (x, y))
        if type(robot_id) is int and numbers:
            run.battle.order(run.players[conn.ctx.author.id], robot_id, x, y)
