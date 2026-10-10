"""Everything that flies and can hurt: the turrets' bullets, the specials' meteors, arrows, bombs and beams, and the
burning bits, oil drops and shrapnel some of them throw. Each kind follows its own sprite's script in the original.

A shot hurts the first enemy whose hit box holds its point, then it is gone. The original removed the shot on a hit
and its position stopped counting, so nothing else in that frame could be hit by it.
"""

import math
import typing as t

from .data import GROUND

if t.TYPE_CHECKING:
    from .battle import Battle

# What the pages draw each kind as (the original's export names), by the number snapshots send
KINDS = (
    "bullet1",
    "bullet2",
    "bullet3",
    "bullet4",
    "bullet5",
    "bullet6",
    "bullet7",
    "bullet8",
    "bullet9",
    "bullet10",
    "bullet11",
    "bullet12",
    "bulletspecial1",
    "bulletspecial2",
    "bulletspecial4",
    "bulletspecial5",
    "part5",
    "part8",
    "part11",
)
CODES = {name: code for code, name in enumerate(KINDS)}

# Cosmetic particles the pages make themselves, by the original's part number
GOLD, BLOOD, DEBRIS, TRAIL, SMOKE, BLAST, SPLASH, RUBBLE, BOMB_BLAST = 1, 2, 3, 4, 6, 7, 9, 10, 12


def radians(degrees: float) -> float:
    return degrees * 0.017453292519943295


def flash_rotation(degrees: float) -> float:
    """Flash keeps _rotation between -180 and 180"""
    degrees = math.fmod(degrees, 360)
    if degrees > 180:
        degrees -= 360
    elif degrees <= -180:
        degrees += 360
    return degrees


class Shot:
    kind = ""

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        self.battle = battle
        self.x, self.y = x, y
        self.rotation = flash_rotation(rotation)
        self.damage = damage
        self.side = side
        self.scale = 100
        self.alive = True
        self.uid = battle.next_uid()

    def frame(self) -> None:
        """One frame of flight. The battle starts calling it the frame after the shot is made, like a newly
        attached clip"""
        raise NotImplementedError

    def struck(self) -> t.Any:
        return self.battle.struck(self.x, self.y, self.side)

    def die(self) -> None:
        self.alive = False

    def view(self) -> list:
        return [self.uid, CODES[self.kind], round(self.x * 10), round(self.y * 10), round(self.rotation), self.scale]


class Lobbed(Shot):
    """A rock, an egg or a stone ball on an arc, turning as it flies"""

    kind = "bullet1"
    lead = 5
    gravity = 0.05
    spin = 2

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        self.xs = 7 * math.cos(radians(self.rotation))
        self.ys = 7 * math.sin(radians(self.rotation))
        self.g = 0.0
        self.launch()

    def launch(self) -> None:
        self.x += self.xs * self.lead
        self.y += self.ys * self.lead

    def frame(self) -> None:
        self.g += self.gravity
        self.x += self.xs
        self.y += self.ys + self.g
        self.rotation = flash_rotation(self.rotation + self.spin)
        if self.y > GROUND:
            self.landed()
            self.die()
            return
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.damage)
            self.hit(target)
            self.die()

    def landed(self) -> None:
        self.battle.effect(DEBRIS, self.x, self.y, 7)

    def hit(self, target: t.Any) -> None:
        self.battle.effect(DEBRIS, self.x, self.y, 4)
        self.battle.bleed(target)


class Egg(Lobbed):
    kind = "bullet2"
    lead = 4

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        self.spin = battle.random_int(6) - 3

    def landed(self) -> None:
        pass

    def hit(self, target: t.Any) -> None:
        pass


class Boulder(Lobbed):
    """The catapults' stones start from the arm's tip: the original moves them up by the throw's sideways speed"""

    kind = "bullet3"

    def launch(self) -> None:
        if self.side == 1:
            self.y -= self.xs * 5
        else:
            self.y += self.xs * 5


class Firepot(Boulder):
    kind = "bullet4"
    spin = 6

    def landed(self) -> None:
        for _ in range(3):
            self.battle.add(Flame(self.battle, self.x, self.y, 0, 0, self.side))
        self.battle.effect(SMOKE, self.x, self.y, 1)
        self.battle.effect(BLAST, self.x, self.y, 1)

    def hit(self, target: t.Any) -> None:
        for _ in range(3):
            self.battle.add(Flame(self.battle, self.x, self.y, 0, 0, self.side))
        self.battle.effect(BLAST, self.x, self.y, 1)
        self.battle.bleed(target)


