import asyncio
import dataclasses
import difflib
import inspect
import itertools
import logging
import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

from .files import hidden, resolve_inside, served_files
from .sessions import ActivityContext
from ..bundled.games import BundledGame

log = logging.getLogger("red.vrt.activityhub.games")

KEY_PATTERN = re.compile(r"[a-z0-9-]{2,32}")
# Action names sit in the address /games/<key>/api/<name>
ACTION_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
ROUTE_PATTERN = re.compile(r"(GET|POST|PUT|PATCH|DELETE) /*([A-Za-z0-9_.\-/]*[A-Za-z0-9_.\-])/*")
SOCKET_EVENTS = ("join", "message", "leave")
# What the hub passes to each kind of handler, in order
HANDLER_ARGS = {
    "actions": ("ctx", "data"),
    "routes": ("ctx", "request"),
    "join": ("ctx", "conn"),
    "message": ("ctx", "conn", "data"),
    "leave": ("ctx", "conn"),
}
FIELDS = {
    "key",
    "name",
    "description",
    "icon",
    "thumbnail",
    "web_dir",
    "actions",
    "socket",
    "routes",
    "scopes",
    "economy",
    "requires",
    "platforms",
    "room",
    "opens_in",
}
REQUIRED = ("key", "name", "web_dir")
# The most characters a game's currency line can have, so the badge fits a card on a phone
ECONOMY_LIMIT = 40
# What Discord says a device is, in the platform part of the Activity's address: its computer app or a browser, or its
# phone and tablet app. Discord says nothing finer, like iOS or Android
PLATFORMS = ("desktop", "mobile")
# Who plays together: everyone in one Activity window, everyone in the server, or everyone the bot has
ROOMS = ("window", "server", "everywhere")
# Where a game opens: only in servers the bot is in, or in DMs and servers the bot isn't in too
OPENS_IN = ("server", "everywhere")
# Seconds a game's room function has to answer, since every action of that game waits on it
ROOM_WAIT = 2
SCOPE_NAME = re.compile(r"[a-z0-9_.]+")
# These add a bot or a webhook to a server, which isn't something a player approves while logging in
NOT_LOGIN_SCOPES = ("bot", "webhook.incoming")
# Copied from the scope list in web/vendor/discord-sdk.js
KNOWN_SCOPES = frozenset(
    "identify identify.premium email connections guilds guilds.join guilds.members.read guilds.channels.read "
    "gdm.join bot rpc rpc.notifications.read rpc.voice.read rpc.voice.write rpc.video.read rpc.video.write "
    "rpc.screenshare.read rpc.screenshare.write rpc.activities.write webhook.incoming messages.read "
    "applications.builds.upload applications.builds.read applications.commands "
    "applications.commands.permissions.update applications.commands.update applications.store.update "
    "applications.entitlements activities.read activities.write activities.invites.write relationships.read "
    "relationships.write voice dm_channels.read role_connections.write presences.read presences.write openid "
    "dm_channels.messages.read dm_channels.messages.write gateway.connect account.global_name.update "
    "payment_sources.country_code sdk.social_layer_presence sdk.social_layer lobbies.write "
    "application_identities.write".split()
)
# src="/..." or href="/..." in a page. The hub serves a game under /games/<key>/, so an address from the site's
# root misses the game's files. Addresses starting with // name another website and are left alone
ABSOLUTE_PATH = re.compile(r"\b(?:src|href)\s*=\s*[\"'](/(?!/)[^\"']*)", re.IGNORECASE)
# More files than any page needs, which usually means web_dir is the project folder rather than the built page
MANY_FILES = 2000
# "requires": the oldest ActivityHub a game works with, as two or three whole numbers like "0.8" or "0.8.0". Each
# number is at most 9 digits, well inside what Python turns into an int
VERSION_PATTERN = re.compile(r"[0-9]{1,9}\.[0-9]{1,9}(?:\.[0-9]{1,9})?")


class GameError(ValueError):
    """Why a game description was refused, worded for the bot owner"""


