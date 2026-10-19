// Aiming, firing and shots in flight (ShootersOffenseController, ProjectilesController).
// Each tick every pig on the belt, in the order its tray started, looks along the rows (from the left or right side) or
// columns (from the bottom or top) near it for the best target its color can hit, and fires while its fire timer is
// due. A shot costs 1 ammo and lands its 1 damage when it arrives, a few ticks later. common/sim/aim.py mirrors this.
import * as base from "./base.js";
import * as belt from "./belt.js";
import * as checks from "./checks.js";
import * as gridx from "./grid.js";
import { clamp, idiv, isqrt } from "./mathx.js";
import {
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
} from "./numbers.js";

// A shot record. target: target id. cell: the cell it was aimed at. fired: tick. land: the tick whose phase 5 it
// arrives in
export function makeShot(pig, target, cell, fired, land) {
  return { pig, target, cell, fired, land };
}

// Beats between one pig's shots: 20.7 shots a second times the fire-speed multiplier, which grows as cubes get smaller
// (ShootersOffenseController$$get_FinalShotsPerSecond, RVA 0x5452090; ShootSpeedMultiplier$$Get)
export function fireInterval(state) {
  let mult = MULT_BASE + idiv(MULT_SPAN * clamp(MULT_SLOW_SIZE - state.grid.size, 0, MULT_SIZE_SPAN), MULT_SIZE_SPAN);
  if (state.finishing) {
    mult += MULT_FINISH;
  }
  const rate = idiv(BASE_FIRE_RATE * mult, 1000);
  return idiv(FIRE_INTERVAL_SCALE, rate);
}

export function pigTray(state, pigId) {
  for (const tray of state.belt) {
    if (tray.pig === pigId && tray.started) {
      return tray;
    }
  }
  return null;
}

// Phase 3: every shooter fires what its timer allows, then pigs that ran dry are announced
// (ShootersOffenseController$$Update, RVA 0x545818C). Returns those pigs' ids, for the core to make vanish
export function stepShooting(state) {
  const empty = [];
  for (const pigId of [...state.shooters]) {
    const pig = state.pigs[pigId];
    const tray = pigTray(state, pigId);
    if (tray === null || pig.tags.includes("disabled")) {
      continue;
    }
    if (tickShooter(state, pig, tray)) {
      empty.push(pigId);
    }
  }
  for (const pigId of empty) {
    base.emit(state, "ammo_out", { pig: pigId });
  }
  return empty;
}

// One pig's turn (ShootersOffenseController$$TickShooter, RVA 0x5451A88). It fires while it has ammo, a target and a
// shot due within this tick (plus the original's 0.0001 s slack), at most a few shots a tick. A pig with no target
// keeps its timer at most one interval ahead. Returns true when the pig has run out of ammo
export function tickShooter(state, pig, tray) {
  if (pig.ammo <= 0) {
    return true;
  }
  const now = state.tick * BEATS_PER_TICK;
  let due = Math.max(now, pig.nextFire);
  const interval = fireInterval(state);
  const window = BEATS_PER_TICK + FIRE_SLACK_BEATS;
  const cap = clamp(-idiv(-window, interval) + 1, 1, MAX_SHOTS_PER_TICK);
  const side = belt.side(state, tray);
  let fired = 0;
  let empty = false;
  while (pig.ammo >= 1 && due - now <= window) {
    const choice = findTarget(state, pig, tray, side);
    if (choice === null) {
      break;
    }
    fire(state, pig, tray, choice[0], choice[1]);
    if (pig.ammo <= 0) {
      empty = true;
      break;
    }
    due += interval;
    pig.nextFire = due;
    fired += 1;
    if (fired === cap) {
      return false;
    }
  }
  if (fired === 0 && now >= due) {
    pig.nextFire = now + interval;
  }
  return empty;
}

// [line, offset] for every row or column whose center is within LINE_TOLERANCE of ref, nearest first, equal offsets in
// line order (ShootersOffenseController$$GatherAlignedRows, RVA 0x54562D8, and its insertion sort)
export function alignedLines(grid, axis, ref) {
  const count = axis === gridx.AXIS_ROW ? grid.height : grid.width;
  const lines = [];
  for (let line = 0; line < count; line++) {
    const center = axis === gridx.AXIS_ROW ? gridx.centerY(grid, line) : gridx.centerX(grid, line);
    const offset = Math.abs(center - ref);
    if (offset > LINE_TOLERANCE) {
      continue;
    }
    let index = lines.length;
    while (index > 0 && lines[index - 1][1] > offset) {
      index -= 1;
    }
    lines.splice(index, 0, [line, offset]);
  }
  return lines;
}

