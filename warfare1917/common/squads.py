"""Squads and what they are made of: soldiers, tanks and trenches.

A squad is one deployment: its members spawn one at a time (createSquad F5:1053-1129, createSoldier F5:1143-1250) and
share one health pool. The battle engine walks squads and moves their members; the frame scripts of each member's
timeline (common/timeline.py) say when an animation has finished.

Each squad is in one of STATES; `act` runs one squad's step in its state, as the original's squadAI switch does
(F5:1318-2157), and `soldier_movements` starts the poses, get-ups, runs, cheers and surrenders (F5:2160-2203).
"""

import math
import typing as t

from . import anims
from .combat import shoot, trench_shot
from .data import CONQUER_AREA, MORALE_COST, SOLDIERS, UNITS, WIRE_SPEED
from .gas import state_masks_off, state_masks_on
from .tanks import GRENADE_AT_TANK, GRENADE_AT_TRENCH, grenade_pick, tank_act
from .timeline import Timeline

if t.TYPE_CHECKING:
    from .battle import Battle

SPAWN_GAP_MS = 300  # one member every 300 ms, F5:1126
JUMPS_KEPT = 3  # one update's steps (common/lobby.py STEPS): the jumps a soldier's row carries
GROUND = 170  # world.ground, F5:4632
TRENCH_SLOTS = 3


class Trench:
    def __init__(self, index: int, x: float):
        self.index = index
        self.x = x
        # Which side holds it: "british", "german" or None (ownerTeam, F5:4643)
        self.owner: str | None = None
        # The squad in each of the trench's three slots ("empty" in the original)
        self.slots: list[Squad | None] = [None] * TRENCH_SLOTS
        self.locked = False


class Squad:
    def __init__(self, battle: "Battle", squad_id: int, side: str, kind: str):
        unit = UNITS[side][kind]
        self.id = squad_id
        self.side = side
        self.kind = kind
        self.slot: int = unit["slot"]
        self.members: list[Soldier | Tank] = []
        self.hp: float = unit["hp"]
        self.pool: float = unit["pool"]
        # Pool the members spawned so far add up to (totalHealth, F5:1160)
        self.total = 0.0
        self.speed: float = unit["speed"]
        self.range: float = unit["range"]
        self.state = "tankMoving" if kind == "tank" else "moving"
        self.last_state = "moving"
        self.target: Squad | None = None
        self.target_dist: float = 999999
        self.hit = False
        self.trench: Trench | None = None
        self.trench_slot: int | None = None
        self.near_trench = False
        self.in_trench = False
        self.all_in_trench = False
        self.passing = False
        self.in_wire = False
        self.near_gas = False
        self.near_officer = False
        self.officer: Squad | None = None
        self.masks = "off"
        self.spawned_at = battle.step

    @property
    def leader(self) -> "Soldier | Tank | None":
        for member in self.members:
            if member.alive:
                return member
        return None

    @property
    def size(self) -> int:
        return len(UNITS[self.side][self.kind]["members"])


