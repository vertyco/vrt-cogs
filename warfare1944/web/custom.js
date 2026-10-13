// The Custom Battle screen (the original's "skirmish", sprite 1208 inside the menu clip), ported from loadSkirmish
// (F6:629-640), skirmishToMainMenu (F6:641-651), setupSkirmishMapDefaults (F6:8903-8929), buttonSetup_skirmish
// (F6:8930-9249), addRemoveSkirmishUnits (F6:9250-9314) and skirmishMapSettings (F6:9315-9478). The page keeps only the
// picks and sends them with Launch; the bot lays the map out and runs the battle.
import { TextField } from "./flash.js";
import { Container } from "./vendor/pixi.min.mjs";
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const CLICK = "sound_interface_click";
const EASE = "easeOutSine";
// Flash color transforms (F6:8934-8940): a picked button 190 % bright, a button under the pointer 140 %, and normal.
// F6:9264 also lifts a picked unit's alpha to 190 %, which Flash caps at the art's own opacity, so it is the same look
// as any other picked button
const PICKED = [190, 0, 190, 0, 190, 0, 100, 0];
const HOVER = [140, 0, 140, 0, 140, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// The eight unit buttons in the order of the settings' `units` list, and the four support buttons in the order of its
// `supports` list (grenades, smoke grenades, air support, artillery)
const UNITS = ["riflemen", "assault", "machineGun", "sniper", "bazooka", "mortarTeam", "officer", "tank"];
const SUPPORTS = ["grenade", "smokeGrenade", "airSupport", "artillery"];
const ALL = { allUnits: "units", allSupport: "supports" };
const TANK = UNITS.indexOf("tank");
// Each one-of-several row: the settings key and the button each choice is
const ROWS = {
  side: { british: "british", german: "german" },
  difficulty: { easy: "easy", medium: "medium", hard: "hard" },
  mood: { aggressive: "AI_aggressive", balanced: "AI_balanced", defensive: "AI_defensive" },
};
// The nine maps, by number: the line under the map buttons (F6:11780-11788) and whether the map has no tanks
// (skirmishMapSettings, F6:9323-9441)
const MAPS = [
  { text: "BEACH LANDING: MEDIUM size beach landing. LIGHT COVER.", noTanks: false },
  { text: "OPEN PLAINS: LONG open Map with NO COVER.", noTanks: false },
  { text: "DESERTED TOWN:  LONG open town Map with NO COVER.", noTanks: false },
  { text: "TOWN: MEDIUM town Map. MEDIUM COVER. NO TANKS!", noTanks: true },
  { text: "HIGH LOW: MEDIUM length. Two open roads, one high one low. LIGHT COVER.", noTanks: false },
  { text: "HEDGEROWS: MEDIUM length. HEAVY COVER. NO TANKS!", noTanks: true },
  { text: "RAILWAY: LONG Map. Dense hedgerows lining a railway track.", noTanks: false },
  { text: "TOWN SQUARE: LONG Map. HEAVY COVER. NO TANKS!", noTanks: true },
  { text: "CEMETARY: MEDIUM Map. HEAVY COVER.", noTanks: false },
];
// A map's name as the lobby lists it ("Beach Landing"), from the first words of its line
export function mapName(number) {
  const name = MAPS[number - 1]?.text.split(":")[0] ?? "";
  return name.toLowerCase().replace(/(^| )[a-z]/g, (letter) => letter.toUpperCase());
}
// The resource points the two plus and minus buttons step through (F6:11763-11765)
const RP_LOW = 500;
const RP_HIGH = 2000;
const RP_STEP = 100;
const RP_START = 800;
const NOT_CONNECTED = "Not connected. Try again in a moment.";
const NO_UNITS = "Pick at least one unit.";
// The part of the menu clip the screen before this one shows
const PART_OF = { main: "mainMenu" };
// The back button the original placed in the screen's bottom corner (depth 77, F6 sprite 1208): it has no name
const BACK_DEPTH = 77;
// The dialog's backing (character 1068) and the heading and words fields of its text box (characters 1211 and 1212)
const NOTE_BACKING = 1068;
const NOTE_HEADING = 1211;
const NOTE_BODY = 1212;
const NOTE_HEADING_Y = 10;
const NOTE_BODY_Y = 36;
const SKIRMISH_ORIGIN = { x: 400.45, y: 204.45 };
// Where the "DIFFICULTY" heading with its three wells, and the "A.I SETTING" heading with its three wells, are baked
// into the screen's background, in stage pixels from the stage's top left. A versus game has neither (a person
// commands the other side), so a panel covers each
const DIFFICULTY_BOX = { x: 228, y: 70, width: 212, height: 79 };
const MOOD_BOX = { x: 52, y: 422, width: 414, height: 30 };
// Who may take a versus game, on the panel over the A.I. setting: anyone in the server, or only the player's own
// voice channel. Each is one of the options screen's buttons (character 957), as the versus lobby uses, lit like
// the screen's other picks
const WHO_BUTTON = 957;
const WHO_BUTTONS = { server: ["whoServer", "WHOLE SERVER"], channel: ["whoChannel", "MY CHANNEL"] };
const WHO_LABEL = "WHO CAN TAKE IT";
const WHO_LABEL_X = 12;
const WHO_LABEL_Y = 5;
const WHO_GAP = 8;
const WHO_PADDING = 24;

let page = null;
// True while the screen sets up a versus game: no difficulty or mood, and Launch opens the game in the versus lobby
let versus = false;
// Who may take the versus game, "server" or "channel": the whole server each time the screen opens
let who = "server";
// What is picked: the starting picks of setupSkirmishMapDefaults and buttonSetup_skirmish (F6:8903-8949)
let picks = startingPicks();

function startingPicks() {
  return {
    side: "british",
    difficulty: "medium",
    units: UNITS.map((name) => name === "riflemen"),
    supports: SUPPORTS.map(() => false),
    mood: "balanced",
    map: 1,
    rp: RP_START,
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

// A button that stays lit once picked ignores the pointer passing over it (F6:8943-8957)
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

// Presses of one-of-several buttons light the pick and put out the others in its row (F6:9054-9120)
function pickRow(skirmish, key, value) {
  picks[key] = value;
  for (const [choice, name] of Object.entries(ROWS[key])) {
    light(skirmish.child(name), choice === value ? PICKED : NORMAL, 0.4);
  }
}

// A NO TANKS map has no tank for either side, so its button stays off (B59)
function tankOff() {
  return MAPS[picks.map - 1].noTanks;
}

function setUnit(skirmish, list, index, on) {
  const kinds = list === "units" ? UNITS : SUPPORTS;
  const lit = on && !(list === "units" && index === TANK && tankOff());
  picks[list][index] = lit;
  light(skirmish.child(kinds[index]), lit ? PICKED : NORMAL, 0.4);
}

// addRemoveSkirmishUnits (F6:9250-9314): a press flips the unit or support. The bot puts a picked unit, air support
// and artillery in the CPU's pool as well. Each button's pick lives on the button alone (B59), so ALL lights every
// button once and never adds one twice
function flip(skirmish, list, index) {
  setUnit(skirmish, list, index, !picks[list][index]);
}

function pickAll(skirmish, list) {
  for (const index of picks[list].keys()) {
    setUnit(skirmish, list, index, true);
  }
}

// skirmishMapSettings drops the tank on a NO TANKS map (F6:9442-9470) and the map's line shows under the maps (F6:9115)
function pickMap(skirmish, number) {
  picks.map = number;
  for (const index of MAPS.keys()) {
    light(skirmish.child(`map_skirmish_${index + 1}`), index + 1 === number ? PICKED : NORMAL, 0.4);
  }
  skirmish.child("mapDesc").text = MAPS[number - 1].text;
  if (tankOff()) {
    setUnit(skirmish, "units", TANK, false);
  }
}

// rp_plus and rp_minus step both sides' points and stop at the ends (F6:8995-9020)
function stepPoints(skirmish, by) {
  picks.rp = Math.min(RP_HIGH, Math.max(RP_LOW, picks.rp + by));
  skirmish.child("resourcePoints").text = String(picks.rp);
}

function pressesOf(skirmish) {
  const presses = {
    launch,
    backToMainButt: leaveScreen,
    rp_plus: () => stepPoints(skirmish, RP_STEP),
    rp_minus: () => stepPoints(skirmish, -RP_STEP),
  };
  for (const [key, row] of Object.entries(ROWS)) {
    for (const [choice, name] of Object.entries(row)) {
      presses[name] = () => pickRow(skirmish, key, choice);
    }
  }
  UNITS.forEach((name, index) => {
    presses[name] = () => flip(skirmish, "units", index);
  });
  SUPPORTS.forEach((name, index) => {
    presses[name] = () => flip(skirmish, "supports", index);
  });
  for (const [name, list] of Object.entries(ALL)) {
    presses[name] = () => pickAll(skirmish, list);
  }
  for (const index of MAPS.keys()) {
    presses[`map_skirmish_${index + 1}`] = () => pickMap(skirmish, index + 1);
  }
  return presses;
}

function wireButtons(skirmish) {
  for (const [name, press] of Object.entries(pressesOf(skirmish))) {
    const button = skirmish.child(name);
    wireHover(button);
    button.setHandler("onRelease", () => {
      click();
      press();
    });
  }
  // The corner button is only a press: skirmishToMainMenu with no click (F6 sprite 1208, depth 77)
  skirmish.at(BACK_DEPTH).setHandler("onRelease", leaveScreen);
  // The padlock the original placed under the German button never shows (lock_slot6, depth 6)
  skirmish.child("lock_slot6").visible = false;
}

// skirmishToMainMenu (F6:641-651)
function leaveScreen() {
  page.show(versus ? "versus" : "main");
}

// ---------- The versus panels ----------

function noteWords(def, text, y, width, x = 0, align = "center") {
  const field = new TextField({ ...def, bounds: [0, 0, width, 24], align, multiline: true, text });
  field.position.set(x, y);
  field.draw();
  return field;
}

// A panel over a baked heading and its wells, shown only while the screen sets up a versus game
function makePanel(skirmish, name, box, words) {
  const panel = skirmish.attach(new Container(), name);
  panel.position.set(box.x - SKIRMISH_ORIGIN.x, box.y - SKIRMISH_ORIGIN.y);
  const backing = page.lib.make(NOTE_BACKING);
  const size = backing.getLocalBounds();
  backing.scale.set(box.width / size.width, box.height / size.height);
  backing.position.set(-size.minX * backing.scale.x, -size.minY * backing.scale.y);
  panel.addChild(backing);
  if (words) {
    const [heading, body] = words;
    const texts = page.lib.data.texts;
    panel.addChild(
      noteWords(texts[NOTE_HEADING], heading, NOTE_HEADING_Y, box.width),
      noteWords(texts[NOTE_BODY], body, NOTE_BODY_Y, box.width),
    );
  }
  return panel;
}

// One of the who buttons, its plate widened to its words as the versus lobby's are
function whoButton(skirmish, name, words, choice) {
  const button = skirmish.attach(page.lib.make(WHO_BUTTON), name);
  const field = button.child("buttonText");
  field.autoSizeCenter();
  field.text = words;
  const backing = button.child("backing");
  backing.scale.x = Math.max(1, (field.box.width + WHO_PADDING) / backing.getLocalBounds().width);
  wireHover(button);
  button.setHandler("onRelease", () => {
    click();
    pickWho(skirmish, choice);
  });
  return button;
}

// The panel over the A.I. setting: its heading on the left, and the two buttons from its right edge in
function makeWho(skirmish) {
  const panel = makePanel(skirmish, "versusWho", MOOD_BOX, null);
  const heading = page.lib.data.texts[NOTE_HEADING];
  panel.addChild(noteWords(heading, WHO_LABEL, WHO_LABEL_Y, MOOD_BOX.width / 2, WHO_LABEL_X, "left"));
  let right = MOOD_BOX.x + MOOD_BOX.width - WHO_GAP;
  for (const [choice, [name, words]] of Object.entries(WHO_BUTTONS).reverse()) {
    const button = whoButton(skirmish, name, words, choice);
    const size = button.getLocalBounds();
    button.position.set(
      right - size.maxX - SKIRMISH_ORIGIN.x,
      MOOD_BOX.y + MOOD_BOX.height / 2 - (size.minY + size.maxY) / 2 - SKIRMISH_ORIGIN.y,
    );
    right -= size.width + WHO_GAP;
  }
}

function pickWho(skirmish, choice) {
  who = choice;
  for (const [key, [name]] of Object.entries(WHO_BUTTONS)) {
    light(skirmish.child(name), key === who ? PICKED : NORMAL, 0.4);
  }
}

function makePanels(skirmish) {
  makePanel(skirmish, "versusDifficulty", DIFFICULTY_BOX, ["VERSUS", "Another player commands\rthe other side."]);
  makeWho(skirmish);
}

// The difficulty and mood buttons, and the panels that hide their headings, are for one mode each
function applyMode(skirmish) {
  for (const key of ["difficulty", "mood"]) {
    for (const name of Object.values(ROWS[key])) {
      skirmish.child(name).visible = !versus;
    }
  }
  for (const name of ["versusDifficulty", "versusWho", ...Object.values(WHO_BUTTONS).map(([name]) => name)]) {
    skirmish.child(name).visible = versus;
  }
}

// ---------- Launch ----------

// The picks as the bot takes them. A versus game has no difficulty and no mood
function settings() {
  const chosen = {
    side: picks.side,
    units: [...picks.units],
    supports: [...picks.supports],
    rp: picks.rp,
    map: picks.map,
  };
  if (!versus) {
    chosen.difficulty = picks.difficulty;
    chosen.mood = picks.mood;
  }
  return chosen;
}

function launch() {
  const chosen = settings();
  if (!chosen.units.some(Boolean)) {
    page.toast(NO_UNITS);
    return;
  }
  if (!(versus ? page.send({ versus: { ...chosen, who } }) : page.launch({ custom: chosen }))) {
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
  for (const index of MAPS.keys()) {
    light(skirmish.child(`map_skirmish_${index + 1}`), index + 1 === picks.map ? PICKED : NORMAL, 0);
  }
  skirmish.child("mapDesc").text = MAPS[picks.map - 1].text;
  skirmish.child("resourcePoints").text = String(picks.rp);
}

// loadSkirmish (F6:629-640): the main menu fades out and the screen fades in after it
async function enter(forVersus) {
  versus = forVersus;
  const had = menuClip() !== null;
  const menu = menuClip() ?? (await menus.loadMenu("custom"));
  await page.lib.need([NOTE_BACKING, WHO_BUTTON]);
  const skirmish = menu.child("skirmish");
  if (!skirmish.wired) {
    skirmish.wired = true;
    wireButtons(skirmish);
    makePanels(skirmish);
  }
  applyMode(skirmish);
  if (page.previousScreen !== "battle") {
    picks = startingPicks();
  }
  show(skirmish);
  for (const [key, [name]] of Object.entries(WHO_BUTTONS)) {
    light(skirmish.child(name), key === "server" ? PICKED : NORMAL, 0);
  }
  who = "server";
  if (had) {
    menus.swap(menu, PART_OF[page.previousScreen] ?? null, "skirmish");
  }
}

function leave(owner, next) {
  menus.keepMenu(next);
}

export const screens = {
  custom: { enter: () => enter(false), leave },
  versusSetup: { enter: () => enter(true), leave },
};
