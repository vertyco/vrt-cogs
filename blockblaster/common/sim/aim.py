"""Aiming, firing and shots in flight (ShootersOffenseController, ProjectilesController).

Each tick every pig on the belt, in the order its tray started, looks along the rows (from the left or right side) or
columns (from the bottom or top) near it for the best target its color can hit, and fires while its fire timer is
due. A shot costs 1 ammo and lands its 1 damage when it arrives, a few ticks later. web/sim/aim.js mirrors this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import base, belt, checks
from . import grid as gridx
from .mathx import clamp, idiv, isqrt
from .numbers import (
    BASE_FIRE_RATE,
    BEATS_PER_TICK,
    FIRE_INTERVAL_SCALE,
    FIRE_SLACK_BEATS,
    HIT_RADIUS,
    LINE_OFFSET_WEIGHT,
    LINE_TOLERANCE,
    MAX_SHOTS_PER_TICK,
    MULT_BASE,
    MULT_FINISH,
    MULT_SIZE_SPAN,
    MULT_SLOW_SIZE,
    MULT_SPAN,
    SHOT_DAMAGE,
    SHOT_SPEED,
)


@dataclass
class Shot:
    pig: int
    target: int  # target id
    cell: int  # the cell it was aimed at
    fired: int  # tick
    land: int  # the tick whose phase 5 it arrives in


def fire_interval(state: base.State) -> int:
    """Beats between one pig's shots: 20.7 shots a second times the fire-speed multiplier, which grows as cubes get
    smaller (ShootersOffenseController$$get_FinalShotsPerSecond, RVA 0x5452090; ShootSpeedMultiplier$$Get)."""
    mult = MULT_BASE + idiv(MULT_SPAN * clamp(MULT_SLOW_SIZE - state.grid.size, 0, MULT_SIZE_SPAN), MULT_SIZE_SPAN)
    if state.finishing:
        mult += MULT_FINISH
    rate = idiv(BASE_FIRE_RATE * mult, 1000)
    return idiv(FIRE_INTERVAL_SCALE, rate)


def pig_tray(state: base.State, pig_id: int) -> base.Tray | None:
    for tray in state.belt:
        if tray.pig == pig_id and tray.started:
            return tray
    return None


def step_shooting(state: base.State) -> list[int]:
    """Phase 3: every shooter fires what its timer allows, then pigs that ran dry are announced
    (ShootersOffenseController$$Update, RVA 0x545818C). Returns those pigs' ids, for the core to make vanish."""
    empty: list[int] = []
    for pig_id in list(state.shooters):
        pig = state.pigs[pig_id]
        tray = pig_tray(state, pig_id)
        if tray is None or "disabled" in pig.tags:
            continue
        if tick_shooter(state, pig, tray):
            empty.append(pig_id)
    for pig_id in empty:
        base.emit(state, "ammo_out", {"pig": pig_id})
    return empty


def tick_shooter(state: base.State, pig: base.Pig, tray: base.Tray) -> bool:
    """One pig's turn (ShootersOffenseController$$TickShooter, RVA 0x5451A88). It fires while it has ammo, a target
    and a shot due within this tick (plus the original's 0.0001 s slack), at most a few shots a tick. A pig with no
    target keeps its timer at most one interval ahead. Returns True when the pig has run out of ammo."""
    if pig.ammo <= 0:
        return True
    now = state.tick * BEATS_PER_TICK
    due = max(now, pig.next_fire)
    interval = fire_interval(state)
    window = BEATS_PER_TICK + FIRE_SLACK_BEATS
    cap = clamp(-idiv(-window, interval) + 1, 1, MAX_SHOTS_PER_TICK)
    side = belt.side(state, tray)
    fired = 0
    empty = False
    while pig.ammo >= 1 and due - now <= window:
        choice = find_target(state, pig, tray, side)
        if choice is None:
            break
        fire(state, pig, tray, choice[0], choice[1])
        if pig.ammo <= 0:
            empty = True
            break
        due += interval
        pig.next_fire = due
        fired += 1
        if fired == cap:
            return False
    if fired == 0 and now >= due:
        pig.next_fire = now + interval
    return empty


