// The watch view: a friend's level, drawn the same way as the player's own, with no input.
// The bot passes along the friend's LevelStart, then each tap it accepted (`ftap`), each tick the friend's page
// reached (`fat`) and the result (`fover`). This page runs the same simulation from those, half a second (30 ticks)
// behind the newest tick it heard of and never ahead of it, so a network bump never shows. Once the result is in,
// the level runs on to its end.
import * as fx from "./fx.js";
import * as hud from "./hud.js";
import { loadLevel } from "./levels.js";
import { rememberPigs, syncPigs } from "./pigs.js";
import { applyTap, newState, step } from "./sim/core.js";
import { expand } from "./sim/level.js";
import { TICKS_PER_SECOND } from "./sim/numbers.js";

const TICK_MS = 1000 / TICKS_PER_SECOND;
// How far behind the newest tick heard of the view runs
export const BEHIND_TICKS = 30;
// Further behind than this (a hidden tab, a slow phone), the view runs a tick extra each frame to catch up
const CATCH_UP_TICKS = 15;
// Further behind than this, it jumps straight there without drawing the ticks in between
const JUMP_TICKS = 120;
const MAX_FRAME_MS = 250;
// Friends' names longer than this are cut, by whole characters, in the top bar
const NAME_CHARACTERS = 10;
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

// `friend` is {id, name}. `taps` holds every [tick, tap] of the friend's level known so far, oldest first, and `next`
// the first one not yet applied. `newest` is the newest tick heard of, `over` the friend's result once it came.
// `holds` are the reasons the clock waits (a booster's animation, as on the friend's page)
const watch = {
  page: null,
  screens: null,
  friend: null,
  levelStart: null,
  level: null,
  sim: null,
  taps: [],
  next: 0,
  newest: 0,
  over: null,
  loading: 0,
  running: false,
  frame: 0,
  last: 0,
  carry: 0,
  holds: new Set(),
  events: [],
  dirty: true,
  stats: { jumps: 0, rebuilds: 0 },
};

function $(id) {
  return document.getElementById(id);
}

// `page` is game.js's page and `screens.show(name)` shows a screen
export function initWatch(page, screens) {
  Object.assign(watch, { page, screens });
}

export function watching() {
  return watch.friend !== null;
}

export function friend() {
  return watch.friend;
}

// A name cut to NAME_CHARACTERS whole characters, so a flag or a joined emoji is never split
export function shortName(name) {
  const parts = segmenter ? Array.from(segmenter.segment(name), (part) => part.segment) : Array.from(name);
  return parts.length > NAME_CHARACTERS ? `${parts.slice(0, NAME_CHARACTERS - 1).join("")}…` : name;
}

// The clock waits while any reason holds it, like the player's own level does during a booster's animation
export function hold(reason) {
  watch.holds.add(reason);
}

export function release(reason) {
  if (watch.holds.delete(reason) && watch.holds.size === 0) {
    watch.carry = 0;
    watch.last = performance.now();
  }
}

function keepEvents(sim, from, tick) {
  for (let i = from; i < sim.events.length; i++) {
    sim.events[i].t = tick;
    watch.events.push(sim.events[i]);
  }
}

// The friend's Shuffle: their clock waits for the animation, as theirs does
function waitForShuffle() {
  hold("shuffle");
  setTimeout(() => release("shuffle"), fx.SHUFFLE_MS);
}

// The friend's Demolish: the blast lands as the tap applies (their bomb's drop happened on their own screen), and the
// clock waits for its flash
function waitForBomb() {
  hold("bomb");
  setTimeout(() => release("bomb"), fx.BOMB_FLASH_MS);
}

// The friend's Super Shooter: their pig is not replayed up to the wind-up, but the volley is, and the clock waits for it
// as theirs does. `ids` are the cubes it shoots
function waitForSuper(ids) {
  hold("super");
  setTimeout(() => release("super"), watch.page.scene.picture.volleyMs(ids));
}

