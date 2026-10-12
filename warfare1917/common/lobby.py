"""One Activity window's battles: every battle running in it, who sees each, and the players' requests for their own.

One loop steps every battle in the window at the original's 35 steps a second, 3 steps at a time, and sends each
battle's update to its players and watchers after each tick. A battle stays here until 6 seconds after it ends
(postBattleScreen's delay, F5:4292); then `over` carries its result and the battle is gone.

A solo battle (campaign or custom) whose player has no page open anywhere pauses at once and waits up to 10 minutes
for them. A page that comes back gets the whole battle, still paused, and the player unpauses it.

A versus battle never pauses. A player with no page in the window loses by surrender once they have been gone 60
seconds, or at once when their only page is in another window (they left this one), or when they quit to the main
menu.
"""

import asyncio
import itertools
import logging
import math
import random
import typing as t
from dataclasses import dataclass, field

from . import view
from .battle import Battle
from .blasts import call_support
from .data import FPS, SUPPORT_KINDS, UNIT_KINDS
from .gas import masks_on
from .missions import other_side
from .morale import end
from .targeting import flip_lock, send_over

log = logging.getLogger("red.vrt.warfare1917.lobby")

STEPS = 3
TICK_SECONDS = STEPS / FPS
# After a freeze longer than this, the loop skips the steps it missed instead of running them all at once
CATCH_UP_SECONDS = 0.25
# The results screen comes 6 seconds after the end (setTimeout(postBattleScreen, 6000), F5:4292)
OVER_STEPS = 210
# A solo battle whose player has no page left waits this long for them, then goes with no result
DROP_SECONDS = 600
# A versus player with no page in the window loses by surrender after this long
VERSUS_DROP_SECONDS = 60
SOLO = ("campaign", "custom")
LOOP_FAILED = "Something went wrong, so the battles in this window were stopped."
# One count for every window, after a prefix drawn each time the cog loads, so no two battles share an id, even
# across a reload while a page still shows an old one
IDS = itertools.count(1)
PREFIX = f"{random.getrandbits(24):06x}"


def new_id(letter: str) -> str:
    return f"{letter}{PREFIX}-{next(IDS)}"


