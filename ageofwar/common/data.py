"""The original game's numbers, from its main script (root frame 13) and the base and menu scripts.

Every time is in frames of the original's 40 a second clock, and every place is in the original's pixels: the field
is 1000 wide, and the ground is at y 425.
"""

from dataclasses import dataclass

FPS = 40
GROUND = 425
FIELD_WIDTH = 1000
AGES = 5


@dataclass(frozen=True)
class UnitKind:
    name: str
    cost: int
    # Frames to train, after the ones queued before it
    train: int
    health: int
    damage: int
    ranged_damage: int
    melee_range: int
    shoot_range: int


@dataclass(frozen=True)
class TurretKind:
    name: str
    cost: int
    # Frames between shots while something is in range (the firing animation can make it longer)
    reload: int
    bullet: int
    damage: int
    range: int


# EN (name, cost, training frames) and ES (health, damage, ranged damage, melee range, shoot range)
UNITS = {
    1: UnitKind("Club man", 15, 40, 55, 16, 0, 20, 0),
    2: UnitKind("Slingshot man", 25, 40, 42, 10, 8, 20, 100),
    3: UnitKind("Dino rider", 100, 100, 160, 40, 0, 45, 0),
    4: UnitKind("Sword man", 50, 70, 100, 35, 0, 20, 0),
    5: UnitKind("Archer", 75, 50, 80, 20, 9, 20, 130),
    6: UnitKind("Knight", 500, 100, 300, 60, 0, 60, 0),
    7: UnitKind("Dueler", 200, 100, 200, 79, 0, 25, 0),
    8: UnitKind("Mousquettere", 400, 100, 160, 40, 20, 25, 130),
    9: UnitKind("Canoneer", 1000, 200, 600, 120, 0, 25, 0),
    10: UnitKind("Melee Infantry", 1500, 100, 350, 100, 0, 25, 0),
    11: UnitKind("Infantry", 2000, 100, 300, 60, 30, 25, 130),
    12: UnitKind("Tank", 7000, 300, 1200, 300, 0, 100, 0),
    13: UnitKind("God's Blade", 5000, 100, 1000, 250, 0, 40, 0),
    14: UnitKind("Blaster", 6000, 100, 800, 130, 80, 40, 130),
    15: UnitKind("War machine", 20000, 300, 3000, 600, 0, 100, 0),
    16: UnitKind("Super Soldier", 150000, 100, 4000, 400, 400, 40, 150),
}

# TU (name, cost) and TS (frames between shots, bullet, damage, range)
TURRETS = {
    1: TurretKind("Rock slingshot", 100, 30, 1, 12, 350),
    2: TurretKind("Egg automatic", 200, 11, 2, 5, 300),
    3: TurretKind("Primitive Catapult", 500, 70, 3, 25, 400),
    4: TurretKind("Catapult", 500, 70, 3, 40, 400),
    5: TurretKind("Fire Catapult", 750, 70, 4, 50, 400),
    6: TurretKind("Oil", 1000, 100, 5, 4, 300),
    7: TurretKind("Small Cannon", 1500, 70, 6, 30, 500),
    8: TurretKind("Large Cannon", 3000, 70, 6, 70, 500),
    9: TurretKind("Explosives Cannon", 6000, 70, 7, 100, 500),
    10: TurretKind("Single Turret", 7000, 40, 8, 70, 500),
    11: TurretKind("Rocket Turret", 9000, 50, 9, 100, 500),
    12: TurretKind("Double Turret", 14000, 22, 8, 60, 500),
    13: TurretKind("Titanium Shooter", 24000, 40, 12, 100, 400),
    14: TurretKind("LazerCannon", 40000, 10, 10, 40, 500),
    15: TurretKind("IonRay", 100000, 10, 11, 60, 500),
}

# Experience needed to reach ages 2 to 5 (EV). Evolving doesn't spend it
EVOLVE_XP = (4000, 14000, 45000, 200000)
# Each new age adds this times the new age's number to the base's health and its most
EVOLVE_HEALTH = 300
# The price of the second, third and fourth turret spots
SPOT_PRICES = (1000, 3000, 7500)
SPOTS = 4
# Turret spots, from the base's position: across, then up for spots 1 to 4
SPOT_X = 52
SPOT_Y = (-80, -125, -172, -220)
START_CASH = 175
BASE_HEALTH = 500
# Where each side's base stands, where its turrets hang from, and where its new units appear
BASE_X = {1: 50, 2: 950}
BASE_ART_X = {1: 0, 2: 1000}
SPAWN_X = {1: 150, 2: 860}
# Queued units, including the one in training
TRAY = 5
SPECIAL_COOLDOWN = 2000
SPEED = 0.7
# A unit looks this far ahead for something in its way, and for an enemy
SIGHT = 300
# A dead unit lies there this long before it goes
CORPSE_FRAMES = 80
# A reward is the unit's price times this, and the killer gets that in cash and twice that in experience
REWARD = 1.3

# The computer's units are this much stronger on each difficulty, as in the original's three buttons
DIFFICULTIES = {"normal": 1.0, "harder": 1.3, "impossible": 2.0}

STATES = ("idle", "walk", "attack", "die", "shoot", "shootwalk")


def age_units(age: int) -> tuple[int, ...]:
    """The units an age can train: three of its own, and the Super Soldier in the last age"""
    first = (age - 1) * 3 + 1
    units = (first, first + 1, first + 2)
    return units + (16,) if age == AGES else units


def age_turrets(age: int) -> tuple[int, ...]:
    first = (age - 1) * 3 + 1
    return (first, first + 1, first + 2)


def reward(kind: int) -> int:
    return flash_round(UNITS[kind].cost * REWARD)


def flash_round(value: float) -> int:
    """ActionScript's Math.round: halves go up, also below zero"""
    whole = int(value // 1)
    return whole + 1 if value - whole >= 0.5 else whole
