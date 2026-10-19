// The world's clock. One fixed step runs 30 times a second, and every system hangs its part on it by registering a
// function under the name of the place it holds in the original's loop (F4:36437-36476). The world advances only while
// nothing has paused it; while it is paused only interface work runs, and every timer stops with the game, so a
// cutscene line, a spawn or a fade never fires behind a panel.
import { data } from "./data.js";
import { input } from "./input.js";

// The places in the original's loop, in the order it runs them. "interface" is the keys, the dialog's typewriter,
// the lockpick pins and tweens; "help" is the hint check; both run even while paused (always). quick, slow and medium
// are the timed loops: they run every few steps (their counts come from the original's constants) and only while the
// world is unpaused, except help, whose own count never stops
const STAGES = [
  { name: "interface", always: true },
  { name: "clock" },
  { name: "camera" },
  { name: "controls" },
  { name: "aim" },
  { name: "gravity" },
  { name: "collisions" },
  { name: "shots" },
  { name: "melee" },
  { name: "companions" },
  { name: "zombies" },
  { name: "humans" },
  { name: "quick", count: "quickEFcountMax" },
  { name: "slow", count: "slowEFcountMax" },
  { name: "medium", count: "mediumEFcountMax" },
  { name: "help", count: "slowEFConstantcountMax", always: true },
];
// Used until the converted constants load
const DEFAULT_COUNTS = { quickEFcountMax: 5, slowEFcountMax: 30, mediumEFcountMax: 15, slowEFConstantcountMax: 30 };
const DEFAULT_TIME_SCALE = 50;
// A new story starts at the first minute of day 1 (12:00 AM)
export const START_TIME = 1440;
// Where a new story begins: Jefferson Ave, in Pinedale, at the original's start x (F4:27398)
export const START_ROOM = "l16_s1_b0_f0_r1";
export const START_X = 858;
const MINUTES_IN_DAY = 1440;
const MINUTES_IN_HOUR = 60;

const stages = new Map(STAGES.map((stage) => [stage.name, { ...stage, entries: [], left: 0 }]));
const minuteListeners = [];
const resetListeners = [];
let timers = [];
let timerCount = 0;
// A function that threw is reported on its first failure and then once in a while, not 30 times a second
const failures = new Map();

function guard(fn, ...args) {
  try {
    fn(...args);
  } catch (e) {
    const count = (failures.get(fn) ?? 0) + 1;
    failures.set(fn, count);
    if (count === 1 || count % 300 === 0) {
      console.warn(`Union City: a step function failed (${count} times)`, e);
    }
  }
}

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULT_COUNTS[name];
}

