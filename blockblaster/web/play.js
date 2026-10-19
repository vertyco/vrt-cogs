// The level loop: the page's clock, taps by tick, the heartbeat to the bot, and catching up with the bot's copy.
// The page runs the same simulation as the bot at 60 ticks a second with a fixed step, so a tap acts the frame it is
// pressed. Each tap is stamped with the tick it landed on and sent; the bot replays its own copy to that tick and
// answers with its checksum. When the two ever disagree, the page rebuilds from the bot's seed and taps.
// The clock may run slower than real time (a pause), never faster: the bot refuses taps from ahead of its own clock.
import { loadLevel } from "./levels.js";
import * as fx from "./fx.js";
import * as hud from "./hud.js";
import { hitTest, pickTest, rememberPigs, syncPigs } from "./pigs.js";
import { applyTap, checksum, newState, runTo, step } from "./sim/core.js";
import { expand } from "./sim/level.js";
import { TICKS_PER_SECOND } from "./sim/numbers.js";

const TICK_MS = 1000 / TICKS_PER_SECOND;
// {"at": tick} goes to the bot after this many ticks of play. Often enough that a friend watching, who runs half a
// second behind the newest tick the bot passed on, never has to wait for the next one
const HEARTBEAT_TICKS = 10;
// A frame that took longer than this (a stalled tab, a slow phone) only moves the clock this far, so the page falls
// behind instead of racing to catch up
const MAX_FRAME_MS = 250;

// `levelStart` is the bot's LevelStart for the level on screen and `level` its expanded level. `pending` holds the
// taps sent and not yet answered, oldest first, each {t, tap, sum}; a tap the page lost in a rebuild keeps sum null.
// `holds` are the reasons the clock waits (settings, tutorial, booster, hidden, focus)
const play = {
  page: null,
  send: null,
  screens: null,
  levelStart: null,
  level: null,
  loading: 0,
  running: false,
  frame: 0,
  last: 0,
  carry: 0,
  holds: new Set(),
  pending: [],
  lastAt: 0,
  endedSent: false,
  resyncing: false,
  dirty: true,
  events: [],
  tickHandlers: [],
  eventHandlers: [],
  refuseHandlers: [],
  shownHandlers: [],
  sentHandlers: [],
  stats: { rebuilds: 0, mismatches: 0, refused: 0, sent: 0 },
};

// `page` is game.js's page, `send` sends one message to the bot, and `screens.show(name)` shows a screen
export function initPlay(page, send, screens) {
  Object.assign(play, { page, send, screens });
  const canvas = document.getElementById("scene");
  canvas.addEventListener("pointerdown", press);
  window.addEventListener("blur", () => hold("focus"));
  window.addEventListener("focus", () => release("focus"));
  document.addEventListener("visibilitychange", () => (document.hidden ? hold("hidden") : release("hidden")));
}

// Called before every tick with the simulation, so a caller can act at an exact tick
export function onTick(handler) {
  play.tickHandlers.push(handler);
}

// Called once per drawn frame with the events of every tick and tap since the last frame
export function onEvents(handler) {
  play.eventHandlers.push(handler);
}

// Called with (tap, reason) when a press lands on something that can't act now (belt full, locked pig)
export function onTapRefused(handler) {
  play.refuseHandlers.push(handler);
}

// Called with (sim, levelStart) each time a level is put on screen: a fresh start, a resume or a rebuild. A handler that
// opens something over the level holds the clock from here, before the first tick of the new clock runs
export function onLevelShown(handler) {
  play.shownHandlers.push(handler);
}

// Called after each tap the page sends to the bot
export function onTapSent(handler) {
  play.sentHandlers.push(handler);
}

// Replay a LevelStart's taps from tick 0, then any still unanswered taps of ours that come after them, then run on
// to `target`. Nothing is drawn meanwhile
function replay(levelStart, target) {
  const sim = newState(play.level, levelStart.seed, play.page.board, levelStart.unicorn === true);
  for (const [t, tap] of levelStart.taps) {
    runTo(sim, t);
    const reason = applyTap(sim, tap);
    if (reason !== null) {
      console.warn("Block Blaster: the bot's tap didn't apply here", t, tap, reason);
    }
  }
  for (const entry of play.pending) {
    entry.sum = null;
    if (entry.t < sim.tick || sim.over !== null) {
      continue;
    }
    runTo(sim, entry.t);
    if (applyTap(sim, entry.tap) === null) {
      entry.sum = checksum(sim);
    }
  }
  runTo(sim, target);
  return sim;
}

