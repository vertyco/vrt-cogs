// The help hints: the bar near the bottom of the stage that says "USE THE [A] AND [D] KEYS TO MOVE" and the others,
// each until the player does the thing (showHelp F4:20518, checkHelp F4:20440, sprite 5516). The art holds every
// hint as a frame of one clip; the page sets the key letters on its key boxes. On a touch screen the key wording is
// replaced by touch wording drawn in the same font on the same bar.
//
// A hint shows 1.5 s after it is asked for. When the player does the thing it holds 2.5 s and fades over 1 s. All of
// that runs on the game clock, so a pause stops it. A panel hides the bar while it is open and the bar comes back
// after (hideAll). A hint already done never returns, and never replaces the one showing.
//
// The systems that own the thing report it with help.did(action): left, right, shove, sprint, jump, mouse, search,
// inventory, levelUp, journal, weaponSwitch. The systems that own the moment ask for the hint with help.show(name).
import { data } from "./data.js";
import { Label, makeFilter } from "./flash.js";
import { story } from "./story.js";
import { actionTop } from "./touch.js";
import { world } from "./world.js";

const HELP_BAR = 5516;
// The clip's bar sits at this depth on every frame; everything else on a frame is the desktop wording
const BAR_DEPTH = 1;
// A hint line's label, whose font the touch wording copies
const LINE_LABEL = "5487";
// The hint wording's size and baseline, and where the line sits (the middle of the stage)
const TEXT_SIZE = 17;
const TEXT_BASELINE = 15;
const TEXT_Y = 306.45;
const MIDDLE_X = 380;
// On touch the line's lowest glyphs sit this far below TEXT_Y, and it keeps this gap above the action button
const TOUCH_TEXT_DEPTH = TEXT_BASELINE + 5;
const TOUCH_GAP = 4;
// Space a Label adds each side of its words
const LABEL_MARGIN = 2;
const WHITE = "#ffffff";
const GLOW = { type: "glow", color: "#000000", alpha: 1, x: 2, y: 2, passes: 1, strength: 2, inner: false, knockout: false };
// Seconds: the wait before a hint shows, its fade in, how long a done hint holds, and its fade out
const SHOW_WAIT = 1.5;
const FADE_IN = 0.2;
const DONE_HOLD = 2.5;
const FADE_OUT = 1;
// The inventory hint comes this long after the search hint is done
const INVENTORY_WAIT = 3;
// What the player must do for each hint to be done. Hints with no entry end by their own timer or never
const ACTIONS = {
  movement: ["left", "right"],
  mouse: ["mouse"],
  shove: ["shove"],
  sprint: ["sprint"],
  jump: ["jump"],
  search: ["search"],
  inventory: ["inventory"],
  levelUp: ["levelUp"],
  journal: ["journal"],
  weaponSwitch: ["weaponSwitch"],
};
// The touch wording, in AlternateGothic2 BT's glyphs (all upper case). A hint with no line here keeps the art's
const TOUCH = {
  movement: "USE THE LEFT STICK TO MOVE",
  mouse: "PUSH THE RIGHT STICK OUT TO FIRE",
  shove: "TAP SHOVE TO SHOVE ENEMIES",
  search: "TAP THE ACTION BUTTON TO SEARCH THE TRUNK",
  inventory: "TAP THE BACKPACK TO OPEN IT AND EQUIP A WEAPON",
  levelUp: "TAP LEVEL UP TO OPEN THE CHARACTER SCREEN",
  journal: "TAP THE JOURNAL TO SEE ALL TASKS",
  weaponSwitch: "TAP SWAP TO SWITCH WEAPONS",
  sprint: "HOLD RUN TO RUN SHORT DISTANCES",
};

let page = null;
let depth = 0;
let building = null;
let ready = false;
// The hint on the stage: { name, hint, clip, age, holdFrames, outAt, finished }
let current = null;
let hidden = false;
// What the player has done this story, by action
const did = new Set();
let started = false;
let inventoryAsked = false;

