// The menu clip's screens (main menu, Options, Instructions, Credits), the dialog box, the quick message and the save
// icon, ported from the original's menu functions (F6:1-12, 141-355, 380-403, 453-605, 830-946, 1039-1203). The menu
// is one clip of the original (sprite 1210) holding every one of these screens as a part of it. A part shows or hides
// as the player moves, and the clip stays until the player leaves for a screen that is not one of its parts.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const DEPTH_MENU = 850000;
const DEPTH_DIALOG = 950000;
const DEPTH_HUD = 900000;
const DEPTH_HUD_QUICK_MESSAGE = 1002;
const DEPTH_SAVE_ICON = 1600500;
const VERSION = "v1.2";
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
// Colors the original tints its button words with (F6:830-1160)
const HOVER = 15461097;
const GREYED = 1973778;
const PICKED = 15987699;
const EASE = "easeOutSine";
// Screen name -> the part of the menu clip it shows
export const PARTS = {
  main: "mainMenu",
  options: "options",
  instructions: "instructions",
  credits: "credits",
  select: "teamSelect",
  map: "mapScreen",
  custom: "skirmish",
  versusSetup: "skirmish",
  // The Watch list and the versus lobby draw on the menu's bare frame
  watch: null,
  versus: null,
};
// The screens that live in the menu clip, which stays while the player moves among them. Screens built later that
// draw on it add their names
export const MENU_SCREENS = new Set([...Object.keys(PARTS), "upgrades", "tutorial"]);
// The Watch and Versus buttons sit in the two slots the original's links to other games had: the clip placed under
// the name on the left becomes the button on the right
const LINK_SLOTS = { playMoreGames: ["WATCH", "watch"], playWarfare1917: ["VERSUS", "versus"] };
// The two buttons of a dialog sit this far either side of its middle (F6:176-178). Three stack: the backing is a fixed
// 150 high and the buttons sit 110, 75 and 40 above its bottom (F6:184-193)
const DIALOG_BUTTON_X = 50;
const DIALOG_PADDING = 30;
const DIALOG_THREE_HEIGHT = 150;
const DIALOG_THREE_Y = [110, 75, 40];
const DIALOG_BUTTON_ROOM = 40;
const DIALOG_BUTTON_Y = 45;
// The Instructions page's invisible press area over the tutorial picture sits at this depth of its clip
const TUTORIAL_PRESS_DEPTH = 6;
// The dark strip behind the Options quality row sits at this depth of the Options clip
const QUALITY_STRIP_DEPTH = 7;
// The saving icon (F6:1-12): 70 % size and opacity near the bottom middle
const SAVE_ICON = { x: 386, y: 460, scale: 0.7, alpha: 0.7 };

let page = null;

