"""Squads and what they are made of: soldiers, tanks, the bunker and the covers they sit behind.

A squad is one deployment into one lane: its members spawn one at a time (createSquad F6:1486-1633, createSoldier
F6:1634-1776) and share one health pool. The battle engine walks squads and moves their members; the frame scripts of
each member's timeline (common/timeline.py) say when an animation has finished.

Each squad is in one of STATES; `act` runs one squad's step in its state, as the original's squadAI switch does, and
`soldier_movements` starts the poses, get-ups, runs, cheers and surrenders.
"""

import math
import typing as t

from . import anims
from .combat import firing_check
from .data import (
    BUNKER,
    CONQUER_AREA,
    COVER_TYPES,
    LANE_HEIGHT,
    LANES,
    MORALE_COST,
    MOVE_MODIFIER,
    SOLDIERS,
    UNITS,
    WIRE_SPEED,
)
from .morale import flank
from .tanks import CONQUER_LANE, FLANK_LANES, bunker_act, tank_act
from .teams import throw_grenade
from .timeline import Timeline

if t.TYPE_CHECKING:
    from .battle import Battle

SPAWN_GAP_MS = 300  # one member every 300 ms, F6:1613
JUMPS_KEPT = 3  # one update's steps (common/lobby.py STEPS): the jumps a soldier's row carries
SPAWN_SPREAD = 50  # spawnPoint - random(50) / + random(50), F6:1749-1754
SIZE = (10, 125)  # random(10) + 125 percent, F6:1655
BAND = LANE_HEIGHT / 2.25  # a soldier spawns at lane + random(70) - 31.1 and drifts in lane - 21.1 to lane + 31.1
BAND_TOP = 10  # minY = lane - 31.1 + 10, F6:1733-1735
TANK_DROP = 35  # a tank sits at lane + 35, F6:1738
BUNKER_RISE = 100  # the bunker sits at lane - 100, F6:1742
COVER_RISE = LANE_HEIGHT / 2 - 10  # a cover sits at lane - 25, F6:7285


class Cover:
    def __init__(self, index: int, lane: int, x: float, kind: str):
        """One wall, fence, sandbag or log pile in a lane (buildMap F6:7280-7311), in the mission's order"""
        self.index = index
        self.lane = lane
        self.x = x
        self.y = LANES[lane - 1] - COVER_RISE
        self.kind = kind
        self.defence: float = COVER_TYPES[kind]["defence"]
        # The one squad sitting behind it ("slot1", "empty" in the original)
        self.holder: Squad | None = None
        # Which side holds it: "british", "german" or None (ownerTeam)
        self.owner: str | None = None


def unit_stats(side: str, kind: str) -> dict:
    """The squad's own numbers: a unit of data.UNITS, or the bunker (german.bunker, F6:10703-10728)"""
    if kind == "bunker":
        return {
            "members": ("bunkerBase",),
            "hp": BUNKER["hp"],
            "pool": BUNKER["hp"],
            "speed": BUNKER["speed"],
            "range": BUNKER["range"],
            "slot": 9,
        }
    return UNITS[side][kind]


class Squad:
    def __init__(self, battle: "Battle", squad_id: int, side: str, kind: str, lane: int, objective: bool):
        unit = unit_stats(side, kind)
        owner = battle.sides[side]
        self.id = squad_id
        self.side = side
        self.kind = kind
        self.lane = lane
        self.slot: int = unit["slot"]
        self.member_types: tuple[str, ...] = unit["members"]
        self.members: list[Soldier | Tank] = []
        self.hp: float = unit["hp"]
        self.pool: float = unit["pool"]
        self.speed: float = unit["speed"]
        # German Heavy and either side's Engine Upgrade work on the owner's own tanks only (F6:1513-1524, B25)
        if kind == "tank" and owner.has("tank_health"):
            self.pool *= owner.effect("tank_health")
        if kind == "tank" and owner.has("tank_speed"):
            self.speed *= owner.effect("tank_speed")
        # Pool the members spawned so far add up to (totalHealth)
        self.total = 0.0
        self.range: float = unit["range"]
        # Tanks and the bunker start in their own states (B42)
        self.state = {"tank": "tankMoving", "bunker": "bunkerIdle"}.get(kind, "moving")
        self.last_state = "moving"
        self.objective = objective or kind == "bunker"
        self.target: Squad | None = None
        self.target_dist: float = 999999
        self.hit = False
        # The cover the squad is sitting in or passing through (trenchRef), whether the find tick last saw a cover near
        # it (nearTrench), whether it claimed that cover's slot (the squad's inTrench), and whether every member is in
        self.cover: Cover | None = None
        self.near_cover = False
        self.in_cover = False
        self.all_in_cover = False
        self.passing = False
        self.in_wire = False
        self.near_officer = False
        self.officer: Squad | None = None
        self.smoked = False
        # Suppressing Fire shots left, and smoke rounds a mortar team has left to fire at its ordered point
        # (specialRoundCount, specialTargetX/Y, F6:6478-6481)
        self.suppress = 0
        self.smoke_rounds = 0
        self.smoke_target: tuple[float, float] = (0.0, 0.0)
        # A mortar team firing smoke rounds searches for no target (firingSmoke, F6:1548, 3455)
        self.firing_smoke = False

    @property
    def leader(self) -> "Soldier | Tank | None":
        for member in self.members:
            if member.alive:
                return member
        return None

    @property
    def size(self) -> int:
        return len(self.member_types)


