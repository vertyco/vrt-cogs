// The HUD: the original's `hud` clip (sprite 5555, F4:17963) drawn once over the world, with every part of it driven
// from the game's state. The bars, counters, icons and prompt lines follow what the story holds, checked every frame
// and redrawn only when a number changes; the alerts, banners, floating XP lines and the save icon are asked for by the
// systems that own the news (hud.alert, hud.banner, hud.xpText, hud.saveIcon).
//
// Its animations run on the real clock like the original's tweens (page.steppers runs while the world is paused), so a
// banner for a quest accepted in a dialog still fades. The HUD stays hidden until a story is running.
import { ColorMatrixFilter } from "./vendor/pixi.min.mjs";
import { companions } from "./companions.js";
import { data } from "./data.js";
import { applyColor } from "./flash.js";
import { touchHintTop } from "./help.js";
import { input } from "./input.js";
import { penalty, refuseOpen } from "./player.js";
import { decorate } from "./rig.js";
import { room } from "./rooms.js";
import { story } from "./story.js";
import { actionTop } from "./touch.js";
import { heldAmmo } from "./weapons.js";
import { world } from "./world.js";

// The most lines kept for a check to read
const MOST_RECORDED = 50;
const HUD = 5555;
// The art the HUD attaches later, by export name
const ROLL_OVER = "hud_bottomBarRollOver";
const XP_LINE = "overlay_xp";
const PAUSE_OVERLAY = "int_pauseOverlay";
const SAVE_ICON = "saveAnim";
// How the ammo icons of each kind lay out (setupAmmoCounter F4:18075). step is the gap between icons, and split puts
// half of them in a second row above the first
const AMMO_ICONS = {
  tinyBullet: { art: "int_smallBullet", step: 2, split: true },
  smallBullet: { art: "int_smallBullet", step: 5, split: true },
  shotgunShell: { art: "int_shotgunShell", step: 9, split: false },
  rifleShell: { art: "int_rifleShell", step: 4, split: false },
  bigBullet: { art: "int_bigBullet", step: 8, split: false },
};
const ROW_GAP = 5;
const DEFAULT_EMPTY_ICON = 30;
const DEFAULT_LOW_HEALTH = 40;
// The reds of the HUD's words and flashes (13369344 and 10027008)
const RED_TEXT = "#cc0000";
const WHITE_TEXT = "#ffffff";
const GREY_TEXT = "#949494";
const XP_GREY_TEXT = "#999999";
const FLASH_RED = 0x990000;
// Where the XP line floats from, and how far it rises (showXPText F4:13679)
const XP_BASE = 62;
const XP_RISE = 8;
// The line's lowest glyphs sit this far above its y. On touch the action button stands over the bar's middle strip,
// so the line starts with those glyphs this gap above the button
const XP_GLYPH_RAISE = 2.5;
const XP_TOUCH_GAP = 4;
const SAVE_ICON_X = 13;
const SAVE_ICON_Y = 382;
const SAVE_ICON_SCALE = 0.9;
// The dock buttons' fade and their hover boxes' words (hudButtonSetup F4:18308)
const BUTTON_OVER = 50;
const BUTTON_OUT = 20;
const ROLL_OVER_Y = 350;
const DOCK_WORDS = {
  btn_inventory: "[ B ] BACKPACK",
  btn_character: "[ C ] CHARACTER",
  btn_journal: "[ J ] JOURNAL",
  btn_achievements: "[ X ] ACHIEVEMENTS",
};
// What each button opens: the name a panel registers with hud.onOpen
const DOCK_OPENS = {
  btn_inventory: "backpack",
  btn_character: "character",
  btn_journal: "journal",
  btn_achievements: "achievements",
  btn_options: "pause",
  levelUp: "character",
};
// The pieces of the HUD that a panel hides and play shows again (hideHUD F4:17900, showHUD F4:17917). The ones that
// show only sometimes (the alert, LEVEL UP, the fuel icon, the companion mark) are worked out where they are drawn
const PLAY_PARTS = ["ammo", "health", "interactText", "activeQuestText", "staminaBar"];
const DOCK_PARTS = ["btn_character", "btn_inventory", "btn_journal", "btn_achievements"];
// The pause reasons that never raise the dim overlay: a room change is a fade, not a stop
const NO_OVERLAY = new Set(["room change"]);
// The alert line is drawn this far above the HUD's band: over the panels that cover the rest of the HUD (band 3000), so
// a line like TOO MUCH WEIGHT is read while a panel is open, and under the achievement panels (band 3500) and the
// dialog boxes (band 4000), which cover it as they cover the original's HUD
const ALERT_RAISE = 1400;

