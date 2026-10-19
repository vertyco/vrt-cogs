// The stash: the footlocker (cont100) in 22 safe rooms, all opening the one shared stash (int_storage, sprite 6246;
// openStorage F4:16817, updateStorageList F4:16878, inventoryToStorage F4:17005, storageToInventory F4:17027,
// closeStorage F4:16843). Two lists side by side, the stash on the left and the backpack on the right. One press on a
// row (on a touch screen the first tap lights it and the second acts) moves that item to the other side if it fits
// under that side's weight limit, and "NO ROOM" flashes if it does not.
//
// The stash is story.storage: the rows of the items in it, the same rows the backpack holds, so an item keeps its id
// and its marks when it crosses. Equipped items, ammo, cash and quest items are not listed and stay in the backpack. The
// stash saves when it closes. The Survival Kit starts in it (story.js) and achievement prizes are sent to it
// (addToStorage).
import { data } from "./data.js";
import { help } from "./help.js";
import { hud, setText, stopTweens, tween } from "./hud.js";
import { addSource, register } from "./interact.js";
import { carry, removeRow, sortInventory, weight, weightOf } from "./inventory.js";
import { closePanel, fadeInBox, fadeOutBox, finger, openPanel, panelOpen, rowList, setAlpha } from "./panels.js";
import { recalcMovement } from "./player.js";
import { room } from "./rooms.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { addRow, findItem, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "storage";
// The footlocker's marker in the room's art
const MARKER = "cont100";
const KIND = "stash";
const PROMPT = "[E] OPEN STORAGE";
// How long the storage hint stays (showHelp F4:16824)
const HINT_SECONDS = 9;
// Rows that are never listed: ammo and cash count up and down on their own, quest items stay with the player
const KEPT_TYPES = new Set(["ammo", "money", "questItem"]);
// Each list's parts in the art: the scroll panel, the scroll bar's thumb and the depth of its track line, and the way
// the arrow between the lists points while a row of that list is lit (F4:16932, 16937). The thumb runs from BAR.top to
// BAR.bottom (setupStorageScrollBar F4:17086)
const SIDES = {
  stash: { panel: "storageScrollPanel", thumb: "storageScrollBar", line: 30, x: 311.2, point: -1, bar: "storageBar" },
  pack: { panel: "inventoryScrollPanel", thumb: "inventoryScrollBar", line: 34, x: 663.2, point: 1, bar: "backpackBar" },
};
const BAR = { top: 140, bottom: 290 };
// A row is 20 px tall and the list shows 180 px of them (storageItemHeight, F4:17082)
const VIEW_HEIGHT = 180;
// The "NO ROOM" note stays 3 s and fades over 2 s (F4:17016). The weight bar of the side that refused flashes red,
// then fades back to grey (the stash's bar in 0.2 s, the backpack's in 0.5 s)
const NO_ROOM_HOLD = 3;
const NO_ROOM_FADE = 2;
const BAR_RED = 0xff0000;
const BAR_FLASH = { stash: 0.2, pack: 0.5 };
const BAR_FADE = 2;
const BAR_FADE_WAIT = 1;
// The question for throwing away a premium or prize item (F4:17046), in the dialog box that fades in over the panel
const DELETE_ASK = {
  heading: "DELETE UNIQUE ITEM?",
  body: "YOU WILL NOT BE ABLE\rTO GET THIS ITEM AGAIN\rFOR THIS CHARACTER",
  yes: "DELETE",
  no: "CANCEL",
};
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
const MOST_RECORDED = 100;

// Registers fn(key, amount) for each counter the stash adds to: "fillStorage" for a move into the stash that did not
// fit (checkAch F4:17016)
const countListeners = [];
// What was moved, refused and deleted, newest last, for checks
const log = [];
// The open panel: { clip, stash, pack, dialog, side }
let view = null;

export function onStorageCount(fn) {
  countListeners.push(fn);
}