class Soldier:
    def __init__(self, battle: "Battle", squad: Squad, soldier_type: str):
        self.id = battle.new_id()
        self.squad = squad
        self.type = soldier_type
        stats = SOLDIERS[squad.side][soldier_type]
        self.damage: float = stats["damage"]
        self.weapon: str = stats["weapon"]
        self.alive = True
        # Draws in createSoldier's order: size F5:1156, drift timer F5:1197, y F5:1217
        self.scale = (battle.random(7) + 105) / 100
        self.direction_count_max = 100
        self.direction_count = self.direction_count_max - battle.random(self.direction_count_max)
        self.y: float = GROUND + battle.random(110)
        self.ground = self.y
        self.x: float = battle.spawn_x(squad.side)
        # Pool level at or below which this member dies: (k + 1) x HP for the k-th member (health, F5:1161)
        squad.total += squad.hp
        self.threshold = squad.total
        # The frame scripts' variables plus the ones the engine sets beside them (F5:1166-1215)
        self.flags: dict = {
            "position": "standing",
            "inPosition": False,
            "changingPosition": False,
            "inMovingPosition": True,
            "animating": True,
            "moveAnim": True,
            "firing": False,
            "firingSecondary": False,
            "throwingGrenade": False,
            "changingToMove": False,
            "changingToFire": False,
            "changingToEntrench": False,
            "inFiringPosition": False,
            "gasMaskOn": False,
            "gasMaskOff": False,
            "inTrench": False,
            "enteringTrench": False,
            "exitedTrench": False,
        }
        self.timeline = Timeline(anims.SOLDIER, self.flags)
        # Per-soldier counters the squad states use (F5:1181-1215)
        self.moving_up = False
        self.moving_down = False
        self.burst_counter = 1
        self.wait_counter = 0
        self.mg_burst_counter = 0
        self.mg_wait_counter = 0
        self.end_battle_anim = False
        self.way_point: float | None = None
        self.way_point_set = False
        self.way_point_reached = False
        self.trench_way_point: float | None = None
        self.trench_way_point_set = False
        self.trench_way_point_reached = False
        self.in_trench_position = False
        self.exiting_trench = False
        self.putting_on_mask = False
        self.taking_off_mask = False
        # Set by a trench firing delay timer, cleared when the squad loses its target (startFiring, F5:1188, 2207)
        self.start_firing = False
        # Where the engine jumped the timeline, newest last: (frame, playing, step), for the page. The last jump of
        # each of the newest JUMPS_KEPT steps, so an update holds every jump since the one before it
        self.jumps: list[tuple[int, bool, int]] = [(1, True, battle.step)]
        # A soldier joins its run cycle at a random frame (F5:1244)
        self.goto(battle, 20 + battle.random(15), True)

    def goto(self, battle: "Battle", target: str | int, play: bool) -> None:
        """gotoAndPlay / gotoAndStop on the soldier's timeline, recorded so the page can play it from the same step.
        Flash ignores a jump to a label the clip doesn't have ("victory_prone"), and so does this"""
        if isinstance(target, str) and target not in self.timeline.labels:
            return
        if play:
            self.timeline.goto_and_play(target)
        else:
            self.timeline.goto_and_stop(target)
        self.jumped(battle, self.timeline.playing)

    def stop(self, battle: "Battle") -> None:
        """stop() from a frame script whose choice depends on the engine, recorded for the page like a jump"""
        self.timeline.stop()
        self.jumped(battle, False)

    def jumped(self, battle: "Battle", playing: bool) -> None:
        """Records the timeline's jump on this step, replacing an earlier jump on the same step"""
        if self.jumps[-1][2] == battle.step:
            self.jumps.pop()
        self.jumps.append((self.timeline.frame, playing, battle.step))
        del self.jumps[:-JUMPS_KEPT]


class Tank:
    def __init__(self, battle: "Battle", squad: Squad):
        self.id = battle.new_id()
        self.squad = squad
        self.type = "tankMarkIV"
        self.damage: float = SOLDIERS[squad.side][self.type]["damage"]
        self.alive = True
        # Draws in createSoldier's order: the size and drift timer every member draws, then a soldier's y, which the
        # tank's own y replaces (F5:1156, 1197, 1217-1220). The number painted on the tank is drawn on the page.
        self.scale = (battle.random(7) + 105) / 100
        self.direction_count_max = 100
        self.direction_count = self.direction_count_max - battle.random(self.direction_count_max)
        battle.random(110)
        self.y: float = 230 + (battle.random(80) - 40)
        self.ground = self.y
        self.x: float = battle.spawn_x(squad.side)
        squad.total += squad.hp
        self.threshold = squad.total
        self.health: float = squad.pool
        # The guns' frame scripts write `firing` and `firingSecondary` into the tank (their `_parent`)
        self.flags: dict = {"firing": False, "firingSecondary": False}
        self.gun = Timeline(anims.TANK_GUN, self.flags)
        self.mg = Timeline(anims.TANK_MG, self.flags)
        self.gun_stamp = battle.step
        self.mg_stamp = battle.step
        # The main gun's counters start where every member's do (F5:1204-1205): one shot already counted
        self.burst_counter = 1
        self.wait_counter = 0
        self.mg_burst_counter = 0
        self.mg_wait_counter = 0