class OilPour(Shot):
    """The oil pot pours a drop every other frame for a second, a little way out from the base"""

    kind = "bullet5"

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        self.x += 116 if side == 1 else -116
        self.y += 7
        self.timer = 40
        self.count = 0

    def frame(self) -> None:
        self.timer -= 1
        self.count += 1
        if self.count == 2:
            self.battle.add(OilDrop(self.battle, self.x, self.y, 0, self.damage, self.side))
            self.count = 0
        if self.timer <= 0:
            self.die()


class Cannonball(Shot):
    """Fast shots that move in four small steps each frame, with a little drop"""

    kind = "bullet6"
    # Times it moves and checks for hits each frame
    steps = 4
    gravity = 0.02

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        self.xs = 7 * math.cos(radians(self.rotation))
        self.ys = 7 * math.sin(radians(self.rotation))
        self.x += self.xs * 5
        self.y += self.ys * 5
        self.g = 0.0

    def frame(self) -> None:
        for _ in range(self.steps):
            self.g += self.gravity
            self.x += self.xs
            self.y += self.ys + self.g
            if self.y > GROUND:
                self.landed()
                self.die()
                return
            target = self.struck()
            if target is not None:
                self.battle.hurt(target, self.damage)
                self.hit(target)
                self.die()
                return

    def landed(self) -> None:
        self.battle.effect(RUBBLE, self.x, self.y, 5)

    def hit(self, target: t.Any) -> None:
        self.battle.effect(RUBBLE, self.x, self.y, 5)
        self.battle.bleed(target)


class Shell(Cannonball):
    """The explosives cannon's shell bursts into burning shrapnel"""

    kind = "bullet7"

    def landed(self) -> None:
        for _ in range(4):
            self.battle.add(Shrapnel(self.battle, self.x, self.y, 0, 0, self.side))
        self.battle.effect(BLAST, self.x, self.y, 1)

    def hit(self, target: t.Any) -> None:
        for _ in range(3):
            self.battle.add(Shrapnel(self.battle, self.x, self.y, 0, 0, self.side))
        self.battle.effect(BLAST, self.x, self.y, 1)
        self.battle.bleed(target)


class Bullet(Cannonball):
    kind = "bullet8"

    def landed(self) -> None:
        pass

    def hit(self, target: t.Any) -> None:
        self.battle.bleed(target)


class Rocket(Shot):
    """Starts slow and speeds up 1% every eighth of a frame, in a straight line"""

    kind = "bullet9"
    steps = 8
    lead = 200
    # The laser kinds stop speeding up past this, and the rocket never does
    top_speed: float | None = None

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        self.xs = 0.2 * math.cos(radians(self.rotation))
        self.ys = 0.2 * math.sin(radians(self.rotation))
        self.x += self.xs * self.lead
        self.y += self.ys * self.lead

    def frame(self) -> None:
        for _ in range(self.steps):
            if self.top_speed is None or self.xs < self.top_speed:
                self.x += self.xs
                self.y += self.ys
                self.xs *= 1.01
                self.ys *= 1.01
            if self.y > GROUND:
                self.landed()
                self.die()
                return
            target = self.struck()
            if target is not None:
                self.battle.hurt(target, self.damage)
                self.hit(target)
                self.die()
                return
        if not -2000 < self.x < 3000 or not -2000 < self.y < 3000:
            # The original kept shots that flew off the field forever, out of sight
            self.die()

    def landed(self) -> None:
        self.battle.effect(BLAST, self.x, self.y, 1)

    def hit(self, target: t.Any) -> None:
        self.battle.effect(BLAST, self.x, self.y, 1)
        self.battle.bleed(target)


class Laser(Rocket):
    kind = "bullet10"
    lead = 42
    top_speed = 15

    def landed(self) -> None:
        pass

    def hit(self, target: t.Any) -> None:
        self.battle.bleed(target)


class Ion(Laser):
    kind = "bullet11"


class Titanium(Laser):
    kind = "bullet12"
    lead = 100


