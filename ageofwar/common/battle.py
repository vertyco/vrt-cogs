"""One battle, frame by frame at the original's 40 a second: two bases, the units they train, their turrets, specials,
and every shot in the air. Nothing here knows about Discord, so the tests drive it directly.

Side 1 is the left base and side 2 the right one. Each side is played by a person or by the original's computer
(cpu.py). The rules are the original's for both: the computer just never spends money, as in the original.
"""

import math
import random
import typing as t

from .anims import BASE_BOXES, HITZONES, TURRET_ANIMS, UNIT_ANIMS
from .data import (
    AGES,
    BASE_ART_X,
    BASE_HEALTH,
    BASE_X,
    CORPSE_FRAMES,
    EVOLVE_HEALTH,
    EVOLVE_XP,
    FIELD_WIDTH,
    GROUND,
    SIGHT,
    SPAWN_X,
    SPECIAL_COOLDOWN,
    SPEED,
    SPOT_PRICES,
    SPOT_X,
    SPOT_Y,
    SPOTS,
    START_CASH,
    STATES,
    TRAY,
    TURRETS,
    UNITS,
    age_turrets,
    age_units,
    flash_round,
    reward,
)
from .shots import BLOOD, BULLETS, GOLD, Arrow, Beam, Bomb, Meteor, Shot
from .timeline import Timeline

if t.TYPE_CHECKING:
    from .cpu import Computer

# How a special's falling things hurt, and how long the healing lasts
SPECIAL_DAMAGE = {1: 200, 2: 200, 4: 400, 5: 1000}
HEAL_FRAMES = 600
# How long each special's thrower stays, and how often it throws (frames)
RAIN_FRAMES = 200
RAIN_EVERY = {1: 9, 2: 5}
PLANE_EVERY = 15
BEAM_EVERY = 5
BEAM_FRAMES = 57


class Base:
    """A side's base, which units and shots treat like one more fighter standing in the field"""

    kind = 0

    def __init__(self, side: int):
        self.side = side
        self.x = float(BASE_X[side])
        self.health = float(BASE_HEALTH)
        self.max_health = float(BASE_HEALTH)
        self.box = BASE_BOXES[side]
        self.half_width = (self.box[2] - self.box[0]) / 2
        self.height = self.box[3] - self.box[1]
        self.gone = False


class Unit:
    def __init__(self, uid: int, kind: int, side: int, x: float, strength: float):
        stats = UNITS[kind]
        self.uid = uid
        self.kind = kind
        self.side = side
        self.x = x
        self.health = stats.health * strength
        self.max_health = self.health
        self.damage = stats.damage * strength
        self.ranged_damage = stats.ranged_damage * strength
        self.melee_range = stats.melee_range
        self.shoot_range = stats.shoot_range
        self.reward = reward(kind)
        self.box = HITZONES[kind]
        self.half_width = (self.box[2] - self.box[0]) / 2
        self.height = self.box[3] - self.box[1]
        self.facing = 1 if side == 1 else -1
        self.speed = SPEED * self.facing
        # Frames until the next look around, then every 5
        self.look_in = 3
        # Distances ahead, in the direction the unit walks: to whatever is closest, and to the nearest enemy's edge
        self.closest = float(SIGHT)
        self.enemy_gap = float(SIGHT)
        self.limit = 100.0
        self.target: Unit | Base | None = None
        self.dead = False
        self.dead_for = 0
        self.gone = False
        self.state = ""
        self.anim: Timeline | None = None


class Turret:
    def __init__(self, kind: int, side: int, spot: int, rng: random.Random):
        stats = TURRETS[kind]
        self.kind = kind
        self.side = side
        self.spot = spot
        self.stats = stats
        self.x = float(BASE_ART_X[side] + (SPOT_X if side == 1 else -SPOT_X))
        self.y = float(GROUND + SPOT_Y[spot - 1])
        self.rotation = 0.0 if side == 1 else -180.0
        self.look_in = 0
        self.wait = 0
        self.gap = 100000.0
        self.target_height = 0.0
        self.target: Unit | Base | None = None
        self.anim = Timeline(TURRET_ANIMS[kind][1], rng)


