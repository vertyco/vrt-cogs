// Feature 9, the Wall: an obstacle that is never damaged and blocks the pigs' sight until it is removed.
// Every wall is removed when the auto-finisher starts (WallFeatureController -> DetachAllWalls, RVA 0x581F98C, called
// from MapAutoFinisherController$$OnAutoFinisherActivated, RVA 0x58CB6D8) and by the Obstacles revive
// (RemoveAllObstacles). Removing a wall frees its cells at once. common/sim/features/wall.py mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";

export const NUMBER = 9;

// Every wall as a record, in file order, with its body standing on its cells as an obstacle
export function setup(state) {
  const listed = state.level.features.walls;
  if (!listed || !listed.Walls.length) {
    return;
  }
  const { grid } = state;
  const walls = [];
  for (const data of listed.Walls) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const body = gridx.makeTarget(NUMBER, -1, 1, true, false);
    gridx.add(grid, body, cells);
    walls.push({ target: body.id });
  }
  state.features[NUMBER] = { walls };
}

// Take every standing wall off the picture, in file order. Returns how many went
export function removeAll(state, why) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return 0;
  }
  let gone = 0;
  for (const wall of mine.walls) {
    const body = state.grid.targets[wall.target];
    if (body.dead) {
      continue;
    }
    body.dead = true;
    gridx.remove(state.grid, body);
    base.emit(state, "wall_gone", { target: body.id, why });
    gone += 1;
  }
  if (gone) {
    base.emit(state, "walls_removed", { why });
  }
  return gone;
}

// The auto-finisher started: every wall goes
export function onAutofinish(state) {
  removeAll(state, "autofinish");
}

// The Obstacles revive removes every wall. Returns the ticks the revive waits (none)
export function revive(state, name) {
  if (name === "obstacles") {
    removeAll(state, "revive");
  }
  return 0;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.walls.length);
  for (const wall of mine.walls) {
    h = base.mix(h, state.grid.targets[wall.target].dead ? 1 : 0);
  }
  return h;
}
