"""One battle, step by step, the way the original's battle frame runs it (frame_5/DoAction.as) at 33 steps a second.
Positions are stage pixels and angles Flash degrees (0 points up, 90 right). The original's number quirks are kept on
purpose: random(n) floors, rotations wrap to -180..180, and NaN from acos makes a robot drive straight on"""

import math
import random
import typing as t
from dataclasses import dataclass

from . import shapes
from .parts import CHASSIS, PLATINGS, WEAPONS, Chassis, Plating, Weapon

FPS = 33
# The countdown says go on its frame 140
MOVE_AT = 140
SCAN_EVERY = 9
FULL = 1000
SHOT_STEP = 4
SPEED = 2
FUSSY_TURN = 45
STUCK_STEPS = 10
# A go-there order stays inside this box, and ends this close to its spot
LEFT, RIGHT, TOP, BOTTOM = 40, 500, 40, 440
ARRIVED = 35
# A robot without a weapon follows at these ranges
UNARMED_MIN, UNARMED_MAX = 50, 100
DRAW_STEPS = 1980
# The win or lose banner runs this long, then the screen fades for FADE_STEPS
BANNER_STEPS = 69
FADE_STEPS = 16
MAX_FLAMES = 90
# Each side's start: x and facing
STARTS = {1: (60, 90), 2: (480, -90)}
DEG = 0.017453292519943295
MISSED, HIT_ROBOT, HIT_WALL = 0, 1, 2


def flash_random(rng: random.Random, n: int) -> int:
    """Flash's random(n): a whole number from 0 to n - 1, and 0 when n is below 1"""
    return rng.randrange(n) if n >= 1 else 0


def wrap(degrees: float) -> float:
    """A rotation as Flash keeps it, between -180 and 180"""
    degrees = math.fmod(degrees, 360.0)
    if degrees > 180:
        return degrees - 360
    if degrees < -180:
        return degrees + 360
    return degrees


def settle(old: float, new: float) -> float:
    """Flash ignores a NaN or infinite rotation and keeps the old one"""
    return wrap(new) if math.isfinite(new) else old


def angle(dx: float, dy: float, dist: float) -> float:
    """The original's angle of (dx, dy) from acos(dx / dist), 0 to 2 pi, NaN where Flash gives NaN"""
    if dist:
        ratio = dx / dist
    else:
        ratio = math.copysign(math.inf, dx) if dx else math.nan
    turn = math.acos(ratio) if -1 <= ratio <= 1 else math.nan
    return 2 * math.pi - turn if dy < 0 else turn


def distance(a: "Robot", b: "Robot") -> float:
    dx, dy = a.x - b.x, a.y - b.y
    return math.sqrt(dx * dx + dy * dy)


def r2(value: float) -> float:
    return round(value, 2)


@dataclass(eq=False)
class Robot:
    id: int
    team: int
    name: str
    chassis: Chassis
    plating: Plating
    weapon: Weapon | None
    frame: int
    x: float
    y: float
    rot: float
    health: int
    max_health: int
    min_range: int
    max_range: int
    var_x: int
    var_y: int
    # Steps to the next scan. None for a robot without a weapon until its first order: the original never sets it
    # for them, so it counts down from NaN and never scans
    lock: int | None
    gun_rot: float = 0.0
    cooldown: int = 0
    target: "Robot | None" = None
    follow: "Robot | None" = None
    closer: bool = False
    order: tuple = ("standard",)
    sway: float = 0.0
    stuck: int = 0
    turn: int = 0

    @property
    def alive(self) -> bool:
        return self.health > 0


