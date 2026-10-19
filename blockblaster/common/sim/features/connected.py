"""Feature 2, the Connected Pig: pigs tied together go on the belt together, ride together and leave together.

Tapping any member places the whole group, in group order, or nothing: every member needs a free tray and must be
free to go (ConnectedShooterCanTapCondition$$CheckWithReason, RVA 0x55D5438). A member that runs dry rides on showing
0 and keeps its tray while any member still has ammo (ConnectedShooterCanDisappearCondition$$Call, RVA 0x55D3FAC);
when one member leaves, every member leaves (ConnectedShooterFeatureController$$TryToMakeConnectedShootersDisappear,
RVA 0x55EB548). While the auto-finisher runs a member's tray loops only while the whole group is on the belt
(ConveyorStayInInfiniteLoopCondition$$CheckConnectedShooter, RVA 0x5907E30). web/sim/features/connected.js mirrors
this file.
"""

from __future__ import annotations

from .. import base, places

NUMBER = 2


def setup(state: base.State) -> None:
    """The level's groups, each a list of pig ids linked first to last, and the groups that have left."""
    listed = state.level.features.get("ConnectedShooters")
    if not listed:
        return
    groups = []
    for connection in listed["Connections"]:
        members = [pig_id for pig_id in connection["Shooters"] if pig_id in state.pigs]
        if len(members) >= 2:
            groups.append(members)
    if groups:
        state.features[NUMBER] = {"groups": groups, "left": []}


def group_index(state: base.State, pig_id: int) -> int:
    """The index of the group holding this pig, or -1."""
    mine = state.features.get(NUMBER)
    if mine is None:
        return -1
    for index, members in enumerate(mine["groups"]):
        if pig_id in members:
            return index
    return -1


def pins(state: base.State, pig_id: int) -> bool:
    """A pig in a group carries the feature, so Shuffle leaves it where it is."""
    return group_index(state, pig_id) >= 0


def group(state: base.State, pig: base.Pig) -> list[int] | None:
    """The pigs a tap on this pig places, in placing order (ShooterProvider$$GetShootersToPlaceToConveyor, RVA
    0x58F989C), or None for a pig in no group."""
    index = group_index(state, pig.id)
    if index < 0:
        return None
    return list(state.features[NUMBER]["groups"][index])


def merge_links(state: base.State, pig: base.Pig) -> list[int] | None:
    """The Super Unicorn merges a pig with its group: the members, or None for a pig in no group."""
    return group(state, pig)


def queue_of(state: base.State, pig_id: int) -> list[int] | None:
    """The level queue holding this pig (MapProvider$$GetMapQueueOfShooter), or None in a slot, the rescue queue or
    on the belt."""
    for queue in state.queues:
        if pig_id in queue:
            return queue
    return None


def blocked_in_front(state: base.State, pig_id: int, members: list[int]) -> bool:
    """A member in a queue is blocked when any pig in front of it is not in its group (IConnectedShooterFeature$$
    IsShooterBlockedInFront, RVA 0x55D50E0). Members in slots or the rescue queue never are."""
    queue = queue_of(state, pig_id)
    if queue is None:
        return False
    return any(other not in members for other in queue[: queue.index(pig_id)])


def other_rules_refuse(state: base.State, pig: base.Pig, hand: bool) -> bool:
    """The other tap conditions the group check runs on every member (its connectedMixCanTapConditions): a
    non-tappable feature on it, or another feature against it."""
    if "untappable" in pig.tags:
        return True
    for module in base.MODULES:
        hook = getattr(module, "can_tap", None)
        if hook is None or hook is can_tap:
            continue
        if hook(state, pig, hand) is not None:
            return True
    return False


def member_refused(state: base.State, pig_id: int, members: list[int], hand: bool) -> bool:
    """One member's part of the group check, in the original's order: busy (mid-hop), the other tap conditions, then
    with the Hand on any member in a queue goes and a member outside one doesn't; without it a member mustn't be
    blocked in its queue or already on the belt."""
    pig = state.pigs[pig_id]
    if state.tick < pig.free_at or other_rules_refuse(state, pig, hand):
        return True
    in_queue = queue_of(state, pig_id) is not None
    if hand:
        return not in_queue
    return blocked_in_front(state, pig_id, members) or pig.place == "belt"


def can_tap(state: base.State, pig: base.Pig, hand: bool) -> str | None:
    """The whole group must fit on the belt, one free tray a member, and every member must be free to go."""
    members = group(state, pig)
    if members is None:
        return None
    if state.tray_total - len(state.belt) < len(members):
        return "belt full"
    for pig_id in members:
        if member_refused(state, pig_id, members, hand):
            return "group blocked"
    return None


def can_tap_normally(state: base.State, pig: base.Pig) -> str | None:
    """The stuck check's version (ConnectedShooterIsUnblockedCondition$$CheckWithReason, RVA 0x55D5DBC): every
    member passes the other tap conditions and none is blocked in its queue. The belt being full doesn't matter."""
    members = group(state, pig)
    if members is None:
        return None
    for pig_id in members:
        if other_rules_refuse(state, state.pigs[pig_id], False) or blocked_in_front(state, pig_id, members):
            return "group blocked"
    return None


def has_ammo(state: base.State, members: list[int]) -> bool:
    return any(state.pigs[pig_id].ammo >= 1 for pig_id in members)


def take_vanish(state: base.State, pig: base.Pig) -> bool:
    """A member can't leave while any member of its group still has ammo: it rides on showing 0 and keeps its tray."""
    members = group(state, pig)
    return members is not None and has_ammo(state, members)


def on_event(state: base.State, name: str, data: dict) -> None:
    """When one member is about to leave, every other member leaves too, in group order."""
    if name != "pig_vanishing" or NUMBER not in state.features:
        return
    index = group_index(state, data["pig"])
    mine = state.features[NUMBER]
    if index < 0 or index in mine["left"]:
        return
    mine["left"].append(index)
    for pig_id in mine["groups"][index]:
        if pig_id != data["pig"]:
            places.vanish(state, state.pigs[pig_id], data["cause"])


def keep_looping(state: base.State, pig: base.Pig) -> bool:
    """While the auto-finisher runs, a member's tray loops only while every member of its group is on the belt."""
    members = group(state, pig)
    return members is None or all(state.pigs[pig_id].place == "belt" for pig_id in members)


def checksum(state: base.State, h: int) -> int:
    if NUMBER not in state.features:
        return h
    left = state.features[NUMBER]["left"]
    h = base.mix(h, len(left))
    for index in left:
        h = base.mix(h, index)
    return h
