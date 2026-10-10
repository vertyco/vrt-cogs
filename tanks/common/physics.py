"""A whole shot, worked out at once at the original's 25 steps a second: flight, splits, rolling balls, the air strike,
blasts, craters, damage, wrecks blowing up, and every tank settling afterwards. The result is a script that every page
plays back the same way"""

import math
import random
from dataclasses import dataclass, field

from .items import AIR_STRIKE
from .tank import Tank, box, check_death, hurt, overlaps, settle_frame, start_settling
from .terrain import HEIGHT, WIDTH, Field, flash_random, js_round

STEP_RATE = 25
GRAVITY = 9.81
# Flash's sine of the launch angle uses this rough degrees-to-radians factor, and its cosine the exact one
ROUGH_RADIANS = 0.017
# The shell drawing's box, before the weapon scales and turns it
SHELL_RECT = (-1.15, -1.10, 1.15, 1.15)
# The fireball drawing's box at scale 1, and how far it sits above the shell's middle
FIREBALL_RECT = (-25.2, -12.0, 24.8, 12.0)
FIREBALL_LIFT = 0.05
# A blast goes off five steps after the hit (the explosion's sixth frame); a volcano bomb splits at the fourth
BLAST_FRAME = 6
SPLIT_FRAME = 4
END_FRAME = 12
# A dying tank blows up five steps after it dies, with a 70 x 40 fireball
WRECK_DELAY = 5
WRECK_RECT = (-35.0, -20.0, 35.0, 20.0)
WRECK_WIDTH = 70
WRECK_CUT = 30
WRECK_HARM = 14
WRECK_SHIELD_HARM = 18
# The Shower splits three seconds into its flight
SPLIT_TIME = 3
TELEPORT_MOVE = 40
TELEPORT_STEPS = 47
# Nothing in the original runs this long; a safety net against a shell that never lands
MAX_STEPS = STEP_RATE * 120


@dataclass(frozen=True)
class Blast:
    """One explosion's numbers, from its sprite's bum(): `cut`/`sink` move a column under the fireball (par1/par2),
    `scrape` takes off columns only its box reaches (par3), `harm`/`shield_harm` set the damage (par4/par5)"""

    key: str
    scale: float
    sx: float
    sy: float
    cut: float
    sink: float
    scrape: float
    harm: float
    shield_harm: float

    @property
    def width(self) -> float:
        return (FIREBALL_RECT[2] - FIREBALL_RECT[0]) * self.scale * self.sx


SMALL = Blast("small", 0.3958, 0.8726, 0.9011, 15, 7.5, 15, 5, 13)
MISSILE = Blast("missile", 0.7, 1.0, 1.0, 15, 7.5, 15, 13, 18)
BNUKE = Blast("bnuke", 1.8348, 1.0, 1.0222, 30, 15, 15, 17, 24)
NUKE = Blast("nuke", 3.8341, 1.0, 1.0222, 35, 30, 30, 22, 40)
FUNKY = Blast("funky", 0.7, 1.0, 1.0222, 15, 7.5, 15, 13, 18)
MIRV = Blast("mirv", 0.7, 1.0, 1.0222, 15, 7.5, 15, 13, 18)
DEATH = Blast("death", 1.8348, 1.0, 1.0222, 15, 7.5, 15, 13, 20)
BROLLER = Blast("broller", 0.7, 1.0, 1.0222, 15, 7.5, 15, 13, 20)
ROLLER = Blast("roller", 1.8348, 1.0, 1.0222, 30, 15, 15, 13, 18)
HROLLER = Blast("hroller", 3.8341, 1.0, 1.0222, 35, 30, 30, 19, 36)
STRIKE = Blast("strike", 0.7, 1.0, 1.0222, 15, 7.5, 15, 13, 18)

# Each weapon by its shop number: how its shell behaves, and its blast
WEAPON_SHELLS = (
    ("plain", SMALL),
    ("plain", MISSILE),
    ("plain", BNUKE),
    ("plain", NUKE),
    ("volcano", FUNKY),
    ("shower", MIRV),
    ("shower", DEATH),
    ("ball", BROLLER),
    ("ball", ROLLER),
    ("ball", HROLLER),
    ("ball2", BROLLER),
    ("ball2", ROLLER),
    ("ball2", HROLLER),
    ("strike", STRIKE),
)


def js_div(a: float, b: float) -> float:
    """Division as Flash does it: dividing by zero gives infinity (or NaN for 0 / 0) instead of an error"""
    if b == 0:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1, b)
    return a / b