function show(sim) {
  play.page.sim = sim;
  play.events = [];
  play.lastAt = sim.tick;
  play.endedSent = false;
  play.resyncing = false;
  play.dirty = true;
  play.page.scene.showLevel(sim);
  hud.showHud(sim.level, play.page.progress);
  hud.frame(sim);
  play.shownHandlers.forEach((handler) => handler(sim, play.levelStart));
}

// A level from the bot: load it, catch up to the bot's tick, and start the clock
export async function startLevel(levelStart) {
  const token = ++play.loading;
  const level = expand(await loadLevel(levelStart.n));
  if (token !== play.loading) {
    return;
  }
  play.levelStart = levelStart;
  play.level = level;
  play.pending = [];
  play.screens.show("level");
  show(replay(levelStart, levelStart.t));
  play.carry = 0;
  play.last = performance.now();
  if (!play.running) {
    play.running = true;
    play.frame = requestAnimationFrame(frame);
  }
}

// The bot's state replaces ours: its taps from tick 0, then our taps still on their way, up to whichever clock is
// further on, so a resync never moves the level backwards on screen
export function rebuild(levelStart) {
  const same = play.levelStart && play.page.sim && levelStart.n === play.levelStart.n;
  if (!same || levelStart.seed !== play.levelStart.seed) {
    startLevel(levelStart).catch((e) => console.warn("Block Blaster: couldn't start the level", e));
    return;
  }
  play.stats.rebuilds += 1;
  play.levelStart = levelStart;
  show(replay(levelStart, Math.max(levelStart.t, play.page.sim.tick)));
}

// After a dropped link: the bot answers none of the taps sent before it, so its copy simply replaces ours
export function resume(levelStart) {
  play.pending = [];
  rebuild(levelStart);
}

// The level is left: the clock stops and nothing more is sent
export function stopLevel() {
  play.loading += 1;
  play.running = false;
  cancelAnimationFrame(play.frame);
  play.levelStart = null;
  play.pending = [];
  play.page.sim = null;
  if (play.page.scene) {
    play.page.scene.looks.clear();
  }
}

export function playing() {
  return play.running && play.page.sim !== null;
}

// The clock waits while any reason holds it
export function hold(reason) {
  play.holds.add(reason);
}

export function release(reason) {
  if (play.holds.delete(reason) && play.holds.size === 0) {
    play.carry = 0;
    play.last = performance.now();
  }
}

// Keep the simulation's events from index `from` on, each stamped with the tick it happened in, for the looks to start
// at the right moment
function keepEvents(sim, from, tick) {
  for (let i = from; i < sim.events.length; i++) {
    sim.events[i].t = tick;
    play.events.push(sim.events[i]);
  }
}

// A tap at the current tick: applied here at once and sent. Returns the reason it can't act, or null
export function tap(what) {
  const sim = play.page.sim;
  if (!sim) {
    return "no level";
  }
  const known = sim.events.length;
  const reason = applyTap(sim, what);
  // The tap's events would be cleared by the next tick before they are drawn. The ones already there came from the
  // last tick and were kept when it ran
  keepEvents(sim, known, sim.tick);
  play.dirty = true;
  if (reason !== null) {
    play.stats.refused += 1;
    if (reason === "belt full") {
      hud.flashCounter();
    }
    play.refuseHandlers.forEach((handler) => handler(what, reason));
    return reason;
  }
  play.pending.push({ t: sim.tick, tap: what, sum: checksum(sim) });
  play.stats.sent += 1;
  play.send({ tap: what, t: sim.tick });
  play.sentHandlers.forEach((handler) => handler(what));
  return null;
}

// Pigs act on press, not release. The press is checked against the boxes worked out once per resize. While the Hand
// waits for its pick, only a queue pig counts (any pig in a queue), and while the Demolish waits only a cell of the
// picture counts; every other press does nothing. Nothing acts while the Shuffle or the bomb plays
function press(event) {
  if (play.page.screen !== "level" || !play.page.sim || play.page.sim.over !== null || hud.busy()) {
    return;
  }
  const box = event.currentTarget.getBoundingClientRect();
  if (hud.pickingCell()) {
    const cell = play.page.scene.picture.cellAt(event.clientX - box.left, event.clientY - box.top);
    if (cell) {
      event.preventDefault();
      hud.pickCell(cell);
    }
    return;
  }
  if (hud.picking()) {
    const at = pickTest(event.clientX - box.left, event.clientY - box.top);
    if (at) {
      event.preventDefault();
      hud.pickPig(at);
    }
    return;
  }
  const what = hitTest(event.clientX - box.left, event.clientY - box.top);
  if (what) {
    event.preventDefault();
    tap(what);
  }
}