def whole(value: t.Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def number(value: t.Any) -> bool:
    """A finite JSON number (not a bool)"""
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(eq=False)
class Run:
    """One battle running in the window"""

    id: str
    kind: str  # "campaign", "custom" or "versus"
    battle: Battle
    players: dict[int, str]  # user id: the side they command
    names: dict[str, str | None]  # each side's player name, None for the CPU
    title: str  # "Mission 3 · TAKE COVER!" or "Custom battle"
    reported: bool = False  # its result went to the cog
    sent_paused: bool = False  # the last update sent said paused
    dropped_at: float | None = None  # when its solo player's last page closed
    away: dict[int, float] = field(default_factory=dict)  # versus players with no page in the window: since when
    camera: dict[str, float] = field(default_factory=dict)  # each side's player: where their camera is (world x)
    watchers: list = field(default_factory=list)
    faces: list = field(default_factory=list)  # the watchers its audience was last told of

    @property
    def solo(self) -> bool:
        return self.kind in SOLO


@dataclass(eq=False)
class Game:
    """An open versus game waiting for a second player"""

    id: str
    user_id: int
    name: str
    avatar: str
    settings: dict  # checked custom settings; `side` is the opener's side


class Window:
    def __init__(
        self,
        room: t.Any,
        on_result: t.Callable[[Run], None],
        on_closed: t.Callable[["Window"], None],
        everywhere: t.Callable[[], t.Iterable["Window"]] | None = None,
        on_take: t.Callable[[t.Any, str], t.Awaitable[None]] | None = None,
        on_level: t.Callable[[Run], None] | None = None,
        on_dismiss: t.Callable[[Run], None] | None = None,
    ):
        """`on_result(run)` is called once, on the step a battle ends (it keeps playing its cheers after).
        `on_closed(window)` is called when the loop has stopped. `everywhere()` gives every live window, since a
        player who reopens the Activity lands in a new window while their battle carries on in the old one.
        `await on_take(conn, game_id)` seats a page in an open versus game and starts the battle.
        `on_level(run)` is called on the step a campaign player's kill XP reaches a new level.
        `on_dismiss(run)` is called when a battle is gone with no result"""
        self.room = room
        self.on_result = on_result
        self.on_closed = on_closed
        self.on_take = on_take
        self.on_level = on_level
        self.on_dismiss = on_dismiss
        self.windows = everywhere or (lambda: [self])
        self.runs: dict[str, Run] = {}
        self.games: dict[str, Game] = {}
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
            # Logged once and stopped, so a bug can't fill the log 11 times a second. A campaign stays as it was
            # saved at Launch Battle, so the mission plays again
            log.error("Warfare 1917 stopped the battles in window %s", self.room.instance_id, exc_info=e)
            stopped = list(self.runs.values())
            self.runs.clear()
            self.games.clear()
            for run in stopped:
                for conn in self.audience(run):
                    await conn.send({"over": {"id": run.id, "result": None, "next": "menu"}})
                    await conn.send({"notice": LOOP_FAILED})
                if self.on_dismiss is not None:
                    self.on_dismiss(run)
            await self.room.broadcast(self.lobby())
        finally:
            self.on_closed(self)

    async def tick(self) -> None:
        now = asyncio.get_running_loop().time()
        for run in list(self.runs.values()):
            if run.dropped_at is not None and now - run.dropped_at >= DROP_SECONDS:
                # Its player never came back: gone with no result, the campaign as saved at Launch Battle
                await self.dismiss(run)
                continue
            self.expire_drops(run, now)
            await self.advance(run)
        if self.dirty:
            self.dirty = False
            await self.room.broadcast(self.lobby())

    def expire_drops(self, run: Run, now: float) -> None:
        """A versus player gone from the window for 60 seconds, or whose only page is in another window, loses by
        surrender (D12). Their opponent keeps playing to the end"""
        if run.kind != "versus" or run.battle.state != "playing":
            return
        for user_id, side in run.players.items():
            if any(conn.ctx.author.id == user_id for conn in self.room.connections):
                run.away.pop(user_id, None)
                continue
            since = run.away.setdefault(user_id, now)
            if now - since >= VERSUS_DROP_SECONDS or self.pages(user_id):
                end(run.battle, other_side(side), "left")
                return

    async def advance(self, run: Run) -> None:
        battle = run.battle
        for _ in range(STEPS):
            battle.tick()
        if battle.state == "ended" and not run.reported:
            run.reported = True
            self.on_result(run)
        audience = self.audience(run)
        faces = self.faces(run)
        changed = faces != run.faces
        run.faces = faces
        # A paused battle doesn't change, so it is sent once when it pauses, not 11 times a second
        if changed or not (battle.paused and run.sent_paused and not battle.events):
            run.sent_paused = battle.paused
            update = view.update(battle, battle.step, run.id)
            for conn in audience:
                if changed:
                    await conn.send({"watchers": {"id": run.id, "people": faces}})
                await conn.send(update)
        # After the update, so the save that counts the level reaches the page behind the kill that earned it
        if battle.level_due:
            battle.level_due = False
            if self.on_level is not None:
                self.on_level(run)
        if battle.state == "ended" and battle.step - battle.ended_at >= OVER_STEPS:
            await self.finish(run)

    async def finish(self, run: Run) -> None:
        """The battle's results screen is due: its audience gets the result, and the battle is gone"""
        audience = self.audience(run)
        self.remove(run)
        for conn in audience:
            next_screen = self.next_screen(run, conn)
            await conn.send({"over": {"id": run.id, "result": view.result(run.battle, next_screen)}})

    def remove(self, run: Run) -> None:
        self.runs.pop(run.id, None)
        run.watchers.clear()
        self.dirty = True

    async def dismiss(self, run: Run, spare: t.Any = None) -> None:
        """A battle gone with no result. Its audience is sent back to the main menu, except the page `spare`, which
        went there itself. The battle is removed from the window it runs in, which may not be this one"""
        audience = self.audience(run)
        owner = next((window for window in self.everywhere() if run.id in window.runs), self)
        owner.remove(run)
        self.dirty = True
        for conn in audience:
            if conn is not spare:
                await conn.send({"over": {"id": run.id, "result": None}})
        if self.on_dismiss is not None:
            self.on_dismiss(run)

    def next_screen(self, run: Run, conn: t.Any) -> str:
        """Where Continue on the results screen goes for this viewer"""
        side = run.players.get(conn.ctx.author.id)
        if side is None:
            return "watch"
        if run.kind == "custom":
            return "custom"
        if run.kind == "versus":
            return "versus"
        battle = run.battle
        last = battle.mission.number == 9
        return "ending" if last and battle.winner == side and battle.campaign else "map"

    # ---------- Battles ----------

    async def start_run(
        self, kind: str, battle: Battle, players: dict[int, str], names: dict[str, str | None], title: str
    ) -> Run:
        """Starts a battle and shows it to its players on every page they have open. Everything up to the first
        await runs at once, so a caller that checked nobody is busy can't be overtaken by another start"""
        run = Run(new_id("b"), kind, battle, players, names, title)
        self.runs[run.id] = run
        self.dirty = True
        everywhere = self.everywhere()
        for user_id in players:
            for window in everywhere:
                window.cancel(user_id)
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
        you = run.players.get(conn.ctx.author.id)
        return view.full(run, run.battle, you, run.names, self.faces(run), self.next_screen(run, conn))

    def players(self, run: Run) -> list[dict]:
        """The people commanding a battle, British first. A player with no page open has no picture to show"""
        people = []
        for side in ("british", "german"):
            user_id = next((uid for uid, played in run.players.items() if played == side), None)
            if user_id is None:
                continue
            page = next(iter(self.pages(user_id)), None)
            avatar = page.ctx.author.display_avatar.url if page is not None else ""
            people.append({"id": str(user_id), "name": run.names[side], "avatar": avatar, "side": side})
        return people

    def lobby(self) -> dict:
        battles = [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "names": r.names,
                "players": self.players(r),
                "watchers": self.faces(r),
            }
            for r in self.runs.values()
        ]
        versus = [
            {
                "id": g.id,
                "side": g.settings["side"],
                "name": g.name,
                "user": str(g.user_id),
                "avatar": g.avatar,
                "settings": g.settings,
            }
            for g in self.games.values()
        ]
        return {"lobby": {"battles": battles, "versus": versus}}

    # ---------- People ----------

    async def join(self, conn: t.Any, follow: int | None = None) -> None:
        """A page arriving. `follow` is the friend whose Join in the hub's people list opened it, if any"""
        # The page hears which battle is its player's, so one still showing a battle whose end it missed knows that
        # battle is gone
        run = self.mine(conn.ctx.author.id)
        # Everyone's list shows this player's picture from now on
        self.dirty = True
        await conn.send({**self.lobby(), "mine": run.id if run is not None else None})
        if run is not None:
            # Back from a drop: the battle stays paused until the page asks to go on
            run.dropped_at = None
            run.away.pop(conn.ctx.author.id, None)
            await conn.send(self.full(run, conn))
        elif follow is not None:
            await self.follow(conn, follow)

    async def follow(self, conn: t.Any, friend: int) -> None:
        """Puts the player with their friend (D6): in the friend's versus game when it is open, else watching the
        battle the friend fights or watches, else on the main menu"""
        game = next((game for game in self.games.values() if game.user_id == friend), None)
        if game is not None:
            if self.on_take is not None:
                await self.on_take(conn, game.id)
            # Seated, the battle is already on the page. If the game could not be taken, the versus lobby opens
            if self.mine(conn.ctx.author.id) is None:
                await conn.send({"follow": "versus"})
            return
        run = self.run_of(friend) or next(
            (run for run in self.runs.values() if any(w.ctx.author.id == friend for w in run.watchers)), None
        )
        if run is not None:
            await self.watch(conn, run.id)
        else:
            await conn.send({"follow": "menu"})

    async def watch(self, conn: t.Any, run_id: t.Any) -> None:
        """A page starts watching a battle of the window. A player with a battle of their own can't watch another"""
        run = self.runs.get(run_id) if isinstance(run_id, str) else None
        if run is None or self.mine(conn.ctx.author.id) is not None:
            return
        self.unwatch(conn)
        run.watchers.append(conn)
        self.dirty = True
        await conn.send(self.full(run, conn))

    def unwatch(self, conn: t.Any) -> None:
        for run in self.runs.values():
            if any(watcher is conn for watcher in run.watchers):
                run.watchers[:] = [watcher for watcher in run.watchers if watcher is not conn]
                self.dirty = True

    def leave(self, conn: t.Any) -> None:
        """A page closing. The hub takes it out of the room before this runs"""
        self.unwatch(conn)
        self.dirty = True
        user_id = conn.ctx.author.id
        # An open game closes with its opener's last page in the window
        if not any(other.ctx.author.id == user_id for other in self.room.connections if other is not conn):
            self.cancel(user_id)
        run = self.mine(user_id)
        if run is None or not run.solo or self.pages(user_id):
            return
        if run.battle.state == "playing":
            run.battle.paused = True
            run.dropped_at = asyncio.get_running_loop().time()

    # ---------- Versus games waiting for a second player ----------

    def open_game(self, conn: t.Any, settings: dict) -> Game:
        """The player's open game, in place of any they had (one open game per player)"""
        author = conn.ctx.author
        self.cancel(author.id)
        game = Game(new_id("v"), author.id, author.display_name, author.display_avatar.url, settings)
        self.games[game.id] = game
        self.dirty = True
        return game

    def cancel(self, user_id: int) -> None:
        for game_id, game in list(self.games.items()):
            if game.user_id == user_id:
                del self.games[game_id]
                self.dirty = True

    def take_game(self, game_id: t.Any, taker: int) -> Game | None:
        """The game, taken out of the list, when it is open and its opener is someone else"""
        game = self.games.get(game_id) if isinstance(game_id, str) else None
        if game is None or game.user_id == taker:
            return None
        del self.games[game.id]
        self.dirty = True
        return game

    # ---------- The player's requests for their own battle ----------

    async def request(self, conn: t.Any, kind: str, value: t.Any) -> None:
        """A request for the player's own battle, wherever it runs. Anything that isn't allowed now is ignored"""
        user_id = conn.ctx.author.id
        run = self.mine(user_id)
        if run is None:
            return
        side = run.players[user_id]
        if kind == "quit" and value is True and run.kind == "versus":
            # Quit to Main Menu in a versus battle is leaving it, which loses by surrender (D12)
            if run.battle.state == "playing":
                end(run.battle, other_side(side), "left")
        elif kind in ("pause", "quit"):
            await self.solo_request(conn, run, kind, value)
        elif kind == "camera":
            if number(value):
                run.camera[side] = value
        elif kind == "surrender":
            if value is True and run.battle.state == "playing":
                # Quit Battle: endBattle(compTeam.team, "morale"), F5:6671-6675. The menu it comes from closes,
                # so the battle runs on to show the surrender
                run.battle.paused = False
                end(run.battle, other_side(side), "surrender")
        else:
            self.order(run.battle, side, kind, value)

    async def solo_request(self, conn: t.Any, run: Run, kind: str, value: t.Any) -> None:
        battle = run.battle
        if not run.solo or battle.state != "playing":
            return
        if kind == "pause" and isinstance(value, bool):
            battle.paused = value
            run.dropped_at = None
        elif kind == "quit" and value is True:
            # Quit to Main Menu (F5:6676-6683): the battle is gone with no result
            await self.dismiss(run, conn)

    @staticmethod
    def order(battle: Battle, side: str, kind: str, value: t.Any) -> None:
        """The battle's own orders, each checked against the battle's state by the engine"""
        if kind == "deploy" and whole(value, 1, len(UNIT_KINDS)):
            battle.deploy(side, value)
        elif kind == "support" and isinstance(value, list) and len(value) == 2:
            slot, x = value
            if whole(slot, 1, len(SUPPORT_KINDS)) and number(x):
                call_support(battle, side, slot, x)
        elif kind == "masks" and value is True:
            masks_on(battle, side)
        elif kind == "trench" and isinstance(value, list) and value:
            index = value[0]
            if not whole(index, 0, len(battle.trenches) - 1):
                return
            if value[1:] == ["lock"]:
                flip_lock(battle, side, index)
            elif len(value) == 3 and value[1] == "go" and whole(value[2], 0, 2):
                send_over(battle, side, index, value[2])