const ease = (t) => Math.sin((Math.min(1, Math.max(0, t)) * Math.PI) / 2);

function frames(seconds) {
  return Math.round(seconds * page.lib.fps);
}

function hintOf(name) {
  return data.story?.help?.hints?.[name] ?? null;
}

function performed(name) {
  const actions = ACTIONS[name] ?? [];
  return actions.length > 0 && actions.every((action) => did.has(action));
}

// ---------- The bar ----------

// The letter a key box shows: the AZERTY setting changes it for the keys that move
function keyLetter(key) {
  return story.settings?.azerty && key.azerty ? key.azerty : key.text;
}

// The touch wording on the bar: the desktop wording and key boxes hide, and one line takes their place
function dressTouch(clip, words) {
  for (const [at, slot] of clip.slots) {
    if (at !== BAR_DEPTH) {
      slot.node.visible = false;
    }
  }
  const font = page.lib.data.labels[LINE_LABEL][0][1];
  const label = new Label([[words, font, false, TEXT_SIZE, WHITE, 0, TEXT_BASELINE, null]]);
  const filter = makeFilter(GLOW, null, page.lib.filterScale);
  label.filters = filter ? [filter] : null;
  label.x = MIDDLE_X - (label.box.width - LABEL_MARGIN * 2) / 2;
  label.y = TEXT_Y;
  clip.attach(label, "touchText");
  liftTouch(clip);
}

// The action button stands over the bar's middle strip, so on touch the line sits just above that button instead
function liftTouch(clip) {
  clip.y = Math.min(0, actionTop() - TOUCH_GAP - (TEXT_Y + TOUCH_TEXT_DEPTH));
}

// The hint's clip, made once the art is loaded
function makeClip(entry) {
  if (!ready) {
    return false;
  }
  const clip = page.lib.make(HELP_BAR);
  clip.label = "help";
  clip.zIndex = depth;
  clip.eventMode = "none";
  clip.alpha = 0;
  clip.gotoAndStop(entry.name);
  for (const key of entry.hint.keys) {
    const box = key.slot ? clip.child(key.slot) : null;
    if (box) {
      box.text = keyLetter(key);
    }
  }
  if (page.touch && TOUCH[entry.name]) {
    dressTouch(clip, TOUCH[entry.name]);
  } else if (page.touch) {
    // A hint with no key wording (the safehouse markings) keeps its own words, but still clears the action button
    liftTouch(clip);
  }
  page.root.addChild(clip);
  entry.clip = clip;
  return true;
}

function removeCurrent() {
  if (current?.clip && !current.clip.destroyed) {
    current.clip.destroy({ children: true });
  }
  current = null;
}

// ---------- Showing and finishing ----------

// The hint is done: it is marked, holds for the wait, then fades out
function finish(entry, wait) {
  if (entry.finished) {
    return;
  }
  entry.finished = true;
  story.help[entry.name] = true;
  entry.outAt = entry.age + frames(wait);
}

// The bar's fade, each step the world runs and the bar is wanted
function fade(entry) {
  entry.age += 1;
  if (entry.holdFrames !== null && !entry.finished && entry.age >= entry.holdFrames) {
    finish(entry, 0);
  }
  // A hint done before it showed has nothing to fade out
  if (entry.finished && entry.clip.alpha === 0) {
    gone(entry);
    return;
  }
  let alpha = ease((entry.age - frames(SHOW_WAIT)) / frames(FADE_IN));
  if (entry.finished) {
    const out = (entry.age - entry.outAt) / frames(FADE_OUT);
    alpha *= 1 - ease(out);
    if (out >= 1) {
      gone(entry);
      return;
    }
  }
  entry.clip.alpha = alpha;
  if (page.touch) {
    liftTouch(entry.clip);
  }
}

