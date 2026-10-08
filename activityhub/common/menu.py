import typing as t
from urllib.parse import quote

from .files import build_id
from .games import Game
from .looks import SettingsError


def ordered_games(games: t.Iterable[Game], order: list[str]) -> list[Game]:
    """Games in the player's saved order, then any others alphabetically by name"""
    by_key = {game.key: game for game in games}
    first = [by_key.pop(key) for key in order if key in by_key]
    rest = sorted(by_key.values(), key=lambda game: game.name.casefold())
    return first + rest


def check_keys(value: t.Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(key, str) for key in value):
        raise SettingsError("Expected a list of activity keys.")
    return list(dict.fromkeys(value))


def clean_order(value: t.Any, installed: t.Collection[str]) -> list[str]:
    """A player's order to save: installed games only, each once"""
    return [key for key in check_keys(value) if key in installed]


def merge_order(saved: list[str], value: t.Any, installed: t.Collection[str]) -> list[str]:
    """
    A player's order to save: the sent keys of installed games, then the saved keys of installed games not sent.

    The menu only lists games that are on in the current server, so the positions of games that are off here
    must survive a save and still apply in other servers. An empty list is the menu's Reset: no saved order,
    so every game, including ones installed later, sorts alphabetically.
    """
    sent = clean_order(value, installed)
    if not value:
        return []
    kept = [key for key in saved if key in installed]
    return list(dict.fromkeys(sent + kept))


def merge_disabled(saved: list[str], value: t.Any, installed: t.Collection[str]) -> list[str]:
    """
    A server's off list to save: the sent keys of installed games, plus the saved keys of uninstalled ones.

    Keeping uninstalled games in the list means reinstalling one doesn't silently turn it back on.
    """
    sent = [key for key in check_keys(value) if key in installed]
    kept = [key for key in saved if key not in installed]
    return list(dict.fromkeys(kept + sent))


def allowed_tabs(in_guild: bool, can_manage: bool, is_owner: bool) -> list[str]:
    """Settings panel tabs a player may see and save"""
    tabs = ["look", "order"]
    if in_guild and (can_manage or is_owner):
        tabs.append("server")
    if is_owner:
        tabs.append("defaults")
    return tabs


def picture_url(game: Game, build: str, picture: str | None) -> str | None:
    return f"/games/{game.key}/{build}/{quote(picture)}" if picture else None


def game_json(game: Game, build: str) -> dict:
    return {
        "key": game.key,
        "name": game.name,
        "description": game.description,
        "icon": picture_url(game, build, game.icon),
        "thumbnail": picture_url(game, build, game.thumbnail),
    }


def games_json(games: t.Iterable[Game]) -> list[dict]:
    return [game_json(game, build_id(game.web_dir)) for game in games]


def player_json(ctx: t.Any) -> dict:
    guild = ctx.guild
    return {
        "id": str(ctx.author.id),
        "username": ctx.author.name,
        "avatar": ctx.author.display_avatar.url,
        "guildId": str(guild.id) if guild else None,
        "guildName": guild.name if guild else None,
        "guildIcon": guild.icon.url if guild and guild.icon else None,
    }
