"""The Super Unicorn: a bar that charges as cubes take damage, and a merged pig that shoots every color at once.

While the player has earned it (the bot says so when the level starts), its bar fills by 1 for every point of damage
a cube takes, except the Unicorn's own (MergedShooterSystem$$OnTargetDamaged, RVA 0x518E55C; CanChargeFrom, RVA
0x518E5D0; aim.charge_unicorn does the counting where damage lands). The tap ["unicorn"] with a full bar merges every
slot pig, and the rescue pigs Connected to them, into one shooter that fires all their ammo, color after color, at
targets spread over the picture, then the merged pigs leave and the stuck check's repair runs.

The original's game is stopped while it runs (MergedShooterSystem is a game pauser), so the whole run lands in the
one tap and the page plays it with its clock held. Its picks use a time-seeded System.Random only for the bucket
shuffles and the pick inside a bucket; this module keeps the algorithm and draws from the level's generator in the
same order of calls. web/sim/unicorn.js mirrors this file.
"""

from __future__ import annotations

from . import aim, base, boosters, checks, places
from . import grid as gridx
from .mathx import idiv, isqrt
from .numbers import SHOT_DAMAGE, UNICORN_CHARGE_COUNT, UNICORN_FILL_PERCENT

# Candidate tiers (MergedShooterTargetTier) and the priority one tier spans (MergedShooterFeatureTargetOrder)
TIER_OPEN_PIXEL = 0
TIER_BLOCKED_PIXEL = 1
TIER_OPEN_FEATURE = 2
TIER_BLOCKED_FEATURE = 3
RANK_SPAN = 100


def new_unicorn(cubes: int, active: bool) -> dict:
    """The level's bar: whether the player has the Unicorn this level, the charge, and the charge that fills it."""
    return {"active": active, "charge": 0, "need": need_for(cubes), "running": False}


def need_for(cubes: int) -> int:
    """round(0.9 x cubes / 3), halves to even, at least 1 (LevelRatioChargeRequirement$$Calculate, RVA 0x514B1D0,
    with MergedShooterSettings' FillPercent 0.9 and ChargeCount 3; the float32 steps give the same whole number)."""
    whole, part = divmod(cubes * UNICORN_FILL_PERCENT, 100 * UNICORN_CHARGE_COUNT)
    twice = 2 * part
    if twice > 100 * UNICORN_CHARGE_COUNT or (twice == 100 * UNICORN_CHARGE_COUNT and whole % 2 == 1):
        whole += 1
    return max(1, whole)


def full(state: base.State) -> bool:
    unicorn = state.unicorn
    return unicorn["active"] and unicorn["charge"] >= unicorn["need"]


def use(state: base.State) -> str | None:
    """The ["unicorn"] tap (MergedShooterSystem$$TryActivate, RVA 0x518F1E0; GetUseFailReason, RVA 0x518F09C).
    Returns why it was refused, or None."""
    if not state.unicorn["active"]:
        return "not active"
    if state.finishing:
        return "auto-finisher running"
    if state.cubes_left <= 0:
        return "no cubes"
    if not full(state):
        return "not charged"
    merged = gather(state)
    if not merged:
        return "no pigs to merge"
    run(state, merged)
    return None


def gather(state: base.State) -> list[int]:
    """Every slot pig, in slot order, that may merge, each followed by the pigs of its Connected group waiting in the
    rescue queue (MergedShooterMergeGatherer$$Gather, RVA 0x5170B90; AddWithRescueConnections, RVA 0x516D25C)."""
    merged: list[int] = []
    for pig_id in state.slots:
        if pig_id is None or pig_id in merged or not mergeable(state, state.pigs[pig_id]):
            continue
        merged.append(pig_id)
        for member in links(state, state.pigs[pig_id]) or []:
            if member in state.rescue and member not in merged:
                merged.append(member)
    return merged


def links(state: base.State, pig: base.Pig) -> list[int] | None:
    """The pig's Connected group from a feature module's merge_links hook, or None."""
    for module in base.MODULES:
        hook = getattr(module, "merge_links", None)
        if hook is not None:
            members = hook(state, pig)
            if members is not None:
                return members
    return None


def mergeable(state: base.State, pig: base.Pig) -> bool:
    """A Connected pig merges only while its whole group waits in slots or the rescue queue
    (MergedShooterMergeGatherer$$IsEligible, RVA 0x516DD4C)."""
    members = links(state, pig)
    return members is None or all(state.pigs[member].place in ("slot", "rescue") for member in members)


def ammo_table(state: base.State, merged: list[int]) -> list[list[int]]:
    """[color, ammo] summed over the merged pigs, colors in the order they first appear
    (MergedShooterMergeGatherer$$BuildColorAmmoTable, RVA 0x516FA90)."""
    table: list[list[int]] = []
    for pig_id in merged:
        pig = state.pigs[pig_id]
        if pig.ammo <= 0:
            continue
        for row in table:
            if row[0] == pig.color:
                row[1] += pig.ammo
                break
        else:
            table.append([pig.color, pig.ammo])
    return table