def spawn_point(battle: "Battle", side: str) -> float:
    """createSoldier's x (F6:1749-1754): American spawnPoint -100 less random(50), German width + 100 plus random(50)
    (spawnPoint, F6:7372-7373). The draw is made even when the squad has a fixed x."""
    spread = battle.random(SPAWN_SPREAD)
    return battle.spawn_x(side) - spread if side == "british" else battle.spawn_x(side) + spread


class Soldier:
    def __init__(self, battle: "Battle", squad: Squad, soldier_type: str, x: float | None):
        self.id = battle.new_id()
        self.squad = squad
        self.type = soldier_type
        stats = SOLDIERS[squad.side][soldier_type]
        self.damage: float = stats["damage"]
        self.weapon: str = stats["weapon"]
        self.alive = True
        # Suppressed from the hit until its recovery ends (common/combat.py `suppress`), and the pose it goes back to
        self.suppressed = False
        self.suppressed_pose: str | None = None
        lane_y = LANES[squad.lane - 1]
        # Draws in createSoldier's order: size F6:1655, drift timer F6:1712, y F6:1735, x F6:1749-1754, run frame
        # F6:1767
        self.scale = (battle.random(SIZE[0]) + SIZE[1]) / 100
        self.direction_count_max = 100
        self.direction_count = self.direction_count_max - battle.random(self.direction_count_max)
        self.min_y = lane_y - BAND + BAND_TOP
        self.max_y = lane_y + BAND
        self.y: float = lane_y + battle.random(LANE_HEIGHT) - BAND
        self.ground = self.y
        spawn_x = spawn_point(battle, squad.side)
        self.x: float = spawn_x if x is None else x
        # Pool level at or below which this member dies: (k + 1) x HP for the k-th member (health, F6:1666-1667)
        squad.total += squad.hp
        self.threshold = squad.total
        # The frame scripts' variables plus the ones the engine sets beside them (F6:1672-1730)
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
            "inTrench": False,
            "enteringTrench": False,
            "exitedTrench": False,
        }
        self.timeline = Timeline(anims.SOLDIER, self.flags)
        # Per-soldier counters the squad states use (F6:1686-1730)
        self.moving_up = False
        self.moving_down = False
        self.burst_counter = 1
        self.wait_counter = 0
        self.mg_burst_counter = 0
        self.mg_wait_counter = 0
        self.end_battle_anim = False
        # What the next throw releases (grenType) and a smoke grenade's aimed point (grenTargetX/Y, F6:8507-8513)
        self.gren_type = "handGrenade"
        self.gren_target: tuple[float, float] | None = None
        # The cheer or surrender waiting for the soldier to stand up (B44)
        self.end_label: str | None = None
        self.way_point: float | None = None
        self.way_point_set = False
        self.way_point_reached = False
        # The spot behind the cover the soldier runs to (trenchWayPoint), and its leaving: the leave animation
        # started, and the one jump out made (B39)
        self.cover_spot: float | None = None
        self.cover_spot_set = False
        self.cover_spot_reached = False
        self.in_cover_position = False
        self.exiting_cover = False
        self.out_of_cover = False
        # Where the engine jumped the timeline, newest last: (frame, playing, step), for the page. The last jump of
        # each of the newest JUMPS_KEPT steps, so an update holds every jump since the one before it
        self.jumps: list[tuple[int, bool, int]] = [(1, True, battle.step)]
        # A soldier joins its run cycle at a random frame (F6:1767)
        self.goto(battle, 20 + battle.random(15), True)

    def goto(self, battle: "Battle", target: str | int, play: bool) -> None:
        """gotoAndPlay / gotoAndStop on the soldier's timeline, recorded so the page can play it from the same step.
        Flash ignores a jump to a label the clip doesn't have, and so does this"""
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
    def __init__(self, battle: "Battle", squad: Squad, x: float | None):
        """A tank (sprite 913) or the bunker (sprite 929). Neither is scaled, and the bunker's main gun never fires
        (mainGunDisabled, F6:1648)"""
        self.id = battle.new_id()
        self.squad = squad
        self.kind = squad.kind
        self.type = squad.member_types[0]
        self.damage: float = SOLDIERS[squad.side][self.type]["damage"]
        self.alive = True
        self.scale = 1.0
        lane_y = LANES[squad.lane - 1]
        # Draws in createSoldier's order: the drift timer and a soldier's y, which the tank's own y replaces, then x
        # (F6:1712, 1735-1742, 1749-1754). The number painted on the tank is drawn on the page.
        self.direction_count_max = 100
        self.direction_count = self.direction_count_max - battle.random(self.direction_count_max)
        battle.random(LANE_HEIGHT)
        self.y: float = lane_y + TANK_DROP if self.kind == "tank" else lane_y - BUNKER_RISE
        self.ground = self.y
        spawn_x = spawn_point(battle, squad.side)
        self.x: float = spawn_x if x is None else x
        squad.total += squad.hp
        self.threshold = squad.total
        self.health: float = squad.pool
        # The guns' frame scripts write `firing` and `firingSecondary` into the tank (their `_parent`); the turret
        # keeps its own flags
        self.flags: dict = {"firing": False, "firingSecondary": False}
        if self.kind == "tank":
            self.gun: Timeline | None = Timeline(anims.TANK_GUN, self.flags)
            self.mg = Timeline(anims.TANK_MG, self.flags)
            self.turret = Timeline(anims.TURRETS[squad.side], {})
        else:
            self.gun = None
            self.mg = Timeline(anims.BUNKER_MG, self.flags)
            self.turret = Timeline(anims.TURRETS["bunker"], {})
        self.broken: set[str] = set()
        self.gun_stamp = battle.step
        self.mg_stamp = battle.step
        # The main gun's counters start where every member's do (F6:1715-1718): one shot already counted
        self.burst_counter = 1
        self.wait_counter = 0
        self.mg_burst_counter = 0
        self.mg_wait_counter = 0
        self.end_battle_anim = False
        # The step the turret's last turn started on, for the page's turret timeline
        self.turret_stamp = battle.step
        # Machine gun rounds left before the bunker reloads (roundCount, F6:1650)
        self.round_count: int = BUNKER["rounds"]

    def timelines(self) -> list[Timeline]:
        return [timeline for timeline in (self.gun, self.mg, self.turret) if timeline is not None]


