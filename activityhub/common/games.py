import difflib
import inspect
import itertools
import logging
import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

from .files import hidden, resolve_inside, served_files

log = logging.getLogger("red.vrt.activityhub.games")

KEY_PATTERN = re.compile(r"[a-z0-9-]{2,32}")
# Action names sit in the address /games/<key>/api/<name>
ACTION_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
ROUTE_PATTERN = re.compile(r"(GET|POST|PUT|PATCH|DELETE) /*([A-Za-z0-9_.\-/]*[A-Za-z0-9_.\-])/*")
SOCKET_EVENTS = ("join", "message", "leave")
# What the hub passes to each kind of handler, in order
HANDLER_ARGS = {
    "actions": ("ctx", "data"),
    "routes": ("request", "ctx"),
    "join": ("ctx", "conn"),
    "message": ("ctx", "conn", "data"),
    "leave": ("ctx", "conn"),
}
FIELDS = {"key", "name", "description", "icon", "thumbnail", "web_dir", "actions", "socket", "routes", "scopes"}
REQUIRED = ("key", "name", "web_dir")
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


async def read_description(cog: t.Any) -> dict:
    hook = cog.activityhub_game
    if not inspect.iscoroutinefunction(hook):
        raise GameError("activityhub_game must be an async def")
    desc = await hook()
    if isinstance(desc, (list, tuple)):
        raise GameError(f"activityhub_game must return one dict (one game per cog), got {type(desc).__name__}")
    if not isinstance(desc, dict):
        raise GameError(f"activityhub_game must return a dict, got {type(desc).__name__}")
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
    if args[0] == "request" and positional[:2] == ["ctx", "request"]:
        raise GameError(
            f"routes handler {name!r} takes (ctx, request), but raw routes get (request, ctx): request first"
        )


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


def check_text(desc: dict) -> tuple[str, str, str]:
    key, name, description = desc["key"], desc["name"], desc.get("description", "")
    if not isinstance(key, str) or KEY_PATTERN.fullmatch(key) is None:
        reason = f"key must be 2-32 characters of a-z, 0-9 and hyphens, got {key!r}"
        suggestion = re.sub("[^a-z0-9-]+", "-", key.lower()).strip("-")[:32] if isinstance(key, str) else ""
        if KEY_PATTERN.fullmatch(suggestion):
            reason += f" (try {suggestion!r})"
        raise GameError(reason)
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
                "Discord login, so a wrong one stops every game from logging in.",
                cog.qualified_name,
                scope,
            )
    return list(value)


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


async def validate_game(cog: t.Any) -> Game:
    """Turn a cog's activityhub_game() description into a Game, or raise GameError saying what is wrong"""
    desc = await read_description(cog)
    key, name, description = check_text(desc)
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
    )
    warn_about_page(key, web_dir, html)
    return game


class GameRegistry:
    """Games from loaded cogs by key, plus each refused cog with the reason"""

    def __init__(self):
        self.games: dict[str, Game] = {}
        self.failed: dict[str, tuple[t.Any, str]] = {}
        # Cog name to the key it was refused because another cog held it, so it can have another go once that frees
        self.clashes: dict[str, str] = {}

    async def add(self, cog: t.Any) -> Game | None:
        """Register a cog's game. Returns None when the cog has no game or its description was refused"""
        if not hasattr(cog, "activityhub_game"):
            return None
        cog_name = cog.qualified_name
        self.failed.pop(cog_name, None)
        self.clashes.pop(cog_name, None)
        try:
            game = await validate_game(cog)
        except GameError as e:
            return self.refuse(cog, str(e))
        except Exception as e:
            log.error("activityhub_game() of %s raised", cog_name, exc_info=e)
            return self.refuse(cog, f"activityhub_game() raised {type(e).__name__}: {e}")
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