// The first cell on the line holding anything solid, seen from the pig's side, and its solid occupants: the cube
// first, then the cell's features (ShootersOffenseController$$TryToFillSolidTargetDataListOnPoint, RVA 0x5459BE0)
export function solidOccupants(state, axis, line, scan) {
  const cell = gridx.firstSolid(state.grid, axis, line, scan);
  if (cell === gridx.NO_CELL) {
    return [cell, []];
  }
  return [cell, gridx.at(state.grid, cell).filter((target) => gridx.isSolid(target))];
}

// The best [target, cell] for this pig, or null (ShootersOffenseController$$FindFrontTargetBest, RVA 0x5452184).
// The score is the squared distance from the pig to the cell's center plus a little for the line's offset. On rows the
// first of equal scores wins, on columns the last
export function findTarget(state, pig, tray, side) {
  const grid = state.grid;
  const [x, y] = belt.point(state, tray.pos);
  const rows = side === belt.LEFT || side === belt.RIGHT;
  const axis = rows ? gridx.AXIS_ROW : gridx.AXIS_COLUMN;
  const scan = side === belt.LEFT || side === belt.BOTTOM ? gridx.FROM_START : gridx.FROM_END;
  let best = null;
  let bestScore = 0;
  for (const [line, offset] of alignedLines(grid, axis, rows ? y : x)) {
    const [cell, occupants] = solidOccupants(state, axis, line, scan);
    const targets = obstacleFilter(state, occupants);
    if (targets === null) {
      break;
    }
    const [cx, cy] = targets.length ? gridx.cellCenter(grid, cell) : [0, 0];
    for (const target of targets) {
      if (!validTarget(state, pig, target) || reserved(pig, target, cell)) {
        continue;
      }
      const score = (cx - x) * (cx - x) + (cy - y) * (cy - y) + LINE_OFFSET_WEIGHT * offset;
      if (best === null || score < bestScore || (!rows && score === bestScore)) {
        best = [target, cell];
        bestScore = score;
      }
    }
  }
  return best;
}

// A cell holding an active obstacle only offers targets that are both an obstacle and hittable (a Biscuit, a Rocket).
// null when such a cell offers nothing: the line of fire is blocked and the search ends
// (ShootersOffenseController$$FilterObstacleTargets, RVA 0x545709C)
export function obstacleFilter(state, occupants) {
  if (!occupants.some((target) => target.obstacle)) {
    return occupants;
  }
  const kept = occupants.filter((target) => target.obstacle && target.hittable);
  return kept.length ? kept : null;
}

// Alive, hittable, takes the pig's color and not already doomed by a shot in flight
// (ShootersOffenseController$$IsValidTarget, RVA 0x54571D4; HitTarget$$IsTargetMatch, RVA 0x544E608)
export function validTarget(state, pig, target) {
  if (target.dead || !target.hittable || !target.cells.length || target.claimed) {
    return false;
  }
  if (target.matchAll) {
    return true;
  }
  if (target.color === pig.color) {
    return true;
  }
  return target.colors !== null && target.colors.includes(pig.color);
}

// This pig already has a shot in flight at this cell of a target that takes several hits
// (ShootersOffenseController$$CheckShooterTargetIsReserved, RVA 0x5457584)
export function reserved(pig, target, cell) {
  return pig.reserved.some((r) => r[0] === target.id && r[1] === cell);
}

