// The touch controls of the world view (the original is keyboard and mouse only): two floating sticks and the round
// world buttons, drawn in Pixi on their own layer above the HUD, so no page element sits over a game button. The move
// stick walks as A and D do; the aim stick points the arm as the mouse does and fires from its outer ring; the buttons
// stand in for the keys (JUMP for W, CROUCH for S, RUN for Shift, SWAP for 1 / 2 / Q, RELOAD for R, SHOVE for Space,
// LIGHT for F). Three more stand at the bottom: the action button (E, with arrows to step through the things in reach),
// the G button and, over the original's A / D prompt, the struggle button. They write into input, the same state the
// keyboard and mouse fill, and show only while the world runs:
// a panel, a dialog, the map, the death screen, a menu or the upright card hides them.
//
// Each finger belongs to the control it started on until it lifts, so a thumb that slides off a button or out of a
// stick's area never starts anything else. The one exception: a finger that started on RUN and slides onto JUMP jumps
// once and keeps running. Places and sizes are in stage pixels; the layer sits in the scaled root, so they follow the
// stage's scale.
import { Container, Graphics, Text } from "./vendor/pixi.min.mjs";
import { input } from "./input.js";
import { interact } from "./interact.js";
import { player } from "./player.js";
import { toScreen } from "./rooms.js";
import { story } from "./story.js";
import { shoulder } from "./weapons.js";
import { world } from "./world.js";
import { struggle } from "./zombies.js";

// The sticks' ring and knob, across
const RING = 110;
const KNOB = 48;
// Past a fifth of the ring's radius sideways the move stick walks
const DEAD_SHARE = 0.2;
// The inner 70% of the aim stick's throw aims only; the ring beyond it holds the trigger
const AIM_ONLY_SHARE = 0.7;
// How far from the shoulder the aim stick puts the crosshair
const AIM_REACH = 160;
// Every control is at least this many screen pixels across, whatever the stage's scale
const LEAST_SCREEN = 44;
const REST_ALPHA = 0.35;
const PRESSED_ALPHA = 0.7;
// The HUD's plate and edge colours
const FILL = 0x1c1c1c;
const EDGE = 0xb6b0a5;
const EDGE_WIDTH = 3;
// The playfield between the original's bars
const TOP = 40;
const BOTTOM = 360;
// Where each stick may start (x range) and where its faint ring waits at rest
const AREAS = {
  move: { left: 0, right: 304, rest: { x: 160, y: 250 } },
  aim: { left: 456, right: 760, rest: { x: 560, y: 250 } },
};
// The round buttons beside the sticks: centre and width in stage pixels, and the word on each. A stick never starts on
// one. They sit in two strips at the playfield's edges (x 23 to 88, y 111 to 244 and x 616 to 755, y 135 to 297), clear
// of the tracked quest, the alerts, the people button and the cash and ammo counters
export const BUTTONS = {
  flashlight: { x: 48, y: 136, size: 50, label: "LIGHT" },
  crouch: { x: 56, y: 212, size: 64, label: "CROUCH" },
  jump: { x: 648, y: 176, size: 64, label: "JUMP" },
  run: { x: 648, y: 250, size: 64, label: "RUN" },
  swap: { x: 730, y: 160, size: 50, label: "SWAP" },
  reload: { x: 730, y: 216, size: 50, label: "RELOAD" },
  shove: { x: 730, y: 272, size: 50, label: "SHOVE" },
};
// The buttons a finger holds down, by the input field they hold; the others act once, on the press
const HOLDS = { crouch: "crouchHeld", run: "sprintHeld" };
// SWAP held this long while both weapon slots are armed shows "1" and "2" to pick a slot
const PICK_HOLD_MS = 300;
// The slot picks show over RELOAD and SHOVE, just under SWAP, so the thumb slides straight down onto one
const PICKS = { 1: "reload", 2: "shove" };
// AlternateGothic2 BT holds capitals and digits only; the words are this share of a button's width tall
const LABEL_FONT = "AlternateGothic2 BT";
const LABEL_SHARE = 0.3;
// A slot pick's digit is drawn larger, as it is the only thing on the pick
const PICK_LABEL_SHARE = 0.5;
const LETTERS = 0xe8e4da;
const PICK_FILL = 0x5a3d1c;
const BUTTON_FILL_ALPHA = 0.6;
// Words are drawn at most this many pixels per stage pixel
const MOST_LABEL_RESOLUTION = 3;
// The action button sits between the health bar and the cash counter, with the G button beside it. Stage pixels; each
// grows upward (and the G button rightward) to stay LEAST_SCREEN across when the stage is small
const ACTION = { left: 250, right: 510, bottom: 358, height: 58 };
const G_BUTTON = { left: 520, bottom: 358, width: 58, height: 58 };
// The arrows that step the action button through the things in reach, each this wide at least
const ARROW_WIDTH = 36;
const ARROW_SHARE = 0.2;
const PLATE_RADIUS = 10;
const ACTION_WORDS = 26;
const G_WORDS = 15;
const WORD_PADDING = 8;
const GREY_LETTERS = 0x949494;
// The struggle button is a ring this big over the original's A / D prompt, with the prompt showing through it
const STRUGGLE_SIZE = 100;
const STRUGGLE_FILL_ALPHA = 0.2;
// The world's pauses the controls stay up through: a room change is a moment's fade while the player keeps walking
const KEEP_THROUGH = new Set(["room change"]);

