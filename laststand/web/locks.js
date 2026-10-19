// Keys, locks and the lockpick screen (checkForContKey F4:16164, pickLock F4:16231, workLock F4:16381, pushPin
// F4:16429, lockPin F4:16457, forceLock F4:16516, attemptUnlockDoor F4:14872).
//
// A locked container opens with its key, which is used up, and nothing else happens: the key never also opens the
// lockpick screen. Without the key it may be picked when the player's adjusted Security is at least the lock's need
// less 25; below that the prompt names the Security it needs and E does nothing. A locked door's key and refusal are
// the interaction's (interact.js); any other locked door opens the lockpick screen at that door's own difficulty.
//
// The lockpick screen: holding W (Z on an AZERTY keyboard, the same key by its place) lifts the pick 5 px a step,
// from -25 up to -90. Letting go pushes the pin to that height in 0.3 s; from 0.5 s it falls back over 1.3 s. While a
// falling pin passes its window it shakes once, and D sets it there. A miss drops this pin and the one before (and on a
// very hard lock one more). Setting the last pin opens the lock. The pins move on the panel's own step, which runs
// while the world is paused. A container without a key also offers FORCE LOCK: it opens, or the lock breaks for good
// and whatever was inside is lost.
import { Container, Graphics, Text } from "./vendor/pixi.min.mjs";
import { data } from "./data.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { interact } from "./interact.js";
import { closePanel, openPanel, panelOpen, setAlpha } from "./panels.js";
import { addXP, adjustedSkill, lockXP } from "./player.js";
import { rng } from "./rng.js";
import { room } from "./rooms.js";
import { containerFor, openSearch, recordOf, search } from "./search.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

const PANEL = "lockpick";
const FPS = 30;
// Pins, the pin window's multiplier and the Security each difficulty needs (pickLock F4:16260-16288)
const LOCKS = {
  "very easy": { pins: 1, mod: 1.65, need: "lockSkillReq_veryEasy" },
  easy: { pins: 2, mod: 1.4, need: "lockSkillReq_easy" },
  normal: { pins: 2, mod: 1.15, need: "lockSkillReq_normal" },
  hard: { pins: 3, mod: 0.85, need: "lockSkillReq_hard" },
  "very hard": { pins: 3, mod: 0.625, need: "lockSkillReq_veryHard" },
};
// The word the screen gives a lock, by how far the player's Security is past its need (F4:16289-16309): above
// `over`, up to `upTo`. Outside every band the word is empty
const FEELS = [
  { word: "VERY EASY", over: 30, upTo: 50 },
  { word: "EASY", over: 15, upTo: 30 },
  { word: "NORMAL", over: -15, upTo: 15 },
  { word: "HARD", over: -45, upTo: -15 },
  { word: "VERY HARD", over: -70, upTo: -45 },
];
// What the original's tables say, for a page that has not loaded them yet (F4:27562-27588)
const DEFAULTS = {
  secSkillBuffer: 25,
  lockForceRange: 100,
  securityClickBuffer: 5,
  pinAlpha: 65,
  pinTop: -90,
  pinBottom: -25,
  pinRangeTop: -85,
  pinRangeBottom: -35,
  securitySkillModMax: 10,
  pinPushRate: 5,
  pinFallSpeed: 1.3,
  secSkillMod: 5,
  lockSkillReq_veryEasy: 15,
  lockSkillReq_easy: 30,
  lockSkillReq_normal: 45,
  lockSkillReq_hard: 60,
  lockSkillReq_veryHard: 75,
};
const TEXT = {
  pick: "[E] PICK LOCK",
  useKey: "[E] USE KEY",
  tooLow: "[LOCKED] SECURITY SKILL TOO LOW - NEED ",
  push: "[ W ] PUSH PIN",
  pushAzerty: "[ Z ] PUSH PIN",
  hold: "[ D ] HOLD PIN",
  force: "FORCE LOCK: ",
};
// The panel stands 10 px up and left of the stage's middle (F4:16239)
const PANEL_SHIFT = 10;
// The small pick inside the lock never rises above this (F4:16424)
const PICK_INSIDE_TOP = -40;
// Forcing at or under this chance, or picking a lock at or over that one, counts for the secret achievements
const BRAWN_CHANCE = 30;
const BRAINS_CHANCE = 70;
const MOST_CHANCE = 95;
// The touch buttons under the lock, in the panel's own pixels (the panel's middle is the stage's 370, 190). They end at
// stage y 356, clear of the dock
const TOUCH_BUTTONS = [
  { name: "push", label: "PUSH PIN", x: -180, y: 120, w: 112, h: 46 },
  { name: "set", label: "SET PIN", x: -58, y: 120, w: 112, h: 46 },
];
const BUTTON_FONT = "AlternateGothic2 BT";
const BUTTON_FILL = 0x1c1c1c;
const BUTTON_LIT = 0x5a3d1c;
const BUTTON_EDGE = 0xb6b0a5;
const MOST_RECORDED = 100;