// Gives the module the page it works on. Called once by game.js
export function bindPage(owner) {
  page = owner;
  page.onMessage("save", () => refreshContinue());
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

function click() {
  sound.play(CLICK);
}

// ---------- Moving between the parts ----------

// What the original does to move from one part to another (loadOptions, optionsToMainMenu and the like, F6:496-591): the part
// leaving fades out, and the part arriving fades in after it, 0.8 seconds on
export function swap(menu, fromPart, toPart) {
  const out = fromPart ? menu.child(fromPart) : null;
  const into = toPart ? menu.child(toPart) : null;
  if (out && out !== into) {
    tweens.alphaTo(out, 0, fromPart === PARTS.main ? 0.8 : 0.6, EASE, 0, (clip) => {
      clip.visible = false;
    });
  }
  if (!into) {
    return;
  }
  if (toPart !== PARTS.main) {
    into.alpha = 0;
  }
  into.visible = true;
  tweens.alphaTo(into, 100, toPart === PARTS.main ? 0.8 : 0.6, EASE, 0.8);
}

// Leaving a menu screen for another screen: the menu clip goes when the next screen is not one of its parts
export function keepMenu(next) {
  if (!MENU_SCREENS.has(next)) {
    page.detach("menu");
  }
}

// The menu clip, made if it is not there, showing the part for this screen
export async function loadMenu(screen) {
  await page.lib.need([page.lib.exported("menu")]);
  const menu = page.attach("menu", DEPTH_MENU, "menu");
  const shown = PARTS[screen];
  for (const [name, part] of Object.entries(menu.named)) {
    part.visible = name === "bg" || name === shown;
  }
  // The backdrop takes presses so nothing under the menu hears them
  menu.child("bg").useHandCursor = false;
  menu.child("bg").setHandler("onRelease", () => {});
  setupMain(menu.child(PARTS.main));
  setupOptions(menu.child(PARTS.options));
  setupClose(menu.child(PARTS.credits));
  setupClose(menu.child(PARTS.instructions));
  setupTutorialPress(menu.child(PARTS.instructions));
  if (screen === "main") {
    fadeInMain(menu);
  }
  return menu;
}

// loadMenu (F6:453-480): the main menu fades in, its logo flashes white and settles, and the music rises
function fadeInMain(menu) {
  sound.menuMusic();
  const main = menu.child(PARTS.main);
  const logo = main.child("logo");
  main.alpha = 0;
  tweens.alphaTo(main, 100, 0.2, EASE);
  logo.alpha = 0;
  tweens.colorTo(logo, 16777215);
  tweens.alphaTo(logo, 100, 0.2, EASE);
  tweens.colorTo(logo, null, 0.8, EASE);
}

async function enterPart(screen) {
  const menu = menuClip();
  if (!menu) {
    await loadMenu(screen);
    return;
  }
  // The tutorial played over Instructions, which stayed shown under it (F6:578-606)
  if (page.previousScreen === "tutorial" && screen === "instructions") {
    return;
  }
  swap(menu, PARTS[page.previousScreen], PARTS[screen]);
}

function leavePart(owner, next) {
  keepMenu(next);
}

// ---------- The main menu ----------

// buttonSetup_mainMenu (F6:830-946) for each button of the main menu. The two link slots hold Watch and Versus
function setupMain(main) {
  main.child("versionNumber").text = VERSION;
  const actions = {
    continueCampaign: ["CONTINUE CAMPAIGN", askContinue],
    newCampaign: ["NEW CAMPAIGN", newCampaign],
    skirmish: ["CUSTOM BATTLE", () => open("custom")],
    options: ["OPTIONS", () => open("options")],
    howToPlay: ["INSTRUCTIONS", () => open("instructions")],
    credits: ["CREDITS", () => open("credits")],
  };
  for (const [name, [words, press]] of Object.entries(actions)) {
    wireButton(main.child(name), words, press);
  }
  for (const [name, [words, screen]] of Object.entries(LINK_SLOTS)) {
    const button = main.child(name);
    button.visible = true;
    wireButton(button, words, () => open(screen));
  }
  refreshContinue();
}

// A main menu button: its words, and the gold tint, swell and glow as the pointer passes (F6:843-862)
function wireButton(button, words, press) {
  const text = button.child("textClip");
  const field = text.child("btnText");
  const glow = button.child("highlights");
  field.autoSizeCenter();
  field.text = words;
  button.activated = true;
  button.setHandler("onRollOver", () => {
    if (!button.activated) {
      return;
    }
    sound.play(ROLL_OVER);
    tweens.colorTo(text, HOVER, 0.4, EASE);
    tweens.scaleTo(text, 110, 0.5);
    tweens.alphaTo(glow, 40, 0.4);
  });
  button.setHandler("onRollOut", () => {
    if (!button.activated) {
      return;
    }
    tweens.colorTo(text, null, 0.8, EASE);
    tweens.scaleTo(text, 100, 0.6);
    tweens.alphaTo(glow, 0, 0.4);
  });
  button.setHandler("onRelease", () => {
    if (button.activated) {
      press();
    }
  });
}

// Continue Campaign is greyed, and takes no presses, while there is no save. Until the bot has said, there is none
function refreshContinue() {
  const button = menuClip()?.child(PARTS.main)?.child("continueCampaign");
  if (!button) {
    return;
  }
  const on = Boolean(page.save);
  if (button.activated === on) {
    return;
  }
  button.activated = on;
  button.useHandCursor = on;
  tweens.colorTo(button.child("textClip"), on ? null : GREYED, 0);
}

function open(screen) {
  click();
  page.show(screen);
}

// The save's own side, mission and difficulty, as both questions name it (F6:273-324)
function savedCampaign(save) {
  const side = save.side === "british" ? "U.S FORCES" : save.side.toUpperCase();
  return `${side} CAMPAIGN - MISSION ${save.mission}\ron ${save.difficulty.toUpperCase()}`;
}

// dialog_continueCampaign (F6:297-324). The bot's word on the save is what it reads; before it speaks nothing is
// known, so a press waits. The press makes no click, as in the original; the ACCEPT button does
function askContinue() {
  const save = page.save;
  if (!save) {
    return;
  }
  dialog({
    heading: "CONTINUE CAMPAIGN?",
    body: `Continue playing:\r\r${savedCampaign(save)}\r\rAre you sure?`,
    buttons: [{ text: "ACCEPT", onPress: () => page.show("map") }, { text: "CANCEL" }],
  });
}

// New Campaign (F6:871-884): with a save, asks before the save is overwritten (F6:273-296). Without one, offers the
// tutorial: OK plays it and then goes on to the campaign choice, NO THANKS goes straight there (F6:336-354)
function newCampaign() {
  click();
  const save = page.save;
  if (save === undefined) {
    return;
  }
  if (save) {
    dialog({
      heading: "START A NEW CAMPAIGN?",
      body: `Starting a new campaign will overwrite\ryour previous save game:\r\r${savedCampaign(save)}\r\rAre you sure?`,
      buttons: [{ text: "ACCEPT", onPress: () => page.show("select") }, { text: "CANCEL" }],
    });
    return;
  }
  dialog({
    heading: "TUTORIAL",
    body: "This is your first time playing Warfare 1944, it is highly recommended\ryou watch the short tutorial presentation.",
    buttons: [
      {
        text: "OK",
        onPress: () => {
          page.fromInstructions = false;
          page.show("tutorial");
        },
      },
      { text: "NO THANKS", onPress: () => page.show("select") },
    ],
  });
}

// ---------- Options ----------

// buttonSetup_options (F6:1039-1161). The Visual Quality row is gone: its three buttons and the dark strip behind
// them are hidden, and nothing takes their place. Its label is not in the art
function setupOptions(options) {
  for (const name of ["low", "medium", "high"]) {
    options.child(name).visible = false;
  }
  options.at(QUALITY_STRIP_DEPTH).visible = false;
  const choices = {
    effectsOn: { words: "ON", other: "effectsOff", on: () => sound.effectsOn(), pick: () => sound.setEffects(true) },
    effectsOff: { words: "OFF", other: "effectsOn", on: () => !sound.effectsOn(), pick: () => sound.setEffects(false) },
    musicOn: {
      words: "ON",
      other: "musicOff",
      on: () => sound.musicOn(),
      pick() {
        sound.setMusic(true);
        sound.menuMusic(0);
      },
    },
    musicOff: { words: "OFF", other: "musicOn", on: () => !sound.musicOn(), pick: () => sound.setMusic(false) },
  };
  for (const [name, choice] of Object.entries(choices)) {
    wireChoice(options, name, choice);
  }
  // buttonSetup_optionsBack (F6:1162-1170): the settings are kept as each choice is made, so DONE only goes back
  const done = options.child("backButton");
  done.child("buttonText").text = "DONE";
  done.setHandler("onRelease", () => {
    click();
    page.show("main");
  });
}

function wireChoice(options, name, choice) {
  const button = options.child(name);
  const text = button.child("textClip");
  text.child("btnText").autoSizeCenter();
  text.child("btnText").text = choice.words;
  if (choice.on()) {
    tweens.colorTo(text, PICKED, 0);
  }
  button.setHandler("onRelease", () => {
    click();
    tweens.colorTo(text, PICKED, 0);
    tweens.colorTo(options.child(choice.other).child("textClip"), null, 0);
    choice.pick();
  });
  button.setHandler("onRollOver", () => {
    sound.play(ROLL_OVER);
    tweens.scaleTo(text, 110, 0.5);
  });
  button.setHandler("onRollOut", () => tweens.scaleTo(text, 100, 0.6));
}

// The back button of Credits and Instructions (their clip actions, sprites 1085 and 1088): CLOSE, back to the main menu
function setupClose(part) {
  const close = part.child("backButton");
  close.child("buttonText").text = "CLOSE";
  close.setHandler("onRollOver", () => sound.play(ROLL_OVER));
  close.setHandler("onRelease", () => {
    click();
    page.show("main");
  });
}

// The Instructions page's WATCH TUTORIAL: an invisible press area over the tutorial picture. The tutorial ends back on
// this page rather than going on to the campaign choice (F6:578-606)
function setupTutorialPress(instructions) {
  const press = instructions.at(TUTORIAL_PRESS_DEPTH);
  press.setHandler("onRollOver", () => sound.play(ROLL_OVER));
  press.setHandler("onRelease", () => {
    click();
    page.fromInstructions = true;
    page.show("tutorial");
  });
}

// ---------- The dialog box ----------

// A flash.js clip's width or height made this many pixels, as Flash's _width and _height do
function sizeTo(clip, width, height) {
  const size = clip.getLocalBounds();
  if (width !== null) {
    clip.scale.x = width / size.width;
  }
  if (height !== null) {
    clip.scale.y = height / size.height;
  }
}

// showDialogBox (F6:141-216): a heading and some words over a darkened screen, with one, two or three buttons. Each
// button closes the dialog, after a click and its onPress
export async function dialog({ heading, body, buttons = [] }) {
  await page.lib.need([page.lib.exported("dialogBox")]);
  const box = page.attach("dialogBox", DEPTH_DIALOG, "dialogBox");
  const [black, backing, texts] = ["blackOut", "backing", "textBoxes"].map((name) => box.child(name));
  const slots = ["button1", "button2", "button3"].map((name) => box.child(name));
  // The darkened screen takes presses, so nothing behind the dialog hears them
  black.useHandCursor = false;
  black.setHandler("onRelease", () => {});
  for (const part of [black, backing, texts, ...slots]) {
    part.alpha = 0;
  }
  const title = texts.child("headingText");
  const words = texts.child("bodyText");
  title.autoSizeCenter();
  words.autoSizeCenter(true);
  title.text = heading;
  words.text = body ?? "";
  const three = buttons.length === 3;
  let height = title.box.height + words.box.height + 20 + (buttons.length ? DIALOG_BUTTON_ROOM : 0);
  if (three) {
    height = DIALOG_THREE_HEIGHT;
  }
  sizeTo(backing, words.box.width + DIALOG_PADDING, height);
  slots.forEach((slot, index) => {
    slot.visible = index < buttons.length;
  });
  buttons.forEach((entry, index) => {
    const y = height - (three ? DIALOG_THREE_Y[index] : DIALOG_BUTTON_Y);
    placeButton(box, slots[index], entry, { x: pairX(buttons.length, index), y });
  });
  box.x = 400;
  box.y = 150;
  tweens.alphaTo(black, 60, 0.8, EASE);
  tweens.alphaTo(backing, 100, 0.6, EASE);
  tweens.alphaTo(texts, 100, 0.6, EASE, 0.4);
  return box;
}

// A lone button stays in the middle; two sit either side of it
function pairX(count, index) {
  if (count !== 2) {
    return 0;
  }
  return index ? DIALOG_BUTTON_X : -DIALOG_BUTTON_X;
}

function placeButton(box, button, entry, spot) {
  button.child("buttonText").text = entry.text;
  button.x = spot.x;
  button.y = spot.y;
  tweens.alphaTo(button, 100, 0.6, EASE, 0.4);
  button.setHandler("onRollOver", () => sound.play(ROLL_OVER));
  button.setHandler("onRelease", () => {
    if (box.closing) {
      return;
    }
    box.closing = true;
    click();
    entry.onPress?.();
    closeDialog(box);
  });
}

// closeDialogBox (F6:217-224)
function closeDialog(box) {
  tweens.alphaTo(box, 0, 0.1, EASE, 0, (gone) => gone.destroy({ children: true }));
}

// ---------- Quick messages ----------

// showQuickMessage (F6:380-403): a line of words on a dark plate near the top of the screen, or in the middle and
// bigger, that fades in and out. It sits in the HUD when there is one
export async function quickMessage(text, position) {
  await page.lib.need([page.lib.exported("dialog_quickMessage")]);
  const hud = page.root.children.find((child) => child.label === "hud" && !child.destroyed && child.attach);
  const note = page.lib.makeExported("dialog_quickMessage");
  if (hud) {
    hud.child("quickMessage")?.removeMovieClip();
    hud.attach(note, "quickMessage");
  } else {
    page.detach("quickMessage");
    note.label = "quickMessage";
    note.zIndex = DEPTH_HUD + DEPTH_HUD_QUICK_MESSAGE;
    page.root.addChild(note);
  }
  note.alpha = 0;
  note.x = 400;
  const centered = position === "center";
  note.y = centered ? 210 : 60;
  note.scale.set(centered ? 1.25 : 1);
  const line = note.child("messageText");
  line.autoSizeCenter();
  line.text = text;
  sizeTo(note.child("backing"), line.box.width + DIALOG_PADDING, null);
  tweens.alphaTo(note, 100, 0.6);
  tweens.alphaTo(note, 0, 1, EASE, text.length * 0.25);
  return note;
}

// ---------- The saving icon ----------

// showSavingGameIcon (F6:1-12): "GAME PROGRESS SAVED" shows for its 85 frames and takes itself away. The upgrade screen's
// saves (an upgrade bought, Done) make the icon invisible instead (faint). A new icon replaces one still showing
export async function savedIcon(faint = false) {
  await page.lib.need([page.lib.exported("saveAnim")]);
  const icon = page.attach("saveAnim", DEPTH_SAVE_ICON, "saveAnim");
  icon.scale.set(SAVE_ICON.scale);
  icon.alpha = faint ? 0 : SAVE_ICON.alpha;
  icon.position.set(SAVE_ICON.x, SAVE_ICON.y);
  return icon;
}

export const screens = {
  main: { enter: () => enterPart("main"), leave: leavePart },
  options: { enter: () => enterPart("options"), leave: leavePart },
  instructions: { enter: () => enterPart("instructions"), leave: leavePart },
  credits: { enter: () => enterPart("credits"), leave: leavePart },
};
