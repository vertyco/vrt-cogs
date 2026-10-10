import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tanks.common import items, match, physics, tank, terrain
from tanks.tests import demo

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))
# The page draws, steers and plays shots back with the same numbers the bot uses
SHARED = {
    "scene.js": {
        "WIDTH": terrain.WIDTH,
        "HEIGHT": terrain.HEIGHT,
        "STEP_RATE": physics.STEP_RATE,
        "DRIVE_STEP": tank.DRIVE_STEP,
        "MIN_X": tank.MIN_X,
        "MAX_X": tank.MAX_X,
    },
    "game.js": {"STEP_RATE": physics.STEP_RATE, "TICK_RATE": match.TICK_RATE},
    "playback.js": {"STEP_RATE": physics.STEP_RATE},
}
ART = [
    "land1",
    "land2",
    "land3",
    "tree1",
    "tree2",
    "tank_tracks",
    "tank_body",
    "tank_boom_01",
    "barrel_01",
    "shell",
    "fireball",
    "smoke",
    "parachute",
    "shield_weak",
    "shield",
    "shield_strong",
    "shield_super",
    "teleport_01",
    "blink_01",
    "strike_cursor",
]
SOUNDS = ["tank_death", "boom_big", "boom_medium", "boom_small", "click", "shop", "turret"]


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_the_art_and_sounds_are_all_there():
    art = json.loads(read("art/art.json"))
    for name in ART:
        assert name in art and (WEB / "art" / f"{name}.svg").is_file(), name
    for kind, count in (("weapon", len(items.WEAPONS)), ("item", len(items.EXTRAS))):
        for number in range(count):
            assert (WEB / "art" / f"{kind}_{number:02}.svg").is_file(), f"{kind}_{number:02}"
    assert all(art["at"][f"land{n}"] for n in terrain.LANDSCAPES)
    for blast in art["blasts"].values():
        assert all(frame["art"] in (None, "fireball", "smoke") for frame in blast["frames"])
    for sound in SOUNDS:
        assert (WEB / "sounds" / f"{sound}.mp3").is_file(), sound


@pytest.mark.parametrize("name", sorted(SHARED))
def test_the_page_uses_the_bots_numbers(name):
    script = read(name)
    for const, value in SHARED[name].items():
        found = re.search(rf"^const {const} = ([0-9.]+);", script, re.M)
        assert found, f"{name} has no const {const}"
        assert float(found.group(1)) == value, const


def test_every_blast_is_drawn_at_the_size_the_bot_digs_and_hurts_with():
    # The bot's blast sizes were measured from the original's explosion art, so the art the page plays must agree
    shells = dict(re.findall(r'^  (\w+): "(\w+)",$', read("scene.js"), re.M))
    blasts = json.loads(read("art/art.json"))["blasts"]
    for blast in (value for value in vars(physics).values() if isinstance(value, physics.Blast)):
        art = blasts[shells[blast.key]]
        fireball = max(frame["sx"] for frame in art["frames"] if frame["art"] == "fireball")
        assert (fireball, *art["scale"]) == (blast.scale, blast.sx, blast.sy), blast.key


def test_the_setup_offers_the_bots_choices():
    page = read("index.html")
    for name, choices in (
        ("rounds", match.ROUND_CHOICES),
        ("landscape", ("random", *terrain.LANDSCAPES)),
        ("timer", (*match.TIMER_CHOICES, "off")),
    ):
        options = re.search(rf'<select id="{name}">(.*?)</select>', page).group(1)
        assert re.findall(r'<option value="([^"]+)"', options) == [str(choice) for choice in choices], name


def test_shields_fade_by_the_bots_strengths():
    found = re.search(r"^const SHIELD_STRENGTH = \{(.*)\};$", read("scene.js"), re.M)
    pairs = dict(re.findall(r"(\d+): (\d+)", found.group(1)))
    assert {int(k): int(v) for k, v in pairs.items()} == items.SHIELD_STRENGTH


def test_the_shop_shows_the_bots_names_prices_and_packs():
    panels = read("panels.js")
    for table, things in (("WEAPONS", items.WEAPONS), ("EXTRAS", items.EXTRAS)):
        block = re.search(rf"^export const {table} = \[\n(.*?)\n\];", panels, re.M | re.S).group(1)
        rows = re.findall(r'\["([^"]+)", (\d+), (\d+)\]', block)
        assert rows == [(thing.name, str(thing.price), str(thing.pack)) for thing in things], table


@pytest.mark.parametrize("name", SCRIPTS)
def test_page_scripts_parse(name, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the scripts can't be checked")
    # As a module, the way the browser loads it
    module = tmp_path / f"{name}.mjs"
    module.write_text(read(name), encoding="utf-8")
    result = subprocess.run([node, "--check", str(module)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_the_preview_recording_matches_the_match_code():
    # Recorded again with `python -m tanks.tests.demo` whenever this fails
    assert demo.dump(await demo.record()) == read("demo.json")
