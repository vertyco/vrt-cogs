"""Gas clouds and gas masks.

A gas round's burst (common/blasts.py) starts a cloud (`gasExplosion`, F5:3347-3384). The cloud lasts a set number of
steps, then fades for 2 seconds and is gone (`clearGas`, F5:3687-3712). While it lasts, and while it fades, it hurts
every infantry squad whose leader overlaps it (`gasCloudCollisions`, F5:3630-3686), unless the squad has its masks on.

Only the player's side wears masks. While any cloud is out the side's gas button shows; pressing it sends every squad
within 400 pixels of a cloud into the masks-on state (F5:3753-3789), which plays the 43-step mask-on animation and
returns the squad to what it was doing. When the last cloud clears, masked squads take them off (36 steps).

When this runs (common/battle.py's step order): clouds count down and clear in step 2, after the strike clips; gas
damage is the root frame's, German squads before British (F5:8000-8001); the mask states are squad turns.
"""

import typing as t

from .boxes import Box, member_box, overlap
from .combat import kill, side_index
from .data import FPS, GAS_DAMAGE, GAS_DETECT, SUPPORTS, UPGRADE_EFFECTS

if t.TYPE_CHECKING:
    from .battle import Battle
    from .squads import Squad

FADE_STEPS = 2 * FPS  # a cloud fades over 2 seconds (alphaTo(0, 2), F5:3367) and still hurts while it does
# The cloud's hit box around its centre (the strike clip's collision child, tree.json sprite 334)
CLOUD_BOX = (-117.0, -123.8, 119.0, 123.05)
# A squad wearing masks, or taking them off, can't be gassed (allMasksOn)
IMMUNE = ("on", "off_going")
# The mask animation labels (S626 frames 85 and 132)
MASK_ON = "gasMaskOn_standing"
MASK_OFF = "gasMaskOff_standing"


class Cloud:
    """One gas cloud on the field. It fades from `fade_start` and is gone on step `end`."""

    __slots__ = ("id", "x", "y", "owner", "fade_start", "end")

    def __init__(self, cloud_id: int, x: float, y: float, owner: str, fade_start: int):
        self.id = cloud_id
        self.x = x
        self.y = y
        self.owner = owner
        self.fade_start = fade_start
        self.end = fade_start + FADE_STEPS


def cloud_box(cloud: Cloud) -> Box:
    left, top, right, bottom = CLOUD_BOX
    return (cloud.x + left, cloud.y + top, cloud.x + right, cloud.y + bottom)


def start_cloud(battle: "Battle", x: float, y: float, owner: str) -> None:
    """gasExplosion (F5:3347-3384): the cloud appears at the round's spot and the gas button shows for every player.
    The cloud counts its life down once a step from the next step on, and fades when the count goes below 0, so the
    fade starts `life + 1` steps after it appears. Lingering Gas makes the owner's clouds last x1.3 (B6). The cloud
    is made even once the battle is over, as a picture only: damage and masks are the root frame's, which stops."""
    life = SUPPORTS[owner]["gas"]["cloud_steps"]
    if battle.sides[owner].has("gas_time"):
        life *= UPGRADE_EFFECTS["gas_time"]["value"]
    battle.round_count += 1
    cloud = Cloud(battle.round_count, x, y, owner, battle.step + round(life) + 1)
    battle.gas.append(cloud)
    for side in battle.sides.values():
        if side.human:
            side.gas_button = True
    battle.event("gas", cloud.id, round(x * 10), round(y * 10), side_index(owner))


def run_clouds(battle: "Battle") -> None:
    """Step 2: each cloud whose fade has finished is cleared, oldest first (the cloud clip's onEnterFrame)"""
    for cloud in [cloud for cloud in battle.gas if cloud.end <= battle.step]:
        clear_gas(battle, cloud)


def clear_gas(battle: "Battle", cloud: Cloud) -> None:
    """clearGas (F5:3687-3712). With no cloud left, every player's button hides, their squads forget the gas, and the
    ones wearing masks (or putting them on) take them off. Once the battle is over nobody changes state."""
    battle.gas.remove(cloud)
    if battle.gas:
        return
    for side in battle.sides.values():
        if not side.human:
            continue
        side.gas_button = False
        # for (v in squads), F5:3703
        for squad in battle.newest_first(side.squads):
            squad.near_gas = False
            if battle.state == "playing" and squad.masks in ("on", "on_going"):
                squad.last_state = squad.state
                squad.state = "gasMasksOff"
                squad.masks = "off_going"
                battle.event("masks", squad.id, 0)


