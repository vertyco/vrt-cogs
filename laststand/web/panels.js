// Panels: the screens the player opens over the world (the backpack, the search and stash lists, the character sheet
// and the rest). Opening one stops the world and hides the help bar; closing brings both back. One panel is open at a
// time: opening another closes the first (openCloseInventory F4:7195 closes every other panel before it opens). E and
// Esc close whatever panel is open.
//
// rowList is the original's scrolling list of rows (buildInventory F4:7860, the search and stash lists): rows a fixed
// distance apart inside a masked container, scrolled by the mouse wheel (the wheel's turn is the original's
// scrollPage F4:18462), by dragging the scroll bar and, on a touch screen, by dragging a finger over the rows. On a
// desktop a row lights up under the pointer, shows its detail and acts on a press. On a touch screen a first tap
// selects a row (it lights up and shows its detail and trash can) and a second tap on the same row acts.
import { applyColor } from "./flash.js";
import { data } from "./data.js";
import { help } from "./help.js";
import { hud, setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

// The reason a panel holds the world still for
export const PANEL_PAUSE = "panel";
// The reason a panel opened with overlay: false holds it for: the dim bar with the place and the time stays off, as the
// achievements page's pauseGame(null, true) leaves it (F4:20613)
const BARE_PAUSE = "barePanel";
const WHITE = "#ffffff";
const BLACK = "#000000";
const DARK_RED = "#990000";
// How far a finger has to move over a row before the touch is a swipe and not a tap
const SWIPE = 8;
// The buttons a dialog box can show
const BOX_BUTTONS = ["button1", "button2", "button3"];
// The mouse wheel turns a list a notch at a time: Flash reports about 3 lines a notch, a browser about 100 pixels
const WHEEL_LINES = 3;
const WHEEL_NOTCH = 100;
// The row lit under the pointer is drawn at full strength; a row at rest at the list's shade, or none on every other
// row
const LIT = 1;
// What the original's tables say, for a page that has not loaded them yet
const DEFAULT_ROW = 22;
const DEFAULT_SHADE = 15;
const DEFAULT_VIEW = 190;
const DEFAULT_WHEEL = 5;
const LEFT_BUTTON = 0;

let page = null;
let depth = 0;
// { name, clip, options } of the panel open now
let open = null;
let lists = [];
// The list the wheel scrolls: the one the pointer or a finger last used
let focused = null;
// Panels closed during an event, destroyed on the next step so the event that closed them can finish
let dying = [];
// Buttons resting after their panel opened: { nodes, modes, left } with left in steps
let resting = [];

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

// A press, release or roll made by a finger (a touch screen's pointer)
export function finger(event) {
  return event?.pointerType === "touch";
}

// Draws a text field's words in a colour, keeping what they say
export function setColor(field, color) {
  if (!field || field.destroyed) {
    return;
  }
  field.def = { ...field.def, color };
  field.shown = null;
  field.draw();
}

// A part's own alpha, which the timeline keeps when it moves the placement
export function setAlpha(node, alpha) {
  node.scriptAlpha = alpha;
  node.alpha = alpha;
}

// colorTo with no time: a part drawn all in one colour (a number like 0x990000), or its own colours again with null
export function tint(node, colour) {
  node.scriptColor =
    colour === null
      ? null
      : { mult: [0, 0, 0, 256], add: [(colour >> 16) & 255, (colour >> 8) & 255, colour & 255, 0] };
  applyColor(node, 0);
}

// ---------- Opening and closing ----------

// Whether a panel is open, or with a name whether that one is
export function panelOpen(name = null) {
  return name ? open?.name === name : open !== null;
}

// Whether a panel may open now: a story is being played and nothing holds the world still but another panel. A dialog,
// a room change or a cutscene holds it for its own reason, and the panels stay shut then
export function canOpenPanel() {
  return world.active && Boolean(story.player) && [...world.reasons].every((reason) => reason === PANEL_PAUSE || reason === BARE_PAUSE);
}

// The clip of the panel open now, or null
export function panelClip() {
  return open?.clip ?? null;
}

// Opens a panel: the exported clip options.art (the name by default) is attached over the world, the world stops and
// the help bar hides. options.setup(clip) builds it; options.close(clip) runs when it closes; options.overlay false keeps
// the pause overlay off. Any other panel closes first. Returns the clip
export function openPanel(name, options = {}) {
  closePanel();
  const clip = page.attach(options.art ?? name, depth, name);
  const reason = options.overlay === false ? BARE_PAUSE : PANEL_PAUSE;
  open = { name, clip, options, reason };
  world.pause(reason);
  help.hideAll(true);
  options.setup?.(clip);
  // Its buttons may sit where the button that opened it was (TAKE ALL over the phone's action button), so the second
  // click of a double click presses nothing
  input.shutByClick();
  return clip;
}

// Closes the open panel. Returns whether there was one
export function closePanel() {
  if (!open) {
    return false;
  }
  const { clip, options, reason } = open;
  open = null;
  try {
    options.close?.(clip);
  } catch (e) {
    console.warn("Union City: a panel's close handler failed", e);
  }
  for (const list of lists) {
    list.dead ||= list.panel === clip;
  }
  clip.eventMode = "none";
  clip.visible = false;
  dying.push(clip);
  world.resume(reason);
  help.hideAll(false);
  // The press that closed it, still down, is not a shot, and the second click of a double click on its button presses
  // nothing
  input.swallowPress();
  input.shutByClick();
  return true;
}

// E and Esc close the open panel. The key is spent, so nothing else answers it
function keys() {
  if (open && (input.usePressed || input.escapePressed)) {
    input.usePressed = false;
    input.escapePressed = false;
    closePanel();
  }
}

// ---------- Dialog boxes ----------

// The black-out behind a box's buttons catches every press that misses them, and the world never takes it as a shot
function swallowOnShade(box) {
  box.child("blackOut")?.setHandler("onPress", () => input.swallowPress());
}

// A dialog box fades in (showDialogBox F4:20000). Its buttons take no press until it has, so the second press of a
// double press can't answer a box nobody has seen yet. options are the fade's (ease)
export function fadeInBox(box, seconds, options = {}) {
  const buttons = BOX_BUTTONS.map((name) => box.child(name)).filter((button) => button?.visible);
  const modes = buttons.map((button) => button.eventMode);
  for (const button of buttons) {
    button.eventMode = "none";
  }
  swallowOnShade(box);
  box.alpha = 0;
  tween(box, "alpha", 100, seconds, {
    ...options,
    done: () => buttons.forEach((button, index) => (button.eventMode = modes[index])),
  });
}

// A dialog box fades out and goes (closeDialogBox F4:20041). Its buttons are dead at once, but its black-out keeps
// swallowing presses until it has gone, so a press then reaches nothing under it; the second click of a double click
// on its button presses nothing even after it has gone
export function fadeOutBox(box, seconds, options = {}) {
  if (!box || box.destroyed) {
    return;
  }
  input.shutByClick();
  for (const name of BOX_BUTTONS) {
    const button = box.child(name);
    if (button) {
      button.eventMode = "none";
    }
  }
  swallowOnShade(box);
  stopTweens(box);
  tween(box, "alpha", 0, seconds, { ...options, done: () => box.destroy({ children: true }) });
}

// Buttons that take no press for some seconds after their panel opens, so the second tap of the double tap that
// opened it can't press one
export function restButtons(nodes, seconds) {
  resting.push({ nodes, modes: nodes.map((node) => node.eventMode), left: Math.round(seconds * page.lib.fps) });
  for (const node of nodes) {
    node.eventMode = "none";
  }
}

function wakeButtons() {
  for (const rest of resting) {
    rest.left -= 1;
    if (rest.left <= 0) {
      rest.nodes.forEach((node, index) => {
        if (!node.destroyed) {
          node.eventMode = rest.modes[index];
        }
      });
    }
  }
  resting = resting.filter((rest) => rest.left > 0);
}

// A new story or a load: whatever panel was open goes at once, and the lists with it
function forget() {
  if (open) {
    open.clip.destroy({ children: true });
    open = null;
    help.hideAll(false);
  }
  for (const clip of dying) {
    clip.destroy({ children: true });
  }
  dying = [];
  resting = [];
  lists = [];
  focused = null;
}

// ---------- Rows ----------

// How far a list's rows can scroll up
function scrollRoom(list) {
  return Math.max(0, list.entries.length * list.rowHeight - list.viewHeight);
}

// Where the scroll bar's thumb stands for the list's position, shown only when the rows overflow the view
function placeBar(list) {
  const bar = list.bar;
  if (!bar) {
    return;
  }
  const room = scrollRoom(list);
  const shows = list.entries.length * list.rowHeight >= list.viewHeight;
  bar.clip.visible = shows;
  if (bar.line) {
    bar.line.visible = shows;
  }
  bar.clip.y = bar.top + (room > 0 ? (-list.pos * (bar.bottom - bar.top)) / room : 0);
}

// Scrolls the rows to a position (0 at the top, negative below), as far as the rows go
function scrollTo(list, position) {
  list.pos = Math.min(0, Math.max(position, -scrollRoom(list)));
  list.container.y = list.pos;
  placeBar(list);
}

// The pointer's height in the list's own pixels, which stay still while the rows scroll
function pointerY(list) {
  return list.container.parent.toLocal(page.lib.pointer).y;
}

// A row lit (under the pointer, or selected by a finger) or at rest
function look(entry, lit) {
  const { backing, name, weight, trash, row } = entry;
  backing.gotoAndStop(lit ? "over" : "off");
  setAlpha(backing, lit ? LIT : entry.shade);
  setColor(name, lit ? WHITE : BLACK);
  setColor(weight, lit ? WHITE : DARK_RED);
  if (trash) {
    trash.visible = lit && row.trash !== false;
    if (!lit) {
      trash.gotoAndStop("close");
    }
  }
}

// A row becomes the lit one: it shows its detail and the list takes the wheel
function makeHot(list, entry) {
  if (list.hot === entry) {
    return;
  }
  if (list.hot) {
    look(list.hot, false);
  }
  list.hot = entry;
  focused = list;
  look(entry, true);
  sound.play("sound_interfaceOver");
  list.onSelect?.(entry.row, entry);
}

function press(list, entry, event) {
  if (finger(event)) {
    list.touch = { entry, y: pointerY(list), from: list.pos, swiping: false };
  } else if (event?.button === LEFT_BUTTON) {
    list.onAct?.(entry.row, entry);
  }
}

// A finger came up on a row: a tap when it went down on the same row and never swiped. The first tap selects the row,
// the second acts
function release(list, entry, event) {
  const touch = list.touch;
  list.touch = null;
  if (!finger(event) || !touch || touch.swiping || touch.entry !== entry) {
    return;
  }
  if (list.hot === entry) {
    list.onAct?.(entry.row, entry);
  } else {
    makeHot(list, entry);
  }
}

// The row's own parts take the pointer: the whole row, and the trash can that shows on a lit row
function wire(list, entry) {
  const { backing, trash } = entry;
  backing.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      list.leaving = null;
      makeHot(list, entry);
    }
  });
  // The pointer moving onto the trash can leaves the row for a moment: the list decides on its next step
  backing.setHandler("onRollOut", (event) => {
    if (!finger(event)) {
      list.leaving = entry;
    }
  });
  backing.setHandler("onPress", (event) => press(list, entry, event));
  backing.setHandler("onRelease", (event) => release(list, entry, event));
  backing.setHandler("onReleaseOutside", () => {
    list.touch = null;
  });
  if (trash) {
    wireTrash(list, entry);
  }
}