@dataclass
class Game:
    key: str
    name: str
    web_dir: Path
    cog: t.Any
    description: str = ""
    icon: str | None = None
    thumbnail: str | None = None
    actions: dict[str, t.Callable] = field(default_factory=dict)
    socket: dict[str, t.Callable] = field(default_factory=dict)
    routes: dict[tuple[str, str], t.Callable] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)
    # None, a fixed line, or an async def taking the player's ctx and returning a line or None
    economy: str | t.Callable | None = None
    # Where the game works. The menu marks it, and won't open it, on the other one
    platforms: list[str] = field(default_factory=lambda: list(PLATFORMS))
    # One of ROOMS, or an async def taking the player's ctx and returning one
    room: str | t.Callable = "window"
    # One of OPENS_IN. Outside the bot's servers the menu marks a "server" game, and won't open it
    opens_in: str = "everywhere"

    async def room_kind(self, ctx: ActivityContext) -> str:
        """
        Which kind of room this game puts the player in. A room function that fails, is slow or answers
        something else keeps the player in their own window
        """
        if isinstance(self.room, str):
            return self.room
        try:
            kind = await asyncio.wait_for(self.room(ctx), ROOM_WAIT)
        except asyncio.TimeoutError:
            log.warning(
                "%s: room took longer than %s seconds, so the player plays in their own window", self.key, ROOM_WAIT
            )
            return "window"
        except Exception as e:
            log.warning("%s: room failed, so the player plays in their own window", self.key, exc_info=e)
            return "window"
        if kind not in ROOMS:
            log.warning(
                '%s: room returned %r, not "window", "server" or "everywhere", so the player plays in their own window',
                self.key,
                kind,
            )
            return "window"
        return kind

    async def context(self, ctx: ActivityContext) -> ActivityContext:
        """The player's ctx as this game's handlers get it, with the room this game puts them in"""
        return dataclasses.replace(ctx, room_id=room_id(await self.room_kind(ctx), ctx))


def room_id(kind: str, ctx: ActivityContext) -> str:
    """The id of a player's room of this kind. In a server room, a window outside a server is a room of its own"""
    if kind == "everywhere":
        return "everywhere"
    if kind == "server" and ctx.guild_id is not None:
        return f"server-{ctx.guild_id}"
    return ctx.instance_id


def version_numbers(text: str) -> tuple[int, int, int]:
    """'0.8' or '0.8.0' as (0, 8, 0), so versions compare by number and 0.10 comes after 0.9"""
    numbers = [int(part) for part in text.split(".")]
    major, minor, patch = numbers + [0] * (3 - len(numbers))
    return major, minor, patch


def check_requires(desc: dict, hub_version: str | None) -> None:
    """
    Refuse a game made for a newer hub with a message saying so. Without a hub version only the shape is checked,
    since there is nothing to compare against
    """
    if "requires" not in desc:
        return
    requires = desc["requires"]
    if not isinstance(requires, str) or VERSION_PATTERN.fullmatch(requires) is None:
        raise GameError(f'requires must be a version like "0.8.0", got {requires!r}')
    if hub_version is not None and version_numbers(requires) > version_numbers(hub_version):
        raise GameError(
            f"This game needs ActivityHub {requires} or newer, and this bot has {hub_version}. "
            "Update it: [p]cog update activityhub"
        )


async def read_description(cog: t.Any, hub_version: str | None) -> dict:
    hook = cog.activityhub_game
    if not inspect.iscoroutinefunction(hook):
        raise GameError("activityhub_game must be an async def")
    desc = await hook()
    if isinstance(desc, (list, tuple)):
        raise GameError(f"activityhub_game must return one dict (one game per cog), got {type(desc).__name__}")
    if not isinstance(desc, dict):
        raise GameError(f"activityhub_game must return a dict, got {type(desc).__name__}")
    # Before the unknown fields, which a game made for a newer hub may well have
    check_requires(desc, hub_version)
    unknown = sorted(str(name) for name in desc if name not in FIELDS)
    for name in unknown:
        close = difflib.get_close_matches(name, sorted(FIELDS), n=1)
        if close:
            raise GameError(f"Unknown field {name!r} (did you mean {close[0]!r}?)")
    if unknown:
        raise GameError(
            f"Unknown fields: {', '.join(unknown)}. Check the spelling. "
            "If this game was made for a newer ActivityHub, update ActivityHub ([p]cog update)."
        )
    missing = [name for name in REQUIRED if name not in desc]
    if missing:
        raise GameError(f"Missing fields: {', '.join(missing)}")
    return desc


