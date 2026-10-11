import json
import struct
from pathlib import Path

import pytest

from farmcord.catalog import ACHIEVEMENTS, ANIMALS, CANS, COSMETICS, CROPS, HOES
from farmcord.game.calendar import SEASONS

ART = Path(__file__).resolve().parents[1] / "web" / "art"
MAX_SHEET = 2048
CROP_STAGES = ("seed", "sprout", "growing", "ripe", "dried", "withered")
SCENES = ("farmhouse", "market", "pond", "trough_feed", "trough_water", "sign", "fence", "gate")
FARMER_LAYERS = ["base", "top", "bottom", "hat"]


def art():
    return json.loads((ART / "art.json").read_text(encoding="utf-8"))


def sheets():
    """(sheet JSON path, sheet data) for every sheet art.json lists"""
    out = []
    for entry in art()["sheets"]:
        path = ART / entry["file"]
        out.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return out


def frames():
    return {name: frame for _, data in sheets() for name, frame in data["frames"].items()}


def png_size(path):
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", head[16:24])


def required_frames():
    keys = {"soil/untilled", "soil/tilled", "crop/rotted", "icon/coin", "icon/xp"}
    for crop in CROPS:
        keys |= {f"crop/{crop}/{stage}" for stage in CROP_STAGES}
        keys |= {f"icon/seed:{crop}", f"icon/crop:{crop}", f"icon/crop:{crop}:x"}
    keys |= {f"icon/feed:{animal}" for animal in ANIMALS}
    keys |= {f"icon/can_{can.tier}" for can in CANS} | {f"icon/hoe_{hoe.tier}" for hoe in HOES}
    keys |= {f"badge/{key}" for key in ACHIEVEMENTS}
    keys |= {f"decor/{item.key}" for item in COSMETICS.values() if item.kind == "decoration"}
    keys |= {f"scene/{name}" for name in SCENES}
    keys |= {f"scene/{name}_{season}" for name in art()["seasonal_scenes"] for season in SEASONS}
    return keys


def test_art_json_lists_sheets_images_and_animations():
    data = art()
    assert data["sheets"] and data["images"] and data["animations"]
    assert data["seasons"] == list(SEASONS)
    assert data["farmer"]["layers"] == FARMER_LAYERS


def test_every_file_art_json_names_exists():
    for path, data in sheets():
        assert path.is_file(), path
        assert (path.parent / data["meta"]["image"]).is_file(), data["meta"]["image"]
    for key, image in art()["images"].items():
        assert (ART / image["file"]).is_file(), key


def test_every_frame_is_inside_its_sheet():
    for path, data in sheets():
        w, h = png_size(path.parent / data["meta"]["image"])
        assert w <= MAX_SHEET and h <= MAX_SHEET, path
        assert (data["meta"]["size"]["w"], data["meta"]["size"]["h"]) == (w, h), path
        assert float(data["meta"]["scale"]) > 0, path
        for name, frame in data["frames"].items():
            r, trim, canvas = frame["frame"], frame["spriteSourceSize"], frame["sourceSize"]
            assert r["x"] >= 0 and r["y"] >= 0 and r["x"] + r["w"] <= w and r["y"] + r["h"] <= h, name
            assert trim["x"] >= 0 and trim["y"] >= 0, name
            assert trim["x"] + trim["w"] <= canvas["w"] and trim["y"] + trim["h"] <= canvas["h"], name
            assert 0 <= frame["anchor"]["x"] <= 1 and 0 <= frame["anchor"]["y"] <= 1, name


def test_every_catalog_key_has_a_picture():
    missing = required_frames() - set(frames())
    assert not missing, sorted(missing)


def test_seasonal_scenes_cover_the_world_and_trees():
    seasonal = art()["seasonal_scenes"]
    assert {"farmhouse", "market", "pond", "fence"} <= set(seasonal)
    assert any(name.startswith("tree_") for name in seasonal)
    assert any(name.startswith("bush_") for name in seasonal)


def test_backgrounds_cover_every_season():
    images = art()["images"]
    wanted = {"room/farmhouse_inside", "ground/path"}
    wanted |= {f"ground/{season}" for season in SEASONS} | {f"sky/{season}" for season in SEASONS}
    assert wanted <= set(images)
    for key in wanted:
        assert images[key]["w"] > 0 and images[key]["h"] > 0, key


def check_animation(key, info, names):
    assert info["frames"] > 0, key
    for n in range(info["frames"]):
        assert f"{key}/{n}" in names, f"{key}/{n}"
    for clip, c in info["clips"].items():
        assert c["count"] > 0 and c["fps"] > 0, (key, clip)
        assert 0 <= c["start"] and c["start"] + c["count"] <= info["frames"], (key, clip)


@pytest.mark.parametrize("kind", list(ANIMALS))
def test_every_animal_has_a_baby_and_an_adult(kind):
    animations, names = art()["animations"], set(frames())
    adults = (
        [f"animal/{kind}/adult"]
        if f"animal/{kind}/adult" in animations
        else [f"animal/{kind}/adult/male", f"animal/{kind}/adult/female"]
    )
    for key in [f"animal/{kind}/baby", *adults]:
        assert key in animations, key
        assert "idle_front" in animations[key]["clips"], key
        check_animation(key, animations[key], names)


def test_farmer_layers_stack_on_one_canvas():
    animations, all_frames = art()["animations"], frames()
    base = animations["farmer/base"]
    check_animation("farmer/base", base, set(all_frames))
    pieces = [f"farmer/{item.kind}/{item.key}" for item in COSMETICS.values() if item.kind != "decoration"]
    for key in pieces:
        assert key in animations, key
        assert animations[key]["clips"] == base["clips"], key
        check_animation(key, animations[key], set(all_frames))
        for n in range(base["frames"]):
            ours, theirs = all_frames[f"{key}/{n}"], all_frames[f"farmer/base/{n}"]
            assert ours["sourceSize"] == theirs["sourceSize"], f"{key}/{n}"
            assert ours["anchor"] == theirs["anchor"], f"{key}/{n}"


def test_art_folder_stays_small():
    total = sum(path.stat().st_size for path in ART.rglob("*") if path.is_file())
    assert total < 15 * 1024 * 1024
