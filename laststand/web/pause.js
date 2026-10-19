// The pause menu and Options (openPauseMenu F4:18813, closePauseMenu F4:18851, pauseMenu_mainBtnSetup F4:18862 and the
// audio, game, video and keyboard setups after it; sprite pauseMenu, 5997). Esc or the gear opens it over the stopped
// world: RESUME, SAVE GAME, OPTIONS and SAVE AND QUIT. OPTIONS leads to the four tabs (AUDIO, GAME, VISUAL and
// CONTROLS), each a list of settings that a press flips or steps to the next value and BACK returns from. Esc or E
// shuts the whole menu from any tab.
//
// The settings are story.settings, kept per save slot (spec 2.16). Changing one takes effect at once; applySettings
// puts every one of them on the systems that show it, for a story that has just started or a save that was loaded. The
// Flash render quality setting is gone (U14), so the VISUAL tab has no QUALITY row and the rows under it move up. The
// button that opens the keyboard tab says CONTROLS, as the tab's own heading does (S9).
//
// The menu cannot open while the player is dead (S22). SAVE AND QUIT saves and, once the save went through, goes back
// to the main menu: the world stops, its pictures go and the keys no longer reach it (S29).
import { data } from "./data.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { light } from "./light.js";
import {
  canOpenPanel,
  closePanel,
  fadeInBox,
  fadeOutBox,
  finger,
  openPanel,
  panelOpen,
  setAlpha,
  tint,
} from "./panels.js";
import { player } from "./player.js";
import { clearRoom } from "./rooms.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { rememberToggleCrouch, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "pause";
const WHITE = 0xffffff;
const MOST_RECORDED = 100;
// The menus inside the art, and the one that shows first
const MENUS = ["main", "optionMenu", "videoMenu", "gameMenu", "keyboard", "audio"];
const FIRST_MENU = "main";
const OPTIONS_MENU = "optionMenu";
// What each button of the first two menus says (the art's own words are replaced, F4:18862)
const MAIN_WORDS = { resume: "RESUME", saveGame: "SAVE GAME", options: "OPTIONS", saveAndQuit: "SAVE AND QUIT" };
const OPTION_WORDS = {
  audio: "AUDIO OPTIONS",
  gameMenu: "GAME OPTIONS",
  videoMenu: "VISUAL OPTIONS",
  keyboard: "CONTROLS",
  back: "BACK",
};
// The Flash quality setting's row on the VISUAL tab and the others of its column, top to bottom: each row is a button
// and the unnamed picture of its words, by depth in the art (pauseMenu_videoBtnSetup, sprite 5958)
const QUALITY_COLUMN = [
  { button: "quality", label: 33 },
  { button: "effects", label: 31 },
  { button: "flashlight", label: 32 },
];
const GAME_SAVED = { heading: "GAME SAVED", body: "\rYOUR GAME HAS BEEN SAVED.", ok: "OK" };
// The menu sits at the stage's middle, so a box at its own origin is in the middle too
const DIALOG = { fade: 0.6, shade: 0.6, out: 0.1 };

const onOff = (value) => (value ? "ON" : "OFF");
const lowHigh = (value) => (value ? "LOW" : "HIGH");
const flip = (value) => !value;
// Body and decal fades step LOW, MEDIUM, HIGH and round again (toggleFades F4:895)
const FADE_WORDS = { low: "LOW", med: "MEDIUM", high: "HIGH" };
const FADE_NEXT = { low: "med", med: "high", high: "low" };
const fade = { words: (value) => FADE_WORDS[value] ?? FADE_WORDS.low, next: (value) => FADE_NEXT[value] ?? FADE_NEXT.low };
const toggle = (key, words = onOff) => ({ key, words, next: flip });

// The settings of each tab: the button's name -> the setting it shows and how a press changes it
const SETTINGS = {
  audio: {
    soundEffects: toggle("soundOn"),
    music: toggle("musicOn"),
  },
  gameMenu: {
    violence: toggle("lowViolence", lowHigh),
    decalFade: { key: "decalFade", ...fade },
    bodyFade: { key: "bodyFade", ...fade },
    damageText: toggle("showDamageText"),
    xpText: toggle("showXPText"),
    achUpdates: toggle("achUpdates"),
  },
  videoMenu: {
    effects: toggle("lowEffects", lowHigh),
    flashlight: toggle("lowFlashlight", lowHigh),
    screenShake: toggle("screenShake"),
    filmGrain: toggle("filmGrain"),
    brightness: { key: "brightness", words: String, next: nextBrightness },
  },
  keyboard: {
    azerty: toggle("azerty"),
    toggleCrouch: toggle("toggleCrouch"),
  },
};

let page = null;
// The open menu: { clip, menu, saved, saving, changed, dialog, tapped }
let view = null;
// What was opened, changed and saved, newest last, for checks
const log = [];

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