const EASE = {
  linear: (t) => t,
  easeOutSine: (t) => Math.sin((t * Math.PI) / 2),
  easeInSine: (t) => 1 - Math.cos((t * Math.PI) / 2),
  easeOutExpo: (t) => (t >= 1 ? 1 : 1 - 2 ** (-10 * t)),
};

let page = null;
let depth = 0;
let clip = null;
let building = null;
// Tweens in flight: { node, prop, to, frames, wait, age, ease, done, from, started, dead }
let tweens = [];
// Words queued for the alert line, and whether one is showing
let alertQueue = [];
let alertShowing = false;
let overlay = null;
let saveIcon = null;
let rollOver = null;
// Whether the whole HUD is wanted, and which groups of parts are hidden by a panel or the map
let wanted = true;
let playHidden = false;
let dockHidden = false;
let barsHidden = false;
// What the parts show now, so a frame that changes nothing touches nothing
let shown = {};
let ammoIcons = [];
let dressedRig = null;
const openers = new Map();
const pressedLog = [];

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

function keep(list, entry) {
  list.push(entry);
  if (list.length > MOST_RECORDED) {
    list.shift();
  }
}

function upper(text) {
  return String(text ?? "").toUpperCase();
}

// ---------- Tweens ----------

// The properties a tween moves, as the original's alphaTo, xScaleTo, yScaleTo, ySlideTo and colorTo did (alpha and
// scales in percent, scale being both scales together; flat is how far the part has gone to a flat colour, 0 to 1)
const PROPS = {
  alpha: { get: (node) => node.alpha * 100, set: (node, value) => (node.alpha = value / 100) },
  xscale: { get: (node) => node.scale.x * 100, set: (node, value) => (node.scale.x = value / 100) },
  scale: { get: (node) => node.scale.x * 100, set: (node, value) => node.scale.set(value / 100) },
  y: { get: (node) => node.y, set: (node, value) => (node.y = value) },
  flat: { get: (node) => node.flatAmount ?? 0, set: (node, value) => setFlat(node, value) },
};

// The part drawn part of the way to one flat colour, over its own look
function setFlat(node, amount) {
  node.flatAmount = amount;
  if (amount <= 0) {
    node.filters = null;
    return;
  }
  node.flatFilter ??= new ColorMatrixFilter();
  const keepShare = 1 - amount;
  const [r, g, b] = [16, 8, 0].map((shift) => (((node.flatColour ?? FLASH_RED) >> shift) & 255) / 255);
  // prettier-ignore
  node.flatFilter.matrix = [
    keepShare, 0, 0, 0, r * amount,
    0, keepShare, 0, 0, g * amount,
    0, 0, keepShare, 0, b * amount,
    0, 0, 0, 1, 0,
  ];
  node.filters = [node.flatFilter];
}

// Moves a property to a value over some seconds, after a delay. A tween that starts takes over from any earlier one on
// the same property (mc_tween2's rule), and one still waiting leaves the part alone
export function tween(node, prop, to, seconds, { ease = "linear", delay = 0, done = null } = {}) {
  const fps = page.lib.fps;
  if (!node || !Number.isFinite(to)) {
    return null;
  }
  const entry = {
    node,
    prop,
    to,
    frames: Math.max(1, Math.round(seconds * fps)),
    wait: Math.round(delay * fps),
    age: 0,
    ease: EASE[ease],
    done,
    from: 0,
    started: false,
    dead: false,
  };
  tweens.push(entry);
  return entry;
}

// The original's stopTween: nothing of this part's moves on
export function stopTweens(node) {
  for (const entry of tweens) {
    if (entry.node === node) {
      entry.dead = true;
    }
  }
}

function stepTweens() {
  for (const entry of tweens) {
    if (entry.dead || entry.node.destroyed) {
      entry.dead = true;
      continue;
    }
    if (entry.wait > 0) {
      entry.wait -= 1;
      continue;
    }
    if (!entry.started) {
      entry.started = true;
      for (const other of tweens) {
        if (other !== entry && other.started && other.node === entry.node && other.prop === entry.prop) {
          other.dead = true;
        }
      }
      const here = PROPS[entry.prop].get(entry.node);
      entry.from = Number.isFinite(here) ? here : entry.to;
    }
    entry.age += 1;
    const share = entry.ease(Math.min(1, entry.age / entry.frames));
    PROPS[entry.prop].set(entry.node, entry.from + (entry.to - entry.from) * share);
    if (entry.age >= entry.frames) {
      entry.dead = true;
      entry.done?.(entry.node);
    }
  }
  tweens = tweens.filter((entry) => !entry.dead);
}

// ---------- Text ----------

