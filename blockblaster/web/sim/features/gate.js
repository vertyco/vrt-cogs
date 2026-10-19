// Feature 5, the Gate: one target of its color over a head and a bar that shortens as it is shot.
// The target's health starts at Count and covers the head's cells and the bar's. The bar leaves the head's side that
// faces Direction, as wide as that side, starting at the next cell; its layers are counted from the head, and the far
// layer goes first when the bar shortens (GateFeature$$UpdateSplineGridPoints, RVA 0x566E8B4, called at once from the
// damage handler through UpdateSplineClipPercent, RVA 0x566DBA0). The layer count is the ceiling of
// clamp(health / Count, 0, 1) x Length, worked out in float32 at each step (GateFeature$$get_HealthPercent, RVA
// 0x566E46C, a float division; then a float multiply and a round up). A cell outside the picture is left out; the
// original keeps it in a set no cell ever matches. At health 0 the gate is gone. common/sim/features/gate.py mirrors
// this file.
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";
import { f32 } from "../mathx.js";

export const NUMBER = 5;

// FacingDirection (0 Left, 1 Up, 2 Right, 3 Down) as the step one layer takes
const STEPS = [
  [-1, 0],
  [0, 1],
  [1, 0],
  [0, -1],
];

// The bar's layers at this health: float32 division, clamp to 0..1, float32 multiply by Length, round up
export function barLayers(health, count, length) {
  let percent = f32(f32(health) / f32(count));
  percent = Math.min(percent, 1.0);
  if (percent < 0.0) {
    percent = 0.0;
  }
  return Math.ceil(f32(percent * f32(length)));
}

// The head's points on the side the bar leaves from (GateFeature$$GetSplineStartSideValue, RVA 0x566CC64: the smallest
// x for Left, the largest y for Up, the largest x for Right, the smallest y for Down)
export function startSide(points, direction) {
  if (direction === 0) {
    const edge = Math.min(...points.map(([x]) => x));
    return points.filter(([x]) => x === edge);
  }
  if (direction === 2) {
    const edge = Math.max(...points.map(([x]) => x));
    return points.filter(([x]) => x === edge);
  }
  if (direction === 1) {
    const edge = Math.max(...points.map(([, y]) => y));
    return points.filter(([, y]) => y === edge);
  }
  const edge = Math.min(...points.map(([, y]) => y));
  return points.filter(([, y]) => y === edge);
}

function inside(grid, x, y) {
  return x >= 0 && x < grid.width && y >= 0 && y < grid.height;
}

// Every gate as a record, in file order, with its target standing on the head and the full bar
export function setup(state) {
  const listed = state.level.features.gates;
  if (!listed || !listed.Gates.length) {
    return;
  }
  const { grid } = state;
  const gates = [];
  for (const data of listed.Gates) {
    const head = data.GridPoints.map((point) => [point.X, point.Y]);
    const direction = data.Direction;
    const [stepX, stepY] = STEPS[direction];
    const points = startSide(head, direction);
    const layers = [];
    for (let layer = 1; layer <= data.Length; layer++) {
      layers.push(
        points
          .filter(([x, y]) => inside(grid, x + stepX * layer, y + stepY * layer))
          .map(([x, y]) => gridx.cellOf(grid, x + stepX * layer, y + stepY * layer)),
      );
    }
    const gate = {
      target: -1,
      head: head.filter(([x, y]) => inside(grid, x, y)).map(([x, y]) => gridx.cellOf(grid, x, y)),
      points: points.map(([x, y]) => [x, y]),
      layers,
      direction,
      length: data.Length,
      count: data.Count,
      bar: data.Length,
    };
    const target = gridx.makeTarget(NUMBER, data.Material, data.Count);
    gridx.add(grid, target, cellsOf(gate));
    gate.target = target.id;
    gates.push(gate);
  }
  state.features[NUMBER] = { gates };
}

// The head's cells, then the bar's layers nearest the head first
export function cellsOf(gate) {
  const cells = [...gate.head];
  for (const layer of gate.layers.slice(0, gate.bar)) {
    cells.push(...layer);
  }
  return cells;
}

// A shot lands on any cell of the gate: it loses health, the bar is recomputed at once, and at 0 the gate is gone
export function onHit(state, target, damage, source) {
  const gate = state.features[NUMBER].gates.find((g) => g.target === target.id);
  target.health = Math.max(0, target.health - damage);
  const cell = source === null ? -1 : source.cell;
  base.emit(state, "hit", { target: target.id, cell, health: target.health });
  const bar = barLayers(target.health, gate.count, gate.length);
  if (bar !== gate.bar) {
    gate.bar = bar;
    base.emit(state, "gate_pull", { target: target.id, bar, health: target.health });
    if (target.health > 0) {
      gridx.move(state.grid, target, cellsOf(gate));
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

// The hits the living gates of this color still take
export function remainingHits(state, color) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return 0;
  }
  let total = 0;
  for (const gate of mine.gates) {
    const target = state.grid.targets[gate.target];
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
  h = base.mix(h, mine.gates.length);
  for (const gate of mine.gates) {
    const target = state.grid.targets[gate.target];
    h = base.mix(base.mix(base.mix(h, target.health), gate.bar), target.dead ? 1 : 0);
  }
  return h;
}