// One shot. A shot that will kill its target claims it for every pig (ClaimTargetDead, RVA 0x5452704); one that won't
// reserves the cell for this pig until something damages it there (ClaimTargetForShooter, RVA 0x5452868). The shot
// flies from the pig's shoot point to the cell's center and lands in phase 5 of the tick it gets within HIT_RADIUS,
// moving SHOT_SPEED a tick from this tick on (ProjectilesController$$MoveProjectiles, RVA 0x546BDD4). A shot at a
// free-shot target costs no ammo (ShooterWeaponController$$Shoot, RVA 0x548A0E8, skips the ammo step for an
// IFreeShootTarget)
export function fire(state, pig, tray, target, cell) {
  if (target.health - (target.pending + SHOT_DAMAGE) < 1) {
    target.claimed = true;
  } else {
    pig.reserved.push([target.id, cell]);
  }
  target.pending += SHOT_DAMAGE;
  if (!target.freeShot) {
    pig.ammo -= 1;
  }
  const [sx, sy] = belt.position(state, tray);
  const sz = belt.muzzleHeight(state);
  const [tx, ty] = gridx.cellCenter(state.grid, cell);
  const distance = isqrt((tx - sx) * (tx - sx) + (ty - sy) * (ty - sy) + sz * sz);
  const moves = Math.max(1, -idiv(HIT_RADIUS - distance, SHOT_SPEED));
  const land = state.tick + moves - 1;
  state.shots.push(makeShot(pig.id, target.id, cell, state.tick, land));
  base.emit(state, "shot", { pig: pig.id, target: target.id, cell, land, from: [sx, sy, sz], to: [tx, ty] });
}

// Phase 5: shots arriving this tick land, in firing order. A shot whose target is already gone vanishes without doing
// damage. When the last shot in flight ends the stuck check starts again
// (ProjectilesEvents$$TriggerLastActiveProjectileDestroyed)
export function stepShots(state) {
  const had = state.shots.length > 0;
  const flying = [];
  for (const shot of state.shots) {
    const target = state.grid.targets[shot.target];
    if (target.dead) {
      base.emit(state, "shot_lost", { pig: shot.pig, target: shot.target });
    } else if (shot.land <= state.tick) {
      hit(state, target, SHOT_DAMAGE, shot);
    } else {
      flying.push(shot);
    }
  }
  state.shots = flying;
  if (had && !flying.length) {
    checks.requestStuckCheck(state);
  }
}

// Land damage on a target. A shot carries the cell it hit; damage at a cell frees every pig's reservation of that cell,
// and damage from no particular cell frees them all (the OnDamaged handler ClaimTargetForShooter adds). Cubes are
// damaged by damageCube, other targets by their feature module's onHit
export function hit(state, target, damage, source) {
  if (target.dead) {
    return;
  }
  const cell = source === null ? null : source.cell;
  release(state, target, cell);
  if (source !== null) {
    target.pending = Math.max(0, target.pending - damage);
  }
  if (target.owner === 0) {
    damageCube(state, target, damage, source !== null ? "shot" : "other", cell);
  } else {
    for (const module of base.MODULES) {
      if (module.NUMBER === target.owner) {
        module.onHit(state, target, damage, source);
        break;
      }
    }
  }
  if (target.dead) {
    release(state, target, null);
  }
}

// Free pigs' reservations of a target: of one cell, or every cell when cell is null
export function release(state, target, cell) {
  for (const pig of Object.values(state.pigs)) {
    if (pig.reserved.length) {
      pig.reserved = pig.reserved.filter((r) => r[0] !== target.id || (cell !== null && r[1] !== cell));
    }
  }
}

// A cube loses health; at none left it is gone from the picture and the win check starts again (HitTarget$$Damage,
// RVA 0x544FE18; HitTargetEvents$$TriggerTargetDeath)
export function damageCube(state, cube, damage, cause, cell) {
  chargeUnicorn(state, damage);
  cube.health = Math.max(0, cube.health - damage);
  base.emit(state, "hit", { target: cube.id, cell: cell === null ? -1 : cell, health: cube.health });
  if (cube.health > 0) {
    return;
  }
  cube.dead = true;
  const cells = cube.cells;
  gridx.remove(state.grid, cube);
  state.cubesLeft -= 1;
  const single = cells.length === 1;
  base.emit(state, "cube_died", { cube: cube.id, color: cube.color, cause, single, cell: cells[0] });
  checks.requestWinCheck(state);
}

// Damage to a cube fills the Super Unicorn's bar while the player has it this level, until the bar is full; its own
// hits don't count (MergedShooterSystem$$OnTargetDamaged, RVA 0x518E55C: CanChargeFrom takes any cube and no feature;
// MergedShooterChargeLogic$$AddPixels, RVA 0x514A924, adds the damage only while the bar isn't full)
export function chargeUnicorn(state, damage) {
  const { unicorn } = state;
  if (unicorn.active && !unicorn.running && damage >= 1 && unicorn.charge < unicorn.need) {
    unicorn.charge += damage;
  }
}
