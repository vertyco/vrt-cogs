"""The page's files follow the hub's rules, and every module, picture, sound, action and season it names exists"""

import json
import re
from pathlib import Path

from farmcord.catalog import ACHIEVEMENTS, ANIMALS, CANS, COSMETICS, CROPS, HOES, ROOMS
from farmcord.game.calendar import SEASONS
from farmcord.main import FarmCord
from farmcord.tests.fakes import FakeBot

WEB = Path(__file__).resolve().parents[1] / "web"
ART = json.loads((WEB / "art" / "art.json").read_text(encoding="utf-8"))
SOUNDS = json.loads((WEB / "sounds" / "sounds.json").read_text(encoding="utf-8"))
# The page's own scripts, not the bundled PixiJS
SCRIPTS = sorted(WEB.glob("*.js"))
# A literal art key in the page's code, like "icon/coin" or "scene/gate"
ART_KEY = re.compile(r"[\"`]((?:icon|scene|decor|ground|sky|room|farmer|crop|soil|badge|animal)/[\w:/]+)[\"`]")


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
    """The top-level keys of an object literal's body"""
    found, depth = set(), 0
    for match in re.finditer(r'[{}\[\]]|"?(\w+)"?\s*:', text):
        token = match.group(0)
        if token in "{[":
            depth += 1
        elif token in "}]":
            depth -= 1
        elif depth == 0:
            found.add(match.group(1))
    return found


def art_keys() -> set[str]:
    frames = set()
    for sheet in ART["sheets"]:
        frames |= set(json.loads((WEB / "art" / sheet["file"]).read_text(encoding="utf-8"))["frames"])
    return frames | set(ART["images"]) | set(ART["animations"])


def test_the_page_follows_the_hubs_file_rules():
    index = source("index.html")
    assert "<head>" in index
    assert not re.search(r'(src|href)="/', index), "paths must be relative"
    files = [path for path in WEB.rglob("*") if path.is_file()]
    assert not [path for path in files if path.suffix == ".webp"], "the hub serves .webp without a type"
    assert sum(path.stat().st_size for path in files) < 20 * 1024 * 1024
    assert (WEB / "fonts" / "fredoka.woff2").exists() and (WEB / "fonts" / "OFL.txt").exists()
    assert (WEB / "vendor" / "PIXI-LICENSE.txt").exists()


def test_every_file_the_page_loads_exists():
    index = source("index.html")
    for path in re.findall(r'(?:src|href)="([^"#]+)"', index):
        assert (WEB / path).exists(), path
    for script in SCRIPTS:
        for path in re.findall(r'(?:from|import\()\s*"(\./[^"]+)"', script.read_text(encoding="utf-8")):
            assert (WEB / path).exists(), f"{script.name} imports {path}"
    assert 'url("fonts/fredoka.woff2")' in source("style.css")


def test_every_art_key_the_page_names_exists():
    known = art_keys()
    named = {key for script in SCRIPTS for key in ART_KEY.findall(script.read_text(encoding="utf-8"))}
    assert named, "the page names no art"
    assert sorted(named - known) == []
    # Keys the page builds from the state: each tool tier, each season's sky and ground, soil, and every crop at every
    # stage and spoil
    built = {f"icon/can_{can.tier}" for can in CANS} | {f"icon/hoe_{hoe.tier}" for hoe in HOES}
    built |= {f"{kind}/{season}" for kind in ("sky", "ground") for season in SEASONS}
    built |= {"soil/untilled", "soil/tilled"}
    stages = ("seed", "sprout", "growing", "ripe", "dried", "withered")
    built |= {f"crop/{crop}/{stage}" for crop in CROPS for stage in stages}
    assert sorted(built - known) == []