def run(state: base.State, merged: list[int]) -> None:
    """The merge and the shooting, then the merged pigs leave, the repair runs, the bar empties and the Pixel Pipes
    that waited check their colors (<ShootAndFinish>d__43$$MoveNext, RVA 0x5167C88; <ShootAllColors>d__44, RVA
    0x51676D0)."""
    unicorn = state.unicorn
    unicorn["running"] = True
    table = ammo_table(state, merged)
    for pig_id in merged:
        state.pigs[pig_id].ammo = 0
    base.emit(state, "unicorn_start", {"ids": list(merged), "colors": [list(row) for row in table]})
    for color, ammo in table:
        for pick in take_targets(state, color, ammo):
            shoot(state, color, pick)
    for pig_id in merged:
        places.vanish(state, state.pigs[pig_id], "merged")
    sync(state)
    unicorn["charge"] = 0
    unicorn["running"] = False
    base.call_hooks(state, "unicorn_done")
    checks.request_stuck_check(state)
    base.emit(state, "unicorn_end", {})
    base.emit(state, "booster_done", {"name": "unicorn"})


def sync(state: base.State) -> None:
    """MapController$$SyncShootersAndPixels, RVA 0x58D1F50: empty pigs vanish, ammo beyond what each color has left
    is taken away lowest pigs first, and the auto-finisher may start."""
    for pig_id in checks.repair(state, checks.extra_ammo(state)):
        places.vanish(state, state.pigs[pig_id], "repair")
    checks.try_autofinish(state)


# ---------- Picking targets ----------


def take_targets(state: base.State, color: int, ammo: int) -> list[dict]:
    """The color's shots: candidates, the spread selection, then where on each target its shots land
    (MergedShooterExecutionFlow$$TakeTargets, RVA 0x515ED0C)."""
    picks = select_targets(state, ammo, collect(state, color, ammo))
    assign_points(state, picks)
    return picks


def candidate(target: int, owner: int, ref: int, cells: list[int], cell: int, priority: int, capacity: int) -> dict:
    """target is a grid target's id (-1 for a feature's queued part, which owner's module names by ref); cells are
    the points its shots may land on and cell its own point."""
    return {
        "target": target,
        "owner": owner,
        "ref": ref,
        "cells": cells,
        "cell": cell,
        "priority": priority,
        "capacity": capacity,
    }


def collect(state: base.State, color: int, max_shots: int) -> list[dict]:
    """Cubes, then features, then the features' queued parts (MergedShooterTargetCollector$$Collect, RVA 0x519ED94).
    Nothing when max_shots is below 1."""
    found: list[dict] = []
    if max_shots < 1:
        return found
    collect_cubes(state, color, max_shots, found)
    collect_features(state, color, max_shots, found)
    collect_queued(state, color, max_shots, found)
    return found


def hits_left(target: gridx.Target) -> int:
    """Damage the target still takes beyond the shots already flying at it (IHitTarget's would-die check)."""
    return target.health - target.pending


def collect_cubes(state: base.State, color: int, max_shots: int, found: list[dict]) -> None:
    """Every living cube of the color, row by row from the bottom, each at its lowest-left cell: tier 0 when no
    obstacle stands on it and it isn't a hidden Surprise Pixel, else tier 1 (CollectPixels, RVA 0x519B38C)."""
    grid = state.grid
    cubes = [t for t in grid.targets if t.owner == 0 and not t.dead and t.cells and t.color == color]
    cubes.sort(key=lambda cube: (idiv(cube.cells[0], grid.width), cube.cells[0] % grid.width))
    for cube in cubes:
        left = hits_left(cube)
        if left < 1 or not cube.hittable:
            continue
        tier = TIER_OPEN_PIXEL if boosters.super_viable(state, cube) else TIER_BLOCKED_PIXEL
        priority = tier * RANK_SPAN
        found.append(candidate(cube.id, 0, -1, list(cube.cells), cube.cells[0], priority, min(left, max_shots)))


def collect_features(state: base.State, color: int, max_shots: int, found: list[dict]) -> None:
    """Every feature target of the color that isn't "match all", in the order it joined the picture, at its cell
    nearest its middle: tier 2, or 3 with an obstacle on its cells (CollectFeatures, RVA 0x519B7DC; TryGetGridPoint,
    RVA 0x519A334; IsBlocked, RVA 0x519A714). No feature has a rank yet, so the rank is 0."""
    for target in state.grid.targets:
        if target.owner == 0 or target.dead or not target.hittable or not target.cells or target.match_all:
            continue
        left = hits_left(target)
        if left < 1 or not checks.matches(target, color):
            continue
        tier = TIER_BLOCKED_FEATURE if blocked(state, target) else TIER_OPEN_FEATURE
        cell = grid_point(state.grid, target.cells)
        found.append(
            candidate(target.id, target.owner, -1, list(target.cells), cell, tier * RANK_SPAN, min(left, max_shots))
        )