const EASES = {
  easeOutSine: (t) => Math.sin((t * Math.PI) / 2),
  easeInSine: (t) => 1 - Math.cos((t * Math.PI) / 2),
  // MC Tween's own ease when a slide names none
  easeOutExpo: (t) => (t >= 1 ? 1 : 1 - 2 ** (-10 * t)),
};

let page = null;
// The open screen: { clip, target, info, pins, current, push, chance, pick, steps, keyDiff }
let view = null;
// Presses from the touch buttons or a check, read by the next step: { held, released, set }
const drive = { held: false, released: false, set: false };
const countListeners = [];
const log = [];

export const locks = {
  get isOpen() {
    return panelOpen(PANEL);
  },
};

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function note(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// Registers fn(key) for each counter a lock adds to: "pickLock", "forceLock", "pickForceLock" (picked a lock that was
// 70% or more to force), "forcePickLock" (forced one at 30% or less) and "forceBreak" (broke one at 95%)
export function onLockCount(fn) {
  countListeners.push(fn);
}

function count(key) {
  for (const fn of countListeners) {
    try {
      fn(key, 1);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function security() {
  return adjustedSkill(story.player, "security");
}

function luck() {
  return story.player.attributes.luck;
}

// The Security a difficulty needs (getLockDiff F4:16211)
export function lockNeed(diff) {
  const lock = LOCKS[diff];
  return lock ? constant(lock.need) : null;
}

// ---------- Keys ----------

// The backpack row that is the key to a container, or -1 (checkForContKey F4:16164)
function contKeyIndex(container) {
  return story.inventory.findIndex((row) => data.items.quest?.[row.ref]?.cont === container.key);
}

// The Security a container's lock asks for before it may be picked: its need less 25
function pickNeed(container) {
  return Math.round(lockNeed(container.def?.lockDiff) - constant("secSkillBuffer"));
}

// What E on a shut container says: USE KEY with its key carried, the Security it needs in grey when the player has too
// little, otherwise PICK LOCK (F4:15449-15466)
function lockWords(container) {
  if (contKeyIndex(container) >= 0) {
    return TEXT.useKey;
  }
  const need = pickNeed(container);
  return security() < need ? { text: `${TEXT.tooLow}${need}`, grey: true } : TEXT.pick;
}

// The container's lock is open for good and the search panel opens on it
function openContainer(container) {
  recordOf(container).unlocked = true;
  openSearch(container);
}

// E on a shut container: its key opens it and is used up (only the key), else the lockpick screen when the player's
// Security is enough, else nothing
function tryContainer(container) {
  const held = contKeyIndex(container);
  if (held >= 0) {
    const [row] = story.inventory.splice(held, 1);
    note("key", { container: container.key, ref: row.ref });
    openContainer(container);
    return "key";
  }
  if (security() >= pickNeed(container)) {
    openLockpick({ kind: "cont", name: container.name, diff: container.def.lockDiff, container });
    return "pick";
  }
  note("refused", { container: container.key, need: pickNeed(container) });
  return "refused";
}

// E on a locked door or container. target is a container (as search.containerFor gives it) or a door request
// { kind: "door", name }. Returns what happened: "key", "pick", "refused", or for a door whatever the door did
export function tryLock(target) {
  if (target.kind === "door") {
    return interact.tryDoor(target.name);
  }
  return tryContainer(target);
}

// ---------- The pins ----------

// A slide of one part's y, started a number of steps from now. When it starts it takes over from the part's other
// slides that are running, as MC Tween's do
function slide(part, to, seconds, ease = "easeOutExpo", delay = 0, done = null) {
  const frames = Math.max(1, Math.round(seconds * FPS));
  part.moves.push({ to, frames, ease, at: view.steps + Math.round(delay * FPS), from: null, done });
}

function stopSlides(part) {
  part.moves = [];
}

function stepSlides(part) {
  for (const move of [...part.moves]) {
    if (view.steps < move.at) {
      continue;
    }
    if (move.from === null) {
      move.from = part.node.y;
      part.moves = part.moves.filter((other) => other === move || other.from === null);
    }
    const t = Math.min(1, (view.steps - move.at) / move.frames);
    part.node.y = move.from + (move.to - move.from) * EASES[move.ease](t);
    if (t >= 1) {
      part.moves = part.moves.filter((other) => other !== move);
      move.done?.(part);
    }
  }
}

// One pin: its picture, where its window is and its state. The window is a band around a random height, wider for a
// better Security, an easier lock and never more than 10 px either side (pickLock F4:16322-16344)
function makePin(node, lock) {
  const half = Math.min(constant("securitySkillModMax"), (security() / constant("secSkillMod")) * lock.mod);
  const top = constant("pinRangeTop");
  const bottom = constant("pinRangeBottom");
  const spread = Math.abs(top - bottom);
  let range = bottom - (rng.random(spread) + 15 / lock.mod + rng.random(luck()));
  range = Math.min(bottom, Math.max(top, range));
  node.visible = true;
  node.y = constant("pinBottom");
  setAlpha(node, 1);
  return { node, range, top: range - half, bottom: range + half, falling: false, shaking: false, moves: [] };
}

function pinAt(index) {
  return view.pins[index] ?? null;
}

// Letting go of W pushes the pin up to where the pick was lifted, then lets it fall (pushPin F4:16429)
function pushPin() {
  const pin = pinAt(view.current);
  if (!pin || pin.falling) {
    return;
  }
  const height = view.push;
  setAlpha(pin.node, 1);
  pin.shaking = false;
  stopSlides(pin);
  slide(pin, height, 0.3, "easeOutSine", 0, () => {
    pin.falling = true;
    view.push = constant("pinBottom");
  });
  slide(pin, constant("pinBottom"), constant("pinFallSpeed"), "easeInSine", 0.5, () => {
    pin.falling = false;
  });
  const pick = view.pick;
  if (pick) {
    slide(pick, pick.originY - Math.abs(height / 5), 0.3, "easeOutSine");
    slide(pick, pick.originY, 0.3, "easeInSine", 0.4);
  }
  note("push", { pin: view.current + 1, height });
}

// A pin dropped back down after a miss
function dropPin(pin) {
  slide(pin, constant("pinBottom"), 0.2);
  setAlpha(pin.node, 1);
  pin.shaking = false;
  pin.falling = false;
}

// A miss drops this pin and the one before; on a very hard lock one more. On the first pin nothing happens
// (lockPin F4:16489-16514)
function missPin() {
  const at = view.current;
  if (at === 0) {
    note("miss", { pin: 1, dropped: 0 });
    return;
  }
  dropPin(pinAt(at));
  dropPin(pinAt(at - 1));
  let back = 1;
  if (view.diff === "very hard" && at > 1) {
    dropPin(pinAt(at - 2));
    back = 2;
  }
  view.current -= back;
  sound.play("sound_security_fail");
  note("miss", { pin: at + 1, dropped: back + 1 });
}

// D: the pin is set when it is inside its window (lockPin F4:16457)
function setPin() {
  const pin = pinAt(view.current);
  if (!pin || pin.node.y < pin.top || pin.node.y > pin.bottom) {
    missPin();
    return;
  }
  sound.play("sound_security_lockPin");
  stopSlides(pin);
  note("set", { pin: view.current + 1, y: pin.node.y });
  if (view.current < view.pins.length - 1) {
    setAlpha(pin.node, constant("pinAlpha") / 100);
    pin.shaking = false;
    pin.falling = false;
    view.current += 1;
    return;
  }
  picked();
}

// ---------- Opening, picking and forcing ----------

// The last pin set: XP, the counters, and the door or the container opens (lockPin F4:16467-16486)
function picked() {
  const { target, chance } = view;
  sound.play("sound_security_complete");
  addXP(lockXP(), { reason: "security" });
  count("pickLock");
  if (chance >= BRAINS_CHANCE) {
    count("pickForceLock");
  }
  note("picked", { lock: target.kind, name: target.name });
  if (target.kind === "door") {
    closePanel();
    target.unlock?.();
  } else {
    openContainer(target.container);
  }
}

// FORCE LOCK: a roll of 1 to 100 at or under the chance opens the container; otherwise its lock breaks for good and
// what it held is lost (forceLock F4:16516, breakLock F4:16541)
export function forceLock(target = view?.target) {
  if (!view || !target || target.kind !== "cont" || !view.canForce) {
    return null;
  }
  const chance = view.chance;
  const roll = rng.random(constant("lockForceRange")) + 1;
  note("force", { chance, roll });
  if (roll <= chance) {
    sound.play("sound_security_complete");
    addXP(lockXP(), { reason: "security" });
    count("forceLock");
    if (chance <= BRAWN_CHANCE) {
      count("forcePickLock");
    }
    openContainer(target.container);
    return "opened";
  }
  if (chance >= MOST_CHANCE) {
    count("forceBreak");
  }
  sound.play("sound_security_break");
  recordOf(target.container).broken = true;
  closePanel();
  return "broken";
}

// The word the screen gives this lock for this player, and the Security it needs
function feel(need) {
  const past = security() - need;
  return FEELS.find((each) => past > each.over && past <= each.upTo)?.word ?? "";
}

// The words on the screen: the lock, the keys (or nothing on a touch screen, where the buttons say it) and the force
// chance when the lock can be forced
function writeWords(clip, need) {
  setText(clip.child("lockDifficulty"), `${feel(need)} LOCK [${need}]`);
  const azerty = story.settings?.azerty === true;
  setText(clip.child("moveText"), page.touch ? "" : azerty ? TEXT.pushAzerty : TEXT.push);
  setText(clip.child("lockText"), page.touch ? "" : TEXT.hold);
  setText(clip.child("forceLockText"), view.canForce ? `${TEXT.force}${view.chance}%` : "");
  clip.child("forceBtn").visible = view.canForce;
}

function toggleHelp() {
  const panel = view?.clip.child("helpPanel");
  if (!panel) {
    return;
  }
  panel.visible = !panel.visible;
  sound.play(panel.visible ? "sound_openInterface" : "sound_closeInterface");
}

function wireButtons(clip) {
  clip.child("exitBtn").setHandler("onPress", closePanel);
  clip.child("forceBtn").setHandler("onPress", () => forceLock());
  clip.child("helpBtn").setHandler("onPress", toggleHelp);
}

function build(clip, target) {
  const lock = LOCKS[target.diff] ?? LOCKS.normal;
  const need = constant(lock.need);
  const canForce = target.kind === "cont" && target.container?.def?.hasKey !== true;
  const chance = Math.min(MOST_CHANCE, Math.round(security() * lock.mod + luck() * lock.mod));
  view = { clip, target, diff: target.diff, pins: [], current: 0, push: constant("pinBottom"), chance, canForce };
  view.steps = 0;
  clip.position.set(page.width / 2 - PANEL_SHIFT, page.height / 2 - PANEL_SHIFT);
  clip.child("helpPanel").visible = false;
  hud.hidePlay(true);
  for (const name of ["pin1", "pin2", "pin3"]) {
    clip.child(name).visible = false;
  }
  for (let n = 1; n <= lock.pins; n += 1) {
    view.pins.push(makePin(clip.child(`pin${n}`), lock));
  }
  for (const name of ["pinBlock1", "pinBlock2", "pinBlock3"]) {
    clip.child(name).visible = false;
  }
  const pick = clip.child("pick");
  view.pick = pick ? { node: pick, originY: pick.y, moves: [] } : null;
  writeWords(clip, need);
  wireButtons(clip);
  if (page.touch) {
    addTouchButtons(clip);
  }
}

function finish() {
  view = null;
  Object.assign(drive, { held: false, released: false, set: false });
  hud.hidePlay(false);
  sound.play("sound_securityClose");
}

// Opens the lockpick screen on a door ({ kind: "door", name, diff, unlock }) or a container ({ kind: "cont", name,
// diff, container }), at that lock's own difficulty
export function openLockpick(target) {
  sound.play("sound_securityOpen");
  openPanel(PANEL, { art: "int_security", setup: (clip) => build(clip, target), close: finish });
  note("open", { lock: target.kind, name: target.name, diff: target.diff });
}

// ---------- The step ----------

function lifting() {
  return input.keys.down("KeyW") || input.keys.down("ArrowUp") || drive.held;
}

function letGo() {
  return input.keys.released("KeyW") || input.keys.released("ArrowUp") || drive.released;
}

function setPressed() {
  return input.keys.pressed("KeyD") || input.keys.pressed("ArrowRight") || drive.set;
}

// A falling pin inside its window (and up to 5 px above it) shakes once (workLock F4:16383)
function shake(pin) {
  const inside = pin.node.y > pin.top - constant("securityClickBuffer") && pin.node.y < pin.bottom;
  const high = pin.node.child?.("pinHigh");
  if (pin.falling && inside && !pin.shaking) {
    pin.shaking = true;
    pin.node.child("shakeAnim")?.gotoAndPlay("shake");
    sound.play(`sound_security_work${rng.random(2) + 1}`);
    if (high) {
      setAlpha(high, 1);
    }
  } else if (high) {
    setAlpha(high, 0);
  }
}

// The small pick inside the lock stays under the pin being worked
function placeInnerPick() {
  const inner = view.clip.child("pickInternal");
  const pin = pinAt(view.current);
  if (inner && pin) {
    inner.x = pin.node.x;
    inner.y = Math.max(PICK_INSIDE_TOP, pin.node.y);
  }
}

function step() {
  if (!view || !panelOpen(PANEL)) {
    return;
  }
  view.steps += 1;
  view.pins.forEach(stepSlides);
  if (view.pick) {
    stepSlides(view.pick);
  }
  if (letGo()) {
    pushPin();
  }
  const pin = pinAt(view.current);
  if (pin) {
    shake(pin);
  }
  if (lifting()) {
    view.push = Math.max(constant("pinTop"), view.push - constant("pinPushRate"));
  }
  if (view && setPressed()) {
    setPin();
  }
  if (view) {
    placeInnerPick();
  }
  drive.released = false;
  drive.set = false;
}

// ---------- Touch ----------

function drawButton(button, lit) {
  const { box, def } = button;
  box.clear();
  box.roundRect(0, 0, def.w, def.h, 6).fill({ color: lit ? BUTTON_LIT : BUTTON_FILL, alpha: 0.9 });
  box.roundRect(0, 0, def.w, def.h, 6).stroke({ width: 2, color: BUTTON_EDGE });
}

function makeButton(def) {
  const holder = new Container();
  holder.position.set(def.x, def.y);
  holder.label = `touch_${def.name}`;
  const box = new Graphics();
  const words = new Text({ text: def.label, style: { fontFamily: BUTTON_FONT, fontSize: 24, fill: 0xffffff } });
  words.anchor.set(0.5);
  words.position.set(def.w / 2, def.h / 2);
  holder.addChild(box, words);
  holder.eventMode = "static";
  holder.cursor = "pointer";
  const button = { holder, box, def };
  drawButton(button, false);
  return button;
}

// PUSH PIN lifts while a finger holds it and pushes when it lets go (or the browser takes the finger away, or the
// page loses focus); SET PIN sets on the press
function addTouchButtons(clip) {
  const [push, set] = TOUCH_BUTTONS.map(makeButton);
  const release = () => {
    if (drive.held) {
      drive.held = false;
      drive.released = true;
    }
    drawButton(push, false);
  };
  push.holder.on("pointerdown", () => {
    drive.held = true;
    drawButton(push, true);
  });
  push.holder.on("pointerup", release);
  push.holder.on("pointerupoutside", release);
  push.holder.on("pointercancel", release);
  set.holder.on("pointerdown", () => {
    drive.set = true;
    drawButton(set, true);
  });
  const unlight = () => drawButton(set, false);
  set.holder.on("pointerup", unlight);
  set.holder.on("pointerupoutside", unlight);
  set.holder.on("pointercancel", unlight);
  clip.addChild(push.holder, set.holder);
  view.buttons = { push, set };
}

// ---------- Setup ----------

export function initLocks(owner) {
  page = owner;
  search.hooks.lock = tryContainer;
  search.hooks.words = lockWords;
  interact.hooks.lockpick = openLockpick;
  world.stage("interface", step);
  world.onReset(() => {
    view = null;
    log.length = 0;
    Object.assign(drive, { held: false, released: false, set: false });
  });
}

Object.assign(locks, { tryLock, openLockpick, forceLock, lockNeed, onCount: onLockCount });

// Helpers for page.py checks
export const locksDebug = {
  // E on a container of this room by its name, as the player would press it
  lockTry(name) {
    return tryLock(containerFor(room.id, name));
  },

  // What the open lockpick screen holds, or null
  lockState() {
    if (!view) {
      return null;
    }
    const text = (name) => view.clip.child(name).text;
    return {
      kind: view.target.kind,
      name: view.target.name,
      diff: view.diff,
      words: text("lockDifficulty"),
      move: text("moveText"),
      hold: text("lockText"),
      force: text("forceLockText"),
      forceShown: view.clip.child("forceBtn").visible,
      chance: view.chance,
      current: view.current + 1,
      push: view.push,
      pins: view.pins.map((pin) => ({
        y: Math.round(pin.node.y * 10) / 10,
        top: Math.round(pin.top * 10) / 10,
        bottom: Math.round(pin.bottom * 10) / 10,
        falling: pin.falling,
        shaking: pin.shaking,
        alpha: pin.node.alpha,
      })),
      buttons: view.buttons ? Object.keys(view.buttons) : [],
      paused: world.paused,
    };
  },

  // Holds the pick up (true) or lets it go (false), as W does
  lockHold(on) {
    if (drive.held && !on) {
      drive.released = true;
    }
    drive.held = Boolean(on);
    return locksDebug.lockState();
  },

  // Presses D once
  lockSet() {
    drive.set = true;
    return true;
  },

  // Where the touch buttons stand on the page, in CSS pixels of the game frame
  lockButtons() {
    if (!view?.buttons) {
      return null;
    }
    const canvas = page.app.canvas.getBoundingClientRect();
    const scale = canvas.width / page.app.screen.width;
    const middle = (button) => {
      const box = button.holder.getBounds();
      return {
        x: Math.round(canvas.left + (box.x + box.width / 2) * scale),
        y: Math.round(canvas.top + (box.y + box.height / 2) * scale),
      };
    };
    return { push: middle(view.buttons.push), set: middle(view.buttons.set) };
  },

  lockForce: () => forceLock(),

  lockLog() {
    return log.map((each) => ({ ...each }));
  },
};