def spawn_member(battle: "Battle", squad: Squad, soldier_type: str) -> None:
    """createSoldier for one member. The member joins the squad it was deployed with. The German soldier's
    horizontal size is replaced by the mirror (F5:1235), so only its height keeps the random size."""
    member = Tank(battle, squad) if squad.kind == "tank" else Soldier(battle, squad, soldier_type)
    squad.members.append(member)


def make_squad(battle: "Battle", side: str, kind: str) -> Squad:
    """createSquad (F5:1053-1129): counts the deployment, gives the officer's or tank's morale, and spawns the members
    one every 300 ms on the battle clock, first one at once."""
    squad = Squad(battle, battle.new_id(), side, kind)
    owner = battle.sides[side]
    owner.deployed += 1
    owner.deployed_kinds[kind] = owner.deployed_kinds.get(kind, 0) + 1
    if kind == "tank":
        owner.add_morale(MORALE_COST["tank_bonus"])
    if kind == "officer":
        owner.officers.append(squad)
        owner.add_morale(MORALE_COST["officer_bonus"])
    # for..in walks the member list newest first, but each timer's delay is its index, so they spawn in list order
    for index, soldier_type in enumerate(UNITS[side][kind]["members"]):
        battle.after(SPAWN_GAP_MS * index, lambda soldier_type=soldier_type: spawn_member(battle, squad, soldier_type))
    owner.squads.append(squad)
    return squad


# The squad states, in the order squadAI's switch lists them (F5:1318-2157). Nothing in the original sets "stopped".
STATES = (
    "moving",
    "engaging",
    "assaultTrench",
    "stopped",
    "entrench",
    "exitTrench",
    "gasMasksOn",
    "gasMasksOff",
    "tankMoving",
    "tankDead",
    "tankEngaging",
    "victory",
    "defeated",
)

DRIFT_SPEED = 6  # a drifting soldier moves speed / 6 up or down, F5:1374-1381
DRIFT_RANGE = 100  # and stays between world.ground and world.ground + 100, F5:1374-1381
STOP_SPREAD = 50  # Engaging's stop point: up to 49 pixels ahead, F5:1446-1499
STOP_FROM_EDGE = 100  # a soldier still off the field stops 100 to 149 pixels in, F5:1452, 1484
ASSAULT_GAP = 150  # an assault squad stops 150 to 209 pixels short of the trench, F5:1640-1646
ASSAULT_SPREAD = 60
TRENCH_HALF = 69.5  # half the trench clip's width (139, sprite 1508): trenchRef._width / 2, F5:1746, 1751
TRENCH_SPOT = {"british": (15, 37), "german": (15, 32)}  # random(15) + 37 and random(15) + 32 in, F5:1746-1751
EXIT_JUMP = 60  # a soldier out of the trench jumps 60 pixels forward, F5:1919-1926
POSE_WAIT = (400, 100)  # random(400) + 100 ms before a pose, a get-up or a cheer, F5:1361, 1524-1535, 2125
DEFEAT_WAIT = (200, 100)  # random(200) + 100 ms before surrendering, F5:2142, 2152
POSES = {1: "stand", 2: "crouch", 3: "prone"}
ASSAULT_POSES = {1: "crouch", 2: "stand"}


def num(value: float | None) -> float:
    """A way point as ActionScript compares it: null is NaN in a SWF 7 or later, so every comparison with it fails"""
    return math.nan if value is None else value


def facing(side: str) -> int:
    """+1 for the British, who advance to the right; -1 for the Germans"""
    return 1 if side == "british" else -1


def step_speed(squad: Squad) -> float:
    """A squad's pace this step: speed / 1.5 in wire (wireSpeedMod)"""
    return squad.speed / WIRE_SPEED if squad.in_wire else squad.speed


def target_alive(squad: Squad) -> bool | None:
    """The original's `enemyTarget.members[0].alive`: None when there is no target or it has no members left (a
    dead soldier leaves the list, a dead tank stays in it with alive false)"""
    if squad.target is None or not squad.target.members:
        return None
    return squad.target.members[0].alive


def set_state(squad: Squad, state: str) -> None:
    if state not in STATES:
        raise ValueError(f"Unknown squad state {state!r}")
    squad.state = state


