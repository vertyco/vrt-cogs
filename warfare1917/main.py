import asyncio
import copy
import logging
import random
import typing as t
import weakref
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common import campaign
from .common.battle import Battle
from .common.lobby import Run, Window
from .common.missions import custom_mission, other_side

log = logging.getLogger("red.vrt.warfare1917")

KEY = "warfare1917"
BUSY = "You already have a battle running."
# Requests for the player's own battle, which the window checks and passes to the battle
BATTLE_REQUESTS = ("deploy", "support", "trench", "masks", "pause", "surrender", "quit", "camera")
# Problems a page reports, logged at most this many per player until the cog reloads, and cut to this length
MOST_REPORTS = 100
REPORT_LENGTH = 1000


class Warfare1917(commands.Cog):
    """
    Warfare 1917 for ActivityHub, ported from the Flash game on Armor Games.

    Lead the British or German army across the trenches of 1917 through two nine-mission campaigns or a Custom Battle,
    and take on other players in a 1 vs 1 or watch their battles.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.3"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101117, force_registration=True)
        self.config.register_user(campaign=None)
        # One window per Activity window, keyed by its instance id
        self.windows: dict[str, Window] = {}
        # One lock per player, so two devices or windows can't interleave changes to one save. A lock nobody holds
        # or waits for is let go, so the map doesn't keep one for every player who ever played
        self.locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()
        # Players whose next campaign battle is a retry after a loss, so it pays no kill XP. Kept in memory like the
        # original's `retry` (F5:7362), so a Red bot restart forgets it
        self.retry: set[int] = set()
        # Result saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # Problems each player's pages have reported, so one page can't flood the log
        self.reports: dict[int, int] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        async with self.lock(user_id):
            await self.config.user_from_id(user_id).clear()
            self.retry.discard(user_id)

    async def cog_unload(self):
        for window in list(self.windows.values()):
            window.stop()
        if self.saving:
            await asyncio.gather(*self.saving, return_exceptions=True)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Warfare 1917",
            "description": "Lead the British or German army across the trenches of 1917",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "web_dir": Path(__file__).parent / "web",
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
            window = Window(
                conn.room,
                self.battle_result,
                self.window_closed,
                self.windows.values,
                self.take_versus,
                self.battle_level,
                self.battle_dismissed,
            )
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
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            save = await self.config.user_from_id(user_id).campaign()
            # A page that connects mid-battle starts from the battle's live XP, as the pages already open do
            run = self.campaign_run(user_id, save)
            if run is not None:
                save = self.live_save(save, run)
            await conn.send({"save": campaign.view(save) if save is not None else None})
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
        window = self.window_for(conn)
        kind, value = next(iter(data.items()))
        handler = self.handlers().get(kind)
        if handler is not None:
            await handler(conn, value)
        elif kind in BATTLE_REQUESTS:
            await window.request(conn, kind, value)

    def handlers(self) -> dict[str, t.Callable[[t.Any, t.Any], t.Awaitable[None]]]:
        return {
            "newCampaign": self.new_campaign,
            "launch": self.launch,
            "buy": self.buy,
            "custom": self.start_custom,
            "watch": self.watch,
            "unwatch": self.unwatch,
            "versus": self.open_versus,
            "cancelVersus": self.cancel_versus,
            "takeVersus": self.take_versus,
            "report": self.report,
        }

    async def report(self, conn: t.Any, value: t.Any) -> None:
        """A problem the page hit on the player's device (an error, the graphics lost, the drawing stopped)"""
        if not isinstance(value, str):
            return
        user_id = conn.ctx.author.id
        count = self.reports.get(user_id, 0)
        if count >= MOST_REPORTS:
            return
        self.reports[user_id] = count + 1
        log.warning("Page problem for player %s: %s", user_id, value[:REPORT_LENGTH])

    # ---------- Campaign ----------

    async def send_save(self, user_id: int, save: dict | None, answer: int | None = None) -> None:
        """The campaign to every page this player has open. `answer` is the upgrade a buy request named, so the page
        knows this save is the reply to it, even a refusal"""
        message: dict[str, t.Any] = {"save": campaign.view(save) if save is not None else None}
        if answer is not None:
            message["answer"] = answer
        for window in list(self.windows.values()):
            for conn in list(window.room.connections):
                if conn.ctx.author.id == user_id:
                    await conn.send(message)

    async def new_campaign(self, conn: t.Any, value: t.Any) -> None:
        """A fresh campaign over the save (the page asked first, F5:171-188)"""
        if value not in ("british", "german"):
            return
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": BUSY})
                return
            save = campaign.new_save(value)
            await self.config.user_from_id(user_id).campaign.set(save)
            # newGame clears the retry flag, F5:421
            self.retry.discard(user_id)
        await self.send_save(user_id, save)

    async def launch(self, conn: t.Any, value: t.Any) -> None:
        """Launch Battle on the campaign map: the save is written as it stands (F5:528), then the mission starts"""
        if value is not True:
            return
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": BUSY})
                return
            self.close_games(user_id)
            group = self.config.user_from_id(user_id)
            save = await group.campaign()
            if save is None:
                await conn.send({"save": None})
                return
            await group.campaign.set(save)
            side = save["side"]
            mission = campaign.mission_for(save)
            battle = Battle(
                mission,
                random.getrandbits(32),
                {side: user_id, other_side(side): None},
                {side: frozenset(save["upgrades"])},
                user_id not in self.retry,
                True,
            )
            battle.level_marks = campaign.level_marks(save)
            names = {side: conn.ctx.author.display_name, other_side(side): None}
            title = f"Mission {mission.number} · {mission.title}"
            await self.window_for(conn).start_run("campaign", battle, {user_id: side}, names, title)

    def campaign_run(self, user_id: int, save: dict | None) -> Run | None:
        """The player's running campaign battle, when `save` is the campaign it belongs to"""
        run = self.running(user_id)
        if run is None or run.kind != "campaign" or save is None:
            return None
        if save["side"] != run.players.get(user_id) or save["mission"] != run.battle.mission.number:
            return None
        return run

    def live_save(self, save: dict, run: Run) -> dict:
        """A copy of the stored `save` with the battle's unpaid kill XP added. Config and `xp_paid` stay as they are"""
        live = copy.deepcopy(save)
        campaign.add_xp(live, run.battle.kill_xp[live["side"]] - run.battle.xp_paid)
        return live

    async def buy(self, conn: t.Any, value: t.Any) -> None:
        """An upgrade bought on the upgrade screen, saved at once (F5:5151-5163). Bought from the battle's HUD, it
        counts in the battle from then on, as the original's upgrade flags do. The battle's kill XP is in the save
        first, so the points it earned can be spent"""
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            group = self.config.user_from_id(user_id)
            save = await group.campaign()
            if save is None:
                return
            run = self.campaign_run(user_id, save)
            if run is not None:
                campaign.pay_xp(save, run.battle)
            bought = campaign.buy(save, value)
            if bought or run is not None:
                await group.campaign.set(save)
            if bought and run is not None:
                own = run.battle.sides[save["side"]]
                own.upgrades = frozenset(save["upgrades"])
                own.retime()
            # Sent either way, so a page that showed a refused buy as bought is put right. Sent inside the lock, so
            # an older save of this player's can't reach the page after it
            answer = value if isinstance(value, int) and not isinstance(value, bool) else None
            await self.send_save(user_id, save, answer)

    async def start_custom(self, conn: t.Any, value: t.Any) -> None:
        """A Custom Battle against the CPU: no XP and no upgrades (spec 3.21)"""
        settings = campaign.check_custom(value, versus=False)
        if settings is None:
            return
        user_id = conn.ctx.author.id
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": BUSY})
                return
            self.close_games(user_id)
            seed = random.getrandbits(32)
            # The mission's mines come from the battle's own generator, so a seed repeats the same battle
            rng = random.Random(seed)
            mission = custom_mission(settings, rng, False)
            side = settings["side"]
            battle = Battle(mission, seed, {side: user_id, other_side(side): None}, {}, True, False, rng=rng)
            names = {side: conn.ctx.author.display_name, other_side(side): None}
            await self.window_for(conn).start_run("custom", battle, {user_id: side}, names, "Custom battle")

    # ---------- Watching and versus ----------

    def close_games(self, user_id: int) -> None:
        """The player's open versus game, in every window, closed: they are about to start a battle of their own"""
        for window in self.windows.values():
            window.cancel(user_id)

    async def watch(self, conn: t.Any, value: t.Any) -> None:
        await self.window_for(conn).watch(conn, value)

    async def unwatch(self, conn: t.Any, value: t.Any) -> None:
        if value is True:
            self.window_for(conn).unwatch(conn)

    async def open_versus(self, conn: t.Any, value: t.Any) -> None:
        """A versus game opened for someone else in the window to take: the Custom Battle's settings with no
        difficulty, and the opener's side"""
        settings = campaign.check_custom(value, versus=True)
        if settings is None:
            return
        user_id = conn.ctx.author.id
        # The lock makes this wait for a Launch Battle or Custom Battle of theirs that is still starting
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": BUSY})
                return
            self.window_for(conn).open_game(conn, settings)

    async def cancel_versus(self, conn: t.Any, value: t.Any) -> None:
        if value is True:
            self.window_for(conn).cancel(conn.ctx.author.id)

    async def take_versus(self, conn: t.Any, value: t.Any) -> None:
        """Takes another player's open game: both sides human, no CPU, no pause, no XP (spec 5, D5)"""
        user_id = conn.ctx.author.id
        window = self.window_for(conn)
        async with self.lock(user_id):
            if self.running(user_id) is not None:
                await conn.send({"notice": BUSY})
                return
            game = window.take_game(value, user_id)
            if game is None:
                return
            settings = game.settings
            side = settings["side"]
            foe = other_side(side)
            seed = random.getrandbits(32)
            rng = random.Random(seed)
            mission = custom_mission(settings, rng, True)
            battle = Battle(mission, seed, {side: game.user_id, foe: user_id}, {}, True, False, rng=rng)
            names = {side: game.name, foe: conn.ctx.author.display_name}
            players = {game.user_id: side, user_id: foe}
            await window.start_run("versus", battle, players, names, "Versus battle")

    # ---------- Results ----------

    def battle_level(self, run: Run) -> None:
        """Called on the step a campaign player's kill XP reaches a level, so the page can show the new upgrade point
        and spend it (updateExperience, F5:6035-6070). The XP isn't saved: in the original it stays in memory until
        saveGame runs on an upgrade purchase (F5:5161) or the next Launch (F5:528)"""
        if run.kind != "campaign":
            return
        task = asyncio.create_task(self.show_level(run))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def show_level(self, run: Run) -> None:
        """The player's pages get the save with the battle's unpaid kill XP added"""
        ((user_id, _),) = run.players.items()
        try:
            async with self.lock(user_id):
                save = await self.config.user_from_id(user_id).campaign()
                if self.campaign_run(user_id, save) is not run:
                    return
                await self.send_save(user_id, self.live_save(save, run))
        except Exception as e:
            log.error("Couldn't send the level of Warfare 1917 battle %s", run.id, exc_info=e)

    def battle_dismissed(self, run: Run) -> None:
        """Called when a battle is gone with no result. Its kill XP was never saved, so the pages get the saved
        campaign back in place of the live one they were showing"""
        if run.kind != "campaign":
            return
        task = asyncio.create_task(self.show_saved(run))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def show_saved(self, run: Run) -> None:
        ((user_id, _),) = run.players.items()
        try:
            async with self.lock(user_id):
                # A battle started since has its own live save to show
                if self.running(user_id) is None:
                    await self.send_save(user_id, await self.config.user_from_id(user_id).campaign())
        except Exception as e:
            log.error("Couldn't send the saved campaign after Warfare 1917 battle %s", run.id, exc_info=e)

    def battle_result(self, run: Run) -> None:
        """Called on the step a battle ends. Only a campaign battle changes a save; it is saved off the battle loop,
        so Config never slows a battle"""
        if run.kind != "campaign":
            return
        task = asyncio.create_task(self.save_result(run))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def save_result(self, run: Run) -> None:
        """A campaign battle's XP, career counts and next mission, saved for the campaign map (F5:4326-4338, 528)"""
        ((user_id, side),) = run.players.items()
        battle = run.battle
        try:
            async with self.lock(user_id):
                group = self.config.user_from_id(user_id)
                save = await group.campaign()
                # None when their data was deleted while the battle ran
                if save is None or save["side"] != side or save["mission"] != battle.mission.number:
                    return
                changed = campaign.apply_result(save, battle, battle.first_try)
                await group.campaign.set(save)
                if changed["retry"]:
                    self.retry.add(user_id)
                else:
                    self.retry.discard(user_id)
                # Sent inside the lock, like buy, so an upgrade bought meanwhile can't have its answer overtaken
                await self.send_save(user_id, save)
        except Exception as e:
            log.error("Couldn't save the result of Warfare 1917 battle %s", run.id, exc_info=e)