// The trash can on a row: the pointer over it keeps the row lit, and a press on it deletes
function wireTrash(list, entry) {
  const trash = entry.trash;
  trash.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      entry.overTrash = true;
      list.leaving = null;
      trash.gotoAndStop("open");
    }
  });
  trash.setHandler("onRollOut", (event) => {
    if (!finger(event)) {
      entry.overTrash = false;
      list.leaving = entry;
      trash.gotoAndStop("close");
    }
  });
  trash.setHandler("onPress", (event) => {
    if (finger(event) || event?.button === LEFT_BUTTON) {
      list.onTrash?.(entry.row, entry);
    }
  });
}

function addEntry(list, row, index) {
  const clip = page.lib.makeExported(list.art);
  list.container.attach(clip, `item${index}`);
  clip.y = index * list.rowHeight;
  const entry = {
    row,
    index,
    clip,
    backing: clip.child("backing"),
    name: clip.child("itemName"),
    weight: clip.child("weightText"),
    mark: clip.child(list.markName),
    trash: clip.child("deleteBtn"),
    shade: index % 2 === 1 ? 0 : list.shade,
    overTrash: false,
  };
  setText(entry.name, row.label, BLACK);
  setText(entry.weight, row.value ?? "", DARK_RED);
  if (entry.mark) {
    entry.mark.visible = row.marked === true;
  }
  look(entry, false);
  wire(list, entry);
  return entry;
}