// The friend's Super Unicorn: it comes in already standing, its run plays, and the clock waits for it as theirs does.
// `shots` are its unicorn_shot events
function waitForUnicorn(shots) {
  const picture = watch.page.scene.picture;
  hold("unicorn");
  setTimeout(() => {
    picture.stopSuper();
    release("unicorn");
  }, picture.unicornMs(shots));
}

// Apply every known tap stamped with the simulation's current tick, keeping their events for the looks
function applyDue(sim, keep) {
  while (watch.next < watch.taps.length && watch.taps[watch.next][0] === sim.tick) {
    const known = sim.events.length;
    const [t, tap] = watch.taps[watch.next];
    const reason = applyTap(sim, tap);
    if (reason !== null) {
      console.warn("Block Blaster: a friend's tap didn't apply here", t, tap, reason);
    }
    watch.next += 1;
    if (keep) {
      keepEvents(sim, known, sim.tick);
      if (reason === null && tap[0] === "shuffle") {
        waitForShuffle();
      }
      if (reason === null && tap[0] === "bomb") {
        waitForBomb();
      }
      if (reason === null && tap[0] === "super") {
        waitForSuper(sim.events.slice(known).find((event) => event.k === "super_shot").ids);
      }
      if (reason === null && tap[0] === "unicorn") {
        waitForUnicorn(sim.events.slice(known).filter((event) => event.k === "unicorn_shot"));
      }
    }
  }
}

// One tick of the friend's level: the taps at this tick, then the step
function tick(sim, keep) {
  applyDue(sim, keep);
  if (sim.over !== null) {
    return;
  }
  if (keep) {
    rememberPigs(sim);
  }
  step(sim);
  if (keep) {
    keepEvents(sim, 0, sim.tick - 1);
  }
}

// The furthest tick the view may show: half a second behind the newest tick heard of, or the level's end once the
// result is in (no more ticks come after it). A result found while simulating tick T leaves the clock at T + 1
function target() {
  return watch.over ? watch.over.tick + 1 : Math.max(0, watch.newest - BEHIND_TICKS);
}

// Run without drawing up to `to`, then put the level on screen afresh
function jump(sim, to) {
  while (sim.tick < to && sim.over === null) {
    tick(sim, false);
  }
  applyDue(sim, false);
  watch.events = [];
  show(sim);
}

// The friend's name over their level number, in the top bar's pill
function pillText(number) {
  const name = document.createElement("b");
  name.className = "watch-name";
  name.textContent = shortName(watch.friend.name);
  const level = document.createElement("small");
  level.className = "watch-level";
  level.textContent = `Level ${number}`;
  $("level-pill-text").replaceChildren(name, level);
}

function show(sim) {
  watch.sim = sim;
  watch.page.sim = sim;
  watch.dirty = true;
  watch.page.scene.showLevel(sim);
  hud.showHud(sim.level, null);
  pillText(sim.level.number);
  hud.frame(sim);
}

// Build the friend's level from its start, with every tap known, up to `to`
function rebuild(to) {
  watch.stats.rebuilds += 1;
  const sim = newState(watch.level, watch.levelStart.seed, watch.page.board, watch.levelStart.unicorn === true);
  watch.next = 0;
  jump(sim, to);
}

// A friend's level from the bot: {n, seed, taps, t}
async function openLevel(levelStart) {
  const token = ++watch.loading;
  const level = expand(await loadLevel(levelStart.n));
  if (token !== watch.loading || !watch.friend) {
    return;
  }
  watch.levelStart = levelStart;
  watch.level = level;
  watch.taps = levelStart.taps.map((entry) => [entry[0], entry[1]]);
  watch.newest = levelStart.t;
  watch.over = null;
  setNote("");
  watch.screens.show("watch");
  rebuild(target());
  watch.carry = 0;
  watch.last = performance.now();
  if (!watch.running) {
    watch.running = true;
    watch.frame = requestAnimationFrame(frame);
  }
}

