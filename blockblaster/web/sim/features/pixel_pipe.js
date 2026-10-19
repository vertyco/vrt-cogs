// Feature 6, the Pixel Pipe: a body on the picture that refills cubes from a queue of color groups.
// The body is an obstacle that is never damaged and stays when the pipe is empty. Its front group is the first with
// cubes left; the original keeps a queue and moves to the next group the moment the count reaches 0
// (PixelPipeFeature$$GetMaterialFromCurrentGroup, RVA 0x5754344, then UpdateState, RVA 0x57532E0).
// Refill on death: when a single-cell cube dies on a cell no pipe covers, the first pipe in file order that isn't busy
// and whose front group has that color puts a new cube of that color into the dead cube's cell at once and counts down
// (PixelPipeFeatureController$$TryToSpawnPixel, RVA 0x575EFA4; SpawnPixel, RVA 0x575BBBC).
// Refill when a color runs out: right after each refill on death, a pipe checks its front color
// (TryToSpawnAdditionalPixels, RVA 0x575DE80). With no single-cell cube of that color left on the picture it turns busy
// and pushes cubes into the first Count cells that held that color in the level file (pixels order, GetSpawnPoints RVA
// 0x575D4E4), the first at once and then one every PIXEL_PIPE_REFILL ticks; after the last it is free again and checks
// once more (PixelPipeFeature.<AutoSpawn>d__73$$MoveNext, RVA 0x575CD14). A run never skips a cell that is already
// taken; the original doesn't either. Every level lists at least one file cell for each group's color, so the
// original's fallback to random empty cells never runs.
// The original pauses refills only while the Super Unicorn runs (the controller's spawnPaused is the "Merged Shooter Is
// In Use" flag), and when that run ends every pipe that isn't busy checks its front color (Update, RVA 0x575E3FC, calls
// SpawnMissingPixels on that edge only). Nothing else pauses them. common/sim/features/pixel_pipe.py mirrors this file.
import * as base from "../base.js";
import * as gridx from "../grid.js";
import { PIXEL_PIPE_REFILL } from "../numbers.js";

export const NUMBER = 6;

// Every pipe as a record, in file order, with its body standing on its cells as an obstacle
export function setup(state) {
  const listed = state.level.features.pixelPipes;
  if (!listed || !listed.Pipes.length) {
    return;
  }
  const { grid } = state;
  const pipes = [];
  for (const data of listed.Pipes) {
    const cells = data.GridPoints.filter(
      (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
    ).map((point) => gridx.cellOf(grid, point.X, point.Y));
    const body = gridx.makeTarget(NUMBER, -1, 1, true, false);
    gridx.add(grid, body, cells);
    pipes.push({
      target: body.id,
      cells,
      groups: data.Queue.map((group) => [group.Material, group.Count]),
      busy: false,
      points: [], // the cells of the run in progress
      next: 0, // the next of them to fill
    });
  }
  state.features[NUMBER] = { pipes };
}

// The [color, count] group the pipe is giving from, or null once it is empty
export function front(pipe) {
  for (const group of pipe.groups) {
    if (group[1] > 0) {
      return group;
    }
  }
  return null;
}

// The cell is under a pipe (PixelPipeFeatureController$$IsOnAnyPipe, RVA 0x575DCF4)
export function underPipe(state, cell) {
  return state.features[NUMBER].pipes.some((pipe) => pipe.cells.includes(cell));
}

// A single-cell cube died: the first free pipe giving its color fills its cell again. Not while the Super Unicorn runs
export function onEvent(state, name, data) {
  if (name !== "cube_died" || !state.features[NUMBER] || !data.single || underPipe(state, data.cell)) {
    return;
  }
  if (state.unicorn.running) {
    return;
  }
  const { pipes } = state.features[NUMBER];
  for (let index = 0; index < pipes.length; index++) {
    const pipe = pipes[index];
    let group = front(pipe);
    if (pipe.busy || group === null || group[0] !== data.color) {
      continue;
    }
    spawn(state, index, data.cell);
    group = front(pipe);
    // A pipe still giving the color it just placed has a cube of it on the picture, so only a new group can be missing
    if (group !== null && group[0] !== data.color) {
      topUp(state, index);
    }
    return;
  }
}

// The pipe's front group gives one cube into the cell, in the grid at once (the jump there is a look)
export function spawn(state, index, cell) {
  const pipe = state.features[NUMBER].pipes[index];
  const group = front(pipe);
  const color = group[0];
  group[1] -= 1;
  const cube = gridx.add(state.grid, gridx.makeTarget(0, color, 1), [cell]);
  // The new cube counts as one more the level has had, so the cleared share stays destroyed over all
  state.cubesStart += 1;
  state.cubesLeft += 1;
  base.emit(state, "pipe_spawn", { pipe: index, cube: cube.id, cell, color });
}

// Some single-cell cube of this color is on the picture (PixelGridController$$GetPixelCountByMaterial with the
// controller's one-cell filter)
export function singlesLeft(state, color) {
  for (const target of state.grid.targets) {
    if (target.owner === 0 && target.color === color && target.cells.length === 1 && !target.dead) {
      return true;
    }
  }
  return false;
}

// The first count cells holding this color in the level file, in its pixels order
export function spawnPoints(state, color, count) {
  const { grid } = state;
  const cells = [];
  for (const [x, y, cubeColor] of state.level.cubes) {
    if (cubeColor === color) {
      cells.push(gridx.cellOf(grid, x, y));
    }
  }
  return cells.slice(0, count);
}

// With no single-cell cube of the front color left, start a run into that color's file cells
export function topUp(state, index) {
  const pipe = state.features[NUMBER].pipes[index];
  const group = front(pipe);
  if (group === null || singlesLeft(state, group[0])) {
    return;
  }
  const points = spawnPoints(state, group[0], group[1]);
  if (!points.length) {
    return;
  }
  pipe.busy = true;
  pipe.points = points;
  pipe.next = 0;
  runStep(state, index);
}

// Timer too: the run fills its next cell; after the last the pipe is free and checks its front color again. The run's
// waits are UniTask waits resumed at PlayerLoopTiming.Update, so its later steps land at the start of a tick
export function runStep(state, index) {
  const pipe = state.features[NUMBER].pipes[index];
  const cell = pipe.points[pipe.next];
  pipe.next += 1;
  spawn(state, index, cell);
  if (pipe.next < pipe.points.length) {
    base.schedule(state, PIXEL_PIPE_REFILL, "pipe_run", index);
    return;
  }
  pipe.busy = false;
  pipe.points = [];
  pipe.next = 0;
  topUp(state, index);
}

base.registerTimer("pipe_run", base.PHASE_TAPS, runStep);

// The Super Unicorn's run ended: every pipe that isn't busy checks its front color (Update, RVA 0x575E3FC, calls
// SpawnMissingPixels on the frame the pause ends)
export function unicornDone(state) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return;
  }
  mine.pipes.forEach((pipe, index) => {
    if (!pipe.busy) {
      topUp(state, index);
    }
  });
}