def spawn_member(battle: "Battle", squad: Squad, soldier_type: str, x: float | None) -> None:
    """createSoldier for one member, which joins the squad it was deployed with (B55)"""
    if squad.kind in ("tank", "bunker"):
        member = Tank(battle, squad, x)
    else:
        member = Soldier(battle, squad, soldier_type, x)
    squad.members.append(member)


def make_squad(
    battle: "Battle", side: str, kind: str, lane: int, x: float | None = None, objective: bool = False
) -> Squad:
    """createSquad (F6:1486-1633) in lane 1 to 3: counts the deployment, gives the officer's or tank's morale (W14),
    and spawns the members one every 300 ms on the battle clock, the first at once. `x` puts every member at one x
    instead of the side's spawn point (a pre-placed squad's fixedLoc)."""
    squad = Squad(battle, battle.new_id(), side, kind, lane, objective)
    owner = battle.sides[side]
    owner.deployed += 1
    owner.deployed_kinds[kind] = owner.deployed_kinds.get(kind, 0) + 1
    if kind == "tank":
        owner.add_morale(MORALE_COST["tank_bonus"])
    if kind == "officer":
        owner.officers.append(squad)
        owner.add_morale(MORALE_COST["officer_bonus"])
    # for..in walks the member list newest first, but each timer's delay is its index, so they spawn in list order
    for index, soldier_type in enumerate(squad.member_types):
        battle.after(
            SPAWN_GAP_MS * index, lambda soldier_type=soldier_type: spawn_member(battle, squad, soldier_type, x)
        )
    owner.squads.append(squad)
    return squad


# The squad states the original runs, in the order squadAI's switch lists them (F6:2035-3379). Its "static", "halt"
# and "stopped" cases can't be reached and its gas mask states have no case, so they are left out.
STATES = (
    "moving",
    "engaging",
    "assaultTrench",
    "entrench",
    "exitTrench",
    "bunkerIdle",
    "bunkerEngaging",
    "tankMoving",
    "tankDead",
    "tankEngaging",
    "victory",
    "defeated",
)

DRIFT_SPEED = 6  # a drifting soldier moves speed / 6 up or down inside its lane band, F6:2117-2124
STOP_SPREAD = 50  # Engaging's stop point: up to 49 pixels ahead, F6:2373, 2397
OFF_FIELD = -50  # an American soldier still behind x -50 stops 100 to 149 pixels in, F6:2365, 2385
STOP_FROM_EDGE = 100  # and a German one still past the right edge 100 to 149 pixels in, F6:2385, 2409
ASSAULT_GAP = 150  # an assault squad stops 150 to 209 pixels short of the target's cover, F6:2620-2627
ASSAULT_SPREAD = 60
COVER_HALF = 42.37 / 2  # half the cover holder's width, the same for every cover type: holder._width / 2, F6:2772
COVER_SPOT = (
    10,
    2,
    5,
)  # a soldier's spot is random(10) + 2 behind the holder's near edge, then 5 back in, F6:2772-2777
EXIT_JUMP = 45  # a soldier out of cover jumps 45 pixels forward, F6:3014-3021
RUN_FRAMES = (10, 20)  # and runs on from frame random(10) + 20 of its run cycle, F6:3022
POSE_WAIT = (400, 100)  # random(400) + 100 ms before a pose or a cheer, F6:2485-2493, 2668-2672, 3351
DEFEAT_WAIT = (200, 100)  # random(200) + 100 ms before surrendering, F6:3367, 3377
BURST_START = 5  # a soldier taking its pose starts its burst count at random(5), F6:2499, 2675
POSES = {1: "stand", 2: "crouch", 3: "prone"}
ASSAULT_POSES = {1: "crouch", 2: "stand"}
# The pose a soldier type always takes in cover, after the random(2) + 1 every soldier draws (F6:2843-2855)
COVER_POSE = {"lieutenant": 1, "mortarCarrier": 2, "mortarLoader": 2, "bazookaMan": 2, "machineGunner": 2}
# The pose a soldier type always takes in Engaging, after the random(3) + 1 every soldier draws (F6:2474-2483)
FIXED_POSE = {"lieutenant": 1, "mortarCarrier": 2, "mortarLoader": 2, "bazookaMan": 2}
CPU_GRENADE_AT_TANK = 2  # a CPU assault soldier facing a tank throws 1 time in 2, F6:2505-2512
# The get-up a soldier plays before it cheers or surrenders, by the pose it is in (B44: the original has only standing
# cheers and surrenders, so it froze anyone kneeling or lying down)
GET_UP = {"crouch": "crouchToStand", "prone": "proneToStand"}


