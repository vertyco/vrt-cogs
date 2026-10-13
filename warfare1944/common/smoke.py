"""Smoke screens: smoke grenades, smoke rounds, and the smoked check.

A screen comes from a smoke grenade (a squad order, `throwSmokeGrenade` F6:8514-8546, bursting on sprite 1589's
frame 41 or 83) or a smoke round (a mortar team order, `smokeStrike` and `smokeRound` F6:5467-5500, sprite 415's
frame 100). Either way the screen sits in the lane under the aimed point (`smokeRound` / `smokeGrenadeRound`,
F6:5477-5524) and is the gas cloud of the original (`gasExplosion` F6:5085-5110): it lasts its owner's cloud time,
counted on unpaused steps, then fades for 2 seconds and is gone (`clearGas` F6:5582).

A screen does no damage. While one lies in a squad's lane between the squad's leader and its target's leader, the
squad is smoked (`checkSmoke`, F6:1967-1998): its bullets do x0.3 (common/combat.py) and blasts spare it more often.

When this runs (common/battle.py's step order): smoke grenades burst, screens appear and faded screens clear in
step 2, after the strike clips; a smoke round's wait is a battle-clock timer (step 3); the smoked check is the find
tick's first job, American then German (F6:10022-10023).
"""

import typing as t

from .combat import side_index
from .data import CLOUD_STEPS, FPS, LANE_HEIGHT, LANES, ORDER_COSTS, SUPPORTS

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Soldier

FADE_STEPS = 2 * FPS  # a screen fades over 2 seconds (alphaTo(0, 2), F6:5103) and still counts while it does
# The smoke grenade's two throws (sprite 1589): (first frame, frame whose script calls smokeGrenadeRound)
ARCS = ((2, 41), (48, 83))
# The landing spread around the tapped point (throwSmokeGrenade F6:8521-8536): random(40) - 20, random(20) - 10
GRENADE_X = (40, 20)
GRENADE_Y = (20, 10)
# smokeGrenadeRound attaches sprite 1590, whose frame 2 makes the screen: one step after the burst
GRENADE_SCREEN = 1
# Sprite 415 is attached on the round's call and makes the screen on its frame 100
ROUND_SCREEN = SUPPORTS["smoke"]["land"]
THROW_LABEL = "standing_throwGrenade"


class Cloud:
    """One smoke screen on the field, from the step it appears to the step its fade ends"""

    __slots__ = ("id", "x", "y", "lane", "owner", "appear", "fade_start", "end")

    def __init__(self, cloud_id: int, x: float, y: float, lane: int, owner: str, appear: int, fade_start: int):
        self.id = cloud_id
        self.x = x
        self.y = y
        self.lane = lane
        self.owner = owner
        self.appear = appear
        self.fade_start = fade_start
        self.end = fade_start + FADE_STEPS


class Pending:
    """A smoke grenade in the air ("grenade") or a screen clip that hasn't reached its smoke frame ("screen").
    `due` is the step its frame script runs."""

    __slots__ = ("kind", "x", "y", "lane", "owner", "due")

    def __init__(self, kind: str, x: float, y: float, lane: int, owner: str, due: int):
        self.kind = kind
        self.x = x
        self.y = y
        self.lane = lane
        self.owner = owner
        self.due = due


def x10(value: float) -> int:
    return round(value * 10)


def lane_at(y: float) -> int:
    """The lane under an aimed y: lane 1 above y 180, lane 2 to 265, lane 3 below (F6:5480-5495). The original's
    gaps (exactly 180 or 265, and 351 or more) matched no lane; they go to the nearest one (B33)."""
    for lane, centre in enumerate(LANES[:-1], 1):
        if y <= centre + LANE_HEIGHT / 2:
            return lane
    return len(LANES)


def place(battle: "Battle", x: float, y: float) -> tuple[float, float, int]:
    """Where a screen clip sits for a point aimed at (x, y): its lane's centre + random(70) - 35, then x + random(50)
    - 25 (F6:5480-5496, the same in smokeGrenadeRound F6:5504-5520)"""
    support = SUPPORTS["smoke"]
    lane = lane_at(y)
    screen_y = LANES[lane - 1] + battle.random(support["y_range"]) - support["y_offset"]
    screen_x = x + battle.random(support["x_range"]) - support["x_offset"]
    return screen_x, screen_y, lane


def start_cloud(battle: "Battle", x: float, y: float, owner: str, lane: int) -> None:
    """gasExplosion (F6:5085-5110): the screen appears at the clip's spot and joins the list once (B32). Its timer
    counts down once a step from the next step on and the fade starts when it goes below 0, so `life + 1` steps after
    it appears. Its turn is a picture, drawn on the page."""
    battle.round_count += 1
    life = CLOUD_STEPS[owner]
    cloud = Cloud(battle.round_count, x, y, lane, owner, battle.step, battle.step + life + 1)
    battle.smoke.append(cloud)
    battle.event("smoke", cloud.id, x10(x), x10(y), lane, side_index(owner), cloud.fade_start, cloud.end)


