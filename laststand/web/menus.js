// The main menu and the slot panels (setupMenu F4:3532, cycleMenus F4:3564, openNewGame F4:3637, openContinue F4:3804,
// menuButtonSetup F4:3864, decorateMenuHead F4:3607; sprite menu 6679 with mainMenu 6494 over the skyline 6462).
//
// One `menu` clip holds every menu page the original keeps in it (main, newGame, continueGame, selectMode, credits); a
// page shows by turning the others off and fading in over 0.4 s. The clip stays while the screens "menu", "slots" and
// "mode" take turns, and goes when any other screen comes.
//
// The slots live on the Red bot, so a page that lists them asks for them each time it opens: CONTINUE is greyed until
// the answer says a slot holds a character, and checked again at every opening (so a Hardcore wipe greys it). A slot
// panel says LOADING and cannot be pressed until its answer comes, so a press never lands on a slot the page does not
// know yet. The Survival Kit and Dead Zone ads, the login badge and the social icons are not drawn (the art leaves
// the login and social parts out; the two ads are hidden here), and neither is the Survival Kit badge on a slot, since
// every character has the kit.
import { BlurFilter } from "./vendor/pixi.min.mjs";
import { makeFilter } from "./flash.js";
import { musicDirector } from "./director.js";
import { showCredits } from "./ending.js";
import { setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { fadeInBox, fadeOutBox, finger, setAlpha, setColor, tint } from "./panels.js";
import { colourOf, goto } from "./rig.js";
import { DONE, listSlots, loadSlot, OVERTAKEN, STALE, wipeSlot } from "./save.js";
import { sound } from "./sound.js";

// The screens that share the menu clip
const KEEP = new Set(["menu", "slots", "mode"]);
// The screens that leave the menu's music playing: character creation goes on under it
const MUSIC_KEEP = new Set(["menu", "slots", "mode", "create"]);
const MAIN = "main";
// The pages a menu shows, and the parts of the art that are never shown
const PAGES = ["main", "newGame", "continueGame", "selectMode"];
const HIDDEN_PARTS = ["credits", "premium", "armorAGI", "login", "purchasing", "allowSave", "allowSaveFailed"];
// The parts of the main page that are ads (the Dead Zone one and the Survival Kit one, with the bands behind them)
const AD_IDS = new Set([6472, 6489, 6493, 6488]);
const SLOT_COUNT = 3;
// The art draws six slot panels; the original fills three
const SLOT_ART = 6;
const PAGE_FADE = 0.4;
const DIALOG_FADE = 0.6;
const DIALOG_SHADE = 0.6;
const DIALOG_OUT = 0.1;
const SLOT_ALPHA = 0.7;
const SLOT_HOVER = 0x333333;
const SLOT_HOVER_SECONDS = 1;
const EMPTY_HEAD = 0x444444;
const GREY_TEXT = "#222222";
// A button's blur: rolled over it sharpens to 1, rolled off it softens to 3.5 after a short wait (menuButtonSetup)
const BLUR = { over: { amount: 1, seconds: 0.8, delay: 0 }, out: { amount: 3.5, seconds: 2, delay: 0.2 } };
const BLUR_PASSES = 2;
// The blur the art places the buttons with
const REST_BLUR = 2;
const MAIN_WORDS = { continueGame: "CONTINUE", newGame: "NEW STORY", credits: "CREDITS" };
const MODE_WORDS = { runAndGun: "RUN & GUN", survivor: "SURVIVOR" };
// The mode cards of the art, in order, and the mode each one starts
const CARDS = { runGun: "runAndGun", survivor: "survivor" };
// The two boxes under the title, and the story flag each one sets
const OPTIONS = { headShotsOnly: "headshots", hardcore: "hardcore" };
const MODE_PROMPT = "SELECT A GAME MODE";
// The description bar's lines. The art's own text fields keep the original's wording; the two cards that promised more
// than the game does say what it does
const MODE_LINES = {
  runGun: "AMMO IS MORE PLENTIFUL, CHARACTER DOES NOT NEED TO EAT OR SLEEP.",
  survivor: "CHARACTER NEEDS FOOD AND SLEEP TO SURVIVE. AMMUNITION IS RARER.",
  hardcore: "[PREMIUM CONTENT] ENABLES HARDCORE MODE: CHARACTER ONLY HAS ONE LIFE.",
  headShotsOnly: "[PREMIUM CONTENT] ENABLES HEADSHOTS ONLY MODE: AIM FOR THE HEAD.",
};
// A card at rest and lit: backing and picture alpha in percent, and the colour of its name
const CARD_REST = { backing: 30, pic: 20, name: 0x444444 };
const CARD_LIT = { backing: 70, pic: 60, name: 0xffffff };
const CARD_FADE = 1;
const LOADING = "LOADING";
const UNAVAILABLE = "SAVES UNAVAILABLE";
const OVERWRITE = {
  heading: "START A NEW STORY",
  body: "THIS WILL OVERWRITE THE EXISTING\rCHARACTER IN THIS SAVE GAME\r\rARE YOU SURE?",
};
const MOST_RECORDED = 100;

let page = null;
let depth = 0;
// The menu now: { clip, page, slots, dialog, tapped, busy, blurs, continueLabel, canContinue, ink, mode }
// (mode is the Select Mode page's { slot, lit, headShotsOnly, hardcore })
let view = null;
// What the menu opened, pressed and loaded, newest last, for checks
const log = [];

function record(kind, extra = {}) {
  log.push({ kind, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

function upper(text) {
  return String(text ?? "").toUpperCase();
}

// ---------- The save slots ----------

// The three slots' summaries (null for an empty one), or null when the bot can't be reached
async function readSlots() {
  try {
    const hub = await page.hubReady;
    if (!hub?.api) {
      throw new Error("There is no connection to ActivityHub");
    }
    return await listSlots();
  } catch (e) {
    console.warn("Union City: couldn't read the save slots", e);
    return null;
  }
}

function hasCharacter(slots) {
  return Array.isArray(slots) && slots.some(Boolean);
}

// ---------- Buttons ----------

// A part acts on a mouse press, where a finger acts on lifting it, so a touch that starts on one and slides away does
// nothing. Pressing plays the click (click: null leaves the sound to press), rolling over plays the roll sound for a
// mouse. press is told whether a finger made it
function wire(node, { press, over = null, out = null, click = "sound_interfaceClick" }) {
  node.setHandler("onRollOver", (event) => {
    if (!finger(event) && !view?.dialog) {
      sound.play("sound_interfaceOver");
      over?.();
    }
  });
  node.setHandler("onRollOut", (event) => {
    if (!finger(event)) {
      out?.();
    }
  });
  node.setHandler("onPress", (event) => {
    if (!view || view.dialog || view.busy) {
      return;
    }
    if (click) {
      sound.play(click);
    }
    if (finger(event)) {
      view.tapped = node;
    } else {
      press(false);
    }
  });
  node.setHandler("onRelease", (event) => {
    if (!finger(event) || !view || view.tapped !== node) {
      return;
    }
    view.tapped = null;
    press(true);
  });
  node.setHandler("onReleaseOutside", () => {
    if (view) {
      view.tapped = null;
    }
  });
}

// Moves a button's blur to an amount over some seconds after a wait, from wherever it is now
function blurTo(button, { amount, seconds, delay }) {
  if (!view) {
    return;
  }
  const from = view.blurs.get(button)?.now ?? 0;
  const frames = Math.max(1, Math.round(seconds * page.lib.fps));
  view.blurs.set(button, {
    from,
    to: amount,
    now: from,
    wait: Math.round(delay * page.lib.fps),
    age: 0,
    frames,
    done: false,
  });
}

// A button's blur filter at an amount, keeping the other filters the art placed on it (its glow)
function setBlur(button, amount) {
  const list = [...(button.filters ?? [])];
  const at = list.findIndex((each) => each instanceof BlurFilter);
  const spec = { type: "blur", x: amount, y: amount, passes: BLUR_PASSES };
  const made = makeFilter(spec, at >= 0 ? list[at] : undefined, page.scale);
  if (at >= 0) {
    list.splice(at, 1, ...(made ? [made] : []));
  } else if (made) {
    list.unshift(made);
  }
  button.filters = list.length ? list : null;
}

function stepBlurs() {
  for (const [button, blur] of view?.blurs ?? []) {
    if (button.destroyed) {
      view.blurs.delete(button);
      continue;
    }
    if (blur.done) {
      continue;
    }
    if (blur.wait > 0) {
      blur.wait -= 1;
      continue;
    }
    blur.age = Math.min(blur.frames, blur.age + 1);
    blur.now = blur.from + (blur.to - blur.from) * Math.sin((blur.age / blur.frames) * (Math.PI / 2));
    setBlur(button, blur.now);
    blur.done = blur.age >= blur.frames;
  }
}

// The art calls menuButtonSetup(name) as each of the main page's buttons loads: its words, its roll and its press
function menuButtonSetup(node, name) {
  const words = MAIN_WORDS[name];
  if (!words) {
    return;
  }
  setText(node.child("butLabel"), words);
  const actions = {
    continueGame: () => {
      if (view.canContinue) {
        show("slots", { mode: "continue" });
      }
    },
    newGame: () => show("slots", { mode: "new" }),
    credits: openCredits,
  };
  view.blurs.set(node, { now: REST_BLUR, done: true });
  wire(node, {
    press: actions[name],
    over: () => blurTo(node, BLUR.over),
    out: () => blurTo(node, BLUR.out),
  });
  if (name === "continueGame") {
    view.continueLabel = node.child("butLabel");
    view.ink = view.continueLabel.def?.color ?? null;
  }
}

export const MENU_LOAD_CALLS = { menuButtonSetup };

// CREDITS: the credits roll over the menu, which stays where it is
async function openCredits() {
  record("credits");
  await showCredits(true);
}

// ---------- Pages ----------

// Turns the other pages off and fades one in (cycleMenus)
function showPage(name) {
  for (const each of PAGES) {
    view.clip.child(each).visible = each === name;
  }
  const part = view.clip.child(name);
  part.alpha = 0;
  tween(part, "alpha", 100, PAGE_FADE, { ease: "easeOutSine" });
  view.page = name;
  record("page", { name });
  // The new page's buttons sit where the old page's were, so the second click of a double click presses nothing
  input.shutByClick();
}

// CONTINUE shows greyed until a slot is known to hold a character
function paintContinue() {
  const label = view?.continueLabel;
  if (!label || label.destroyed) {
    return;
  }
  const on = hasCharacter(view.slots);
  view.canContinue = on;
  setColor(label, on ? view.ink : GREY_TEXT);
}

async function refreshContinue() {
  const mine = view;
  const slots = await readSlots();
  if (view !== mine) {
    return;
  }
  view.slots = slots;
  paintContinue();
  record("continue", { enabled: hasCharacter(slots) });
}

// Builds the menu clip, once for as long as the menu screens last (setupMenu)
async function ensureMenu() {
  if (view?.clip && !view.clip.destroyed) {
    return;
  }
  await page.lib.need([page.lib.exported("menu")]);
  view = {
    clip: null,
    page: null,
    slots: null,
    canContinue: false,
    dialog: null,
    tapped: null,
    busy: false,
    blurs: new Map(),
    continueLabel: null,
    ink: null,
  };
  const clip = page.attach("menu", depth, "menu");
  view.clip = clip;
  for (const name of HIDDEN_PARTS) {
    clip.child(name).visible = false;
  }
  for (const part of clip.child(MAIN).children) {
    if (AD_IDS.has(part.charId)) {
      part.visible = false;
    }
  }
  paintContinue();
  musicDirector.menu();
  record("open");
}

// ---------- Slot panels ----------

// A part drawn all in one colour, when the saved look has that part (a bald head has no hair colour to show)
function paint(node, colour) {
  if (node) {
    tint(node, colour);
  }
}

// A head as the slot panels show it (decorateMenuHead): the saved look on the head and neck, or a grey shape for an
// empty slot. slot is the panel clip; look is the summary's look, or null
export function decorateMenuHead(slot, look) {
  const head = slot.child("head");
  const neck = slot.child("neck");
  if (!look) {
    tint(head, EMPTY_HEAD);
    tint(neck, EMPTY_HEAD);
    return;
  }
  tint(head, null);
  tint(neck, null);
  const sex = look.sex === "female" ? "female" : "male";
  const hair = String(look.hair ?? "cropped");
  goto(head.child("skin"), sex === "female" ? "head2" : "head1");
  goto(head.child("accessories"), look.hat ?? "none");
  goto(head.child("accessoriesFace"), look.face ?? "none");
  goto(head.child("accessoriesEyes"), look.eyes ?? "none");
  goto(head.child("hair"), /^(male|female)_/.test(hair) ? hair : `${sex}_${hair}`);
  goto(head.child("facialHair"), look.facialHair ?? "none");
  const skin = colourOf(look.skin, null);
  const hairColour = colourOf(look.hairColour, null);
  if (skin !== null) {
    paint(head.child("skin")?.child("skin"), skin);
    paint(neck.child("skin"), skin);
  }
  if (hairColour !== null) {
    paint(head.child("hair")?.child("base"), hairColour);
    paint(head.child("facialHair")?.child("base"), hairColour);
  }
}

function fillSlot(panel, summary) {
  const words = {
    charName: summary ? upper(summary.name) : "EMPTY",
    charDetails: summary ? `LEVEL - ${summary.level}` : "",
    charDay: summary ? `${upper(summary.area)} - DAY ${summary.day}` : "",
    gameMode: summary ? (MODE_WORDS[summary.mode] ?? upper(summary.mode)) : "",
    hardcore: summary?.hardcore ? "HARDCORE" : "",
  };
  for (const [field, text] of Object.entries(words)) {
    setText(panel.child(field), text);
  }
  panel.child("headShotsOnly").visible = Boolean(summary?.headshots);
  panel.child("premium").visible = false;
  decorateMenuHead(panel, summary?.look ?? null);
}

// The slots' answer on a page: each panel says who is in it, or that the bot can't be reached
function paintSlots(name, slots) {
  const panels = view.clip.child(name).child("panels");
  for (let n = 1; n <= SLOT_COUNT; n += 1) {
    const panel = panels.child(`slot${n}`);
    if (slots) {
      fillSlot(panel, slots[n - 1]);
    } else {
      setText(panel.child("charName"), UNAVAILABLE);
    }
  }
  view.slots = slots;
  paintContinue();
}

function slotsWaiting(name) {
  const panels = view.clip.child(name).child("panels");
  for (let n = SLOT_ART; n > SLOT_COUNT; n -= 1) {
    panels.child(`slot${n}`).visible = false;
  }
  for (let n = 1; n <= SLOT_COUNT; n += 1) {
    const panel = panels.child(`slot${n}`);
    setText(panel.child("charName"), LOADING);
    for (const field of ["charDetails", "charDay", "gameMode", "hardcore"]) {
      setText(panel.child(field), "");
    }
    panel.child("headShotsOnly").visible = false;
    panel.child("premium").visible = false;
    decorateMenuHead(panel, null);
  }
}

// A slot panel lights up under the pointer, fading to a dark grey over a second (colorTo)
function lightSlot(panel, on) {
  const backing = panel.child("backing");
  backing.flatColour = SLOT_HOVER;
  tween(backing, "flat", on ? 1 : 0, SLOT_HOVER_SECONDS);
}

function wireSlots(name, mode) {
  const panels = view.clip.child(name).child("panels");
  for (let n = 1; n <= SLOT_COUNT; n += 1) {
    const panel = panels.child(`slot${n}`);
    const backing = panel.child("backing");
    backing.alpha = SLOT_ALPHA;
    backing.scriptAlpha = SLOT_ALPHA;
    wire(panel, {
      press: () => pressSlot(n, mode),
      over: () => lightSlot(panel, true),
      out: () => lightSlot(panel, false),
    });
  }
  const heading = view.clip.child(name).child("continueText");
  if (heading) {
    setText(heading, "CONTINUE");
  }
  const back = view.clip.child(name).child("back");
  wire(back, { press: () => show("menu"), click: "sound_interfaceClickBack" });
}

// A slot was pressed: an empty one starts a story, an occupied one asks first (New Story) or loads (Continue)
function pressSlot(n, mode) {
  const summary = view.slots?.[n - 1];
  if (!view.slots) {
    return;
  }
  record("slot", { n, mode, occupied: Boolean(summary) });
  if (mode === "continue") {
    if (summary) {
      continueSlot(n);
    }
  } else if (summary) {
    askOverwrite(n);
  } else {
    startStory(n);
  }
}

// ---------- Dialogs ----------

function closeDialog() {
  if (view) {
    fadeOutBox(view.dialog, DIALOG_OUT);
    view.dialog = null;
  }
}

function dialogButton(box, name, words, action) {
  const button = box.child(name);
  button.visible = true;
  setText(button.child("buttonText"), words);
  button.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

// The box over the menu (showDialogBox F4:20000) with a heading, words and its buttons ({ button, words, action } each).
// Everything behind it is shut off until a button is pressed
function showDialog(heading, body, buttons) {
  closeDialog();
  const box = page.lib.makeExported("dialogBox");
  box.position.set(page.width / 2, page.height / 2);
  view.clip.attach(box, "dialogBox");
  view.dialog = box;
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  shade.scriptAlpha = DIALOG_SHADE;
  shade.alpha = DIALOG_SHADE;
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), heading);
  setText(box.child("textBoxes").child("bodyText"), body);
  for (const { button, words, action } of buttons) {
    dialogButton(box, button, words, action);
  }
  fadeInBox(box, DIALOG_FADE);
  record("dialog", { heading });
}

function askOverwrite(n) {
  showDialog(OVERWRITE.heading, OVERWRITE.body, [
    {
      button: "button1",
      words: "YES",
      action: () => {
        closeDialog();
        startStory(n);
      },
    },
    { button: "button2", words: "NO", action: closeDialog },
  ]);
}

// A box with its words and one OK
function tell({ heading, body }) {
  showDialog(heading, body, [{ button: "button3", words: "OK", action: closeDialog }]);
}

function askFailed(heading) {
  tell({ heading, body: "\rTHE SAVE SLOTS COULDN'T BE REACHED.\rTRY AGAIN IN A MOMENT." });
}

// ---------- Select Mode ----------

function modePage() {
  return view.clip.child("selectMode");
}

function describe(text) {
  setText(modePage().child("desc"), text);
}

// A card lit (rolled over, or tapped once) or put back to rest: its backing and picture fade over a second, its name
// changes colour at once
function paintCard(name, look) {
  const card = modePage().child(name);
  tween(card.child("backing"), "alpha", look.backing, CARD_FADE, { ease: "easeOutExpo" });
  tween(card.child("pic"), "alpha", look.pic, CARD_FADE, { ease: "easeOutExpo" });
  tint(card.child("txt"), look.name);
}

function lightCard(name) {
  if (view.mode.lit === name) {
    return;
  }
  dimCard(view.mode.lit);
  view.mode.lit = name;
  paintCard(name, CARD_LIT);
  describe(MODE_LINES[name]);
}

function dimCard(name) {
  if (!name || view.mode.lit !== name) {
    return;
  }
  view.mode.lit = null;
  paintCard(name, CARD_REST);
  describe(MODE_PROMPT);
}

// A card was pressed: it starts the story in that mode. A finger's first tap lights the card and shows its line (a
// finger can't roll over); tapping the lit card picks it
function pressCard(name, touched) {
  if (touched && view.mode.lit !== name) {
    lightCard(name);
    return;
  }
  const { slot, hardcore, headShotsOnly } = view.mode;
  const choice = { mode: CARDS[name], hardcore, headshots: headShotsOnly, slot };
  record("mode", choice);
  show("create", choice);
}

function setBox(name, on) {
  goto(modePage().child("premium").child(name), on ? "on" : "off");
}

// A box was pressed: it flips and says so. A finger can't roll over, so its tap also shows the box's line
function pressBox(name, touched) {
  view.mode[name] = !view.mode[name];
  setBox(name, view.mode[name]);
  sound.play(view.mode[name] ? "sound_interfaceClick" : "sound_interfaceClickBack");
  if (touched) {
    describe(MODE_LINES[name]);
  }
  record("box", { name, on: view.mode[name] });
}

// Everything on the page starts over at each visit: both boxes off and unchecked, both cards at rest
function resetMode(slot) {
  view.mode = { slot, lit: null, headShotsOnly: false, hardcore: false };
  const page = modePage();
  setAlpha(page.child("premium"), 1);
  for (const name of Object.keys(OPTIONS)) {
    setBox(name, false);
  }
  for (const name of Object.keys(CARDS)) {
    const card = page.child(name);
    for (const part of ["backing", "pic"]) {
      stopTweens(card.child(part));
      setAlpha(card.child(part), CARD_REST[part] / 100);
    }
    tint(card.child("txt"), CARD_REST.name);
  }
  describe(MODE_PROMPT);
}

function wireMode() {
  const page = modePage();
  for (const name of Object.keys(CARDS)) {
    wire(page.child(name), {
      press: (touched) => pressCard(name, touched),
      over: () => lightCard(name),
      out: () => dimCard(name),
    });
  }
  for (const name of Object.keys(OPTIONS)) {
    wire(page.child("premium").child(name), {
      press: (touched) => pressBox(name, touched),
      over: () => describe(MODE_LINES[name]),
      out: () => describe(MODE_PROMPT),
      click: null,
    });
  }
  wire(page.child("back"), { press: () => show("menu"), click: "sound_interfaceClickBack" });
}

// ---------- Starting and loading ----------

// New Story in a slot (createNewSaveGame): an occupied slot is emptied first, then the mode is chosen. A slot another
// device saved since it was listed is listed again, with the box that says so
async function startStory(n) {
  const mine = view;
  mine.busy = true;
  if (mine.slots?.[n - 1]) {
    const cleared = await wipeSlot(n);
    if (view !== mine) {
      return;
    }
    if (cleared !== DONE) {
      mine.busy = false;
      if (cleared === STALE) {
        await show("slots", { mode: "new" });
        tell(OVERTAKEN);
      } else {
        askFailed("SAVE FAILED");
      }
      return;
    }
  }
  mine.busy = false;
  record("start", { slot: n });
  show("mode", { slot: n });
}

// Continue in a slot: the menu goes, the world comes up on the saved room
async function continueSlot(n) {
  view.busy = true;
  await show("world");
  let loaded = false;
  try {
    loaded = await loadSlot(n);
  } catch (e) {
    console.warn(`Union City: couldn't load slot ${n}`, e);
  }
  record("load", { slot: n, loaded });
  if (!loaded) {
    await show("menu");
    askFailed("LOAD FAILED");
  }
}

// ---------- The screens ----------

function leaveMenu(next) {
  if (!MUSIC_KEEP.has(next)) {
    sound.stopMusic();
  }
  if (KEEP.has(next)) {
    return;
  }
  page.detach("menu");
  view = null;
  record("close", { next });
}

const MENU_SCREENS = {
  menu: {
    // notice is a box to show over the menu ({ heading, body }): a story saved on another device
    async enter(shown, { notice = null } = {}) {
      await ensureMenu();
      showPage(MAIN);
      refreshContinue();
      if (notice) {
        tell(notice);
      }
    },
    leave: (shown, next) => leaveMenu(next),
    step: stepBlurs,
  },
  slots: {
    async enter(shown, { mode = "new" } = {}) {
      await ensureMenu();
      const name = mode === "new" ? "newGame" : "continueGame";
      showPage(name);
      slotsWaiting(name);
      wireSlots(name, mode);
      const mine = view;
      const slots = await readSlots();
      if (view === mine && view.page === name) {
        paintSlots(name, slots);
        record("slots", { mode, count: slots?.filter(Boolean).length ?? null });
      }
    },
    leave: (shown, next) => leaveMenu(next),
    step: stepBlurs,
  },
  mode: {
    async enter(shown, { slot = 0 } = {}) {
      await ensureMenu();
      showPage("selectMode");
      resetMode(slot);
      wireMode();
    },
    leave: (shown, next) => leaveMenu(next),
    step: stepBlurs,
  },
};

// show() is game.js's; the menu asks for the next screen through the page
function show(name, options) {
  return page.show(name, options);
}

export function initMenus(owner, band) {
  page = owner;
  depth = band;
}

export { MENU_SCREENS };

export const menus = {
  get active() {
    return view !== null;
  },
  log,
};

// Helpers for page.py checks
export const menusDebug = {
  menuState() {
    return view && {
      page: view.page,
      canContinue: view.canContinue,
      busy: view.busy,
      dialog: Boolean(view.dialog),
      slots: view.slots,
      screen: page.screen,
      mode: view.mode && {
        ...view.mode,
        desc: modePage().child("desc").text,
        boxes: Object.fromEntries(
          Object.keys(OPTIONS).map((name) => [name, modePage().child("premium").child(name).frame]),
        ),
      },
    };
  },

  menuLog: () => log.map((each) => ({ ...each })),

  // A slot panel's words and badges as they show now, on a page ("newGame" or "continueGame")
  menuSlot(name, n) {
    const panel = view.clip.child(name).child("panels").child(`slot${n}`);
    return {
      name: panel.child("charName").text,
      details: panel.child("charDetails").text,
      day: panel.child("charDay").text,
      mode: panel.child("gameMode").text,
      hardcore: panel.child("hardcore").text,
      headshots: panel.child("headShotsOnly").visible,
    };
  },

  // Where the middle of a part of the menu is in the page's pixels, for a click: a path like "main.newGame"
  menuPoint(path) {
    let node = view.clip;
    for (const step of path.split(".")) {
      node = node.child(step);
    }
    const box = node.getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: canvas.left + (box.x + box.width / 2) * (canvas.width / page.app.screen.width),
      y: canvas.top + (box.y + box.height / 2) * (canvas.height / page.app.screen.height),
    };
  },

  // The pointer events at a point of the page, from the top: what a click there would reach
  menuHit(x, y) {
    return document.elementsFromPoint(x, y).map((each) => each.tagName.toLowerCase() + (each.id ? `#${each.id}` : ""));
  },
};
