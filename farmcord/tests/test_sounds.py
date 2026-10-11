import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
SOUNDS = WEB / "sounds"
MUSIC = WEB / "music"

EFFECTS = [
    "step",
    "hoe",
    "plant",
    "water",
    "refill",
    "harvest",
    "exceptional",
    "clear",
    "feed",
    "chicken",
    "goose",
    "pig",
    "goat",
    "cow",
    "horse",
    "birth",
    "buy",
    "sell",
    "levelup",
    "achievement",
    "refused",
    "tap",
    "door",
    "rain",
]


def manifest():
    return json.loads((SOUNDS / "sounds.json").read_text(encoding="utf-8"))


def is_mp3(path):
    head = path.read_bytes()[:3]
    return head == b"ID3" or (head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


def test_manifest_lists_every_effect_and_the_music():
    assert sorted(manifest()) == sorted([*EFFECTS, "music"])


def test_every_effect_file_exists():
    data = manifest()
    for name in EFFECTS:
        assert (SOUNDS / data[name]).is_file(), name


def test_effects_are_small_mp3s():
    data = manifest()
    for name in EFFECTS:
        path = SOUNDS / data[name]
        assert is_mp3(path), name
        assert 0 < path.stat().st_size < 100 * 1024, name


def test_music_file_exists_and_has_a_title():
    music = manifest()["music"]
    assert music["title"].strip()
    path = MUSIC / music["file"]
    assert path.is_file()
    assert is_mp3(path)
