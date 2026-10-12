// The menu clip's screens (main menu, Options, Instructions, Credits), the dialog box and the quick message, ported
// from the original's menu functions (F5:114-246, 293-412, 623-722, 818-950). The menu is one clip of the original
// (sprite 1036) holding every one of these screens as a part of it. A part shows or hides as the player moves, and
// the clip stays until the player leaves for a screen that is not one of its parts.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const DEPTH_MENU = 850000;
const DEPTH_DIALOG = 950000;
const DEPTH_HUD = 900000;
const DEPTH_HUD_QUICK_MESSAGE = 1002;
const VERSION = "v1.2";
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
// Colors the original tints its button words with (F5:623-950)
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
export const MENU_SCREENS = new Set([...Object.keys(PARTS), "upgrades"]);
// The Watch and Versus buttons take Play More Games' row, one each side of the column's middle. The next row down
// would sit on the frame's bottom edge
const EXTRA_BUTTONS = { watch: ["WATCH", -1], versus: ["VERSUS", 1] };
const EXTRA_OFFSET = 70;
// The two buttons of a dialog sit this far either side of its middle when there are two (F5:136-141)
const DIALOG_BUTTON_X = 50;
const DIALOG_PADDING = 30;
// The picture of the words VISUAL QUALITY over the options row that is hidden
const QUALITY_LABEL = 839;
// The dialog's heading and words (characters 1038 and 1039) use a font the game does not carry, so a player sees the
// machine's own sans serif there
const DEVICE_TEXTS = [1038, 1039];
const DEVICE_FONT = '"Noto Sans", "Segoe UI", "Open Sans", Arial, sans-serif';

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

// What the original does to move from one part to another (loadOptions, optionsToMainMenu and the like): the part
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
  if (screen === "main") {
    fadeInMain(menu);
  }
  return menu;
}

// loadMenu (F5:293-312): the main menu fades in, its logo flashes white and settles, and the music rises
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
  swap(menu, PARTS[page.previousScreen], PARTS[screen]);
}

function leavePart(owner, next) {
  keepMenu(next);
}

// ---------- The main menu ----------

// buttonSetup_mainMenu (F5:623-722) for each button of the main menu. Play More Games stays hidden. Watch and Versus
// are copies of a button of the column, in its place
function setupMain(main) {
  main.child("versionNumber").text = VERSION;
  const spare = main.child("playMoreGames");
  spare.visible = false;
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
  for (const [name, [words, side]] of Object.entries(EXTRA_BUTTONS)) {
    const button = main.attach(page.lib.make(spare.charId), name);
    button.position.set(spare.x + EXTRA_OFFSET * side, spare.y);
    wireButton(button, words, () => open(name));
  }
  refreshContinue();
}

