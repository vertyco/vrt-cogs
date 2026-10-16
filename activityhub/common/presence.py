"""Who's here: everyone in each Activity window, where they are in the hub, and what their game says they're doing"""

import asyncio
import logging
import re
import typing as t
from dataclasses import dataclass, field

from .playlog import PlayLog
from .replies import dumps
from .sessions import ActivityContext
from .sockets import Connection

log = logging.getLogger("red.vrt.activityhub.presence")

STATUS_MAX = 60
DATA_MAX = 1024
# A person whose last menu link dropped stays listed this long, marked away, so a reconnect doesn't flicker them out
GRACE_SECONDS = 15
# Each window's list goes out at most this often. Changes in between are merged into the next one
SEND_EVERY = 0.25
FIELDS = {"where", "status", "data", "busy", "away", "platform"}
# What Discord calls the two kinds of device, in the Activity's address
PLATFORMS = {"desktop", "mobile"}
# Control characters, and the lone halves of an emoji (surrogates) that a page cut in two, which can't be sent on
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")


def clean_status(value: t.Any) -> str:
    if not isinstance(value, str):
        return ""
    return CONTROL.sub("", value).strip()[:STATUS_MAX]


def clean_data(value: t.Any) -> t.Any:
    """The page's data for its own game, or None when it can't be sent on or is too big to pass around"""
    try:
        text = dumps(value)
    except (TypeError, ValueError) as e:
        log.debug("Dropped status data that can't be sent on: %s", e)
        return None
    return value if len(text) <= DATA_MAX else None


def clean_platform(value: t.Any) -> str:
    """Phone or computer as Discord says it, or empty for anything else. A list or dict can't be looked up in a set"""
    return value if isinstance(value, str) and value in PLATFORMS else ""


@dataclass
class Person:
    member: t.Any
    # Their place in the window's arrival order
    arrived: int
    links: list[Connection] = field(default_factory=list)
    where: str | None = None
    status: str = ""
    data: t.Any = None
    busy: bool = False
    away: bool = False
    # Phone or computer, for the play log only. Never in view(), so nobody else sees it
    platform: str = ""
    # Takes them off the list once the grace after their last link dropped is over
    leaving: asyncio.Task | None = None

    def view(self) -> dict:
        return {
            "id": str(self.member.id),
            "name": self.member.display_name,
            "avatar": self.member.display_avatar.url,
            "game": self.where,
            "status": self.status,
            "data": self.data,
            "busy": self.busy,
            # Someone whose link dropped is shown away until they're back or the grace is over
            "away": self.away or not self.links,
        }


@dataclass
class Window:
    instance_id: str
    guild_id: int | None
    people: dict[int, Person] = field(default_factory=dict)
    arrivals: int = 0
    sent_at: float = float("-inf")
    sender: asyncio.Task | None = None

    def links(self) -> list[Connection]:
        return [conn for person in self.people.values() for conn in person.links]


