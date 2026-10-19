// The character sheet (int_character, sprite 5918; openCharacter F4:12915, updateCharacterInfo F4:12986,
// characterBtnSkills F4:13128, addPoint and removePoint F4:13519-13560, confirmStats F4:13562): the player's face and
// name, level and XP, health, stamina, hunger, sleep and carry weight, the five attributes and the 12 skills with their
// adjusted values, and the + buttons that spend level-up points. C and the dock's character button open and close it.
//
// A level gives 1 attribute point and 10 skill points. A + puts a point on a row for now: attributes stop at 20 and
// skills at 100 (on the raw skill). The points are only placed until CONFIRM, which needs every point spent: it applies
// them, heals fully and saves, and the numbers that follow from the stats (carry weight, health, stamina, speed, jump)
// are worked out again. Closing any other way (C, E, Esc, the X with nothing left to spend) gives the points back; the
// stats themselves are never touched until CONFIRM, so nothing is left to put right (P29).
//
// A skill's number is round(skill + Attribute x 1.6 - 5). While attribute points are placed the skill numbers show
// them at the same 1.6 each, as they will be worth after CONFIRM (P16). Hovering a row (desktop) or tapping it (touch)
// shows its description, and the Strength, Endurance, Precision and Intellect rows say what hunger or sleep takes off.
import { data } from "./data.js";
import { help } from "./help.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { canOpenPanel, closePanel, fadeInBox, fadeOutBox, finger, openPanel, panelOpen, setAlpha } from "./panels.js";
import { adjustedSkill, attributeOf, fullHealth, penalty, recalcStats, refuseOpen, vitalState } from "./player.js";
import { decorate } from "./rig.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

const PANEL = "sheet";
const WHITE = "#ffffff";
const PENALTY_RED = "#cc0000";
// The attribute box rests above the stage until a penalised row is pointed at (F4:13172)
const INFO_HIDDEN_Y = -400;
// The skill levels that count toward "Skillful" and "Masterful" (confirmStats F4:13565)
const SKILLFUL = 50;
const MASTERFUL = 100;
// What each hunger or sleep penalty takes from which attributes, and what the box says the player needs
const PENALISED = {
  strength: "YOU NEED FOOD",
  endurance: "YOU NEED FOOD",
  precision: "YOU NEED SLEEP",
  intellect: "YOU NEED SLEEP",
};
// The text fields beside each skill column's heading that show an attribute's penalty
const PEN_FIELDS = ["strength", "precision", "intellect", "endurance"];
// The dialog box over the sheet when the X is pressed with points still to spend (dialog_levelUpPoints F4:20249)
const POINTS_LEFT = {
  heading: "POINTS REMAINING",
  body: "YOU STILL HAVE POINTS TO\rTHAT NEED TO BE ASSIGNED\rIN ORDER TO CONTINUE",
  button: "OK",
};
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };

// The sheet open now: { clip, dialog }
let view = null;
// Points placed and not yet confirmed: how many of each kind are used, and on which rows
let spent = { attribute: 0, skill: 0 };
let temp = { attribute: {}, skill: {} };
const countListeners = [];

function constant(name) {
  return data.actors.constants[name];
}

