import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from ageofwar.common import data, match, shots
from ageofwar.tests import demo

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def js_list(script: str, name: str) -> list:
    found = re.search(rf"^(?:export )?const {name} = (\[.*?\]);", script, re.M | re.S)
    assert found, f"no const {name}"
    # The page's lists may end with a comma, which JSON doesn't allow
    return json.loads(re.sub(r",\s*\]$", "]", found.group(1)))


def js_table(script: str, name: str) -> dict[int, tuple]:
    found = re.search(rf"^export const {name} = \{{\n(.*?)\n\}};", script, re.M | re.S)
    assert found, f"no const {name}"
    block = found.group(1)
    return {int(k): (n, int(p)) for k, n, p in re.findall(r'^  (\d+): \["([^"]+)", (\d+)\],$', block, re.M)}


def test_the_menus_show_the_bots_names_and_prices():
    hud = read("hud.js")
    assert js_table(hud, "UNITS") == {k: (u.name, u.cost) for k, u in data.UNITS.items()}
    assert js_table(hud, "TURRETS") == {k: (u.name, u.cost) for k, u in data.TURRETS.items()}
    assert js_list(hud, "EVOLVE_XP") == list(data.EVOLVE_XP)
    assert js_list(hud, "SPOT_PRICES") == list(data.SPOT_PRICES)
    assert re.search(rf"^export const SPECIAL_COOLDOWN = {data.SPECIAL_COOLDOWN};$", hud, re.M)


def test_the_field_uses_the_bots_numbers():
    scene = read("scene.js")
    assert re.search(rf"^export const FPS = {data.FPS};$", scene, re.M)
    assert js_list(scene, "STATES") == list(data.STATES)
    assert js_list(scene, "SHOT_KINDS") == list(shots.KINDS)
    assert js_list(scene, "SPOT_Y") == list(data.SPOT_Y)
    assert re.search(rf"^const SPOT_X = {data.SPOT_X};$", scene, re.M)
    assert f"ground: {data.GROUND}" in scene and f"width: {data.FIELD_WIDTH}" in scene
    assert re.search(rf"^const GROUND = {data.GROUND};$", read("particles.js"), re.M)


def test_the_page_draws_the_bots_effects():
    particles = read("particles.js")
    for name in ("GOLD", "BLOOD", "TRAIL", "SMOKE", "BLAST", "BOMB_BLAST"):
        found = re.search(rf"^(?:export )?const {name} = (\d+);", particles, re.M)
        assert found and int(found.group(1)) == getattr(shots, name), name


def test_the_setup_offers_the_bots_difficulties():
    page = read("index.html")
    assert re.findall(r'data-difficulty="(\w+)"', page) == list(data.DIFFICULTIES)
    assert re.findall(r'data-board="(\w+)"', page) == list(data.DIFFICULTIES)


def test_the_art_and_sounds_are_all_there():
    art = json.loads(read("art/flash.json"))
    for page in art["atlas"]["pages"]:
        assert (WEB / "art" / page).is_file(), page
    for name in ("ennemy", "turret", "base_player", "base_comp", "bg", "menu", *shots.KINDS):
        assert name in art["exports"], name
    for special in (1, 2, 4, 5):
        assert f"special{special}" in art["exports"]
    sounds = js_list(read("sound.js"), "EFFECTS")
    for sound in [*sounds, 1035]:
        assert (WEB / "sounds" / f"{sound}.mp3").is_file(), sound
    for sprite in art["sprites"].values():
        for sound in (sprite.get("a") or {}).values():
            assert sound in sounds, sound


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


def test_the_preview_recording_matches_the_battle_code():
    # Recorded again with `python -m ageofwar.tests.demo` whenever this fails
    assert demo.dump(demo.record()) == read("demo.json")


def test_the_preview_plays_at_the_bots_update_rate():
    assert match.TICK_RATE * match.STEPS == data.FPS
    assert "(FPS / 2)" in read("game.js") and match.STEPS == 2