let host = null;
let layer = null;
// Whether the screen showing is the world view (show)
let wanted = false;
// Each stick: { name, pointer (the finger's id, or null), centre, offset, dir (the aim stick's unit direction), view }
const sticks = {};
// Each button: { name, def, pointer, view, disc, words, seen (a step has read its press), lateLift (lifted before any
// step read the press), ignored (CROUCH pressed while RUN was held), slid (RUN's finger has jumped), lit, state (SWAP:
// "down", "picking" or "done"), downAt }
const buttons = {};
// The two slot picks SWAP shows: { slot, def, view, disc, words, lit }
const picks = {};
// The action, G and struggle buttons: { name, view, plate, words, pointer, shown, key (what it was last drawn for),
// label }. The action button's arrows are drawn on its plate and told apart by where a finger lands
const bars = {};
// The stage scale the buttons were last drawn at
let drawnScale = 0;
// RUN's hold as last seen, and whether a sprint has run since RUN went down
let runWas = false;
let sprinted = false;

export const touch = {
  // -1 while the move stick walks left, 1 right, 0 otherwise
  moveDir: 0,

  get visible() {
    return Boolean(layer?.visible);
  },

  // The world view is showing (true) or another screen is (false)
  show(on) {
    wanted = Boolean(on);
    sync();
  },
};

// A control's size in stage pixels, grown so it is never under 44 screen pixels
export function controlSize(size) {
  return Math.max(size, LEAST_SCREEN / (host?.scale || 1));
}

function ringRadius() {
  return controlSize(RING) / 2;
}

function within(def, x, y) {
  return Math.hypot(x - def.x, y - def.y) <= controlSize(def.size) / 2;
}

function buttonAt(x, y) {
  return Object.values(buttons).find((b) => within(b.def, x, y)) ?? null;
}

function onButton(x, y) {
  return buttonAt(x, y) !== null || barAt(x, y) !== null;
}

function boxOf(left, bottom, width, height) {
  return { left, top: bottom - height, right: left + width, bottom };
}

// The action button's box as drawn at the stage's scale: grown upward to stay tall enough to press
function actionBox() {
  return boxOf(ACTION.left, ACTION.bottom, ACTION.right - ACTION.left, controlSize(ACTION.height));
}

// The top of the action button at the stage's scale, in stage pixels (the help line stands above it)
export function actionTop() {
  return actionBox().top;
}

function gBox() {
  return boxOf(G_BUTTON.left, G_BUTTON.bottom, controlSize(G_BUTTON.width), controlSize(G_BUTTON.height));
}

// The struggle button's centre follows the prompt over the player's head, in stage pixels
function struggleSpot() {
  const radius = controlSize(STRUGGLE_SIZE) / 2;
  const node = struggle.hud;
  if (!node || node.destroyed || !layer) {
    return { x: 0, y: 0, radius };
  }
  const at = layer.toLocal(node.getGlobalPosition());
  return { x: at.x, y: Math.max(at.y, TOP + radius), radius };
}

