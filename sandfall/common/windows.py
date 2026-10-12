"""
Everything Sandfall keeps for one Activity window: who is connected, and the shared worlds open in it.

`Window.handle` takes each message a page sends (one JSON object with a "t" field) and answers or passes it to the
shared world the player sits in. Every player starts in their own private world, which lives on their page only.
"""

import asyncio
import logging
import re
import secrets
import typing as t

from .shared import GRACE_SECONDS, MAX_PLAYERS, SharedWorld
from .strokes import check_stroke
from .worldfile import ELEMENT_COUNT, H, W, check_world

log = logging.getLogger("red.vrt.sandfall.windows")

WORLD_ID = re.compile(r"[0-9a-f]{6}")
HASH = re.compile(r"[0-9a-f]{8}")
PNG_PREFIX = "data:image/png;base64,"
MAX_PIC = 20 * 1024
FULL = f"That world is full ({MAX_PLAYERS} players)."


def whole(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def batch_number(value: object) -> int | None:
    if isinstance(value, int) and whole(value, 0, 2**53):
        return value
    return None


def world_id(value: object) -> str | None:
    return value if isinstance(value, str) and WORLD_ID.fullmatch(value) else None


def user_id(value: object) -> int | None:
    """A user id the page sent as text"""
    return int(value) if isinstance(value, str) and value.isdigit() and len(value) < 21 else None


def cursor_fits(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    x, y, size, element = value
    return whole(x, 0, W - 1) and whole(y, 0, H - 1) and whole(size, 1, 40) and whole(element, 0, ELEMENT_COUNT - 1)


class Window:
    def __init__(self, instance_id: str, forget: t.Callable[["Window"], None], clock: t.Callable[[], float]):
        """`forget(window)` is called once nobody is connected and no world is open, so the cog can drop it"""
        self.instance_id = instance_id
        self.forget = forget
        self.clock = clock
        self.worlds: dict[str, SharedWorld] = {}
        # Each player's newest connection, by user id
        self.conns: dict[int, t.Any] = {}
        # Players waiting for a world that isn't open again yet after a restart: world id to {user id: (b, since)}
        self.expecting: dict[str, dict[int, tuple[int | None, float]]] = {}
        self.handlers = {
            "open": self.open,
            "enter": self.enter,
            "ask": self.ask,
            "exit": self.exit,
            "close": self.close,
            "s": self.stroke,
            "cur": self.cursor,
            "snap": self.snapshot,
            "hash": self.fingerprint,
            "behind": self.behind,
            "speed": self.speed,
            "once": self.once,
            "load": self.load,
            "pic": self.picture,
        }
        # Messages that only make sense from a seated player, handed the world they sit in
        self.member_only = {"exit", "close", "s", "cur", "snap", "hash", "behind", "speed", "once", "load", "pic"}

    def stop(self) -> None:
        for world in self.worlds.values():
            world.stop()
        self.worlds.clear()

    # Connections

    async def join(self, conn: t.Any) -> None:
        uid = conn.ctx.author.id
        self.conns[uid] = conn
        await conn.send({"hello": {"you": str(uid), "worlds": self.summaries()}})
        follow = getattr(conn, "follow", None)
        if follow is None:
            return
        world = self.seated_world(follow)
        if world is not None and world.full:
            await conn.send({"note": FULL})
        elif world is not None:
            await conn.send({"follow": {"world": world.id}})
        elif follow in self.conns:
            name = self.conns[follow].ctx.author.display_name
            await conn.send({"follow": {"private": {"id": str(follow), "name": name}}})

    async def leave(self, conn: t.Any) -> None:
        uid = conn.ctx.author.id
        if self.conns.get(uid) is conn:
            del self.conns[uid]
        world = self.seated_world(uid)
        if world is not None and world.drop(uid, conn):
            if world.asked == uid:
                world.asked = None
                await world.ask_supplier(skip=uid)
            await world.changed()
        self.forget_if_empty()

    def forget_if_empty(self) -> None:
        if not self.conns and not self.worlds:
            self.forget(self)

    # Lists the window sees

    def summaries(self) -> list[dict]:
        return [world.summary() for world in self.worlds.values()]

    async def send_window(self, data: dict) -> None:
        for conn in list(self.conns.values()):
            await conn.send(data)

    async def send_worlds(self) -> None:
        await self.send_window({"worlds": self.summaries()})

    async def world_ended(self, world: SharedWorld) -> None:
        if self.worlds.get(world.id) is world:
            del self.worlds[world.id]
            await self.send_worlds()
        self.forget_if_empty()

    def seated_world(self, uid: int) -> SharedWorld | None:
        return next((world for world in self.worlds.values() if uid in world.members), None)

    def owned_world(self, uid: int) -> SharedWorld | None:
        return next((world for world in self.worlds.values() if world.owner == uid), None)

    # Messages

    async def handle(self, conn: t.Any, data: object) -> None:
        if not isinstance(data, dict):
            return
        handler = self.handlers.get(data.get("t"))
        if handler is None:
            return
        uid = conn.ctx.author.id
        if data["t"] not in self.member_only:
            await handler(conn, uid, data)
            return
        world = self.seated_world(uid)
        # A message from an old connection whose player already came back on a new one is ignored
        if world is not None and world.members[uid].conn is conn:
            await handler(world, uid, data)

    async def leave_seat(self, uid: int) -> None:
        """Takes a player out of any shared world and forgets any world they were waiting for"""
        for waiting in self.expecting.values():
            waiting.pop(uid, None)
        world = self.seated_world(uid)
        if world is not None:
            await world.unseat(uid)

    async def open(self, conn: t.Any, uid: int, data: dict) -> None:
        """Opens the player's world to friends, reopens it after a restart, or seats a player they invite"""
        invite = user_id(data.get("invite"))
        reopen = world_id(data.get("id"))
        b = batch_number(data.get("b"))
        existing = self.worlds.get(reopen) if reopen else None
        if existing is not None and uid in existing.members:
            # The connection dropped but the world carried on without them (the owner too): they take their seat
            # back and get a `world` that brings their screen into step
            await existing.seat(uid, conn, since=b)
            if invite is not None:
                await self.invite(existing, invite, conn)
            return
        owned = self.owned_world(uid)
        if owned is not None:
            if invite is not None:
                await self.invite(owned, invite, conn)
            return
        try:
            await asyncio.to_thread(check_world, data.get("snap"))
        except ValueError as e:
            await conn.send({"note": str(e)})
            return
        if self.owned_world(uid) is not None or self.conns.get(uid) is not conn:
            return
        await self.leave_seat(uid)
        world = self.make_world(uid, reopen, b, data.get("speed"))
        world.add_member(uid, conn)
        world.start()
        await conn.send({"opened": {"id": world.id, "b": world.batch - 1}})
        await self.seat_expected(world)
        if invite is not None:
            await self.invite(world, invite, conn)
        await world.changed()

    def make_world(self, uid: int, reopen: str | None, b: int | None, speed: object) -> SharedWorld:
        """A new shared world. A reopen keeps its id when nobody took it, and its batches go on after the page's"""
        wid = reopen if reopen and reopen not in self.worlds else None
        while wid is None or wid in self.worlds:
            wid = secrets.token_hex(3)
        speed = speed if whole(speed, 0, 4) else 3
        world = SharedWorld(self, wid, uid, 0 if b is None else b + 1, speed)
        self.worlds[wid] = world
        return world

    async def seat_expected(self, world: SharedWorld) -> None:
        """Seats the players who tried to enter this world before its owner reopened it"""
        now = self.clock()
        for uid, (b, since) in self.expecting.pop(world.id, {}).items():
            conn = self.conns.get(uid)
            if conn is None or now - since > GRACE_SECONDS or self.seated_world(uid) is not None:
                continue
            await world.seat(uid, conn, since=b)

    async def invite(self, world: SharedWorld, invitee: int, conn: t.Any) -> None:
        guest = self.conns.get(invitee)
        if guest is None or invitee in world.members:
            return
        if world.full:
            await conn.send({"note": FULL})
            return
        await self.leave_seat(invitee)
        await world.seat(invitee, guest)

    async def enter(self, conn: t.Any, uid: int, data: dict) -> None:
        wid = world_id(data.get("id"))
        b = batch_number(data.get("b"))
        world = self.worlds.get(wid) if wid else None
        if world is None:
            if wid is not None:
                # Remembered so the owner's reopen after a restart seats them
                self.expecting.setdefault(wid, {})[uid] = (b, self.clock())
                await conn.send({"waiting": wid})
            return
        if uid not in world.members:
            if world.full:
                # The page has already left the world it sat in and switched into this one, so its old seat goes
                # (handing that world on if it owned it) and the page is told to come back
                await self.leave_seat(uid)
                await conn.send({"full": {"id": wid, "note": FULL}})
                return
            await self.leave_seat(uid)
        await world.seat(uid, conn, since=b)

    async def ask(self, conn: t.Any, uid: int, data: dict) -> None:
        target = self.conns.get(user_id(data.get("to")))
        if target is not None and target is not conn:
            await target.send({"asked": {"id": str(uid), "name": conn.ctx.author.display_name}})

    async def exit(self, world: SharedWorld, uid: int, data: dict) -> None:  # noqa: ARG002
        await world.unseat(uid)

    async def close(self, world: SharedWorld, uid: int, data: dict) -> None:  # noqa: ARG002
        if uid != world.owner:
            return
        await world.send_present({"closed": {"name": world.name, "by": world.name}}, but=uid)
        await world.end()

    async def stroke(self, world: SharedWorld, uid: int, data: dict) -> None:
        stroke = check_stroke(data.get("k"))
        if stroke is not None:
            world.add_stroke(uid, stroke)

    async def cursor(self, world: SharedWorld, uid: int, data: dict) -> None:
        if cursor_fits(data.get("c")):
            await world.send_present({"cur": [str(uid), *data["c"]]}, but=uid)

    async def snapshot(self, world: SharedWorld, uid: int, data: dict) -> None:
        if uid != world.asked:
            return
        try:
            await asyncio.to_thread(check_world, data.get("snap"))
        except ValueError as e:
            log.warning("Sandfall world %s: player %s sent a snapshot that didn't check out", world.id, uid, exc_info=e)
            await world.bad_snapshot(uid)
            return
        await world.got_snapshot(uid, data.get("b"), data["snap"])

    async def fingerprint(self, world: SharedWorld, uid: int, data: dict) -> None:
        b, h = batch_number(data.get("b")), data.get("h")
        if b is not None and isinstance(h, str) and HASH.fullmatch(h):
            await world.fingerprint(uid, b, h)

    async def behind(self, world: SharedWorld, uid: int, data: dict) -> None:  # noqa: ARG002
        await world.want_snapshot(uid)

    async def speed(self, world: SharedWorld, uid: int, data: dict) -> None:
        if uid == world.owner and whole(data.get("v"), 0, 4):
            await world.set_speed(data["v"])

    async def once(self, world: SharedWorld, uid: int, data: dict) -> None:  # noqa: ARG002
        if uid == world.owner:
            world.step_once()

    async def load(self, world: SharedWorld, uid: int, data: dict) -> None:
        if uid != world.owner:
            return
        try:
            await asyncio.to_thread(check_world, data.get("snap"))
        except ValueError as e:
            await world.members[uid].conn.send({"note": str(e)})
            return
        if not world.closed:
            await world.load(data["snap"])

    async def picture(self, world: SharedWorld, uid: int, data: dict) -> None:
        png = data.get("png")
        if uid == world.owner and isinstance(png, str) and png.startswith(PNG_PREFIX) and len(png) <= MAX_PIC:
            await self.send_window({"pic": [world.id, png]})
