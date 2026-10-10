"""The browser preview's recording: the original's computer playing both bases, sent by the bot's own battle code.
After changing how a battle plays, run `python -m ageofwar.tests.demo` from the repo root to record it again"""

import json
import random
from pathlib import Path

from ageofwar.common.battle import Battle
from ageofwar.common.cpu import Computer
from ageofwar.common.match import STEPS

DEMO = Path(__file__).resolve().parents[1] / "web" / "demo.json"
SEED = 5
# The armies need this long to walk out and meet, so the recording starts when they do
WARMUP_FRAMES = 1700
RECORD_FRAMES = 1000
# The left base calls its meteor shower this far in, so the preview shows a special too
SPECIAL_AT = 300


def record() -> list:
    """Every update a watcher would get, in order"""
    battle = Battle(random.Random(SEED))
    for side in battle.sides.values():
        side.cpu = Computer(side)
    for _ in range(WARMUP_FRAMES):
        battle.step()
    battle.view()
    views = []
    for frame in range(0, RECORD_FRAMES, STEPS):
        if frame == SPECIAL_AT:
            battle.special(1)
        for _ in range(STEPS):
            battle.step()
        views.append(battle.view())
    return views


def dump(views: list) -> str:
    return json.dumps(views, separators=(",", ":"))


if __name__ == "__main__":
    DEMO.write_text(dump(record()), encoding="utf-8")