function record(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// Brightness runs from the least to the most and round again (toggleBrightness F4:876)
function nextBrightness(value) {
  const next = (value ?? 0) + 1;
  return next > constant("brightnessMax", 5) ? constant("brightnessMin", -5) : next;
}

// ---------- Applying the settings ----------

// Puts every setting on what shows it: sound and music, the film grain and the world's light. The others (violence,
// effects, fades, flashlight, text, screen shake, the keys) are read where they are used. Run after a change, after a
// new story and after a save loads
export function applySettings() {
  const settings = story.settings;
  if (!settings) {
    return;
  }
  sound.setEffects(settings.soundOn !== false);
  sound.setMusic(settings.musicOn !== false);
  hud.refresh();
  light.refresh();
}

// ---------- Painting ----------

// The words a setting's button shows
function wordsOf(spec) {
  return spec.words(story.settings?.[spec.key]);
}

function setWords(button, words) {
  setText(button.child("textClip").child("settingText"), words);
}

// A button under the pointer: its red bar shows and its words go white (the original's highlight and colorTo)
function glow(button, on) {
  button.child("highlight").visible = on;
  tint(button.child("textClip"), on ? WHITE : null);
}

// The new menu's buttons take the old ones' places under the pointer, so the second click of a double click on OPTIONS
// or BACK presses nothing
function showMenu(name) {
  view.menu = name;
  for (const each of MENUS) {
    view.clip.child(each).visible = each === name;
  }
  input.shutByClick();
}

// ---------- Pressing ----------

// A button acts on a mouse press; a finger acts on lifting, so a touch that starts on one and slides away does nothing
function wireButton(button, press) {
  glow(button, false);
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      glow(button, true);
    }
  });
  button.setHandler("onRollOut", (event) => {
    if (!finger(event)) {
      glow(button, false);
    }
  });
  button.setHandler("onPress", (event) => {
    if (view?.dialog) {
      return;
    }
    sound.play("sound_interfacePage1");
    if (finger(event)) {
      view.tapped = button;
    } else {
      press();
    }
  });
  button.setHandler("onRelease", (event) => {
    if (!finger(event) || !view || view.tapped !== button) {
      return;
    }
    view.tapped = null;
    press();
  });
  button.setHandler("onReleaseOutside", () => {
    if (view) {
      view.tapped = null;
    }
  });
}

// A setting's button was pressed: the value changes, takes effect and shows
function change(spec, button) {
  const settings = story.settings;
  settings[spec.key] = spec.next(settings[spec.key]);
  view.changed = true;
  if (spec.key === "toggleCrouch") {
    rememberToggleCrouch(settings.toggleCrouch);
  }
  record("change", { key: spec.key, value: settings[spec.key] });
  applySettings();
  setWords(button, wordsOf(spec));
}

// SAVE GAME: one save for each time the menu opens, then the box that says so (F4:18926). A save that fails leaves the
// button pressable, with the HUD's SAVE FAILED showing
async function saveGame() {
  if (view.saved || view.saving || player.alive !== true) {
    return;
  }
  const mine = view;
  mine.saving = true;
  const ok = await savePoint("save game");
  mine.saving = false;
  record("save", { ok });
  if (ok && view === mine) {
    view.saved = true;
    askSaved();
  }
}

// SAVE AND QUIT: the save, then back to the main menu. A save that fails keeps the menu open over the story, with the
// HUD's SAVE FAILED showing, so the player can try again
async function saveAndQuit() {
  if (view.saving || player.alive !== true) {
    return;
  }
  const mine = view;
  mine.saving = true;
  const ok = await savePoint("save and quit");
  mine.saving = false;
  if (!ok || view !== mine) {
    return;
  }
  record("quit");
  // The save just made holds the settings
  view.changed = false;
  closePanel();
  quitToMenu();
}

// The world goes away and the main menu comes back, showing the notice's box when there is one ({ heading, body }).
// Nothing of the story reads the keys from here on
export function quitToMenu(notice = null) {
  sound.stopAll();
  world.stop();
  world.reset();
  clearRoom();
  hud.hidePlay(false);
  page.show("menu", notice ? { notice } : undefined);
}

// The first two menus' buttons
function wireMain(clip) {
  const actions = {
    resume: () => closePanel(),
    saveGame,
    options: () => showMenu(OPTIONS_MENU),
    saveAndQuit,
  };
  for (const [name, words] of Object.entries(MAIN_WORDS)) {
    const button = clip.child("main").child(name);
    setWords(button, words);
    wireButton(button, actions[name]);
  }
  for (const [name, words] of Object.entries(OPTION_WORDS)) {
    const button = clip.child(OPTIONS_MENU).child(name);
    setWords(button, words);
    wireButton(button, () => showMenu(name === "back" ? FIRST_MENU : name));
  }
}

