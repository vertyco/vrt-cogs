"""The live connection: ActivityHub's join, message and leave handlers. Only exact message shapes count"""

import logging

from redbot.core.i18n import Translator

from ..abc import MixinMeta
from .catalog import GAMES
from .info import casino_info, me
from .perms import can_manage
from .rounds import AllInTable, BlackjackTable
from .table import Closed, Floor

_ = Translator("Casino", __file__)

log = logging.getLogger("red.vrt.casino.sockets")

NOT_IN_A_SERVER = 4100
NOT_READY = 4101


class Sockets(MixinMeta):
    def floor_for(self, conn) -> Floor:
        """The window's floor, made when its first player arrives"""
        floor = self.floors.get(conn.ctx.instance_id)
        if floor is None:
            floor = Floor(self, conn.room, conn.ctx.guild)
            self.floors[conn.ctx.instance_id] = floor
        elif floor.room is not conn.room:
            # Reloading ActivityHub gives the window a new room, while the floor keeps its running rounds
            floor.room = conn.room
        return floor

    async def hello(self, ctx) -> dict:
        scope = await self.store.scope_for(ctx.guild.id)
        global_mode = await self.store.global_mode()
        return {
            "t": "hello",
            "me": await me(self.store, self.money, scope, ctx.author),
            "casino": await casino_info(self.store, scope),
            "currency": await self.bank.currency(ctx.guild),
            "can_manage": await can_manage(self.bot, ctx.author, global_mode),
            "owner": await self.bot.is_owner(ctx.author),
        }

    async def join(self, ctx, conn) -> None:
        if ctx.guild is None:
            await conn.send({"t": "notice", "text": _("Open the casino in a server.")})
            await conn.close(NOT_IN_A_SERVER)
            return
        if not self.ready.is_set():
            await conn.send({"t": "notice", "text": _("The casino is still opening. Try again in a moment.")})
            await conn.close(NOT_READY)
            return
        greeting = await self.hello(ctx)
        # No await between this check and the floor's creation, so a floor can't appear once unloading began
        if not self.ready.is_set():
            await conn.send({"t": "notice", "text": _("The casino is still opening. Try again in a moment.")})
            await conn.close(NOT_READY)
            return
        floor = self.floor_for(conn)
        await conn.send(greeting)
        await floor.arrive(conn)

    async def message(self, ctx, conn, data) -> None:
        floor = self.floors.get(ctx.instance_id)
        if not self.ready.is_set() or not isinstance(data, dict) or floor is None or conn not in floor.where:
            return
        try:
            await self.dispatch(floor, conn, data)
        except Closed as e:
            log.debug("Ignored a message to a closing floor: %r", e)

    async def dispatch(self, floor: Floor, conn, data: dict) -> None:
        kind = data.get("t")
        if kind == "enter" and data.get("game") in GAMES:
            await floor.enter(conn, data["game"])
            return
        if kind == "lobby":
            await floor.to_lobby(conn)
            return
        game = floor.where.get(conn)
        if game is None:
            return
        table = floor.table(game)
        solo = isinstance(table, AllInTable)
        if kind == ("pull" if solo else "bet"):
            await table.bet(conn, data)
        elif kind == "go":
            await table.press_go(conn)
        elif kind == "move":
            await table.move(conn, data)
        elif isinstance(table, BlackjackTable) and kind in ("sit", "stand"):
            await (table.sit(conn, data.get("seat")) if kind == "sit" else table.stand(conn))

    async def leave(self, ctx, conn) -> None:
        floor = self.floors.get(ctx.instance_id)
        if floor is None:
            return
        await floor.depart(conn)
        self.floor_done(floor)
