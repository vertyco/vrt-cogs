// Feature 10, the Egg Box: eggs of different colors sharing one box, every egg a target of its own.
// Each egg is a target of its color with health Count, standing on every cell of the box (EggBoxFeature$$AttachInternal,
// RVA 0x566430C; EggBoxEggInstance$$get_OccupiedPoints, RVA 0x5662DD8). So at a box cell first in line a pig can hit
// any living egg of its color, and the eggs take hits in parallel, in no order. While any egg lives, the box's cells are
// solid for every color, since each living egg is a solid hit target on them. The box is gone when the last egg breaks
// (OnEggDamaged, RVA 0x5661B84), which frees its cells. An egg whose Count is 0 is hidden at once: it starts dead.
// Cells outside the picture are left out. common/sim/features/egg_box.py mirrors this file.
import * as base from "../base.js";
import * as checks from "../checks.js";
import * as gridx from "../grid.js";

export const NUMBER = 10;

// Every box as a record, in file order, with one target per egg standing on all of the box's cells
export function setup(state) {
  const listed = state.level.features.eggBoxes;
  if (!listed || !listed.EggBoxes.length) {
    return;
  }
  const { grid } = state;
  const boxes = [];
  for (const data of listed.EggBoxes) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const eggs = [];
    for (const egg of data.Eggs) {
      const target = gridx.makeTarget(NUMBER, egg.Material, egg.Count);
      if (egg.Count > 0) {
        gridx.add(grid, target, cells);
      } else {
        target.dead = true;
        gridx.add(grid, target, []);
      }
      eggs.push(target.id);
    }
    boxes.push({ cells, eggs, gone: !eggs.some((id) => grid.targets[id].cells.length > 0) });
  }
  state.features[NUMBER] = { boxes };
}

// A shot lands on an egg: it loses health, and at 0 it breaks and leaves the box; the last egg takes the box with it
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
  const box = state.features[NUMBER].boxes.find((b) => b.eggs.includes(target.id));
  if (!box.gone && box.eggs.every((id) => state.grid.targets[id].dead)) {
    box.gone = true;
    base.emit(state, "egg_box_gone", { cells: [...box.cells] });
  }
  checks.requestWinCheck(state);
}

// The hits the living eggs of this color still take
export function remainingHits(state, color) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return 0;
  }
  let total = 0;
  for (const box of mine.boxes) {
    for (const eggId of box.eggs) {
      const target = state.grid.targets[eggId];
      if (!target.dead && target.color === color) {
        total += target.health;
      }
    }
  }
  return total;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.boxes.length);
  for (const box of mine.boxes) {
    h = base.mix(h, box.eggs.length);
    for (const eggId of box.eggs) {
      const target = state.grid.targets[eggId];
      h = base.mix(base.mix(h, target.health), target.dead ? 1 : 0);
    }
  }
  return h;
}