// The bar is finished with. On touch screens the mouse hint follows the movement hint
function gone(entry) {
  removeCurrent();
  if (entry.name === "movement" && page.touch) {
    help.show("mouse");
  }
}

function step() {
  if (!started && world.active && story.player) {
    started = true;
    help.show("movement");
  }
  if (!current) {
    return;
  }
  if (!current.clip && !makeClip(current)) {
    return;
  }
  const wanted = world.active && Boolean(story.player) && !hidden;
  current.clip.visible = wanted;
  if (wanted && !world.paused) {
    fade(current);
  }
}

// Once a second, even while paused: has the player done what the hint asks (checkHelp F4:20440)
function check() {
  if (!current || current.finished || !performed(current.name)) {
    return;
  }
  finish(current, DONE_HOLD);
  if (current.name === "search" && !inventoryAsked) {
    inventoryAsked = true;
    world.later(frames(INVENTORY_WAIT), () => help.show("inventory"));
  }
}

function reset() {
  removeCurrent();
  did.clear();
  hidden = false;
  started = false;
  inventoryAsked = false;
}

// On touch, the top of the hint bar that is showing, in stage pixels, or null when no hint shows. The XP line starts
// above it so the bar never covers it
export function touchHintTop() {
  const clip = current?.clip;
  if (!page?.touch || !clip || clip.destroyed || !clip.visible || clip.alpha <= 0) {
    return null;
  }
  const bar = clip.slots.get(BAR_DEPTH)?.node;
  return bar ? page.root.toLocal({ x: 0, y: bar.getBounds().y }).y : null;
}

export const help = {
  // Asks for a hint: seconds, when given, is how long it stays before fading. A hint already done, or whose thing the
  // player has already done, is marked and never shows. Others replace the one showing. Returns whether it will show
  show(name, seconds = null) {
    const hint = hintOf(name);
    if (!hint || !story.help || story.help[name] === true) {
      return false;
    }
    // The mouse hint is the phone's alone: the original never shows it (Q53)
    if (name === "mouse" && !page.touch) {
      return false;
    }
    if (performed(name)) {
      story.help[name] = true;
      return false;
    }
    // Asked for again while it waits or shows: it carries on
    if (current?.name === name && !current.finished) {
      return true;
    }
    removeCurrent();
    current = { name, hint, clip: null, age: 0, holdFrames: seconds === null ? null : frames(seconds), outAt: null };
    return true;
  },

  // The player did a thing a hint may be waiting for
  did(action) {
    did.add(action);
  },

  // Whether the player has done the thing this story
  has(action) {
    return did.has(action);
  },

  // A panel opened (true) or closed (false): the bar hides and comes back
  hideAll(on) {
    hidden = Boolean(on);
  },
};

export function initHelp(owner, band) {
  page = owner;
  depth = band;
  page.steppers.push(step);
  world.stage("help", check, { whilePaused: true });
  world.onReset(reset);
  building = page.lib
    .need([HELP_BAR])
    .then(() => {
      ready = true;
    })
    .catch((e) => console.warn("Union City: the help bar couldn't be drawn", e));
}

// Helpers for page.py checks
export const helpDebug = {
  // Resolves once the bar's art is loaded
  helpReady() {
    return building.then(() => ready);
  },

  // Asks for a hint by hand
  helpShow(name, seconds = null) {
    return help.show(name, seconds);
  },

  // What the bar shows now
  helpState() {
    const clip = current?.clip;
    return {
      name: current?.name ?? null,
      finished: current?.finished ?? null,
      age: current?.age ?? null,
      visible: Boolean(clip?.visible),
      alpha: clip ? Math.round(clip.alpha * 100) / 100 : null,
      touchText: clip?.child("touchText") ? TOUCH[current.name] : null,
      keys: (current?.hint.keys ?? []).map((key) => key.slot && clip?.child(key.slot)?.text).filter(Boolean),
      hidden,
      did: [...did],
      done: { ...story.help },
    };
  },
};
