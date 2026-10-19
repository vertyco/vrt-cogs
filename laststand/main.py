import logging
import typing as t
from pathlib import Path

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from .common.saves import SaveError, SaveStore

log = logging.getLogger("red.vrt.laststand")

KEY = "laststand"


class LastStand(commands.Cog):
    """
    The Last Stand: Union City for ActivityHub, ported from the Flash game on Armor Games.

    A side-view zombie survival RPG across Union City, with three save slots per Discord user that the bot keeps.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.store = SaveStore(cog_data_path(self) / "saves")

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.store.delete_user(user_id)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "The Last Stand: Union City",
            "description": "A zombie survival RPG across Union City, with three save slots that follow you everywhere",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"slots": self.slots, "load": self.load, "save": self.save, "wipe": self.wipe},
            "requires": "0.8.0",
        }

    # ---------- Save slots ----------

    async def attempt(self, ctx: t.Any, action: str, call: t.Awaitable[dict]) -> dict:
        """Run a store call, turning a refusal into the plain words the page shows"""
        try:
            return await call
        except SaveError as e:
            log.debug("Refused %s for user %s: %s", action, ctx.author.id, e)
            return {"error": str(e)}

    def written(self, result: tuple[bool, int]) -> dict:
        """A save's or wipe's reply: ok with the slot's new revision, or stale with its revision as it stands when
        another device saved or wiped it first"""
        done, revision = result
        return {"ok": True, "rev": revision} if done else {"stale": True, "rev": revision}

    async def slots(self, ctx: t.Any, data: dict) -> dict:
        summaries, revisions = await self.store.summaries(ctx.author.id)
        return {"slots": summaries, "revs": revisions}

    async def load(self, ctx: t.Any, data: dict) -> dict:
        async def run() -> dict:
            save, revision = await self.store.load(ctx.author.id, data.get("slot"))
            return {"save": save, "rev": revision}

        return await self.attempt(ctx, "load", run())

    async def save(self, ctx: t.Any, data: dict) -> dict:
        async def run() -> dict:
            slot, revision = data.get("slot"), data.get("rev")
            return self.written(await self.store.save(ctx.author.id, slot, data.get("save"), revision))

        return await self.attempt(ctx, "save", run())

    async def wipe(self, ctx: t.Any, data: dict) -> dict:
        async def run() -> dict:
            return self.written(await self.store.wipe(ctx.author.id, data.get("slot"), data.get("rev")))

        return await self.attempt(ctx, "wipe", run())
