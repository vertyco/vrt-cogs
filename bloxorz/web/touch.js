// Bloxorz on a phone: a swipe on the board rolls the block, and one small Switch button changes between the two small
// blocks. There is no arrow pad. The page's keys (pieces.js) do the rolling; a swipe presses and releases the same
// directions a key would, so the rules about presses during a roll stay the original's.

// How far a finger moves (CSS pixels) before it counts as a swipe
const SWIPE_DISTANCE = 24;
// The board's slant in stage pixels (R47:1-6): one square right is (32, -5), one square down is (10, 16)
const RIGHT_X = 32;
const RIGHT_Y = -5;
const DOWN_X = 10;
const DOWN_Y = 16;
const SLANT = RIGHT_X * DOWN_Y - DOWN_X * RIGHT_Y;
// Room the Switch button takes: below the stage on an upright phone, beside it on a sideways one (CSS pixels)
export const SWITCH_BAND = 60;
export const SWITCH_SIDE = 80;
// The button's own size (style.css), which place() needs while the button is hidden
const SWITCH_WIDTH = 64;
const SWITCH_HEIGHT = 40;
const SWITCH_GAP = 8;

const touchScreen = window.matchMedia("(pointer: coarse)");

// True on a screen worked with a finger, where the Switch button's room is kept
export function isTouchScreen() {
  return touchScreen.matches;
}

// A finger's movement across the stage (stage pixels) as the nearest of the board's four ways: the movement is turned
// into board squares with the slant's inverse and the longer part wins
export function swipeDirection(dx, dy) {
  const right = (DOWN_Y * dx - DOWN_X * dy) / SLANT;
  const down = (-RIGHT_Y * dx + RIGHT_X * dy) / SLANT;
  if (Math.abs(right) >= Math.abs(down)) {
    return right > 0 ? "right" : "left";
  }
  return down > 0 ? "down" : "up";
}

// Wires the swipes on the stage's canvas and the Switch button (page.pieces comes from pieces.js). Returns place(), which
// puts the button by the stage, and update(), which shows it while the two small blocks are out
export function setupTouch(page, canvas, button) {
  // The one finger being followed: { id, x, y, dir } with dir set once it has swiped
  let finger = null;

  function release() {
    if (finger?.dir) {
      page.pieces.press(finger.dir, false);
    }
    finger = null;
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "touch" || finger || page.screen !== "stage") {
      return;
    }
    finger = { id: event.pointerId, x: event.clientX, y: event.clientY, dir: null };
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch (e) {
      console.warn("Bloxorz: couldn't follow the finger past the stage", e);
    }
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!finger || finger.dir || event.pointerId !== finger.id || page.screen !== "stage") {
      return;
    }
    const dx = event.clientX - finger.x;
    const dy = event.clientY - finger.y;
    if (Math.hypot(dx, dy) < SWIPE_DISTANCE) {
      return;
    }
    // Held like a key until the finger lifts
    finger.dir = swipeDirection(dx / page.world.scale.x, dy / page.world.scale.y);
    page.pieces.press(finger.dir, true);
  });
  for (const type of ["pointerup", "pointercancel"]) {
    canvas.addEventListener(type, (event) => {
      if (finger && event.pointerId === finger.id) {
        release();
      }
    });
  }

  button.addEventListener("click", () => {
    page.pieces.swap();
    // A later Space press would otherwise press the focused button too
    button.blur();
  });

  // The button sits in the room fit() keeps: under the stage's middle upright, or in the right bar's middle sideways
  function place(rect, box, below) {
    const width = SWITCH_WIDTH;
    const height = SWITCH_HEIGHT;
    if (below) {
      button.style.left = `${rect.left + (rect.width - width) / 2}px`;
      button.style.top = `${rect.bottom + SWITCH_GAP}px`;
    } else {
      button.style.left = `${rect.right + (box.right - rect.right - width) / 2}px`;
      button.style.top = `${rect.top + (rect.height - height) / 2}px`;
    }
  }

  // Shown on a touch screen while the two small blocks are out
  function update() {
    const show = isTouchScreen() && page.screen === "stage" && page.pieces.cubesOut();
    if (button.hidden === show) {
      button.hidden = !show;
    }
  }

  return { place, update };
}