function inBox(box, x, y) {
  return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
}

function arrowWidth() {
  return controlSize(ARROW_WIDTH);
}

// The one of these that shows and holds a stage point: "struggle", "prev" or "next" (the action button's arrows, with
// two or more things in reach), "action" or "g"; or null
function barAt(x, y) {
  const ring = struggleSpot();
  if (bars.struggle?.shown && Math.hypot(x - ring.x, y - ring.y) <= ring.radius) {
    return "struggle";
  }
  const box = actionBox();
  if (bars.action?.shown && inBox(box, x, y)) {
    if (interact.count >= 2 && x <= box.left + arrowWidth()) {
      return "prev";
    }
    return interact.count >= 2 && x >= box.right - arrowWidth() ? "next" : "action";
  }
  return bars.g?.shown && inBox(gBox(), x, y) ? "g" : null;
}

// The slot pick under a stage point while SWAP shows them, or null
function pickAt(x, y) {
  if (buttons.swap?.state !== "picking") {
    return null;
  }
  return Object.values(picks).find((pick) => within(pick.def, x, y)) ?? null;
}

// The stick whose area holds a stage point, or null
function stickAt(x, y) {
  if (y < TOP || y > BOTTOM || onButton(x, y)) {
    return null;
  }
  return Object.values(sticks).find((stick) => x >= AREAS[stick.name].left && x <= AREAS[stick.name].right) ?? null;
}

// ---------- Drawing ----------

function buildStick(name) {
  const view = new Container();
  view.label = `${name}Stick`;
  view.eventMode = "none";
  const ring = new Graphics()
    .circle(0, 0, RING / 2)
    .fill({ color: FILL, alpha: 0.5 })
    .stroke({ width: EDGE_WIDTH, color: EDGE });
  const knob = new Graphics()
    .circle(0, 0, KNOB / 2)
    .fill({ color: EDGE })
    .stroke({ width: EDGE_WIDTH, color: FILL });
  view.addChild(ring, knob);
  layer.addChild(view);
  const stick = { name, pointer: null, centre: { x: 0, y: 0 }, offset: { x: 0, y: 0 }, dir: null, view, ring, knob };
  sticks[name] = stick;
  rest(stick);
}

// A stick no finger holds: a faint ring at its resting place
function rest(stick) {
  stick.pointer = null;
  stick.offset = { x: 0, y: 0 };
  stick.view.position.copyFrom(AREAS[stick.name].rest);
  stick.view.alpha = REST_ALPHA;
  stick.knob.visible = false;
  stick.knob.position.set(0, 0);
  stick.ring.scale.set(ringRadius() / (RING / 2));
}

function drawHeld(stick) {
  stick.view.position.set(stick.centre.x, stick.centre.y);
  stick.view.alpha = PRESSED_ALPHA;
  stick.knob.visible = true;
  stick.knob.position.set(stick.offset.x, stick.offset.y);
  stick.ring.scale.set(ringRadius() / (RING / 2));
}

function buildRound(name, def, fill, share = LABEL_SHARE) {
  const view = new Container();
  view.label = name;
  view.eventMode = "none";
  const disc = new Graphics();
  const style = { fontFamily: LABEL_FONT, fontSize: def.size * share, fill: LETTERS };
  const words = new Text({ text: def.label, style });
  words.anchor.set(0.5);
  view.addChild(disc, words);
  view.position.set(def.x, def.y);
  layer.addChild(view);
  return { def, view, disc, words, fill, lit: false, bright: false };
}

function buildButton(name) {
  const round = buildRound(`${name}Button`, BUTTONS[name], FILL);
  const state = { name, pointer: null, seen: false, lateLift: false, ignored: false, slid: false, state: null };
  buttons[name] = { ...round, ...state, downAt: 0 };
}

function buildPick(slot) {
  const def = { ...BUTTONS[PICKS[slot]], label: String(slot) };
  picks[slot] = { ...buildRound(`pick${slot}`, def, PICK_FILL, PICK_LABEL_SHARE), slot, bright: true };
  picks[slot].view.visible = false;
}