def check_action_name(name: t.Any) -> None:
    # The browser drops an address part made only of dots, so the page could never call such an action
    if not isinstance(name, str) or ACTION_PATTERN.fullmatch(name) is None or set(name) == {"."}:
        raise GameError(f"actions key {name!r} must be 1-64 letters, digits, _ . and -, and not only dots")


def check_socket_name(name: t.Any) -> None:
    if name not in SOCKET_EVENTS:
        raise GameError(f"socket keys can only be 'join', 'message' and 'leave', got {name!r}")


def check_route_name(name: t.Any) -> None:
    match = ROUTE_PATTERN.fullmatch(name) if isinstance(name, str) else None
    # The browser resolves . and .. in an address before sending it, so a path holding them could never be reached
    if match is None or any(part in (".", "..") for part in match[2].split("/")):
        raise GameError(
            f'routes key {name!r} must be "METHOD path": GET, POST, PUT, PATCH or DELETE in capitals, one space, '
            "then letters, digits, _ . - and /, with no . or .. parts. Paths match exactly, so there are no "
            "{parameters}: read values from request.query instead."
        )


def is_async(handler: t.Any) -> bool:
    """Whether calling it gives something to await: an async def, one behind functools.wraps, or an async __call__"""
    return inspect.iscoroutinefunction(inspect.unwrap(handler)) or inspect.iscoroutinefunction(
        getattr(handler, "__call__", None)
    )


def check_signature(label: str, name: str, handler: t.Callable, args: tuple[str, ...]) -> None:
    """Refuse a handler the hub can't call with its arguments now, rather than when a player first uses it"""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        # Some callables have no signature Python can read. Those fail when they are called instead
        return
    try:
        signature.bind(*args)
    except TypeError:
        hint = ""
        # ClassName.method has no self bound to it, so the hub's first argument would land in self
        if inspect.isfunction(handler) and next(iter(signature.parameters), None) == "self":
            hint = f" Use self.{handler.__name__}, not {handler.__qualname__}."
        shown = signature.replace(return_annotation=inspect.Signature.empty)
        expected = ", ".join(args)
        raise GameError(f"{label} handler {name!r} takes {shown}, but the hub calls it with ({expected}).{hint}")
    # Swapped arguments still bind, so the names are the only clue
    kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    positional = [param.name for param in signature.parameters.values() if param.kind in kinds]
    if args == HANDLER_ARGS["routes"] and positional[:2] == ["request", "ctx"]:
        raise GameError(f"routes handler {name!r} takes (request, ctx), but raw routes get (ctx, request): ctx first")


def check_handlers(label: str, value: t.Any, check_name: t.Callable[[t.Any], None]) -> dict[str, t.Callable]:
    if not isinstance(value, dict):
        raise GameError(f"{label} must be a dict")
    for name, handler in value.items():
        check_name(name)
        if inspect.iscoroutine(handler):
            # Closed here, so Python doesn't also warn that it was never awaited
            handler.close()
            raise GameError(f"{label} {name!r} is a coroutine, not a method: write self.{handler.__name__} without ()")
        if not is_async(handler):
            raise GameError(f"{label} handler {name!r} must be an async def")
        # Each socket event gets its own arguments
        check_signature(label, name, handler, HANDLER_ARGS[name if label == "socket" else label])
    return dict(value)


