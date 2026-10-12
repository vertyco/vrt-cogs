import asyncio
import logging
import time
from pathlib import Path

from aiohttp import web
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from .common.gallery import Gallery
from .common.storage import Storage
from .common.windows import Window
from .common.worldfile import check_world, to_text

log = logging.getLogger("red.vrt.sandfall")

KEY = "sandfall"


class Sandfall(commands.Cog):
    """
    A falling-sand sandbox for ActivityHub.

    Paint sand, water, fire and fifty more materials into a small world and watch them fall, flow and burn. Worlds
    save themselves, friends can paint in the same world, and each server has a gallery.
    """

    __author__ = "Vertyco"
    __version__ = "0.2.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101101, force_registration=True)
        self.config.register_guild(gallery={})
        self.storage = Storage(cog_data_path(self))
        self.gallery = Gallery(self.config, self.storage)
        # Each Activity window's connections and shared worlds, by instance id
        self.windows: dict[str, Window] = {}
        self.clock = time.monotonic

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.storage.delete_private(user_id)
        await self.gallery.forget_user(user_id)

    async def cog_unload(self):
        self.stop_all()

    def stop_all(self) -> None:
        """Stops every shared world's clock and forgets every window"""
        for window in self.windows.values():
            window.stop()
        self.windows.clear()

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Sandfall",
            "description": "Paint sand, water, fire and fifty more, and watch them fall, flow and burn",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "actions": {
                "load_world": self.load_world,
                "save_world": self.save_world,
                "gallery": self.gallery_list,
                "gallery_save": self.gallery_save,
                "gallery_load": self.gallery_load,
                "like": self.like,
                "delete": self.delete,
            },
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "routes": {"GET thumb": self.thumb},
            "requires": "0.8.0",
        }

    def forget_window(self, window: Window) -> None:
        if self.windows.get(window.instance_id) is window:
            del self.windows[window.instance_id]

    async def join(self, ctx, conn) -> None:
        window = self.windows.get(ctx.instance_id)
        if window is None:
            window = Window(ctx.instance_id, self.forget_window, self.clock)
            self.windows[ctx.instance_id] = window
        await window.join(conn)

    async def message(self, ctx, conn, data) -> None:
        window = self.windows.get(ctx.instance_id)
        if window is not None:
            await window.handle(conn, data)

    async def leave(self, ctx, conn) -> None:
        # After an unload, leave runs for every player with the windows already forgotten
        window = self.windows.get(ctx.instance_id)
        if window is not None:
            await window.leave(conn)

    async def load_world(self, ctx, data: dict) -> dict:
        stored = await self.storage.read_private(ctx.author.id)
        return {"snap": None if stored is None else to_text(stored)}

    async def save_world(self, ctx, data: dict) -> dict:
        try:
            stored = await asyncio.to_thread(check_world, data.get("snap"))
        except ValueError as e:
            return {"error": str(e)}
        await self.storage.write_private(ctx.author.id, stored)
        return {"ok": True}

    async def gallery_list(self, ctx, data: dict) -> dict:
        return await self.gallery.list(ctx, data.get("sort"))

    async def gallery_save(self, ctx, data: dict) -> dict:
        return await self.gallery.save(ctx, data.get("name"), data.get("snap"), data.get("png"))

    async def gallery_load(self, ctx, data: dict) -> dict:
        return await self.gallery.load(ctx, data.get("id"))

    async def like(self, ctx, data: dict) -> dict:
        return await self.gallery.like(ctx, data.get("id"))

    async def delete(self, ctx, data: dict) -> dict:
        return await self.gallery.delete(ctx, data.get("id"))

    async def thumb(self, ctx, request: web.Request) -> web.Response:
        if ctx is None:
            return web.json_response({"error": "Open this from Discord first."}, status=401)
        png = await self.gallery.picture(ctx, request.query.get("id"))
        if png is None:
            return web.json_response({"error": "That picture isn't there."}, status=404)
        return web.Response(body=png, content_type="image/png")
