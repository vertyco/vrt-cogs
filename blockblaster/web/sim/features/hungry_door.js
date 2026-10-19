// Feature 15, Hungry Doors: an obstacle over a patch of cubes that is fed by the cubes of its own color dying.
// Every death of a single-cell cube of the door's color anywhere takes 1 off every door of that color that isn't
// already doomed (PixelColorDoorFeatureController$$OnTargetDeath, RVA 0x56CF8C0, skips big cubes; DamageDoors, RVA
// 0x56CF064, skips a door whose pending damage is already lethal, PixelColorDoorFeature$$IsLethalDamage, RVA 0x56CA31C).
// The damage is pending at once and lands when a copy of the cube finishes its jump into the door, CUBE_FLY_IN ticks
// later (DamageDoor, RVA 0x56CA870, with AddPendingDamage, RVA 0x56CA270, and the callback <DamageDoor>b__0 calling
// Damage). When the health reaches 0 the door opens (gea, RVA 0x56CA480, then OpenDoor, RVA 0x56CA3D0) and its cells are
// free at once. Until the open animation ends the stuck check waits, and so it does while any cube is still on its way
// in. The door implements IRemovablePixelGridObstacle, so the Obstacles revive opens it too (MapRescueController
// .<RemoveAllObstacles>d__29). Shots never hit a door. common/sim/features/hungry_door.py mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";
import { CUBE_FLY_IN, DOOR_OPEN } from "../numbers.js";

export const NUMBER = 15;

// Every door as a record, in file order, with its body standing on its cells as an obstacle
export function setup(state) {
  const listed = state.level.features.pixelColorDoors;
  if (!listed || !listed.Doors.length) {
    return;
  }
  const { grid } = state;
  const doors = [];
  for (const data of listed.Doors) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const body = gridx.makeTarget(NUMBER, -1, data.Health, true, false);
    gridx.add(grid, body, cells);
    doors.push({ target: body.id, color: data.Material, start: data.Health, cells, pending: 0, opening: false });
  }
  state.features[NUMBER] = { doors };
}

// A single-cell cube died: every door of its color that isn't doomed gets 1 damage on its way
export function onEvent(state, name, data) {
  const mine = state.features[NUMBER];
  if (!mine || name !== "cube_died" || !data.single) {
    return;
  }
  mine.doors.forEach((door, index) => {
    const body = state.grid.targets[door.target];
    if (door.color !== data.color || body.dead || body.health - door.pending <= 0) {
      return;
    }
    door.pending += 1;
    base.schedule(state, CUBE_FLY_IN, "door_land", index);
    base.emit(state, "door_feed", { door: index, cell: data.cell, color: data.color });
  });
}

// Timer: the cube copy lands in the door, which loses 1 health and opens at 0
export function doorLand(state, index) {
  const door = state.features[NUMBER].doors[index];
  const body = state.grid.targets[door.target];
  door.pending = Math.max(0, door.pending - 1);
  if (body.dead) {
    return;
  }
  body.health -= 1;
  base.emit(state, "door_hit", { door: index, target: body.id, health: body.health });
  if (body.health <= 0) {
    openDoor(state, index, "cubes");
  }
}

// Timer: the open animation is over
export function doorDone(state, index) {
  state.features[NUMBER].doors[index].opening = false;
}

// The door is gone from the picture and its cells are free at once. The hit event makes keys and Surprise Pixels look at
// the picture again
function openDoor(state, index, why) {
  const door = state.features[NUMBER].doors[index];
  const body = state.grid.targets[door.target];
  body.health = 0;
  body.dead = true;
  gridx.remove(state.grid, body);
  door.opening = true;
  base.schedule(state, DOOR_OPEN, "door_done", index);
  base.emit(state, "door_open", { door: index, target: body.id, why });
  base.emit(state, "hit", { target: body.id, cell: -1, health: 0 });
}

base.registerTimer("door_land", base.PHASE_FEATURES, doorLand);
base.registerTimer("door_done", base.PHASE_FEATURES, doorDone);

// Cubes on their way into a door, or a door still opening, hold the stuck check
export function busy(state) {
  const mine = state.features[NUMBER];
  return Boolean(mine) && mine.doors.some((door) => door.pending > 0 || door.opening);
}

// The Obstacles revive opens every standing door, in file order. Returns the ticks the revive waits (none)
export function revive(state, name) {
  const mine = state.features[NUMBER];
  if (name !== "obstacles" || !mine) {
    return 0;
  }
  mine.doors.forEach((door, index) => {
    if (!state.grid.targets[door.target].dead) {
      openDoor(state, index, "revive");
    }
  });
  return 0;
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.doors.length);
  for (const door of mine.doors) {
    const body = state.grid.targets[door.target];
    h = base.mix(base.mix(h, body.health), body.dead ? 1 : 0);
    h = base.mix(base.mix(h, door.pending), door.opening ? 1 : 0);
  }
  return h;
}