// Puts words on one of the HUD's text fields. The field's starting words and its markup never show, so the words are
// drawn plain in the field's own font and size, in white or the colour asked for
export function setText(field, text, color = null) {
  if (!field || field.destroyed) {
    return;
  }
  // The prompts are set every step; words already drawn the same way are not drawn again
  const words = text === undefined || text === null ? "" : String(text);
  if (field.def.html === null && (!color || field.def.color === color) && field.shown === words) {
    return;
  }
  field.def = { ...field.def, html: null, ...(color ? { color } : {}) };
  field.shown = null;
  field.text = text;
}

function part(name) {
  return clip?.child(name) ?? null;
}

function inside(name, ...path) {
  let node = part(name);
  for (const step of path) {
    node = node?.child?.(step) ?? null;
  }
  return node;
}

// ---------- The state the HUD shows ----------

export const hud = {
  // { text, colour } for the latest alerts, oldest first
  alerts: [],
  // { kind, text } for the latest banners ("LEVEL 4")
  banners: [],
  // { text, dim } for the latest floating XP lines
  xpTexts: [],
  // What the red edges show now
  edges: { visible: false, alpha: 0 },
  // The words on the prompt lines now ("" for none), and whether the E line is grey
  interactText: "",
  interactGrey: false,
  survivorText: "",
  // Whether the dim overlay of a paused game is up
  overlayShown: false,
  // The pause reasons that raise no overlay
  noOverlay: NO_OVERLAY,

  // A line in the alert queue ("LOW STAMINA"). Red unless colour is "white"
  alert(text, colour) {
    keep(hud.alerts, { text, colour: colour ?? "red" });
    alertQueue.push({ text: upper(text), white: colour === "white" });
  },

  // Takes every waiting copy of a line out of the queue (removeAlerts F4:20411)
  removeAlert(text) {
    const gone = upper(text);
    alertQueue = alertQueue.filter((line) => line.text !== gone);
  },

  // A banner for a moment. "accepted" and "complete" give the quest's words; "level" the new level; "gotItem" an alert
  banner(kind, text) {
    keep(hud.banners, { kind, text });
    if (kind === "gotItem") {
      hud.alert(/^YOU GOT/i.test(text) ? text : `YOU GOT ${text}`, "white");
    } else if (kind === "level") {
      showLevelUp(text);
    } else if (kind === "accepted" || kind === "complete") {
      showTask(kind, text);
    }
  },

  // The "+50 XP" line that floats up from the bottom. dim is the grey "NO XP" line for an enemy too weak to count
  xpText(text, dim = false) {
    keep(hud.xpTexts, { text, dim });
    floatXP(text, dim);
  },

  // The E prompt ("[E] SEARCH", "REQUIRES KEY") for the thing in reach. target.grey draws it in grey. "" clears it
  prompt(text, target = null) {
    hud.interactText = text;
    hud.interactGrey = target?.grey === true;
    setText(part("interactText"), text, hud.interactGrey ? GREY_TEXT : WHITE_TEXT);
  },

  // The G prompt ("[G] SWAP WEAPONS") for a companion in reach. "" clears it
  gPrompt(text) {
    hud.survivorText = text;
    setText(part("survivorText"), text, WHITE_TEXT);
  },

  // The red edges for the player's health, as a percent of the most. They show at 40 percent and below
  damage(percent) {
    hud.edges.visible = percent <= constant("dmgOpacCutOff", DEFAULT_LOW_HEALTH);
    hud.edges.alpha = Math.min(1, Math.max(0, (100 - percent * 2) / 100));
    applyEdges();
  },

  // A hit that took health lower than it has been: the health icon and bar flash (hudDamageDisplay F4:18030)
  hurt() {
    inside("health", "healthIconAnim")?.play();
    inside("health", "healthBarAnim")?.play();
  },

  // The cash counter flashes red, for a buy (F4:4589)
  cashFlash() {
    const cash = part("cash");
    if (!cash) {
      return;
    }
    cash.flatColour = FLASH_RED;
    tween(cash, "flat", 1, 0.1);
    tween(cash, "flat", 0, 1, { delay: 0.5 });
  },

  // The tracked quest at the top right: the first line is its title, the others its objectives, one to a line. No
  // lines clears it (setTrackQuestText F4:3486)
  trackedQuest(lines) {
    const [title = "", ...objectives] = lines ?? [];
    const objectiveField = inside("activeQuestText", "objectives");
    if (objectiveField) {
      objectiveField.def = { ...objectiveField.def, multiline: true };
    }
    setText(inside("activeQuestText", "txt"), upper(title));
    setText(objectiveField, objectives.map(upper).join("\n"));
  },

  // Shows or hides the whole HUD (a cutscene, the ending)
  show(on) {
    wanted = Boolean(on);
  },

  // The play parts hidden for a panel or the map, and brought back (hideHUD, showHUD)
  hidePlay(on) {
    playHidden = Boolean(on);
  },

  // The four dock buttons hidden or shown (hideDock, showDock)
  hideDock(on) {
    dockHidden = Boolean(on);
  },

  // The health and ammo hidden while the city map is open (hideHudElements, showHudElements)
  hideBars(on) {
    barsHidden = Boolean(on);
  },

  // The map's top box: the area's name and its danger, or null to hide it (updateMapInfo F4:3996)
  mapInfo(info) {
    const box = part("mapInfo");
    if (!box) {
      return;
    }
    box.visible = Boolean(info);
    if (info) {
      setText(box.child("locName"), upper(info.name));
      setText(box.child("dangerLevel"), `DANGER LEVEL - ${info.danger}`);
    }
  },

  // The map's CANCEL button shown or hidden
  cancelTravel(on) {
    const button = part("cancelTravel");
    if (button) {
      button.visible = Boolean(on);
    }
  },

  // The street and area names on arrival by the map (showLocationOnHUD F4:17866). Not while a task banner shows
  showLocation() {
    const box = part("locationName");
    if (!box || part("taskComplete")?.visible || !room.def) {
      return;
    }
    setText(box.child("streetName"), upper(room.def.buildingName));
    setText(box.child("locationName"), upper(room.def.areaName));
    stopTweens(box);
    box.visible = true;
    box.alpha = 0;
    tween(box, "alpha", 100, 1.6, { ease: "easeOutSine" });
    tween(box, "alpha", 0, 1, { ease: "easeOutSine", delay: 5, done: () => (box.visible = false) });
  },

  // The save icon: "saving" while a save is on its way, "failed" when it did not go through, null for none
  saveIcon(state) {
    showSaveIcon(state);
  },

  // Registers what a button opens (hud.onOpen("backpack", fn)): backpack, character, journal, achievements, pause and
  // cancelTravel
  onOpen(name, fn) {
    openers.set(name, fn);
  },

  // A dock button, the gear or LEVEL UP pressed (not while a zombie holds the player)
  press(name) {
    if (refuseOpen()) {
      return;
    }
    const open = openers.get(DOCK_OPENS[name] ?? name);
    keep(pressedLog, DOCK_OPENS[name] ?? name);
    if (open) {
      open();
    } else {
      console.debug(`Union City: nothing opens for ${name} yet`);
    }
  },

  // Redraws everything from the state on the next frame
  refresh() {
    shown = {};
  },

  // The part of the HUD clip with that name, for the systems that drive their own piece of it
  part,

  // What a button was pressed to open, latest last
  pressed: pressedLog,
};