class Side:
    def __init__(self, number: int):
        self.number = number
        self.cash = START_CASH
        self.xp = 0
        self.age = 1
        self.addons = 0
        self.turrets: list[Turret | None] = [None] * SPOTS
        self.tray = [0] * TRAY
        self.training = 0
        self.train_left = -1
        self.train_total = 0
        self.special_timer = SPECIAL_COOLDOWN - 1
        self.healing = 0
        # Living units, which the computer keeps to six
        self.alive = 0
        self.base = Base(number)
        # The computer's units are this much stronger
        self.strength = 1.0
        self.cpu: "Computer | None" = None


class Special:
    """The thing a special leaves on the field: a rain of meteors or arrows, the plane, or the laser"""

    def __init__(self, age: int, side: int, born: int):
        self.age = age
        self.side = side
        self.born = born
        self.uid = 0
        self.timer = RAIN_FRAMES
        self.count = 0
        self.frames = 0
        self.alive = True
        mirror = side == 2
        if age == 4:
            self.x, self.y = (FIELD_WIDTH + 100.0, 200.0) if mirror else (-100.0, 200.0)
        elif age == 5:
            self.x, self.y = (FIELD_WIDTH - 150.0, float(GROUND)) if mirror else (150.0, float(GROUND))
        else:
            self.x, self.y = 0.0, 0.0


