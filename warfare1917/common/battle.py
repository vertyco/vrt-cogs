"""One battle on the Red bot: the field, both sides, the battle clock and the order things happen in each step.

The original runs at 35 frames a second; one call to `Battle.tick()` is one of those frames, called a step. Every
rule that decides an outcome runs here, in the original's order, drawing from the battle's own seeded generator, so
the same seed plays the same battle.

Order inside one step (web/flash.js steps clips the same way, so the page and the bot agree):
1. Paused: nothing at all happens, not even timers (the original let timers run through a pause).
2. The clips' own frames: every live member's timelines advance one frame, squads oldest first, members in spawn
   order; then the strike and mine clips count down, start and burst (common/blasts.py); then the gas clouds fade
   and clear (common/gas.py); then the HUD's deploy and fire support dials fill (F5:3964-4008, 4116-4143).
3. Millisecond timers that are due, in the order they were set.
4. The root's onEnterFrame (F5:7995-8011) while the battle is on: the slow tick, the medium tick, gas damage to the
   Germans then the British.
5. Every squad's turn: the German squads, then the British, each side newest first (F5:8002-8003).
6. The step count goes up.
Once the battle has ended, steps 2 (members and strike clips, whose blasts are then only pictures), 3 and 5 still
run, so winners cheer and losers surrender.
"""

import math
import random
import typing as t

from .blasts import Round, run_rounds
from .cpu import Cpu
from .data import FPS, MEDIUM_TICK, SIDES, SLOW_TICK, SUPPORT_KINDS, SUPPORTS, UNIT_KINDS, UNITS, UPGRADE_EFFECTS
from .gas import Cloud, gas_damage, run_clouds
from .missions import Mission
from .morale import check_surrender, conquer, ground_bar, regen, start_front, update_ground
from .squads import Squad, Soldier, Tank, Trench, act, make_squad, run_loop
from .tanks import throw_grenade
from .targeting import find_enemy, find_mines, find_officers, find_trenches, find_wire

# The dials' starting angle: a fresh battle's support dial (F5:4028), and any dial after a deploy or a strike
# (resetButtonTimers F5:4021, resetSupportButtonTimers F5:4152)
FRESH_DIAL = -180
RESET_DIAL = -179


def wrap_angle(angle: float) -> float:
    """Flash keeps `_rotation` between -180 and 180"""
    if angle > 180:
        return angle - 360
    if angle < -180:
        return angle + 360
    return angle


def dial_steps(timer: float, right: float) -> int:
    """Steps a HUD dial takes to fill (buttonTimer F5:3974-4006). The right half turns from `right` up to 0, then the
    left half turns from 0 past 180, where Flash wraps it negative and the slot is ready. Both halves move
    180 / (timer / 2) a step, so a dial takes about `timer` steps."""
    turn = 180 / (timer / 2)
    left = 0.0
    steps = 0
    while True:
        steps += 1
        if right < 0:
            right = wrap_angle(right + turn)
        if right >= 0 and left > -180:
            left = wrap_angle(left + turn)
        if left < 0 and right >= 0:
            return steps


