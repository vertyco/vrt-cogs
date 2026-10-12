// The batch clock. 20 times a second a batch applies the strokes collected since the last one, then runs a few
// steps, spread across the 50 ms until the next batch. A private world makes its own batches here ("local"); a shared
// world plays the batches the bot sends ("shared"), so every screen applies the same strokes at the same step.
import { applyStroke, EL, STROKE, stepWorld, W } from "./sim/index.js";

export const BATCH_MS = 50;
// Further behind than this (a hidden page, a long stall) and the clock starts again from now instead of catching up
const LATE_MS = 250;
const PRIVATE_PLAYER = "0";
// A shared world holds one batch in hand to ride out network wobble. A batch held this long with none behind it (a
// paused world only gets batches when someone paints) starts anyway
const HOLD_MS = 100;
// With more than this many batches waiting, extra whole batches run each frame within EXTRA_MS
const IN_HAND = 2;
const EXTRA_MS = 8;
// 2 seconds of batches waiting: the screen asks for a fresh snapshot instead of running fast for a long time
const BEHIND = 40;
// Batches a `world` message brought with it run back to back, this long per frame
const CATCH_UP_MS = 30;

/** Steps in batch number b at speed s: 0 paused, 1 quarter, 2 half, 3 normal, 4 double */
export function stepsFor(s, b) {
  return [0, b % 2 === 0 ? 1 : 0, b % 2 === 0 ? 2 : 1, 3, 6][s] ?? 0;
}

/**
 * On December 24 and 25 (the page's local date) it snows: two flakes at random places on row 2, as PAINT strokes
 * so a shared world stays in step. Any other day: no strokes.
 */
export function snowStrokes(date = new Date()) {
  if (date.getMonth() !== 11 || (date.getDate() !== 24 && date.getDate() !== 25)) {
    return [];
  }
  const flake = () => [STROKE.PAINT, EL.snow, 1, 0, 0, 0, 1 + Math.floor(Math.random() * (W - 2)), 2];
  return [flake(), flake()];
}

/** Whether a stroke is one of those flakes, so a save can tell the world's own snow from what a player painted */
export function isSnowStroke(stroke) {
  return stroke[0] === STROKE.PAINT && stroke[1] === EL.snow && stroke[2] === 1 && stroke[7] === 2;
}

export class Runner {
  constructor(world) {
    this.world = world;
    this.mode = "local";
    this.speed = 3;
    // The number the next batch made here will get
    this.batch = 0;
    // The last batch whose steps have all run
    this.done = -1;
    this.queued = [];
    // Shared world: batches from the bot as { batch, at } in batch order, and the number of the last batch started.
    // The bot numbers its batches with no gaps, so only batch `ran + 1` may start next
    this.inbox = [];
    this.ran = -1;
    // Waiting for a `world` message: nothing runs, live batches pile up for when it comes
    this.loading = false;
    // Batches up to this number came with a `world` message and run as fast as the frame budget allows
    this.catchUpTo = null;
    this.current = null;
    this.startStep = 0;
    this.left = 0;
    this.startedAt = 0;
    this.clock = null;
    this.stepOnce = false;
    // What the steps reported (explosions, sizzles, sparks) since sound last asked
    this.heard = { boom: 0, sizzle: 0, zap: 0, bolt: 0 };
    this.listeners = [];
    this.doneListeners = [];
    this.behindListeners = [];
    document.addEventListener("visibilitychange", () => {
      this.clock = null;
    });
  }

  stepsFor(s, b) {
    return stepsFor(s, b);
  }

  // One step of the world, keeping its events: each step starts them from zero, and a batch can hold several steps
  step() {
    stepWorld(this.world);
    const { events } = this.world;
    this.heard.boom += events.boom;
    this.heard.sizzle += events.sizzle;
    this.heard.zap += events.zap;
    this.heard.bolt += events.bolt;
  }

  /** The events of every step since the last call, added up */
  takeHeard() {
    const heard = this.heard;
    this.heard = { boom: 0, sizzle: 0, zap: 0, bolt: 0 };
    return heard;
  }

  /** A stroke for the next batch (private world) */
  queueStroke(stroke) {
    this.queued.push(stroke);
  }

  /** One step while paused: the next batch runs a single step */
  once() {
    this.stepOnce = true;
  }

  /** A batch from the bot (shared world). One already started, or already waiting, is a repeat and is ignored */
  push(batch) {
    const b = batch[0];
    if (b <= this.ran) {
      return;
    }
    let at = this.inbox.length;
    while (at > 0 && this.inbox[at - 1].batch[0] >= b) {
      at -= 1;
    }
    if (this.inbox[at]?.batch[0] === b) {
      return;
    }
    this.inbox.splice(at, 0, { batch, at: performance.now() });
  }

  /** Calls fn(batch) each time a batch starts, after its strokes are applied */
  onBatch(fn) {
    this.listeners.push(fn);
  }

  /** Calls fn(batch, stepBefore) each time a batch's last step has run; stepBefore is the world's step at its start */
  onBatchDone(fn) {
    this.doneListeners.push(fn);
  }

  /** Calls fn() when a shared world fell 2 seconds behind and dropped its queue; a `world` message must follow */
  onBehind(fn) {
    this.behindListeners.push(fn);
  }

  /**
   * Switches to the bot's clock, with batch `after` as the last one run. Strokes still waiting for a private batch
   * are applied first, so nothing painted is lost
   */
  enterShared(after) {
    this.finish();
    for (const stroke of this.queued) {
      applyStroke(this.world, PRIVATE_PLAYER, stroke, 1);
    }
    this.queued = [];
    this.mode = "shared";
    this.inbox = [];
    this.done = after;
    this.ran = after;
    this.loading = false;
    this.catchUpTo = null;
  }

