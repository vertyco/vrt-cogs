import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from activityhub.common import economy
from activityhub.common.games import Game
from activityhub.common.sessions import ActivityContext

CTX = ActivityContext(author=SimpleNamespace(id=1), guild=SimpleNamespace(id=9), instance_id="i-1")


def game(key, value, room="window"):
    return Game(key=key, name=key.title(), web_dir=Path("."), cog=None, economy=value, room=room)


@pytest.mark.parametrize(
    "value, cleaned",
    [(None, None), ("Earn credits", "Earn credits"), ("  Earn  ", "Earn"), ("   ", None), ("y" * 50, "y" * 40)],
)
def test_clean(value, cleaned):
    assert economy.clean("k", value) == cleaned


def test_an_overlong_line_is_cut_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="red.vrt.activityhub.economy"):
        assert economy.clean("k", "z" * 45) == "z" * 40
    assert "k: economy returned 45 characters, so its label was cut to 40" in caplog.text


@pytest.mark.parametrize("value", [True, 5, ["a"], {"a": 1}])
def test_a_non_string_is_dropped_and_logged(caplog, value):
    with caplog.at_level(logging.WARNING, logger="red.vrt.activityhub.economy"):
        assert economy.clean("k", value) is None
    assert "k: economy returned" in caplog.text and "not a string or None" in caplog.text


@pytest.mark.asyncio
async def test_fixed_lines_and_none_need_no_call():
    assert await economy.line(game("a", "Bet credits"), CTX) == "Bet credits"
    assert await economy.line(game("b", None), CTX) is None


@pytest.mark.asyncio
async def test_a_function_gets_the_players_ctx():
    seen = []

    async def answer(ctx):
        seen.append(ctx)
        return "Cash in up to 500 credits"

    assert await economy.line(game("a", answer), CTX) == "Cash in up to 500 credits"
    assert seen == [CTX]
    # Like every handler, it gets the room the game puts the player in
    await economy.line(game("b", answer, room="server"), CTX)
    assert seen[1].author is CTX.author and seen[1].room_id == "server-9"


@pytest.mark.asyncio
async def test_a_broken_line_only_loses_its_own_badge(caplog):
    async def broken(ctx):
        raise RuntimeError("no bank")

    async def fine(ctx):
        return "Earn credits"

    with caplog.at_level(logging.WARNING, logger="red.vrt.activityhub.economy"):
        lines = await economy.lines([game("a", broken), game("b", fine)], CTX)
    assert lines == {"a": None, "b": "Earn credits"}
    assert "a: economy failed, so its card has no currency label" in caplog.text


@pytest.mark.asyncio
async def test_a_slow_line_is_dropped_without_holding_the_menu(monkeypatch, caplog):
    monkeypatch.setattr(economy, "WAIT", 0.05)

    async def slow(ctx):
        await asyncio.sleep(10)
        return "Too late"

    async def fine(ctx):
        return "Earn credits"

    loop = asyncio.get_running_loop()
    started = loop.time()
    with caplog.at_level(logging.WARNING, logger="red.vrt.activityhub.economy"):
        lines = await economy.lines([game("a", slow), game("b", fine)], CTX)
    assert loop.time() - started < 1
    assert lines == {"a": None, "b": "Earn credits"}
    assert "a: economy took longer than 0.05 seconds, so its card has no currency label" in caplog.text
