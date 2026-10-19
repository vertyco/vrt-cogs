// Feature 11, the Pig Pipe: a queue entry that holds more pigs and lets one out for each pig that leaves ahead of it.
// The pipe entry can't be tapped and never goes on the belt. It remembers the index it started at in its queue
// (ShooterPipeFeature$$AttachInternal, RVA 0x57A5ADC). When pigs leave its queue from in front of that index it releases
// min(pigs that left, pigs inside) pigs at once, each inserted at start + k - released (OnShootersExitingQueue, RVA
// 0x57A48CC, whose FindAll predicate <OnShootersExitingQueue>b__22_0 is "same queue and index < start"; SpawnShooter, RVA
// 0x57A3980), so one pig leaving puts the new pig right in front of the pipe and the pipe never moves forward while it
// has pigs. When the last pig is out the entry vanishes and the queue closes up (RemoveSelf, RVA 0x57A42F4).
// The pigs inside are pigs of the level from the start, held where no rule reaches them (addPigs makes them before any
// other module sets up, since Connected groups, Surprise pigs, hammers and Frozen pigs may list them). They are not on
// the map for the stuck check (spec O4), but they are in the shooter list the auto-finisher counts (ShooterProvider keeps
// nested shooters in its list and filters them with IsShooterNested). common/sim/features/pig_pipe.py mirrors this file.
import * as base from "../base.js";
import * as places from "../places.js";

export const NUMBER = 11;

// Every pig inside a pipe, held, in the order the pipes list them
export function addPigs(state) {
  const listed = state.level.features.ShooterPipes;
  if (!listed) {
    return;
  }
  for (const data of listed.Pipes) {
    for (const shooter of data.Queue.shooters) {
      state.pigs[shooter.id] = base.makePig(shooter.id, shooter.material, shooter.ammo, "held");
    }
  }
}

// Each pipe entry made untappable and disabled, with the queue and index it starts at
export function setup(state) {
  const listed = state.level.features.ShooterPipes;
  if (!listed) {
    return;
  }
  const pipes = [];
  for (const data of listed.Pipes) {
    const entry = data.ShooterId;
    const queue = state.queues.findIndex((ids) => ids.includes(entry));
    if (queue < 0) {
      continue;
    }
    state.pigs[entry].tags.push("disabled", "untappable");
    pipes.push({
      pig: entry,
      queue,
      start: state.queues[queue].indexOf(entry),
      inside: data.Queue.shooters.map((shooter) => shooter.id),
      gone: false,
    });
  }
  state.features[NUMBER] = { pipes };
}

// Let min(left, inside) pigs out, each into the queue at start + k - released. With none inside the entry vanishes at
// once and the queue closes up
function letOut(state, pipe, left) {
  const count = Math.min(left, pipe.inside.length);
  const queue = state.queues[pipe.queue];
  for (let k = 0; k < count; k++) {
    const pigId = pipe.inside.shift();
    const index = pipe.start + k - count;
    state.pigs[pigId].place = "queue";
    queue.splice(index, 0, pigId);
    base.emit(state, "pipe_release", { pipe: pipe.pig, pig: pigId, queue: pipe.queue, index });
  }
  base.emit(state, "queue_changed", {});
  if (!pipe.inside.length) {
    pipe.gone = true;
    places.vanish(state, state.pigs[pipe.pig], "pipe");
  }
}

// Pigs left a queue: every pipe in it counts those that stood in front of its starting index
export function onEvent(state, name, data) {
  const mine = state.features[NUMBER];
  if (!mine || name !== "pigs_exit_queue") {
    return;
  }
  for (const pipe of mine.pipes) {
    if (pipe.gone || !pipe.inside.length) {
      continue;
    }
    let left = 0;
    data.queues.forEach((queue, at) => {
      if (queue === pipe.queue && data.indices[at] < pipe.start) {
        left += 1;
      }
    });
    if (left > 0) {
      letOut(state, pipe, left);
    }
  }
}

export function checksum(state, h) {
  const mine = state.features[NUMBER];
  if (!mine) {
    return h;
  }
  h = base.mix(h, mine.pipes.length);
  for (const pipe of mine.pipes) {
    h = base.mix(base.mix(h, pipe.gone ? 1 : 0), pipe.inside.length);
    for (const pigId of pipe.inside) {
      h = base.mix(h, pigId);
    }
  }
  return h;
}
