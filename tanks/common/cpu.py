"""Computer tanks, ported from the original's five CPU scripts. They pick the nearest tank, open with a rough shot,
then correct from where their last shot landed. The five levels share one decision tree with different numbers.
Like the original's, they never shop and always fire the free Small missile"""

import math
from dataclasses import dataclass

from .physics import js_div
from .tank import Tank

LEVELS = ("very_easy", "easy", "normal", "hard", "very_hard")
LEVEL_NAMES = {
    "very_easy": "Very easy",
    "easy": "Easy",
    "normal": "Normal",
    "hard": "Hard",
    "very_hard": "Very hard",
}


@dataclass(frozen=True)
class Level:
    """One difficulty's numbers. `opening` divides the opening shot's power; the rest weigh each correction"""

    opening: float
    wind_change: float
    wind_reach: float
    reach: float
    reach_step: float
    height_reach: float
    height: float
    right_angle: float
    left_angle: float
    # The harder levels only correct a miss when it wasn't already a strong shot
    picky: bool
    # Very easy compares one angle the other way round (a slip in the original that makes it worse)
    slip: bool
    # Very hard also allows for wind and height in its opening shot
    sharp_opening: bool


TABLE = {
    "very_easy": Level(120, 7, 380, 10.9, 7, 30, 22, 100, 80, picky=False, slip=True, sharp_opening=False),
    "easy": Level(120, 99999, 380000, 25, 15, 3000, 22000, 100, 80, picky=False, slip=False, sharp_opening=False),
    "normal": Level(110, 15, 500, 18, 12, 50, 40, 106, 74, picky=True, slip=False, sharp_opening=False),
    "hard": Level(80, 11, 420, 14, 9, 40, 30, 102, 78, picky=True, slip=False, sharp_opening=False),
    "very_hard": Level(80, 7, 380, 10.9, 7, 30, 22, 100, 80, picky=True, slip=False, sharp_opening=True),
}


def side(value: float) -> int:
    """The original's p_m(): 1 for a positive number, -1 otherwise"""
    return 1 if value > 0 else -1


@dataclass
class Aim:
    """calc_shot()'s working numbers for one turn"""

    level: Level
    x: float
    y: float
    tx: float
    ty: float
    lx: float
    ly: float
    angle: float
    power: float
    wind: float
    last_wind: float
    plan_angle: float
    plan_power: float

    def __post_init__(self):
        self.last_dist = math.hypot(self.x - self.lx, self.y - self.ly)
        self.target_dist = math.hypot(self.x - self.tx, self.y - self.ty)
        self.x_miss = abs(self.lx - self.tx)
        self.y_miss = abs(self.ly - self.ty)
        level = self.level
        self.wind_reach = level.wind_reach
        self.reach_step = level.reach_step + abs(self.x - self.lx) / 80
        self.height = level.height
        spread = (200 - abs(self.x - self.tx)) / 30
        self.right_angle = level.right_angle - spread
        self.left_angle = level.left_angle + spread
        # The wind's pull on an upright shot, which the corrections lean against
        self.gust = self.wind / 7

    def windage(self) -> float:
        """How much the wind changed since the last shot, scaled by how far that shot went"""
        return js_div(
            self.wind - self.last_wind, self.level.wind_change - js_div(abs(self.lx - self.x), self.wind_reach)
        )

    def reach(self, offset: float, lean: float) -> float:
        """The miss in pixels turned into power, less for barrels leaning far from `lean` degrees"""
        return js_div(self.x_miss, self.level.reach + offset - js_div(abs(lean - self.angle), self.reach_step))

    def retry(self) -> bool:
        tried = self.last_dist > 60 or self.target_dist < 70 or self.power < 10
        if self.level.picky:
            return tried and (self.power < 70 or self.last_dist > 200)
        return tried


def plan_first(level: Level, me: Tank, target: Tank, wind: float) -> tuple[float, float]:
    """calc_first_shot(): 45 degrees toward the target, with power for the distance"""
    gap = abs(me.x - target.x)
    angle = 90 + side(target.x - me.x) * 45
    power = gap / (2 + gap / level.opening)
    if level.sharp_opening:
        power += -side(target.x - me.x) * wind / 13 + (me.y - target.y) / 20
    return angle, min(power, me.energy)