def turned_box(rect: tuple, sx: float, sy: float, degrees: float, lift: float = 0.0) -> tuple:
    """The box around a drawing scaled by (sx, sy) and turned, as Flash measures a turned clip: around its corners"""
    turn = math.radians(degrees)
    cos_t, sin_t = math.cos(turn), math.sin(turn)
    xs, ys = [], []
    for x, y in ((rect[0], rect[1]), (rect[2], rect[1]), (rect[0], rect[3]), (rect[2], rect[3])):
        x, y = x * sx, (y + lift) * sy
        xs.append(cos_t * x - sin_t * y)
        ys.append(sin_t * x + cos_t * y)
    return (min(xs), min(ys), max(xs), max(ys))


def in_fireball(u: float, v: float) -> bool:
    """The fireball drawing's filled parts: a bright ball in the middle and a ring of flame either side"""
    if (u - 0.1) ** 2 + v**2 <= 144:
        return True
    outer = ((u + 0.2) / 25) ** 2 + (v / 12) ** 2 <= 1
    inner = (u / 17.15) ** 2 + (v / 12) ** 2 <= 1
    return outer and not inner


@dataclass
class Shell:
    behavior: str
    blast: Blast
    owner: Tank
    x0: float
    y0: float
    vox: float
    voy: float
    rotation: float
    speed: float = 0.0
    t: float = 0.0
    time_step: float = 0.1
    windy: bool = True
    # Sideways speed added every step: the Shower's pieces fan out by it
    spread: float = 0.0
    # Main shells tell the owner where they ended when they leave the field, for computer tanks to aim from
    reports: bool = False
    x: float = 0.0
    y: float = 0.0
    immune: bool = True
    frame: int = 1
    playing: bool = False
    done: bool = False
    waiting: bool = False
    end: bool = False
    children: list = field(default_factory=list)
    rolling: bool = False
    flying: bool = True
    heading: str | None = None
    starting: bool = True
    points: list = field(default_factory=list)
    start_step: int = 0

    def __post_init__(self):
        self.x, self.y = self.x0, self.y0
        self.box = turned_box(SHELL_RECT, self.blast.sx, self.blast.sy, self.rotation)

    def area(self) -> tuple:
        return box(self.x, self.y, self.box)


def launch(blast: Blast, behavior: str, owner: Tank, x: float, y: float, degrees: float, speed: float) -> Shell:
    """A shell leaving at `degrees` (0 points left, 90 up, 180 right) with `speed`, as the original's load code
    sets it up from the clip's rotation"""
    heading = 180 - degrees
    vox = math.cos(math.radians(heading)) * speed
    voy = math.sin(ROUGH_RADIANS * heading) * speed
    return Shell(behavior, blast, owner, x, y, vox, voy, rotation=degrees - 90, speed=speed)