class Battle:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.width = FIELD_WIDTH
        self.sides = {1: Side(1), 2: Side(2)}
        # The original's list of everything that can be fought: both bases, then units in the order they appeared.
        # Units leave it when they die, and every search walks it from the end
        self.field: list[Unit | Base] = [self.sides[1].base, self.sides[2].base]
        self.units: list[Unit] = []
        self.unit_born: dict[int, int] = {}
        self.shots: list[Shot] = []
        self.shot_born: dict[int, int] = {}
        self.specials: list[Special] = []
        self.events: list[list] = []
        self.frame = 0
        self.uid = 0
        self.winner: int | None = None

    # ---------- Helpers the shots and the computer use ----------

    def next_uid(self) -> int:
        self.uid += 1
        return self.uid

    def random(self) -> float:
        return self.rng.random()

    def random_int(self, below: int) -> int:
        """ActionScript's random(n): a whole number from 0 to n - 1"""
        return int(self.rng.random() * below)

    def add(self, shot: Shot) -> None:
        self.shots.append(shot)
        self.shot_born[shot.uid] = self.frame

    def effect(self, part: int, x: float, y: float, count: int = 1, param: int = 0) -> None:
        self.events.append([part, round(x), round(y), count, param])

    def bleed(self, target: "Unit | Base", count: int = 5) -> None:
        """Blood where a unit was hit. Bases and the tank don't bleed"""
        if isinstance(target, Unit) and target.kind != 12:
            self.effect(BLOOD, target.x, GROUND - target.height / 1.5, count)

    def hurt(self, target: "Unit | Base", amount: float) -> None:
        target.health -= amount

    def struck(self, x: float, y: float, side: int) -> "Unit | Base | None":
        """The newest enemy of `side` whose hit box holds the point"""
        for fighter in reversed(self.field):
            if fighter.side == side:
                continue
            box = fighter.box
            if fighter.x + box[0] <= x <= fighter.x + box[2] and GROUND + box[1] <= y <= GROUND + box[3]:
                return fighter
        return None

    # ---------- One frame ----------

    def step(self) -> None:
        if self.winner is not None:
            return
        self.frame += 1
        for side in self.sides.values():
            self.tick_side(side)
        for unit in list(self.units):
            if self.unit_born[unit.uid] < self.frame:
                self.move_unit(unit)
        for unit in list(self.units):
            if unit.anim is not None and not unit.gone:
                self.unit_hooks(unit, unit.anim.advance())
        for side in self.sides.values():
            for turret in side.turrets:
                if turret is not None:
                    self.aim_turret(turret)
                    for _ in turret.anim.advance():
                        self.fire(turret)
        for special in list(self.specials):
            if special.born < self.frame:
                self.run_special(special)
        for shot in list(self.shots):
            if shot.alive and self.shot_born[shot.uid] < self.frame:
                shot.frame()
        self.tidy()
        self.check_bases()

    def paused_step(self) -> None:
        """One frame of a pause. The original's menu kept training a player's units through a pause, while the rest of
        the battle, the computer's base and the special's cooldown stood still. The new units wait at the base"""
        if self.winner is not None:
            return
        for side in self.sides.values():
            if side.cpu is None:
                self.tick_training(side)

    def tidy(self) -> None:
        for shot in self.shots:
            if not shot.alive:
                del self.shot_born[shot.uid]
        self.shots = [shot for shot in self.shots if shot.alive]
        for unit in self.units:
            if unit.gone:
                del self.unit_born[unit.uid]
        self.units = [unit for unit in self.units if not unit.gone]
        self.specials = [special for special in self.specials if special.alive]

    def check_bases(self) -> None:
        # The original ends the game once a base's rounded health drops below zero
        for number in (1, 2):
            if flash_round(self.sides[number].base.health) < 0:
                self.winner = 3 - number
                return

    def tick_side(self, side: Side) -> None:
        if side.cpu is not None:
            side.cpu.tick(self)
        else:
            self.tick_training(side)
        if side.special_timer < SPECIAL_COOLDOWN:
            side.special_timer += 1
        if side.healing > 0:
            side.healing -= 1

    def tick_training(self, side: Side) -> None:
        if side.train_left > 0:
            side.train_left -= 1
        if side.train_left == 0:
            self.spawn(side.number, side.training)
            side.training, side.train_total, side.train_left = 0, 0, -1
            side.tray = side.tray[1:] + [0]
            if side.tray[0]:
                self.start_training(side, side.tray[0])

    def start_training(self, side: Side, kind: int) -> None:
        if side.training == 0:
            side.training = kind
            side.train_left = side.train_total = UNITS[kind].train

    def spawn(self, side_number: int, kind: int) -> Unit:
        side = self.sides[side_number]
        # Each new unit stands a random fraction of a pixel forward, so two never share a spot
        unit = Unit(self.next_uid(), kind, side_number, SPAWN_X[side_number] + self.random(), side.strength)
        self.units.append(unit)
        self.unit_born[unit.uid] = self.frame
        self.field.append(unit)
        side.alive += 1
        return unit

    # ---------- Units ----------

    def move_unit(self, unit: Unit) -> None:
        if unit.health <= 0:
            self.unit_dying(unit)
            return
        if self.sides[unit.side].healing > 0 and unit.health < unit.max_health:
            unit.health += 1
        moving = abs(unit.closest) > unit.limit
        if moving:
            unit.x += unit.speed
        melee = abs(unit.enemy_gap) < unit.melee_range
        ranged = not melee and abs(unit.enemy_gap) < unit.shoot_range
        state = None
        if not melee and not moving and not ranged:
            state = "idle"
        elif melee and not moving:
            state = "attack"
        elif ranged:
            state = "shootwalk" if moving else "shoot"
        elif moving and not melee:
            state = "walk"
        if state is not None:
            self.set_state(unit, state)
        unit.look_in -= 1
        if unit.look_in == 0:
            self.look(unit)
            unit.look_in = 5

    def set_state(self, unit: Unit, state: str) -> None:
        """Like gotoAndStop on the unit's animations: a new state starts its animation from the top"""
        if state != unit.state:
            unit.state = state
            unit.anim = Timeline(UNIT_ANIMS[unit.kind][state][1], self.rng)

    def look(self, unit: Unit) -> None:
        """What's closest ahead (to stop behind it) and the nearest enemy ahead (to fight it), up to 300 away"""
        unit.target = None
        unit.closest = float(SIGHT)
        unit.enemy_gap = float(SIGHT)
        for other in reversed(self.field):
            gap = (other.x - unit.x) * unit.facing
            if gap <= 0:
                continue
            if unit.closest > gap:
                unit.closest = gap
                unit.limit = unit.half_width + other.half_width + 2
            if other.side != unit.side and unit.enemy_gap > gap - other.half_width:
                unit.enemy_gap = gap - other.half_width
                unit.target = other

    def unit_hooks(self, unit: Unit, hooks: list[str]) -> None:
        for hook in hooks:
            if hook in ("hit", "rhit") and unit.target is not None and not unit.target.gone:
                target = unit.target
                damage = unit.ranged_damage if hook == "rhit" else unit.damage
                self.hurt(target, damage - self.random() * 2)
                self.bleed(target)

    def unit_dying(self, unit: Unit) -> None:
        if not unit.dead:
            unit.dead = True
            self.field.remove(unit)
            mine, theirs = self.sides[unit.side], self.sides[3 - unit.side]
            mine.alive -= 1
            theirs.cash += unit.reward
            theirs.xp += unit.reward * 2
            mine.xp += flash_round(unit.reward / 2)
            self.effect(GOLD, unit.x, GROUND - unit.height, 1, unit.reward)
            self.effect(BLOOD, unit.x, GROUND - unit.height / 1.5, 9)
        self.set_state(unit, "die")
        unit.dead_for += 1
        if unit.dead_for > CORPSE_FRAMES:
            unit.gone = True

    # ---------- Turrets ----------

    def aim_turret(self, turret: Turret) -> None:
        turret.look_in += 1
        if turret.look_in == 10:
            turret.look_in = 0
            turret.gap = 100000.0
            for other in reversed(self.field):
                gap = math.hypot(other.x - turret.x, GROUND - turret.y)
                if other.side != turret.side and turret.gap > gap:
                    turret.gap = gap
                    turret.target_height = other.height
                    turret.target = other
        if turret.gap >= turret.stats.range:
            return
        target = turret.target
        if turret.kind != 6 and target is not None and not target.gone:
            aim_y = GROUND - turret.target_height / 1.3
            turret.rotation = float(round(math.degrees(math.atan2(aim_y - turret.y, target.x - turret.x))))
        turret.wait += 1
        if turret.wait >= turret.stats.reload:
            turret.anim.play()
            turret.wait = 0

    def fire(self, turret: Turret) -> None:
        stats = turret.stats
        self.add(BULLETS[stats.bullet](self, turret.x, turret.y, turret.rotation, stats.damage, turret.side))

    # ---------- Specials ----------

    def run_special(self, special: Special) -> None:
        special.frames += 1
        special.count += 1
        if special.age in (1, 2):
            special.timer -= 1
            if special.count == RAIN_EVERY[special.age]:
                kind = Meteor if special.age == 1 else Arrow
                self.add(kind(self, special.x, special.y, 0, SPECIAL_DAMAGE[special.age], special.side))
                special.count = 0
            special.alive = special.timer > 0
        elif special.age == 4:
            self.fly_plane(special)
        elif special.age == 5:
            self.sweep_beam(special)

    def fly_plane(self, special: Special) -> None:
        ahead = special.x < 700 if special.side == 1 else special.x > FIELD_WIDTH - 700
        if special.count == PLANE_EVERY and ahead:
            self.add(Bomb(self, special.x, special.y, 0, SPECIAL_DAMAGE[4], special.side))
            special.count = 0
        special.x += 4 if special.side == 1 else -4
        special.alive = special.x <= FIELD_WIDTH if special.side == 1 else special.x >= 0

    def sweep_beam(self, special: Special) -> None:
        ahead = special.x < 700 if special.side == 1 else special.x > FIELD_WIDTH - 700
        if special.count == BEAM_EVERY and ahead:
            reach = 30 if special.side == 1 else -30
            self.add(Beam(self, special.x + reach, special.y - 5, 0, SPECIAL_DAMAGE[5], special.side))
            special.x += 50 if special.side == 1 else -50
            special.count = 0
        # The laser's own animation ends on its 57th frame, and that removes it
        special.alive = special.frames < BEAM_FRAMES - 1

    # ---------- What a person can do ----------

    def buy_unit(self, number: int, kind: int) -> bool:
        side = self.sides[number]
        if kind not in age_units(side.age) or side.cash < UNITS[kind].cost or 0 not in side.tray:
            return False
        side.cash -= UNITS[kind].cost
        slot = side.tray.index(0)
        side.tray[slot] = kind
        if slot == 0:
            self.start_training(side, kind)
        return True

    def build_turret(self, number: int, kind: int, spot: int) -> bool:
        side = self.sides[number]
        if kind not in age_turrets(side.age) or not 1 <= spot <= side.addons + 1:
            return False
        if side.turrets[spot - 1] is not None or side.cash < TURRETS[kind].cost:
            return False
        side.cash -= TURRETS[kind].cost
        self.place_turret(number, kind, spot)
        return True

    def place_turret(self, number: int, kind: int, spot: int) -> None:
        self.sides[number].turrets[spot - 1] = Turret(kind, number, spot, self.rng)

    def sell_turret(self, number: int, spot: int) -> bool:
        side = self.sides[number]
        turret = side.turrets[spot - 1] if 1 <= spot <= SPOTS else None
        if turret is None:
            return False
        side.cash += flash_round(TURRETS[turret.kind].cost / 2)
        side.turrets[spot - 1] = None
        return True

    def add_spot(self, number: int) -> bool:
        side = self.sides[number]
        if side.addons >= len(SPOT_PRICES) or side.cash < SPOT_PRICES[side.addons]:
            return False
        side.cash -= SPOT_PRICES[side.addons]
        side.addons += 1
        return True

    def evolve(self, number: int) -> bool:
        side = self.sides[number]
        if side.age >= AGES or side.xp < EVOLVE_XP[side.age - 1]:
            return False
        self.advance_age(side)
        return True

    def advance_age(self, side: Side) -> None:
        side.age += 1
        side.base.max_health += EVOLVE_HEALTH * side.age
        side.base.health += EVOLVE_HEALTH * side.age

    def special(self, number: int) -> bool:
        side = self.sides[number]
        if side.special_timer < SPECIAL_COOLDOWN:
            return False
        side.special_timer = 0
        if side.age == 3:
            side.healing = HEAL_FRAMES
            return True
        special = Special(side.age, number, self.frame)
        special.uid = self.next_uid()
        self.specials.append(special)
        return True

    # ---------- What the pages see ----------

    def view(self) -> dict:
        events, self.events = self.events, []
        return {
            "f": self.frame,
            "u": [self.unit_view(unit) for unit in self.units],
            "b": [shot.view() for shot in self.shots],
            "x": [[s.uid, s.age, s.side, round(s.x * 10), round(s.y * 10)] for s in self.specials],
            "s": [self.side_view(self.sides[1]), self.side_view(self.sides[2])],
            "e": events,
        }

    def unit_view(self, unit: Unit) -> list:
        state = STATES.index(unit.state) if unit.state else 0
        frame = unit.anim.frame if unit.anim is not None else 1
        health = max(0, min(100, round(unit.health / unit.max_health * 100)))
        return [unit.uid, unit.kind, unit.side, round(unit.x * 10), state, frame, health]

    def side_view(self, side: Side) -> list:
        turrets = [
            [turret.kind, round(turret.rotation), turret.anim.frame] if turret is not None else 0
            for turret in side.turrets
        ]
        if side.cpu is not None:
            training = side.cpu.next_unit if side.cpu.queued() else 0
            progress = side.cpu.progress()
        else:
            training = side.training
            progress = 0 if side.train_total <= 0 else round(100 - side.train_left / side.train_total * 100)
        return [
            side.cash,
            side.xp,
            side.age,
            side.addons,
            flash_round(side.base.health),
            round(side.base.max_health),
            training,
            progress,
            side.tray,
            side.special_timer,
            turrets,
            side.healing > 0,
        ]
