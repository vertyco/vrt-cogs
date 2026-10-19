// Beds, sleep and wait (sleepWait F4:22858, wakeUpAnim F4:22923, openTimePanel F4:19437, timePanel_btnSetup F4:19470,
// timePanel_sliderSetup F4:19527; int_timePanel, sprite 5934, and the slider, sprite 5933). A bed ("[E] USE BED") in a
// safe house opens the SLEEP panel: a slider picks 0 to 10 hours and the SLEEP button spends them. A bed anywhere else
// says the player cannot sleep there. The beds that count are the ones inside the screen: every room carries an
// abed1 marker, and the ones parked above the screen are not offered.
//
// passHours(h, { sleep }) is the time itself, and the map's travel spends its hours through it too. Each hour the clock
// goes on an hour, health and permanent health come back (both to the same amount) and stamina fills. Sleeping also
// takes sleep need off (10 an hour) and puts hunger on (6 an hour), and counts the hour for "Sleepy". Waiting costs
// neither. The wait for the next rush starts again, the flashlight goes off, and the light follows the new clock on its
// own. The screen then fades to black, the player wakes up at the bed, and the world goes on after five seconds.
import { showLoading } from "./art.js";
import { director } from "./director.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { interact, register } from "./interact.js";
import { light } from "./light.js";
import { canOpenPanel, closePanel, openPanel, panelOpen } from "./panels.js";
import { adjustVital, attributeOf, showHealth, vitalState } from "./player.js";
import { room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

const PANEL = "sleep";
const KIND = "abed";
const PROMPT = "[E] USE BED";
const WAKE_PAUSE = "sleep";
const MAX_HOURS = 10;
// The slider's arrow runs along 0 to 252 px, at y -5, and each tenth of the way is an hour (F4:19535)
const SLIDER = { left: 0, right: 252, y: -5 };
const SLIDER_SHARE = 100;
// Each hour: a tenth of the most health and a fifth of the most stamina, plus what Fitness and Endurance add
const HEALTH_SHARE = 0.1;
const STAMINA_SHARE = 0.2;
const HUNGER_PER_HOUR = 6;
const MINUTES_IN_HOUR = 60;
const HUNGER_PER_MINUTE = 0.1;
// The black-out after SLEEP: a second to fade to black after 0.2 s, the new light and the bed once it is black, and a
// second to fade back after 4 s, when the world goes on (F4:22906-22920)
const FADE_IN = { delay: 0.2, seconds: 1 };
const FADE_OUT = { delay: 4, seconds: 1 };
const MOST_RECORDED = 100;
const NO_SLEEP_DIALOG = {
  heading: "YOU CANNOT SLEEP HERE",
  body: "IT'D BE SUICIDE TO SLEEP\nOUTSIDE OF A SECURE AREA.\n\nFIND A SAFEHOUSE.",
  ok: "OK",
};

let page = null;
// The open panel: { clip, hours, bed }
let view = null;
// The black-out going on: { bed, step, faded, lit, back }
let wake = null;
// Registers fn(key, amount) for each counter sleeping adds to: "sleep" for each hour slept (checkAch F4:22872)
const countListeners = [];
// What was slept or passed, newest last, for checks
const log = [];

export function onSleepCount(fn) {
  countListeners.push(fn);
}

function count(key, amount = 1) {
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function record(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- The time ----------

// Lets hours go by (sleepWait F4:22858, all but the fade). sleep is true for a night's sleep, false for waiting or a
// trip: both heal, only sleep costs sleep need and hunger
export function passHours(hours, { sleep = false } = {}) {
  const who = story.player;
  light.setFlashlight(false);
  // The original reads Fitness raw and Endurance with its hunger penalty (F4:22876)
  const fitness = who.skills.fitness;
  const endurance = attributeOf(who, "endurance");
  const healed = Math.round(who.healthMax * HEALTH_SHARE) + Math.round((fitness + endurance) / 2);
  const rested = Math.round(who.staminaMax * STAMINA_SHARE) + Math.round(fitness + endurance);
  for (let hour = 0; hour < hours; hour += 1) {
    world.time += MINUTES_IN_HOUR;
    if (sleep) {
      count("sleep");
    }
    who.permHealth = Math.min(who.healthMax, who.permHealth + healed);
    who.health = who.permHealth;
    who.stamina = Math.min(who.staminaMax, who.stamina + rested);
  }
  if (sleep) {
    adjustVital("sleep", "decNeed", hours);
    adjustVital("hunger", "incNeed", Math.round(hours * MINUTES_IN_HOUR) * HUNGER_PER_MINUTE);
  }
  showHealth();
  hud.refresh();
  director.restartRushTimer();
  record("pass", { hours, sleep });
}

// ---------- The panel ----------

function timeWords() {
  const hour = world.hour % 12 || 12;
  return `TIME: ${hour}:${String(world.minute).padStart(2, "0")} ${world.hour < 12 ? "AM" : "PM"}`;
}

// How tired the player is, in words and the percent rested. Run & Gun has no tiredness line (spec 2.13)
function tirednessWords() {
  if (story.mode !== "survivor") {
    return "";
  }
  return `${vitalState("sleep").name.toUpperCase()} - ${Math.round(100 - story.player.sleep)}%`;
}

function arrowOf(clip) {
  return clip.child("timeSlide").child("arrow");
}

// The hours the arrow stands at: a tenth of the slider's length is an hour
function hoursAt(x) {
  return Math.round(((x / SLIDER.right) * SLIDER_SHARE) / MAX_HOURS);
}

function build(clip) {
  view.clip = clip;
  hud.hidePlay(true);
  // The art is drawn around its middle, which sits at the stage's middle (openTimePanel F4:19447)
  clip.position.set(page.width / 2, page.height / 2);
  setText(clip.child("time"), timeWords());
  setText(clip.child("tiredness"), tirednessWords());
  clip.child("timeSlide").child("desc").text = "HOURS TO SLEEP: 0";
  record("open", { bed: view.bed.name });
}

function finish() {
  view = null;
  hud.hidePlay(false);
  sound.play("sound_closeInterface");
}

// Opens the sleep panel at a bed. A bed outside a safe house gives the refusal instead. Returns whether it opened
export function openSleep(bed) {
  if (!room.def?.safeHouse) {
    interact.showDialog("noSleepHere", NO_SLEEP_DIALOG);
    record("refused", { bed: bed.name });
    return false;
  }
  if (!canOpenPanel()) {
    return false;
  }
  view = { clip: null, hours: 0, bed };
  openPanel(PANEL, { art: "int_timePanel", setup: build, close: finish });
  sound.play("sound_openInterface");
  return true;
}

// The slider's hours show as the arrow moves
function followSlider() {
  if (!view?.clip) {
    return;
  }
  view.hours = hoursAt(arrowOf(view.clip).x);
  setText(view.clip.child("timeSlide").child("desc"), `HOURS TO SLEEP: ${view.hours}`);
}

// The SLEEP button: the hours pass at once, the panel goes, and the black-out holds the world until the player wakes
function sleepPressed() {
  if (!view?.clip) {
    return;
  }
  const { hours, bed } = view;
  passHours(hours, { sleep: true });
  world.pause(WAKE_PAUSE);
  closePanel();
  wake = { bed, step: 0, faded: false, lit: false, back: false };
  record("sleep", { hours, bed: bed.name });
}

// ---------- The black-out ----------

function seconds(n) {
  return Math.round(n * page.lib.fps);
}

// Fade to black, light the new hour and stand at the bed once it is black, fade back, and go on
function followWake() {
  if (!wake) {
    return;
  }
  wake.step += 1;
  if (!wake.faded && wake.step >= seconds(FADE_IN.delay)) {
    wake.faded = true;
    showLoading(true, FADE_IN.seconds, { linear: true });
  }
  if (!wake.lit && wake.step >= seconds(FADE_IN.delay + FADE_IN.seconds)) {
    wake.lit = true;
    light.refresh();
    world.player.x = wake.bed.x;
    record("wake", { x: wake.bed.x });
  }
  if (!wake.back && wake.step >= seconds(FADE_OUT.delay)) {
    wake.back = true;
    showLoading(false, FADE_OUT.seconds, { linear: true });
  }
  if (wake.step >= seconds(FADE_OUT.delay + FADE_OUT.seconds)) {
    wake = null;
    world.resume(WAKE_PAUSE);
  }
}

// ---------- The art's button setups ----------

export const SLEEP_LOAD_CALLS = {
  // The slider's arrow is dragged along its line
  timePanel_sliderSetup(node) {
    node.setHandler("onPress", () => node.startDrag(true, [SLIDER.left, SLIDER.y, SLIDER.right, SLIDER.y]));
    const drop = () => node.stopDrag();
    node.setHandler("onRelease", drop);
    node.setHandler("onReleaseOutside", drop);
  },
  // EXIT shuts the panel; the button beside the slider spends the hours
  timePanel_btnSetup(node, name) {
    if (name === "exit") {
      node.setHandler("onPress", () => input.swallowPress());
      node.setHandler("onRelease", () => closePanel());
    } else if (name === "sleepWait") {
      node.setHandler("onRelease", sleepPressed);
    }
  },
};

// ---------- The bed in the room ----------

function use(thing) {
  openSleep(thing);
}

// A bed above the screen is a place to read from, not one to lie on
function available(thing) {
  return thing.y > 0;
}

export const sleep = {
  open: openSleep,
  pass: passHours,
  close: closePanel,
  onCount: onSleepCount,
  get isOpen() {
    return panelOpen(PANEL);
  },
  get waking() {
    return wake !== null;
  },
  log,
};

export function initSleep(owner) {
  page = owner;
  register(KIND, { prompt: () => PROMPT, use, available, look: {} });
  world.stage("interface", followSlider);
  world.stage("interface", followWake);
  world.onReset(() => {
    if (view) {
      hud.hidePlay(false);
    }
    view = null;
    wake = null;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const sleepDebug = {
  // Uses the bed with that name in this room as E would, from wherever the player stands
  sleepOpen(name = "abed1") {
    const bed = room.markers[name];
    if (!bed) {
      return null;
    }
    openSleep({ name, x: bed.x, y: bed.y, marker: bed });
    return sleepDebug.sleepState();
  },

  // Puts the slider's arrow at an hour and says what the panel shows
  sleepSlide(hours) {
    arrowOf(view.clip).x = (hours * SLIDER.right * MAX_HOURS) / SLIDER_SHARE;
    followSlider();
    return sleepDebug.sleepState();
  },

  // A press and release on the SLEEP button
  sleepPress() {
    view.clip.child("sleepWait").handlers.onRelease?.();
    return sleepDebug.sleepState();
  },

  // Lets hours go by with no panel and no fade
  sleepPass(hours, asleep = true) {
    passHours(hours, { sleep: asleep });
    return sleepDebug.sleepState();
  },

  // What the panel shows and where the clock, the vitals and the black-out stand; the panel part is null when shut
  sleepState() {
    const who = story.player;
    const clip = view?.clip;
    return {
      panel: clip
        ? {
            hours: view.hours,
            time: clip.child("time").text,
            tiredness: clip.child("tiredness").text,
            desc: clip.child("timeSlide").child("desc").text,
            button: clip.child("sleepWait").child("txt")?.text ?? null,
          }
        : null,
      waking: wake ? wake.step : null,
      paused: world.paused,
      time: world.time,
      day: world.day,
      hour: world.hour,
      minute: world.minute,
      light: light.level(),
      health: who.health,
      permHealth: who.permHealth,
      healthMax: who.healthMax,
      stamina: who.stamina,
      staminaMax: who.staminaMax,
      hunger: who.hunger,
      sleep: who.sleep,
      playerX: world.player?.x ?? null,
      dialog: interact.dialog?.kind ?? null,
    };
  },

  // What was opened, slept and passed so far
  sleepLog() {
    return log.map((each) => ({ ...each }));
  },
};