def num(value: float | None) -> float:
    """A way point as ActionScript compares it: null is NaN in a SWF 7 or later, so every comparison with it fails"""
    return math.nan if value is None else value


def facing(side: str) -> int:
    """+1 for the Americans, who advance to the right; -1 for the Germans"""
    return 1 if side == "british" else -1


def step_speed(squad: Squad) -> float:
    """A walking or running soldier's pace: speed / 1.5 in wire (wireSpeedMod), else speed x 0.75 (moveModifier)"""
    return squad.speed / WIRE_SPEED if squad.in_wire else squad.speed * MOVE_MODIFIER


def moving_speed(battle: "Battle", squad: Squad) -> float:
    """A Moving squad's pace (F6:2103-2116, 2141-2148): the American side's GO! GO! GO! makes it x1.2 out of wire"""
    owner = battle.sides[squad.side]
    if not squad.in_wire and squad.side == "british" and owner.has("move_speed"):
        return step_speed(squad) * owner.effect("move_speed")
    return step_speed(squad)


def target_alive(squad: Squad) -> bool | None:
    """The original's `enemyTarget.members[0].alive`: None when there is no target or it has no members left (a
    dead soldier leaves the list, a dead tank stays in it with alive false)"""
    if squad.target is None or not squad.target.members:
        return None
    return squad.target.members[0].alive


def stop_frame(label: str, action: str = "stop") -> int:
    """The frame a soldier animation from `label` stops on, or with `action` "goto" the frame it first jumps from"""
    frame = anims.SOLDIER["labels"][label]
    while not any(step[0] == action for step in anims.SOLDIER["actions"].get(frame, ())):
        frame += 1
    return frame


# The suppression's frames: the crouching suppression (S666 frames 162 to 218, whose last jumps to the recovery) and
# its recovery (497 to 501, which stops crouched)
RECOVERED = stop_frame("recoverSuppressed_crouch")
SUPPRESSION_FRAMES = set(
    range(anims.SOLDIER["labels"]["suppressed_crouch"], stop_frame("suppressed_crouch", "goto") + 1)
) | set(range(anims.SOLDIER["labels"]["recoverSuppressed_crouch"], RECOVERED + 1))
# The frame each other pose rests on, where its position and inFiringPosition are set (S666 frames 128 and 1103)
POSE_REST = {"standing": stop_frame("rifle_stop_standing"), "prone": stop_frame("rifle_stop_prone")}


def recover(battle: "Battle", soldier: Soldier) -> None:
    """A suppressed soldier's recovery, after its timeline's frame this step (B34, W9). Once the recovery stops
    crouched, 60 steps after the hit, a standing or prone soldier is back in its own pose and the soldier may fire
    again. A soldier the engine moved off the suppression's frames (leaving cover, the battle's end) is no longer
    suppressed."""
    frame = soldier.timeline.frame
    if frame == RECOVERED and not soldier.timeline.playing:
        rest = POSE_REST.get(soldier.suppressed_pose)
        if rest is not None:
            soldier.goto(battle, rest, False)
    elif frame in SUPPRESSION_FRAMES:
        return
    soldier.suppressed = False
    soldier.suppressed_pose = None


def set_state(squad: Squad, state: str) -> None:
    if state not in STATES:
        raise ValueError(f"Unknown squad state {state!r}")
    squad.state = state


def stop_firing(squad: Squad) -> None:
    """A squad that lost its target: no member fires or waits to start firing any more (F6:3530-3534, 3574-3578). A
    tank's or the bunker's `firing` is its main gun's reload, which runs its full 96 steps (as for B41)"""
    for member in squad.members:
        if isinstance(member, Soldier):
            member.flags["firing"] = False


def soldier_movements(battle: "Battle", move: str, soldier: "Soldier | None", entrenching: bool = False) -> None:
    """soldierMovements (F6:3383-3442): start a pose, a get-up, a run, a cheer or a surrender. `entrenching` marks the
    soldier as in its cover first. A dead soldier, or no soldier at all, does nothing. Every soldier's weapon type is
    "rifle" (createSoldier F6:1679)."""
    if not isinstance(soldier, Soldier):
        return
    if entrenching:
        soldier.flags["inTrench"] = True
    if not soldier.alive:
        return
    labels = {
        "exitTrench": "exitTrench",
        "crouch": "rifle_stop_crouch",
        "stand": "rifle_stop_standing",
        "prone": "rifle_stop_prone",
        "proneToStand": "rifle_start_prone",
        "crouchToStand": "rifle_start_crouch",
        "standingToStand": "rifle_start_standing",
    }
    if move == "victory":
        end_pose(battle, soldier, "victory_standing")
    elif move in ("defeatTrench", "defeatGround"):
        end_pose(battle, soldier, "defeat_standing")
    elif move == "run":
        if not soldier.flags["changingToMove"]:
            soldier.goto(battle, "rifle_run", True)
    elif move in labels:
        if move != "exitTrench":
            soldier.flags["moveAnim"] = False
        soldier.goto(battle, labels[move], True)