def parse_routes(value: t.Any) -> dict[tuple[str, str], t.Callable]:
    routes = check_handlers("routes", value, check_route_name)
    parsed = {}
    for name, handler in routes.items():
        method, path = ROUTE_PATTERN.fullmatch(name).groups()
        route = (method, path.strip("/"))
        if route in parsed:
            raise GameError(f"routes has {name!r} twice (paths ignore leading and trailing /)")
        parsed[route] = handler
    return parsed


def check_web_dir(value: t.Any, cog: t.Any) -> tuple[Path, str]:
    """The game's folder, and the text of its index.html"""
    if not isinstance(value, (str, Path)):
        raise GameError("web_dir must be a folder path")
    web_dir = Path(value).expanduser()
    try:
        source = Path(inspect.getfile(type(cog))).resolve()
    except (TypeError, OSError):
        # A class that wasn't made from a file (typed into a REPL, say) has no folder to start from
        source = None
    if source is not None and not web_dir.is_absolute():
        # A relative path starts at the cog's own folder, not wherever the bot was started from
        web_dir = source.parent / web_dir
    index = web_dir / "index.html"
    if not index.is_file():
        raise GameError(f"web_dir has no index.html: looked for {index.resolve()}")
    # Not a refusal of every .py file, since Pyodide games ship some on purpose
    if source is not None and source.is_relative_to(web_dir.resolve()):
        raise GameError(
            "web_dir holds your cog's Python code, and everything in web_dir is public. "
            'Keep the page in its own folder, like Path(__file__).parent / "web".'
        )
    try:
        html = index.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise GameError(f"index.html isn't UTF-8 text ({e.reason} at byte {e.start}). Save it as UTF-8.")
    return web_dir, html


def check_text(desc: dict, cog: t.Any) -> tuple[str, str, str]:
    key, name, description = desc["key"], desc["name"], desc.get("description", "")
    if not isinstance(key, str) or KEY_PATTERN.fullmatch(key) is None:
        reason = f"key must be 2-32 characters of a-z, 0-9 and hyphens, got {key!r}"
        suggestion = re.sub("[^a-z0-9-]+", "-", key.lower()).strip("-")[:32] if isinstance(key, str) else ""
        if KEY_PATTERN.fullmatch(suggestion):
            reason += f" (try {suggestion!r})"
        raise GameError(reason)
    if key.startswith("hub-") and not isinstance(cog, BundledGame):
        raise GameError("keys starting with 'hub-' are kept for ActivityHub's own games")
    if not isinstance(name, str) or not name.strip():
        raise GameError("name must be a non-empty string")
    if not isinstance(description, str):
        raise GameError("description must be a string")
    return key, name.strip(), description


def check_scopes(value: t.Any, cog: t.Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(scope, str) and scope for scope in value):
        raise GameError("scopes must be a list of strings")
    for scope in value:
        if SCOPE_NAME.fullmatch(scope) is None:
            raise GameError(
                f"scopes has {scope!r}, which isn't a Discord scope name. "
                'Write one scope per string, like ["identify", "guilds"].'
            )
        if scope in NOT_LOGIN_SCOPES:
            raise GameError(f"scopes can't include {scope!r}: it isn't a permission an Activity login can ask for")
        if scope not in KNOWN_SCOPES:
            # Only a warning, so scopes Discord adds later still work
            log.warning(
                "%s asks for the scope %r, which ActivityHub doesn't know. Every installed game's scopes go into one "
                "Discord login, so a wrong one makes every player log in without the extra permissions.",
                cog.qualified_name,
                scope,
            )
    return list(value)


def check_economy(value: t.Any) -> str | t.Callable | None:
    """None, a fixed line (None when blank), or an async def the hub calls with the player's ctx"""
    if value is None:
        return None
    if isinstance(value, str):
        line = value.strip()
        if len(line) > ECONOMY_LIMIT:
            raise GameError(
                f"economy is {len(line)} characters long, but the menu's badge fits {ECONOMY_LIMIT}. Shorten it."
            )
        return line or None
    return check_ctx_function("economy", value, "economy must be None, a string, or an async def that takes ctx")