// ---------- Edges and prompts ----------

function applyEdges() {
  const edges = part("dmg");
  if (!edges || edges.destroyed) {
    return;
  }
  edges.visible = hud.edges.visible;
  edges.alpha = hud.edges.alpha;
}

// ---------- Alerts, banners and the floating lines ----------

// The next waiting alert fades in and, three seconds on, out (showAlert F4:20352)
function showAlert(line) {
  const box = part("alertText");
  const field = box?.child("txt");
  if (!box || !field) {
    return;
  }
  alertShowing = true;
  stopTweens(box);
  setText(field, line.text, line.white ? WHITE_TEXT : RED_TEXT);
  box.alpha = 0;
  tween(box, "alpha", 100, 0.4, { ease: "easeOutSine" });
  tween(box, "alpha", 0, 0.4, {
    ease: "easeOutSine",
    delay: 3,
    done: () => {
      alertShowing = false;
    },
  });
}

// One alert at a time (cycleAlerts F4:20381)
function cycleAlerts() {
  if (alertQueue.length > 0 && !alertShowing) {
    showAlert(alertQueue.shift());
  }
}

function showLevelUp(text) {
  const box = part("levelUpAnim");
  if (!box) {
    return;
  }
  setText(box.child("levelText"), text);
  box.child("glowAnim")?.gotoAndPlay(1);
  stopTweens(box);
  box.alpha = 0;
  tween(box, "alpha", 100, 0.2, { ease: "easeOutSine" });
  tween(box, "alpha", 0, 0.5, { ease: "easeOutSine", delay: 2.5 });
}

// The task banner. It is dropped while another banner shows (questStartCompleteAnim F4:3162)
function showTask(kind, text) {
  const box = part("taskComplete");
  if (!box || box.visible || part("locationName")?.visible) {
    return;
  }
  setText(box.child("taskTitle"), kind === "accepted" ? "TASK ACCEPTED" : "TASK COMPLETE");
  setText(box.child("taskName"), upper(text));
  box.alpha = 0;
  box.visible = true;
  tween(box, "alpha", 100, 0.8, { ease: "easeOutSine" });
  tween(box, "alpha", 0, 1, { ease: "easeOutSine", delay: 4, done: () => (box.visible = false) });
}