// The bot's answer to our oldest unanswered tap. A checksum that differs means the two copies split: ask for the
// bot's state (a start of the level in play resumes it)
export function answered(t, sum) {
  const entry = play.pending.shift();
  if (entry && entry.t === t && entry.sum === sum) {
    return;
  }
  play.stats.mismatches += 1;
  console.warn("Block Blaster: the bot's copy of the level differs", { t, sum, ours: entry });
  if (!play.resyncing && play.levelStart) {
    play.resyncing = true;
    play.send({ start: play.levelStart.n });
  }
}

// The bot took the revive's coins and applied the revive at `tick`, its copy's checksum now `sum`. The page applies the
// same tap at the same tick, which the bot never sends back. False when the two don't agree: the bot's state is then
// asked for and replaces ours
export function revived(tick, sum) {
  const sim = play.page.sim;
  if (sim && sim.over !== null && sim.tick === tick) {
    const known = sim.events.length;
    if (applyTap(sim, ["revive"]) === null && checksum(sim) === sum) {
      keepEvents(sim, known, sim.tick);
      play.endedSent = false;
      play.lastAt = sim.tick;
      play.dirty = true;
      return true;
    }
  }
  play.stats.mismatches += 1;
  console.warn("Block Blaster: the revive didn't match the bot's copy", { tick, sum, ours: sim && sim.tick });
  if (!play.resyncing && play.levelStart) {
    play.resyncing = true;
    play.send({ start: play.levelStart.n });
  }
  return false;
}

// The bot refused our oldest unanswered tap and sent its state
export function refused(reason, levelStart) {
  play.pending.shift();
  console.warn("Block Blaster: the bot refused a tap", reason);
  rebuild(levelStart);
}

function heartbeat(sim) {
  if (sim.over !== null) {
    if (!play.endedSent) {
      play.endedSent = true;
      play.send({ ended: sim.tick });
    }
    return;
  }
  if (sim.tick - play.lastAt >= HEARTBEAT_TICKS) {
    play.lastAt = sim.tick;
    play.send({ at: sim.tick });
  }
}

// Run the ticks this frame's time pays for. Returns how far the clock is toward the next tick (0 to 1)
function advance(sim, now) {
  const elapsed = Math.min(now - play.last, MAX_FRAME_MS);
  play.last = now;
  if (play.holds.size > 0 || sim.over !== null) {
    play.carry = 0;
    return 1;
  }
  play.carry += elapsed;
  while (play.carry >= TICK_MS && sim.over === null) {
    play.carry -= TICK_MS;
    play.tickHandlers.forEach((handler) => handler(sim));
    rememberPigs(sim);
    step(sim);
    keepEvents(sim, 0, sim.tick - 1);
    play.dirty = true;
    heartbeat(sim);
  }
  return sim.over === null ? play.carry / TICK_MS : 1;
}

// The looks (fx.js) start from the events; other modules hang off onEvents
function drawEvents(sim, events) {
  fx.onEvents(events, sim);
  hud.frame(sim);
  play.eventHandlers.forEach((handler) => handler(events, sim));
}

function frame(now) {
  if (!play.running) {
    return;
  }
  play.frame = requestAnimationFrame(frame);
  const sim = play.page.sim;
  if (!sim) {
    return;
  }
  const alpha = advance(sim, now);
  const moving = play.holds.size === 0 && sim.over === null;
  if (!moving && !play.dirty && !fx.animating()) {
    return;
  }
  const events = play.events;
  play.events = [];
  drawEvents(sim, events);
  fx.frame(alpha, sim);
  syncPigs(sim, alpha);
  play.page.scene.render(((sim.tick - 1 + alpha) * TICK_MS) / 1000);
  play.dirty = false;
}

// What checks read through window.blockblaster.play
export const debug = { state: play, stats: play.stats };
