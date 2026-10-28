"""
Each game's currency line for its menu card: how it ties into the server's economy, in the game's own words.

A game passes None, a fixed line, or an async def the hub calls with the player's ctx each time the menu loads in a
server. A slow or broken game only loses its own badge: the menu never waits long or fails because of it.
"""

import asyncio
import logging
import typing as t

from .games import ECONOMY_LIMIT, Game

log = logging.getLogger("red.vrt.activityhub.economy")

# Seconds one game's function has to answer
WAIT = 2


def clean(key: str, value: t.Any) -> str | None:
    """A game's answer as a badge line, or None for no badge"""
    if value is None:
        return None
    if not isinstance(value, str):
        log.warning(
            "%s: economy returned %s, not a string or None, so its card has no currency label",
            key,
            type(value).__name__,
        )
        return None
    line = value.strip()
    if len(line) > ECONOMY_LIMIT:
        log.warning("%s: economy returned %d characters, so its label was cut to %d", key, len(line), ECONOMY_LIMIT)
        line = line[:ECONOMY_LIMIT].rstrip()
    return line or None


async def line(game: Game, ctx: t.Any) -> str | None:
    if game.economy is None or isinstance(game.economy, str):
        return game.economy
    try:
        value = await asyncio.wait_for(game.economy(await game.context(ctx)), WAIT)
    except asyncio.TimeoutError:
        log.warning("%s: economy took longer than %s seconds, so its card has no currency label", game.key, WAIT)
        return None
    except Exception as e:
        log.warning("%s: economy failed, so its card has no currency label", game.key, exc_info=e)
        return None
    return clean(game.key, value)


async def lines(games: list[Game], ctx: t.Any) -> dict[str, str | None]:
    """Every game's line for this player, asked all at once"""
    answers = await asyncio.gather(*(line(game, ctx) for game in games))
    return {game.key: answer for game, answer in zip(games, answers, strict=True)}