// A line of XP that rises from the bottom and fades (showXPText F4:13679)
function floatXP(text, dim) {
  if (!clip || !page.lib.exported(XP_LINE)) {
    return;
  }
  const line = page.lib.makeExported(XP_LINE);
  clip.attach(line, "xpText");
  line.eventMode = "none";
  line.x = page.width / 2;
  line.y = page.height - XP_BASE;
  if (page.touch) {
    // A hint on screen stands above the action button, so the line starts above that hint's bar instead
    const top = Math.min(actionTop(), touchHintTop() ?? Infinity);
    line.y = Math.min(line.y, top - XP_TOUCH_GAP + XP_GLYPH_RAISE);
  }
  setText(line.child("txt"), text, dim ? XP_GREY_TEXT : null);
  tween(line, "y", line.y - XP_RISE, 2, { ease: "easeOutExpo" });
  tween(line, "alpha", 0, 1, { delay: 1, done: () => line.removeMovieClip() });
}

// ---------- The save icon ----------

function showSaveIcon(state) {
  if (saveIcon && !saveIcon.destroyed) {
    stopTweens(saveIcon);
    saveIcon.removeMovieClip();
    saveIcon = null;
  }
  if (!state || !clip || !page.lib.exported(SAVE_ICON)) {
    return;
  }
  const icon = page.lib.makeExported(SAVE_ICON);
  clip.attach(icon, "saveAnim");
  icon.eventMode = "none";
  icon.scale.set(SAVE_ICON_SCALE);
  icon.x = SAVE_ICON_X;
  icon.y = SAVE_ICON_Y;
  const failed = state === "failed";
  setText(icon.child("txt"), failed ? "SAVE FAILED" : "SAVING");
  icon.alpha = 0;
  // A save that goes on stays up until it ends; a failure says so for a few seconds
  tween(icon, "alpha", failed ? 100 : 15, 0.3);
  if (failed) {
    tween(icon, "alpha", 0, 0.3, { delay: 4, done: () => icon.removeMovieClip() });
  }
  saveIcon = icon;
}

// ---------- The pause overlay ----------

function timeWords() {
  const hour = world.hour % 12 || 12;
  const minute = String(world.minute).padStart(2, "0");
  return `DAY ${world.day} - ${hour}:${minute} ${world.hour < 12 ? "AM" : "PM"}`;
}

function locationWords() {
  return room.def ? `${upper(room.def.buildingName)}, ${upper(room.def.areaName)}` : "";
}

// The dim bar with the place and the time that shows whenever the game is stopped for a panel (pauseGame F4:25184)
function syncOverlay() {
  const wantsOverlay = world.paused && [...world.reasons].some((reason) => !hud.noOverlay.has(reason));
  if (wantsOverlay && (!overlay || overlay.destroyed)) {
    if (!page.lib.exported(PAUSE_OVERLAY)) {
      return;
    }
    overlay = clip.attach(page.lib.makeExported(PAUSE_OVERLAY), "pauseOverlay");
    overlay.eventMode = "none";
  }
  if (overlay && !overlay.destroyed) {
    overlay.visible = wantsOverlay;
    if (wantsOverlay) {
      setText(overlay.child("time"), timeWords());
      setText(overlay.child("location"), locationWords());
    }
  }
  hud.overlayShown = Boolean(wantsOverlay && overlay);
}

// ---------- The ammo counter ----------

// Draws the icons for the weapon in hand (setupAmmoCounter F4:18075), one for each round the gun holds
function setupAmmo(weapon) {
  for (const icon of ammoIcons) {
    icon.destroy({ children: true });
  }
  ammoIcons = [];
  const ammo = part("ammo");
  const layout = AMMO_ICONS[weapon.ammoIcon];
  if (!ammo || !layout || weapon.weaponClass === "melee" || weapon.weaponType === "chainsaw") {
    return;
  }
  const most = weapon.maxAmmo;
  const top = layout.split ? Math.round(most / 2) : 0;
  const bottom = most - top;
  for (let index = 0; index < most; index += 1) {
    const upperRow = index >= bottom;
    const place = upperRow ? index - bottom : index;
    const icon = page.lib.makeExported(layout.art);
    ammo.attach(icon, `ammoIcon${index + 1}`);
    icon.eventMode = "none";
    icon.x = -layout.step * place;
    icon.y = layout.split ? (upperRow ? -ROW_GAP : ROW_GAP) : 0;
    icon.alpha = constant("ammoIconEmpty", DEFAULT_EMPTY_ICON) / 100;
    ammoIcons.push(icon);
  }
}