def check_ctx_function(name: str, value: t.Any, refused: str) -> t.Callable:
    """An async def the hub calls with the player's ctx, or GameError with `refused` for anything else"""
    if inspect.iscoroutine(value):
        # Closed here, so Python doesn't also warn that it was never awaited
        value.close()
        raise GameError(f"{name} is a coroutine, not a method: write self.{value.__name__} without ()")
    if not callable(value) or not is_async(value):
        raise GameError(refused)
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        # Some callables have no signature Python can read. Those fail when they are called instead
        return value
    try:
        signature.bind(None)
    except TypeError:
        shown = signature.replace(return_annotation=inspect.Signature.empty)
        raise GameError(f"{name} takes {shown}, but the hub calls it with (ctx).")
    return value


def check_platforms(value: t.Any) -> list[str]:
    """The platforms a game works on, each once"""
    if not isinstance(value, list) or not all(isinstance(item, str) and item in PLATFORMS for item in value):
        raise GameError(f'platforms can only hold "desktop" and "mobile" (all Discord tells the hub), got {value!r}')
    if not value:
        raise GameError("platforms can't be empty: leave it out to run everywhere")
    return list(dict.fromkeys(value))


def check_room(value: t.Any) -> str | t.Callable:
    """One of ROOMS, or an async def the hub calls with the player's ctx to pick one"""
    refused = f'room must be "window", "server", "everywhere", or an async def that takes ctx, got {value!r}'
    if isinstance(value, str):
        if value not in ROOMS:
            raise GameError(refused)
        return value
    return check_ctx_function("room", value, refused)


def check_opens_in(value: t.Any) -> str:
    if not isinstance(value, str) or value not in OPENS_IN:
        raise GameError(f'opens_in must be "server" or "everywhere", got {value!r}')
    return value


def check_picture(desc: dict, field_name: str, web_dir: Path) -> str | None:
    picture = desc.get(field_name)
    if picture is None:
        return None
    refused = GameError(
        f"{field_name} must be a file inside web_dir, written relative to it (like 'icon.png'): {picture}"
    )
    relative = picture.as_posix() if isinstance(picture, Path) else picture
    if isinstance(picture, (str, Path)) and Path(picture).is_absolute():
        # Kept relative, so the menu's data never shows the server's folders
        try:
            relative = Path(picture).resolve().relative_to(web_dir.resolve()).as_posix()
        except ValueError:
            raise refused
    if not isinstance(relative, str):
        raise refused
    # resolve_inside refuses these too, but "must be a file inside web_dir" wouldn't say why
    if hidden(Path(relative)) and ".." not in Path(relative).parts:
        raise GameError(
            f"{field_name} has a name starting with a dot in its path, and the hub never serves those: {picture}"
        )
    if resolve_inside(web_dir, relative) is None:
        raise refused
    return relative


def warn_about_page(key: str, web_dir: Path, html: str) -> None:
    """Log the page mistakes that register fine but break the page or slow the hub down. Never refuses"""
    match = ABSOLUTE_PATH.search(html)
    if match is not None:
        log.warning(
            "%s: index.html refers to %s with an absolute path, which the hub can't serve. Use a relative path with "
            "no leading /. Built with Vite? Set base: './'. To go back to the menu, call backToMenu().",
            key,
            match[1],
        )
    crowded = None
    if (web_dir / "node_modules").is_dir():
        crowded = "a node_modules folder"
    else:
        # Counting stops past the limit, since walking a huge folder is the slow part. Hidden files never count
        if sum(1 for _ in itertools.islice(served_files(web_dir), MANY_FILES + 1)) > MANY_FILES:
            crowded = f"more than {MANY_FILES} files"
    if crowded is not None:
        log.warning(
            "%s: web_dir has %s. Every file in it is public and is fingerprinted each time the game opens. Point "
            "web_dir at your built page (for example dist/).",
            key,
            crowded,
        )