// A tab: its settings, and the BACK that returns to the options list
function wireTab(clip, menu, specs) {
  const tab = clip.child(menu);
  for (const [name, spec] of Object.entries(specs)) {
    const button = tab.child(name);
    setWords(button, wordsOf(spec));
    wireButton(button, () => change(spec, button));
  }
  const back = tab.child("back");
  setWords(back, "BACK");
  wireButton(back, () => showMenu(OPTIONS_MENU));
}

// The VISUAL tab has no QUALITY row: it goes, and the rows under it each move up one place
function dropQuality(clip) {
  const tab = clip.child("videoMenu");
  const rows = QUALITY_COLUMN.map(({ button, label }) => ({ button: tab.child(button), label: tab.at(label) }));
  const places = rows.map((row) => ({ button: row.button.y, label: row.label.y }));
  rows[0].button.visible = false;
  rows[0].label.visible = false;
  rows.slice(1).forEach((row, index) => {
    row.button.y = places[index].button;
    row.label.y = places[index].label;
  });
}

// ---------- The box that says the game is saved ----------

function closeDialog() {
  if (view) {
    fadeOutBox(view.dialog, DIALOG.out);
    view.dialog = null;
  }
}

// The box over the menu (showDialogBox F4:20000): everything behind it is shut off until OK
function askSaved() {
  const box = view.clip.lib.makeExported("dialogBox");
  view.clip.attach(box, "dialogBox");
  view.dialog = box;
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), GAME_SAVED.heading);
  setText(box.child("textBoxes").child("bodyText"), GAME_SAVED.body);
  const ok = box.child("button3");
  ok.visible = true;
  setText(ok.child("buttonText"), GAME_SAVED.ok);
  ok.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  ok.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  ok.setHandler("onRelease", closeDialog);
  fadeInBox(box, DIALOG.fade);
}

// ---------- Opening and closing ----------

function build(clip) {
  view = { clip, menu: FIRST_MENU, saved: false, saving: false, changed: false, dialog: null, tapped: null };
  hud.hidePlay(true);
  // The art is drawn around its middle, which sits at the stage's middle (openPauseMenu F4:18843)
  clip.position.set(page.width / 2, page.height / 2);
  dropQuality(clip);
  wireMain(clip);
  for (const [menu, specs] of Object.entries(SETTINGS)) {
    wireTab(clip, menu, specs);
  }
  showMenu(FIRST_MENU);
  record("open");
}

// Closing keeps the settings with the save slot (closePauseMenu saves them, F4:18851)
function finish() {
  const changed = view?.changed;
  view = null;
  hud.hidePlay(false);
  hud.refresh();
  sound.play("sound_closeInterface");
  if (changed) {
    savePoint("settings");
  }
}

// Opens the pause menu (openPauseMenu F4:18813) over the world, closing any panel that is open. Nothing opens while the
// player is dead, or while a dialog, a room change or a cutscene holds the world. Returns whether it opened
export function openPause() {
  if (!canOpenPanel() || player.alive !== true) {
    return false;
  }
  openPanel(PANEL, { art: "pauseMenu", setup: build, close: finish });
  sound.play("sound_openInterface");
  return true;
}

// Esc with nothing open pauses (an open panel took the key first)
function keys() {
  if (input.escapePressed && !panelOpen() && openPause()) {
    input.escapePressed = false;
  }
}

export const pause = {
  open: openPause,
  close: closePanel,
  apply: applySettings,
  get isOpen() {
    return panelOpen(PANEL);
  },
  log,
};

export function initPause(owner) {
  page = owner;
  world.stage("interface", keys);
  hud.onOpen("pause", openPause);
  world.onReset(() => {
    view = null;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const pauseDebug = {
  // Opens the menu as Esc would
  pauseOpen() {
    openPause();
    return pauseDebug.pauseState();
  },

  // Presses a button of a menu ("main", "resume") as a mouse press would
  pausePress(menu, name) {
    view.clip.child(menu).child(name).handlers.onPress({ pointerType: "mouse", button: 0 });
    return pauseDebug.pauseState();
  },

  // What the menu shows: the menu in front, every button's words, the settings and where the world stands
  pauseState() {
    const open = view !== null;
    const menus = {};
    if (open) {
      for (const menu of MENUS) {
        const tab = view.clip.child(menu);
        menus[menu] = {};
        for (const [name, node] of Object.entries(tab.named)) {
          const words = node.named?.textClip?.child("settingText")?.text;
          if (words !== undefined && node.visible) {
            menus[menu][name] = words;
          }
        }
      }
    }
    return {
      open,
      menu: view?.menu ?? null,
      menus,
      dialog: Boolean(view?.dialog),
      saved: view?.saved ?? null,
      settings: story.settings ? { ...story.settings } : null,
      paused: world.paused,
      reasons: [...world.reasons],
      overlay: hud.overlayShown,
    };
  },

  pauseLog() {
    return log.map((each) => ({ ...each }));
  },
};