class Presence:
    """The people list of every window, kept up to date by each player's menu link"""

    def __init__(self, game_on: t.Callable[[int | None, str], t.Awaitable[bool]], playlog: PlayLog):
        # Whether a game is installed and on in a server, so a page can't claim to be somewhere it can't be
        self.game_on = game_on
        self.playlog = playlog
        self.windows: dict[str, Window] = {}

    def links(self) -> list[Connection]:
        return [conn for window in self.windows.values() for conn in window.links()]

    async def connect(self, conn: Connection) -> None:
        ctx = conn.ctx
        window = self.windows.get(ctx.instance_id)
        if window is None:
            window = Window(ctx.instance_id, ctx.guild_id)
            self.windows[ctx.instance_id] = window
        person = window.people.get(ctx.author.id)
        if person is None:
            window.arrivals += 1
            person = Person(ctx.author, window.arrivals)
            window.people[ctx.author.id] = person
        elif person.leaving is not None:
            person.leaving.cancel()
            person.leaving = None
        person.member = ctx.author
        person.links.append(conn)
        self.log_play(window, person)
        self.changed(window)

    def find(self, conn: Connection) -> tuple[Window, Person] | None:
        window = self.windows.get(conn.ctx.instance_id)
        person = window.people.get(conn.ctx.author.id) if window else None
        if window is None or person is None or conn not in person.links:
            return None
        return window, person

    async def update(self, conn: Connection, data: t.Any) -> None:
        """The page's whole state for its player, cleaned before anyone else sees it"""
        if not isinstance(data, dict) or not set(data) <= FIELDS:
            log.debug("Ignored a menu link message from %s: %r", conn.ctx.author.id, data)
            return
        found = self.find(conn)
        if found is None:
            return
        window, person = found
        person.platform = clean_platform(data.get("platform"))
        where = await self.clean_where(conn.ctx, data.get("where"))
        state = (where, clean_status(data.get("status")), data.get("busy") is True, data.get("away") is True)
        new_data = clean_data(data.get("data"))
        # A message that changes nothing sends no list, which would go to everyone in the window. Data is compared
        # as JSON, where 1 and true differ
        if state == (person.where, person.status, person.busy, person.away) and dumps(new_data) == dumps(person.data):
            return
        moved = where != person.where
        person.where, person.status, person.busy, person.away = state
        person.data = new_data
        self.log_play(window, person)
        self.changed(window, moved)

    async def clean_where(self, ctx: ActivityContext, value: t.Any) -> str | None:
        if not isinstance(value, str) or not await self.game_on(ctx.guild_id, value):
            return None
        return value

    def disconnect(self, conn: Connection) -> None:
        found = self.find(conn)
        if found is None:
            return
        window, person = found
        person.links.remove(conn)
        self.log_play(window, person)
        if not person.links:
            person.leaving = asyncio.create_task(self.forget(window, person))
        self.changed(window)

    async def forget(self, window: Window, person: Person) -> None:
        await asyncio.sleep(GRACE_SECONDS)
        person.leaving = None
        if person.links or window.people.get(person.member.id) is not person:
            return
        del window.people[person.member.id]
        self.playlog.end((window.instance_id, person.member.id))
        if not window.people and self.windows.get(window.instance_id) is window:
            del self.windows[window.instance_id]
        self.changed(window, person.where is not None)

    def log_play(self, window: Window, person: Person) -> None:
        """Tell the play log where the person is, and whether their play's clock runs: in a game, linked, not away"""
        running = bool(person.links) and not person.away
        key = (window.instance_id, person.member.id)
        self.playlog.sync(key, window.guild_id, person.member.id, person.where, person.platform, running)

    def follow_target(self, ctx: ActivityContext, value: t.Any) -> int | None:
        """The user id a game connection's follow names, when that person is someone else in the same window"""
        # Discord ids are at most 20 digits. isdigit() alone also accepts characters int() refuses, like "²"
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 20:
            return None
        user_id = int(value)
        window = self.windows.get(ctx.instance_id)
        if window is None or user_id not in window.people or user_id == ctx.author.id:
            return None
        return user_id

    def changed(self, window: Window, moved: bool = False) -> None:
        """Send this window's list soon. A move also changes the other-channel counts of the server's other windows"""
        self.schedule(window)
        if moved and window.guild_id is not None:
            for other in self.windows.values():
                if other is not window and other.guild_id == window.guild_id:
                    self.schedule(other)

    def schedule(self, window: Window) -> None:
        # A window that was dropped, or cleared by stop, has nobody left to send to
        if self.windows.get(window.instance_id) is not window:
            return
        if window.sender is None or window.sender.done():
            window.sender = asyncio.create_task(self.send_soon(window))

    async def send_soon(self, window: Window) -> None:
        loop = asyncio.get_running_loop()
        wait = window.sent_at + SEND_EVERY - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        window.sent_at = loop.time()
        try:
            text = dumps(self.snapshot(window))
        except Exception as e:
            # Left alone, the task would fail with nobody told, and every later list for this window would too
            log.error("Couldn't build the people list of window %s: %s", window.instance_id, e, exc_info=e)
            return
        for conn in window.links():
            conn.queue_text(text)

    def snapshot(self, window: Window) -> dict:
        people = sorted(window.people.values(), key=lambda person: person.arrived)
        return {"people": [person.view() for person in people], "elsewhere": self.elsewhere(window)}

    def elsewhere(self, window: Window) -> dict[str, int]:
        """How many people play each game in the server's other windows. Nothing outside a server"""
        counts: dict[str, int] = {}
        if window.guild_id is None:
            return counts
        for other in self.windows.values():
            if other is window or other.guild_id != window.guild_id:
                continue
            for person in other.people.values():
                if person.where is not None:
                    counts[person.where] = counts.get(person.where, 0) + 1
        return counts

    def stop(self) -> None:
        """End every open play, and cancel every pending send and grace, for a server shutting down"""
        self.playlog.end_all()
        for window in self.windows.values():
            if window.sender is not None:
                window.sender.cancel()
            for person in window.people.values():
                if person.leaving is not None:
                    person.leaving.cancel()
        self.windows.clear()