function buildBars() {
  for (const name of ["action", "g", "struggle"]) {
    const view = new Container();
    view.label = `${name}Button`;
    view.eventMode = "none";
    view.visible = false;
    view.alpha = REST_ALPHA;
    const plate = new Graphics();
    const style = { fontFamily: LABEL_FONT, fontSize: name === "g" ? G_WORDS : ACTION_WORDS, fill: LETTERS };
    const words = new Text({ text: "", style: { ...style, align: "center" } });
    words.anchor.set(0.5);
    view.addChild(plate, words);
    layer.addChild(view);
    bars[name] = { name, view, plate, words, pointer: null, shown: false, key: "", label: "" };
  }
}

function barLook(bar) {
  bar.view.alpha = bar.pointer === null ? REST_ALPHA : PRESSED_ALPHA;
}

// The words at the plate's size (grown with it when the stage is small), shrunk to fit the room they have
function fitWords(words, grown, room) {
  words.resolution = Math.min(MOST_LABEL_RESOLUTION, (host.scale || 1) * host.app.renderer.resolution);
  words.scale.set(grown);
  const wide = (room.width - WORD_PADDING) / (words.width || 1);
  const tall = (room.height - WORD_PADDING) / (words.height || 1);
  words.scale.set(grown * Math.min(1, wide, tall));
}

function plateOf(bar, box) {
  bar.plate
    .clear()
    .roundRect(box.left, box.top, box.right - box.left, box.bottom - box.top, PLATE_RADIUS)
    .fill({ color: FILL, alpha: BUTTON_FILL_ALPHA })
    .stroke({ width: EDGE_WIDTH, color: EDGE });
}

function drawArrow(plate, x, y, size, leftward) {
  const tip = leftward ? -size : size;
  plate.poly([x + tip, y, x - tip, y - size, x - tip, y + size]).fill({ color: LETTERS });
}

// The action button: its plate, the arrows when two or more things are in reach, and the prompt between them
function drawAction(bar, target, arrows) {
  const box = actionBox();
  const height = box.bottom - box.top;
  plateOf(bar, box);
  const middle = { x: (box.left + box.right) / 2, y: (box.top + box.bottom) / 2 };
  const side = arrows ? arrowWidth() : 0;
  if (arrows) {
    drawArrow(bar.plate, box.left + side / 2, middle.y, height * ARROW_SHARE, true);
    drawArrow(bar.plate, box.right - side / 2, middle.y, height * ARROW_SHARE, false);
  }
  bar.words.text = target.label;
  bar.words.style.fill = target.grey === true ? GREY_LETTERS : LETTERS;
  fitWords(bar.words, height / ACTION.height, { width: box.right - box.left - side * 2, height });
  bar.words.position.set(middle.x, middle.y);
}

// The G button: its plate with the words on two lines ("SWAP" over "WEAPONS")
function drawG(bar, text) {
  const box = gBox();
  plateOf(bar, box);
  bar.words.text = text.replace(/ (.*)/, "\n$1");
  const height = box.bottom - box.top;
  fitWords(bar.words, height / G_BUTTON.height, { width: box.right - box.left, height });
  bar.words.position.set((box.left + box.right) / 2, (box.top + box.bottom) / 2);
}

// The struggle button: a ring drawn about its own centre, which moves with the prompt
function drawStruggle(bar) {
  bar.plate
    .clear()
    .circle(0, 0, controlSize(STRUGGLE_SIZE) / 2)
    .fill({ color: FILL, alpha: STRUGGLE_FILL_ALPHA })
    .stroke({ width: EDGE_WIDTH, color: EDGE });
}