// The icons lit for the rounds loaded, the rounds held beside them, and the chainsaw's fuel (updateAmmoCounter
// F4:18044, updateInterface "ammo" F4:18289)
function syncAmmo() {
  const { weapon, loaded, reserve } = heldAmmo();
  const key = `${weapon.ref}:${weapon.maxAmmo}`;
  if (shown.weapon !== key) {
    shown.weapon = key;
    shown.loaded = null;
    setupAmmo(weapon);
  }
  const fuel = part("fuelIcon");
  if (fuel) {
    fuel.visible = weapon.weaponType === "chainsaw" && !playHidden && !barsHidden;
    const level = fuel.visible ? Math.round((loaded / weapon.maxAmmo) * 100) : 0;
    if (shown.fuel !== level) {
      shown.fuel = level;
      const bar = inside("fuelIcon", "bar");
      if (bar) {
        bar.scale.y = level / 100;
      }
    }
  }
  if (shown.loaded !== loaded) {
    shown.loaded = loaded;
    const empty = constant("ammoIconEmpty", DEFAULT_EMPTY_ICON) / 100;
    ammoIcons.forEach((icon, index) => (icon.alpha = index < loaded ? 1 : empty));
  }
  if (shown.reserve !== reserve) {
    shown.reserve = reserve;
    // Under 100 rounds the count gets a leading zero
    const words = reserve === null ? "" : `${reserve < 100 ? "0" : ""}${reserve}`;
    setText(inside("ammo", "ammoTotal"), words);
  }
}

// ---------- Vitals, XP and points ----------

// Health and permanent health as bars. A fall in permanent health drains both bars over a second and flashes the bar's
// backing red; anything else sets them at once (updateInterface F4:18263)
function syncHealth() {
  const who = story.player;
  const key = `${Math.round(who.health)}:${Math.round(who.permHealth)}:${who.healthMax}`;
  if (shown.health === key || !Number.isFinite(who.health / who.healthMax)) {
    return;
  }
  const dropped = shown.perm !== undefined && who.permHealth < shown.perm;
  shown.health = key;
  shown.perm = who.permHealth;
  const healthBar = inside("health", "healthBar", "bar");
  const permBar = inside("health", "permHealth", "bar");
  const healthScale = Math.round((who.health / who.healthMax) * 100);
  const permScale = Math.round((who.permHealth / who.healthMax) * 100);
  if (dropped) {
    const backing = inside("health", "healthBar", "backing");
    if (backing) {
      backing.flatColour = FLASH_RED;
      tween(backing, "flat", 1, 0.3);
      tween(backing, "flat", 0, 1, { delay: 0.5 });
    }
    tween(healthBar, "xscale", healthScale, 1);
    tween(permBar, "xscale", permScale, 1);
  } else {
    stopTweens(healthBar);
    stopTweens(permBar);
    healthBar?.scale.set(healthScale / 100, 1);
    permBar?.scale.set(permScale / 100, 1);
  }
}

// The stamina bar is drawn mirrored (under a mirrored clip), so its scale keeps the sign it was placed with and the bar
// shrinks toward the same end
function syncStamina() {
  const who = story.player;
  const percent = Math.round((who.stamina / who.staminaMax) * 100);
  if (!Number.isFinite(percent) || shown.stamina === percent) {
    return;
  }
  shown.stamina = percent;
  const bar = inside("staminaBar", "bar");
  if (bar) {
    bar.placedSign ??= Math.sign(bar.scale.x) || 1;
    tween(bar, "xscale", percent * bar.placedSign, 0.2, { ease: "easeOutSine" });
  }
}

function syncXP() {
  const who = story.player;
  const percent = Math.round((who.xp / who.levelXP) * 100);
  if (Number.isFinite(percent) && shown.xp !== percent) {
    shown.xp = percent;
    inside("xpBar", "bar")?.scale.set(percent / 100, 1);
  }
}

// The hunger and sleep icons in Survivor mode, as strong as the penalty they cost: 20 percent a point, and none under
// a point (updateInterface F4:18235)
function syncNeeds() {
  const gauges = [
    ["hungerIcon", penalty("strength")],
    ["sleepIcon", penalty("precision")],
  ];
  for (const [name, points] of gauges) {
    const icon = part(name);
    if (icon) {
      const alpha = Math.min(100, points * 20);
      icon.visible = points > 0;
      icon.alpha = alpha < 20 ? 0 : alpha / 100;
    }
  }
}

