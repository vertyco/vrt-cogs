// A one-line hint over a button: it shows when a mouse rests on the button, or when a finger is held on it (a long
// press). A long press only shows the hint: the click that would follow is dropped, so reading about an element
// doesn't pick it. A hint from a long press stays until the next touch anywhere, a scroll, or a few seconds pass, so
// it never sits over the list it describes for long.
const MOUSE_DELAY_MS = 350;
const HOLD_MS = 450;
// A touch screen's browser may follow a tap with pretend mouse events, which must not count as a mouse resting there
const AFTER_TOUCH_MS = 1000;
const EDGE = 8;
const GAP = 8;
const TOUCH_HINT_MS = 3500;
// A screen with no real hover (a phone) only shows hints on a long press
const NO_HOVER = window.matchMedia("(hover: none)");

let tip = null;
let anchor = null;
let showTimer = 0;
let watchTimer = 0;
let leaveTimer = 0;
let touchedAt = -Infinity;

function tipNode() {
  if (tip === null) {
    tip = document.createElement("div");
    tip.className = "hint";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.append(tip);
  }
  return tip;
}

function hide() {
  clearTimeout(showTimer);
  clearTimeout(leaveTimer);
  clearInterval(watchTimer);
  anchor = null;
  if (tip !== null) {
    tip.hidden = true;
  }
}

// Above the button when there is room, below it otherwise, and never past the screen's edge
function show(button, text) {
  const node = tipNode();
  node.textContent = text;
  node.hidden = false;
  // A list that is rebuilt under a resting pointer never sends the pointerleave, so a gone button ends its hint
  anchor = button;
  clearInterval(watchTimer);
  watchTimer = setInterval(() => {
    if (!anchor?.isConnected) {
      hide();
    }
  }, 250);
  const box = button.getBoundingClientRect();
  const wide = node.offsetWidth;
  const high = node.offsetHeight;
  const left = box.left + box.width / 2 - wide / 2;
  node.style.left = `${Math.max(EDGE, Math.min(left, document.documentElement.clientWidth - wide - EDGE))}px`;
  const above = box.top - high - GAP;
  node.style.top = `${above >= EDGE ? above : box.bottom + GAP}px`;
}

// Any new press anywhere ends the hint on show; a long press on a button then starts its own
document.addEventListener(
  "pointerdown",
  (event) => {
    if (event.pointerType !== "mouse") {
      touchedAt = performance.now();
    }
    if (tip !== null && !tip.hidden) {
      hide();
    }
  },
  true,
);

// A list scrolling under a hint moves its button away from it
document.addEventListener(
  "scroll",
  () => {
    if (tip !== null && !tip.hidden) {
      hide();
    }
  },
  true,
);

function mouseHovers(event) {
  return event.pointerType === "mouse" && !NO_HOVER.matches && performance.now() - touchedAt >= AFTER_TOUCH_MS;
}

/** Gives `button` a hint. `getText()` is read each time the hint is about to show */
export function attachHint(button, getText) {
  let held = false;
  let swallow = false;
  button.addEventListener("pointerenter", (event) => {
    if (mouseHovers(event)) {
      clearTimeout(showTimer);
      showTimer = setTimeout(() => show(button, getText()), MOUSE_DELAY_MS);
    }
  });
  button.addEventListener("pointerleave", (event) => {
    if (event.pointerType === "mouse") {
      hide();
    }
  });
  button.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse") {
      hide();
      return;
    }
    held = true;
    swallow = false;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => {
      swallow = true;
      show(button, getText());
      leaveTimer = setTimeout(hide, TOUCH_HINT_MS);
    }, HOLD_MS);
  });
  const lift = () => {
    if (!held) {
      return;
    }
    held = false;
    clearTimeout(showTimer);
  };
  button.addEventListener("pointerup", lift);
  button.addEventListener("pointercancel", () => {
    swallow = false;
    lift();
    hide();
  });
  // A held finger also makes the browser offer its own menu
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  button.addEventListener("click", (event) => {
    if (swallow) {
      swallow = false;
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  });
}