// Each step: what the three buttons say and where they stand, redrawn only when something about them changed
function barsStep() {
  const target = interact.target;
  const arrows = interact.count >= 2;
  const action = bars.action;
  action.shown = Boolean(target);
  action.view.visible = action.shown;
  const actionKey = `${host.scale}|${target?.label}|${target?.grey}|${arrows}`;
  if (action.shown && action.key !== actionKey) {
    action.key = actionKey;
    action.label = target.label;
    drawAction(action, target, arrows);
  }
  const g = bars.g;
  const gWords = interact.gPrompt.replace(/^\[G\]\s*/, "");
  g.shown = gWords !== "";
  g.view.visible = g.shown;
  if (g.shown && g.key !== `${host.scale}|${gWords}`) {
    g.key = `${host.scale}|${gWords}`;
    g.label = gWords;
    drawG(g, gWords);
  }
  const hold = bars.struggle;
  hold.shown = player.struggling === true && Boolean(struggle.hud) && !struggle.hud.destroyed;
  hold.view.visible = hold.shown;
  if (hold.shown) {
    if (hold.key !== String(host.scale)) {
      hold.key = String(host.scale);
      drawStruggle(hold);
    }
    const spot = struggleSpot();
    hold.view.position.set(spot.x, spot.y);
  }
}

// A button or pick at its size for the stage's scale: grown about its centre to stay 44 screen pixels across
function drawRound(round) {
  const radius = controlSize(round.def.size) / 2;
  round.disc
    .clear()
    .circle(0, 0, radius)
    .fill({ color: round.fill, alpha: BUTTON_FILL_ALPHA })
    .stroke({ width: EDGE_WIDTH, color: EDGE });
  round.words.scale.set((radius * 2) / round.def.size);
  round.words.resolution = Math.min(MOST_LABEL_RESOLUTION, (host.scale || 1) * host.app.renderer.resolution);
  look(round);
}

// Pressed (a finger holds it, or RUN's finger rests on JUMP) or at rest. A slot pick stands out a step brighter, as it
// shows only while SWAP is held
function look(round) {
  const held = round.pointer !== undefined && round.pointer !== null;
  if (round.bright) {
    round.view.alpha = held || round.lit ? 1 : PRESSED_ALPHA;
  } else {
    round.view.alpha = held || round.lit ? PRESSED_ALPHA : REST_ALPHA;
  }
}

function drawAllRounds() {
  drawnScale = host.scale;
  for (const round of [...Object.values(buttons), ...Object.values(picks)]) {
    drawRound(round);
  }
}

// ---------- Fingers ----------

// A browser point in stage pixels, from the canvas as it is drawn
function stagePoint(event) {
  const box = host.app.canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - box.left) * host.width) / (box.width || 1),
    y: ((event.clientY - box.top) * host.height) / (box.height || 1),
  };
}

function pressed(event) {
  const at = layer.toLocal(event.global);
  const pick = pickAt(at.x, at.y);
  if (pick) {
    choosePick(pick.slot);
    return;
  }
  const bar = barAt(at.x, at.y);
  if (bar) {
    pressBar(bar, event.pointerId);
    return;
  }
  const button = buttonAt(at.x, at.y);
  if (button) {
    pressButton(button, event.pointerId);
    return;
  }
  const stick = stickAt(at.x, at.y);
  if (!stick || stick.pointer !== null) {
    return;
  }
  stick.pointer = event.pointerId;
  stick.centre = { x: at.x, y: at.y };
  drag(stick, at);
}

// The thumb moved: the knob follows it inside the ring, and past the ring the stick slides along behind it
function drag(stick, at) {
  const radius = ringRadius();
  let dx = at.x - stick.centre.x;
  let dy = at.y - stick.centre.y;
  const reach = Math.hypot(dx, dy);
  if (reach > radius) {
    dx *= radius / reach;
    dy *= radius / reach;
    stick.centre = { x: at.x - dx, y: at.y - dy };
  }
  stick.offset = { x: dx, y: dy };
  drawHeld(stick);
  if (stick.name === "move") {
    walkTo(dx);
  } else {
    aimAlong(dx, dy);
  }
}

function moved(event) {
  for (const stick of Object.values(sticks)) {
    if (stick.pointer === event.pointerId) {
      drag(stick, stagePoint(event));
    }
  }
  if (buttons.run.pointer === event.pointerId) {
    slideRun(stagePoint(event));
  }
  if (buttons.swap.pointer === event.pointerId && buttons.swap.state === "picking") {
    hoverPicks(stagePoint(event));
  }
}