// Registers fn(key, amount) for each counter the sheet adds to: "skillful" and "masterful" (checkAch F4:13565)
export function onSheetCount(fn) {
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

// ---------- Points ----------

function typeOf(name) {
  return name in data.actors.attributes ? "attribute" : "skill";
}

function tableFor(type) {
  return type === "attribute" ? story.player.attributes : story.player.skills;
}

function placed(name) {
  return temp[typeOf(name)][name] ?? 0;
}

// Points of a kind still to spend: what the level gave, less what is placed
function remaining(type) {
  return story.player.points[type] - spent[type];
}

// A + press: one point onto the row, as far as its kind has points and the row has room (addPoint F4:13519)
function addPoint(name) {
  const type = typeOf(name);
  const most = constant(type === "attribute" ? "attributeMax" : "skillMax");
  if (tableFor(type)[name] + placed(name) < most && remaining(type) > 0) {
    temp[type][name] = placed(name) + 1;
    spent[type] += 1;
  }
}

// A - press: the row's latest point comes back (removePoint F4:13539)
function removePoint(name) {
  const type = typeOf(name);
  if (placed(name) > 0) {
    temp[type][name] = placed(name) - 1;
    spent[type] -= 1;
  }
}

// An attribute as the sheet shows it: with hunger or sleep taken off, plus the points placed on it
function shownAttribute(name) {
  return attributeOf(story.player, name) + placed(name);
}

// A skill as the sheet shows it: round(skill + Attribute x 1.6 - 5), with the points placed on the skill and on its
// attribute (P16)
function shownSkill(name) {
  const attribute = data.actors.skills[name].attribute;
  const skill = story.player.skills[name] + placed(name);
  return Math.round(skill + shownAttribute(attribute) * constant("attributeMod") - constant("attributeBase"));
}

// ---------- Painting ----------

function paintVitals(clip) {
  const who = story.player;
  const survivor = story.mode === "survivor";
  const vitals = clip.child("vitals");
  vitals.visible = survivor;
  for (const [vital, attribute] of [
    ["hunger", "strength"],
    ["sleep", "precision"],
  ]) {
    const words = `${vitalState(vital).name.toUpperCase()} - ${Math.round(100 - who[vital])}%`;
    setText(vitals.child(vital), words, penalty(attribute) > 0 ? PENALTY_RED : WHITE);
  }
}

function paintBars(clip) {
  const who = story.player;
  setText(clip.child("health"), `${Math.round(who.health)} / ${Math.round(who.healthMax)}`);
  clip.child("healthBar").scale.x = Math.round((who.health / who.healthMax) * 100) / 100;
  setText(clip.child("stamina"), `${Math.round(who.stamina)} / ${who.staminaMax}`);
  clip.child("staminaBar").scale.x = Math.round((who.stamina / who.staminaMax) * 100) / 100;
}

function paintHeading(clip) {
  const who = story.player;
  const mode = story.mode === "runAndGun" ? "RUN & GUN" : "SURVIVOR";
  setText(clip.child("gameMode"), story.hardcore ? `${mode} - HARDCORE` : mode);
  setText(clip.child("name"), who.name.toUpperCase());
  setText(clip.child("level"), `LEVEL ${who.level}`);
  setText(clip.child("xp"), `XP: ${who.xp} / ${who.levelXP}`);
  const carry = (who.attributes.strength + placed("strength")) * constant("carryWeightMultiplier");
  setText(clip.child("weight"), `${carry} lbs`);
  for (const type of ["attribute", "skill"]) {
    const box = clip.child(type === "attribute" ? "attRem" : "skillRem");
    const left = remaining(type);
    box.visible = left > 0;
    const words = `${left} ${left === 1 ? "POINT" : "POINTS"} REMAINING`;
    setText(box.child(type === "attribute" ? "attributeRemaining" : "skillRemaining"), words);
  }
}

// One row: its number and its + and - buttons. An attribute row a penalty is taking from is red
function paintRow(clip, name) {
  const row = clip.child(name);
  const type = typeOf(name);
  if (type === "attribute") {
    const colour = penalty(name) > 0 ? PENALTY_RED : WHITE;
    setText(row.child("skillNumber"), String(shownAttribute(name)), colour);
    setText(row.child("skill"), data.actors.attributes[name].title, colour);
  } else {
    setText(row.child("skillNumber"), String(shownSkill(name)));
    setText(row.child("skill"), data.actors.skills[name].title);
  }
  const controls = row.child("levelUpControls");
  controls.child("plus").visible = remaining(type) > 0;
  controls.child("minus").visible = placed(name) > 0;
}

function paintPenalties(clip) {
  for (const name of PEN_FIELDS) {
    const lost = penalty(name);
    setText(clip.child(`${name}Pen`), lost > 0 ? `-${lost}` : "");
  }
}

// CONFIRM shows once every point is spent and at least one is placed (updateCharacterInfo F4:13055)
function paintConfirm(clip) {
  const placedAny = spent.attribute + spent.skill > 0;
  clip.child("confirm").visible = placedAny && remaining("attribute") === 0 && remaining("skill") === 0;
}

function paint() {
  const clip = view.clip;
  paintHeading(clip);
  paintBars(clip);
  paintVitals(clip);
  for (const name of [...Object.keys(data.actors.attributes), ...Object.keys(data.actors.skills)]) {
    paintRow(clip, name);
  }
  paintPenalties(clip);
  paintConfirm(clip);
}

// The face: the head's skin, hair and facial hair as the player was made, in the skin and hair colours (F4:12932)
function paintFace(clip) {
  const who = story.player;
  decorate(clip, { ...who.look, sex: who.sex }, {}, { backpack: false });
}

// ---------- Descriptions ----------

// The row's name and words in the box under the lists, and for a penalised attribute the box that says what it costs
function describe(name, row) {
  const clip = view.clip;
  const type = typeOf(name);
  const info = data.actors[type === "attribute" ? "attributes" : "skills"][name];
  setText(clip.child("descTitle"), info.title);
  setText(clip.child("desc"), info.desc);
  const box = clip.child("attrInfo");
  box.y = INFO_HIDDEN_Y;
  if (name in PENALISED && penalty(name) > 0) {
    setText(box.child("youNeed"), PENALISED[name]);
    setText(box.child("numbers"), `${attributeOf(story.player, name)} (-${penalty(name)})`);
    box.y = row.y;
  }
}

function hideInfo() {
  view.clip.child("attrInfo").y = INFO_HIDDEN_Y;
}

// ---------- The dialog ----------

function closeDialog() {
  fadeOutBox(view.dialog, DIALOG.out);
  view.dialog = null;
}

// The box over the sheet with one OK button (showDialogBox F4:20000): everything behind it is shut off until OK
function showPointsLeft() {
  if (view.dialog) {
    return;
  }
  const box = view.clip.lib.makeExported("dialogBox");
  view.clip.attach(box, "dialogBox");
  box.position.set(DIALOG.x, DIALOG.y);
  view.dialog = box;
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), POINTS_LEFT.heading);
  setText(box.child("textBoxes").child("bodyText"), POINTS_LEFT.body);
  const button = box.child("button3");
  button.visible = true;
  setText(button.child("buttonText"), POINTS_LEFT.button);
  button.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", closeDialog);
  fadeInBox(box, DIALOG.fade);
}