def collect_queued(state: base.State, color: int, max_shots: int, found: list[dict]) -> None:
    """Features' queued parts of the color, from each module's unicorn_reserves hook as [ref, cells, tier, rank,
    hits] (CollectQueuedFeatures, RVA 0x5199FEC): a Pixel Pipe's cubes still in its queue."""
    for module in base.MODULES:
        hook = getattr(module, "unicorn_reserves", None)
        if hook is None:
            continue
        for ref, cells, tier, rank, hits in hook(state, color):
            if hits >= 1 and cells:
                cell = grid_point(state.grid, cells)
                found.append(
                    candidate(-1, module.NUMBER, ref, list(cells), cell, tier * RANK_SPAN + rank, min(hits, max_shots))
                )


def blocked(state: base.State, target: gridx.Target) -> bool:
    """Some other obstacle stands on one of the target's cells."""
    for cell in target.cells:
        for other in gridx.at(state.grid, cell):
            if other is not target and other.obstacle and not other.dead:
                return True
    return False


def grid_point(grid: gridx.Grid, cells: list[int]) -> int:
    """The first of the cells nearest the middle of their bounding box."""
    xs = [cell % grid.width for cell in cells]
    ys = [idiv(cell, grid.width) for cell in cells]
    mid_x, mid_y = min(xs) + max(xs), min(ys) + max(ys)
    best, best_distance = cells[0], -1
    for cell, x, y in zip(cells, xs, ys, strict=True):
        distance = (2 * x - mid_x) * (2 * x - mid_x) + (2 * y - mid_y) * (2 * y - mid_y)
        if best_distance < 0 or distance < best_distance:
            best, best_distance = cell, distance
    return best


def select_targets(state: base.State, ammo: int, found: list[dict]) -> list[dict]:
    """Up to ammo shots: the priorities lowest first, and inside each the shots spread over its candidates' area,
    each picked candidate taking as many shots as kill it (MergedShooterTargetingLogic$$SelectTargets, RVA
    0x65BE194). Each shot is its own copy of its candidate."""
    picks: list[dict] = []
    if ammo < 1 or not found:
        return picks
    priorities: list[int] = []
    for entry in found:
        if entry["priority"] not in priorities:
            priorities.append(entry["priority"])
    priorities.sort()
    remaining = ammo
    for priority in priorities:
        if remaining < 1:
            break
        remaining -= pick_for_priority(state, picks, found, priority, remaining)
    return picks


def pick_for_priority(state: base.State, picks: list[dict], found: list[dict], priority: int, remaining: int) -> int:
    """PickForPriority: one candidate per bucket a round until the shots run out. Returns the shots it gave."""
    group = [index for index, entry in enumerate(found) if entry["priority"] == priority and entry["capacity"] >= 1]
    width = state.grid.width
    spread = setup_spread(state, [[found[i]["cell"] % width, idiv(found[i]["cell"], width)] for i in group], remaining)
    used = 0
    while used < remaining:
        index = pick_next(state, spread)
        if index < 0:
            break
        entry = found[group[index]]
        take = min(entry["capacity"], remaining - used)
        for _ in range(take):
            picks.append(dict(entry))
        used += take
    return used


# ---------- The spread (MergedShooterSpreadLogic) ----------


def setup_spread(state: base.State, points: list[list[int]], shot_count: int) -> dict:
    """Cut the points' bounding box into square buckets of about one shot each, file each point into its bucket, and
    shuffle the non-empty buckets (Setup, RVA 0x519577C; FillBuckets, RVA 0x5197AF4; CollectOrder, RVA 0x5198034)."""
    spread = {"order": [], "cursor": 0, "starts": [], "ends": [], "items": []}
    if not points:
        return spread
    low_x = min(p[0] for p in points)
    low_y = min(p[1] for p in points)
    size_x = max(p[0] for p in points) - low_x + 1
    size_y = max(p[1] for p in points) - low_y + 1
    side = bucket_side(size_x, size_y, shot_count)
    columns = idiv(size_x + side - 1, side)
    count = columns * idiv(size_y + side - 1, side)
    buckets = [idiv(p[1] - low_y, side) * columns + idiv(p[0] - low_x, side) for p in points]
    starts = [0] * (count + 1)
    for bucket in buckets:
        starts[bucket + 1] += 1
    for index in range(1, count + 1):
        starts[index] += starts[index - 1]
    ends = starts[:count]
    items = [0] * len(points)
    for index, bucket in enumerate(buckets):
        items[ends[bucket]] = index
        ends[bucket] += 1
    spread.update(starts=starts, ends=ends, items=items)
    spread["order"] = [bucket for bucket in range(count) if ends[bucket] > starts[bucket]]
    shuffle(state, spread["order"])
    return spread