def run_clouds(battle: "Battle") -> None:
    """Step 2, oldest first: smoke grenades reaching their burst frame place their screen clip, screen clips reaching
    their smoke frame make the screen, and screens whose fade has ended are cleared. A screen is made even once the
    battle is over, as a picture only: the smoked check is the root frame's, which stops."""
    due = [clip for clip in battle.smoke_clips if clip.due <= battle.step]
    if due:
        battle.smoke_clips = [clip for clip in battle.smoke_clips if clip.due > battle.step]
        for clip in due:
            if clip.kind == "grenade":
                grenade_round(battle, clip.x, clip.y, clip.owner)
            else:
                start_cloud(battle, clip.x, clip.y, clip.owner, clip.lane)
    if any(cloud.end <= battle.step for cloud in battle.smoke):
        battle.smoke = [cloud for cloud in battle.smoke if cloud.end > battle.step]


def grenade_round(battle: "Battle", x: float, y: float, owner: str) -> None:
    """smokeGrenadeRound (F6:5501-5524): the burst attaches the smoke clip (sprite 1590) in the lane under the
    grenade, and its frame 2 makes the screen on the next step"""
    battle.round_count += 1
    screen_x, screen_y, lane = place(battle, x, y)
    battle.smoke_clips.append(Pending("screen", screen_x, screen_y, lane, owner, battle.step + GRENADE_SCREEN))


def smoke_round(battle: "Battle", x: float, y: float, owner: str) -> None:
    """smokeStrike (F6:5467-5476): counts once in the owner's support used, then each of its rounds (one) starts
    after random(800) + 1100n ms on the battle clock, counting up (`while (v < numSmokeRounds)`, F6:5471)"""
    battle.sides[owner].support_used += 1
    support = SUPPORTS["smoke"]
    for number in range(support["rounds"]):
        wait = battle.random(support["wait_ms"]) + number * support["gap_ms"]
        battle.after(wait, lambda: start_round(battle, x, y, owner))


def start_round(battle: "Battle", x: float, y: float, owner: str) -> None:
    """smokeRound (F6:5477-5500): the smoke round clip (sprite 415) is placed in the lane under the aimed point and
    plays from now; its frame 100 makes the screen 99 steps later. The page plays the clip from the "round" event."""
    battle.round_count += 1
    round_id = battle.round_count
    screen_x, screen_y, lane = place(battle, x, y)
    battle.smoke_clips.append(Pending("screen", screen_x, screen_y, lane, owner, battle.step + ROUND_SCREEN))
    battle.event("round", "smoke", x10(screen_x), x10(screen_y), side_index(owner), round_id)


def throw_smoke(battle: "Battle", soldier: "Soldier", x: float, y: float) -> None:
    """throwSmokeCommand (F6:8507-8513): the leader keeps the aimed point and plays the throw; the grenade leaves on
    the throw frame (S666/frame_1436, `release`)"""
    soldier.gren_type = "smokeGrenade"
    soldier.gren_target = (x, y)
    soldier.goto(battle, THROW_LABEL, True)


def release(battle: "Battle", soldier: "Soldier") -> None:
    """The smoke grenade leaves the hand (S666/frame_1436, throwSmokeGrenade F6:8514-8546): it lands at the aimed
    point + random(40) - 20 in x and random(20) - 10 in y (the original's tank line reads a stray global, so every
    throw takes the ± 10) and plays arc 1 or 2, bursting 39 or 35 steps later. The throw costs its side 50 RP. The
    grenade's turn along the throw is the page's."""
    aim_x, aim_y = soldier.gren_target
    owner = soldier.squad.side
    x = aim_x + battle.random(GRENADE_X[0]) - GRENADE_X[1]
    y = aim_y + battle.random(GRENADE_Y[0]) - GRENADE_Y[1]
    arc = battle.random(2) + 1
    start, burst = ARCS[arc - 1]
    battle.smoke_clips.append(Pending("grenade", x, y, 0, owner, battle.step + burst - start))
    battle.event("grenade", soldier.id, x10(x), x10(y), arc, "smoke")
    soldier.gren_type = "handGrenade"
    soldier.gren_target = None
    battle.adjust_rp(owner, -ORDER_COSTS["smoke"])


def between(owner: str, leader_x: float, smoke_x: float, target_x: float) -> bool:
    """The screen lies between the squad and its target: for the American side leader x < smoke x < target x,
    mirrored for the German (F6:1976, 1987)"""
    if owner == "british":
        return leader_x < smoke_x < target_x
    return leader_x > smoke_x > target_x


def check_smoke(battle: "Battle", side: str) -> None:
    """checkSmoke (F6:1967-1998) with B31 fixed: every squad of the side is smoked exactly while any screen in its
    lane, appeared and not yet faded out, lies between its leader and its target's leader"""
    for squad in battle.sides[side].squads:
        leader = squad.leader
        target = squad.target.leader if squad.target is not None else None
        squad.smoked = (
            leader is not None
            and target is not None
            and any(cloud.lane == squad.lane and between(side, leader.x, cloud.x, target.x) for cloud in battle.smoke)
        )