class Timer:
    __slots__ = ("due", "fn", "cancelled")

    def __init__(self, due: int, fn: t.Callable[[], None]):
        self.due = due
        self.fn = fn
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class Side:
    def __init__(self, name: str, user: int | None, human: bool, upgrades: frozenset[int], mission: Mission):
        self.name = name
        self.index = SIDES.index(name)
        self.user = user
        self.human = human
        self.upgrades = upgrades
        # Morale starts full; the human's maximum grows with its morale upgrades (assignMorale, F5:5486-5507)
        self.morale_max: float = mission.morale[name]
        if self.has("morale_15"):
            self.morale_max *= UPGRADE_EFFECTS["morale_15"]["value"]
        if self.has("morale_20"):
            self.morale_max *= UPGRADE_EFFECTS["morale_20"]["value"]
        self.morale: float = self.morale_max
        # The ground held, in whole percents, and the front it comes from: the most forward squad leader seen, and
        # the squad that holds it (updateProgressBar, F5:3807-3869). A fresh front is the start line.
        self.front: float = start_front(mission.width, name)
        self.front_squad: Squad | None = None
        self.ground: int = ground_bar(mission.width, name, self.front)
        self.ground_marks: set[int] = set()
        # The CPU on this side panics while the other side holds half the field or more (AIpanicMode, F5:3845-3860)
        self.panic = False
        # Morale the side lost and the other side's deaths gave it, for the campaign's career counts
        self.morale_lost = 0.0
        self.morale_gained = 0.0
        self.units: list[bool] = list(mission.units[name])
        self.supports: list[bool] = list(mission.supports[name])
        # Dials, counted in steps: a slot is ready when its count reaches its length. Allowed units start ready
        # (F5:3894-3906); fire support starts empty (F5:4028).
        self.unit_timer_max = [dial_steps(self.unit_time(kind), RESET_DIAL) for kind in UNIT_KINDS]
        self.unit_timer = [length if on else 0 for length, on in zip(self.unit_timer_max, self.units, strict=True)]
        self.support_timer_max = [dial_steps(self.support_time(kind), FRESH_DIAL) for kind in SUPPORT_KINDS]
        # Where each support dial starts its turn: a fresh battle's, then any after a strike
        self.support_start = [FRESH_DIAL] * len(SUPPORT_KINDS)
        self.support_timer = [0] * len(SUPPORT_KINDS)
        self.squads: list[Squad] = []
        self.officers: list[Squad] = []
        spots, count = mission.mines[name]
        self.mines: list[float] = list(spots)
        self.mine_count: int = count
        self.kills = 0
        self.lost = 0
        # Soldiers shot dead by this side and soldiers of this side shot dead, for the campaign's career counts
        # (F5:2840-2845: the original counts bullet deaths only)
        self.soldier_kills = 0
        self.soldier_losses = 0
        self.deployed = 0
        self.deployed_kinds: dict[str, int] = {}
        self.support_used = 0
        self.trenches_held = 0
        self.cpu: Cpu | None = None
        self.gas_button = False

    def has(self, effect: str) -> bool:
        """Whether this side owns the upgrade that brings `effect` (data.UPGRADE_EFFECTS)"""
        return UPGRADE_EFFECTS[effect]["numbers"].get(self.name) in self.upgrades

    def unit_time(self, kind: str) -> float:
        """A unit's deploy timer with this side's reinforcement upgrades, in buttonTimer's order (F5:3966-3987)"""
        time = UNITS[self.name][kind]["timer"]
        if kind == "tank":
            effects = ("tank_timer",)
        else:
            effects = ("timer_10", "timer_15")
        for effect in effects:
            if self.has(effect):
                time *= UPGRADE_EFFECTS[effect]["value"]
        return time

    def support_time(self, kind: str) -> float:
        """A fire support's recharge with Resupply (buttonTimer_supportButtons, F5:4116-4122)"""
        time = SUPPORTS[self.name][kind]["timer"]
        if self.has("resupply"):
            time *= UPGRADE_EFFECTS["resupply"]["value"]
        return time

    def unit_ready(self, index: int) -> bool:
        return self.units[index] and self.unit_timer[index] >= self.unit_timer_max[index]

    def support_ready(self, index: int) -> bool:
        return self.supports[index] and self.support_timer[index] >= self.support_timer_max[index]

    def restart_units(self) -> None:
        """resetButtonTimers (F5:4009-4025): every allowed unit dial starts over, not only the one used, at the
        length the upgrades owned now give"""
        for index, on in enumerate(self.units):
            if on:
                self.unit_timer_max[index] = dial_steps(self.unit_time(UNIT_KINDS[index]), RESET_DIAL)
                self.unit_timer[index] = 0

    def restart_support(self, index: int) -> None:
        """resetSupportButtonTimers (F5:4144-4154): only the support used starts over"""
        self.support_start[index] = RESET_DIAL
        self.support_timer_max[index] = dial_steps(self.support_time(SUPPORT_KINDS[index]), RESET_DIAL)
        self.support_timer[index] = 0

    def retime(self) -> None:
        """The dials' lengths again after the upgrades changed. buttonTimer reads the upgrade flags on every frame
        (F5:3964-3987, 4116-4122), so a purchase speeds the dials at once: each keeps the same fraction filled."""
        for index, kind in enumerate(UNIT_KINDS):
            length = dial_steps(self.unit_time(kind), RESET_DIAL)
            self.unit_timer[index] = round(self.unit_timer[index] * length / self.unit_timer_max[index])
            self.unit_timer_max[index] = length
        for index, kind in enumerate(SUPPORT_KINDS):
            length = dial_steps(self.support_time(kind), self.support_start[index])
            self.support_timer[index] = round(self.support_timer[index] * length / self.support_timer_max[index])
            self.support_timer_max[index] = length

    def count_timers(self) -> None:
        """The HUD dials' onEnterFrame: each allowed slot that isn't ready fills one step"""
        for index, on in enumerate(self.units):
            if on and self.unit_timer[index] < self.unit_timer_max[index]:
                self.unit_timer[index] += 1
        for index, on in enumerate(self.supports):
            if on and self.support_timer[index] < self.support_timer_max[index]:
                self.support_timer[index] += 1

    def add_morale(self, amount: float) -> None:
        self.morale = min(self.morale + amount, self.morale_max)