function count(key, amount = 1) {
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function note(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- Weight ----------

function roundTenth(value) {
  return Math.round(value * 10) / 10;
}

// The stash's limit: every character has the premium stash (spec 2.9)
export function stashLimit() {
  return data.actors.constants.premiumWeightLimit;
}

export function stashWeight() {
  return roundTenth(story.storage.reduce((sum, row) => sum + weightOf(row), 0));
}

// ---------- What is listed ----------

function listed(row) {
  return !row.eqd && !KEPT_TYPES.has(row.type);
}

function rowsOf(side) {
  return (side === "stash" ? story.storage : story.inventory).filter(listed);
}

function toRow(side, item) {
  return {
    key: item.id,
    label: findItem(item.ref).item.name.toUpperCase(),
    value: String(weightOf(item)),
    marked: false,
    side,
    item,
  };
}

// A premium or prize item can't be got again, so throwing it away asks first
function isUnique(item) {
  const def = findItem(item.ref).item;
  return def.premium === true || def.reward === true || item.prize === true;
}

// Puts an item in the stash whatever it weighs: the Survival Kit and achievement prizes arrive this way (F4:8336).
// prize marks the row as a prize, which asks before it is thrown away. Returns the new row
export function addToStorage(ref, { prize = false } = {}) {
  const row = addRow(ref, true);
  if (prize) {
    row.prize = true;
  }
  savePoint("storage");
  return row;
}

// ---------- Drawing ----------

function percentOf(held, most) {
  return Math.min(100, Math.round((held / most) * 100)) / 100;
}

function refreshTop() {
  const { clip } = view;
  const held = stashWeight();
  const carried = weight();
  setText(clip.child("storageWeight"), `${held} / ${stashLimit()}`);
  setText(clip.child("backPackWeight"), `${carried} / ${carry()}`);
  clip.child("storageBar").scale.x = percentOf(held, stashLimit());
  clip.child("backpackBar").scale.x = percentOf(carried, carry());
}

function refresh() {
  for (const side of Object.keys(SIDES)) {
    view[side].setRows(rowsOf(side).map((item) => toRow(side, item)));
  }
  refreshTop();
}

// The arrow between the lists shows which way a press on the lit row sends it. It stands there when the panel opens, and
// from the first lit row on it shows only while a row is lit
function arrowStep() {
  if (!view?.touched) {
    return;
  }
  const arrow = view.clip.child("storageArrow");
  const lit = view[view.side]?.hot;
  arrow.visible = Boolean(lit);
  if (lit) {
    arrow.scale.x = SIDES[view.side].point;
  }
}

// "NO ROOM" shows over the lists and the weight bar of the side that was full flashes red
function flashNoRoom(side) {
  const { clip } = view;
  const box = clip.child("noRoom");
  stopTweens(box);
  box.visible = true;
  box.alpha = 1;
  tween(box, "alpha", 0, NO_ROOM_FADE, {
    delay: NO_ROOM_HOLD,
    done: () => {
      box.visible = false;
    },
  });
  const bar = clip.child(SIDES[side].bar);
  stopTweens(bar);
  bar.flatColour = BAR_RED;
  tween(bar, "flat", 1, BAR_FLASH[side]);
  tween(bar, "flat", 0, BAR_FADE, { delay: BAR_FADE_WAIT });
}

// ---------- Moving and deleting ----------

// One press on a row (inventoryToStorage F4:17005, storageToInventory F4:17027). The press clicks whether or not the
// item fits
function move(entry) {
  const { side, item } = entry;
  if (view.dialog) {
    return;
  }
  sound.play("sound_interfacePage1");
  const toStash = side === "pack";
  const space = toStash ? stashLimit() - stashWeight() : carry() - weight();
  const from = toStash ? story.inventory : story.storage;
  const at = from.indexOf(item);
  if (at < 0) {
    return;
  }
  if (weightOf(item) > roundTenth(space)) {
    flashNoRoom(toStash ? "stash" : "pack");
    note("noRoom", { ref: item.ref, into: toStash ? "stash" : "pack" });
    if (toStash) {
      count("fillStorage");
    }
    return;
  }
  from.splice(at, 1);
  if (toStash) {
    story.storage.push(item);
  } else {
    story.inventory.push(item);
    sortInventory();
  }
  recalcMovement();
  note("move", { ref: item.ref, into: toStash ? "stash" : "pack" });
  refresh();
}

function remove(side, item) {
  sound.play("sound_trash");
  if (side === "stash") {
    story.storage.splice(story.storage.indexOf(item), 1);
  } else {
    removeRow(item);
  }
  note("delete", { ref: item.ref, from: side });
  savePoint("storage");
  refresh();
}

function closeDialog() {
  if (view) {
    fadeOutBox(view.dialog, DIALOG.out);
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

// The dialog box over the panel: everything behind it is shut off until a button is pressed
function askDelete(side, item) {
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
    remove(side, item);
  });
  dialogButton(box, "button2", DELETE_ASK.no, closeDialog);
  fadeInBox(box, DIALOG.fade);
}

function trash(entry) {
  const { side, item } = entry;
  if (view.dialog) {
    return;
  }
  if (isUnique(item)) {
    askDelete(side, item);
  } else {
    remove(side, item);
  }
}

// ---------- The panel ----------

function makeList(clip, side) {
  const { panel, thumb, line, x } = SIDES[side];
  return rowList(clip.child(panel).child("scrollContainer"), [], {
    art: "storageItem",
    rowHeight: data.actors.constants.storageItemHeight,
    viewHeight: VIEW_HEIGHT,
    onSelect: (row) => {
      view.side = row.side;
      view.touched = true;
    },
    onAct: (row) => move(row),
    onTrash: (row) => trash(row),
    bar: { clip: clip.child(thumb), line: clip.at(line), x, ...BAR },
  });
}

function build(clip) {
  view = { clip, stash: null, pack: null, dialog: null, side: "stash", touched: false };
  hud.hidePlay(true);
  clip.child("noRoom").visible = false;
  clip.child("exitButton").setHandler("onPress", () => closePanel());
  view.stash = makeList(clip, "stash");
  view.pack = makeList(clip, "pack");
  refresh();
}

// Closing saves (closeStorage F4:16852)
function finish() {
  view = null;
  hud.hidePlay(false);
  savePoint("storage");
  sound.play("sound_closeBag");
}

// Opens the stash panel, with the storage hint (openStorage F4:16817)
export function openStorage() {
  openPanel(PANEL, { art: "int_storage", setup: build, close: finish });
  help.show("storage", HINT_SECONDS);
  sound.play("sound_openBag");
  note("open");
}

// ---------- The footlocker in the room ----------

function footlockers() {
  const marker = room.markers[MARKER];
  if (!marker) {
    return [];
  }
  const { x, y, w, h } = marker;
  return [{ kind: KIND, key: `m:${MARKER}`, name: MARKER, x, y, w, h, marker }];
}

export function initStorage() {
  addSource(footlockers);
  register(KIND, { prompt: () => PROMPT, use: openStorage, look: {} });
  world.stage("interface", arrowStep);
  world.onReset(() => {
    if (view) {
      hud.hidePlay(false);
    }
    view = null;
    log.length = 0;
  });
}

export const storage = {
  open: openStorage,
  close: closePanel,
  addToStorage,
  stashWeight,
  stashLimit,
  onCount: onStorageCount,
  get isOpen() {
    return panelOpen(PANEL);
  },
};

// Helpers for page.py checks
export const storageDebug = {
  // Opens the stash panel wherever the player stands
  storageOpen() {
    openStorage();
    return storageDebug.storageState();
  },

  // What the open panel shows, in words; null when it is shut
  storageState() {
    if (!view) {
      return null;
    }
    const { clip } = view;
    const side = (name) => ({
      rows: view[name].entries.map((each) => `${each.row.label} | ${each.row.value}`),
      lit: view[name].hot ? view[name].hot.index : null,
      scroll: view[name].container.y,
    });
    const arrow = clip.child("storageArrow");
    return {
      stash: side("stash"),
      pack: side("pack"),
      stashWeight: clip.child("storageWeight").text,
      packWeight: clip.child("backPackWeight").text,
      stashBar: Math.round(clip.child("storageBar").scale.x * 100),
      packBar: Math.round(clip.child("backpackBar").scale.x * 100),
      arrow: arrow.visible ? arrow.scale.x : null,
      noRoom: clip.child("noRoom").visible,
      dialog: view.dialog !== null,
      paused: world.paused,
    };
  },

  // The pointer over a row, and a press on it, by side ("stash" or "pack") and place in the list
  storageHover(side, index) {
    return view[side].select(view[side].entries[index].row.key);
  },

  storagePress(side, index) {
    move(view[side].entries[index].row);
    return storageDebug.storageState();
  },

  storageTrash(side, index) {
    trash(view[side].entries[index].row);
    return storageDebug.storageState();
  },

  // The delete dialog's DELETE (true) or CANCEL (false)
  storageAnswer(yes) {
    const box = view.dialog;
    box.child(yes ? "button1" : "button2").handlers.onRelease?.();
    return storageDebug.storageState();
  },

  storageClose: closePanel,

  // What the moves, refusals and deletes did so far
  storageLog() {
    return log.map((each) => ({ ...each }));
  },
};