function lifted(event) {
  for (const stick of Object.values(sticks)) {
    if (stick.pointer === event.pointerId) {
      letGo(stick);
    }
  }
  for (const bar of Object.values(bars)) {
    if (bar.pointer === event.pointerId) {
      bar.pointer = null;
      barLook(bar);
    }
  }
  for (const button of Object.values(buttons)) {
    if (button.pointer === event.pointerId) {
      liftButton(button, stagePoint(event), event.type === "pointercancel");
    }
  }
}

function letGo(stick) {
  if (stick.name === "move") {
    walkTo(0);
  } else {
    // The arm stays where it points, like a resting mouse
    input.touchHold("fireHeld", false);
  }
  rest(stick);
}

function letGoAll() {
  for (const stick of Object.values(sticks)) {
    if (stick.pointer !== null) {
      letGo(stick);
    }
  }
  for (const button of Object.values(buttons)) {
    if (button.pointer !== null || button.lateLift) {
      button.pointer = null;
      button.state = null;
      releaseHold(button);
      look(button);
    }
  }
  for (const bar of Object.values(bars)) {
    bar.pointer = null;
    barLook(bar);
  }
  showPicks(false);
  setLit(buttons.jump, false);
}

// ---------- What the buttons do ----------

// The press of each button, as its key's press (playerControls F4:12373-12514)
const PRESSES = {
  flashlight: () => {
    input.flashPressed = true;
  },
  // Crouch does nothing while RUN (or Shift) is held, as S does while Shift is down (F4:12429)
  crouch: (button) => {
    button.ignored = input.sprintHeld;
    if (!button.ignored) {
      input.crouchPressed = true;
      input.touchHold("crouchHeld", true);
    }
  },
  // One jump per press: the world reads the press once and holding does not repeat (F4:12398-12425)
  jump: () => {
    input.jumpPressed = true;
  },
  run: (button) => {
    button.slid = false;
    input.touchHold("sprintHeld", true);
  },
  swap: (button) => {
    button.state = "down";
    button.downAt = performance.now();
  },
  reload: () => {
    input.reloadPressed = true;
  },
  shove: () => {
    input.shovePressed = true;
  },
};

function pressButton(button, pointerId) {
  if (button.pointer !== null) {
    return;
  }
  button.pointer = pointerId;
  button.seen = false;
  button.lateLift = false;
  PRESSES[button.name](button);
  look(button);
}

// A held button lets go of its field. A tap quicker than a step keeps its hold until a step has read it, so CROUCH's
// toggle and RUN never lose a press between two steps
function liftButton(button, at, cancelled) {
  button.pointer = null;
  if (button.name === "swap") {
    liftSwap(at, cancelled);
  }
  if (button.name === "run") {
    setLit(buttons.jump, false);
  }
  if (HOLDS[button.name]) {
    if (button.seen) {
      releaseHold(button);
    } else {
      button.lateLift = true;
    }
  }
  look(button);
}

function releaseHold(button) {
  button.lateLift = false;
  if (HOLDS[button.name] && !button.ignored) {
    input.touchHold(HOLDS[button.name], false);
  }
  button.ignored = false;
}

function setLit(round, on) {
  if (round.lit !== on) {
    round.lit = on;
    look(round);
  }
}

// RUN's finger sliding onto JUMP jumps once and keeps the sprint; sliding back off and on again does not jump again
function slideRun(at) {
  const jump = buttons.jump;
  const onJump = within(jump.def, at.x, at.y);
  if (onJump && !buttons.run.slid) {
    buttons.run.slid = true;
    input.jumpPressed = true;
  }
  setLit(jump, onJump);
}

// ---------- The action, G and struggle buttons ----------

// A press of one of them. The action button is E and the G button is G, read by the next step; the arrows step through
// the things in reach; the struggle button is one press toward breaking free, a new one for every tap
function pressBar(name, pointerId) {
  const bar = bars[{ prev: "action", next: "action" }[name] ?? name];
  if (bar.pointer !== null) {
    return;
  }
  bar.pointer = pointerId;
  barLook(bar);
  if (name === "action") {
    input.usePressed = true;
  } else if (name === "g") {
    input.gPressed = true;
  } else if (name === "struggle") {
    input.struggleTap = true;
  } else {
    interact.cycle(name === "next" ? 1 : -1);
  }
}