def test_every_picture_the_market_builds_exists():
    """The shop's rows: every seed, crop and feed icon, each decoration, each outfit piece on the standing farmer's
    frame, and each animal's baby and grown-up looks on their front idle's first frame"""
    known = art_keys()
    built = {f"icon/seed:{crop}" for crop in CROPS} | {f"icon/feed:{animal}" for animal in ANIMALS}
    built |= {f"icon/crop:{crop}{grade}" for crop in CROPS for grade in ("", ":x")}
    stand = ART["animations"]["farmer/base"]["clips"]["stand_front"]["start"]
    for item in COSMETICS.values():
        built.add(f"decor/{item.key}" if item.kind == "decoration" else f"farmer/{item.kind}/{item.key}/{stand}")
    animations = ART["animations"]
    for kind in ANIMALS:
        looks = {f"animal/{kind}/baby"} | {look for look in animations if look.startswith(f"animal/{kind}/adult")}
        built |= {f"{look}/{animations[look]['clips']['idle_front']['start']}" for look in looks}
    assert sorted(built - known) == []


def test_every_picture_the_farmhouse_builds_exists():
    """The board's badges and the wardrobe's farmer: the plain farmer and each outfit piece on the standing frame"""
    known = art_keys()
    built = {f"badge/{key}" for key in ACHIEVEMENTS}
    stand = ART["animations"]["farmer/base"]["clips"]["stand_front"]["start"]
    built.add(f"farmer/base/{stand}")
    built |= {f"farmer/{item.kind}/{item.key}/{stand}" for item in COSMETICS.values() if item.kind != "decoration"}
    assert sorted(built - known) == []
    assert ART["farmer"]["layers"] == ["base", "top", "bottom", "hat"]


def test_the_extra_rooms_are_the_bots():
    """The farmhouse's extra rooms in the page's map carry the catalog's numbers and names, in order"""
    found = re.findall(r'extraRoom\((\d+), "([^"]+)"', source("rooms.js"))
    assert found == [(str(room.number), room.name) for room in ROOMS.values()]


def test_every_animal_has_a_baby_and_a_grown_up_look_with_an_idle():
    """The pen draws a baby, and a grown-up per sex where the art has one (chickens, cows), else a shared one"""
    animations = ART["animations"]
    for kind in ANIMALS:
        looks = [f"animal/{kind}/baby"]
        for sex in ("male", "female"):
            sexed = f"animal/{kind}/adult/{sex}"
            looks.append(sexed if sexed in animations else f"animal/{kind}/adult")
        for look in looks:
            assert "idle_front" in animations[look]["clips"], look


def test_every_scene_piece_in_every_room_has_a_picture_for_every_season():
    known = art_keys()
    pieces = set(re.findall(r'art: "(\w+)"', source("rooms.js"))) | {"fence", "gate"}
    for name in pieces:
        for season in SEASONS:
            key = f"scene/{name}_{season}" if name in ART["seasonal_scenes"] else f"scene/{name}"
            assert key in known, key


def test_every_sound_the_page_plays_exists():
    played = set()
    for script in SCRIPTS:
        text = script.read_text(encoding="utf-8")
        played |= set(re.findall(r'play\("(\w+)"\)', text))
    game = source("game.js")
    played |= set(re.findall(r': "(\w+)"', block(game, "ACTION_SOUNDS")))
    # Sounds a view passes to act() instead of the action's own, and each animal's voice when it is tapped
    for script in SCRIPTS:
        played |= set(re.findall(r'sound: "(\w+)"', script.read_text(encoding="utf-8")))
    played |= set(ANIMALS)
    played |= set(re.findall(r': "(\w+)"', block(game, "NEWS_SOUNDS")))
    played.add("rain")
    assert {"step", "tap", "door", "refused"} <= played
    assert sorted(played - set(SOUNDS)) == []
    for name in played:
        assert (WEB / "sounds" / SOUNDS[name]).exists(), name
    assert (WEB / "music" / SOUNDS["music"]["file"]).exists()


def test_action_sounds_name_real_actions():
    actions = set(FarmCord(FakeBot()).action_handlers())
    assert keys(block(source("game.js"), "ACTION_SOUNDS")) <= actions


def test_seasons_and_weather_match_the_bots():
    assert keys(block(source("hud.js"), "SEASONS")) == set(SEASONS)
    assert keys(block(source("hud.js"), "WEATHER")) == {"sun", "rain", "snow"}
    assert keys(block(source("scene.js"), "SKY_TOP")) == set(SEASONS)
    assert keys(block(source("scene.js"), "FENCE")) == set(SEASONS)
    assert tuple(ART["seasons"]) == SEASONS
