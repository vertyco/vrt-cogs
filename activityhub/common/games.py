import inspect
import logging
import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

from .files import resolve_inside

log = logging.getLogger("red.vrt.activityhub.games")

KEY_PATTERN = re.compile(r"[a-z0-9-]{2,32}")
# Action names sit in the address /games/<key>/api/<name>
ACTION_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
ROUTE_PATTERN = re.compile(r"(GET|POST|PUT|PATCH|DELETE) /*([A-Za-z0-9_.\-/]*[A-Za-z0-9_.\-])/*")
SOCKET_EVENTS = ("join", "message", "leave")
FIELDS = {"key", "name", "description", "icon", "thumbnail", "web_dir", "actions", "socket", "routes", "scopes"}
REQUIRED = ("key", "name", "web_dir")


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
    if not isinstance(desc, dict):
        raise GameError("activityhub_game must return a dict")
    unknown = sorted(str(name) for name in desc if name not in FIELDS)
    if unknown:
        raise GameError(f"Unknown fields: {', '.join(unknown)}")
    missing = [name for name in REQUIRED if name not in desc]
    if missing:
        raise GameError(f"Missing fields: {', '.join(missing)}")
    return desc


def check_handlers(label: str, value: t.Any, name_ok: t.Callable[[str], bool]) -> dict[str, t.Callable]:
    if not isinstance(value, dict):
        raise GameError(f"{label} must be a dict")
    for name, handler in value.items():
        if not isinstance(name, str) or not name_ok(name):
            raise GameError(f"{label} has an invalid name: {name!r}")
        if not inspect.iscoroutinefunction(handler):
            raise GameError(f"{label} handler {name!r} must be an async def")
    return dict(value)


def parse_routes(value: t.Any) -> dict[tuple[str, str], t.Callable]:
    routes = check_handlers("routes", value, lambda name: ROUTE_PATTERN.fullmatch(name) is not None)
    parsed = {}
    for name, handler in routes.items():
        method, path = ROUTE_PATTERN.fullmatch(name).groups()
        parsed[(method, path.strip("/"))] = handler
    return parsed


def check_web_dir(value: t.Any) -> Path:
    if not isinstance(value, (str, Path)):
        raise GameError("web_dir must be a folder path")
    web_dir = Path(value)
    if not (web_dir / "index.html").is_file():
        raise GameError(f"web_dir has no index.html: {web_dir}")
    return web_dir


def check_text(desc: dict) -> tuple[str, str, str]:
    key, name, description = desc["key"], desc["name"], desc.get("description", "")
    if not isinstance(key, str) or KEY_PATTERN.fullmatch(key) is None:
        raise GameError("key must be 2-32 characters of a-z, 0-9 and hyphens")
    if not isinstance(name, str) or not name.strip():
        raise GameError("name must be a non-empty string")
    if not isinstance(description, str):
        raise GameError("description must be a string")
    return key, name.strip(), description


def check_picture(desc: dict, field_name: str, web_dir: Path) -> str | None:
    picture = desc.get(field_name)
    if picture is not None and (not isinstance(picture, str) or resolve_inside(web_dir, picture) is None):
        raise GameError(f"{field_name} must name a file inside web_dir: {picture!r}")
    return picture


async def validate_game(cog: t.Any) -> Game:
    """Turn a cog's activityhub_game() description into a Game, or raise GameError saying what is wrong"""
    desc = await read_description(cog)
    key, name, description = check_text(desc)
    web_dir = check_web_dir(desc["web_dir"])
    scopes = desc.get("scopes", [])
    if not isinstance(scopes, list) or not all(isinstance(scope, str) and scope for scope in scopes):
        raise GameError("scopes must be a list of strings")
    return Game(
        key=key,
        name=name,
        web_dir=web_dir,
        cog=cog,
        description=description,
        icon=check_picture(desc, "icon", web_dir),
        thumbnail=check_picture(desc, "thumbnail", web_dir),
        actions=check_handlers("actions", desc.get("actions", {}), lambda n: ACTION_PATTERN.fullmatch(n) is not None),
        socket=check_handlers("socket", desc.get("socket", {}), lambda n: n in SOCKET_EVENTS),
        routes=parse_routes(desc.get("routes", {})),
        scopes=list(scopes),
    )


class GameRegistry:
    """Games from loaded cogs by key, plus each refused cog with the reason"""

    def __init__(self):
        self.games: dict[str, Game] = {}
        self.failed: dict[str, tuple[t.Any, str]] = {}

    async def add(self, cog: t.Any) -> Game | None:
        """Register a cog's game. Returns None when the cog has no game or its description was refused"""
        if not hasattr(cog, "activityhub_game"):
            return None
        cog_name = cog.qualified_name
        self.failed.pop(cog_name, None)
        try:
            game = await validate_game(cog)
        except GameError as e:
            return self.refuse(cog, str(e))
        except Exception as e:
            log.error("activityhub_game() of %s raised", cog_name, exc_info=e)
            return self.refuse(cog, f"activityhub_game() raised {type(e).__name__}: {e}")
        holder = self.games.get(game.key)
        if holder is not None and holder.cog.qualified_name != cog_name:
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

    def scopes(self) -> list[str]:
        """Every extra Discord permission the installed games ask for"""
        return sorted({scope for game in self.games.values() for scope in game.scopes})