def stop_firing(squad: Squad) -> None:
    """A squad that lost its target: no member fires or waits on a trench firing delay any more (F5:2249-2253)"""
    for member in squad.members:
        if isinstance(member, Soldier):
            member.start_firing = False
        member.flags["firing"] = False


def soldier_movements(battle: "Battle", move: str, soldier: "Soldier | None") -> None:
    """soldierMovements (F5:2160-2203): start a pose, a get-up, a run, a cheer or a surrender. A dead soldier, or no
    soldier at all, does nothing. Every soldier's weapon type is "rifle" (createSoldier F5:1179)."""
    if not isinstance(soldier, Soldier) or not soldier.alive:
        return
    labels = {
        "victory": "victory_" + soldier.flags["position"],
        "defeatTrench": "defeat_trench",
        "defeatGround": "defeat_standing",
        "crouch": "rifle_stop_crouch",
        "stand": "rifle_stop_standing",
        "prone": "rifle_stop_prone",
        "proneToStand": "rifle_start_prone",
        "crouchToStand": "rifle_start_crouch",
        "standingToStand": "rifle_start_standing",
    }
    if move == "run":
        if not soldier.flags["changingToMove"]:
            soldier.goto(battle, "rifle_run", True)
    elif move in labels:
        soldier.goto(battle, labels[move], True)


def movement_later(battle: "Battle", wait: tuple[int, int], move: str, soldier: Soldier) -> None:
    """setTimeout(soldierMovements, random(a) + b, move, soldier): the move is named now, played when the timer runs"""
    battle.after(battle.random(wait[0]) + wait[1], lambda: soldier_movements(battle, move, soldier))


def run_loop(battle: "Battle", soldier: Soldier) -> None:
    """S626/frame_38, the end of one run cycle: run on, or stop on this frame when the soldier is stopping to fire,
    getting into a trench, or the battle is over"""
    flags = soldier.flags
    if soldier.alive and not flags["changingToFire"] and not flags["enteringTrench"] and battle.state == "playing":
        # gotoAndStop("rifle_run") then play()
        soldier.goto(battle, "rifle_run", False)
        soldier.timeline.play()
        soldier.jumped(battle, True)
    else:
        soldier.stop(battle)
        flags["moveAnim"] = False


def act(battle: "Battle", squad: Squad) -> None:
    """One squad's turn in its state (squadAI's switch, F5:1318-2157). Each state walks the members with for..in,
    newest first. The tank states are common/tanks.py's; the gas mask states are common/gas.py's."""
    handler = STATE_HANDLERS.get(squad.state)
    if handler is not None:
        handler(battle, squad)


def reset_for_moving(soldier: Soldier) -> None:
    """Moving clears every stop point and firing flag, every step (F5:1331-1340)"""
    soldier.flags["firing"] = False
    soldier.flags["inFiringPosition"] = False
    soldier.flags["inTrench"] = False
    soldier.way_point = None
    soldier.trench_way_point = None
    soldier.way_point_set = False
    soldier.way_point_reached = False
    soldier.trench_way_point_set = False
    soldier.trench_way_point_reached = False


def drift_roll(battle: "Battle", soldier: Soldier) -> None:
    """The drift timer: when it runs out, 1 in 10 drift up, 1 in 10 down, else straight on (F5:1341-1358)"""
    soldier.direction_count -= 1
    if soldier.direction_count < 0:
        soldier.direction_count = soldier.direction_count_max
        roll = battle.random(10)
        if roll == 0:
            soldier.moving_up = True
        if roll == 1:
            soldier.moving_down = True
        if roll > 1:
            soldier.moving_up = False
            soldier.moving_down = False