  /** Back to the page's own clock */
  leaveShared() {
    this.finish();
    this.mode = "local";
    this.inbox = [];
    this.loading = false;
    this.catchUpTo = null;
    this.clock = null;
  }

  /**
   * Stops running batches until resync(); batches that arrive meanwhile wait. With `after`, the world on its way
   * stands after that batch, so every later batch is kept, even one numbered at or below a batch this screen ran in
   * another world (its own, or a shared world before a restart)
   */
  hold(after = null) {
    this.loading = true;
    if (after !== null) {
      this.ran = after;
    }
  }

  /**
   * The world now stands after batch `b` (a snapshot was just loaded, or the page's own world is already there).
   * `batches` follow it and run quickly; live batches that came in meanwhile run after them, repeats dropped
   */
  resync(b, batches) {
    const live = this.inbox;
    this.inbox = [];
    this.current = null;
    this.left = 0;
    this.done = b;
    this.ran = b;
    for (const batch of batches) {
      this.push(batch);
    }
    this.catchUpTo = this.inbox.at(-1)?.batch[0] ?? null;
    for (const item of live) {
      this.push(item.batch);
    }
    this.loading = false;
  }

  /**
   * Swaps in another world (undo, a loaded world). The strokes waiting for the next batch and the steps left in the
   * batch in progress belonged to the old world, so they go with it.
   */
  replaceWorld(world) {
    this.world = world;
    this.queued = [];
    this.left = 0;
    if (this.current !== null) {
      this.done = this.current[0];
      this.current = null;
    }
  }

  /** Runs whatever is left of the batch in progress, and returns the last batch that has fully run */
  boundary() {
    this.finish();
    return this.done;
  }

  finish() {
    while (this.left > 0) {
      this.step();
      this.left -= 1;
    }
    if (this.current !== null) {
      this.complete();
    }
  }

  complete() {
    const batch = this.current;
    this.done = batch[0];
    this.current = null;
    for (const fn of this.doneListeners) {
      fn(batch, this.startStep);
    }
  }

  start(batch, now) {
    this.finish();
    const [, n, strokes] = batch;
    for (const [player, stroke] of strokes) {
      applyStroke(this.world, player, stroke, Math.max(1, n));
    }
    this.current = batch;
    this.ran = batch[0];
    this.left = n;
    this.startedAt = now;
    this.startStep = this.world.step;
    for (const fn of this.listeners) {
      fn(batch);
    }
  }

  // The batch due now in a private world, or null when a paused world has nothing to do
  makeBatch() {
    let n = this.stepsFor(this.speed, this.batch);
    if (this.stepOnce) {
      this.stepOnce = false;
      n = this.speed === 0 ? 1 : n;
    }
    if (n === 0 && this.queued.length === 0) {
      if (this.speed !== 0) {
        this.batch += 1;
      }
      return null;
    }
    const snow = n > 0 ? snowStrokes() : [];
    const strokes = [...this.queued, ...snow].map((stroke) => [PRIVATE_PLAYER, stroke]);
    this.queued = [];
    const batch = [this.batch, n, strokes];
    this.batch += 1;
    return batch;
  }

  tickLocal(now) {
    if (this.clock === null || now - this.clock > LATE_MS) {
      this.clock = now - BATCH_MS;
    }
    while (now - this.clock >= BATCH_MS) {
      this.clock += BATCH_MS;
      const batch = this.makeBatch();
      if (batch !== null) {
        this.start(batch, this.clock);
      }
    }
  }

  // Whether the next batch in line can start: it follows the last one started with no gap
  nextReady() {
    return this.inbox.length > 0 && this.inbox[0].batch[0] === this.ran + 1;
  }

  catchingUp() {
    return this.catchUpTo !== null && this.nextReady() && this.inbox[0].batch[0] <= this.catchUpTo;
  }

  // Starts batch k once batch k + 1 is in, runs extra batches when several wait, and gives up when far behind
  tickShared(now) {
    if (this.loading) {
      return;
    }
    if (!this.catchingUp()) {
      this.catchUpTo = null;
      if (this.inbox.length >= BEHIND) {
        this.inbox = [];
        this.loading = true;
        this.behindListeners.forEach((fn) => fn());
        return;
      }
    }
    const budget = this.catchUpTo === null ? EXTRA_MS : CATCH_UP_MS;
    const begin = performance.now();
    while (
      this.nextReady() &&
      (this.inbox.length > IN_HAND || this.catchingUp()) &&
      performance.now() - begin < budget
    ) {
      this.start(this.inbox.shift().batch, now);
      this.finish();
    }
    const head = this.inbox[0];
    if (this.nextReady() && (this.inbox.length > 1 || (this.left === 0 && now - head.at >= HOLD_MS))) {
      this.start(this.inbox.shift().batch, now);
    }
  }

  /** Called every animation frame with its timestamp: makes or starts batches and runs the steps due by now */
  frame(now) {
    if (this.mode === "local") {
      this.tickLocal(now);
    } else {
      this.tickShared(now);
    }
    if (this.current === null) {
      return;
    }
    const n = this.current[1];
    const due = Math.min(n, Math.ceil((n * (now - this.startedAt)) / BATCH_MS));
    while (n - this.left < due) {
      this.step();
      this.left -= 1;
    }
    if (this.left === 0) {
      this.complete();
    }
  }
}