// ---------- Scrolling ----------

// The thumb of the scroll bar is dragged between its top and bottom; the rows follow it
function wireBar(list) {
  const bar = list.bar;
  bar.clip.setHandler("onPress", () => {
    list.dragging = true;
    bar.clip.startDrag(false, [bar.x, bar.top, bar.x, bar.bottom]);
  });
  const drop = () => {
    list.dragging = false;
    bar.clip.stopDrag();
  };
  bar.clip.setHandler("onRelease", drop);
  bar.clip.setHandler("onReleaseOutside", drop);
}

function followBar(list) {
  const { clip, top, bottom } = list.bar;
  const share = (clip.y - top) / (bottom - top);
  list.pos = -share * scrollRoom(list);
  list.container.y = list.pos;
}

// A finger down on a row that has moved far enough scrolls the list with it
function swipe(list) {
  const touch = list.touch;
  const moved = pointerY(list) - touch.y;
  touch.swiping ||= Math.abs(moved) >= SWIPE;
  if (touch.swiping) {
    scrollTo(list, touch.from + moved);
  }
}

function stepList(list) {
  const leaving = list.leaving;
  if (leaving && !leaving.overTrash) {
    list.leaving = null;
    look(leaving, false);
    if (list.hot === leaving) {
      list.hot = null;
    }
  }
  if (list.dragging) {
    followBar(list);
  } else if (list.touch) {
    swipe(list);
  }
}