def aligned_lines(grid: gridx.Grid, axis: int, ref: int) -> list[tuple[int, int]]:
    """(line, offset) for every row or column whose center is within LINE_TOLERANCE of ref, nearest first, equal
    offsets in line order (ShootersOffenseController$$GatherAlignedRows, RVA 0x54562D8, and its insertion sort)."""
    count = grid.height if axis == gridx.AXIS_ROW else grid.width
    lines: list[tuple[int, int]] = []
    for line in range(count):
        center = gridx.center_y(grid, line) if axis == gridx.AXIS_ROW else gridx.center_x(grid, line)
        offset = abs(center - ref)
        if offset > LINE_TOLERANCE:
            continue
        index = len(lines)
        while index > 0 and lines[index - 1][1] > offset:
            index -= 1
        lines.insert(index, (line, offset))
    return lines


def solid_occupants(state: base.State, axis: int, line: int, scan: int) -> tuple[int, list[gridx.Target]]:
    """The first cell on the line holding anything solid, seen from the pig's side, and its solid occupants: the cube
    first, then the cell's features (ShootersOffenseController$$TryToFillSolidTargetDataListOnPoint, RVA 0x5459BE0)."""
    cell = gridx.first_solid(state.grid, axis, line, scan)
    if cell == gridx.NO_CELL:
        return cell, []
    return cell, [target for target in gridx.at(state.grid, cell) if gridx.is_solid(target)]


def find_target(state: base.State, pig: base.Pig, tray: base.Tray, side: int) -> tuple[gridx.Target, int] | None:
    """The best (target, cell) for this pig, or None (ShootersOffenseController$$FindFrontTargetBest, RVA 0x5452184).

    The score is the squared distance from the pig to the cell's center plus a little for the line's offset. On rows
    the first of equal scores wins, on columns the last."""
    grid = state.grid
    x, y, _ = belt.point(state, tray.pos)
    rows = side in (belt.LEFT, belt.RIGHT)
    axis = gridx.AXIS_ROW if rows else gridx.AXIS_COLUMN
    scan = gridx.FROM_START if side in (belt.LEFT, belt.BOTTOM) else gridx.FROM_END
    best = None
    best_score = 0
    for line, offset in aligned_lines(grid, axis, y if rows else x):
        cell, occupants = solid_occupants(state, axis, line, scan)
        targets = obstacle_filter(state, occupants)
        if targets is None:
            break
        cx, cy = gridx.cell_center(grid, cell) if targets else (0, 0)
        for target in targets:
            if not valid_target(state, pig, target) or reserved(pig, target, cell):
                continue
            score = (cx - x) * (cx - x) + (cy - y) * (cy - y) + LINE_OFFSET_WEIGHT * offset
            if best is None or score < best_score or (not rows and score == best_score):
                best = (target, cell)
                best_score = score
    return best


def obstacle_filter(state: base.State, occupants: list[gridx.Target]) -> list[gridx.Target] | None:  # noqa: ARG001
    """A cell holding an active obstacle only offers targets that are both an obstacle and hittable (a Biscuit, a
    Rocket). None when such a cell offers nothing: the line of fire is blocked and the search ends
    (ShootersOffenseController$$FilterObstacleTargets, RVA 0x545709C)."""
    if not any(target.obstacle for target in occupants):
        return occupants
    kept = [target for target in occupants if target.obstacle and target.hittable]
    return kept or None


def valid_target(state: base.State, pig: base.Pig, target: gridx.Target) -> bool:  # noqa: ARG001
    """Alive, hittable, takes the pig's color and not already doomed by a shot in flight
    (ShootersOffenseController$$IsValidTarget, RVA 0x54571D4; HitTarget$$IsTargetMatch, RVA 0x544E608)."""
    if target.dead or not target.hittable or not target.cells or target.claimed:
        return False
    if target.match_all:
        return True
    if target.color == pig.color:
        return True
    return target.colors is not None and pig.color in target.colors


def reserved(pig: base.Pig, target: gridx.Target, cell: int) -> bool:
    """This pig already has a shot in flight at this cell of a target that takes several hits
    (ShootersOffenseController$$CheckShooterTargetIsReserved, RVA 0x5457584)."""
    return [target.id, cell] in pig.reserved


