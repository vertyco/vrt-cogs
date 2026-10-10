import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
import typing as t

import discord
from aiohttp import web

from activityhub.bundled.scores import ScoreBoard
from activityhub.common.games import GameRegistry
from activityhub.common.sessions import ActivityContext, LaunchMemory, SessionStore

APP_ID = 1000
OWNER_ID = 1
MEMBER_ID = 2
MANAGER_ID = 3
ADMIN_ID = 4
OUTSIDER_ID = 5  # a Discord user who isn't in the test server
GUILD_ID = 500
UNKNOWN_GUILD_ID = 600  # a server the bot isn't in
GUILD_OWNER_ID = 6  # owns the test server, with no Manage Server role permission or Red admin role


def not_found(what: str) -> discord.NotFound:
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), f"Unknown {what}")


class FakeValue:
    def __init__(self, data: dict, name: str):
        self.data = data
        self.name = name

    def __call__(self):
        return self.read()

    async def read(self):
        return copy.deepcopy(self.data[self.name])

    async def set(self, value):
        self.data[self.name] = copy.deepcopy(value)


class FakeGroup:
    def __init__(self, data: dict):
        self.data = data

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return FakeValue(self.data, name)

    async def all(self):
        return copy.deepcopy(self.data)


class FakeConfig:
    """Dict-backed stand-in for Red's Config with ActivityHub's defaults"""

    def __init__(self):
        self.globals = {"host": "127.0.0.1", "port": 8742, "look": {}, "disabled": []}
        self.guilds: dict[int, dict] = {}
        self.users: dict[int, dict] = {}
        self.members: dict[int, dict[int, dict]] = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return FakeValue(self.globals, name)

    def guild_from_id(self, guild_id: int) -> FakeGroup:
        return FakeGroup(self.guilds.setdefault(guild_id, {"look": {}, "disabled": []}))

    def guild(self, guild) -> FakeGroup:
        return self.guild_from_id(guild.id)

    def user_from_id(self, user_id: int) -> FakeGroup:
        return FakeGroup(self.users.setdefault(user_id, {"look": {}, "order": []}))

    def user(self, user) -> FakeGroup:
        return self.user_from_id(user.id)

    def member_from_ids(self, guild_id: int, user_id: int) -> FakeGroup:
        return FakeGroup(self.members.setdefault(guild_id, {}).setdefault(user_id, {"best": {}}))

    def member(self, member) -> FakeGroup:
        return self.member_from_ids(member.guild.id, member.id)

    async def all_members(self, guild=None) -> dict:
        if guild is None:
            return copy.deepcopy(self.members)
        return copy.deepcopy(self.members.get(guild.id, {}))