// The bot's answer to {"watch": id}: the friend's name and level
export function begin(watching) {
  watch.friend = { id: watching.user, name: watching.name };
  return openLevel(watching.level);
}

// The friend started another level
export function newLevel(levelStart) {
  if (watch.friend) {
    openLevel(levelStart).catch((e) => console.warn("Block Blaster: couldn't open the friend's level", e));
  }
}

// One tap the bot accepted from the friend. A tap stamped before the tick on screen (a very late message) means the
// level is built again with it
export function friendTap(entry) {
  if (!watch.sim) {
    return;
  }
  const [t, tap] = entry;
  watch.taps.push([t, tap]);
  watch.newest = Math.max(watch.newest, t);
  if (watch.over && t >= watch.over.tick) {
    // A revive: the level goes on from where it stopped
    watch.over = null;
    setNote("");
  }
  if (t < watch.sim.tick) {
    rebuild(watch.sim.tick);
  }
}

export function friendAt(t) {
  watch.newest = Math.max(watch.newest, t);
}

// The friend's level ended: the view runs on to that tick, then says how it went
export function friendOver(over) {
  watch.over = over;
  watch.newest = Math.max(watch.newest, over.tick + 1);
}

// Leave the watch view. The clock stops and the friend's level is dropped
export function stop() {
  watch.loading += 1;
  watch.running = false;
  cancelAnimationFrame(watch.frame);
  watch.friend = null;
  watch.sim = null;
  watch.over = null;
  watch.holds.clear();
  setNote("");
  if (watch.page && watch.page.screen === "watch") {
    watch.page.sim = null;
  }
}

function setNote(text) {
  const node = $("watch-note");
  if (!node || node.textContent === text) {
    return;
  }
  node.textContent = text;
  node.hidden = text === "";
}

function overNote(sim) {
  if (!watch.over || sim.over === null) {
    return;
  }
  const name = watch.friend.name;
  const n = sim.level.number;
  setNote(watch.over.result === "won" ? `${name} cleared level ${n}!` : `${name} lost level ${n}.`);
}

// Run the ticks this frame pays for, never past the target. Returns how far the clock is toward the next tick
function advance(sim, now) {
  const elapsed = Math.min(now - watch.last, MAX_FRAME_MS);
  watch.last = now;
  const to = target();
  if (watch.holds.size > 0) {
    watch.carry = 0;
    return 1;
  }
  if (to - sim.tick > JUMP_TICKS) {
    watch.stats.jumps += 1;
    jump(sim, to - BEHIND_TICKS);
    return 1;
  }
  applyDue(sim, true);
  watch.carry += elapsed;
  let due = Math.floor(watch.carry / TICK_MS);
  watch.carry -= due * TICK_MS;
  if (to - sim.tick > CATCH_UP_TICKS) {
    due += 1;
  }
  while (due > 0 && sim.tick < to && sim.over === null) {
    tick(sim, true);
    due -= 1;
    watch.dirty = true;
  }
  if (sim.tick >= to || sim.over !== null) {
    // Waiting for the friend: the view stands at a whole tick
    watch.carry = 0;
    applyDue(sim, true);
    return 1;
  }
  return watch.carry / TICK_MS;
}

function frame(now) {
  if (!watch.running) {
    return;
  }
  watch.frame = requestAnimationFrame(frame);
  const sim = watch.sim;
  if (!sim) {
    return;
  }
  const before = sim.tick;
  const alpha = advance(sim, now);
  const current = watch.sim;
  overNote(current);
  if (current.tick === before && !watch.dirty && watch.events.length === 0 && !fx.animating()) {
    return;
  }
  const events = watch.events;
  watch.events = [];
  fx.onEvents(events, current);
  hud.frame(current);
  fx.frame(alpha, current);
  syncPigs(current, alpha);
  watch.page.scene.render(((current.tick - 1 + alpha) * TICK_MS) / 1000);
  watch.dirty = alpha < 1;
}

// What checks read through window.blockblaster.watch
export const debug = { state: watch, stats: watch.stats, target };