def end_pose(battle: "Battle", soldier: Soldier, label: str) -> None:
    """The cheer or the surrender. A standing soldier plays it at once; anyone kneeling or lying down gets up first
    and plays it once up (B44, `finish_end_pose`)"""
    get_up = GET_UP.get(soldier.flags["position"])
    if get_up is None:
        soldier.end_label = None
        soldier.goto(battle, label, True)
        return
    soldier.end_label = label
    soldier_movements(battle, get_up, soldier)


def finish_end_pose(battle: "Battle", soldier: Soldier) -> None:
    """A soldier that got up for its cheer or surrender plays it once the get-up's last frame has stood it up"""
    flags = soldier.flags
    if soldier.end_label is None or not soldier.alive:
        return
    if flags["position"] == "standing" and not flags["changingToMove"]:
        label, soldier.end_label = soldier.end_label, None
        soldier.goto(battle, label, True)


def movement_later(
    battle: "Battle", wait: tuple[int, int], move: str, soldier: Soldier, entrenching: bool = False
) -> None:
    """setTimeout(soldierMovements, random(a) + b, move, soldier, entrenching): the move is named now, played when the
    timer runs"""
    battle.after(battle.random(wait[0]) + wait[1], lambda: soldier_movements(battle, move, soldier, entrenching))


def run_loop(battle: "Battle", soldier: Soldier) -> None:
    """S666/frame_34, the end of one run cycle: run on, or stop on this frame when the soldier is stopping to fire or
    getting into cover. Once the battle is over the frame does nothing, so the playhead runs on into the frames after
    it until the cheer or the surrender starts."""
    if battle.state != "playing":
        return
    flags = soldier.flags
    if soldier.alive and not flags["changingToFire"] and not flags["enteringTrench"]:
        # gotoAndStop("rifle_run") then play()
        soldier.goto(battle, "rifle_run", False)
        soldier.timeline.play()
        soldier.jumped(battle, True)
    else:
        soldier.stop(battle)
        flags["moveAnim"] = False


def act(battle: "Battle", squad: Squad) -> None:
    """One squad's turn in its state (squadAI's switch, F6:2035-3379). Each state walks the members with for..in,
    newest first. The tank and bunker states are common/tanks.py's."""
    handler = STATE_HANDLERS.get(squad.state)
    if handler is not None:
        handler(battle, squad)


def reset_for_moving(soldier: Soldier) -> None:
    """Moving clears every stop point and firing flag, every step (F6:2056-2065)"""
    flags = soldier.flags
    flags["firing"] = False
    flags["inFiringPosition"] = False
    flags["inTrench"] = False
    flags["changingToFire"] = False
    soldier.way_point = None
    soldier.cover_spot = None
    soldier.way_point_set = False
    soldier.way_point_reached = False
    soldier.cover_spot_set = False
    soldier.cover_spot_reached = False


def drift_roll(battle: "Battle", soldier: Soldier) -> None:
    """The drift timer: when it runs out, 1 in 10 drift up, 1 in 10 down, else straight on (F6:2066-2083)"""
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


def lane_end(battle: "Battle", squad: Squad, soldier: Soldier, index: int) -> bool:
    """The far end of the lane (F6:2125-2136, 2157-2168), checked by the squad's leader only (B45). A leader past the
    edge in lane 1 or 3 flanks and its squad leaves the field; one past the conquer line in lane 2 wins the battle.
    True when the squad left the field"""
    if index != 0:
        return False
    if squad.side == "british":
        near, past = soldier.x > battle.width - CONQUER_AREA, soldier.x > battle.width
    else:
        near, past = soldier.x < CONQUER_AREA, soldier.x < 0
    if not near:
        return False
    if past and squad.lane in FLANK_LANES:
        flank(battle, squad)
        return True
    if squad.lane == CONQUER_LANE:
        battle.conquer(squad.side)
    return False