def plan_next(aim: Aim, energy: float) -> tuple[float, float]:
    """calc_shot(): correct the last plan from where the last shot landed"""
    if aim.x < aim.tx:
        aim_right(aim)
    else:
        aim_left(aim)
    return finish(aim, energy)


def finish(aim: Aim, energy: float) -> tuple[float, float]:
    """The end of calc_shot(): keep power within 100 and health, trading power for a steeper barrel at full power"""
    angle, power = aim.plan_angle, aim.plan_power
    if power > 100:
        power = 100
    if power >= energy:
        power = energy
        if aim.x < aim.tx:
            if angle < 135:
                if power > 70:
                    power -= (135 - angle) / 2.5
                angle += (135 - angle) / 3
        elif angle > 45:
            if power > 70:
                power -= (angle - 45) / 2.5
            angle -= (angle - 45) / 3
    power = max(power, 0)
    angle = min(max(angle, 0), 180)
    return angle, power


# ---------- Target to the right ----------


def aim_right(aim: Aim) -> None:
    aim.wind_reach -= (180 - aim.angle) * 3
    aim.height += (135 - aim.angle) * 1.7
    if aim.lx < aim.x:
        aim.plan_angle += (aim.x - aim.lx) / 10 + (aim.tx - aim.x) / 20 - aim.wind / 50
    elif aim.retry():
        right_retry(aim)
    elif aim.y - aim.ty > 100 and aim.tx - aim.x < 100:
        aim.plan_angle -= (aim.angle - (aim.right_angle - aim.gust)) / 2
    else:
        aim.plan_angle -= (aim.angle - (aim.right_angle - aim.gust)) / 2 - (aim.tx - aim.x) / 100


def right_retry(aim: Aim) -> None:
    if aim.lx >= aim.tx:
        if aim.x_miss > 20:
            aim.plan_power -= aim.reach(2.5, 135) + aim.windage() - js_div(aim.ly - aim.ty, aim.height)
        else:
            aim.plan_power -= aim.reach(-1, 135) + aim.windage()
    elif aim.ly < aim.ty:
        if aim.ty < aim.y:
            right_short_below(aim)
        else:
            right_short_above(aim)
    elif (aim.last_dist < 150 and aim.tx - aim.x < 170) or aim.last_dist >= 100 or aim.power < 30:
        if aim.ty < aim.y or not aim.ty - aim.y > 100:
            aim.plan_power += aim.reach(0, 135) - aim.windage() + js_div(aim.ly - aim.ty, aim.height)
        else:
            aim.plan_power += aim.reach(0, 135) - aim.windage()
    elif aim.angle < aim.right_angle - 5:
        aim.plan_angle += (135 - aim.angle) / 10 + aim.tx - aim.x / 100
    else:
        aim.plan_angle -= (aim.angle - (aim.right_angle - aim.gust)) / 2
        aim.plan_power += aim.reach(0, 135) / 1.5 + (aim.angle - (aim.right_angle - aim.gust)) / 5


def right_short_below(aim: Aim) -> None:
    """Short, with the target higher up than this tank"""
    tilt = aim.right_angle - aim.gust
    if (
        aim.y - aim.ty > 80
        and 20 < aim.y_miss < 80
        and aim.last_dist < 100
        and aim.target_dist > 220
        and aim.power > 30
        and aim.angle > tilt
    ):
        aim.plan_angle -= (aim.angle - tilt) / 4 + aim.wind / 20 - aim.target_dist / 100
    elif aim.angle < tilt or (aim.y_miss < 30 and aim.x_miss < 200):
        aim.plan_power += aim.reach(0, 135) - aim.windage() + js_div(aim.ly - aim.ty, aim.height)
    elif aim.y_miss >= 30:
        if aim.tx - aim.x > 300 and aim.power < 50 and aim.angle < 110:
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / 3) - aim.windage()
        elif aim.angle > tilt:
            right_steepen(aim, tilt, 1)


