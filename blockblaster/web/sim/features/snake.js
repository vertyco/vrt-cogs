// Feature 8, the Snake: one target of its color over a body that shortens toward its nest as it is shot.
// The body is the snake path's cross-sections (spline.build over the nest and its corner squares), nest first; the
// snake covers sections 0..index and is hit on any of them. It starts on every section (SnakeFeature$$AttachInternal,
// RVA 0x57C190C, sets the index to the last one). Each hit takes 1 health and recomputes the index at once
// (OnHitTargetDamaged, RVA 0x57BCD64, through UpdateSplineClipPercent, RVA 0x57B93B4): the spline point at
// t = clamp(1 - health / Count, 0.0001, 0.9999), worked out in float32 (get_HealthPercent, RVA 0x57BAF2C, a float
// division; GetCurrentClipPercent, RVA 0x57BAEF4), names the cell whose section plus one is the new index
// (UpdateCurrentObstaclePointIndex, RVA 0x57BBD1C); a point on no section leaves the index as it was. At health 0 the
// snake is gone, nest included. common/sim/features/snake.py mirrors this file.
// The index for every health is worked out once at setup, so the state holds whole numbers only and the path's
// samples stay out of it.
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";
import { f32 } from "../mathx.js";
import * as spline from "../spline.js";

export const NUMBER = 8;

// The clamp's bounds are float32 constants in the original
const LOW = f32(0.0001);
const HIGH = f32(0.9999);

// The nest, then each corner square, as lists of [x, y] cells
export function squaresOf(data) {
  const squares = [data.MainGridPoints.map((point) => [point.X, point.Y])];
  for (const square of data.SnakeGridPoints) {
    squares.push(square.GridPoints.map((point) => [point.X, point.Y]));
  }
  return squares;
}

// 1 - health / Count in float32, clamped to 0.0001..0.9999 (the spline point the body's far end is cut at)
export function clipPercent(health, count) {
  let percent = f32(1.0 - f32(f32(health) / f32(count)));
  if (percent > HIGH) {
    percent = HIGH;
  }
  if (percent < LOW) {
    percent = LOW;
  }
  return percent;
}

// Every snake as a record, in file order, with its target on every section of its body
export function setup(state) {
  const listed = state.level.features.snakes;
  if (!listed || !listed.Snakes.length) {
    return;
  }
  const { grid } = state;
  const snakes = [];
  for (const data of listed.Snakes) {
    const path = spline.build(squaresOf(data), spline.STRAIGHT_DISTANCE);
    const count = data.Count;
    const stops = [];
    // stops[health]: the index spline.indexAt gives at that health (-1: keep the index)
    for (let health = 0; health <= count; health++) {
      stops.push(spline.indexAt(path, clipPercent(health, count)));
    }
    const snake = {
      target: -1,
      sections: spline.crossSections(path, [grid.width, grid.height]),
      stops,
      count,
      index: path.sections.length - 1,
    };
    const target = gridx.makeTarget(NUMBER, data.Material, count);
    gridx.add(grid, target, cellsOf(snake));
    snake.target = target.id;
    snakes.push(snake);
  }
  state.features[NUMBER] = { snakes };
}

// Sections 0..index, nest first, each cell once
export function cellsOf(snake) {
  const cells = [];
  const seen = new Set();
  for (const section of snake.sections.slice(0, snake.index + 1)) {
    for (const cell of section) {
      if (!seen.has(cell)) {
        seen.add(cell);
        cells.push(cell);
      }
    }
  }
  return cells;
}

// A shot lands on any cell of the snake: it loses health, the body is recomputed at once, and at 0 it is gone
export function onHit(state, target, damage, source) {
  const snake = state.features[NUMBER].snakes.find((s) => s.target === target.id);
  target.health = Math.max(0, target.health - damage);
  const cell = source === null ? -1 : source.cell;
  base.emit(state, "hit", { target: target.id, cell, health: target.health });
  const index = snake.stops[target.health];
  if (index >= 0 && index !== snake.index) {
    snake.index = index;
    base.emit(state, "snake_shrink", { target: target.id, index, health: target.health });
    if (target.health > 0) {
      gridx.move(state.grid, target, cellsOf(snake));
    }
  }
  if (target.health > 0) {
    return;
  }
  target.dead = true;
  gridx.remove(state.grid, target);
  base.emit(state, "target_died", { target: target.id, owner: NUMBER });
  checks.requestWinCheck(state);
}

// The hits the living snakes of this color still take
export function remainingHits(state, color) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return 0;
  }
  let total = 0;
  for (const snake of mine.snakes) {
    const target = state.grid.targets[snake.target];
    if (!target.dead && target.color === color) {
      total += target.health;
    }
  }
  return total;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.snakes.length);
  for (const snake of mine.snakes) {
    const target = state.grid.targets[snake.target];
    h = base.mix(base.mix(base.mix(h, target.health), snake.index), target.dead ? 1 : 0);
  }
  return h;
}