def fire(state: base.State, pig: base.Pig, tray: base.Tray, target: gridx.Target, cell: int) -> None:
    """One shot. A shot that will kill its target claims it for every pig (ClaimTargetDead, RVA 0x5452704); one that
    won't reserves the cell for this pig until something damages it there (ClaimTargetForShooter, RVA 0x5452868).
    The shot flies from the pig's shoot point to the cell's center and lands in phase 5 of the tick it gets within
    HIT_RADIUS, moving SHOT_SPEED a tick from this tick on (ProjectilesController$$MoveProjectiles, RVA 0x546BDD4).
    A shot at a free-shot target costs no ammo (ShooterWeaponController$$Shoot, RVA 0x548A0E8, skips the ammo step
    for an IFreeShootTarget)."""
    if target.health - (target.pending + SHOT_DAMAGE) < 1:
        target.claimed = True
    else:
        pig.reserved.append([target.id, cell])
    target.pending += SHOT_DAMAGE
    if not target.free_shot:
        pig.ammo -= 1
    sx, sy = belt.position(state, tray)
    sz = belt.muzzle_height(state)
    tx, ty = gridx.cell_center(state.grid, cell)
    distance = isqrt((tx - sx) * (tx - sx) + (ty - sy) * (ty - sy) + sz * sz)
    moves = max(1, -idiv(HIT_RADIUS - distance, SHOT_SPEED))
    land = state.tick + moves - 1
    state.shots.append(Shot(pig=pig.id, target=target.id, cell=cell, fired=state.tick, land=land))
    base.emit(
        state,
        "shot",
        {"pig": pig.id, "target": target.id, "cell": cell, "land": land, "from": [sx, sy, sz], "to": [tx, ty]},
    )


def step_shots(state: base.State) -> None:
    """Phase 5: shots arriving this tick land, in firing order. A shot whose target is already gone vanishes without
    doing damage. When the last shot in flight ends the stuck check starts again
    (ProjectilesEvents$$TriggerLastActiveProjectileDestroyed)."""
    had = bool(state.shots)
    flying = []
    for shot in state.shots:
        target = state.grid.targets[shot.target]
        if target.dead:
            base.emit(state, "shot_lost", {"pig": shot.pig, "target": shot.target})
        elif shot.land <= state.tick:
            hit(state, target, SHOT_DAMAGE, shot)
        else:
            flying.append(shot)
    state.shots = flying
    if had and not flying:
        checks.request_stuck_check(state)


def hit(state: base.State, target: gridx.Target, damage: int, source: Shot | None) -> None:
    """Land damage on a target. A shot carries the cell it hit; damage at a cell frees every pig's reservation of that
    cell, and damage from no particular cell frees them all (the OnDamaged handler ClaimTargetForShooter adds). Cubes
    are damaged by damage_cube, other targets by their feature module's on_hit."""
    if target.dead:
        return
    cell = None if source is None else source.cell
    release(state, target, cell)
    if source is not None:
        target.pending = max(0, target.pending - damage)
    if target.owner == 0:
        damage_cube(state, target, damage, "shot" if source is not None else "other", cell)
    else:
        for module in base.MODULES:
            if getattr(module, "NUMBER", None) == target.owner:
                module.on_hit(state, target, damage, source)
                break
    if target.dead:
        release(state, target, None)


def release(state: base.State, target: gridx.Target, cell: int | None) -> None:
    """Free pigs' reservations of a target: of one cell, or every cell when cell is None."""
    for pig in state.pigs.values():
        if pig.reserved:
            pig.reserved = [r for r in pig.reserved if r[0] != target.id or (cell is not None and r[1] != cell)]


def damage_cube(state: base.State, cube: gridx.Target, damage: int, cause: str, cell: int | None) -> None:
    """A cube loses health; at none left it is gone from the picture and the win check starts again (HitTarget$$Damage,
    RVA 0x544FE18; HitTargetEvents$$TriggerTargetDeath)."""
    charge_unicorn(state, damage)
    cube.health = max(0, cube.health - damage)
    base.emit(state, "hit", {"target": cube.id, "cell": -1 if cell is None else cell, "health": cube.health})
    if cube.health > 0:
        return
    cube.dead = True
    cells = cube.cells
    gridx.remove(state.grid, cube)
    state.cubes_left -= 1
    base.emit(
        state,
        "cube_died",
        {"cube": cube.id, "color": cube.color, "cause": cause, "single": len(cells) == 1, "cell": cells[0]},
    )
    checks.request_win_check(state)


def charge_unicorn(state: base.State, damage: int) -> None:
    """Damage to a cube fills the Super Unicorn's bar while the player has it this level, until the bar is full; its
    own hits don't count (MergedShooterSystem$$OnTargetDamaged, RVA 0x518E55C: CanChargeFrom takes any cube and no
    feature; MergedShooterChargeLogic$$AddPixels, RVA 0x514A924, adds the damage only while the bar isn't full)."""
    unicorn = state.unicorn
    if unicorn["active"] and not unicorn["running"] and damage >= 1 and unicorn["charge"] < unicorn["need"]:
        unicorn["charge"] += damage
