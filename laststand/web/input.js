// The one input state the world reads. The keyboard and mouse fill it here and touch.js fills the same fields from its
// sticks and buttons; each step clears the one-step flags at its end, so a press is seen by exactly one step even when
// it came between two. A held field is on while any key, the mouse or a finger holds it.
//
// Keys are read by their place on the keyboard (KeyboardEvent.code), so an AZERTY keyboard's Z, Q, S and D work with no
// setting. The listeners are added once and only record while the screen showing is one that owns the keyboard, so a
// menu never moves the player.

// Action -> the keys that do it
const BINDINGS = {
  left: ["KeyA", "ArrowLeft"],
  right: ["KeyD", "ArrowRight"],
  up: ["KeyW", "ArrowUp"],
  crouch: ["KeyS", "ArrowDown", "ControlLeft", "ControlRight"],
  sprint: ["ShiftLeft", "ShiftRight"],
  shove: ["Space"],
  slot1: ["Digit1"],
  slot2: ["Digit2"],
  swap: ["KeyQ"],
  reload: ["KeyR"],
  flash: ["KeyF"],
  use: ["KeyE"],
  g: ["KeyG"],
  backpack: ["KeyB", "KeyI", "Tab"],
  sheet: ["KeyC"],
  journal: ["KeyJ"],
  achievements: ["KeyX"],
  escape: ["Escape"],
};
// Action -> the field that says it is held
const HELD_FIELDS = { left: "left", right: "right", up: "upHeld", crouch: "crouchHeld", sprint: "sprintHeld" };
// Action -> the field that is true for the one step after the key went down
const EDGE_FIELDS = {
  up: "jumpPressed",
  crouch: "crouchPressed",
  shove: "shovePressed",
  reload: "reloadPressed",
  flash: "flashPressed",
  use: "usePressed",
  g: "gPressed",
  backpack: "backpackPressed",
  sheet: "sheetPressed",
  journal: "journalPressed",
  achievements: "achievementsPressed",
  escape: "escapePressed",
};
// Action -> what slotPressed holds after its key goes down
const SLOT_VALUES = { slot1: 1, slot2: 2, swap: "swap" };
// A wheel that reports lines moves a list about this many pixels a line
const LINE_PIXELS = 16;
const LEFT_BUTTON = 0;
// A second press this soon after the first is the second click of a double click, as Windows counts one by default.
// Where no button is under either press (the open world), it must also land this close (CSS pixels); a finger's double
// tap lands less exactly
const DOUBLE_CLICK = { ms: 500, mouse: 4, touch: 12 };

const actionsByCode = new Map();
for (const [action, codes] of Object.entries(BINDINGS)) {
  for (const code of codes) {
    actionsByCode.set(code, [...(actionsByCode.get(code) ?? []), action]);
  }
}

const held = new Set();
const pressed = new Set();
const released = new Set();
// What the touch controls hold now, by input field: a held field is on while a key or a finger holds it
const touchHolds = { left: false, right: false, upHeld: false, crouchHeld: false, sprintHeld: false, fireHeld: false };
// The page this reads (its canvas, the screen showing and the stage's size), set by attach
let host = null;
let cursorOn = true;
// A press the page's own buttons used: the world does not take it as a shot
let swallowed = false;
// The press being handled, { id, time, x, y, type, up }: from its pointerdown, seen before anything on the page hears
// it, to the end of the step after it comes up (a tap's action runs in that step). Then the press that shut a box or
// changed the buttons under it, while its second click may still come
let current = null;
let shutPress = null;
// The world stands still (a panel, a box, a room change): no press is a trigger pull until it runs again
let still = false;
// The aim stick was in its firing ring while the world stood still: it pulls no trigger until the finger leaves the ring
let aimSpent = false;

// Whether the aim stick holds the trigger now
function aimFires() {
  return touchHolds.fireHeld && !aimSpent;
}