class Battle:
    def __init__(
        self,
        mission: Mission,
        seed: int,
        humans: dict[str, int | None],
        upgrades: dict[str, frozenset[int]],
        first_try: bool,
        campaign: bool,
        rng: random.Random | None = None,
    ):
        """`humans` maps each side to its player's user id, or None for the CPU. `upgrades` holds each human side's
        owned upgrade numbers. `rng` continues a generator the mission was already built with (a Custom Battle draws
        its mines first); otherwise the battle seeds its own."""
        self.mission = mission
        self.seed = seed
        self.rng = rng if rng is not None else random.Random(seed)
        self.first_try = first_try
        self.campaign = campaign
        self.step = 0
        self.paused = False
        self.state = "playing"
        self.ended_at: int | None = None
        self.winner: str | None = None
        self.how: str | None = None
        self.width: float = mission.width
        # One counter for squads, soldiers and tanks, from 1: the page's trench slots use 0 for empty
        self.next_id = 0
        # Kill XP each side's player earned this battle (campaign first tries only, common/combat.py)
        self.kill_xp = {name: 0 for name in SIDES}
        # Kill XP already added to the player's save while the battle runs (main.py), so the end adds only the rest
        self.xp_paid = 0
        # Kill XP totals that reach each level still to come (campaign.level_marks), set from the save at launch;
        # `level_due` says a level was reached since the cog last looked
        self.level_marks: list[int] = []
        self.level_due = False
        self.sides: dict[str, Side] = {}
        for name in SIDES:
            user = humans.get(name)
            human = user is not None
            owned = upgrades.get(name, frozenset()) if human else frozenset()
            self.sides[name] = Side(name, user, human, owned, mission)
            if not human:
                self.sides[name].cpu = Cpu(name, mission)
        # buildMap, F5:4628-4683
        self.trenches = [Trench(index, x) for index, x in enumerate(mission.trenches)]
        self.wires: list[float] = list(mission.wires)
        self.timers: list[Timer] = []
        # Strike, mine and shell clips on the field, oldest first, and how many were ever made (specialRounds)
        self.rounds: list[Round] = []
        self.round_count = 0
        # Gas clouds on the field, oldest first (activeGas, F5:7299); their ids come from the same counter as rounds
        self.gas: list[Cloud] = []
        # Destroyed tanks, which stay on the field as burning wrecks (deadTanks, F5:3010)
        self.wrecks: list[Tank] = []
        self.events: list[list] = []
        # The slow and medium ticks' countdowns start at 0, so both run on the first step (F5:6902-6905)
        self.slow_count = 0
        # Slow ticks run so far, which the page counts to redo a ground bar's red flash on each (updateProgressBar)
        self.slow_ticks = 0
        self.medium_count = 0
        # The original's global movingSoldierRef: the last soldier a Moving squad walked (F5:1326), any side
        self.moving_ref: Soldier | None = None

    def score_level(self, side: str) -> None:
        """Kill XP was scored: note any level it reached, for the cog to add to the save"""
        while self.level_marks and self.kill_xp[side] > self.level_marks[0]:
            self.level_marks.pop(0)
            self.level_due = True

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def random(self, n: int) -> int:
        """ActionScript's random(n): a whole number 0 to n - 1, and 0 when n is 0 or less"""
        if n <= 0:
            return 0
        return self.rng.randrange(int(n))

    def spawn_x(self, side: str) -> float:
        """british.spawnPoint and german.spawnPoint, F5:4680-4681"""
        return -100 if side == "british" else self.width + 100

    def after(self, ms: float, fn: t.Callable[[], None]) -> Timer:
        """setTimeout on the battle clock: `fn` runs on the first step at least `ms` after now. Paused steps don't
        count. A timer set while the timers run waits for the next step at the soonest."""
        timer = Timer(self.step + math.ceil(round(ms * FPS / 1000, 9)), fn)
        self.timers.append(timer)
        return timer

    def event(self, code: str, *args) -> None:
        self.events.append([self.step, code, *args])

    def take_events(self) -> list[list]:
        events, self.events = self.events, []
        return events

    @staticmethod
    def newest_first(items: list) -> list:
        """ActionScript's `for (x in list)` walks an array from its newest entry to its oldest"""
        return items[::-1]

    def live_squads(self, side: str) -> list[Squad]:
        """A side's squads with a member on the field, oldest first"""
        return [squad for squad in self.sides[side].squads if squad.leader is not None]

    def deploy(self, side: str, slot: int) -> bool:
        """A human side's portrait press (buttonSetup's onPress, F5:3946-3955). False when refused"""
        owner = self.sides.get(side)
        if owner is None or not owner.human or self.state != "playing" or self.paused:
            return False
        if not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= len(UNIT_KINDS):
            return False
        if not owner.unit_ready(slot - 1):
            return False
        make_squad(self, side, UNIT_KINDS[slot - 1])
        owner.restart_units()
        self.event("deploy", owner.index, slot)
        return True

    def tick(self) -> None:
        """One step of the battle, in the order this module's docstring lists"""
        if self.paused:
            return
        self.advance_clips()
        self.run_timers()
        if self.state == "playing":
            self.root_frame()
        self.squad_walk()
        self.step += 1

    def advance_clips(self) -> None:
        squads = sorted((squad for side in self.sides.values() for squad in side.squads), key=lambda squad: squad.id)
        for squad in squads:
            for member in squad.members:
                if not member.alive:
                    continue
                if squad.kind == "tank":
                    member.gun.advance()
                    member.mg.advance()
                    continue
                for hook in member.timeline.advance():
                    self.member_hook(member, hook)
        run_rounds(self)
        run_clouds(self)
        if self.state == "playing":
            for side in self.sides.values():
                if side.human:
                    side.count_timers()

    def member_hook(self, member, hook: str) -> None:
        """A frame script hook a soldier's timeline reached this step: "throw" (the grenade leaves the hand,
        S626/frame_1514) or "runloop" (the run cycle's end, S626/frame_38)"""
        if hook == "runloop":
            run_loop(self, member)
        elif hook == "throw":
            throw_grenade(self, member)

    def run_timers(self) -> None:
        due = [timer for timer in self.timers if timer.due <= self.step]
        if not due:
            return
        self.timers = [timer for timer in self.timers if timer.due > self.step]
        for timer in due:
            if not timer.cancelled:
                timer.fn()

    def root_frame(self) -> None:
        """The root's onEnterFrame while the battle is on (F5:7995-8001)"""
        self.slow_count -= 1
        if self.slow_count <= 0:
            self.slow_tick()
            self.slow_count = SLOW_TICK
        self.medium_count -= 1
        if self.medium_count <= 0:
            self.medium_tick()
            self.medium_count = MEDIUM_TICK
        self.gas_damage("german")
        self.gas_damage("british")

    def slow_tick(self) -> None:
        """Every 40 steps (slowEnterFrame, F5:6828-6842): CPU squads, CPU support, ground, morale regeneration, the
        morale check and surrender, CPU trench orders, in that order"""
        self.slow_ticks += 1
        cpus = [side.cpu for side in self.sides.values() if side.cpu is not None]
        for cpu in cpus:
            cpu.squads_tick(self)
        for cpu in cpus:
            cpu.support_tick(self)
        update_ground(self)
        regen(self)
        check_surrender(self)
        for cpu in cpus:
            cpu.trench_tick(self)

    def medium_tick(self) -> None:
        """Every 4 steps (mediumEnterFrame, F5:6843-6857): mines, wire, officers, German before British each time"""
        find_mines(self, "german")
        find_mines(self, "british")
        find_wire(self, "german")
        find_wire(self, "british")
        find_officers(self, "german")
        find_officers(self, "british")

    def gas_damage(self, side: str) -> None:
        """gasCloudCollisions for one side's squads (F5:8000-8001)"""
        gas_damage(self, side)

    def squad_walk(self) -> None:
        """squadAI("german") then squadAI("british") (F5:8002-8003), each a for..in walk, newest first"""
        for side in ("german", "british"):
            for squad in self.newest_first(self.live_squads(side)):
                self.squad_step(squad)

    def squad_step(self, squad: Squad) -> None:
        """One squad's turn (squadAI F5:1253-2157): while the battle is on, target and trench finding for both sides
        (F5:1311-1317), then the squad's state"""
        if self.state == "playing":
            self.find_all()
        act(self, squad)

    def find_all(self) -> None:
        """findEnemy both ways, then findTrenches for both sides (F5:1313-1316)"""
        find_enemy(self, "british", "german")
        find_enemy(self, "german", "british")
        find_trenches(self, "british")
        find_trenches(self, "german")

    def conquer(self, side: str) -> None:
        """A soldier or tank of `side` crossed the conquer line: that side wins on ground (endBattle, F5:1390-1416)"""
        conquer(self, side)