// ---------- SWAP and its slot picks ----------

function bothArmed() {
  const slots = story.player?.slots;
  return Boolean(slots) && slots.primary !== "hands" && slots.secondary !== "hands";
}

// The picks cover RELOAD and SHOVE while they show, so only the digits read there
function showPicks(on) {
  for (const pick of Object.values(picks)) {
    pick.view.visible = on;
    buttons[PICKS[pick.slot]].view.visible = !on;
    setLit(pick, false);
  }
  if (on) {
    buttons.swap.state = "picking";
  }
}

function hoverPicks(at) {
  for (const pick of Object.values(picks)) {
    setLit(pick, within(pick.def, at.x, at.y));
  }
}

// A slot picked, by SWAP's finger lifting on it or another finger tapping it
function choosePick(slot) {
  input.slotPressed = Number(slot);
  showPicks(false);
  buttons.swap.state = "done";
}

// A tap swaps, as Q does; lifted over a pick it takes that slot, and lifted elsewhere after the picks showed it does
// nothing
function liftSwap(at, cancelled) {
  const swap = buttons.swap;
  if (swap.state === "picking") {
    const pick = pickAt(at.x, at.y);
    showPicks(false);
    if (pick && !cancelled) {
      choosePick(pick.slot);
    }
  } else if (swap.state === "down" && !cancelled) {
    input.slotPressed = "swap";
  }
  swap.state = null;
}

// Each step: a hold lifted early lets go once an earlier step has read it, SWAP held long enough shows the picks, and
// every held press (or early lift still holding) is marked read, as the world's step runs right after this. So a tap
// between two steps keeps its hold for exactly one world step
function buttonsStep() {
  if (host.scale !== drawnScale) {
    drawAllRounds();
  }
  for (const button of Object.values(buttons)) {
    if (button.lateLift && button.seen) {
      releaseHold(button);
    }
  }
  const swap = buttons.swap;
  const held = swap.pointer !== null && swap.state === "down";
  if (held && performance.now() - swap.downAt >= PICK_HOLD_MS && bothArmed()) {
    showPicks(true);
  }
  for (const button of Object.values(buttons)) {
    button.seen = button.seen || button.pointer !== null || button.lateLift;
  }
}

// ---------- What the sticks do ----------

// The move stick sideways: walk left, right or not at all. A push out toward the zombie holding the player counts as
// one press toward breaking free, like a new press of A or D
function walkTo(dx) {
  const dead = ringRadius() * DEAD_SHARE;
  const dir = dx < -dead ? -1 : dx > dead ? 1 : 0;
  if (dir === touch.moveDir) {
    return;
  }
  const toward = struggle.side === "left" ? -1 : 1;
  if (player.struggling === true && dir === toward) {
    input.struggleTap = true;
  }
  touch.moveDir = dir;
  input.touchHold("left", dir < 0);
  input.touchHold("right", dir > 0);
}

// The aim stick: past the dead zone its direction aims, and in its outer ring it holds the trigger
function aimAlong(dx, dy) {
  const radius = ringRadius();
  const reach = Math.hypot(dx, dy);
  if (reach >= radius * DEAD_SHARE) {
    sticks.aim.dir = { x: dx / reach, y: dy / reach };
    pointArm(sticks.aim.dir);
  }
  input.touchHold("fireHeld", reach > radius * AIM_ONLY_SHARE);
}

// The arm points along a direction: the crosshair stands that far from the shoulder, as a mouse there would
function pointArm(dir) {
  if (!player.clip) {
    return;
  }
  const from = shoulder(player);
  const at = toScreen(from.x, from.y);
  input.aim.x = at.x + dir.x * AIM_REACH;
  input.aim.y = at.y + dir.y * AIM_REACH;
}

// While RUN is held and no sprint has run since it went down, the arm turns level toward the side the stick walks, so
// the sprint starts away from where the player was aiming (a sprint only runs toward where the arm points)
function runTurn() {
  const run = input.touchHeld("sprintHeld");
  if (run && !runWas) {
    sprinted = false;
  }
  runWas = run;
  if (player.sprinting === true) {
    sprinted = true;
  }
  if (run && !sprinted && touch.moveDir !== 0 && sticks.aim.pointer === null) {
    pointArm({ x: touch.moveDir, y: 0 });
  }
}