export const input = {
  // Held now
  left: false,
  right: false,
  upHeld: false,
  crouchHeld: false,
  sprintHeld: false,
  fireHeld: false,
  // True for the one step after the key went down
  jumpPressed: false,
  crouchPressed: false,
  shovePressed: false,
  reloadPressed: false,
  flashPressed: false,
  usePressed: false,
  gPressed: false,
  backpackPressed: false,
  sheetPressed: false,
  journalPressed: false,
  achievementsPressed: false,
  escapePressed: false,
  // 1, 2 or "swap" for the one step after its key went down, otherwise null
  slotPressed: null,
  // True for the one step after a touch press toward a struggle (the struggle button, or a push of the move stick)
  struggleTap: false,
  // The stage point the arm points at, in stage pixels
  aim: { x: 380, y: 200 },
  // The mouse in stage pixels, whether its left button is down, and the button's edges for one step
  mouse: { x: 380, y: 200, down: false, pressed: false, released: false },
  // Pixels the wheel turned since the last step (down is positive)
  wheel: 0,
  // The screens that read the keyboard and mouse. The world adds itself; a screen that needs keys adds its own name
  owners: new Set(["world"]),
  keys: {
    down: (code) => held.has(code),
    pressed: (code) => pressed.has(code),
    released: (code) => released.has(code),
  },

  // Whether the system's arrow shows over the stage (menus) or the crosshair stands in for it (the playfield)
  get cursorShown() {
    return cursorOn;
  },

  set cursorShown(on) {
    cursorOn = Boolean(on);
    if (host?.app) {
      host.app.canvas.style.cursor = cursorOn ? "" : "none";
    }
  },

  // Starts listening for the page: { app, screen, width, height }. Once only
  attach(page) {
    if (host) {
      return;
    }
    host = page;
    const canvas = page.app.canvas;
    canvas.tabIndex = -1;
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    window.addEventListener("pointerdown", watchPress, true);
    window.addEventListener("pointerup", pressUp, true);
    window.addEventListener("pointercancel", () => (current = null), true);
    window.addEventListener("pointerdown", pointerDown);
    window.addEventListener("pointermove", pointerMove);
    window.addEventListener("pointerup", pointerUp);
    window.addEventListener("pointercancel", pointerUp);
    window.addEventListener("blur", clearHeld);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        clearHeld();
      }
    });
    canvas.addEventListener("wheel", wheelTurned, { passive: false });
    canvas.addEventListener("contextmenu", (event) => live() && event.preventDefault());
    input.cursorShown = cursorOn;
  },

  // Lets a screen read the keyboard and mouse
  own(screen) {
    input.owners.add(screen);
  },

  // The press being handled belongs to a button of the page's own (the canvas hears it first, then the window): the
  // world never takes it as a shot, even when the button just let the world run again
  swallowPress() {
    swallowed = true;
  },

  // The press being handled shut a box or a panel, or put other buttons under it: if the next press is the second click
  // of a double click and would press what now sits where the first click was, it presses nothing. A change a key, a
  // timer or the game itself makes arms nothing
  shutByClick() {
    if (current) {
      shutPress = current;
    }
  },

  // The world stops (true) or runs again: a held press stops being a trigger pull, and a press made while it stands
  // still never becomes one, so the player presses again on the playfield
  holdStill(on) {
    still = Boolean(on);
    if (still) {
      input.mouse.down = false;
      input.mouse.pressed = false;
      aimSpent = touchHolds.fireHeld;
      input.fireHeld = false;
    }
  },

  // A touch control holds a held field (left, right, upHeld, crouchHeld, sprintHeld, fireHeld) or lets it go
  touchHold(field, on) {
    touchHolds[field] = Boolean(on);
    refreshHeld();
    if (field === "fireHeld") {
      aimSpent = touchHolds.fireHeld && (aimSpent || still);
      input.fireHeld = input.mouse.down || aimFires();
    }
  },

  // Whether a touch control holds that field now
  touchHeld(field) {
    return touchHolds[field] === true;
  },

  // The end of a step: one-step flags clear
  endStep() {
    swallowed = false;
    if (current?.up) {
      current = null;
    }
    pressed.clear();
    released.clear();
    for (const field of Object.values(EDGE_FIELDS)) {
      input[field] = false;
    }
    input.slotPressed = null;
    input.struggleTap = false;
    input.wheel = 0;
    input.mouse.pressed = false;
    input.mouse.released = false;
  },

  // Everything let go (the window lost focus, or a story is starting)
  clear() {
    clearHeld();
    input.endStep();
  },
};

function live() {
  return Boolean(host) && input.owners.has(host.screen);
}

// A text box takes its own typing
function typing(target) {
  const box = /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName ?? "");
  return target instanceof HTMLElement && (target.isContentEditable || box);
}

function refreshHeld() {
  for (const [action, field] of Object.entries(HELD_FIELDS)) {
    input[field] = touchHolds[field] || BINDINGS[action].some((code) => held.has(code));
  }
}