def advance(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A running soldier's step forward and drift, then the conquer line (F5:1374-1416)"""
    soldier.x += facing(squad.side) * step_speed(squad)
    if soldier.moving_up and soldier.y > GROUND:
        soldier.y -= squad.speed / DRIFT_SPEED
    if soldier.moving_down and soldier.y < GROUND + DRIFT_RANGE:
        soldier.y += squad.speed / DRIFT_SPEED
    if squad.side == "british":
        crossed = soldier.x > battle.width - CONQUER_AREA
    else:
        crossed = soldier.x < CONQUER_AREA
    if crossed:
        battle.conquer(squad.side)


def state_moving(battle: "Battle", squad: Squad) -> None:
    """Moving (F5:1320-1421)"""
    for soldier in battle.newest_first(squad.members):
        # The engine's global movingSoldierRef, which Engaging later hands to soldierMovements (F5:1453)
        battle.moving_ref = soldier
        reset_for_moving(soldier)
        drift_roll(battle, soldier)
        if not soldier.alive or battle.state != "playing":
            continue
        flags = soldier.flags
        if not flags["changingToMove"] and not flags["inMovingPosition"]:
            # Get up from its pose after a short wait: "standingToStand", "crouchToStand", "proneToStand"
            flags["changingToMove"] = True
            movement_later(battle, POSE_WAIT, flags["position"] + "ToStand", soldier)
        if not flags["changingToMove"] and flags["inMovingPosition"]:
            if not flags["moveAnim"]:
                flags["moveAnim"] = True
                soldier_movements(battle, "run", soldier)
            advance(battle, squad, soldier)


def pick_stop(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """Engaging's stop point (F5:1440-1508). Starting the run hands soldierMovements the engine's movingSoldierRef,
    not this soldier, as the original does"""
    flags = soldier.flags
    if squad.near_trench:
        soldier.way_point = soldier.x + facing(squad.side)
    else:
        if not flags["moveAnim"] and soldier.alive:
            flags["moveAnim"] = True
            soldier_movements(battle, "run", battle.moving_ref)
        spread = battle.random(STOP_SPREAD)
        if squad.side == "british":
            soldier.way_point = soldier.x + spread if soldier.x > -STOP_SPREAD else STOP_FROM_EDGE + spread
        elif soldier.x < battle.width:
            soldier.way_point = soldier.x - spread
        else:
            soldier.way_point = battle.width - STOP_FROM_EDGE - spread
    soldier.way_point_set = True


def ready_to_pose(soldier: Soldier) -> bool:
    flags = soldier.flags
    return soldier.way_point_reached and not flags["inFiringPosition"] and not flags["changingToFire"] and soldier.alive


def take_pose(battle: "Battle", soldier: Soldier) -> None:
    """Stop at the way point and go idle; the pose follows after a short wait (F5:1519-1522, 1664-1667)"""
    soldier.flags["changingToFire"] = True
    soldier.flags["inMovingPosition"] = False
    soldier.flags["moveAnim"] = False
    soldier.goto(battle, "stop_idle", False)


def check_target_lost(battle: "Battle", squad: Squad) -> None:
    """A target with no members, or a dead tank, sends a squad that isn't in a trench back to Moving
    (F5:1557-1563, 1690-1696)"""
    if battle.state != "playing" or squad.in_trench:
        return
    alive = target_alive(squad)
    if alive is None or (squad.target.kind == "tank" and alive is False):
        squad.state = "moving"


def firing_chance(squad: Squad, soldier: Soldier) -> bool:
    """Whether a soldier in its pose may fire now: the target has a member and the soldier isn't mid-shot
    (F5:1564-1566, 1697-1699). Its moving pose is over either way. The shot or grenade follows (F5:1567-1615,
    1700-1720)"""
    flags = soldier.flags
    if target_alive(squad) is not None and flags["inFiringPosition"] and not flags["firing"] and soldier.alive:
        flags["inMovingPosition"] = False
        return True
    return False


def state_engaging(battle: "Battle", squad: Squad) -> None:
    """Engaging (F5:1422-1618): run to a stop point, take a pose, fire from it"""
    ahead = facing(squad.side)
    for soldier in battle.newest_first(squad.members):
        if not soldier.alive:
            continue
        if not soldier.way_point_set:
            pick_stop(battle, squad, soldier)
        if ahead * soldier.x < ahead * num(soldier.way_point):
            soldier.x += ahead * step_speed(squad)
        if ahead * soldier.x >= ahead * num(soldier.way_point):
            soldier.way_point_reached = True
        if ready_to_pose(soldier):
            take_pose(battle, soldier)
            # Riflemen, assault and sharpshooters pick any pose, the officer stands, the machine gunner kneels or
            # lies down; every soldier still draws random(3) first (F5:1522-1530)
            pick = battle.random(3) + 1
            if soldier.type == "lieutenant":
                pick = 1
            if soldier.type == "machineGunner":
                pick = battle.random(2) + 2
            movement_later(battle, POSE_WAIT, POSES[pick], soldier)
        check_target_lost(battle, squad)
        if firing_chance(squad, soldier):
            if squad.target is not None and squad.target.kind == "tank":
                grenade_pick(battle, squad, soldier, GRENADE_AT_TANK)
            shoot(battle, soldier)


def assault_point(battle: "Battle", squad: Squad) -> float:
    """150 to 209 pixels short of the target's trench (F5:1640-1646). With no trench the point is NaN, so the
    soldier neither moves nor arrives, as the original's undefined arithmetic does"""
    spread = battle.random(ASSAULT_SPREAD)
    trench = squad.target.trench if squad.target is not None else None
    if trench is None:
        return math.nan
    return trench.x - facing(squad.side) * (ASSAULT_GAP + spread)


def state_assault(battle: "Battle", squad: Squad) -> None:
    """Assaulting a trench (F5:1619-1724): stand off from the target's trench, kneel or stand, then fire or throw.
    Arriving counts from the step after the last move (the original's else-if)"""
    ahead = facing(squad.side)
    for soldier in battle.newest_first(squad.members):
        if not soldier.alive:
            continue
        if not soldier.way_point_set:
            soldier.way_point = assault_point(battle, squad)
            soldier.way_point_set = True
        if ahead * soldier.x <= ahead * num(soldier.way_point):
            soldier.x += ahead * step_speed(squad)
        elif ahead * soldier.x >= ahead * num(soldier.way_point):
            soldier.way_point_reached = True
        if ready_to_pose(soldier):
            take_pose(battle, soldier)
            movement_later(battle, POSE_WAIT, ASSAULT_POSES[battle.random(2) + 1], soldier)
        check_target_lost(battle, squad)
        if firing_chance(squad, soldier):
            grenade_pick(battle, squad, soldier, GRENADE_AT_TRENCH)
            shoot(battle, soldier)


def trench_spot(battle: "Battle", squad: Squad) -> float:
    """A soldier's spot in its squad's trench (F5:1743-1752)"""
    spread, inset = TRENCH_SPOT[squad.side]
    offset = battle.random(spread) + inset
    if squad.trench is None:
        return math.nan
    if squad.side == "british":
        return squad.trench.x - TRENCH_HALF + offset
    return squad.trench.x + TRENCH_HALF - offset


def run_to_trench(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """Run to the trench spot, and arrive there (F5:1754-1802). Arriving clears the spot, so the soldier neither
    moves nor arrives again until it is given a new one"""
    flags = soldier.flags
    ahead = facing(squad.side)
    if ahead * soldier.x < ahead * num(soldier.trench_way_point):
        if not flags["moveAnim"] and soldier.alive and not flags["enteringTrench"]:
            flags["changingToMove"] = False
            flags["changingToFire"] = False
            flags["moveAnim"] = True
            soldier_movements(battle, "run", soldier)
        soldier.x += ahead * step_speed(squad)
    if ahead * soldier.x >= ahead * num(soldier.trench_way_point):
        soldier.trench_way_point_reached = True
        soldier.in_trench_position = True
        soldier.trench_way_point = None


def trench_firing_chance(squad: Squad, soldier: Soldier) -> bool:
    """Whether a soldier in the trench may start its firing delay or fire: the target has a member and the soldier
    isn't mid-shot (F5:1844). The delay timers and the shot follow (F5:1846-1895)"""
    flags = soldier.flags
    return target_alive(squad) is not None and flags["inTrench"] and not flags["firing"]


def state_entrench(battle: "Battle", squad: Squad) -> None:
    """Entrenching (F5:1731-1897): run to a spot in the trench, play Enter trench, then fire from it. A squad
    passing through leaves once every member is in"""
    for soldier in battle.newest_first(squad.members):
        if not soldier.alive:
            continue
        flags = soldier.flags
        if not soldier.trench_way_point_set:
            soldier.trench_way_point = trench_spot(battle, squad)
            soldier.trench_way_point_set = True
        run_to_trench(battle, squad, soldier)
        if soldier.trench_way_point_reached and soldier.in_trench_position and not flags["inTrench"]:
            if not flags["enteringTrench"]:
                flags["enteringTrench"] = True
                soldier.goto(battle, "enterTrench_officer" if soldier.type == "lieutenant" else "enterTrench", True)
        if flags["inTrench"] and squad.trench is not None:
            squad.trench.owner = squad.side
        squad.all_in_trench = all(member.flags["inTrench"] for member in squad.members)
        if squad.passing and squad.all_in_trench:
            squad.state = "exitTrench"
            squad.passing = False
        if trench_firing_chance(squad, soldier):
            trench_shot(battle, soldier)


def leave_trench(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A soldier whose Leave trench has played: jump forward, run, and take the squad back to Moving
    (F5:1917-1946)"""
    flags = soldier.flags
    flags["exitedTrench"] = False
    soldier.x += facing(squad.side) * EXIT_JUMP
    soldier.goto(battle, "rifle_run", True)
    soldier.trench_way_point_reached = False
    soldier.trench_way_point_set = False
    soldier.trench_way_point = None
    soldier.in_trench_position = False
    flags["enteringTrench"] = False
    flags["firing"] = False
    flags["inTrench"] = False
    squad.trench = None
    squad.trench_slot = None
    squad.state = "moving"
    squad.in_trench = False
    squad.near_trench = False
    squad.all_in_trench = False
    soldier.exiting_trench = False
    flags["inFiringPosition"] = False
    flags["moveAnim"] = False


def state_exit(battle: "Battle", squad: Squad) -> None:
    """Leaving a trench (F5:1898-1949). A CPU squad empties its slot every step it is leaving; a player's squad
    freed its slot when it was sent over the top"""
    squad.target = None
    if not battle.sides[squad.side].human and squad.trench is not None and squad.trench_slot is not None:
        squad.trench.slots[squad.trench_slot] = None
    for soldier in battle.newest_first(squad.members):
        if not soldier.exiting_trench:
            soldier.exiting_trench = True
            soldier.goto(battle, "exitTrench", True)
        if soldier.flags["exitedTrench"]:
            leave_trench(battle, squad, soldier)


def state_stopped(battle: "Battle", squad: Squad) -> None:
    """F5:1725-1730: every member stops on frame 1"""
    for soldier in battle.newest_first(squad.members):
        if isinstance(soldier, Soldier):
            soldier.goto(battle, 1, False)


def state_victory(battle: "Battle", squad: Squad) -> None:
    """The winners cheer after a short wait, in the pose they are in (F5:2116-2128). A pose with no cheer of its own
    (prone, crouched) keeps still. Tanks don't cheer: the check reads a flag only soldiers have"""
    for soldier in battle.newest_first(squad.members):
        if isinstance(soldier, Soldier) and not soldier.end_battle_anim:
            soldier.end_battle_anim = True
            movement_later(battle, POSE_WAIT, "victory", soldier)


def state_defeated(battle: "Battle", squad: Squad) -> None:
    """The losers surrender after a short wait, in the trench or standing (F5:2129-2156)"""
    for soldier in battle.newest_first(squad.members):
        if isinstance(soldier, Soldier) and not soldier.end_battle_anim:
            soldier.end_battle_anim = True
            move = "defeatTrench" if soldier.flags["inTrench"] else "defeatGround"
            movement_later(battle, DEFEAT_WAIT, move, soldier)


STATE_HANDLERS = {
    "moving": state_moving,
    "engaging": state_engaging,
    "assaultTrench": state_assault,
    "stopped": state_stopped,
    "entrench": state_entrench,
    "exitTrench": state_exit,
    "gasMasksOn": state_masks_on,
    "gasMasksOff": state_masks_off,
    "tankMoving": tank_act,
    "tankDead": tank_act,
    "tankEngaging": tank_act,
    "victory": state_victory,
    "defeated": state_defeated,
}