class Battle:
    def __init__(
        self,
        teams: t.Sequence[t.Sequence[dict]],
        colors: t.Sequence[int],
        *,
        owned: t.Sequence[bool],
        draws: bool = False,
        rng: random.Random | None = None,
    ):
        """
        `teams` are the left and right side's robots as {"name", "chassis", "plating", "weapon"} part names, `colors`
        each side's team color. `owned` says whether a player commands each side: a player's robots take their hit
        outline from their weapon's art, the computer's always the first. With `draws`, DRAW_STEPS without damage end
        the battle in a draw (PvP)
        """
        self.rng = rng or random.Random()
        self.colors = list(colors)
        self.draws = draws
        self.step = 0
        self.moving = False
        self.ended: int | None = None
        self.winner: int | None = None
        self.last_damage = 0
        self.flames = 0
        self.fires: dict[int, list] = {}
        self.events: list[list] = []
        self.robots: list[Robot] = []
        for team in (1, 2):
            specs = teams[team - 1]
            x, rot = STARTS[team]
            for number, spec in enumerate(specs, start=1):
                y = 400 / (len(specs) + 1) * number + 40
                self.robots.append(self.make(team, spec, owned[team - 1], x, y, rot))

    def make(self, team: int, spec: dict, owned: bool, x: float, y: float, rot: float) -> Robot:
        chassis, plating = CHASSIS[spec["chassis"]], PLATINGS[spec["plating"]]
        weapon = WEAPONS[spec["weapon"]] if spec["weapon"] else None
        var_x = flash_random(self.rng, 150) - 75
        var_y = flash_random(self.rng, 150) - 75
        if weapon is None:
            low, high, lock = UNARMED_MIN, UNARMED_MAX, None
        else:
            low, high, lock = weapon.min_range, weapon.max_range, flash_random(self.rng, SCAN_EVERY)
        health = plating.shielding + chassis.shielding * 3
        frame = shapes.bot_frame(weapon.gun if weapon else None, owned)
        return Robot(
            len(self.robots) + 1,
            team,
            spec["name"],
            chassis,
            plating,
            weapon,
            frame,
            x,
            y,
            rot,
            health,
            health,
            low,
            high,
            var_x,
            var_y,
            lock,
        )

    # ---------- One step ----------

    def tick(self) -> None:
        self.step += 1
        if self.step == MOVE_AT:
            self.moving = True
        # Flash runs attached clips newest first, so the last robot acts first
        for robot in reversed(self.robots):
            if robot.alive:
                self.think(robot)
        if self.draws and self.ended is None and self.step - self.last_damage >= DRAW_STEPS:
            self.finish(0)

    def think(self, robot: Robot) -> None:
        """The original's botframe"""
        if robot.weapon is not None:
            self.arm(robot)
        elif robot.lock is not None:
            robot.lock -= 1
            if robot.lock <= 0:
                self.obey(robot)
                robot.lock = SCAN_EVERY
        if self.moving:
            self.move(robot)

    def move(self, robot: Robot) -> None:
        """Three feelers in front: one touching a robot (wrecks and itself included) or a wall stops it for 10 steps"""
        for local_x, local_y in shapes.FEELERS[robot.frame]:
            x, y = shapes.to_stage(robot.x, robot.y, robot.rot, local_x, local_y)
            if self.robot_at(x, y) is not None or shapes.wall_hit(x, y):
                robot.stuck = STUCK_STEPS
        if robot.stuck <= 0:
            self.drive(robot)
        else:
            self.fuss(robot)

    def drive(self, robot: Robot) -> None:
        """Turn by a tenth of the sway and drive 2 pixels. Without a go-there order the sway settles toward 0, then
        picks a new wobble"""
        robot.rot = settle(robot.rot, robot.rot + robot.sway / 10)
        robot.x += math.sin(DEG * robot.rot) * SPEED
        robot.y -= math.cos(DEG * robot.rot) * SPEED
        if robot.order[0] == "goto":
            return
        if robot.sway != 0:
            robot.sway /= 1.04
            if -1 < robot.sway < 1:
                robot.sway = 0
        else:
            robot.sway += flash_random(self.rng, 21) - 10

    def fuss(self, robot: Robot) -> None:
        """Stopped: pick a random turn, then turn on the spot 5 degrees a step"""
        robot.stuck -= 1
        robot.sway = 0
        if robot.turn == 0:
            robot.turn = flash_random(self.rng, FUSSY_TURN * 2) - FUSSY_TURN
        elif robot.turn > 0:
            robot.rot = settle(robot.rot, robot.rot + 5)
            robot.turn -= 1
        else:
            robot.rot = settle(robot.rot, robot.rot - 5)
            robot.turn += 1

    def order(self, team: int, robot_id: int, x: float, y: float) -> bool:
        """A drag from one of this side's living robots, released at (x, y). Released on itself: back to normal. On
        empty ground: go there. On a living robot of either side: follow it. On a wreck: nothing"""
        robot = self.by_id(robot_id)
        if robot is None or robot.team != team or not robot.alive or not (math.isfinite(x) and math.isfinite(y)):
            return False
        if shapes.robot_hit(robot.frame, robot.x, robot.y, robot.rot, x, y):
            robot.order = ("standard",)
            return True
        other = self.robot_at(x, y)
        if other is None:
            robot.order = ("goto", min(max(x, LEFT), RIGHT), min(max(y, TOP), BOTTOM))
        elif other.alive:
            robot.order = ("follow", other)
        else:
            return False
        robot.lock = 0
        return True

    def arm(self, robot: Robot) -> None:
        if robot.cooldown < FULL:
            robot.cooldown += robot.weapon.refire
        elif robot.cooldown > FULL:
            robot.cooldown = FULL
        target = robot.target
        if target is not None:
            dx, dy = robot.x - target.x, robot.y - target.y
            dist = math.sqrt(dx * dx + dy * dy)
            robot.gun_rot = settle(robot.gun_rot, angle(dx, dy, dist) * 180 / math.pi - robot.rot - 90)
            if robot.min_range < dist < robot.max_range and robot.cooldown == FULL:
                robot.cooldown = flash_random(self.rng, 5)
                self.fire(robot)
        else:
            robot.gun_rot = settle(robot.gun_rot, robot.gun_rot / 1.1)
        robot.lock -= 1
        if robot.lock <= 0:
            self.scan(robot)
            robot.lock = SCAN_EVERY

    # ---------- Scans and steering ----------

    def scan(self, robot: Robot) -> None:
        """The original's getclosesttarget_gun"""
        robot.follow = robot.target = None
        follow = self.find_enemy(robot) if robot.weapon.hostile else self.find_patient(robot)
        robot.closer = False
        if robot.order[0] == "standard":
            if follow is not None:
                self.close_in(robot, follow)
        else:
            self.obey(robot)

    def find_enemy(self, robot: Robot) -> Robot | None:
        """The closest living enemy past the shortest range, locked on when it is within the longest"""
        best, found = math.inf, None
        for other in self.robots:
            if other is robot or other.team == robot.team or not other.alive:
                continue
            dist = distance(robot, other)
            if dist <= best and dist > robot.min_range:
                best, found = dist, other
        robot.follow = found
        if best <= robot.max_range:
            robot.target = found
        return found

    def find_patient(self, robot: Robot) -> Robot | None:
        """A repair tool locks on to the most hurt teammate in range, and follows the weakest teammate anywhere"""
        best = anywhere = math.inf
        follow = None
        for other in self.robots:
            if other is robot or other.team != robot.team:
                continue
            dist = distance(robot, other)
            share = other.health / other.max_health
            if robot.min_range < dist < robot.max_range and share <= best and share < 1 and other.alive:
                best, follow, robot.target = share, other, other
            if share <= anywhere and other.alive:
                anywhere, follow = share, other
        robot.follow = follow
        return follow

    def close_in(self, robot: Robot, follow: Robot) -> None:
        """Steer toward a point jittered around the robot followed, once it is too far. The original keeps the old
        distance after jittering, which can make the angle NaN"""
        dx, dy = robot.x - follow.x, robot.y - follow.y
        dist = math.sqrt(dx * dx + dy * dy)
        reach = robot.max_range * (1.2 if robot.weapon.hostile else 0.5)
        if dist > reach:
            dx += (flash_random(self.rng, 300) - 150 - robot.var_x) / 5
            dy += (flash_random(self.rng, 300) - 150 - robot.var_y) / 5
            robot.closer = True
            self.steer(robot, dx, dy, dist)

    def obey(self, robot: Robot) -> None:
        """A go-there or follow order, for robots with or without a weapon"""
        kind = robot.order[0]
        if kind == "goto":
            dx, dy = robot.x - robot.order[1], robot.y - robot.order[2]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < ARRIVED:
                robot.order = ("standard",)
            self.steer(robot, dx, dy, dist)
        elif kind == "follow":
            leader = robot.order[1]
            if not leader.alive:
                # The original drops the order, then measures to the robot it no longer has, gets NaN, and doesn't steer
                robot.order = ("standard",)
                return
            dx, dy = robot.x - leader.x, robot.y - leader.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > robot.min_range * 1.2:
                self.steer(robot, dx, dy, dist)

    def steer(self, robot: Robot, dx: float, dy: float, dist: float) -> None:
        """The original's adjustmove: aim the sway at (dx, dy), at most 90 degrees either way"""
        sway = angle(dx, dy, dist) * 180 / math.pi - 90 - robot.rot
        if sway > 180:
            sway -= 360
        if sway > 90:
            sway = 90
        elif sway < -90:
            sway = -90
        robot.sway = sway

    # ---------- Shots ----------

    def fire(self, robot: Robot) -> None:
        weapon = robot.weapon
        tip_x, tip_y = shapes.gun_tip(robot.plating.graphic, weapon.gun, robot.x, robot.y, robot.rot, robot.gun_rot)
        spread = flash_random(self.rng, weapon.spread * 2) - weapon.spread
        direction = robot.gun_rot + robot.rot + spread
        x, y, length, victim, hit = self.trace(robot, direction, tip_x, tip_y)
        rico = flash_random(self.rng, weapon.rico_max) + weapon.rico_min
        self.events.append(
            [
                self.step,
                "shot",
                robot.id,
                r2(tip_x),
                r2(tip_y),
                r2(robot.gun_rot + robot.rot),
                r2(direction),
                length,
                r2(x),
                r2(y),
                hit,
                rico,
            ]
        )
        if victim is not None:
            self.hurt(victim, weapon.damage, robot.team)

    def trace(self, robot: Robot, direction: float, x: float, y: float) -> tuple:
        """The original's drawpath: 4 pixel jumps until a robot or a wall, up to the longest range"""
        step_x = math.sin(DEG * direction) * SHOT_STEP
        step_y = math.cos(DEG * direction) * SHOT_STEP
        travelled = 0
        while travelled < robot.max_range:
            x += step_x
            y -= step_y
            victim = self.robot_at(x, y, skip=robot)
            if victim is not None:
                return x, y, travelled, victim, HIT_ROBOT
            if shapes.wall_hit(x, y):
                return x, y, travelled, None, HIT_WALL
            travelled += SHOT_STEP
        return x, y, travelled, None, MISSED

    def robot_at(self, x: float, y: float, skip: Robot | None = None) -> Robot | None:
        """The first robot by id whose outline covers the point, wrecks included"""
        for robot in self.robots:
            if robot is not skip and shapes.robot_hit(robot.frame, robot.x, robot.y, robot.rot, x, y):
                return robot
        return None

    def hurt(self, victim: Robot, amount: int, team: int) -> None:
        """The original's lifeadjust: damage lands only on the other side, repairs only on your own, up to full"""
        if not victim.alive:
            return
        if amount > 0:
            if team == victim.team:
                return
            victim.health -= amount
            self.last_damage = self.step
            if victim.health <= 0:
                victim.health = 0
                if self.ended is None and self.team_health(victim.team) <= 0:
                    self.finish(3 - victim.team)
                self.kill(victim)
        elif team == victim.team:
            victim.health = min(victim.health - amount, victim.max_health)

    def team_health(self, team: int) -> int:
        return sum(robot.health for robot in self.robots if robot.team == team)

    def kill(self, robot: Robot) -> None:
        """A wreck: it stops, explodes and burns with up to 4 flames, until the battle has 90"""
        flames = []
        if self.flames < MAX_FLAMES:
            for _ in range(flash_random(self.rng, 7) - 2):
                dx = flash_random(self.rng, 25) - 12
                dy = flash_random(self.rng, 25) - 12
                flames.append([dx, dy, flash_random(self.rng, 40) + 20])
            self.flames += len(flames)
        self.fires[robot.id] = flames
        self.events.append([self.step, "die", robot.id, r2(robot.x), r2(robot.y), flames])

    def finish(self, winner: int) -> None:
        self.ended, self.winner = self.step, winner
        self.events.append([self.step, "end", winner])

    def done(self) -> bool:
        """The banner and the fade after the result have played"""
        return self.ended is not None and self.step >= self.ended + BANNER_STEPS + FADE_STEPS

    # ---------- What the pages see ----------

    def by_id(self, robot_id: int) -> Robot | None:
        return next((robot for robot in self.robots if robot.id == robot_id), None)

    def take_events(self) -> list:
        events, self.events = self.events, []
        return events

    def view(self) -> list:
        return [
            [r2(r.x), r2(r.y), r2(r.rot), r2(r.gun_rot), r.health, r.cooldown, self.order_view(r)] for r in self.robots
        ]

    def order_view(self, robot: Robot) -> t.Any:
        kind = robot.order[0]
        if kind == "goto":
            return [1, r2(robot.order[1]), r2(robot.order[2])]
        if kind == "follow":
            return [2, robot.order[1].id]
        if robot.weapon is not None and robot.closer and robot.follow is not None:
            return [3, robot.follow.id]
        return 0

    def setup(self) -> list[dict]:
        return [
            {
                "id": r.id,
                "team": r.team,
                "name": r.name,
                "chassis": r.chassis.name,
                "plating": r.plating.name,
                "weapon": r.weapon.name if r.weapon else None,
                "max": r.max_health,
                "frame": r.frame,
            }
            for r in self.robots
        ]

    def wrecks(self) -> list:
        return [[robot_id, flames] for robot_id, flames in self.fires.items()]