class Shot:
    """Works out one shot, step by step, and records the script the pages play"""

    def __init__(self, field_: Field, tanks: list[Tank], shooter: Tank, rng: random.Random):
        self.field = field_
        self.tanks = tanks
        self.shooter = shooter
        self.rng = rng
        self.step = 0
        self.shells: list[Shell] = []
        self.wrecks: list[tuple[int, Tank]] = []
        self.settle_phase = False
        self.weapon: int | None = None
        self.events: list[list] = []
        self.changed_columns: set[int] = set()
        self.seen = {tank.seat: tank.view() for tank in tanks}

    # ---------- Starting ----------

    def fire(self, weapon: int, strike: tuple[float, int] = (0.0, 1)) -> None:
        """Fire the weapon from the shooter's barrel. The air strike instead drops in at `strike`: (x, direction)"""
        self.weapon = weapon
        tank = self.shooter
        behavior, blast = WEAPON_SHELLS[weapon]
        if weapon == AIR_STRIKE:
            self.start_strike(*strike)
            return
        shell = launch(blast, behavior, tank, tank.x, tank.y - 1, tank.angle, tank.power)
        shell.reports = behavior == "plain" or behavior == "volcano"
        self.add(shell)

    def start_strike(self, x: float, direction: int) -> None:
        """Five shells drop in from above the field, 20 pixels apart, flying the way the player picked"""
        degrees = 0 if direction > 0 else 180
        for number in range(5):
            start = x - 120 + number * 20 if direction > 0 else x + 120 - number * 20
            vox = math.cos(math.radians(degrees)) * 10
            voy = math.sin(ROUGH_RADIANS * degrees) * 10
            shell = Shell("strike", STRIKE, self.shooter, start, -50, vox, voy, rotation=0, time_step=0.12, windy=False)
            shell.immune = False
            self.add(shell)

    def teleport(self, x: float, y: float) -> None:
        """The original's teleport: a 48 frame beam, with the tank moving across at frame 41"""
        tank = self.shooter
        self.events.append([0, "beam", tank.seat, round(tank.x, 1), round(tank.y, 1), round(x, 1), round(y, 1)])
        self.step = TELEPORT_MOVE
        tank.x, tank.y = x, y
        self.record()
        self.step = TELEPORT_STEPS

    def add(self, shell: Shell) -> None:
        shell.start_step = self.step + 1
        self.shells.append(shell)

    # ---------- Running ----------

    def run(self) -> dict:
        while self.busy() and self.step < MAX_STEPS:
            self.step += 1
            self.advance()
        return self.script()

    def busy(self) -> bool:
        if any(not shell.done for shell in self.shells) or self.wrecks:
            return True
        if not self.settle_phase:
            return True
        return any(tank.settling and tank.alive for tank in self.tanks)

    def advance(self) -> None:
        for shell in list(self.shells):
            if not shell.done and shell.start_step <= self.step:
                self.update(shell)
        for due, tank in [wreck for wreck in self.wrecks if wreck[0] == self.step]:
            self.wrecks.remove((due, tank))
            self.wreck_blast(tank)
        if not self.settle_phase and all(shell.done for shell in self.shells):
            self.settle_phase = True
            self.retest()
        if self.settle_phase:
            for tank in self.tanks:
                if tank.alive and tank.settling:
                    settle_frame(tank, self.field)
        for tank in self.tanks:
            if check_death(tank):
                self.events.append([self.step, "die", tank.seat, round(tank.x, 1), round(tank.y, 1)])
                self.wrecks.append((self.step + WRECK_DELAY, tank))
        self.record()

    def retest(self) -> None:
        """The original's test(): every tank checks its ground again and falls if it's gone"""
        for tank in self.tanks:
            if tank.alive:
                start_settling(tank)

    # ---------- Shells ----------

    def update(self, shell: Shell) -> None:
        if shell.playing:
            self.play_frame(shell)
            if shell.done:
                return
        if shell.behavior in ("plain", "volcano", "sub"):
            self.update_plain(shell)
        elif shell.behavior == "shower":
            self.update_shower(shell)
        elif shell.behavior == "strike":
            self.update_strike(shell)
        else:
            self.update_ball(shell)

    def play_frame(self, shell: Shell) -> None:
        """The explosion's timeline after a hit: the volcano bomb splits, the blast goes off, then it ends once the
        pieces it is waiting for are done"""
        if not shell.waiting:
            shell.frame += 1
        if shell.frame == SPLIT_FRAME and shell.behavior == "volcano":
            self.erupt(shell)
        elif shell.frame == BLAST_FRAME:
            self.blast(shell)
        elif shell.frame >= END_FRAME:
            shell.waiting = True
            if all(child.done for child in shell.children) or shell.end:
                shell.done = True

    def play(self, shell: Shell) -> None:
        if not shell.playing:
            shell.playing = True
            self.events.append(
                [self.step, "boom", round(shell.x, 1), round(shell.y, 1), shell.blast.key, shell.rotation]
            )

    def fly(self, shell: Shell) -> None:
        shell.x = shell.x0 + shell.vox * shell.t
        shell.y = shell.y0 - shell.voy * shell.t + GRAVITY / 2 * (shell.t * shell.t)
        if shell.windy:
            shell.vox += self.field.wind / 600
        shell.vox += shell.spread
        shell.points.append((round(shell.x, 1), round(shell.y, 1)))

    def leave(self, shell: Shell) -> None:
        """Out of the field: no blast. A main shell tells its owner where it went"""
        if shell.reports:
            shell.owner.last_shot = (shell.x, shell.y)
        shell.done = True

    def hits_ground(self, shell: Shell) -> bool:
        column = min(max(js_round(shell.x), 0), WIDTH - 1)
        return shell.area()[3] >= self.field.top(column)

    def owner_touched(self, shell: Shell, with_shield: bool = True) -> bool:
        owner = shell.owner
        if with_shield:
            return owner.touched_by(shell.area())
        return overlaps(shell.area(), owner.body_box())

    def hits_tank(self, shell: Shell, shields: bool = True) -> bool:
        area = shell.area()
        for tank in self.tanks:
            if tank is shell.owner or not tank.hittable:
                continue
            if overlaps(area, tank.hit_box() if shields else tank.body_box()):
                return True
        return False

    def update_plain(self, shell: Shell) -> None:
        if shell.x < 0 or shell.x > WIDTH:
            self.leave(shell)
            return
        if shell.frame == 1:
            self.fly(shell)
        touching_owner = self.owner_touched(shell)
        if self.hits_ground(shell) or self.hits_tank(shell) or (touching_owner and not shell.immune):
            self.play(shell)
        if not touching_owner:
            shell.immune = False
        shell.t += shell.time_step

    def update_shower(self, shell: Shell) -> None:
        """The Shower and Hot shower: they ignore shields in flight, and split three seconds in"""
        if shell.x < 0 or shell.x > WIDTH:
            shell.playing, shell.frame, shell.waiting = True, END_FRAME, True
        if shell.frame == 1:
            self.fly(shell)
        touching_owner = self.owner_touched(shell, with_shield=False)
        if self.hits_ground(shell) or self.hits_tank(shell, shields=False) or (touching_owner and not shell.immune):
            self.play(shell)
        if not touching_owner:
            shell.immune = False
        if js_round(shell.t * 10) / 10 == SPLIT_TIME:
            if shell.frame == 1:
                self.scatter(shell)
            else:
                shell.end = True
        shell.t += shell.time_step

    def update_strike(self, shell: Shell) -> None:
        if shell.y > HEIGHT:
            shell.done = True
            return
        if shell.frame == 1:
            self.fly(shell)
        hits_any = any(tank.hittable and overlaps(shell.area(), tank.hit_box()) for tank in self.tanks)
        if hits_any or shell.area()[3] >= self.field.top(js_round(shell.x)):
            self.play(shell)
        shell.t += shell.time_step

    def update_ball(self, shell: Shell) -> None:
        """Balls fly like shells, then roll along the ground (downhill, or for V2 the original's uphill rule) and
        blow up where they stop"""
        if shell.x < 0 or shell.x > WIDTH or shell.y > HEIGHT:
            shell.done = True
            return
        touching_owner = self.owner_touched(shell)
        if self.hits_tank(shell) or (touching_owner and not shell.immune):
            self.play(shell)
            shell.flying = shell.rolling = False
        if not touching_owner:
            shell.immune = False
        if shell.flying:
            self.fly(shell)
            if self.hits_ground(shell):
                shell.flying, shell.rolling = False, True
            shell.t += shell.time_step
        if shell.rolling:
            self.roll(shell, uphill=shell.behavior == "ball2")

    def roll(self, shell: Shell, uphill: bool) -> None:
        top = self.field.top
        if shell.starting:
            shell.starting = False
            column = js_round(shell.x)
            here, left, right = top(column), top(column - 1), top(column + 1)
            shell.y = here
            if uphill:
                shell.heading = "right" if here >= left else "left" if here >= right else None
            else:
                shell.heading = "left" if left >= here else "right" if right >= here else None
            if shell.heading is None:
                self.stop_ball(shell)
                return
        column = js_round(shell.x)
        here = top(column)
        shell.y = here
        step = -1 if shell.heading == "left" else 1
        beside = top(column + step)
        if (here >= beside) if uphill else (beside >= here):
            shell.x += step
            shell.points.append((round(shell.x, 1), round(shell.y, 1)))
        else:
            self.stop_ball(shell)

    def stop_ball(self, shell: Shell) -> None:
        shell.rolling = False
        self.play(shell)

    # ---------- Splitting ----------

    def erupt(self, shell: Shell) -> None:
        """The Volcano bomb throws five burning pieces up from where it hit, at random angles and speeds"""
        for _ in range(5):
            turn = flash_random(self.rng, 90) - 45
            speed = flash_random(self.rng, 30) + 15
            piece = launch(FUNKY, "sub", shell.owner, shell.x, shell.y - 5, turn + 90, speed)
            self.add(piece)
            shell.children.append(piece)

    def scatter(self, shell: Shell) -> None:
        """The Shower splits into five pieces (the Hot shower into seven small atom bombs) that fan out sideways.
        The pieces restart from the launch speed, shifted by a seventh of the wind to make up for it, as in the
        original"""
        count, blast = (7, BNUKE) if shell.blast is DEATH else (5, FUNKY)
        heading = 90 - shell.rotation
        vox = math.cos(math.radians(heading)) * shell.speed
        voy = math.sin(ROUGH_RADIANS * heading) * shell.speed
        x0 = shell.x0 + self.field.wind / 7
        for number in range(count):
            spread = (number - count // 2) / 20
            piece = Shell("sub", blast, shell.owner, x0, shell.y0, vox, voy, shell.rotation, t=shell.t, spread=spread)
            self.add(piece)
            shell.children.append(piece)

    # ---------- Blasts ----------

    def blast(self, shell: Shell) -> None:
        """bum(): carve the crater column by column, then damage every tank the fireball's box reaches"""
        blast = shell.blast
        width = blast.width
        px, py = shell.x, shell.y
        turn = math.radians(shell.rotation)
        cos_t, sin_t = math.cos(turn), math.sin(turn)
        area = box(
            px,
            py,
            turned_box(
                FIREBALL_RECT,
                blast.sx * blast.scale,
                blast.sy * blast.scale,
                shell.rotation,
                lift=-FIREBALL_LIFT / blast.scale,
            ),
        )
        tops = self.field.tops
        for i in range(math.ceil(width)):
            column = js_round(px - width / 2 + i)
            if not 0 <= column < WIDTH:
                continue
            top = tops[column]
            dx, dy = column - px, top - py
            u = (cos_t * dx + sin_t * dy) / blast.sx / blast.scale
            v = ((-sin_t * dx + cos_t * dy) / blast.sy + FIREBALL_LIFT) / blast.scale
            if in_fireball(u, v):
                strength = math.cos(ROUGH_RADIANS * (math.hypot(dx, dy) * (180 / width)))
                tops[column] = top + blast.sink * strength + blast.cut * strength / 2
                self.changed_columns.add(column)
            elif area[3] >= top and area[0] <= column + 0.5 and column - 0.5 <= area[2]:
                tops[column] = top + blast.scrape * math.cos(ROUGH_RADIANS * (abs(dx) * (180 / width)))
                self.changed_columns.add(column)
        shell.owner.last_shot = (px, py)
        for tank in self.tanks:
            if tank.hittable and tank.touched_by(area):
                self.harm(tank, shell.owner, width, math.hypot(px - tank.x, py - tank.y), blast.harm, blast.shield_harm)

    def harm(self, tank: Tank, attacker: Tank, width: float, distance: float, harm: float, shield_harm: float) -> None:
        if tank.shield is None:
            damage = min(js_round(width / ((distance + 1) / harm)), tank.energy)
        else:
            damage = js_round(width / ((distance / 2 + 1) / shield_harm))
        hurt(tank, damage, attacker)

    def wreck_blast(self, wreck: Tank) -> None:
        """A dead tank blows up: a 70 x 40 fireball that digs a crater and hurts everyone near it. The wreck's
        owner is paid for the damage, as in the original"""
        tops = self.field.tops
        for i in range(WRECK_WIDTH):
            column = js_round(wreck.x - WRECK_WIDTH / 2 + i)
            if not 0 <= column < WIDTH:
                continue
            dx, dy = column - wreck.x, tops[column] - wreck.y
            if (dx / 35) ** 2 + (dy / 20) ** 2 <= 1:
                strength = math.cos(ROUGH_RADIANS * (math.hypot(dx, dy) * (180 / WRECK_WIDTH)))
                tops[column] += WRECK_CUT * strength
                self.changed_columns.add(column)
        area = box(wreck.x, wreck.y, WRECK_RECT)
        for tank in self.tanks:
            if tank is not wreck and tank.hittable and tank.touched_by(area):
                distance = math.hypot(wreck.x - tank.x, wreck.y - tank.y)
                self.harm(tank, wreck, WRECK_WIDTH, distance, WRECK_HARM, WRECK_SHIELD_HARM)
        if self.settle_phase:
            self.retest()

    # ---------- The script ----------

    def record(self) -> None:
        """What changed this step: ground columns, and any tank that moved or whose numbers changed"""
        if self.changed_columns:
            ground = []
            for column in sorted(self.changed_columns):
                ground += [column, js_round(self.field.tops[column])]
            self.events.append([self.step, "ground", ground])
            self.changed_columns.clear()
        for tank in self.tanks:
            view = tank.view()
            if view != self.seen[tank.seat]:
                self.seen[tank.seat] = view
                self.events.append([self.step, "tank", tank.seat, view])

    def script(self) -> dict:
        shells = []
        for shell in self.shells:
            flat = [value for point in shell.points for value in point]
            if flat:
                shells.append([shell.start_step, flat])
        return {
            "seat": self.shooter.seat,
            "weapon": self.weapon,
            "steps": self.step,
            "shells": shells,
            "events": self.events,
        }