def cloud_damage(battle: "Battle", cloud: Cloud) -> float:
    """The pool a cloud takes from a squad each step: 0.4, or x1.25 for a cloud its owner's Toxic Gas made (B8)"""
    damage = GAS_DAMAGE
    if battle.sides[cloud.owner].has("toxic_gas"):
        damage *= UPGRADE_EFFECTS["toxic_gas"]["value"]
    return damage


def gas_damage(battle: "Battle", side: str) -> None:
    """gasCloudCollisions (F5:3630-3686) for one side's squads. A cloud whose centre is within 400 pixels of a squad's
    leader marks the squad near gas (and it stays marked); a marked, unmasked infantry squad whose leader's box
    touches the cloud's loses its damage, then every member at or past its threshold dies, walked newest first with
    no early stop. A gas death gives no XP and no kill count."""
    if not battle.gas:
        return
    owner = battle.sides[side]
    # for (v in activeGas), F5:3634
    for cloud in battle.newest_first(battle.gas):
        box = cloud_box(cloud)
        # for (s in squads), F5:3636
        for squad in battle.newest_first(owner.squads):
            if not squad.members:
                continue
            leader = squad.members[0]
            if -GAS_DETECT < cloud.x - leader.x < GAS_DETECT:
                squad.near_gas = True
            if not squad.near_gas or squad.masks in IMMUNE or squad.kind == "tank":
                continue
            if overlap(box, member_box(leader)):
                hurt(battle, squad, cloud_damage(battle, cloud))


def hurt(battle: "Battle", squad: "Squad", damage: float) -> None:
    squad.pool -= damage
    # for (m in members), F5:3653: newest first, so a removed member never shifts one still to come
    for member in battle.newest_first(squad.members):
        if member.alive and squad.pool <= member.threshold:
            kill(battle, member, "gas", None)


def masks_on(battle: "Battle", side: str) -> bool:
    """The player's press on the gas button (F5:3768-3779): every squad of the side near a cloud that isn't already
    masked goes to the masks-on state. Tanks wear none. False when refused: not a player's side, the battle isn't
    running, or no cloud is out so the button is hidden."""
    owner = battle.sides.get(side)
    if owner is None or not owner.human or battle.state != "playing" or battle.paused or not owner.gas_button:
        return False
    # for (g in squads), F5:3772
    for squad in battle.newest_first(owner.squads):
        if squad.near_gas and squad.kind != "tank" and squad.masks == "off":
            squad.last_state = squad.state
            squad.state = "gasMasksOn"
            squad.masks = "on_going"
            battle.event("masks", squad.id, 1)
    return True


def state_masks_on(battle: "Battle", squad: "Squad") -> None:
    """gasMasksOn (F5:1950-1978): each member that hasn't its mask on starts the mask animation, once; when every
    member's has finished the squad goes back to what it was doing. The members' mask-off flag is cleared so a later
    cloud plays the whole take-off again."""
    squad.masks = "on_going"
    done = True
    for soldier in battle.newest_first(squad.members):
        flags = soldier.flags
        if not flags["gasMaskOn"] and not soldier.putting_on_mask:
            soldier.putting_on_mask = True
            flags["moveAnim"] = False
            flags["firing"] = False
            soldier.goto(battle, MASK_ON, True)
        if not flags["gasMaskOn"]:
            done = False
    if not done:
        return
    for soldier in squad.members:
        soldier.putting_on_mask = False
        soldier.flags["gasMaskOff"] = False
    squad.masks = "on"
    squad.state = squad.last_state


def state_masks_off(battle: "Battle", squad: "Squad") -> None:
    """gasMasksOff (F5:1979-2018): the same for taking masks off. Then the squad goes back to the trench if it is in
    one, else to Moving: the original's `lastState = "gasMasksOn"` there assigns instead of comparing, so its
    earlier state is never restored."""
    squad.masks = "off_going"
    done = True
    for soldier in battle.newest_first(squad.members):
        flags = soldier.flags
        if not flags["gasMaskOff"] and not soldier.taking_off_mask:
            soldier.taking_off_mask = True
            flags["moveAnim"] = False
            flags["firing"] = False
            soldier.goto(battle, MASK_OFF, True)
        if not flags["gasMaskOff"]:
            done = False
    if not done:
        return
    for soldier in squad.members:
        soldier.taking_off_mask = False
        soldier.flags["gasMaskOn"] = False
    squad.masks = "off"
    squad.state = "entrench" if squad.members[0].flags["position"] == "trench" else "moving"
