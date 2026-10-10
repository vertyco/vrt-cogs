"""The original's computer opponent (base_comp's script). It never earns or spends money: it runs on timers.

Every second it rolls a 30% chance to train a unit, picked at random from the first one, two or three of its age's
units as time goes on, and it keeps no more than six alive. Turrets come and go at fixed times in each age, and it
moves to the next age every 200 seconds, until the last one.
"""

import typing as t

from .data import AGES, EVOLVE_HEALTH, UNITS

if t.TYPE_CHECKING:
    from .battle import Battle, Side

ROLL_EVERY = 40
TRAIN_CHANCE = 0.3
MAX_ALIVE = 6
AGE_FRAMES = 8000
# Frames into an age when the computer can pick from two, then three, of the age's units
SECOND_UNIT = 1500
THIRD_UNIT = 5000

# Frames into each age -> what happens: ("sell", spot), ("build", spot, turret) and ("spots", count of extra spots)
PLAN: dict[int, dict[int, list[tuple]]] = {
    1: {
        1000: [("build", 1, 1)],
        4000: [("sell", 1), ("build", 1, 2)],
        6000: [("sell", 1), ("build", 1, 3)],
    },
    2: {
        1000: [("sell", 1), ("build", 1, 4)],
        4000: [("spots", 1), ("sell", 1), ("build", 1, 6)],
        6000: [("build", 2, 5)],
    },
    3: {
        1000: [("sell", 1), ("build", 1, 7)],
        4000: [("spots", 2), ("sell", 2), ("build", 2, 7)],
        6000: [("sell", 2), ("sell", 1), ("build", 3, 9)],
    },
    4: {
        5000: [("build", 1, 10)],
        7000: [("spots", 2), ("sell", 3), ("sell", 1), ("build", 2, 11)],
    },
    5: {
        5000: [("build", 1, 13)],
        12000: [("sell", 2), ("sell", 1), ("sell", 3), ("build", 2, 14)],
        20000: [("spots", 3), ("sell", 2), ("sell", 1), ("sell", 3), ("build", 4, 15)],
    },
}


class Computer:
    def __init__(self, side: "Side"):
        self.side = side
        self.age_timer = 0
        self.roll_timer = 0
        self.unit_level = 1
        self.wants_unit = False
        # Frames until the unit in training appears. Below -5 means it is ready to start another
        self.train_left = -1
        self.train_total = 1
        self.next_unit = 0

    def tick(self, battle: "Battle") -> None:
        side = self.side
        self.age_timer += 1
        if self.unit_level == 1 and self.age_timer == SECOND_UNIT:
            self.unit_level = 2
        elif self.unit_level == 2 and self.age_timer == THIRD_UNIT:
            self.unit_level = 3
        if self.age_timer == AGE_FRAMES and side.age != AGES:
            side.age += 1
            side.base.health += EVOLVE_HEALTH * side.age
            side.base.max_health += EVOLVE_HEALTH * side.age
            self.unit_level = 1
            self.age_timer = 0
        for step in PLAN[side.age].get(self.age_timer, ()):
            self.follow(battle, step)
        self.roll(battle)

    def follow(self, battle: "Battle", step: tuple) -> None:
        side = self.side
        if step[0] == "sell":
            side.turrets[step[1] - 1] = None
        elif step[0] == "spots":
            side.addons = step[1]
        elif side.turrets[step[1] - 1] is None:
            battle.place_turret(side.number, step[2], step[1])

    def roll(self, battle: "Battle") -> None:
        self.roll_timer += 1
        if self.roll_timer == ROLL_EVERY:
            # Once a second: a 30% chance it wants a unit until the next roll
            self.wants_unit = battle.random() < TRAIN_CHANCE
            self.roll_timer = 0
        if self.wants_unit and self.train_left < -5 and self.side.alive + self.queued() < MAX_ALIVE:
            kind = battle.random_int(self.unit_level) + 1 + (self.side.age - 1) * 3
            self.next_unit = kind
            self.train_left = self.train_total = UNITS[kind].train
            self.wants_unit = False
        if self.train_left == 0:
            battle.spawn(self.side.number, self.next_unit)
        self.train_left -= 1

    def queued(self) -> int:
        """The unit in training already counts toward the six, as the original counted it when training began"""
        return 1 if self.train_left >= 0 else 0

    def progress(self) -> int:
        if self.train_left < 0:
            return 0
        return round(100 - self.train_left / self.train_total * 100)