// A main menu button: its words, and the gold tint and swell as the pointer passes (F5:640-651)
function wireButton(button, words, press) {
  const text = button.child("textClip");
  const field = text.child("btnText");
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
  });
  button.setHandler("onRollOut", () => {
    if (!button.activated) {
      return;
    }
    tweens.colorTo(text, null, 0.8, EASE);
    tweens.scaleTo(text, 100, 0.6);
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

// The bot's word on the save is what the dialogs read; before it speaks nothing is known, so a press waits
function askContinue() {
  const save = page.save;
  if (!save) {
    return;
  }
  dialog({
    heading: "CONTINUE CAMPAIGN?",
    body: `Continue playing:\r\r${save.side.toUpperCase()} CAMPAIGN - MISSION ${save.mission}\r\rAre you sure?`,
    buttons: [{ text: "ACCEPT", onPress: () => page.show("map") }, { text: "CANCEL" }],
  });
}

// New Campaign (F5:652-668): with a save, asks before the save is overwritten. Without one, the campaign choice
// opens at once and the dialog says a save was made
function newCampaign() {
  click();
  if (page.save === undefined) {
    return;
  }
  const save = page.save;
  if (save) {
    dialog({
      heading: "START A NEW CAMPAIGN?",
      body: `Starting a new campaign will overwrite\ryour previous save game:\r\r${save.side.toUpperCase()} CAMPAIGN - MISSION ${save.mission}\r\rAre you sure?`,
      buttons: [{ text: "ACCEPT", onPress: () => page.show("select") }, { text: "CANCEL" }],
    });
    return;
  }
  dialog({
    heading: "NEW CAMPAIGN",
    body: "A new save game has been created.\r\rProgress will be saved for you\rautomatically during the campaign.",
    buttons: [{ text: "OK" }],
  });
  page.show("select");
}

// ---------- Options ----------

// buttonSetup_options (F5:818-934). The Visual Quality row is gone: its label, its three buttons and the dark strip
// behind them are hidden, and nothing takes their place
function setupOptions(options) {
  for (const name of ["low", "medium", "high"]) {
    options.child(name).visible = false;
  }
  options.at(7).visible = false;
  for (const slot of options.slots.values()) {
    if (slot.node.charId === QUALITY_LABEL) {
      slot.node.visible = false;
    }
  }
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

// The back button of Credits and Instructions (sprites 975 and 990): CLOSE, back to the main menu
function setupClose(part) {
  const close = part.child("backButton");
  close.child("buttonText").text = "CLOSE";
  close.setHandler("onRollOver", () => sound.play(ROLL_OVER));
  close.setHandler("onRelease", () => {
    click();
    page.show("main");
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

// showDialogBox (F5:114-166): a heading and some words over a darkened screen, with one or two buttons. lines is
// the heading then the lines of the words. Each button closes the dialog, after its onPress and a click
export async function dialog({ heading, body, lines, buttons = [] }) {
  if (lines) {
    heading = lines[0];
    body = lines.slice(1).join("\r");
  }
  await page.lib.need([page.lib.exported("dialogBox")]);
  for (const id of DEVICE_TEXTS) {
    page.lib.data.texts[id].font = DEVICE_FONT;
  }
  const box = page.attach("dialogBox", DEPTH_DIALOG, "dialogBox");
  const [black, backing, texts] = ["blackOut", "backing", "textBoxes"].map((name) => box.child(name));
  const slots = [box.child("button1"), box.child("button2")];
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
  const buttonRoom = buttons.length ? 40 : 0;
  const height = title.box.height + words.box.height + 20 + buttonRoom;
  sizeTo(backing, words.box.width + DIALOG_PADDING, height);
  slots.forEach((slot, index) => {
    slot.visible = index < buttons.length;
  });
  buttons.forEach((entry, index) => placeButton(box, slots[index], entry, { pair: buttons.length === 2, index, height }));
  box.x = 400;
  box.y = 150;
  tweens.alphaTo(black, 60, 0.8, EASE);
  tweens.alphaTo(backing, 100, 0.6, EASE);
  tweens.alphaTo(texts, 100, 0.6, EASE, 0.4);
  return box;
}

function placeButton(box, button, entry, { pair, index, height }) {
  button.child("buttonText").text = entry.text;
  if (pair) {
    button.x = index ? DIALOG_BUTTON_X : -DIALOG_BUTTON_X;
  }
  button.y = height - 45;
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

// closeDialogBox (F5:167-173)
function closeDialog(box) {
  tweens.alphaTo(box, 0, 0.1, EASE, 0, (gone) => gone.destroy({ children: true }));
}

// ---------- Quick messages ----------

// showQuickMessage (F5:222-246): a line of words on a dark plate near the top of the screen, or in the middle and
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

export const screens = {
  main: { enter: () => enterPart("main"), leave: leavePart },
  options: { enter: () => enterPart("options"), leave: leavePart },
  instructions: { enter: () => enterPart("instructions"), leave: leavePart },
  credits: { enter: () => enterPart("credits"), leave: leavePart },
};