// ---------- Confirming and closing ----------

// Moves one table's placed points into the player's stats and takes the spent points off the pool
function applyPlaced(type) {
  const table = tableFor(type);
  for (const [name, points] of Object.entries(temp[type])) {
    table[name] += points;
  }
  story.player.points[type] -= spent[type];
}

// CONFIRM: the placed points become the player's, the points spent are gone, the numbers that follow from the stats are
// worked out again and health is full (confirmStats F4:13562)
function confirm() {
  const who = story.player;
  applyPlaced("skill");
  // The skill table is applied and checked before the attribute points land, so a skill that only reaches 50 or 100
  // through attribute points placed in this same confirm is not counted yet
  for (const name of Object.keys(data.actors.skills)) {
    if (adjustedSkill(who, name) >= SKILLFUL) {
      count("skillful");
    }
    if (adjustedSkill(who, name) >= MASTERFUL) {
      count("masterful");
    }
  }
  applyPlaced("attribute");
  temp = { attribute: {}, skill: {} };
  spent = { attribute: 0, skill: 0 };
  recalcStats();
  fullHealth();
  closePanel();
}

// The X: it closes when nothing is left to spend, and says so when points are (charCloseButton F4:13197)
function exitPressed() {
  if (view.dialog) {
    return;
  }
  if (remaining("attribute") === 0 && remaining("skill") === 0) {
    closePanel();
  } else {
    showPointsLeft();
  }
}

// Closing saves (closeCharacter F4:12954). Points placed and not confirmed are dropped with the sheet
function finish() {
  view = null;
  hud.hidePlay(false);
  temp = { attribute: {}, skill: {} };
  spent = { attribute: 0, skill: 0 };
  sound.play("sound_closeInterface");
  savePoint("character");
  hud.refresh();
}

// The colons after FOOD and SLEEP were saved in the art with a typed "\r" that draws as letters over the words
function fixColons(clip) {
  for (const field of clip.child("vitals").children) {
    if (field.text === ":\\r") {
      setText(field, ":");
    }
  }
}

function build(clip) {
  view = { clip, dialog: null };
  hud.hidePlay(true);
  fixColons(clip);
  clip.child("attrInfo").y = INFO_HIDDEN_Y;
  paintFace(clip);
  paint();
}

// Opens the sheet (openCharacter F4:12915)
export function openSheet() {
  temp = { attribute: {}, skill: {} };
  spent = { attribute: 0, skill: 0 };
  openPanel(PANEL, { art: "int_character", setup: build, close: finish });
  sound.play("sound_openInterface");
  const points = story.player.points;
  if (points.attribute > 0 || points.skill > 0) {
    help.did("levelUp");
  }
}

function toggle() {
  if (panelOpen(PANEL)) {
    closePanel();
  } else if (canOpenPanel()) {
    openSheet();
  }
}

// C. A zombie's hold refuses the opening with its alert
function keys() {
  if (!input.sheetPressed) {
    return;
  }
  input.sheetPressed = false;
  if (panelOpen(PANEL) || !canOpenPanel() || !refuseOpen()) {
    toggle();
  }
}

export const sheet = {
  open: openSheet,
  close: closePanel,
  toggle,
  onCount: onSheetCount,
  get isOpen() {
    return panelOpen(PANEL);
  },
};

