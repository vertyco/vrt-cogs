// Feature 12, Ice Blocks: an obstacle that cracks as single-cell cubes die and breaks all at once.
// Every death of a single-cell cube anywhere, of any color, takes 1 off every ice block at once; big cubes don't count
// (PixelIceBlockFeatureController$$OnTargetDeath, RVA 0x56DCC88, which adds 1 to its pending count unless the dead
// target is a big cube and then runs ExecuteIceDamage, RVA 0x56DB658, in the same call; each block takes the whole
// pending count through PixelIceBlockFeature$$Damage, RVA 0x56D5E9C). Shots never hit the ice. A block stands on its
// cells as an obstacle (shots stop at it and the cubes under it can't be hit) until its health reaches 0 and it breaks
// (PixelIceBlockFeature$$OnDamage, RVA 0x56D97D4: a hit with health left plays the hit effect, otherwise the shatter).
// The block is an IRemovablePixelGridObstacle, so the Obstacles revive removes it (MapRescueController
// .<RemoveAllObstacles>d__29 walks every such obstacle). BlockSize is drawing only. common/sim/features/ice_block.py
// mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";

export const NUMBER = 12;

// Every ice block as a record, in file order, with its body standing on its cells as an obstacle
export function setup(state) {
  const listed = state.level.features.pixelIceBlocks;
  if (!listed || !listed.IceBlocks.length) {
    return;
  }
  const { grid } = state;
  const blocks = [];
  for (const data of listed.IceBlocks) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const body = gridx.makeTarget(NUMBER, -1, data.Health, true, false);
    gridx.add(grid, body, cells);
    blocks.push({ target: body.id, size: data.BlockSize, start: data.Health, cells });
  }
  state.features[NUMBER] = { blocks };
}

// A single-cell cube died: every standing block loses 1, and breaks at 0
export function onEvent(state, name, data) {
  if (name !== "cube_died" || !state.features[NUMBER] || !data.single) {
    return;
  }
  for (const block of state.features[NUMBER].blocks) {
    const body = state.grid.targets[block.target];
    if (body.dead) {
      continue;
    }
    body.health -= 1;
    if (body.health > 0) {
      base.emit(state, "ice_hit", { target: body.id, health: body.health });
    } else {
      body.health = 0;
      shatter(state, body, "cubes");
    }
  }
}

// The block is gone from the picture and its cells are free at once
function shatter(state, body, why) {
  body.dead = true;
  gridx.remove(state.grid, body);
  base.emit(state, "ice_gone", { target: body.id, why });
}

// The Obstacles revive breaks every standing block, in file order. Returns the ticks the revive waits (none)
export function revive(state, name) {
  const mine = state.features[NUMBER];
  if (name !== "obstacles" || !mine) {
    return 0;
  }
  for (const block of mine.blocks) {
    const body = state.grid.targets[block.target];
    if (!body.dead) {
      body.health = 0;
      shatter(state, body, "revive");
    }
  }
  return 0;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.blocks.length);
  for (const block of mine.blocks) {
    const body = state.grid.targets[block.target];
    h = base.mix(base.mix(h, body.health), body.dead ? 1 : 0);
  }
  return h;
}
