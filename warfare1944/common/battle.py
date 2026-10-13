"""One battle on the Red bot: the field, both sides, the battle clock and the order things happen in each step.

The original runs at 30 frames a second; one call to `Battle.tick()` is one of those frames, called a step. Every
rule that decides an outcome runs here, in the original's order, drawing from the battle's own seeded generator, so
the same seed plays the same battle.

Order inside one step (web/flash.js steps clips the same way, so the page and the bot agree):
1. Paused: nothing at all happens, not even timers (the original let timers run through a pause).
2. The clips' own frames: every live member's timelines advance one frame, squads oldest first, members in spawn
   order; then the strike and mine clips count down, start and burst (common/blasts.py); then the HUD's deploy
   dials fill (buttonTimer, F6:5909-5962).
3. Millisecond timers that are due, in the order they were set.
4. The root's onEnterFrame (F6:11850-11869) while the battle is on: the really-slow, find, one-second, slow and
   medium ticks, then every squad's turn (the German squads, then the American, each side newest first), then the
   CPU's unit cooldowns.
5. The step count goes up.
Once the battle has ended, steps 2, 3 and the squads' turns still run, so winners cheer and losers surrender.
"""

import math
import random
import typing as t

from .blasts import Round, run_rounds
from .cpu import Cpu
from .data import (
    FIND_TICK,
    FPS,
    MEDIUM_TICK,
    REALLY_SLOW_TICK,
    SECOND_TICK,
    SIDES,
    SLOW_TICK,
    SUPPLY,
    SUPPLY_TICKS,
    UNIT_KINDS,
    UNITS,
    UPGRADE_EFFECTS,
)
from .missions import Mission
from .morale import check_surrender, conquer, ground_bar, player_order, regen, second_tick, start_front, update_ground
from .orders import unlocked
from .smoke import Cloud, Pending, check_smoke, release, run_clouds
from .squads import Cover, Soldier, Squad, Tank, act, make_squad, recover, run_loop
from .teams import mortar_end, mortar_round, release_grenade, rocket
from .targeting import find_cover, find_enemy, find_mines, find_officers, find_wire

# The dials' starting angle after a deploy (resetButtonTimers F6:5973)
RESET_DIAL = -179
DIAL_FULL = 1000  # the refill dial for the view, 0 to 1000
DIFFICULTIES = ("recruit", "regular", "hardened")
# The tick counters' lengths, and where each starts at a battle start: all fire on the first step except the
# one-second tick, which first fires on step 30 (F6:10097-10106, reset every battle, B54)
TICKS = {
    "really_slow": (REALLY_SLOW_TICK, 0),
    "find": (FIND_TICK, 0),
    "second": (SECOND_TICK, SECOND_TICK),
    "slow": (SLOW_TICK, 0),
    "medium": (MEDIUM_TICK, 0),
}


def wrap_angle(angle: float) -> float:
    """Flash keeps `_rotation` between -180 and 180"""
    if angle > 180:
        return angle - 360
    if angle < -180:
        return angle + 360
    return angle