def advance(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A running soldier's step forward and its drift inside its lane band (F6:2103-2124, 2141-2156)"""
    soldier.x += facing(squad.side) * moving_speed(battle, squad)
    if soldier.moving_up and soldier.y > soldier.min_y:
        soldier.y -= squad.speed / DRIFT_SPEED
    if soldier.moving_down and soldier.y < soldier.max_y:
        soldier.y += squad.speed / DRIFT_SPEED


def get_up_now(battle: "Battle", soldier: Soldier) -> None:
    """A soldier still in a pose gets up at once: "standingToStand", "crouchToStand", "proneToStand" (F6:2088-2093)"""
    flags = soldier.flags
    flags["changingToMove"] = True
    flags["inFiringPosition"] = False
    flags["changingToFire"] = False
    flags["moveAnim"] = False
    soldier_movements(battle, flags["position"] + "ToStand", soldier)


def start_run(battle: "Battle", soldier: Soldier) -> None:
    """gotoAndPlay("rifle_run") for a soldier not yet running (F6:2097-2102, 2367-2373)"""
    flags = soldier.flags
    flags["moveAnim"] = True
    flags["changingToFire"] = False
    flags["changingToMove"] = False
    soldier.goto(battle, "rifle_run", True)


def state_moving(battle: "Battle", squad: Squad) -> None:
    """Moving (F6:2051-2174): run on down the lane, getting up first from any pose"""
    for index, soldier in battle.newest_first(list(enumerate(squad.members))):
        reset_for_moving(soldier)
        drift_roll(battle, soldier)
        if not soldier.alive or battle.state != "playing":
            continue
        flags = soldier.flags
        if not flags["changingToMove"] and not flags["inMovingPosition"]:
            get_up_now(battle, soldier)
        if not flags["changingToMove"] and flags["inMovingPosition"]:
            if not flags["moveAnim"]:
                start_run(battle, soldier)
            advance(battle, squad, soldier)
            if lane_end(battle, squad, soldier, index):
                return


def pick_stop(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """Engaging's stop point (F6:2359-2423): a little way ahead, a way onto the field for a soldier still off it, or
    one pixel on beside cover. A soldier not yet running starts its run; the German side leaves its changing flags
    as they are"""
    flags = soldier.flags
    ahead = facing(squad.side)
    if squad.near_cover:
        soldier.way_point = soldier.x + ahead
        soldier.way_point_set = True
        return
    if not flags["moveAnim"]:
        if squad.side == "british":
            start_run(battle, soldier)
        else:
            flags["moveAnim"] = True
            soldier.goto(battle, "rifle_run", True)
    spread = battle.random(STOP_SPREAD)
    if squad.side == "british":
        soldier.way_point = soldier.x + spread if soldier.x > OFF_FIELD else STOP_FROM_EDGE + spread
    elif soldier.x < battle.width:
        soldier.way_point = soldier.x - spread
    else:
        soldier.way_point = battle.width - STOP_FROM_EDGE - spread
    soldier.way_point_set = True


def take_pose(battle: "Battle", soldier: Soldier) -> None:
    """Stop at the way point and go idle; the pose follows after a short wait (F6:2466-2472, 2660-2664)"""
    flags = soldier.flags
    flags["moveAnim"] = False
    flags["changingToMove"] = False
    flags["changingToFire"] = True
    flags["inMovingPosition"] = False
    soldier.goto(battle, "stop_idle", False)


def ready_to_pose(soldier: Soldier) -> bool:
    flags = soldier.flags
    return soldier.way_point_reached and not flags["inFiringPosition"] and not flags["changingToFire"] and soldier.alive


def back_to_moving(squad: Squad) -> None:
    """The target is gone: every member drops its firing and changing flags and the squad runs on (F6:2346-2358,
    2678-2690)"""
    for member in squad.members:
        flags = member.flags
        flags["firing"] = False
        flags["changingToFire"] = False
        flags["changingToMove"] = False
        flags["moveAnim"] = False
    squad.state = "moving"


def walk_to_stop(squad: Squad, soldier: Soldier) -> None:
    """Engaging's walk to the stop point, and arriving there (F6:2425-2463). A German soldier that arrives stops its
    run as it does"""
    ahead = facing(squad.side)
    if ahead * soldier.x < ahead * num(soldier.way_point):
        soldier.x += ahead * step_speed(squad)
    if ahead * soldier.x >= ahead * num(soldier.way_point):
        soldier.way_point_reached = True
        if squad.side == "german":
            soldier.flags["moveAnim"] = False


def engaging_pose(battle: "Battle", soldier: Soldier) -> None:
    """Go idle, roll the pose (1 stand, 2 crouch, 3 prone; the officer stands, mortar and bazooka men kneel, the
    machine gunner kneels or lies down), take it after a short wait, and start the burst count (F6:2464-2500)"""
    take_pose(battle, soldier)
    pick = battle.random(3) + 1
    pick = FIXED_POSE.get(soldier.type, pick)
    if soldier.type == "machineGunner":
        pick = battle.random(2) + 2
    movement_later(battle, POSE_WAIT, POSES[pick], soldier)
    soldier.burst_counter = battle.random(BURST_START)


def engaging_fire(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A soldier in its pose, not mid-shot and not suppressed, fires by its fire type (F6:2497-2604). A CPU assault
    soldier facing a tank first throws a grenade 1 time in 2, and fires nothing on the step its throw starts (B36)."""
    flags = soldier.flags
    if not flags["inFiringPosition"] or flags["firing"] or not soldier.alive or soldier.suppressed:
        return
    flags["moveAnim"] = False
    flags["inMovingPosition"] = False
    target = squad.target
    cpu = not battle.sides[squad.side].human
    if (
        cpu
        and not flags["throwingGrenade"]
        and squad.kind == "assault"
        and target is not None
        and target.kind == "tank"
    ):
        if battle.random(CPU_GRENADE_AT_TANK) == 0:
            throw_grenade(battle, soldier, target)
            return
    firing_check(battle, soldier, False)


def state_engaging(battle: "Battle", squad: Squad) -> None:
    """Engaging (F6:2335-2607): run to a stop point, take a pose, fire from it. A squad not in cover whose target's
    leader is dead runs on (the check is made for every member)"""
    for soldier in battle.newest_first(squad.members):
        if battle.state == "playing" and target_alive(squad) is not True and not squad.in_cover:
            back_to_moving(squad)
        if not soldier.alive:
            continue
        if not soldier.way_point_set:
            pick_stop(battle, squad, soldier)
        walk_to_stop(squad, soldier)
        if ready_to_pose(soldier):
            engaging_pose(battle, soldier)
        engaging_fire(battle, squad, soldier)


def assault_point(battle: "Battle", squad: Squad) -> float:
    """150 to 209 pixels short of the target's cover (F6:2615-2627). With no cover the point is NaN, so the soldier
    neither moves nor arrives, as the original's undefined arithmetic does"""
    spread = battle.random(ASSAULT_SPREAD)
    cover = squad.target.cover if squad.target is not None else None
    if cover is None:
        return math.nan
    return cover.x - facing(squad.side) * (ASSAULT_GAP + spread)


def assault_fire(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A soldier in its pose, not mid-shot and not suppressed (B35), fires by its fire type while the target has
    members; never a grenade here (F6:2692-2750). Assault squads hold only slowBurst and medBurst soldiers, the two
    fire types this state's code handles"""
    flags = soldier.flags
    if squad.target is None or not squad.target.members:
        return
    if not flags["inFiringPosition"] or flags["firing"] or not soldier.alive:
        return
    flags["inMovingPosition"] = False
    if not flags["throwingGrenade"]:
        firing_check(battle, soldier, False)


def state_assault(battle: "Battle", squad: Squad) -> None:
    """Assaulting cover (F6:2608-2754): stand off from the target's cover, kneel or stand 1 in 2, then fire.
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
            soldier.burst_counter = battle.random(BURST_START)
        if battle.state == "playing" and target_alive(squad) is None and not squad.in_cover:
            back_to_moving(squad)
        assault_fire(battle, squad, soldier)


def leave_cover(battle: "Battle", squad: Squad) -> None:
    """Send a squad out of its cover: the player's Advance, the CPU's rolls and the sniper scare all set Leaving cover
    (enemyUnitAI F6:3873-3912, F6:4472-4478). Leaving cover's own steps do the rest"""
    set_state(squad, "exitTrench")


def fully_in_cover(squad: Squad) -> bool:
    """Every member is in the squad's cover and it is not passing through: Advance may be given (F6:6582)"""
    return squad.all_in_cover and not squad.passing


def cover_spot(battle: "Battle", squad: Squad) -> float:
    """A soldier's spot behind its squad's cover (F6:2768-2779): American cover x - 21.2 - (2 to 11) + 5, which is
    x - 27.2 to x - 18.2, German mirrored. The draw is made even with no cover, whose spot is NaN"""
    spread, inset, back = COVER_SPOT
    offset = battle.random(spread) + inset
    if squad.cover is None:
        return math.nan
    return squad.cover.x - facing(squad.side) * (COVER_HALF + offset - back)


def run_to_cover(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """Run to the cover spot, and arrive there (F6:2780-2828). A soldier already past its spot arrives where it is.
    Arriving clears the spot, so the soldier neither moves nor arrives again until it is given a new one"""
    flags = soldier.flags
    ahead = facing(squad.side)
    spot = num(soldier.cover_spot)
    if soldier.cover_spot_set and ahead * soldier.x < ahead * spot and not soldier.cover_spot_reached:
        if not flags["moveAnim"] and soldier.alive and not flags["enteringTrench"]:
            flags["changingToMove"] = False
            flags["changingToFire"] = False
            flags["moveAnim"] = True
            soldier.goto(battle, "rifle_run", True)
        soldier.x += ahead * step_speed(squad)
    if ahead * soldier.x >= ahead * spot:
        soldier.cover_spot_reached = True
        soldier.in_cover_position = True
        soldier.cover_spot = None


def cover_pose(battle: "Battle", soldier: Soldier) -> None:
    """At its spot the soldier goes idle, rolls stand or crouch 1 in 2 (the officer stands; mortar, bazooka and machine
    gun men crouch) and takes it after 100 to 499 ms, which puts it in cover. There is no enter-cover animation. Its
    own burst count starts at random(5) (F6:2834-2864, B38)"""
    flags = soldier.flags
    flags["enteringTrench"] = True
    flags["changingToFire"] = True
    flags["inMovingPosition"] = False
    flags["moveAnim"] = False
    soldier.goto(battle, "stop_idle", False)
    pick = battle.random(2) + 1
    pick = COVER_POSE.get(soldier.type, pick)
    movement_later(battle, POSE_WAIT, POSES[pick], soldier, True)
    soldier.burst_counter = battle.random(BURST_START)


def cover_check(squad: Squad) -> None:
    """Whether every member is in; a squad passing through goes on once they are (F6:2869-2894)"""
    squad.all_in_cover = all(member.flags["inTrench"] for member in squad.members)
    if squad.passing and squad.all_in_cover:
        set_state(squad, "exitTrench")
        squad.passing = False


def cover_fire(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A soldier in its pose, not mid-shot and not suppressed (B35), fires by its fire type while the target has
    members (F6:2895-2990). It fires as soon as it is in pose: nothing delays a soldier's first shot from cover"""
    flags = soldier.flags
    if squad.target is None or not squad.target.members:
        return
    if flags["inFiringPosition"] and not flags["firing"] and soldier.alive:
        firing_check(battle, soldier, True)


def state_in_cover(battle: "Battle", squad: Squad) -> None:
    """In cover (state "entrench", F6:2761-2992): run to a spot behind the cover, take a pose, fire from it. The cover
    is this side's while a member of the squad holding it is in (ownerTeam, B47: a squad passing through never makes
    it so). A squad passing through stops passing once the cover's holder has gone"""
    cover = squad.cover
    for soldier in battle.newest_first(squad.members):
        flags = soldier.flags
        if soldier.alive:
            if not soldier.cover_spot_set:
                soldier.cover_spot = cover_spot(battle, squad)
                soldier.cover_spot_set = True
            run_to_cover(battle, squad, soldier)
        if cover is None or cover.holder is None:
            squad.passing = False
        if (
            soldier.cover_spot_reached
            and not flags["inFiringPosition"]
            and not flags["changingToFire"]
            and soldier.alive
        ):
            cover_pose(battle, soldier)
        if flags["inTrench"] and cover is not None and cover.holder is squad:
            cover.owner = squad.side
        cover_check(squad)
        cover_fire(battle, squad, soldier)


def step_out(battle: "Battle", squad: Squad, soldier: Soldier) -> None:
    """A soldier whose leave animation has played jumps 45 pixels forward once (B39) and runs on the spot from a random
    run frame until the whole squad is out (F6:3012-3034)"""
    flags = soldier.flags
    soldier.out_of_cover = True
    soldier.x += facing(squad.side) * EXIT_JUMP
    soldier.goto(battle, battle.random(RUN_FRAMES[0]) + RUN_FRAMES[1], True)
    soldier.cover_spot_reached = False
    soldier.cover_spot_set = False
    soldier.cover_spot = None
    soldier.in_cover_position = False
    flags["enteringTrench"] = False
    flags["firing"] = False
    flags["inTrench"] = False
    flags["inFiringPosition"] = False
    flags["moveAnim"] = False


def all_out(squad: Squad) -> None:
    """The whole squad is out: it frees its cover if it holds it (B46) and runs on (F6:3044-3057)"""
    for member in squad.members:
        member.flags["exitedTrench"] = False
        member.flags["changingToMove"] = False
        member.flags["inMovingPosition"] = True
        member.exiting_cover = False
        member.out_of_cover = False
    if squad.cover is not None and squad.cover.holder is squad:
        squad.cover.holder = None
    squad.cover = None
    squad.in_cover = False
    squad.near_cover = False
    squad.all_in_cover = False
    set_state(squad, "moving")


def state_leaving(battle: "Battle", squad: Squad) -> None:
    """Leaving cover (state "exitTrench", F6:2993-3058): each member plays its 25-step leave animation, then steps
    out. A CPU squad gives up its cover's slot at once, a player's once the whole squad is out; either only if it
    holds it (B46). A member already out never replays the leave animation while it waits for the rest (B39)."""
    squad.target = None
    if not battle.sides[squad.side].human and squad.cover is not None and squad.cover.holder is squad:
        squad.cover.holder = None
    for soldier in battle.newest_first(squad.members):
        soldier.flags["moveAnim"] = False
        if not soldier.exiting_cover:
            soldier.exiting_cover = True
            soldier.goto(battle, "exitTrench", True)
        if soldier.flags["exitedTrench"] and not soldier.out_of_cover:
            step_out(battle, squad, soldier)
    if squad.members and all(member.flags["exitedTrench"] for member in squad.members):
        all_out(squad)


def state_victory(battle: "Battle", squad: Squad) -> None:
    """The winners cheer after a short wait, standing up first (F6:3339-3354, B44). A tank's timer is drawn too and
    does nothing, as the original's has no cheer to play. Its engine sound fades on the page."""
    for member in battle.newest_first(squad.members):
        if not member.end_battle_anim:
            member.end_battle_anim = True
            movement_later(battle, POSE_WAIT, "victory", member)
        if isinstance(member, Soldier):
            finish_end_pose(battle, member)


def state_defeated(battle: "Battle", squad: Squad) -> None:
    """The losers surrender after a short wait, standing up first, in cover or not (F6:3355-3379, B44). A tank's
    `inTrench` is undefined, which neither of the original's checks takes, so a tank draws no timer."""
    for member in battle.newest_first(squad.members):
        if isinstance(member, Soldier) and not member.end_battle_anim:
            member.end_battle_anim = True
            move = "defeatTrench" if member.flags["inTrench"] else "defeatGround"
            movement_later(battle, DEFEAT_WAIT, move, member)
        if isinstance(member, Soldier):
            finish_end_pose(battle, member)


STATE_HANDLERS = {
    "moving": state_moving,
    "engaging": state_engaging,
    "assaultTrench": state_assault,
    "entrench": state_in_cover,
    "exitTrench": state_leaving,
    "bunkerIdle": bunker_act,
    "bunkerEngaging": bunker_act,
    "tankMoving": tank_act,
    "tankDead": tank_act,
    "tankEngaging": tank_act,
    "victory": state_victory,
    "defeated": state_defeated,
}
