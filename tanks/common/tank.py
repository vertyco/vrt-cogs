"""One tank on the field: the original's frame-by-frame driving, hill climbing, falling, parachutes and fall
damage, and how a tank takes damage. Every number here is the original's, per frame at 25 frames a second"""

import math
import random
from dataclasses import dataclass, field

from .items import (
    FUEL,
    PARACHUTES,
    SHIELD_STRENGTH,
    SUPER_SHIELD,
    UP_ARMOR,
    UP_ENGINE,
    UP_HILL,
    Kit,
)
from .terrain import HEIGHT, WIDTH, Field, flash_random, js_round

# The tank's drawn box around its position, which Flash's hit tests use
BODY = (-6.45, -2.25, 6.50, 4.13)
# The original walks this many pixels of ground under the tank each frame (the box's width)
SPAN = 12.95
# The tracks: only they stand on the ground
TRACKS = (-4.75, 2.51, 4.75, 4.13)
# A new tank's first frame also draws a wider shadow, which flattens the ground it lands on
SPAWN_BOX = (-8.0, -2.25, 8.0, 4.25)
SHIELD_BOX = (-21.4, -21.4, 21.4, 21.4)
SUPER_SHIELD_BOX = (-20.75, -21.4, 22.05, 21.4)
DRIVE_STEP = 0.5
BUMP_BACK = 0.6
HILL_PUSH = 0.7
MIN_X = 10
MAX_X = 540
# Falling: speed gained per ground column checked, the parachute's steady speed, and when it opens
FALL_GAIN = 0.01
CHUTE_SPEED = 0.2
CHUTE_OPENS = 0.2
FELL_OFF_COST = 2000
KILL_REWARD = 5000
SUICIDE_COST = 2000
HIT_REWARD = 100
SELF_HIT_COST = 50