// The companion's head at the screen's edge toward them, red while they are down (companionIndicator F4:16750)
function syncCompanion() {
  const mark = part("compInd");
  if (!mark) {
    return;
  }
  const { visible, side, down } = companions.indicator;
  const follower = world.companions.find((each) => !each.partner && each.alive === true);
  mark.visible = visible && !playHidden && Boolean(follower?.rig);
  if (!mark.visible) {
    return;
  }
  if (follower.rig !== dressedRig) {
    dressedRig = follower.rig;
    decorate(mark, follower.rig.look, follower.rig.clothes, { backpack: false });
  }
  mark.scale.x = side === "left" ? -1 : 1;
  mark.x = side === "left" ? 0 : page.width;
  if (shown.down !== down) {
    shown.down = down;
    applyColor(mark, down ? { mult: [307, 128, 128, 256], add: [0, 0, 0, 0] } : null);
  }
}

// ---------- One frame ----------

function syncParts() {
  const who = story.player;
  for (const name of PLAY_PARTS) {
    const node = part(name);
    if (node) {
      node.visible = !playHidden && !(barsHidden && (name === "health" || name === "ammo"));
    }
  }
  // On a touch screen the action and G buttons carry these two lines' words
  const gLine = part("survivorText");
  if (gLine) {
    gLine.visible = !page.touch;
  }
  const useLine = part("interactText");
  if (useLine && page.touch) {
    useLine.visible = false;
  }
  const alerts = part("alertText");
  if (alerts) {
    alerts.visible = !playHidden && alertShowing;
  }
  const levelUp = part("levelUp");
  if (levelUp) {
    levelUp.visible = (who.points.attribute > 0 || who.points.skill > 0) && !playHidden;
  }
  for (const name of DOCK_PARTS) {
    const button = part(name);
    if (button) {
      button.visible = !dockHidden;
    }
  }
  const cash = part("cash");
  if (cash) {
    cash.visible = room.def?.isShop === true;
    if (cash.visible && shown.cash !== who.cash) {
      shown.cash = who.cash;
      setText(inside("cash", "totalCash"), `$${who.cash}`);
    }
  }
  const grain = part("filmGrain");
  if (grain) {
    grain.visible = story.settings?.filmGrain === true;
  }
}

function step() {
  stepTweens();
  if (!clip) {
    return;
  }
  const on = wanted && world.active && Boolean(story.player);
  clip.visible = on;
  if (!on) {
    const alerts = part("alertText");
    if (alerts) {
      alerts.visible = false;
    }
    return;
  }
  syncHealth();
  syncStamina();
  syncXP();
  syncNeeds();
  syncAmmo();
  syncParts();
  syncCompanion();
  syncOverlay();
  cycleAlerts();
}

// ---------- Building the clip ----------

// What setupInterface starts hidden or empty (F4:17963)
function setupParts() {
  for (const name of ["social", "locationName", "taskComplete", "helpBar", "mapInfo", "cancelTravel", "compInd"]) {
    const node = part(name);
    if (node) {
      node.visible = false;
    }
  }
  for (const name of ["levelUpAnim", "dmg", "levelText", "alertText"]) {
    const node = part(name);
    if (node) {
      node.alpha = 0;
    }
  }
  const alerts = part("alertText");
  if (alerts) {
    alerts.visible = false;
    alerts.zIndex = depth + ALERT_RAISE;
    page.root.addChild(alerts);
  }
  setText(part("survivorText"), hud.survivorText, WHITE_TEXT);
  setText(part("interactText"), hud.interactText, hud.interactGrey ? GREY_TEXT : WHITE_TEXT);
  setText(part("levelText"), "");
  setText(inside("activeQuestText", "txt"), "");
  setText(inside("activeQuestText", "objectives"), "");
  setText(inside("alertText", "txt"), "");
  // The bars that hover and the art the original hides with its own scripts stay out of the way
  for (const node of ["achProgress", "reloadBar", "loadScreen", "cutSceneTop", "cutSceneBottom"]) {
    const found = part(node);
    if (found) {
      found.visible = false;
    }
  }
  applyEdges();
  setupRollOver();
  setupXPHover();
}

function setupRollOver() {
  if (!page.lib.exported(ROLL_OVER)) {
    return;
  }
  rollOver = clip.attach(page.lib.makeExported(ROLL_OVER), "rollOverBox");
  rollOver.eventMode = "none";
  rollOver.alpha = 0;
  rollOver.y = ROLL_OVER_Y;
}

