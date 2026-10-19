// The backpack panel (int_inventory, sprite 5828; openInventory F4:7245, buildInventory F4:7860,
// updateInventoryItemInfo F4:7355): the list of everything carried, its seven filters, the weight and cash at the top
// and the detail of the item under the pointer. A press on a row uses it (food, medicine, books, clothing) or, with a
// weapon slot picked, equips it. The left side shows the two weapon slots, the clothing doll or the status panel
// (setupEquipPanel F4:7544, switchEquipPanel F4:7607, setupCharPanel F4:8544). B, I and Tab and the dock's backpack
// button open and close it. The rules for using, wearing and throwing away are inventory.js's; the rows are drawn by
// panels.js's rowList.
import { data } from "./data.js";
import { help } from "./help.js";
import { hud, setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { carry, definition, deleteRow, equip, label, rowsFor, unequip, useRow, weight, weightOf } from "./inventory.js";
import {
  canOpenPanel,
  closePanel,
  fadeInBox,
  fadeOutBox,
  finger,
  openPanel,
  panelOpen,
  rowList,
  setAlpha,
  tint,
} from "./panels.js";
import { adjustedSkill, refuseOpen, vitalState } from "./player.js";
import { goto, makeHuman, partAt, storyLook } from "./rig.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { findItem, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "backpack";
// The filter buttons, in the order the art places them. The original's list also names "tools", which has no button
const FILTERS = ["all", "weapons", "aid", "ammo", "clothing", "junk", "quest"];
// Rows that have no trash can: ammo and cash count up and down on their own, quest items stay
const KEPT_TYPES = new Set(["ammo", "money", "questItem"]);
// The filter buttons' look: lit (selected) is red with a white icon; under the pointer a light veil; at rest nothing
const SELECTED_RED = 0x990000;
const WHITE = 0xffffff;
const HOVER_ALPHA = 0.3;
// The scroll bar's track beside the list (F4:8076)
const BAR = { x: 538, top: 150, bottom: 300 };
// The item name shrinks to fit this width, and starts this high, dropping half a pixel for each step smaller
const NAME_WIDTH = 150;
const NAME_TOP = 98.6;
const NAME_STEP = 0.5;
// The use popup fades in, waits and fades out (useItemPopup F4:8390)
const POPUP_IN = 0.2;
const POPUP_HOLD = 3;
const POPUP_OUT = 0.2;
const MONEY_DIGITS = 5;
// The two weapon slots, and what a slot is called by its number
const SLOTS = ["primary", "secondary"];
const SLOT_NAMES = { 1: "primary", 2: "secondary", primary: "primary", secondary: "secondary" };
// Which side of the left panel a filter shows: the weapon slots, the clothing doll or the status panel. The other
// filters leave the left panel as it was (switchEquipPanel F4:7607)
const PANEL_FOR = { weapons: "weapons", clothing: "armor", aid: "aid" };
// The sound the switch to a left panel makes
const PANEL_SOUND = { weapons: "sound_inventoryEquipConfirm", clothing: "sound_inventoryClothingOn" };
const HANDS = "hands";
// The clothing doll's text fields, and what each shows: the clothes slot it reads (updateArmorPanel F4:7644)
const ARMOUR_FIELDS = {
  face: "face",
  eyes: "eyes",
  head: "head",
  torso: "top",
  armor: "torso",
  legs: "bottom",
  feet: "shoes",
};
// The doll stands in the clothing panel at 70% (addInventoryModel F4:7654)
const DOLL = { x: -65, y: 80, scale: 0.7 };
// The question for throwing away a premium or prize item (F4:8083), in the dialog box that fades in over the panel
const DELETE_ASK = {
  heading: "DELETE UNIQUE ITEM?",
  body: "YOU WILL NOT BE ABLE\rTO GET THIS ITEM AGAIN\rFOR THIS CHARACTER",
  yes: "DELETE",
  no: "CANCEL",
};
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
const WEAPON_BARS = [
  ["DAMAGE", "maxDamage"],
  ["ACCURACY", "maxAccuracy"],
  ["KNOCKBACK", "maxKnockback"],
  ["NOISE", "maxNoise"],
];

// What the list shows (currentFilter F4:26659), and which side the left panel shows (currentPanel F4:26664)
let filter = "all";
let panelMode = "weapons";
// The weapon slot picked and waiting for a weapon row ("primary" or "secondary"), or null
let equipSlot = null;
// The open backpack: { clip, list }
let view = null;

function constant(name) {
  return data.actors.constants[name];
}

function roundDecimal(value, places) {
  const scale = 10 ** places;
  return Math.round(value * scale) / scale;
}

// ---------- The detail panel ----------

function weightLine(item) {
  return `WEIGHT: ${item.weight}`;
}

// The four bars and numbers of a weapon: damage (a blast's own damage when it has one), accuracy (higher is tighter, so
// it is shown from the loosest), knockback and noise, each a share of the most the game has
function weaponBars(item) {
  const damage = item.splashDamage ?? item.damage;
  const accuracy = item.accuracy === undefined ? null : Math.max(0, constant("maxAccuracy") - item.accuracy * 10);
  const values = [damage, accuracy, item.knockback, item.weaponNoise ?? 0];
  return values.map((value, place) => {
    const most = constant(WEAPON_BARS[place][1]);
    if (value === null) {
      return { label: WEAPON_BARS[place][0], number: "N/A", percent: 0 };
    }
    const shown = place === 2 ? value : roundDecimal(value, 2);
    const percent = Math.min(100, Math.round((value / most) * 100));
    return { label: WEAPON_BARS[place][0], number: String(shown), percent };
  });
}

function weaponInfo(item) {
  const firearm = item.weaponClass === "firearm";
  const ammo = firearm ? data.items.ammo[item.ammoType] : null;
  return {
    bars: weaponBars(item),
    ammo: ammo ? String(story.ammo[item.ammoType] ?? "") : "",
    fields: [weightLine(item), `SKILL: ${item.skill.toUpperCase()}`, ammo ? `AMMO: ${ammo.invName}` : "", ""],
  };
}

// A book's reading bonus, with the part Smarts adds
function bookInfo(item) {
  const smarts = Math.ceil(adjustedSkill(story.player, "smarts") / constant("bookSmartsMod"));
  return {
    fields: [
      weightLine(item),
      "EFFECT: ",
      `+${Math.ceil(smarts + item.bonus)} ${item.effect.toUpperCase()}`,
      `(+${smarts} FROM SMARTS)`,
    ],
  };
}

const DETAIL = {
  weapon: weaponInfo,
  food: (item) => ({ fields: [weightLine(item), `EFFECT: +${item.bonus}%`, "", ""] }),
  meds: (item) => ({ fields: [weightLine(item), `EFFECT: ${item.effect.toUpperCase()}`, "", ""] }),
  books: bookInfo,
  junk: (item) => ({ fields: [weightLine(item), "", "", ""] }),
  money: (item) => ({ fields: [weightLine(item), "", "", ""] }),
};

// What the detail panel shows for a backpack row, or for nothing: the name, picture, description, the lines under the
// picture, the number of rounds held for a gun, and the weapon bars (null when the item has none)
export function infoOf(row) {
  const blank = { name: "", desc: "", icon: "none", ammo: "", bars: null, fields: ["", "", "", ""] };
  if (!row) {
    return blank;
  }
  const item = definition(row);
  const name = row.type === "ammo" ? item.invName.toUpperCase() : label(row);
  const info = { ...blank, name, icon: item.icon, desc: item.desc ?? "", ...DETAIL[row.type]?.(item) };
  if (row.type === "ammo") {
    info.desc = `${story.ammo[row.ammoType]}${item.desc}`;
  }
  return info;
}

// The item's name, kept to its box by drawing it smaller, a little lower for each step
function setName(field, text) {
  setText(field, text);
  const smaller = Math.max(0, Math.ceil(field.def.size - field.sizeFor(text)));
  field.y = NAME_TOP + smaller * NAME_STEP;
}

function showInfo(row) {
  paintInfo(infoOf(row));
}

function paintInfo(info) {
  const clip = view.clip;
  setName(clip.child("itemName"), info.name);
  setText(clip.child("desc"), info.desc);
  setText(clip.child("ammoText"), info.ammo);
  const icon = clip.child("infoIcon");
  icon.gotoAndStop("none");
  icon.gotoAndStop(info.icon);
  info.fields.forEach((text, place) => setText(clip.child(`field${place + 1}`), text));
  const panel = clip.child("barPanel");
  panel.visible = Boolean(info.bars);
  info.bars?.forEach((bar, place) => {
    setText(panel.child(`field${place + 1}`), bar.label);
    setText(panel.child(`number${place + 1}`), bar.number);
    panel.child(`bar${place + 1}`).scale.x = bar.percent / 100;
  });
}

// ---------- The list ----------

function toEntry(row) {
  return {
    key: row.id,
    label: label(row),
    value: String(weightOf(row)),
    marked: row.eqd === true,
    trash: !KEPT_TYPES.has(row.type),
    item: row,
  };
}

function refreshTop() {
  const clip = view.clip;
  setText(clip.child("backPack"), filter === "all" ? "BACKPACK" : `BACKPACK - ${filter.toUpperCase()}`);
  setText(clip.child("carryWeight"), `${weight()} / ${carry()} lbs`);
  setText(clip.child("totalMoney"), String(Math.floor(story.player.cash)).padStart(MONEY_DIGITS, "0"));
}

// Draws the list again from what is carried, and the detail of the row still lit (keepInfo leaves the detail as it is)
function refresh(keepInfo = false) {
  const list = view.list;
  list.setRows(rowsFor(filter).map(toEntry));
  refreshTop();
  paintLeft();
  if (!keepInfo) {
    showInfo(list.hot?.row.item ?? null);
  }
}

// ---------- The left panel ----------

function weaponIn(slot) {
  return data.items.weapons[story.player.slots[slot]] ?? data.items.weapons[HANDS];
}

// What the detail panel shows for the weapon in a slot. Bare hands have no picture, bars or words but the name
function slotInfo(slot) {
  const weapon = weaponIn(slot);
  if (weapon.type === "weapon") {
    return infoOf({ type: "weapon", ref: weapon.ref });
  }
  return { ...infoOf(null), name: weapon.name.toUpperCase() };
}

// A weapon's picture shows its scope or suppressor, and a suppressed one sits further back (updateInventory F4:7258)
function paintIcon(icon, weapon) {
  goto(icon, weapon.ref);
  if (weapon.weaponBase) {
    goto(icon, weapon.weaponBase);
  }
  const scoped = weapon.mod === "scope" || weapon.mod === "specOps";
  const quiet = weapon.mod === "suppressed" || weapon.mod === "specOps";
  for (const [name, shown] of [["scope", scoped], ["suppressor", quiet]]) {
    const part = partAt(icon, `item.${name}`);
    if (part) {
      part.visible = shown;
    }
  }
  icon.x = icon.restX - (quiet ? constant("suppWeaponOffset") : 0);
}

function paintSlot(box, slot) {
  const weapon = weaponIn(slot);
  const reserve = story.ammo[weapon.ammoType];
  setText(box.child("weaponName"), weapon.name.toUpperCase());
  setText(box.child("weaponDetails"), `DMG: ${weapon.damage} RNDS: ${weapon.maxAmmo}`);
  setText(box.child("ammo"), reserve === undefined ? "" : `AMMUNITION AVAILABLE: ${reserve}`);
  paintIcon(box.child("weaponIcon"), weapon);
  box.child("unequip").visible = weapon.ref !== HANDS;
  setAlpha(box.child("highlight"), equipSlot === slot ? 1 : 0);
}

// The clothing doll: a human dressed as the player is, standing in full-body pose (addInventoryModel F4:7654)
function paintDoll(panel) {
  if (!view.doll) {
    const { sex, look, backpack } = storyLook();
    view.doll = makeHuman({ sex, look, backpack, clothes: story.player.clothes });
    view.doll.setAnimMode("full");
    view.doll.clip.scale.set(DOLL.scale);
    view.doll.clip.position.set(DOLL.x, DOLL.y);
    panel.attach(view.doll.clip, "model");
  }
  view.doll.setClothes(story.player.clothes);
}

function paintArmour(panel) {
  for (const [field, place] of Object.entries(ARMOUR_FIELDS)) {
    setText(panel.child(field), findItem(story.player.clothes[place]).item.name.toUpperCase());
  }
  paintDoll(panel);
}

// The status panel: health, hunger and sleep as bars and words (setupCharPanel F4:8544). The art's second frame, for
// Run & Gun, has only the health bar
function paintStatus(panel) {
  const who = story.player;
  panel.gotoAndStop(story.mode === "runAndGun" ? "runGun" : "survivor");
  setText(panel.child("health"), `${Math.round(who.permHealth)} / ${who.healthMax}`);
  panel.child("healthBar").scale.x = Math.round((who.permHealth / who.healthMax) * 100) / 100;
  for (const vital of ["hunger", "sleep"]) {
    const left = 100 - who[vital];
    panel.child(`${vital}Bar`).scale.x = Math.round(left) / 100;
    setText(panel.child(vital), `${vitalState(vital).name.toUpperCase()} - ${Math.round(left)}%`);
  }
}

// What the left side shows now, drawn again from what the player has
function paintLeft() {
  const clip = view.clip;
  const slots = clip.child("equipWeapons");
  SLOTS.forEach((slot) => paintSlot(slots.child(slot), slot));
  if (panelMode === "armor") {
    paintArmour(clip.child("equipArmor"));
  } else if (panelMode === "aid") {
    paintStatus(clip.child("charPanel"));
  }
}

// Which side of the left panel is showing: the weapon slots, the clothing doll or the status panel. The picture on the
// switch shows the side it goes to, and the switch is hidden on the status panel
function showLeftSide() {
  const clip = view.clip;
  clip.child("equipWeapons").visible = panelMode === "weapons";
  clip.child("equipArmor").visible = panelMode === "armor";
  clip.child("charPanel").visible = panelMode === "aid";
  clip.child("equipIcon").visible = panelMode !== "aid";
  clip.child("panelSwitch").visible = panelMode !== "aid";
  clip.child("equipIcon").gotoAndStop(panelMode === "armor" ? "weapons" : "armor");
}

// Pressing a weapon slot: the list shows weapons, and the next weapon row pressed goes into this slot
// (F4:7573-7600)
function slotPick(slot) {
  const name = SLOT_NAMES[slot];
  if (!name || !view) {
    return;
  }
  sound.play("sound_inventoryEquipSelect");
  filter = "weapons";
  panelMode = "weapons";
  equipSlot = name;
  // The filter buttons keep their look: the original lists the weapons without lighting the weapons button
  showLeftSide();
  refresh(true);
}

function wireSlots(clip) {
  for (const slot of SLOTS) {
    const box = clip.child("equipWeapons").child(slot);
    const press = box.child("btn");
    press.setHandler("onPress", (event) => {
      slotPick(slot);
      if (finger(event)) {
        paintInfo(slotInfo(slot));
      }
    });
    press.setHandler("onRollOver", (event) => {
      if (!finger(event)) {
        paintInfo(slotInfo(slot));
      }
    });
    box.child("weaponIcon").restX = box.child("weaponIcon").x;
    box.child("unequip").setHandler("onPress", () => {
      sound.play("sound_inventoryEquipSelect");
      unequip(slot);
      refresh();
    });
  }
  clip.child("panelSwitch").setHandler("onPress", () => switchPanel(panelMode === "armor" ? "weapons" : "clothing"));
}

// ---------- The use popup ----------

// What a used item did, in the box over the list: { icon, text } from useRow
function popup(result) {
  const box = view.clip.child("useItem");
  if (!box || !result) {
    return;
  }
  stopTweens(box);
  box.visible = true;
  box.alpha = 0;
  box.child("icons").gotoAndStop(result.icon);
  setText(box.child("txt"), result.text);
  tween(box, "alpha", 100, POPUP_IN);
  tween(box, "alpha", 0, POPUP_OUT, {
    delay: POPUP_HOLD,
    done: () => {
      box.visible = false;
    },
  });
}

// ---------- Asking before deleting ----------

// The dialog box over the panel (showDialogBox F4:20000): everything behind it is shut off until a button is pressed
function closeDialog() {
  fadeOutBox(view.dialog, DIALOG.out);
  view.dialog = null;
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

// A premium or prize item can't be got again, so throwing it away asks first
function askDelete(row) {
  if (!view || view.dialog) {
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
  setText(box.child("textBoxes").child("headingText"), DELETE_ASK.heading);
  setText(box.child("textBoxes").child("bodyText"), DELETE_ASK.body);
  dialogButton(box, "button1", DELETE_ASK.yes, () => {
    closeDialog();
    deleteRow(row, true);
    refresh();
  });
  dialogButton(box, "button2", DELETE_ASK.no, closeDialog);
  fadeInBox(box, DIALOG.fade);
}

// ---------- Pressing rows ----------

// A press (or a second tap) on a row: use it, or equip it into the slot that was picked
function act(entry) {
  const row = entry.item;
  if (row.type === "weapon") {
    if (equipSlot && equip(equipSlot, row)) {
      refresh();
    }
    return;
  }
  popup(useRow(row));
  refresh();
}

// The trash can on a row. A premium or prize item has to be asked about first
function trash(entry) {
  const result = deleteRow(entry.item);
  if (result === "deleted") {
    refresh();
  } else if (result === "confirm") {
    backpack.askDelete(entry.item);
  }
}

// ---------- The filters ----------

// A filter button's look: lit, under the pointer, or at rest
function paintFilter(node, mode) {
  const backing = node.child("backing");
  const icon = node.child("icon");
  tint(backing, mode === "lit" ? SELECTED_RED : null);
  tint(icon, mode === "lit" ? WHITE : null);
  setAlpha(backing, { lit: 1, over: HOVER_ALPHA, rest: 0 }[mode]);
}

function paintFilters() {
  for (const name of FILTERS) {
    const node = view.clip.child(name);
    if (node) {
      paintFilter(node, name === filter ? "lit" : "rest");
    }
  }
}

// A filter button or the panel switch picked a filter: the list, and the left side where the filter has one
function setFilter(name) {
  filter = name;
  panelMode = PANEL_FOR[name] ?? panelMode;
  if (filter !== "weapons") {
    equipSlot = null;
  }
  paintFilters();
  showLeftSide();
  refresh();
}

function switchPanel(name) {
  sound.play(PANEL_SOUND[name]);
  setFilter(name);
}

// The art calls this once for each filter button as the panel is built (backPackFilterBtn F4:8171)
function filterButton(node, name) {
  node.setHandler("onRollOver", (event) => {
    if (!finger(event) && filter !== name) {
      paintFilter(node, "over");
    }
  });
  node.setHandler("onRollOut", (event) => {
    if (!finger(event) && filter !== name) {
      paintFilter(node, "rest");
    }
  });
  node.setHandler("onPress", () => {
    if (filter !== name) {
      sound.play("sound_interfacePage1");
      setFilter(name);
      if (PANEL_SOUND[name]) {
        sound.play(PANEL_SOUND[name]);
      }
    }
  });
}

// ---------- Opening and closing ----------

function build(clip) {
  view = { clip, list: null, doll: null, dialog: null };
  clip.child("useItem").visible = false;
  wireSlots(clip);
  showLeftSide();
  const panel = clip.child("scrollPanel");
  clip.child("itemName").fit();
  view.list = rowList(panel.child("scrollContainer"), [], {
    onSelect: (entry) => showInfo(entry.item),
    onAct: act,
    onTrash: trash,
    bar: { clip: clip.child("scrollBar"), line: clip.child("scrollBarLine"), ...BAR },
  });
  paintFilters();
  refresh();
}

// Closing saves (closeInventory F4:7241)
function finish() {
  view = null;
  equipSlot = null;
  savePoint("backpack");
  sound.play("sound_closeBag");
}

// Opens the backpack under a filter ("all", "weapons", "aid", "ammo", "clothing", "junk" or "quest"; the one it was
// last left on by default)
export function openBackpack(wanted = filter) {
  filter = FILTERS.includes(wanted) ? wanted : "all";
  panelMode = PANEL_FOR[filter] ?? panelMode;
  openPanel(PANEL, { art: "int_inventory", setup: build, close: finish });
  sound.play("sound_openBag");
  help.did("inventory");
}

function toggle() {
  if (panelOpen(PANEL)) {
    closePanel();
  } else if (canOpenPanel()) {
    openBackpack();
  }
}

// B, I and Tab. A zombie's hold refuses the opening with its alert
function keys() {
  if (!input.backpackPressed) {
    return;
  }
  input.backpackPressed = false;
  if (panelOpen(PANEL) || !canOpenPanel() || !refuseOpen()) {
    toggle();
  }
}

export const backpack = {
  open: openBackpack,
  close: closePanel,
  toggle,
  askDelete,
  slotPick,
  get filter() {
    return filter;
  },
  get isOpen() {
    return panelOpen(PANEL);
  },
};

export function initBackpack() {
  world.stage("interface", keys);
  hud.onOpen(PANEL, toggle);
  world.onReset(() => {
    filter = "all";
    panelMode = "weapons";
    equipSlot = null;
    view = null;
  });
}

// The art's load handlers: the close button and one for each filter button (invCloseButton F4:7168)
export const BACKPACK_LOAD_CALLS = {
  invCloseButton(node) {
    node.setHandler("onPress", () => closePanel());
  },
  backPackFilterBtn: filterButton,
};

// A weapon bar as "number@percent"
function shownBar(panel, place) {
  const percent = Math.round(panel.child(`bar${place}`).scale.x * 100);
  return `${panel.child(`number${place}`).text}@${percent}`;
}

// What the left side shows, in words: the panel, the picked slot and each side's fields
function leftState() {
  const clip = view.clip;
  const shown = (name) => clip.child(name).visible;
  const text = (panel, name) => clip.child(panel).child(name).text;
  const slots = {};
  for (const slot of SLOTS) {
    const box = clip.child("equipWeapons").child(slot);
    slots[slot] = {
      name: box.child("weaponName").text,
      details: box.child("weaponDetails").text,
      ammo: box.child("ammo").text,
      icon: box.child("weaponIcon").frame,
      unequip: box.child("unequip").visible,
      lit: box.child("highlight").alpha > 0,
    };
  }
  const armour = Object.fromEntries(Object.keys(ARMOUR_FIELDS).map((field) => [field, text("equipArmor", field)]));
  const status = ["health", "hunger", "sleep"].map((name) => text("charPanel", name));
  const bars = ["healthBar", "hungerBar", "sleepBar"].map((name) => clip.child("charPanel").child(name)?.scale.x);
  return {
    mode: panelMode,
    slot: equipSlot,
    shown: {
      weapons: shown("equipWeapons"),
      armor: shown("equipArmor"),
      aid: shown("charPanel"),
      switch: shown("panelSwitch"),
    },
    switchPicture: clip.child("equipIcon").frame,
    slots,
    armour,
    doll: view.doll ? { clothes: view.doll.clothes, mode: view.doll.mode } : null,
    status,
    bars,
  };
}

function dialogState(box) {
  const words = (name) => box.child("textBoxes").child(name).text;
  return {
    heading: words("headingText"),
    body: words("bodyText"),
    buttons: ["button1", "button2", "button3"].filter((name) => box.child(name).visible),
  };
}

// Helpers for page.py checks
export const backpackDebug = {
  // Opens the backpack, under a filter
  backpack(wanted) {
    openBackpack(wanted);
    return backpackDebug.backpackState();
  },

  // What the open backpack shows, in words and numbers; null when it is shut
  backpackState() {
    if (!view) {
      return null;
    }
    const text = (name) => view.clip.child(name)?.text ?? null;
    const list = view.list;
    const bar = view.clip.child("scrollBar");
    const panel = view.clip.child("barPanel");
    return {
      filter,
      paused: world.paused,
      title: text("backPack"),
      weight: text("carryWeight"),
      money: text("totalMoney"),
      rows: list.entries.map((entry) => `${entry.row.label} | ${entry.row.value}${entry.row.marked ? " | worn" : ""}`),
      lit: list.hot ? list.hot.index : null,
      scroll: { y: list.container.y, bar: bar.visible ? bar.y : null },
      name: text("itemName"),
      desc: text("desc"),
      fields: [1, 2, 3, 4].map((place) => text(`field${place}`)),
      ammoText: text("ammoText"),
      bars: panel.visible ? [1, 2, 3, 4].map((place) => shownBar(panel, place)) : null,
      popup: view.clip.child("useItem").visible ? view.clip.child("useItem").child("txt").text : null,
      left: leftState(),
      dialog: view.dialog ? dialogState(view.dialog) : null,
    };
  },

  // What the detail panel would show for the backpack row with an id (from rows())
  backpackInfo(id) {
    const row = rowsFor("all").find((each) => each.id === id);
    return infoOf(row ?? null);
  },

  // The pointer over a row, and a press on it, by its place in the list
  backpackHover(index) {
    return view.list.select(view.list.entries[index].row.key);
  },

  backpackPress(index) {
    act(view.list.entries[index].row);
    return backpackDebug.backpackState();
  },
};
