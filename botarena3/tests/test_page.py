import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from botarena3.common import battle, lobby
from botarena3.common.parts import WEAPONS

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))
LINKAGES = ["bot", "top", "stats", "boom", "fire", "spark", "ricco", "shold", "listitem", "lnode", "tcolorball"]
MUSIC = ["dnb", "ambi", "rave", "shop"]
EFFECTS = ["cash", "cons", "dismount", "dit", "mount", "splode", "pdown", "pup"]
SCREENS = ["intro", "menu", "shop", "battle", "wingame", "instructions", "levelselect", "challengeselect", "settings"]
# The original's sponsor (GameGecko.com): its logo and link clips, the pictures and texts only they show
SPONSOR_IDS = {11, 329, 344, 528, 10, 326, 343, 525, 328, 526, 527}
# The designer's credit in the credits text names the sponsor, and stays as a plain credit
KEPT_CREDIT = "GAME DESIGN AND CONCEPT BY LUKE HAILLAY FOR GAMEGECKO.COM."


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_the_art_has_every_page_and_clip_the_game_uses():
    art = json.loads(read("art/flash.json"))
    for page in art["atlas"]["pages"]:
        assert (WEB / "art" / page).is_file(), page
    for name in LINKAGES:
        assert name in art["exports"], name
    root_labels = art["sprites"]["0"]["labels"]
    for name in SCREENS:
        assert name in root_labels, name


def test_the_sponsors_logos_and_links_are_left_out():
    words = read("art/flash.json")
    art = json.loads(words)
    placed = {op[1] for sprite in art["sprites"].values() for frame in sprite["f"] for op in frame if len(op) > 1}
    assert not placed & SPONSOR_IDS
    for table in (art["sprites"], art["atlas"]["shapes"], art["atlas"]["blank"], art["texts"], art["labels"]):
        assert not {int(key) for key in table} & SPONSOR_IDS
    assert "gecko" not in words.replace(KEPT_CREDIT, "").lower()
    assert art["labels"]["345"][0][0] == "GAME DESIGN AND CONCEPT BY LUKE HAILLAY"
    # The intro opens on its own "A game by..." (332), with no empty frames where the splash was
    intro = art["sprites"]["333"]
    assert intro["f"][0][0][1] == 332 and intro["n"] == 101


def test_the_countdown_matches_the_bots_timing():
    art = json.loads(read("art/flash.json"))
    labels = art["sprites"]["550"]["labels"]
    assert labels["playerlose"] == 162 and labels["complose"] == 232
    assert labels["complose"] - labels["playerlose"] == battle.BANNER_STEPS + 1


def test_every_sound_the_game_plays_is_there():
    names = {w.sound for w in WEAPONS.values()} | {f"rico{n}" for n in range(1, 8)} | set(MUSIC) | set(EFFECTS)
    for name in names:
        assert (WEB / "sounds" / f"{name}.mp3").is_file(), name


def test_the_pixel_font_is_there():
    assert (WEB / "fonts" / "04b_03b.ttf").is_file()


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


def test_the_page_uses_the_bots_timing():
    assert re.search(rf"^export const FPS = {battle.FPS};$", read("flash.js"), re.M)


def test_the_battle_screen_uses_the_bots_numbers():
    script = read("battle.js")
    for name, value in (
        ("STEPS", lobby.STEPS),
        ("MOVE_AT", battle.MOVE_AT),
        ("BANNER_STEPS", battle.BANNER_STEPS),
        ("FADE_STEPS", battle.FADE_STEPS),
    ):
        assert re.search(rf"^export const {name} = {value};$", script, re.M), name


def test_the_move_marker_stays_in_the_bots_box():
    box = (battle.LEFT, battle.TOP, battle.RIGHT, battle.BOTTOM)
    assert re.search(rf"^export const ORDER_BOX = \[{', '.join(map(str, box))}\];$", read("battle.js"), re.M)
