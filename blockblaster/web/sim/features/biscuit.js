// Feature 16, the Biscuit: a block that any pig color can hit, standing over cubes until it is shot to pieces.
// It is a "match all" target (BiscuitFeature$$Awake, RVA 0x55A298C: the hit target takes every material) with one pool
// of LayerCount x LayerHealth hits (SetCapacity, RVA 0x55A41A0); the layers are drawing only. It is an obstacle and a
// hit target at once, so the obstacle filter keeps it: a pig whose line meets it shoots the biscuit and cannot reach
// the cubes under or beyond it. At 0 it is gone and its cells are free (OnHitTargetDamaged, RVA 0x55A77AC, which only
// redraws the layers). It is no IRemovablePixelGridObstacle, so the Obstacles revive leaves it. Its hits belong to no
// color, so no color's remaining hits count them. common/sim/features/biscuit.py mirrors this file.
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";

export const NUMBER = 16;

// Every biscuit as a record, in file order, with its body standing on its cells
export function setup(state) {
  const listed = state.level.features.biscuits;
  if (!listed || !listed.Biscuits.length) {
    return;
  }
  const { grid } = state;
  const biscuits = [];
  for (const data of listed.Biscuits) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const total = data.LayerCount * data.LayerHealth;
    const body = gridx.makeTarget(NUMBER, -1, total, true, true);
    body.matchAll = true;
    body.freeShot = true;
    gridx.add(grid, body, cells);
    biscuits.push({ target: body.id, layers: data.LayerCount, layerHealth: data.LayerHealth, total });
  }
  state.features[NUMBER] = { biscuits };
}

// A shot lands on a biscuit: the pool loses health, and at 0 the biscuit is gone and its cells are free
export function onHit(state, target, damage, source) {
  target.health = Math.max(0, target.health - damage);
  const cell = source === null ? -1 : source.cell;
  base.emit(state, "hit", { target: target.id, cell, health: target.health });
  if (target.health > 0) {
    return;
  }
  target.dead = true;
  gridx.remove(state.grid, target);
  base.emit(state, "target_died", { target: target.id, owner: NUMBER });
  base.emit(state, "biscuit_gone", { target: target.id });
  checks.requestWinCheck(state);
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  let out = base.mix(h, mine.biscuits.length);
  for (const biscuit of mine.biscuits) {
    const body = state.grid.targets[biscuit.target];
    out = base.mix(base.mix(out, body.health), body.dead ? 1 : 0);
  }
  return out;
}