// How far the wheel's turn since the last step moves a list, in pixels (down is positive)
export function wheelStep() {
  return (input.wheel * constant("scrollSpeed", DEFAULT_WHEEL) * WHEEL_LINES) / WHEEL_NOTCH;
}

// The wheel turns the focused list: up is toward the top. The step is the original's (scrollSpeed a line, 3 lines a
// notch)
function turnWheel() {
  const list = focused && !focused.dead ? focused : lists.find((each) => !each.dead);
  if (list && input.wheel) {
    scrollTo(list, list.pos - wheelStep());
  }
}

function step() {
  for (const clip of dying) {
    if (!clip.destroyed) {
      clip.destroy({ children: true });
    }
  }
  dying = [];
  wakeButtons();
  lists = lists.filter((list) => !list.dead && !list.container.destroyed);
  if (open) {
    turnWheel();
  }
  for (const list of lists) {
    stepList(list);
  }
}

// ---------- The list ----------

// Replaces a list's rows. The lit row stays lit when its key is still there, and the scroll position stays as far as
// the new rows allow
function setRows(list, rows) {
  const keep = list.hot?.row.key;
  for (const entry of list.entries) {
    entry.clip.removeMovieClip();
  }
  Object.assign(list, { entries: [], hot: null, leaving: null, touch: null });
  rows.forEach((row, index) => list.entries.push(addEntry(list, row, index)));
  const again = list.entries.find((entry) => entry.row.key === keep);
  if (again) {
    list.hot = again;
    look(again, true);
  }
  scrollTo(list, list.pos);
  // Other rows now sit under the pointer (the next one slides up into a moved row's place), so the second click of a
  // double click presses nothing
  input.shutByClick();
}