def box(x: float, y: float, rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (x + rect[0], y + rect[1], x + rect[2], y + rect[3])


def overlaps(a: tuple, b: tuple) -> bool:
    """Flash's hitTest between two clips: do their boxes touch"""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def armor(level: int) -> float:
    """The share of damage that gets through, from the original's upgrade loop: about 1/1.12 per level"""
    factor = step = 1.0
    for _ in range(level):
        factor /= 1.12 / step
        step /= 1.0002
    return factor


def driving_fall_damage(fall: float) -> int:
    """A person's tank driving off a ledge: gentle up to a point, then deadly"""
    return js_round(fall * 25) if fall < 2 else js_round(fall * fall * 3000)


def landing_fall_damage(fall: float) -> int:
    """A tank landing after its ground was blown away, and a computer tank on its own turn"""
    return js_round(fall * 25) if fall < 0.8 else js_round(fall * fall * 80)


@dataclass
class Tank:
    seat: int
    kit: Kit
    x: float
    y: float = 0.0
    energy: float = 100.0
    # Barrel angle in degrees: 0 points left, 90 up, 180 right
    angle: int = 90
    power: float = 50.0
    fuel: float = 0.0
    alive: bool = True
    # The raised shield's extras number, and what it can still absorb
    shield: int | None = None
    shield_left: float = 0.0
    fall: float = 0.0
    grounded: bool = False
    chute_out: bool = False
    # One parachute pays for every fall until this tank's next turn
    chute_paid: bool = False
    can_left: bool = True
    can_right: bool = True
    # Settling after a shot, until the tank stops moving
    settling: bool = False
    steady: bool = False
    recent: list = field(default_factory=list)
    # A kill is paid once, however many blasts hit the wreck
    kill_paid: bool = False
    # Where this tank's last shot ended, which computer tanks aim from
    last_shot: tuple[float, float] | None = None

    @property
    def max_energy(self) -> int:
        return self.kit.max_energy

    @property
    def hittable(self) -> bool:
        return self.alive and self.energy > 0

    def body_box(self) -> tuple:
        return box(self.x, self.y, BODY)

    def shield_box(self) -> tuple | None:
        if self.shield is None:
            return None
        return box(self.x, self.y, SUPER_SHIELD_BOX if self.shield == SUPER_SHIELD else SHIELD_BOX)

    def hit_box(self) -> tuple:
        """What a shell flying at this tank hits: the shield when one is up"""
        return self.shield_box() or self.body_box()

    def touched_by(self, area: tuple) -> bool:
        shield = self.shield_box()
        return overlaps(area, self.body_box()) or (shield is not None and overlaps(area, shield))

    def raise_shield(self, kind: int) -> None:
        self.kit.extras[kind] -= 1
        self.shield = kind
        self.shield_left = SHIELD_STRENGTH[kind]

    def start_turn(self) -> None:
        self.chute_paid = False

    def view(self) -> dict:
        return {
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "angle": self.angle,
            "power": round(self.power),
            "health": max(0, round(self.energy)),
            "max": self.max_energy,
            "fuel": max(0, round(self.fuel)),
            "alive": self.alive,
            "shield": self.shield,
            "shieldLeft": round(self.shield_left),
            "chute": self.chute_out,
            "money": round(self.kit.money),
            "score": round(self.kit.score),
            "kills": self.kit.kills,
        }


# ---------- Damage ----------


def hurt(tank: Tank, amount: float, attacker: Tank, fall: bool = False) -> None:
    """The original's damage(): a shield soaks blasts, armor softens what gets through, and money follows damage.
    Falls skip the shield and cost a third as much"""
    if tank.shield is None or fall:
        tank.energy -= amount * armor(tank.kit.extras[UP_ARMOR])
    else:
        hit_shield(tank, amount, attacker)
    # Power can't be more than health, as in the original, so a hurt tank's power drops with it
    tank.power = min(tank.power, max(0.0, tank.energy))
    if tank.energy <= 0 and not tank.kill_paid:
        tank.kill_paid = True
        if attacker is not tank:
            attacker.kit.kills += 1
            attacker.kit.money += KILL_REWARD
            attacker.kit.score += KILL_REWARD
        else:
            tank.kit.kills -= 1
            tank.kit.money -= SUICIDE_COST
            tank.kit.score -= SUICIDE_COST
    if attacker is not tank:
        attacker.kit.money += amount * HIT_REWARD
        attacker.kit.score += amount * HIT_REWARD
        return
    if fall:
        amount /= 3
    cost = js_round(amount * SELF_HIT_COST)
    tank.kit.money = max(0, tank.kit.money - cost)
    tank.kit.score -= cost


def hit_shield(tank: Tank, amount: float, attacker: Tank) -> None:
    """A shield absorbs until it breaks, and what breaks through it hits the tank twice as hard"""
    tank.shield_left -= amount
    if tank.shield_left <= 0:
        overflow = abs(tank.shield_left) * 2
        tank.shield, tank.shield_left = None, 0.0
        hurt(tank, overflow, attacker)


def check_death(tank: Tank) -> bool:
    """Run every frame: below the field or out of health. True when the tank just died"""
    if not tank.alive:
        return False
    if tank.y > HEIGHT:
        tank.kit.money = max(0, tank.kit.money - FELL_OFF_COST)
        tank.energy = 0
    if tank.energy > 0:
        return False
    tank.energy = 0
    tank.alive = False
    tank.shield, tank.shield_left, tank.chute_out = None, 0.0, False
    return True


# ---------- Placing ----------


def place(field_: Field, seats: list[int], rng: random.Random) -> list[float]:
    """Each tank's spot: a random column that isn't a pit, spread apart by the original's rule"""
    spacing = 350 / len(seats)
    xs: list[float] = []
    for _ in seats:
        x = open_column(field_, rng)
        tries = 0
        while any(other - spacing < x < other + spacing for other in xs) and tries < 10000:
            x = open_column(field_, rng)
            tries += 1
        xs.append(x)
    return xs


def open_column(field_: Field, rng: random.Random) -> int:
    x = flash_random(rng, 500) + 20
    while field_.top(x) > HEIGHT:
        x = flash_random(rng, 500) + 20
    return x


def land(tank: Tank, field_: Field, rng: random.Random) -> None:
    """A new tank's first frame: sit on its column, flatten the ground under its shadow, and pick a barrel angle"""
    tank.y = field_.top(js_round(tank.x)) - 4
    shadow = box(tank.x, tank.y, SPAWN_BOX)
    for i in range(math.ceil(SPAWN_BOX[2] - SPAWN_BOX[0])):
        column = math.floor(tank.x - 8 + i)
        if 0 <= column < WIDTH and field_.tops[column] <= shadow[3]:
            field_.tops[column] = tank.y + 3.25
    tank.angle = flash_random(rng, 67) * 2 + 46
    tank.power = 50
    tank.energy = tank.max_energy
    tank.fuel = tank.kit.extras[FUEL]


# ---------- Moving ----------


def hill_check(tank: Tank, field_: Field) -> None:
    """test_hill(): a wall taller than the tank can climb pushes it back and stops it driving this frame"""
    limit = tank.y - (0.5 + tank.kit.extras[UP_HILL] - tank.fall * 10)
    left = tank.x - SPAN / 2
    right = tank.x + SPAN / 2
    if field_.top(math.ceil(left)) < limit or field_.top(math.floor(left)) < limit:
        tank.x += HILL_PUSH
        tank.steady = False
        tank.can_left = tank.can_right = False
    elif field_.top(math.floor(right)) < limit or field_.top(math.ceil(right)) < limit:
        tank.x -= HILL_PUSH
        tank.steady = False
        tank.can_left = tank.can_right = False
    else:
        tank.can_left = tank.can_right = True


def touches(tank: Tank, column: int, top: float) -> bool:
    tracks = box(tank.x, tank.y, TRACKS)
    return tracks[0] <= column + 0.5 and column - 0.5 <= tracks[2] and top <= tracks[3]


def ground_pass(tank: Tank, field_: Field, landing, settling: bool) -> None:
    """One frame's walk over the ground under the tank: landing (with fall damage), standing on the highest column,
    and falling where nothing holds it. Falling happens per column checked, as in the original"""
    highest = 500.0
    found = False
    for i in range(math.ceil(SPAN)):
        column = js_round(tank.x - SPAN / 2 + i)
        top = field_.top(column)
        if touches(tank, column, top):
            tank.chute_out = False
            if tank.fall > 0.4:
                hurt(tank, landing(tank.fall), tank, fall=True)
            tank.grounded = True
            tank.fall = 0.0
        if top < highest and tank.grounded:
            found = True
            highest = top
        if i + 1 >= SPAN and tank.grounded and found:
            tank.y = highest - 2
            found = False
        if settling and tank.fall > 0.001:
            tank.steady = False
        if not tank.grounded:
            drop(tank, field_.wind)


def drop(tank: Tank, wind: float) -> None:
    if tank.fall >= CHUTE_OPENS and (tank.chute_paid or tank.kit.extras[PARACHUTES] > 0):
        if not tank.chute_paid:
            tank.chute_paid = True
            tank.kit.extras[PARACHUTES] -= 1
        tank.chute_out = True
    tank.y += tank.fall
    if tank.chute_out:
        tank.fall = CHUTE_SPEED
        tank.x += wind / 3000
    else:
        tank.fall += FALL_GAIN


def drive_frame(tank: Tank, field_: Field, tanks: list[Tank], direction: int, landing=driving_fall_damage) -> None:
    """One frame of the tank whose turn it is: drive, climb or fall, and keep power within health"""
    if direction < 0 and tank.can_left and tank.fuel > 0 and tank.x > MIN_X:
        move(tank, -DRIVE_STEP, tanks)
    elif direction > 0 and tank.can_right and tank.fuel > 0 and tank.x < MAX_X:
        move(tank, DRIVE_STEP, tanks)
    tank.grounded = False
    tank.can_left = tank.can_right = True
    hill_check(tank, field_)
    ground_pass(tank, field_, landing, settling=False)
    if tank.energy < tank.power:
        tank.power = tank.energy


def move(tank: Tank, step: float, tanks: list[Tank]) -> None:
    tank.x += step
    tank.fuel -= 1 / (tank.kit.extras[UP_ENGINE] + 1)
    for other in tanks:
        if other is not tank and other.alive and overlaps(tank.body_box(), other.body_box()):
            tank.x -= math.copysign(BUMP_BACK, step)


def start_settling(tank: Tank) -> None:
    tank.settling = True
    tank.grounded = False


def settle_frame(tank: Tank, field_: Field) -> None:
    """One frame of a tank settling after a shot: it falls until it lands, and is done once it stops moving"""
    hill_check(tank, field_)
    ground_pass(tank, field_, landing_fall_damage, settling=True)
    if tank.fall > 0.001:
        tank.steady = False
    hill_check(tank, field_)
    tank.recent = (tank.recent + [(js_round(tank.x), js_round(tank.y * 10) / 10)])[-3:]
    if len(tank.recent) == 3 and tank.recent[0] == tank.recent[2]:
        tank.steady = True
    if tank.steady:
        tank.settling = False
    tank.steady = True