class Meteor(Shot):
    """The first age's special: rocks falling from the sky onto the middle of the field"""

    kind = "bulletspecial1"

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, rotation, damage, side)
        rotation = 80 + battle.random_int(20)
        x = battle.random_int(500) + 200
        if side == 2:
            rotation, x = 180 - rotation, battle.width - x
        self.rotation = flash_rotation(rotation)
        self.xs = 10 * math.cos(radians(rotation))
        self.ys = 10 * math.sin(radians(rotation))
        self.x, self.y = float(x), -100.0
        self.g = 0.0
        self.scale = battle.random_int(70) + 120

    def frame(self) -> None:
        self.g += 0.05
        self.x += self.xs
        self.y += self.ys + self.g
        self.trail()
        if self.y > GROUND:
            self.landed()
            self.die()
            return
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.damage)
            self.hit(target)
            self.die()

    def trail(self) -> None:
        self.battle.effect(TRAIL, self.x, self.y, 1, round(self.rotation))

    def landed(self) -> None:
        self.battle.effect(DEBRIS, self.x, self.y - 10, 7)

    def hit(self, target: t.Any) -> None:
        self.battle.effect(DEBRIS, self.x, self.y, 4)
        self.battle.bleed(target)


class Arrow(Meteor):
    """The second age's special: a rain of arrows"""

    kind = "bulletspecial2"

    def trail(self) -> None:
        pass

    def landed(self) -> None:
        pass

    def hit(self, target: t.Any) -> None:
        self.battle.bleed(target)


class Bomb(Shot):
    """Dropped by the fourth age's plane: keeps some of the plane's speed and falls faster and faster"""

    kind = "bulletspecial4"

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, 0, damage, side)
        self.xs = 4.0 if side == 1 else -4.0
        self.ys = 1.0
        self.g = 0.0
        self.spin = battle.random_int(10) - 5

    def fall(self) -> None:
        if self.g < 15:
            self.g += 0.2
        self.xs /= 1.02
        self.x += self.xs
        self.y += self.ys + self.g
        self.rotation = flash_rotation(self.rotation + self.spin)

    def frame(self) -> None:
        self.fall()
        if self.y > GROUND:
            self.battle.effect(BOMB_BLAST, self.x, self.y, 1)
            self.die()
            return
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.damage)
            self.battle.effect(BOMB_BLAST, self.x, self.y, 1)
            self.battle.bleed(target)
            self.die()


class Beam(Bomb):
    """One strike of the last age's laser: it checks for a hit once, then it is gone"""

    kind = "bulletspecial5"

    def frame(self) -> None:
        self.fall()
        if self.y > GROUND:
            self.die()
            return
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.damage)
            self.battle.bleed(target)
        self.die()


class Flame(Shot):
    """A burning bit thrown up by the fire catapult. It only hurts on the way down"""

    kind = "part5"
    burn = 10

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, 0, damage, side)
        angle = -90 + (battle.random_int(60) - 30)
        self.rotation = flash_rotation(angle)
        self.xs = 7 * math.cos(radians(angle))
        self.ys = 7 * math.sin(radians(angle)) + battle.random()
        self.g = 0.0
        self.spin = battle.random_int(20) - 10

    def frame(self) -> None:
        self.g += 0.2
        self.x += self.xs
        self.y += self.ys + self.g
        self.turn()
        if self.ys + self.g <= 0:
            return
        if self.y > GROUND:
            self.battle.effect(BLAST, self.x, self.y, 1)
            self.battle.effect(SMOKE, self.x, self.y, 1)
            self.die()
            return
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.burn)
            self.battle.effect(BLAST, self.x, self.y, 1)
            self.battle.bleed(target)
            self.die()

    def turn(self) -> None:
        self.rotation = flash_rotation(self.rotation + self.spin)


class Shrapnel(Flame):
    kind = "part11"
    burn = 30

    def turn(self) -> None:
        self.rotation = 0


class OilDrop(Shot):
    """Boiling oil falling straight down from the pot"""

    kind = "part8"

    def __init__(self, battle: "Battle", x: float, y: float, rotation: float, damage: float, side: int):
        super().__init__(battle, x, y, 0, damage, side)
        self.x += battle.random() * 2 - 1
        self.y += battle.random() * 2 - 1
        self.g = 1.0
        self.spin = battle.random_int(4) - 1.5

    def frame(self) -> None:
        self.g += 0.2
        self.y += self.g
        self.rotation = flash_rotation(self.rotation + self.spin)
        target = self.struck()
        if target is not None:
            self.battle.hurt(target, self.damage)
            self.battle.effect(SPLASH, self.x, self.y, 3)
            self.battle.bleed(target, 2)
            self.die()
            return
        if self.y > GROUND:
            self.die()


# The bullet each turret's "bullet" number makes
BULLETS: dict[int, type[Shot]] = {
    1: Lobbed,
    2: Egg,
    3: Boulder,
    4: Firepot,
    5: OilPour,
    6: Cannonball,
    7: Shell,
    8: Bullet,
    9: Rocket,
    10: Laser,
    11: Ion,
    12: Titanium,
}