// ---------- Each step ----------

function shouldShow() {
  const paused = [...world.reasons].some((reason) => !KEEP_THROUGH.has(reason));
  return wanted && host.touch && world.active && !paused;
}

// The controls show only in the world view; hiding them lets go of every finger. A held aim stick keeps the crosshair
// at its distance from the shoulder as the player moves
function sync() {
  if (!layer) {
    return;
  }
  const shown = shouldShow();
  if (shown !== layer.visible) {
    layer.visible = shown;
    if (!shown) {
      letGoAll();
    }
  }
  if (!shown) {
    return;
  }
  if (sticks.aim.pointer !== null && sticks.aim.dir) {
    pointArm(sticks.aim.dir);
  }
  buttonsStep();
  barsStep();
  runTurn();
}

export function initTouch(owner, depth) {
  host = owner;
  layer = new Container();
  layer.label = "touchControls";
  layer.zIndex = depth;
  layer.visible = false;
  layer.eventMode = "static";
  // Only the sticks' areas, the buttons and the slot picks take presses, so the HUD's bars and buttons under the layer
  // keep theirs
  layer.hitArea = { contains: (x, y) => stickAt(x, y) !== null || onButton(x, y) || pickAt(x, y) !== null };
  layer.on("pointerdown", pressed);
  buildStick("move");
  buildStick("aim");
  for (const name of Object.keys(BUTTONS)) {
    buildButton(name);
  }
  buildPick(1);
  buildPick(2);
  buildBars();
  drawAllRounds();
  host.root.addChild(layer);
  window.addEventListener("pointermove", moved);
  window.addEventListener("pointerup", lifted);
  window.addEventListener("pointercancel", lifted);
  window.addEventListener("blur", letGoAll);
  host.steppers.push(sync);
}

// Helpers for page.py checks
export const touchDebug = {
  // The controls as they stand: shown or not, each stick's finger, centre and knob offset, and what they hold
  touchState() {
    const stick = (s) => ({
      pointer: s.pointer,
      centre: s.centre,
      offset: s.offset,
      dir: s.dir,
      at: [s.view.x, s.view.y],
    });
    return {
      visible: touch.visible,
      wanted,
      moveDir: touch.moveDir,
      move: stick(sticks.move),
      aim: stick(sticks.aim),
      held: {
        left: input.left,
        right: input.right,
        fire: input.fireHeld,
        sprint: input.sprintHeld,
        crouch: input.crouchHeld,
      },
      aimAt: { ...input.aim },
      ring: ringRadius() * 2,
      buttons: Object.fromEntries(
        Object.values(buttons).map((b) => [b.name, { pointer: b.pointer, alpha: b.view.alpha, state: b.state }]),
      ),
      bars: Object.fromEntries(
        Object.values(bars).map((b) => [
          b.name,
          { shown: b.shown, label: b.label, pointer: b.pointer, alpha: b.view.alpha, words: b.words.text },
        ]),
      ),
      count: interact.count,
      index: interact.index,
      picks: Object.values(picks).map((pick) => ({
        slot: pick.slot,
        shown: pick.view.visible,
        label: pick.words.text,
      })),
    };
  },

  // Each button's box in stage pixels, as drawn at the stage's scale: { name: { left, top, right, bottom } }
  touchBoxes() {
    const round = Object.fromEntries(
      Object.values(buttons).map((b) => {
        const radius = controlSize(b.def.size) / 2;
        const { x, y } = b.def;
        return [b.name, { left: x - radius, top: y - radius, right: x + radius, bottom: y + radius }];
      }),
    );
    const ring = struggleSpot();
    const struggleBox = {
      left: ring.x - ring.radius,
      top: ring.y - ring.radius,
      right: ring.x + ring.radius,
      bottom: ring.y + ring.radius,
    };
    return { ...round, action: actionBox(), g: gBox(), struggle: struggleBox };
  },
};