def right_short_above(aim: Aim) -> None:
    """Short, with the target level with or below this tank"""
    tilt = aim.right_angle - aim.gust
    if (
        aim.ty - aim.y < 70
        and 20 < aim.y_miss < 100
        and aim.last_dist < 100
        and aim.target_dist > 250
        and aim.power > 30
        and aim.angle > tilt
    ):
        aim.plan_angle -= (aim.angle - tilt) / 4.5 + aim.wind / 20 - aim.target_dist / 100
    elif aim.angle < tilt or (aim.y_miss < 30 and aim.x_miss < 200):
        aim.plan_power += aim.reach(0, 135) - aim.windage() + js_div(aim.ly - aim.ty, aim.height)
    elif aim.y_miss >= 30:
        if aim.ty - aim.y > 200 and aim.y < aim.ly:
            share = 1.5 if aim.plan_angle > 120 else 2
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / share) - aim.windage()
        elif aim.tx - aim.x > 300 and aim.power < 50 and aim.angle < 110:
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / 3) - aim.windage()
        elif aim.angle > tilt:
            right_steepen(aim, tilt, -1)


def right_steepen(aim: Aim, tilt: float, rise: int) -> None:
    """More power and a steeper barrel, for a shot that has to clear a height difference"""
    climb = rise * js_div(aim.y_miss, aim.level.height_reach)
    base = js_div(aim.x_miss, aim.level.reach * 2) - aim.windage() + climb - aim.wind / 15
    if aim.plan_angle <= 135:
        aim.plan_power += base + (135 - aim.angle) / 8 + (aim.angle - tilt) / 8
    else:
        aim.plan_power += base
    aim.plan_angle -= (aim.angle - tilt) / 4.5 + js_div(aim.y_miss, aim.level.height_reach)


# ---------- Target to the left ----------


def aim_left(aim: Aim) -> None:
    aim.wind_reach -= aim.angle * 3
    aim.height += (aim.angle - 45) * 1.7
    if aim.x < aim.lx:
        aim.plan_angle -= (aim.lx - aim.x) / 10 + (aim.x - aim.tx) / 20 + aim.wind / 50
    elif aim.retry():
        left_retry(aim)
    elif aim.y - aim.ty > 100 and aim.x - aim.tx < 100:
        aim.plan_angle += (aim.left_angle + aim.gust - aim.angle) / 2
    else:
        aim.plan_angle += (aim.left_angle + aim.gust - aim.angle) / 2 - (aim.tx - aim.x) / 100


def left_retry(aim: Aim) -> None:
    if aim.tx >= aim.lx:
        if aim.x_miss > 20:
            aim.plan_power -= aim.reach(2.5, 45) - aim.windage() - js_div(aim.ly - aim.ty, aim.height)
        else:
            aim.plan_power -= aim.reach(-1, 45) - aim.windage()
    elif aim.ly < aim.ty:
        if aim.ty < aim.y:
            left_short_below(aim)
        else:
            left_short_above(aim)
    elif (aim.last_dist < 150 and aim.x - aim.tx < 170) or aim.last_dist >= 100 or aim.power < 30:
        if aim.ty < aim.y or not aim.ty - aim.y > 100:
            aim.plan_power += aim.reach(0, 45) + aim.windage() + js_div(aim.ly - aim.ty, aim.height)
        else:
            aim.plan_power += aim.reach(0, 45) + aim.windage()
    elif (aim.angle < aim.left_angle + 5) if aim.level.slip else (aim.angle > aim.left_angle + 5):
        aim.plan_angle -= (aim.angle - 45) / 10 + aim.x - aim.tx / 100
    else:
        aim.plan_angle += (aim.left_angle + aim.gust - aim.angle) / 3
        aim.plan_power += aim.reach(0, 45) / 1.5 + (aim.left_angle + aim.gust - aim.angle) / 5


def left_short_below(aim: Aim) -> None:
    tilt = aim.left_angle + aim.gust
    if (
        aim.y - aim.ty > 80
        and 20 < aim.y_miss < 80
        and aim.last_dist < 100
        and aim.target_dist > 220
        and aim.power > 30
        and aim.angle > tilt
    ):
        aim.plan_angle += (tilt - aim.angle) / 4 - aim.wind / 20 - aim.target_dist / 100
    elif aim.angle > tilt or (aim.y_miss < 30 and aim.x_miss < 200):
        aim.plan_power += aim.reach(0, 45) + aim.windage() + js_div(aim.ly - aim.ty, aim.height)
    elif aim.y_miss >= 30:
        if aim.x - aim.tx > 300 and aim.power < 50 and aim.angle > 70:
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / 3) + aim.windage()
        elif aim.angle < tilt:
            left_steepen(aim, tilt)


