"""The browser preview's recording: two computer tanks trading shots, sent by the bot's own match code.
After changing how a match plays, run `python -m tanks.tests.demo` from the repo root to record it again"""

import asyncio
import json
import random
from pathlib import Path

from tanks.common.cpu import Brain
from tanks.common.items import Kit
from tanks.common.match import DT, PLAYING, TICK_RATE, Match
from tanks.tests.fakes import Clock, FakeConn, FakeRoom

DEMO = Path(__file__).resolve().parents[1] / "web" / "demo.json"
SEED = 3
LANDSCAPE = 2
SHOTS = 6
LIMIT_SECONDS = 120


async def record() -> list:
    """Every message a watcher gets, as [update number, message], from the round's start to the snapshot after
    the last shot"""
    room, clock = FakeRoom(), Clock()
    match = Match(room, lambda results: None, lambda match: None, rng=random.Random(SEED), clock=clock)
    watcher = FakeConn(room, 1)
    for number, level in ((0, "hard"), (1, "normal")):
        seat = match.seats[number]
        seat.level, seat.name, seat.kit, seat.brain = level, f"CPU {number + 1}", Kit(), Brain(level)
    match.landscape = LANDSCAPE
    match.start_round()
    messages = []
    shots = 0
    for tick in range(LIMIT_SECONDS * TICK_RATE):
        if (shots >= SHOTS and not match.firing) or match.stage != PLAYING:
            break
        before = len(watcher.sent)
        clock.now += DT
        await match.tick()
        for message in watcher.sent[before:]:
            messages.append([tick, message])
            shots += "shot" in message
    return messages


def dump(messages: list) -> str:
    return json.dumps(messages, separators=(",", ":"))


if __name__ == "__main__":
    DEMO.write_text(dump(asyncio.run(record())), encoding="utf-8")
