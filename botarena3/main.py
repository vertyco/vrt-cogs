import asyncio
import logging
import typing as t
import weakref
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common import career, leaderboard
from .common.arenas import ARENAS, BACKGROUNDS, CHALLENGES, WEIGHT_CLASSES
from .common.lobby import Fight, Run, Window
from .common.parts import DATA, SECRET_LASER

log = logging.getLogger("red.vrt.botarena3")

# What a joining page gets: the game data without the secret laser, which is never sold or given, and which no arena
# team carries, so the page never needs it
PAGE_DATA = {**DATA, "weapons": [weapon for weapon in DATA["weapons"] if weapon["name"] != SECRET_LASER]}


class BotArena3(commands.Cog):
    """
    Bot Arena 3 for ActivityHub, ported from the Flash game on Armor Games.

    Build a team of up to five robots from chassis, plating and weapons, fight your way through 15 arenas, and battle
    other players' teams in the same Activity.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.1"

    BUSY = "You already have a battle running."
    FIGHT_GONE = "That fight isn't open any more."

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101011, force_registration=True)
        self.config.register_user(career=None, pvp=dict(leaderboard.DEFAULTS))
        # One window per Activity window, keyed by its instance id
        self.windows: dict[str, Window] = {}
        # One lock per player, so two devices or windows can't interleave changes to one career. A lock nobody holds
        # or waits for is let go, so the map doesn't keep one for every player who ever played
        self.locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()
        # Result saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        async with self.lock(user_id):
            await self.config.user_from_id(user_id).clear()

    async def cog_unload(self):
        for window in list(self.windows.values()):
            window.stop()
        if self.saving:
            await asyncio.gather(*self.saving, return_exceptions=True)

    async def activityhub_game(self) -> dict:
        return {
            "key": "botarena3",
            "name": "Bot Arena 3",
            "description": "Build robot teams and fight through 15 arenas",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"leaderboard": self.leaderboard},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
        }

    # ---------- Windows ----------

    def lock(self, user_id: int) -> asyncio.Lock:
        lock = self.locks.get(user_id)
        if lock is None:
            lock = self.locks[user_id] = asyncio.Lock()
        return lock

    def window_for(self, conn: t.Any) -> Window:
        """The window's battles, started when its first player arrives, or again after its loop stopped"""
        window = self.windows.get(conn.ctx.instance_id)
        if window is None:
            window = Window(conn.room, self.battle_result, self.window_closed, self.windows.values)
            self.windows[conn.ctx.instance_id] = window
            window.start()
        elif window.room is not conn.room:
            # Reloading ActivityHub gives the window a new room, while its battles live on
            window.room = conn.room
        return window

    def window_closed(self, window: Window) -> None:
        if self.windows.get(window.room.instance_id) is window:
            del self.windows[window.room.instance_id]

    def running(self, user_id: int) -> Run | None:
        """The battle this player is in, in any window"""
        for window in self.windows.values():
            run = window.run_of(user_id)
            if run is not None:
                return run
        return None

    # ---------- Live connections ----------

    async def join(self, ctx, conn) -> None:
        window = self.window_for(conn)
        await conn.send({"data": PAGE_DATA})
        data = await self.settle(conn.ctx.author.id)
        await conn.send({"career": career.view(data)})
        # Set only on the first connection after a Join in the hub's people list
        await window.join(conn, conn.follow)

    async def leave(self, ctx, conn) -> None:
        window = self.windows.get(ctx.instance_id)
        if window is not None:
            window.leave(conn)

    async def message(self, ctx, conn, data) -> None:
        """A page's request. Anything but the exact messages the page sends is ignored"""
        if not isinstance(data, dict) or len(data) != 1:
            return
        # Joining makes the window first; this covers a message that somehow comes before
        self.window_for(conn)
        kind, value = next(iter(data.items()))
        handler = self.handlers().get(kind)
        if handler is not None:
            await handler(conn, value)
            return
        act = career.action(kind, value)
        if act is not None:
            await self.shop(conn, kind, act)

    def handlers(self) -> dict[str, t.Callable[[t.Any, t.Any], t.Awaitable[None]]]:
        return {
            "newCareer": self.new_career,
            "arena": self.start_arena,
            "challenge": self.start_challenge,
            "order": self.give_order,
            "watch": self.watch,
            "unwatch": self.unwatch,
            "open": self.open_fight,
            "cancel": self.cancel_fight,
            "join": self.join_fight,
        }

    # ---------- Careers ----------

    async def settle(self, user_id: int) -> dict | None:
        """The player's career, with an entry fee given back when the battle it paid for was stopped before it ended"""
        async with self.lock(user_id):
            group = self.config.user_from_id(user_id)
            data = await group.career()
            if self.give_back_fee(data, user_id):
                await group.career.set(data)
            return data

    def give_back_fee(self, data: dict | None, user_id: int) -> bool:
        """Refunds a held entry fee when no battle is running to earn it back. True when something was given back"""
        if data is None or not data.get("fee") or self.running(user_id) is not None:
            return False
        career.refund(data)
        return True

    async def shop(self, conn: t.Any, kind: str, act: t.Callable[[dict], str]) -> None:
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            group = self.config.user_from_id(user_id)
            data = await group.career()
            if data is None:
                return
            try:
                said = act(data)
            except career.ShopError as e:
                await conn.send({"career": career.view(data), "refused": str(e)})
                return
            await group.career.set(data)
        await self.send_career(user_id, data, conn, {"done": kind, "said": said})

    async def new_career(self, conn: t.Any, value: t.Any) -> None:
        user_id = conn.ctx.author.id
        if value is not True:
            return
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": self.BUSY})
                return
            data = career.new_career()
            await self.config.user_from_id(user_id).career.set(data)
        await self.send_career(user_id, data, conn, {"done": "newCareer", "said": ""})

    async def send_career(self, user_id: int, data: dict, requester: t.Any = None, extra: dict | None = None) -> None:
        """The career to every device this player has open, with the prompt only for the one that asked"""
        view = career.view(data)
        for window in list(self.windows.values()):
            for conn in list(window.room.connections):
                if conn.ctx.author.id == user_id:
                    await conn.send({"career": view, **(extra or {})} if conn is requester else {"career": view})

    # ---------- Battles ----------

    async def start_arena(self, conn: t.Any, value: t.Any) -> None:
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": self.BUSY})
                return
            group = self.config.user_from_id(user_id)
            data = await group.career()
            if data is None:
                await conn.send({"career": None, "refused": career.NO_TEAM})
                return
            if self.give_back_fee(data, user_id):
                await group.career.set(data)
            try:
                arena = career.enter_arena(data, value)
            except career.ShopError as e:
                await conn.send({"career": career.view(data), "refused": str(e)})
                return
            await group.career.set(data)
            teams = (career.team(data), list(arena.opponents))
            beats = arena is ARENAS[-1] and not data["won"]
            self.close_fights(user_id)
            await self.window_for(conn).add_run(
                "arena",
                value,
                arena.name,
                arena.background,
                teams,
                (data["color"], career.COMPUTER_COLOR),
                {user_id: 1},
                [conn.ctx.author.display_name, None],
                {user_id: self.board_name(conn)},
                owned=(True, False),
                draws=False,
                beats_game=beats,
            )
        await self.send_career(user_id, data)

    async def start_challenge(self, conn: t.Any, value: t.Any) -> None:
        user_id = conn.ctx.author.id
        if not career.whole(value) or not 0 <= value < len(CHALLENGES):
            return
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": self.BUSY})
                return
            challenge = CHALLENGES[value]
            self.close_fights(user_id)
            await self.window_for(conn).add_run(
                "challenge",
                value,
                challenge.name,
                challenge.background,
                (list(challenge.players), list(challenge.opponents)),
                (career.CHALLENGE_COLOR, career.COMPUTER_COLOR),
                {user_id: 1},
                [conn.ctx.author.display_name, None],
                {user_id: self.board_name(conn)},
                owned=(True, False),
                draws=False,
            )

    @staticmethod
    def board_name(conn: t.Any) -> str:
        """The Discord-wide name, since the leaderboard covers every server"""
        author = conn.ctx.author
        return author.global_name or author.name

    async def open_fight(self, conn: t.Any, value: t.Any) -> None:
        if not isinstance(value, list) or len(value) != 2:
            return
        background, weight = value
        if not career.whole(background) or background not in BACKGROUNDS:
            return
        if weight is not None and (not isinstance(weight, str) or weight not in WEIGHT_CLASSES):
            return
        user_id = conn.ctx.author.id
        # Held through the open, so a battle of their own can't start between the check and the fight
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": self.BUSY})
                return
            problem = career.fight_problem(await self.config.user_from_id(user_id).career(), weight)
            if problem is not None:
                await conn.send({"notice": problem})
                return
            name = conn.ctx.author.display_name
            self.window_for(conn).open_fight(user_id, name, self.board_name(conn), background, weight)

    async def cancel_fight(self, conn: t.Any, value: t.Any) -> None:
        if value is True:
            self.window_for(conn).cancel(conn.ctx.author.id)

    async def join_fight(self, conn: t.Any, value: t.Any) -> None:
        if not isinstance(value, str):
            return
        window = self.window_for(conn)
        fight = window.fights.get(value)
        user_id = conn.ctx.author.id
        if fight is None:
            # The page listed it before it closed
            await conn.send({"notice": self.FIGHT_GONE})
            return
        if fight.user_id == user_id:
            return
        # Both players' locks, lowest id first so two joins can't wait on each other. A start of their own (which
        # holds one of these locks) can't slip in between the checks and the battle
        first, second = sorted((user_id, fight.user_id))
        async with self.lock(first), self.lock(second):
            await self.start_pvp(conn, window, fight)

    async def start_pvp(self, conn: t.Any, window: Window, fight: Fight) -> None:
        user_id = conn.ctx.author.id
        if self.running(user_id) is not None:
            await conn.send({"notice": self.BUSY})
            return
        mine = await self.config.user_from_id(user_id).career()
        theirs = await self.config.user_from_id(fight.user_id).career()
        problem = career.fight_problem(mine, fight.weight)
        if problem is not None:
            await conn.send({"notice": problem})
            return
        if self.running(fight.user_id) or career.fight_problem(theirs, fight.weight) is not None:
            window.take_fight(fight.id)
            await conn.send({"notice": self.FIGHT_GONE})
            return
        if window.take_fight(fight.id) is None:
            await conn.send({"notice": self.FIGHT_GONE})
            return
        guest_color = mine["color"] if mine["color"] != theirs["color"] else career.COMPUTER_COLOR
        self.close_fights(user_id, fight.user_id)
        await window.add_run(
            "pvp",
            0,
            "PVP",
            fight.background,
            (career.team(theirs), career.team(mine)),
            (theirs["color"], guest_color),
            {fight.user_id: 1, user_id: 2},
            [fight.name, conn.ctx.author.display_name],
            {fight.user_id: fight.board, user_id: self.board_name(conn)},
            owned=(True, True),
            draws=True,
        )

    def close_fights(self, *user_ids: int) -> None:
        """Starting a battle takes a player's own open fights off every window"""
        for window in self.windows.values():
            for user_id in user_ids:
                window.cancel(user_id)

    async def give_order(self, conn: t.Any, value: t.Any) -> None:
        self.window_for(conn).order(conn, value)

    async def watch(self, conn: t.Any, value: t.Any) -> None:
        await self.window_for(conn).watch(conn, value)

    async def unwatch(self, conn: t.Any, value: t.Any) -> None:
        if value is True:
            self.window_for(conn).unwatch(conn)

    # ---------- Results ----------

    def battle_result(self, run: Run) -> None:
        # Saved off the battle loop, so Config never slows a battle
        task = asyncio.create_task(self.save_result(run))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def save_result(self, run: Run) -> None:
        try:
            if run.kind == "arena":
                await self.pay(run)
            elif run.kind == "pvp":
                await self.record(run)
        except Exception as e:
            log.error("Couldn't save the result of Bot Arena 3 battle %s", run.id, exc_info=e)

    async def pay(self, run: Run) -> None:
        ((user_id, team),) = run.players.items()
        async with self.lock(user_id):
            group = self.config.user_from_id(user_id)
            data = await group.career()
            if data is None:
                return
            career.finish_arena(data, ARENAS[run.index], run.battle.winner == team)
            await group.career.set(data)
        await self.send_career(user_id, data)

    async def record(self, run: Run) -> None:
        winner = run.battle.winner
        for user_id, team in run.players.items():
            outcome = "draw" if winner == 0 else "win" if winner == team else "loss"
            try:
                async with self.lock(user_id):
                    group = self.config.user_from_id(user_id)
                    # Every PvP player has a career, so none means their data was deleted while the fight ran
                    if await group.career() is None:
                        continue
                    await group.pvp.set(leaderboard.add(await group.pvp(), outcome, run.boards[user_id]))
            except Exception as e:
                log.error("Couldn't save the PvP record of %s for battle %s", user_id, run.id, exc_info=e)

    async def leaderboard(self, ctx, data: dict) -> dict:
        return leaderboard.rank(await self.config.all_users(), ctx.author.id)