// The XP line shows the level and the XP needed while the pointer is over it
function setupXPHover() {
  const bar = part("xpBar");
  const words = part("levelText");
  if (!bar || !words) {
    return;
  }
  bar.useHandCursor = false;
  bar.setHandler("onRollOver", () => {
    const who = story.player;
    words.alpha = 0;
    setText(words, `LEVEL ${who.level} - ${who.xp} / ${who.levelXP}`);
    tween(words, "alpha", 100, 0.1, { delay: 0.2 });
  });
  bar.setHandler("onRollOut", () => {
    stopTweens(words);
    words.alpha = 0;
  });
}

async function build() {
  const ids = [HUD, ...[ROLL_OVER, XP_LINE, PAUSE_OVERLAY, SAVE_ICON, ...Object.values(AMMO_ICONS).map((i) => i.art)]]
    .map((each) => (typeof each === "string" ? page.lib.exported(each) : each))
    .filter(Boolean);
  await page.lib.need(ids);
  clip = page.lib.make(HUD);
  clip.label = "hud";
  clip.zIndex = depth;
  clip.visible = false;
  // Drawn from its own list, apart from the world's, which changes every step
  clip.enableRenderGroup();
  page.root.addChild(clip);
  setupParts();
  shown = {};
}

export function initHud(owner, band) {
  page = owner;
  depth = band;
  page.steppers.push(step);
  world.onReset(() => {
    alertQueue = [];
    alertShowing = false;
    shown = {};
    dressedRig = null;
    hud.interactText = "";
    hud.survivorText = "";
    hud.interactGrey = false;
  });
  building = build().catch((e) => console.warn("Union City: the HUD couldn't be drawn", e));
}

// ---------- The art's load handlers ----------

// A dock button, the gear or LEVEL UP: it fades up under the pointer, names itself in a box and opens its panel
// (hudButtonSetup F4:18308)
function buttonSetup(node, name) {
  if (!node.setHandler) {
    return;
  }
  node.setHandler("onRollOver", () => {
    if (page.touch) {
      return;
    }
    tween(node, "alpha", BUTTON_OVER, 0.5);
    const words = DOCK_WORDS[name];
    if (!rollOver || !words) {
      return;
    }
    stopTweens(rollOver);
    rollOver.x = node.x;
    rollOver.alpha = 0;
    setText(rollOver.child("txt"), words);
    tween(rollOver, "alpha", 100, 0.1, { delay: 0.4 });
  });
  node.setHandler("onRollOut", () => {
    if (page.touch) {
      return;
    }
    tween(node, "alpha", BUTTON_OUT, 0.5);
    if (rollOver) {
      stopTweens(rollOver);
      rollOver.alpha = 0;
    }
  });
  // The press is the button's, never a shot, even held on after the panel it opens has shut
  node.setHandler("onPress", () => {
    input.swallowPress();
    hud.press(name);
  });
}

export const HUD_LOAD_CALLS = {
  hudButtonSetup: buttonSetup,
  // The map's CANCEL: back to the section the player stands in (cancelTravelButton F4:4037)
  cancelTravelButton(node) {
    node.setHandler?.("onRelease", () => openers.get("cancelTravel")?.());
  },
};

export const HUD_LOAD_ACTIONS = {
  // The reload bar sits in the middle of the stage
  centerX(node) {
    node.x = (page.width - node.width) / 2;
  },
};

// Helpers for page.py checks
export const hudDebug = {
  // Resolves once the HUD's clip is drawn
  hudReady() {
    return building.then(() => Boolean(clip));
  },

  // What the HUD shows now, in words and numbers
  hudState() {
    const text = (...path) => inside(...path)?.text ?? null;
    const percent = (name) => (part(name)?.visible ? Math.round(part(name).alpha * 100) : null);
    return {
      visible: clip?.visible ?? false,
      alerts: { queued: alertQueue.length, showing: alertShowing, text: text("alertText", "txt") },
      banners: hud.banners.slice(-3),
      overlay: hud.overlayShown,
      ammo: {
        total: text("ammo", "ammoTotal"),
        icons: ammoIcons.length,
        lit: ammoIcons.filter((icon) => icon.alpha === 1).length,
      },
      quest: { title: text("activeQuestText", "txt"), objectives: text("activeQuestText", "objectives") },
      interact: hud.interactText,
      survivor: hud.survivorText,
      hunger: percent("hungerIcon"),
      sleep: percent("sleepIcon"),
      levelUp: part("levelUp")?.visible ?? null,
      cash: part("cash")?.visible ? text("cash", "totalCash") : null,
      health: {
        bar: inside("health", "healthBar", "bar")?.scale.x,
        perm: inside("health", "permHealth", "bar")?.scale.x,
      },
      stamina: inside("staminaBar", "bar")?.scale.x,
      xp: inside("xpBar", "bar")?.scale.x,
      compInd: part("compInd")?.visible ?? null,
      tweens: tweens.length,
    };
  },
};