def bucket_side(size_x: int, size_y: int, shot_count: int) -> int:
    """max(1, ceil(sqrt(area / shots))) in whole numbers (GetCellSize, RVA 0x5197A48)."""
    area = size_x * size_y
    shots = max(1, shot_count)
    side = isqrt(idiv(area, shots))
    while side * side * shots < area:
        side += 1
    return max(1, side)


def pick_next(state: base.State, spread: dict) -> int:
    """The next point: a random one left in the next bucket of the round, the round reshuffled when it ends; a
    bucket leaves the round once empty. -1 when every bucket is empty (TryPickNext, RVA 0x5195B54)."""
    order = spread["order"]
    if not order:
        return -1
    if spread["cursor"] >= len(order):
        spread["cursor"] = 0
        shuffle(state, order)
    bucket = order[spread["cursor"]]
    start, ends, items = spread["starts"][bucket], spread["ends"], spread["items"]
    slot = start + state.rng.rand_int(ends[bucket] - start)
    index = items[slot]
    ends[bucket] -= 1
    items[slot] = items[ends[bucket]]
    if ends[bucket] > start:
        spread["cursor"] += 1
    else:
        order.pop(spread["cursor"])
    return index


def shuffle(state: base.State, values: list[int]) -> None:
    """Fisher-Yates from the back (MergedShooterSpreadLogic$$Shuffle, RVA 0x51974F8)."""
    for i in range(len(values) - 1, 0, -1):
        k = state.rng.rand_int(i + 1)
        values[i], values[k] = values[k], values[i]


def assign_points(state: base.State, picks: list[dict]) -> None:
    """Spread the shots of each run of shots at one target over that target's cells, so a big target is hit all
    over (MergedShooterShotPointLogic$$Assign, RVA 0x5196300; AssignRun, RVA 0x5195174). A target on one cell keeps
    its point."""
    width = state.grid.width
    start = 0
    while start < len(picks):
        end = start + 1
        while end < len(picks) and same_target(picks[end], picks[start]):
            end += 1
        cells = picks[start]["cells"]
        if len(cells) >= 2:
            points = [[cell % width, idiv(cell, width)] for cell in cells]
            spread = setup_spread(state, points, end - start)
            for index in range(start, end):
                point = pick_next(state, spread)
                if point < 0:
                    spread = setup_spread(state, points, end - index)
                    point = pick_next(state, spread)
                picks[index]["cell"] = cells[point]
        start = end


def same_target(a: dict, b: dict) -> bool:
    return a["target"] == b["target"] and a["owner"] == b["owner"] and a["ref"] == b["ref"]


# ---------- Shooting ----------


def module_of(owner: int) -> object | None:
    for module in base.MODULES:
        if getattr(module, "NUMBER", None) == owner:
            return module
    return None


def shootable(state: base.State, color: int, pick: dict) -> bool:
    """The pick still takes a shot (MergedShooterExecutionFlow$$IsShootable, RVA 0x515F2B4)."""
    if pick["target"] >= 0:
        target = state.grid.targets[pick["target"]]
        return not target.dead and bool(target.cells) and hits_left(target) >= 1
    module = module_of(pick["owner"])
    return module is not None and module.unicorn_reserve_left(state, pick["ref"], color) >= 1


def replacement(state: base.State, color: int) -> dict | None:
    """A fresh one-shot pick for a shot whose target died meanwhile (TryFindReplacement, RVA 0x515F364)."""
    picks = select_targets(state, 1, collect(state, color, 1))
    if not picks:
        return None
    assign_points(state, picks)
    return picks[0]


def shoot(state: base.State, color: int, pick: dict) -> None:
    """One shot of 1 damage (MergedShooterExecutionFlow$$ShootTarget, RVA 0x515EF9C). A shot with nothing left to
    shoot is lost. A shot at a Pixel Pipe's queue pops one of its cubes out and breaks it (PixelPipeDrainer$$PopPixel,
    RVA 0x5752420)."""
    if not shootable(state, color, pick):
        pick = replacement(state, color)
        if pick is None:
            base.emit(state, "unicorn_miss", {"color": color})
            return
    base.emit(
        state, "unicorn_shot", {"target": pick["target"], "owner": pick["owner"], "cell": pick["cell"], "color": color}
    )
    if pick["target"] >= 0:
        aim.hit(state, state.grid.targets[pick["target"]], SHOT_DAMAGE, None)
        return
    module = module_of(pick["owner"])
    cube = module.unicorn_pop(state, pick["ref"], color)
    if cube is not None:
        aim.hit(state, cube, cube.health, None)