// Lights the row with a key as a tap or the pointer would, showing its detail. Returns whether there was such a row
function selectRow(list, key) {
  const entry = list.entries.find((each) => each.row.key === key);
  if (entry) {
    makeHot(list, entry);
  }
  return Boolean(entry);
}

// Makes a scrolling list of rows in a masked container (the scrollContainer of a panel's scrollPanel).
// rows: [{ key, label, value, marked, trash }, ...] ("marked" draws the red square of a worn or wielded item, "trash"
// false hides the trash can). options: onSelect(row) when a row lights up, onAct(row) for a press or a second tap,
// onTrash(row), art (the row's exported clip, "inventoryItem"; a clip with no deleteBtn has no trash can), markName
// (the part that shows a row's "marked" state, "mark"), rowHeight, viewHeight, bar { clip, line, x, top,
// bottom } for the scroll bar. Returns { setRows(rows), select(key), scrollTo(position), entries, hot }
export function rowList(container, rows, options = {}) {
  const list = {
    container,
    art: options.art ?? "inventoryItem",
    markName: options.markName ?? "mark",
    rowHeight: options.rowHeight ?? constant("invItemYDist", DEFAULT_ROW),
    viewHeight: options.viewHeight ?? constant("scrollBarHide", DEFAULT_VIEW),
    shade: constant("itemGreyAlpha", DEFAULT_SHADE) / 100,
    bar: options.bar ?? null,
    onSelect: options.onSelect,
    onAct: options.onAct,
    onTrash: options.onTrash,
    panel: open?.clip ?? null,
    entries: [],
    hot: null,
    leaving: null,
    touch: null,
    dragging: false,
    dead: false,
    pos: 0,
    setRows: (next) => setRows(list, next),
    select: (key) => selectRow(list, key),
    scrollTo: (position) => scrollTo(list, position),
  };
  if (list.bar) {
    wireBar(list);
  }
  lists.push(list);
  focused ??= list;
  setRows(list, rows);
  return list;
}

export function initPanels(owner, band) {
  page = owner;
  depth = band;
  hud.noOverlay.add(BARE_PAUSE);
  page.steppers.push(step);
  world.stage("interface", keys);
  world.onReset(forget);
}

// Helpers for page.py checks
export const panelsDebug = {
  // The name of the open panel, or null
  panel() {
    return open?.name ?? null;
  },

  // Where the middle of a part of the open panel (a path like "scrollBar" or "barPanel.bar1") is, in the game frame's
  // CSS pixels, for page.py's tap
  // Every row of every live list, with the middle of its clip in page pixels: [[{ label, x, y, hot }, ...], ...]
  rowPoints() {
    const canvas = page.app.canvas.getBoundingClientRect();
    const k = canvas.width / page.app.screen.width;
    return lists
      .filter((list) => !list.dead && !list.container.destroyed)
      .map((list) =>
        list.entries.map((entry) => {
          const box = entry.clip.getBounds();
          return {
            label: entry.row.label,
            x: Math.round(canvas.left + (box.x + box.width / 2) * k),
            y: Math.round(canvas.top + (box.y + box.height / 2) * k),
            hot: list.hot === entry,
          };
        }),
      );
  },

  pointOf(path) {
    let node = open?.clip;
    for (const name of path.split(".")) {
      node = node?.child(name);
    }
    if (!node) {
      return null;
    }
    const box = node.getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: Math.round(canvas.left + (box.x + box.width / 2) * (canvas.width / page.app.screen.width)),
      y: Math.round(canvas.top + (box.y + box.height / 2) * (canvas.height / page.app.screen.height)),
    };
  },
};