// The cubes of this color still in the pipe's groups (PixelPipeFeature$$CountPixels)
export function colorLeft(pipe, color) {
  let total = 0;
  for (const [groupColor, count] of pipe.groups) {
    if (groupColor === color) {
      total += count;
    }
  }
  return total;
}

// For the Super Unicorn: [pipe index, cells, tier, rank, hits] for every pipe still holding cubes of this color. Each
// pipe is one target per color whose health is that count (PixelPipeDrainer$$CollectTargets, RVA 0x5752A28), in the
// reserve tier 4 with no rank (MergedShooterFeatureTargetOrder$$IsPixelReserve)
export function unicornReserves(state, color) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return [];
  }
  const found = [];
  mine.pipes.forEach((pipe, index) => {
    const left = colorLeft(pipe, color);
    if (left >= 1) {
      found.push([index, [...pipe.cells], 4, 0, left]);
    }
  });
  return found;
}

export function unicornReserveLeft(state, index, color) {
  return colorLeft(state.features[NUMBER].pipes[index], color);
}

// A Super Unicorn shot at the pipe's queue: the first group holding the color gives one cube, placed on the first of the
// pipe's cells with no cube (the first cell when all have one) for the shot to break (PixelPipeFeature$$DrainPixel, RVA
// 0x57506DC; TryTakePixel, RVA 0x57558B4; PixelPipeDrainer$$PopPixel, RVA 0x5752420; TryFindFreePoint, RVA
// 0x5751384). null when the color ran out
export function unicornPop(state, index, color) {
  const pipe = state.features[NUMBER].pipes[index];
  const group = pipe.groups.find((g) => g[1] > 0 && g[0] === color);
  if (!group || !pipe.cells.length) {
    return null;
  }
  group[1] -= 1;
  const { grid } = state;
  const free = pipe.cells.find((c) => !gridx.at(grid, c).some((t) => t.owner === 0));
  const cell = free === undefined ? pipe.cells[0] : free;
  const cube = gridx.add(grid, gridx.makeTarget(0, color, 1), [cell]);
  state.cubesStart += 1;
  state.cubesLeft += 1;
  base.emit(state, "pipe_pop", { pipe: index, cube: cube.id, cell, color });
  return cube;
}

// The cubes of this color the pipes still hold
export function remainingHits(state, color) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return 0;
  }
  let total = 0;
  for (const pipe of mine.pipes) {
    for (const [groupColor, count] of pipe.groups) {
      if (groupColor === color) {
        total += count;
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
  h = base.mix(h, mine.pipes.length);
  for (const pipe of mine.pipes) {
    h = base.mix(base.mix(base.mix(h, pipe.busy ? 1 : 0), pipe.next), pipe.points.length);
    for (const cell of pipe.points) {
      h = base.mix(h, cell);
    }
    for (const [, count] of pipe.groups) {
      h = base.mix(h, count);
    }
  }
  return h;
}