async def validate_game(cog: t.Any, hub_version: str | None = None) -> Game:
    """Turn a cog's activityhub_game() description into a Game, or raise GameError saying what is wrong"""
    desc = await read_description(cog, hub_version)
    key, name, description = check_text(desc, cog)
    web_dir, html = check_web_dir(desc["web_dir"], cog)
    scopes = check_scopes(desc.get("scopes", []), cog)
    game = Game(
        key=key,
        name=name,
        web_dir=web_dir,
        cog=cog,
        description=description,
        icon=check_picture(desc, "icon", web_dir),
        thumbnail=check_picture(desc, "thumbnail", web_dir),
        actions=check_handlers("actions", desc.get("actions", {}), check_action_name),
        socket=check_handlers("socket", desc.get("socket", {}), check_socket_name),
        routes=parse_routes(desc.get("routes", {})),
        scopes=scopes,
        economy=check_economy(desc.get("economy")),
        platforms=check_platforms(desc.get("platforms", list(PLATFORMS))),
        room=check_room(desc.get("room", "window")),
        opens_in=check_opens_in(desc.get("opens_in", "everywhere")),
    )
    warn_about_page(key, web_dir, html)
    return game


class GameRegistry:
    """Games from loaded cogs by key, plus each refused cog with the reason"""

    def __init__(self, hub_version: str):
        # ActivityHub's own version, which a game's "requires" is checked against
        self.hub_version = hub_version
        self.games: dict[str, Game] = {}
        self.failed: dict[str, tuple[t.Any, str]] = {}
        # Cog name to the key it was refused because another cog held it, so it can have another go once that frees
        self.clashes: dict[str, str] = {}

    async def add(self, cog: t.Any, still_loaded: t.Callable[[], bool] = lambda: True) -> Game | None:
        """
        Register a cog's game. Returns None when the cog has no game, its description was refused, or
        still_loaded() says the cog unloaded (or was replaced by a reloaded copy) while it described itself
        """
        if not hasattr(cog, "activityhub_game"):
            return None
        cog_name = cog.qualified_name
        self.failed.pop(cog_name, None)
        self.clashes.pop(cog_name, None)
        game, reason = None, ""
        try:
            game = await validate_game(cog, self.hub_version)
        except GameError as e:
            reason = str(e)
        except Exception as e:
            log.error("activityhub_game() of %s raised", cog_name, exc_info=e)
            reason = f"activityhub_game() raised {type(e).__name__}: {e}"
        # Checked before anything changes: an old copy finishing after its reloaded copy registered would
        # otherwise replace the new copy's game or refusal, and then be removed itself, leaving neither
        if not still_loaded():
            return None
        if game is None:
            return self.refuse(cog, reason)
        holder = self.games.get(game.key)
        if holder is not None and holder.cog.qualified_name != cog_name:
            self.clashes[cog_name] = game.key
            return self.refuse(cog, f"The key {game.key!r} is already used by {holder.cog.qualified_name}")
        # A reload can add the new copy before removing the old one, so the new copy replaces
        # whatever the same cog registered before, even under a different key
        for old in [g for g in self.games.values() if g.cog.qualified_name == cog_name]:
            del self.games[old.key]
        self.games[game.key] = game
        log.info("Registered activity %s from %s", game.key, cog_name)
        return game

    def refuse(self, cog: t.Any, reason: str) -> None:
        log.warning("Skipped the activity from %s: %s", cog.qualified_name, reason)
        self.failed[cog.qualified_name] = (cog, reason)
        return None

    def remove(self, cog: t.Any) -> None:
        """Forget what this exact cog object registered (a reloaded copy is a different object)"""
        for game in [g for g in self.games.values() if g.cog is cog]:
            del self.games[game.key]
            log.info("Removed activity %s", game.key)
        entry = self.failed.get(cog.qualified_name)
        if entry is not None and entry[0] is cog:
            del self.failed[cog.qualified_name]
            self.clashes.pop(cog.qualified_name, None)

    def scopes(self) -> list[str]:
        """Every extra Discord permission the installed games ask for"""
        return sorted({scope for game in self.games.values() for scope in game.scopes})
