// The Custom Battle screen (the original's "skirmish", sprite 1034 inside the menu clip), ported from loadSkirmish
// (F5:432-443), skirmishToMainMenu (F5:444-453), setupSkirmishMapDefaults (F5:6093-6122), buttonSetup_skirmish
// (F5:6123-6308), addRemoveSkirmishUnits (F5:6309-6351) and skirmishMapSettings (F5:6352-6567). The page keeps only the
// picks and sends them with Launch; the bot lays the map out and runs the battle.
import { TextField } from "./flash.js";
import { Container, Rectangle } from "./vendor/pixi.min.mjs";
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const CLICK = "sound_interface_click";
const EASE = "easeOutSine";
// Flash color transforms (F5:6143-6152): a picked button 220 % bright, a button under the pointer 140 %, and normal.
// F5:6322 also lifts a picked unit's alpha to 220 %, which Flash caps at the art's own opacity, so it is the same
// look as any other picked button
const PICKED = [220, 0, 220, 0, 220, 0, 100, 0];
const HOVER = [140, 0, 140, 0, 140, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
const UNITS = ["riflemen", "assault", "machineGun", "sniper", "officer", "tank"];
const SUPPORTS = ["mortar", "artillery", "gas", "antiTank"];
// Each one-of-several row: the settings key and the button each choice is
const ROWS = {
  side: { british: "british", german: "german" },
  difficulty: { easy: "easy", medium: "medium", hard: "hard" },
  mood: { aggressive: "AI_aggressive", balanced: "AI_balanced", defensive: "AI_defensive" },
  map: { short: "map_short", medium: "map_medium", long: "map_long" },
  mines: { few: "mines_few", medium: "mines_medium", many: "mines_many" },
};
// The number boxes and the most each counts to (F5:6377-6388)
const BOXES = { trenches: 5, wire: 4 };
const NOT_CONNECTED = "Not connected. Try again in a moment.";
const NO_UNITS = "Pick at least one unit.";
// The part of the menu clip the screen before this one shows
const PART_OF = { main: "mainMenu" };
// The dialog's backing (character 1037) and the words it carries (characters 1038 and 1039 use a font the game does not
// carry, so a player sees the machine's own sans serif, as in the dialog box)
const NOTE_BACKING = 1037;
const NOTE_FONT = '"Noto Sans", "Segoe UI", "Open Sans", Arial, sans-serif';
const NOTE_HEADING = 1038;
const NOTE_BODY = 1039;
// Where the "DIFFICULTY" heading and the three wells under it are baked into the screen's background, in the screen's
// own pixels from the stage's top left. A versus game has no difficulty, so the note covers them
const NOTE_BOX = { x: 230, y: 70, width: 212, height: 79 };
const SKIRMISH_ORIGIN = { x: 400.45, y: 204.45 };
const NOTE_HEADING_Y = 12;
const NOTE_BODY_Y = 40;

let page = null;
// True while the screen sets up a versus game: no difficulty (a person commands the other side), and Launch opens
// the game in the versus lobby
let versus = false;
// What is picked: the starting picks of setupSkirmishMapDefaults and buttonSetup_skirmish (F5:6126). The boxes' words
// are kept apart, as the original's boxes keep theirs
let picks = startingPicks();
let words = { trenches: "0", wire: "0" };
// The number box that takes typed letters, and the two boxes while the screen shows
let focus = null;
let fields = [];

function startingPicks() {
  return {
    side: "british",
    difficulty: "medium",
    units: UNITS.map((name) => name === "riflemen"),
    supports: SUPPORTS.map(() => false),
    mood: "balanced",
    map: "medium",
    mines: "none",
  };
}

// Gives the module the page it works on. Called once by game.js
export function bindPage(owner) {
  page = owner;
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

function click() {
  sound.play(CLICK);
}

// ---------- The buttons ----------

function light(button, how, seconds) {
  button.picked = how !== NORMAL;
  tweens.colorTransformTo(button, ...how, seconds, EASE);
}

// A button that stays lit once picked ignores the pointer passing over it (F5:6128-6142)
function wireHover(button) {
  button.picked = false;
  button.setHandler("onRollOver", () => {
    if (!button.picked) {
      tweens.colorTransformTo(button, ...HOVER, 0.4, EASE);
    }
  });
  button.setHandler("onRollOut", () => {
    if (!button.picked) {
      tweens.colorTransformTo(button, ...NORMAL, 0.4, EASE);
    }
  });
}

// Presses of one-of-several buttons light the pick and put out the others in its row (F5:6169-6300)
function pickRow(skirmish, key, value) {
  picks[key] = value;
  for (const [choice, name] of Object.entries(ROWS[key])) {
    light(skirmish.child(name), choice === value ? PICKED : NORMAL, 0.4);
  }
}

// addRemoveSkirmishUnits (F5:6309-6351): a press flips the unit or support. The bot puts a picked one in the CPU's
// pool as well
function flipUnit(skirmish, list, kinds, name) {
  const index = kinds.indexOf(name);
  picks[list][index] = !picks[list][index];
  light(skirmish.child(name), picks[list][index] ? PICKED : NORMAL, 0.4);
}

function wireButtons(skirmish) {
  const presses = {
    launch: launch,
    backToMainButt: () => page.show(versus ? "versus" : "main"),
  };
  for (const [key, row] of Object.entries(ROWS)) {
    for (const [choice, name] of Object.entries(row)) {
      presses[name] = () => pickRow(skirmish, key, choice);
    }
  }
  for (const name of UNITS) {
    presses[name] = () => flipUnit(skirmish, "units", UNITS, name);
  }
  for (const name of SUPPORTS) {
    presses[name] = () => flipUnit(skirmish, "supports", SUPPORTS, name);
  }
  for (const [name, press] of Object.entries(presses)) {
    const button = skirmish.child(name);
    wireHover(button);
    button.setHandler("onRelease", () => {
      click();
      press();
    });
  }
}

// ---------- The versus note ----------

function noteWords(def, text, y) {
  const width = NOTE_BOX.width - 16;
  const bounds = [0, 0, width, 40];
  const field = new TextField({ ...def, bounds, font: NOTE_FONT, align: "center", multiline: true, text });
  field.position.set(8, y);
  field.draw();
  return field;
}

// A panel over the baked difficulty heading and wells, shown only while the screen sets up a versus game
function makeNote(skirmish) {
  const holder = skirmish.attach(page.lib.make(NOTE_BACKING), "versusNote");
  const size = holder.getLocalBounds();
  holder.scale.set(NOTE_BOX.width / size.width, NOTE_BOX.height / size.height);
  holder.position.set(
    NOTE_BOX.x - SKIRMISH_ORIGIN.x - size.minX * holder.scale.x,
    NOTE_BOX.y - SKIRMISH_ORIGIN.y - size.minY * holder.scale.y,
  );
  const words = skirmish.attach(new Container(), "versusWords");
  words.position.set(NOTE_BOX.x - SKIRMISH_ORIGIN.x, NOTE_BOX.y - SKIRMISH_ORIGIN.y);
  words.addChild(
    noteWords(page.lib.data.texts[NOTE_HEADING], "VERSUS", NOTE_HEADING_Y),
    noteWords(page.lib.data.texts[NOTE_BODY], "Another player commands\rthe other side.", NOTE_BODY_Y),
  );
  return [holder, words];
}

// The difficulty buttons and the note are for one mode each
function applyMode(skirmish) {
  for (const name of Object.values(ROWS.difficulty)) {
    skirmish.child(name).visible = !versus;
  }
  for (const part of [skirmish.child("versusNote"), skirmish.child("versusWords")]) {
    part.visible = versus;
  }
}

// ---------- The number boxes ----------

// skirmishMapSettings (F5:6377-6388): only 1 up to the most counts, anything else is none
function count(text, most) {
  return /^[1-9]$/.test(text) && Number(text) <= most ? Number(text) : 0;
}

function setWords(name, text) {
  words[name] = text;
  fields.find((field) => field.boxName === name).text = text;
}

// A tap on a box steps it to the next number and back to 0 after the most (D18). A key typed after a tap goes into
// the box in place of what it held, as the original's one-character boxes take it
function wireBoxes(skirmish) {
  fields = Object.keys(BOXES).map((name) => Object.assign(skirmish.child(name), { boxName: name }));
  for (const field of fields) {
    const box = field.box;
    field.eventMode = "static";
    field.cursor = "pointer";
    field.hitArea = new Rectangle(box.x, box.y, box.width, box.height);
    field.on("pointertap", () => {
      click();
      focus = field.boxName;
      const most = BOXES[focus];
      setWords(focus, String((count(words[focus], most) + 1) % (most + 1)));
    });
  }
}

function blur(event) {
  if (!fields.includes(event.target)) {
    focus = null;
  }
}

function typed(event) {
  if (!focus || event.ctrlKey || event.metaKey || event.altKey) {
    return;
  }
  if (event.key === "Backspace" || event.key === "Delete") {
    setWords(focus, "");
  } else if (event.key.length === 1) {
    setWords(focus, event.key);
  } else if (event.key === "Enter" || event.key === "Escape") {
    focus = null;
  } else {
    return;
  }
  event.preventDefault();
}

// ---------- Launch ----------

// The picks as the bot takes them
function settings() {
  return {
    side: picks.side,
    difficulty: picks.difficulty,
    units: [...picks.units],
    supports: [...picks.supports],
    mood: picks.mood,
    map: picks.map,
    trenches: count(words.trenches, BOXES.trenches),
    wire: count(words.wire, BOXES.wire),
    mines: picks.mines,
  };
}

function launch() {
  const chosen = settings();
  if (!chosen.units.some(Boolean)) {
    page.toast(NO_UNITS);
    return;
  }
  if (versus) {
    delete chosen.difficulty;
  }
  if (!(versus ? page.send({ versus: chosen }) : page.launch({ custom: chosen }))) {
    page.toast(NOT_CONNECTED);
    return;
  }
  if (versus) {
    page.show("versus");
  }
}

// ---------- The screen ----------

// Every button shows the picks, at once. Opening from the main menu starts again from the starting picks; coming back
// from a custom battle keeps the last ones (B16: the original reset the lists but left the old buttons lit)
function show(skirmish) {
  for (const [key, row] of Object.entries(ROWS)) {
    for (const [choice, name] of Object.entries(row)) {
      light(skirmish.child(name), choice === picks[key] ? PICKED : NORMAL, 0);
    }
  }
  for (const [list, kinds] of [
    ["units", UNITS],
    ["supports", SUPPORTS],
  ]) {
    kinds.forEach((name, index) => light(skirmish.child(name), picks[list][index] ? PICKED : NORMAL, 0));
  }
  for (const [name, text] of Object.entries(words)) {
    fields.find((field) => field.boxName === name).text = text;
  }
}

// loadSkirmish (F5:432-443): the main menu fades out and the screen fades in after it
async function enter(forVersus) {
  versus = forVersus;
  const had = menuClip() !== null;
  const menu = menuClip() ?? (await menus.loadMenu("custom"));
  await page.lib.need([NOTE_BACKING]);
  const skirmish = menu.child("skirmish");
  if (!skirmish.wired) {
    skirmish.wired = true;
    wireButtons(skirmish);
    wireBoxes(skirmish);
    makeNote(skirmish);
  }
  applyMode(skirmish);
  if (page.previousScreen !== "battle") {
    picks = startingPicks();
  }
  focus = null;
  show(skirmish);
  page.app.stage.on("pointerdown", blur);
  document.addEventListener("keydown", typed);
  if (had) {
    menus.swap(menu, PART_OF[page.previousScreen] ?? null, "skirmish");
  }
}

function leave(owner, next) {
  page.app.stage.off("pointerdown", blur);
  document.removeEventListener("keydown", typed);
  focus = null;
  menus.keepMenu(next);
}

export const screens = {
  custom: { enter: () => enter(false), leave },
  versusSetup: { enter: () => enter(true), leave },
};