function keyDown(event) {
  const actions = actionsByCode.get(event.code);
  if (!actions || !live() || typing(event.target)) {
    return;
  }
  // Tab, Space and the arrows would otherwise move focus or scroll the page
  event.preventDefault();
  if (held.has(event.code)) {
    return;
  }
  held.add(event.code);
  pressed.add(event.code);
  for (const action of actions) {
    if (EDGE_FIELDS[action]) {
      input[EDGE_FIELDS[action]] = true;
    }
    if (action in SLOT_VALUES) {
      input.slotPressed = SLOT_VALUES[action];
    }
  }
  refreshHeld();
}

// A key let go is always heard, so nothing stays held after a screen changes under the player's fingers
function keyUp(event) {
  if (!held.delete(event.code)) {
    return;
  }
  released.add(event.code);
  refreshHeld();
}

function clearHeld() {
  current = null;
  held.clear();
  for (const field of Object.keys(touchHolds)) {
    touchHolds[field] = false;
  }
  refreshHeld();
  aimSpent = false;
  input.fireHeld = false;
  input.mouse.down = false;
}

// A browser point in stage pixels, from the canvas as it is drawn
function stagePoint(event) {
  const box = host.app.canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - box.left) * host.width) / (box.width || 1),
    y: ((event.clientY - box.top) * host.height) / (box.height || 1),
  };
}

// Touch drives the same fields from its own sticks, so a finger never moves the mouse's aim or fires
function fromMouse(event) {
  return event.pointerType !== "touch";
}

function pointerMove(event) {
  if (!host || !fromMouse(event)) {
    return;
  }
  const point = stagePoint(event);
  input.mouse.x = point.x;
  input.mouse.y = point.y;
  input.aim.x = point.x;
  input.aim.y = point.y;
}

function pointerDown(event) {
  if (!host) {
    return;
  }
  // The first click gives the game the keyboard, inside Discord's frame too
  window.focus();
  if (swallowed) {
    swallowed = false;
    return;
  }
  if (event.button !== LEFT_BUTTON || !fromMouse(event) || event.target !== host.app.canvas) {
    return;
  }
  pointerMove(event);
  if (live() && !still) {
    input.mouse.down = true;
    input.mouse.pressed = true;
    input.fireHeld = true;
  }
}

// Runs first for every press, before Pixi hears it on the canvas: the second click (or tap) of a double one whose first
// shut a box or changed the buttons under it goes no further
function watchPress(event) {
  if (event.button !== LEFT_BUTTON) {
    return;
  }
  const { pointerId: id, timeStamp: time, clientX: x, clientY: y, pointerType: type } = event;
  const press = { id, time, x, y, type };
  const shut = shutPress;
  shutPress = null;
  if (shut && secondPress(shut, press)) {
    event.stopPropagation();
    return;
  }
  current = press;
}

function pressUp(event) {
  if (current?.id === event.pointerId) {
    current.up = true;
  }
}

// The second click presses nothing when it would press the button or row that now sits where the first click was (the
// next row slid up, SAVE AND QUIT under a shut box's OK); one on any other button goes through
function secondPress(first, press) {
  if (press.type !== first.type || press.time - first.time > DOUBLE_CLICK.ms) {
    return false;
  }
  const there = buttonAt(first);
  const here = buttonAt(press);
  if (there || here) {
    return there === here;
  }
  const reach = press.type === "touch" ? DOUBLE_CLICK.touch : DOUBLE_CLICK.mouse;
  return Math.abs(press.x - first.x) <= reach && Math.abs(press.y - first.y) <= reach;
}

// The Flash button (a clip with press handlers) a press at this browser point would reach now, or null for the stage,
// the touch controls and the map, which take presses by where they land
function buttonAt({ x, y }) {
  const events = host.app.renderer.events;
  const point = { x: 0, y: 0 };
  events.mapPositionToPoint(point, x, y);
  const target = events.rootBoundary.hitTest(point.x, point.y);
  return target?.handlers ? target : null;
}

function pointerUp(event) {
  if (!fromMouse(event) || (event.button !== LEFT_BUTTON && event.type !== "pointercancel")) {
    return;
  }
  if (input.mouse.down) {
    input.mouse.released = true;
  }
  input.mouse.down = false;
  input.fireHeld = aimFires();
}

function wheelTurned(event) {
  if (!live()) {
    return;
  }
  event.preventDefault();
  input.wheel += event.deltaMode === 1 ? event.deltaY * LINE_PIXELS : event.deltaY;
}