export function initSheet() {
  world.stage("interface", keys);
  hud.onOpen("character", toggle);
  world.onReset(() => {
    if (view) {
      hud.hidePlay(false);
    }
    view = null;
    temp = { attribute: {}, skill: {} };
    spent = { attribute: 0, skill: 0 };
  });
}

// ---------- The art's load handlers ----------

// A row of the lists, called once for each as the sheet is built (characterBtnSkills F4:13128): the row says what it is
// when the pointer is over it or a finger taps it, and its + and - place and take back a point
function rowButton(node, name) {
  const backing = node.child("backing");
  backing.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      describe(name, node);
    }
  });
  backing.setHandler("onRollOut", (event) => {
    if (!finger(event)) {
      hideInfo();
    }
  });
  backing.setHandler("onPress", (event) => {
    if (finger(event)) {
      describe(name, node);
    }
  });
  const controls = node.child("levelUpControls");
  controls.child("plus").setHandler("onPress", () => {
    sound.play("sound_interfacePage1");
    addPoint(name);
    paint();
  });
  controls.child("minus").setHandler("onPress", () => {
    sound.play("sound_interfacePage2");
    removePoint(name);
    paint();
  });
}

export const SHEET_LOAD_CALLS = {
  characterBtnSkills: rowButton,
  confirmButton(node) {
    node.visible = false;
    node.setHandler("onPress", confirm);
  },
  charCloseButton(node) {
    node.setHandler("onPress", exitPressed);
  },
};

// Helpers for page.py checks
export const sheetDebug = {
  // Opens the sheet
  sheet() {
    openSheet();
    return sheetDebug.sheetState();
  },

  // What the open sheet shows, in words and numbers; null when it is shut
  sheetState() {
    if (!view) {
      return null;
    }
    const clip = view.clip;
    const text = (name) => clip.child(name).text;
    const rows = {};
    for (const name of [...Object.keys(data.actors.attributes), ...Object.keys(data.actors.skills)]) {
      const row = clip.child(name);
      const controls = row.child("levelUpControls");
      rows[name] = {
        label: row.child("skill").text,
        number: row.child("skillNumber").text,
        plus: controls.child("plus").visible,
        minus: controls.child("minus").visible,
        y: row.y,
      };
    }
    const info = clip.child("attrInfo");
    const dialog = view.dialog?.child("textBoxes");
    return {
      paused: world.paused,
      name: text("name"),
      level: text("level"),
      xp: text("xp"),
      health: text("health"),
      healthBar: clip.child("healthBar").scale.x,
      stamina: text("stamina"),
      staminaBar: clip.child("staminaBar").scale.x,
      weight: text("weight"),
      mode: text("gameMode"),
      vitals: clip.child("vitals").visible
        ? { hunger: clip.child("vitals").child("hunger").text, sleep: clip.child("vitals").child("sleep").text }
        : null,
      attRem: clip.child("attRem").visible ? clip.child("attRem").child("attributeRemaining").text : null,
      skillRem: clip.child("skillRem").visible ? clip.child("skillRem").child("skillRemaining").text : null,
      confirm: clip.child("confirm").visible,
      pens: Object.fromEntries(PEN_FIELDS.map((name) => [name, text(`${name}Pen`)])),
      descTitle: text("descTitle"),
      desc: text("desc"),
      info: info.y === INFO_HIDDEN_Y ? null : { y: info.y, numbers: info.child("numbers").text, need: info.child("youNeed").text },
      rows,
      points: { ...story.player.points },
      spent: { ...spent },
      dialog: dialog ? { heading: dialog.child("headingText").text, body: dialog.child("bodyText").text } : null,
    };
  },

  // A + or - on a row, as a press on its button
  sheetPlus(name) {
    view.clip.child(name).child("levelUpControls").child("plus").handlers.onPress();
    return sheetDebug.sheetState();
  },

  sheetMinus(name) {
    view.clip.child(name).child("levelUpControls").child("minus").handlers.onPress();
    return sheetDebug.sheetState();
  },

  // The pointer over a row, as a mouse roll over its backing
  sheetHover(name) {
    view.clip.child(name).child("backing").handlers.onRollOver({ pointerType: "mouse" });
    return sheetDebug.sheetState();
  },

  sheetConfirm() {
    view.clip.child("confirm").handlers.onPress();
    return sheetDebug.sheetState();
  },

  sheetExit() {
    view.clip.child("exitBtn").handlers.onPress();
    return sheetDebug.sheetState();
  },
};
