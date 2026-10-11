"""Small battles for the engine tests"""

import random

from botarena3.common.battle import Battle

LIGHT = 'AKAUMIN "DLZ-100"'
BIG = 'XEROI "DELIVERANCE"'
AURO = 'SANTRIN "AURO"'
THICK = 'KURON "SHRED-MK3"'
LP = 'ZINTEK "LP"'
FIREWORKS = 'KEDRON "SPKL-D4"'
REPAIR = 'ZENI "PRS"'


class ZeroRandom(random.Random):
    """Every random(n) is 0: spreads are all the way to one side, waits and jitters are as short as they go"""

    def randrange(self, *args, **kwargs):
        return 0


def robot(name="R", weapon=LP, plating=AURO, chassis=LIGHT) -> dict:
    return {"name": name, "chassis": chassis, "plating": plating, "weapon": weapon}


def battle(left: list[dict], right: list[dict], *, owned=(True, False), draws=False, rng=None) -> Battle:
    return Battle((left, right), (1, 9), owned=owned, draws=draws, rng=rng or ZeroRandom())


def place(robot, x, y, rot) -> None:
    robot.x, robot.y, robot.rot = x, y, rot


def shots(events: list) -> list[int]:
    return [event[0] for event in events if event[1] == "shot"]
