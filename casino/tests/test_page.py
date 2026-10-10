"""The page's fixed numbers and names match the bot's, and its files follow the hub's rules"""

import re
from pathlib import Path

from casino.common import catalog, table
from casino.common.games import simple

WEB = Path(__file__).resolve().parents[1] / "web"
MOVES = {"hit", "stay", "double", "war", "surrender", "cashout", "keep", "roll"}


def source(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def block(text: str, name: str) -> str:
    """The text between the braces or brackets after `name =`"""
    match = re.search(rf"{name} = ([{{\[])", text)
    assert match, name
    closing = "}" if match.group(1) == "{" else "]"
    depth, start = 0, match.start(1)
    for i in range(start, len(text)):
        depth += text[i] == match.group(1)
        depth -= text[i] == closing
        if depth == 0:
            return text[start + 1 : i]
    raise AssertionError(name)


def keys(text: str) -> set[str]:
    return set(re.findall(r"^\s*\"?([\w ]+)\"?:", text, re.M))


def test_animation_times_match_the_bots_pacing():
    pairs = re.findall(r"(\w+): ([\d.]+)", block(source("table.js"), "PACE"))
    assert {kind: float(seconds) for kind, seconds in pairs} == table.PACE


def test_games_and_their_stations_match_the_bots():
    assert re.findall(r'"(\w+)"', block(source("format.js"), "GAMES")) == list(catalog.GAMES)
    assert keys(block(source("lobby.js"), "STATIONS")) == set(catalog.GAMES)
    for key in catalog.GAMES:
        assert (WEB / "scenes" / f"{key}.js").exists(), key
        assert (WEB / "art" / "icons" / f"{key}.png").exists(), key


def test_calls_and_moves_match_the_bots():
    choices = block(source("tray.js"), "CHOICES")
    for game, expected in (("coin", simple.COIN_SIDES), ("cups", simple.CUPS), ("hilo", simple.HILO_CHOICES)):
        found = re.search(rf"{game}: \[(.*?)\n  \]", choices, re.S).group(1)
        values = re.findall(r'\[\s*"?(\w+)"?,', found)
        assert sorted(values) == sorted(str(value) for value in expected), game
    assert keys(block(source("table.js"), "MOVE_LABELS")) == MOVES


def test_membership_colors_match_the_bots():
    colors = dict(re.findall(r'(\w+): "#([0-9a-f]{6})"', block(source("format.js"), "TIER_COLORS")))
    assert {name: int(value, 16) for name, value in colors.items() if name != "grey"} == catalog.COLORS
    assert int(colors["grey"], 16) == catalog.BASIC_COLOR


def test_every_recorded_sound_is_bundled():
    takes = re.findall(r'"([\w-]+)"', block(source("sound.js"), "SAMPLES"))
    assert takes
    for take in takes:
        assert (WEB / "sounds" / f"{take}.mp3").exists(), take
    assert (WEB / "sounds" / "License.txt").exists()
    assert (WEB / "music" / "lounge.mp3").exists()


def test_the_page_follows_the_hubs_file_rules():
    index = source("index.html")
    assert "<head>" in index
    assert not re.search(r'(src|href)="/', index), "paths must be relative"
    files = [path for path in WEB.rglob("*") if path.is_file()]
    assert not [path for path in files if path.suffix == ".webp"], "the hub serves .webp without a type"
    assert sum(path.stat().st_size for path in files) < 20 * 1024 * 1024