def fake_user(user_id: int, name: str) -> SimpleNamespace:
    avatar = SimpleNamespace(url=f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png")
    # A user with no display name of their own, so Discord shows the username
    return SimpleNamespace(id=user_id, name=name, display_name=name, global_name=None, display_avatar=avatar)


def fake_member(user: SimpleNamespace, guild: "FakeGuild", manage: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=user.id,
        name=user.name,
        display_name=user.name.title(),
        global_name=user.global_name,
        display_avatar=user.display_avatar,
        guild=guild,
        guild_permissions=SimpleNamespace(manage_guild=manage),
    )


class FakeGuild:
    def __init__(self, guild_id: int, name: str):
        self.id = guild_id
        self.name = name
        self.icon = None
        self.owner_id = GUILD_OWNER_ID
        self.members: dict[int, SimpleNamespace] = {}

    def get_member(self, user_id: int):
        return self.members.get(user_id)

    async def fetch_member(self, user_id: int):
        if user_id not in self.members:
            raise not_found("Member")
        return self.members[user_id]


class FakeBot:
    def __init__(self):
        self.application_id = APP_ID
        self.users = {
            user_id: fake_user(user_id, name)
            for user_id, name in [
                (OWNER_ID, "owner"),
                (MEMBER_ID, "member"),
                (MANAGER_ID, "manager"),
                (ADMIN_ID, "admin"),
                (OUTSIDER_ID, "outsider"),
                (GUILD_OWNER_ID, "guildowner"),
            ]
        }
        guild = FakeGuild(GUILD_ID, "Test Server")
        for user_id in (OWNER_ID, MEMBER_ID, ADMIN_ID, GUILD_OWNER_ID):
            guild.members[user_id] = fake_member(self.users[user_id], guild)
        guild.members[MANAGER_ID] = fake_member(self.users[MANAGER_ID], guild, manage=True)
        self.guilds = {GUILD_ID: guild}
        self.admins = {ADMIN_ID}  # members holding Red's admin role
        self.tokens = {"client_secret": "secret"}

    def get_user(self, user_id: int):
        return self.users.get(user_id)

    async def fetch_user(self, user_id: int):
        if user_id not in self.users:
            raise not_found("User")
        return self.users[user_id]

    def get_guild(self, guild_id: int):
        return self.guilds.get(guild_id)

    async def is_owner(self, user) -> bool:
        return user.id == OWNER_ID

    async def is_admin(self, member) -> bool:
        return member.id in self.admins

    async def get_shared_api_tokens(self, service: str) -> dict:
        return dict(self.tokens) if service == "activityhub" else {}


def make_hub() -> SimpleNamespace:
    config = FakeConfig()
    return SimpleNamespace(
        bot=FakeBot(),
        config=config,
        registry=GameRegistry(),
        sessions=SessionStore(),
        launches=LaunchMemory(),
        scores=ScoreBoard(config),
    )


def context_for(
    hub, user_id: int = MEMBER_ID, guild_id: int | None = GUILD_ID, instance_id: str = "i-1"
) -> ActivityContext:
    user = hub.bot.get_user(user_id)
    guild = hub.bot.get_guild(guild_id) if guild_id else None
    member = guild.get_member(user_id) if guild else None
    return ActivityContext(author=member or user, guild=guild, channel_id=77, instance_id=instance_id)


def session_headers(hub, **kwargs) -> dict:
    return {"Authorization": f"Bearer {hub.sessions.create(context_for(hub, **kwargs))}"}


DEMO_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Demo</title>
  </head>
  <body>
    <button id="back" type="button">Back</button>
    <p id="status">loading</p>
    <script type="module" src="game.js"></script>
  </body>
</html>
"""

# Used by the browser tests: logs in through sdk.js, calls an action, opens the live connection
DEMO_JS = """import { connect, backToMenu } from "activityhub";

document.getElementById("back").addEventListener("click", backToMenu);
window.demo = { done: false, messages: [] };
try {
  const hub = await connect();
  window.demo.offline = hub.offline;
  window.demo.player = hub.player;
  if (!hub.offline) {
    window.demo.echo = await hub.api("echo", { n: 1 });
    const conn = await hub.socket();
    conn.on((data) => window.demo.messages.push(data));
    conn.send({ ping: 1 });
  }
} catch (e) {
  window.demo.error = e.message;
}
window.demo.done = true;
document.getElementById("status").textContent = "done";
"""

DEMO_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8" fill="#5865F2"/></svg>'
)
DEMO_THUMBNAIL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect width="16" height="9" fill="#ED4245"/>'
    '<circle cx="8" cy="4.5" r="3" fill="#FEE75C"/></svg>'
)


def register(hub, cog) -> t.Any:
    """Register a game from synchronous test code, where no event loop is running"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(hub.registry.add(cog))
    finally:
        loop.close()


def write_demo_web(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(DEMO_INDEX, encoding="utf-8")
    (folder / "game.js").write_text(DEMO_JS, encoding="utf-8")
    (folder / "icon.svg").write_text(DEMO_ICON, encoding="utf-8")
    (folder / "thumb.svg").write_text(DEMO_THUMBNAIL, encoding="utf-8")
    return folder


class DemoCog:
    """A game cog using every hook, recording what the hub hands it"""

    def __init__(self, web_dir: Path, key="demo", name="Demo", cog_name="Demo", with_socket=True, thumbnail=None):
        self.qualified_name = cog_name
        self.web_dir = web_dir
        self.key = key
        self.name = name
        self.with_socket = with_socket
        self.thumbnail = thumbnail
        self.events: list[tuple] = []
        self.join_error = False
        self.result: t.Any = None  # what the "give" action returns

    async def activityhub_game(self) -> dict:
        desc = {
            "key": self.key,
            "name": self.name,
            "description": f"{self.name} for tests",
            "icon": "icon.svg",
            "web_dir": self.web_dir,
            "actions": {
                "echo": self.echo,
                "none": self.give_none,
                "refuse": self.refuse,
                "crash": self.crash,
                "list": self.give_list,
                "weird": self.weird,
                "give": self.give,
            },
            "routes": {
                "GET hello": self.hello,
                "POST teapot": self.teapot,
                "GET crash": self.raw_crash,
                "GET notaresponse": self.not_a_response,
            },
            "scopes": ["guilds.members.read"],
        }
        if self.thumbnail:
            desc["thumbnail"] = self.thumbnail
        if self.with_socket:
            desc["socket"] = {"join": self.on_join, "message": self.on_message, "leave": self.on_leave}
        return desc

    async def echo(self, ctx, data):
        return {"user": ctx.author.id, "guild": ctx.guild_id, "instance": ctx.instance_id, "data": data}

    async def give_none(self, ctx, data):
        return None

    async def refuse(self, ctx, data):
        return {"error": "Not today.", "extra": 1}

    async def crash(self, ctx, data):
        raise RuntimeError("action broke")

    async def give_list(self, ctx, data):
        return [1, 2]

    async def weird(self, ctx, data):
        return {"when": object()}

    async def give(self, ctx, data):
        return self.result

    async def hello(self, request, ctx):
        self.events.append(("hello", ctx.author.id if ctx else None))
        return web.json_response({"user": ctx.author.id if ctx else None})

    async def teapot(self, request, ctx):
        raise web.HTTPForbidden(text="no tea")

    async def raw_crash(self, request, ctx):
        raise RuntimeError("raw broke")

    async def not_a_response(self, request, ctx):
        return {"oops": True}

    async def on_join(self, ctx, conn):
        self.events.append(("join", ctx.author.id))
        if self.join_error:
            raise RuntimeError("join broke")
        await conn.send({"joined": ctx.author.id, "peers": len(conn.peers())})

    async def on_message(self, ctx, conn, data):
        self.events.append(("message", ctx.author.id, data))
        if data == "boom":
            raise RuntimeError("message broke")
        if isinstance(data, dict) and "shout" in data:
            await conn.broadcast({"shout": data["shout"], "from": ctx.author.id})
        else:
            await conn.send({"echo": data})

    async def on_leave(self, ctx, conn):
        self.events.append(("leave", ctx.author.id))