def dial_steps(timer: float, right: float) -> int:
    """Steps a HUD dial takes to fill (buttonTimer F6:5940-5961). The right half turns from `right` up to 0, then the
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


def flash_round(value: float) -> int:
    """Math.round: halves go up"""
    return math.floor(value + 0.5)


class Timer:
    __slots__ = ("due", "fn", "cancelled")

    def __init__(self, due: int, fn: t.Callable[[], None]):
        self.due = due
        self.fn = fn
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class Side:
    def __init__(
        self, name: str, user: int | None, human: bool, upgrades: frozenset[int], mission: Mission, campaign: bool
    ):
        self.name = name
        self.index = SIDES.index(name)
        self.user = user
        self.human = human
        self.upgrades = upgrades
        # Morale starts full; the human's maximum grows with its morale upgrades (assignMorale, F6:8190-8211)
        self.morale_max: float = mission.morale[name]
        for effect in ("morale_us", "morale_fuhrer", "morale_fatherland"):
            if self.has(effect):
                self.morale_max *= self.effect(effect)
        self.morale: float = self.morale_max
        # The quick messages showing their 15 seconds' wait (common/morale.py)
        self.shown: set[str] = set()
        # The ground held, in whole percents, and the front it comes from: the most forward squad leader seen, and
        # the squad that holds it. A fresh front is the start line.
        self.front: float = start_front(mission.width, name)
        self.front_squad: Squad | None = None
        self.ground: int = ground_bar(mission.width, name, self.front)
        # Morale the side lost and the other side's deaths gave it, for the campaign's career counts
        self.morale_lost = 0.0
        self.morale_gained = 0.0
        # Resource points: the mission's start is also the cap (setupResourcePoints, F6:1427-1437). The refill
        # timer starts at supplyTimerMax 7 (F6:6727) and refills when it goes below 0 (resourceResupply).
        self.rp: int = mission.rp[name]
        self.rp_cap: int = mission.rp[name]
        self.supply_timer = SUPPLY_TICKS - 1
        self.units: list[bool] = list(mission.units[name])
        # Each slot's own deploy dial, counted in steps: a slot is ready when its count reaches its length. Allowed
        # units start ready (F6:5840-5853).
        self.cooldown_max = [dial_steps(self.unit_time(kind), RESET_DIAL) for kind in UNIT_KINDS]
        self.cooldown = [length if on else 0 for length, on in zip(self.cooldown_max, self.units, strict=True)]
        # The order buttons: a campaign side's come from its upgrades, a Custom Battle side's from the screen's toggles
        self.campaign = campaign
        self.custom_orders: frozenset[str] = frozenset(mission.orders[name])
        self.orders: frozenset[str] = unlocked(self)
        self.squads: list[Squad] = []
        self.officers: list[Squad] = []
        spots, count = mission.mines[name]
        self.mines: list[float] = list(spots)
        self.mine_count: int = count
        self.kills = 0
        self.lost = 0
        # Soldiers shot dead by this side and soldiers of this side shot dead, for the campaign's career counts
        self.soldier_kills = 0
        self.soldier_losses = 0
        self.deployed = 0
        self.deployed_kinds: dict[str, int] = {}
        self.support_used = 0
        self.covers_held = 0
        self.cpu: Cpu | None = None

    def has(self, effect: str) -> bool:
        """Whether this side owns the upgrade that brings `effect` (data.UPGRADE_EFFECTS)"""
        return UPGRADE_EFFECTS[effect]["numbers"].get(self.name) in self.upgrades

    @staticmethod
    def effect(effect: str) -> float:
        return UPGRADE_EFFECTS[effect]["value"]

    def unit_time(self, kind: str) -> float:
        """A unit's deploy timer with this side's own cooldown upgrades (buttonTimer F6:5917-5939, B20): the tank
        with Armor Production, every other slot with the two reinforcement upgrades"""
        time = UNITS[self.name][kind]["cooldown"]
        effects = ("tank_timer",) if kind == "tank" else ("timer_10", "timer_15")
        for effect in effects:
            if self.has(effect):
                time *= self.effect(effect)
        return time

    def unit_ready(self, index: int) -> bool:
        return self.units[index] and self.cooldown[index] >= self.cooldown_max[index]

    def restart_slot(self, index: int) -> None:
        """resetButtonTimers (F6:5963-5976): only the slot just used starts over, at the length the upgrades owned
        now give"""
        if self.units[index]:
            self.cooldown_max[index] = dial_steps(self.unit_time(UNIT_KINDS[index]), RESET_DIAL)
            self.cooldown[index] = 0

    def retime(self) -> None:
        """The dials' lengths again after the upgrades changed. buttonTimer reads the upgrade flags on every frame,
        so a purchase speeds the dials at once: each keeps the same fraction filled."""
        for index, kind in enumerate(UNIT_KINDS):
            length = dial_steps(self.unit_time(kind), RESET_DIAL)
            self.cooldown[index] = round(self.cooldown[index] * length / self.cooldown_max[index])
            self.cooldown_max[index] = length

    def count_timers(self) -> None:
        """The HUD dials' onEnterFrame (F6:5909-5915): each allowed slot that isn't ready fills one step"""
        for index, on in enumerate(self.units):
            if on and self.cooldown[index] < self.cooldown_max[index]:
                self.cooldown[index] += 1

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
        difficulty: str = "regular",
    ):
        """`humans` maps each side to its player's user id, or None for the CPU. `upgrades` holds each human side's
        owned upgrade numbers. Custom battles and versus games play at "regular" (F6:9317)."""
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty {difficulty!r}")
        self.mission = mission
        self.seed = seed
        self.rng = random.Random(seed)
        self.first_try = first_try
        self.campaign = campaign
        self.difficulty = difficulty
        self.step = 0
        self.paused = False
        self.state = "playing"
        self.ended_at: int | None = None
        self.winner: str | None = None
        self.how: str | None = None
        self.width: float = mission.width
        # One counter for squads, soldiers, tanks, clouds and rounds, from 1: the page's cover rows use 0 for empty
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
            self.sides[name] = Side(name, user, human, owned, mission, campaign)
        # buildMap, F6:7267-7379: covers lane 1's first, then lane 2's, then lane 3's; the wire lines' x (their
        # posts' random spread is drawn on the page)
        self.covers = [Cover(index, lane, x, kind) for index, (lane, x, kind) in enumerate(mission.covers)]
        self.wires: list[float] = list(mission.wires)
        self.timers: list[Timer] = []
        # Objective wipe-outs waiting 3 seconds to end the battle, and pre-placed squads waiting to appear: the end
        # drops both (common/morale.py `end`)
        self.objective_timers: list[Timer] = []
        self.spawn_timers: list[Timer] = []
        # Unpaused seconds played, the defend countdown's seconds left (-1 once it ran out; None on a mission with no
        # countdown), and whether the CPU may still deploy (spawnEnemyActive, F6:6730)
        self.mission_seconds = 0
        self.defend_left: int | None = None if mission.timed is None else mission.timed[0] * 60 + mission.timed[1]
        self.spawn_active = True
        # Strike, mine and shell clips on the field, oldest first, and how many were ever made (specialRounds)
        self.rounds: list[Round] = []
        self.round_count = 0
        # Destroyed tanks and bunkers: they leave their squads but stay on the field as burning wrecks (deadTanks)
        self.wrecks: list[Tank] = []
        # Smoke screens on the field, oldest first, from appearing to faded; smoke grenades in the air and screen
        # clips waiting for their smoke frame (common/smoke.py)
        self.smoke: list[Cloud] = []
        self.smoke_clips: list[Pending] = []
        self.events: list[list] = []
        self.counters = {name: start for name, (_length, start) in TICKS.items()}
        # Slow ticks run so far, which the page counts to redo a ground bar's red flash on each
        self.slow_ticks = 0
        # Every side without a player is the CPU's, and it places its free squads at the start (startBattle)
        for name, side in self.sides.items():
            if not side.human:
                side.cpu = Cpu(name, mission, difficulty)
                side.cpu.place_squads(self)

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
        """british.spawnPoint and german.spawnPoint, F6:7372-7373 (the 1700 at F6:10179 is overwritten)"""
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

    def lane_has_cover(self, lane: int) -> bool:
        """Whether the map puts any cover in this lane (currentMap.coverZone<n>), which shuts it to tanks"""
        return any(cover.lane == lane for cover in self.covers)

    def adjust_rp(self, side: str, amount: int) -> None:
        """adjustRP (F6:1345-1426): add or spend, kept between 0 and the cap"""
        owner = self.sides[side]
        owner.rp = max(0, min(owner.rp + amount, owner.rp_cap))
        self.event("rp", owner.index, amount)

    def cost(self, side: str, slot: int) -> int:
        """A unit's deploy price for this side (setUnitCosts F6:1278-1302). The owner's In Good Supply makes infantry
        x0.8, rounded; its Conscripts makes riflemen 100 (W3, B20, B24). Tanks pay full price."""
        owner = self.sides[side]
        kind = UNIT_KINDS[slot - 1]
        price = UNITS[side][kind]["cost"]
        if kind == "riflemen" and owner.has("conscripts"):
            price = int(owner.effect("conscripts"))
        if kind != "tank" and owner.has("good_supply"):
            price = flash_round(price * owner.effect("good_supply"))
        return price

    def refill_dial(self) -> int:
        """How far the RP refill has come, 0 to 1000 (resourceResupplyTimer F6:1329-1344 turns it each slow tick)"""
        timer = self.sides[SIDES[0]].supply_timer
        return round((SUPPLY_TICKS - 1 - timer) * DIAL_FULL / SUPPLY_TICKS)

    def deploy(self, side: str, slot: int, lane: int) -> bool:
        """A human side's deploy into a lane (setupDeployButtons' onPress, F6:1893-1934). False when refused"""
        owner = self.sides.get(side)
        if owner is None or not owner.human or self.state != "playing" or self.paused:
            return False
        for value, top in ((slot, len(UNIT_KINDS)), (lane, 3)):
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= top:
                return False
        if not owner.unit_ready(slot - 1):
            return False
        kind = UNIT_KINDS[slot - 1]
        if kind == "tank" and self.lane_has_cover(lane):
            self.event("msg", "blocked", owner.index, None)
            return False
        price = self.cost(side, slot)
        if owner.rp < price:
            self.event("msg", "rp", owner.index, price)
            return False
        self.adjust_rp(side, -price)
        make_squad(self, side, kind, lane)
        owner.restart_slot(slot - 1)
        self.event("deploy", owner.index, slot, lane)
        return True

    def place_squad(self, side: str, kind: str, lane: int, x: float | None = None, objective: bool = False) -> Squad:
        """createSquad with no deploy checks and no price: a pre-placed squad (common/tanks.py `make_bunker`)"""
        return make_squad(self, side, kind, lane, x, objective)

    def tick(self) -> None:
        """One step of the battle, in the order this module's docstring lists"""
        if self.paused:
            return
        self.advance_clips()
        self.run_timers()
        if self.state == "playing":
            self.root_frame()
        else:
            self.squad_walk()
        self.step += 1

    def advance_clips(self) -> None:
        squads = sorted((squad for side in self.sides.values() for squad in side.squads), key=lambda squad: squad.id)
        for squad in squads:
            for member in squad.members:
                if not member.alive:
                    continue
                if isinstance(member, Tank):
                    for timeline in member.timelines():
                        timeline.advance()
                    continue
                for hook in member.timeline.advance():
                    self.member_hook(member, hook)
                # A suppressed soldier's recovery reads the frame it reached (common/combat.py `suppress`)
                if member.suppressed:
                    recover(self, member)
        run_rounds(self)
        run_clouds(self)
        if self.state == "playing":
            for side in self.sides.values():
                if side.human:
                    side.count_timers()

    def member_hook(self, member: Soldier, hook: str) -> None:
        """A frame script hook a soldier's timeline reached this step: "runloop" (the run cycle's end,
        S666/frame_34), "rocket" (the bazooka round leaves, S666/frame_634), "mortar" (the mortar fires,
        S666/frame_829), "mortarend" (the mortar cycle's end, S666/frame_905) or "throw" (the grenade or smoke
        grenade leaves the hand, S666/frame_1436)"""
        if hook == "runloop":
            run_loop(self, member)
        elif hook == "rocket":
            rocket(self, member)
        elif hook == "mortar":
            mortar_round(self, member)
        elif hook == "mortarend":
            mortar_end(self, member)
        elif hook == "throw" and member.gren_type == "smokeGrenade":
            release(self, member)
        elif hook == "throw":
            release_grenade(self, member)

    def run_timers(self) -> None:
        due = [timer for timer in self.timers if timer.due <= self.step]
        if not due:
            return
        self.timers = [timer for timer in self.timers if timer.due > self.step]
        for timer in due:
            if not timer.cancelled:
                timer.fn()

    def ticked(self, name: str) -> bool:
        """One tick counter counts down a step; at 0 or less it fires and starts over"""
        self.counters[name] -= 1
        if self.counters[name] > 0:
            return False
        self.counters[name] = TICKS[name][0]
        return True

    def root_frame(self) -> None:
        """The root's onEnterFrame while the battle is on (F6:11850-11862). The really-slow tick's work is the
        CPU's cover leaving (enemyUnitAI, F6:10042-10051; its depth sort is the page's). The one-second tick's is the
        defend countdown, the mission clock (common/morale.py `second_tick`) and the CPU's deploys (F6:10031-10041).
        After the squads come the CPU's unit cooldowns (runEnemyTimers)."""
        if self.ticked("really_slow"):
            for cpu in self.cpus():
                cpu.cover_tick(self)
        if self.ticked("find"):
            self.find_tick()
        if self.ticked("second"):
            second_tick(self)
            for cpu in self.cpus():
                cpu.deploy_tick(self)
        if self.ticked("slow"):
            self.slow_tick()
        if self.ticked("medium"):
            self.medium_tick()
        self.squad_walk()
        for cpu in self.cpus():
            cpu.run_timers(self)

    def cpus(self) -> list[Cpu]:
        """The CPUs on the field, in the player-first order the other per-side work runs in"""
        return [cpu for name in player_order(self) if (cpu := self.sides[name].cpu) is not None]

    def find_tick(self) -> None:
        """findEnterFrame (F6:10017-10030): the smoke check and cover finding, American then German each, then
        target finding both ways"""
        check_smoke(self, "british")
        check_smoke(self, "german")
        find_cover(self, "british")
        find_cover(self, "german")
        find_enemy(self, "british", "german")
        find_enemy(self, "german", "british")

    def slow_tick(self) -> None:
        """slowEnterFrame (F6:9988-10001): the RP refill and its dial, the CPU's fire support, the ground bars, the
        morale bar and surrender check, morale regeneration"""
        self.slow_ticks += 1
        self.resupply()
        for cpu in self.cpus():
            cpu.support_tick(self)
        update_ground(self)
        check_surrender(self)
        regen(self)

    def resupply(self) -> None:
        """resourceResupply (F6:1319-1328): every 8th slow tick both sides get 200 RP, the player first"""
        for name in player_order(self):
            side = self.sides[name]
            side.supply_timer -= 1
            if side.supply_timer < 0:
                side.supply_timer = SUPPLY_TICKS - 1
                self.adjust_rp(name, SUPPLY)

    def medium_tick(self) -> None:
        """mediumEnterFrame (F6:10002-10016): mines, wire, officers, German before American each time"""
        find_mines(self, "german")
        find_mines(self, "british")
        find_wire(self, "german")
        find_wire(self, "british")
        find_officers(self, "german")
        find_officers(self, "british")

    def squad_walk(self) -> None:
        """squadAI("german") then squadAI("british") (F6:11858-11859), each a for..in walk, newest first"""
        for side in ("german", "british"):
            for squad in self.newest_first(self.live_squads(side)):
                act(self, squad)

    def conquer(self, side: str) -> None:
        """A soldier or tank of `side` crossed the conquer line: that side wins on ground"""
        conquer(self, side)