export const world = {
  // The original's game.state: "unpaused", or "paused" while any reason holds it
  state: "unpaused",
  // Steps taken while unpaused
  frame: 0,
  // Game minutes since day 0. A new story starts at 1440
  time: START_TIME,
  // Steps into the current game minute (the original's timeCounter)
  sub: 0,
  // True while a story is being played. The step does nothing otherwise
  active: false,
  // Why the world is paused, by name. It runs only while this is empty
  reasons: new Set(),
  room: null,
  player: null,
  zombies: [],
  humans: [],
  companions: [],
  npcs: [],
  shots: [],
  drops: [],
  effects: [],
  // Set by the rooms: enterRoom(id, arrival), so a check can drop the player anywhere
  enter: null,

  get paused() {
    return this.reasons.size > 0;
  },

  // The day number: day 1 begins at the story's start
  get day() {
    return Math.floor(this.time / MINUTES_IN_DAY);
  },

  // Game minutes into the day
  get minuteOfDay() {
    return this.time % MINUTES_IN_DAY;
  },

  // How many timers are waiting (for checks)
  get pendingTimers() {
    return timers.length;
  },

  get hour() {
    return Math.floor(this.minuteOfDay / MINUTES_IN_HOUR);
  },

  get minute() {
    return this.minuteOfDay % MINUTES_IN_HOUR;
  },

  // Hangs fn on a place in the loop. { whilePaused: true } also runs it while the world is paused. Returns a function
  // that takes it off again
  stage(name, fn, { whilePaused = false } = {}) {
    const place = stages.get(name);
    if (!place) {
      throw new Error(`Union City: no step stage called ${name}`);
    }
    if (whilePaused && place.count && !place.always) {
      throw new Error(`Union City: the ${name} loop never runs while paused`);
    }
    const entry = { fn, whilePaused };
    place.entries.push(entry);
    return () => {
      place.entries = place.entries.filter((each) => each !== entry);
    };
  },

  // fn(time) runs at the start of each game minute, after the clock moved (vitals, lighting)
  onMinute(fn) {
    minuteListeners.push(fn);
  },

  // fn runs whenever a story begins or a save loads, after the lists are emptied (the memory of what a system keeps
  // between rooms starts fresh)
  onReset(fn) {
    resetListeners.push(fn);
  },

  // The player's trigger lets go as the world stops (pauseGame F4:25188), so a gun held firing into a panel does not
  // fire on once it closes, and a weapon equipped in the backpack shows in the hands at once
  pause(reason) {
    this.reasons.add(reason);
    this.state = "paused";
    if (this.player) {
      this.player.firing = false;
    }
    input.holdStill(true);
  },

  resume(reason) {
    this.reasons.delete(reason);
    this.state = this.reasons.size ? "paused" : "unpaused";
    input.holdStill(this.reasons.size > 0);
  },

  // fn runs once after that many unpaused steps. { room: true } drops it when the player leaves the room. Returns
  // { cancel() }
  later(frames, fn, { room = false } = {}) {
    return addTimer(frames, fn, room, 0);
  },

  // fn runs every that many unpaused steps until cancelled
  every(frames, fn, { room = false } = {}) {
    return addTimer(frames, fn, room, Math.max(1, Math.round(frames)));
  },

  // The player left the room: its timers go
  leaveRoom() {
    for (const timer of timers) {
      timer.dead ||= timer.room;
    }
    timers = timers.filter((timer) => !timer.dead);
  },

  // A story begins or a save loads: the clock, the pauses, the timers and the lists start fresh
  reset() {
    this.frame = 0;
    this.time = START_TIME;
    this.sub = 0;
    this.reasons.clear();
    this.state = "unpaused";
    input.holdStill(false);
    timers = [];
    failures.clear();
    for (const place of stages.values()) {
      place.left = 0;
    }
    this.room = null;
    this.player = null;
    for (const list of [this.zombies, this.humans, this.companions, this.npcs, this.shots, this.drops, this.effects]) {
      list.length = 0;
    }
    for (const fn of resetListeners) {
      guard(fn);
    }
  },

  start() {
    this.active = true;
  },

  stop() {
    this.active = false;
  },

  // One step of the original's loop. force runs it as if unpaused (a check pauses the world, then takes steps by hand)
  step(force = false) {
    if (!this.active && !force) {
      // A screen that reads keys still gets its one-step flags cleared
      input.endStep();
      return;
    }
    const running = force || this.reasons.size === 0;
    if (running) {
      this.frame += 1;
      fireTimers();
    }
    for (const place of stages.values()) {
      runStage(place, running);
    }
    input.endStep();
  },
};

function addTimer(frames, fn, room, repeat) {
  const timer = {
    id: timerCount,
    due: world.frame + Math.max(0, Math.round(frames) || 0),
    fn,
    room,
    repeat,
    dead: false,
    cancel() {
      this.dead = true;
    },
  };
  timerCount += 1;
  timers.push(timer);
  return timer;
}

// Runs what has come due, in the order it was due and then set. A timer set while this runs waits for the next step
function fireTimers() {
  const due = timers.filter((timer) => !timer.dead && timer.due <= world.frame);
  due.sort((a, b) => a.due - b.due || a.id - b.id);
  for (const timer of due) {
    if (timer.dead) {
      continue;
    }
    if (timer.repeat) {
      timer.due += timer.repeat;
    } else {
      timer.dead = true;
    }
    guard(timer.fn);
  }
  timers = timers.filter((timer) => !timer.dead);
}

function runStage(place, running) {
  if (!running && !place.always && !place.entries.some((entry) => entry.whilePaused)) {
    return;
  }
  if (place.count) {
    // A timed loop counts steps and runs when its count is used up; it starts at 0, so it runs on its first step. The
    // loops that stop with the world never get here paused, and the hint check counts every step
    place.left -= 1;
    if (place.left > 0) {
      return;
    }
    place.left = constant(place.count);
  }
  if (place.name === "clock" && running) {
    guard(tickClock);
  }
  for (const entry of place.entries) {
    if (running || place.always || entry.whilePaused) {
      guard(entry.fn);
    }
  }
}

// A game minute passes every timeScale steps (F4:22783)
function tickClock() {
  world.sub += 1;
  if (world.sub < (data.actors?.constants?.timeScale ?? DEFAULT_TIME_SCALE)) {
    return;
  }
  world.sub = 0;
  world.time += 1;
  for (const fn of minuteListeners) {
    guard(fn, world.time);
  }
}