def left_short_above(aim: Aim) -> None:
    tilt = aim.left_angle + aim.gust
    if (
        aim.ty - aim.y < 70
        and 20 < aim.y_miss < 100
        and aim.last_dist < 100
        and aim.target_dist > 250
        and aim.power > 30
        and aim.angle < aim.left_angle - aim.gust
    ):
        aim.plan_angle += (tilt - aim.angle) / 4.5 - aim.wind / 20 - aim.target_dist / 100
    elif aim.angle > tilt or (aim.y_miss < 30 and aim.x_miss < 200):
        aim.plan_power += aim.reach(0, 45) + aim.windage() + js_div(aim.ly - aim.ty, aim.height)
    elif aim.y_miss >= 30:
        if aim.ty - aim.y > 200 and aim.y < aim.ly:
            share = 1.5 if aim.plan_angle < 60 else 2
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / share) + aim.windage()
        elif aim.x - aim.tx > 300 and aim.power < 50 and aim.angle > 70:
            aim.plan_power += js_div(aim.x_miss, aim.level.reach / 3) + aim.windage()
        elif aim.angle < tilt:
            left_steepen(aim, tilt)


def left_steepen(aim: Aim, tilt: float) -> None:
    climb = js_div(aim.y_miss, aim.level.height_reach)
    base = js_div(aim.x_miss, aim.level.reach * 2) + aim.windage() + climb + aim.wind / 15
    if aim.plan_angle >= 45:
        aim.plan_power += base + (aim.angle - 45) / 8 + (tilt - aim.angle) / 8
    else:
        aim.plan_power += base
    aim.plan_angle += (tilt - aim.angle) / 4.5 + climb


# ---------- One computer tank ----------


class Brain:
    """One computer tank's memory through a round: its target, its plan, and the wind when it last fired"""

    def __init__(self, level: str):
        self.level = level
        self.turns = 0
        self.target: Tank | None = None
        self.plan_angle = 90.0
        self.plan_power = 50.0
        self.last_wind = 0.0

    def new_round(self, me: Tank, tanks: list[Tank]) -> None:
        self.turns = 0
        self.target = nearest(me, tanks)

    def plan(self, me: Tank, tanks: list[Tank], wind: float) -> tuple[int, float]:
        """This turn's barrel angle and power, as whole numbers the way the original's barrel steps to them"""
        self.turns += 1
        if self.target is None or not self.target.alive:
            self.turns = 1
            self.target = nearest(me, tanks)
        if self.target is None:
            return me.angle, me.power
        level = TABLE[self.level]
        if self.turns == 1 or me.last_shot is None:
            self.plan_angle, self.plan_power = plan_first(level, me, self.target, wind)
        else:
            aim = Aim(
                level,
                me.x,
                me.y,
                self.target.x,
                self.target.y,
                *me.last_shot,
                me.angle,
                me.power,
                wind,
                self.last_wind,
                self.plan_angle,
                self.plan_power,
            )
            self.plan_angle, self.plan_power = plan_next(aim, me.energy)
        if not (math.isfinite(self.plan_angle) and math.isfinite(self.plan_power)):
            # The original divides by zero now and then, and its tank then never fires. Start over instead
            self.plan_angle, self.plan_power = plan_first(level, me, self.target, wind)
        angle = min(max(math.ceil(self.plan_angle), 0), 180)
        power = min(max(math.ceil(self.plan_power), 0), 100, me.energy)
        return angle, power

    def fired(self, wind: float) -> None:
        self.last_wind = wind


def nearest(me: Tank, tanks: list[Tank]) -> Tank | None:
    """select_target(): the closest living tank, sideways"""
    others = [tank for tank in tanks if tank is not me and tank.alive]
    if not others:
        return None
    return min(others, key=lambda tank: abs(me.x - tank.x))
