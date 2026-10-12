// Pointer input on the stage: painting with one finger or the mouse, panning and zooming with two fingers, the wheel,
// the middle button or Space plus drag, and picking with a right click. Painting turns into strokes: while the
// pointer is held, one stroke every 50 ms carries the path since the last one, or the current cell when the pointer
// is still, so holding still keeps pouring. The Hand tool sends a grab on press, the newest cell every 50 ms while it
// moves, and a release on lift. Line and Box draw an outline while dragged and send one stroke on release; Fill and
// Lightning send one stroke on press; the Picker picks on press. A finger held still for 500 ms picks the element
// under it with any tool except the Hand.
import { EL, ELEMENTS, SHAPE, STROKE, W } from "./sim/index.js";

const FLUSH_MS = 50;
const MAX_POINTS = 64;
// A finger waits this long (or moves this far) before it paints, so the first finger of a pinch never paints
const TOUCH_HOLD_MS = 70;
const TOUCH_SLOP = 6;
const LONG_PRESS_MS = 500;
const ONLY_EMPTY = 1;
const MIRROR = 2;
const HAND_GRAB = 0;
const HAND_MOVE = 1;
const HAND_RELEASE = 2;
const HEAT_DELTA = 25;
// Tools that paint the picked element: choosing an element keeps one of these and switches any other tool to the brush
export const ELEMENT_TOOLS = new Set(["brush", "line", "box", "fill"]);
const DRAG_TOOLS = new Set(["line", "box"]);
// The stroke kind and first number of the tools that don't paint an element
const OTHER_STROKES = {
  heat: [STROKE.HEAT, HEAT_DELTA],
  cool: [STROKE.HEAT, -HEAT_DELTA],
  shove: [STROKE.SHOVE, 0],
};

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** Cuts a path into pieces of at most 64 points; each piece after the first starts where the last one ended */
export function splitPath(points) {
  const pieces = [];
  let from = 0;
  do {
    const piece = points.slice(from, from + MAX_POINTS);
    pieces.push(piece);
    from += MAX_POINTS - 1;
  } while (from < points.length - 1);
  return pieces;
}

export class Painter {
  constructor(stage, view, getWorld) {
    this.stage = stage;
    this.view = view;
    this.getWorld = getWorld;
    this.tool = "brush";
    this.element = EL.sand;
    this.size = 6;
    this.shape = SHAPE.ROUND;
    this.onlyEmpty = false;
    this.mirror = false;
    this.hue = 200;
    // The cell under the cursor, or null when the cursor is off the world
    this.pointer = null;
    // Whether the newest pointer event came from a finger or pen rather than a mouse
    this.touch = false;
    // While a Line or Box is being dragged: { tool, start, end } in cells, for the outline
    this.drag = null;
    this.strokeListeners = [];
    this.pickListeners = [];
    this.spaceListeners = [];
    this.startListeners = [];
    this.activeListeners = [];
    this.pointers = new Map();
    this.paint = null;
    this.waiting = null;
    this.gesture = null;
    this.longPress = null;
    this.panning = null;
    this.spaceHeld = false;
    this.listen();
  }

  onStroke(fn) {
    this.strokeListeners.push(fn);
  }

  /** fn(element) runs when a pick lands on a cell, by the Picker, a right click or a long press */
  onPick(fn) {
    this.pickListeners.push(fn);
  }

  /** fn() runs as a drag or tap starts, before its first stroke: a whole drag is one action */
  onStart(fn) {
    this.startListeners.push(fn);
  }

  /** fn(active) runs when a drag that paints starts (true) and ends (false): the controls fade back meanwhile */
  onActive(fn) {
    this.activeListeners.push(fn);
  }

  /** fn() runs when Space is used to drag the view rather than tapped on its own */
  onSpaceDrag(fn) {
    this.spaceListeners.push(fn);
  }

  listen() {
    const stage = this.stage;
    stage.addEventListener("pointerdown", (event) => this.down(event));
    stage.addEventListener("pointermove", (event) => this.move(event));
    stage.addEventListener("pointerup", (event) => this.up(event));
    stage.addEventListener("pointercancel", (event) => this.up(event));
    stage.addEventListener("pointerleave", (event) => {
      if (event.pointerType === "mouse" && this.paint === null) {
        this.pointer = null;
      }
    });
    stage.addEventListener("contextmenu", (event) => event.preventDefault());
    stage.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    window.addEventListener("keydown", (event) => {
      if (event.key === " ") {
        this.spaceHeld = true;
      }
    });
    window.addEventListener("keyup", (event) => {
      if (event.key === " ") {
        this.spaceHeld = false;
      }
    });
    window.addEventListener("blur", () => {
      this.spaceHeld = false;
    });
  }

  down(event) {
    try {
      this.stage.setPointerCapture(event.pointerId);
    } catch (e) {
      // The pointer can already be gone (lifted between the event and now); the gesture still works without capture
      console.warn("Sandfall: couldn't capture the pointer", e);
    }
    this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    this.pointer = this.view.cellAt(event.clientX, event.clientY);
    this.touch = event.pointerType !== "mouse";
    if (this.pointers.size >= 2) {
      this.startGesture();
      return;
    }
    const mouse = event.pointerType === "mouse";
    if (event.button === 1 || (event.button === 0 && this.spaceHeld)) {
      this.panning = { id: event.pointerId, x: event.clientX, y: event.clientY };
      if (this.spaceHeld) {
        this.spaceListeners.forEach((fn) => fn());
      }
    } else if (event.button === 2) {
      this.pick(event);
    } else if (event.button === 0 && (mouse || event.pointerType === "pen")) {
      this.startPaint(event);
    } else if (event.button === 0) {
      const timer = setTimeout(() => this.startPaint(event), TOUCH_HOLD_MS);
      this.waiting = { id: event.pointerId, x: event.clientX, y: event.clientY, timer };
      this.armLongPress(event);
    }
  }

  armLongPress(event) {
    // What was under the finger when it went down: by 500 ms the brush has painted over it
    const press = { id: event.pointerId, x: event.clientX, y: event.clientY };
    press.element = this.elementAt(event.clientX, event.clientY);
    press.timer = setTimeout(() => this.fireLongPress(press), LONG_PRESS_MS);
    this.longPress = press;
  }

  cancelLongPress() {
    if (this.longPress !== null) {
      clearTimeout(this.longPress.timer);
      this.longPress = null;
    }
  }

  // Picks the element that was under a finger that has held still. When that would change nothing (pouring sand with
  // a finger held still on sand), the finger keeps painting.
  fireLongPress(press) {
    this.longPress = null;
    const element = press.element;
    if (this.tool === "hand" || !ELEMENTS[element]?.paint) {
      return;
    }
    if (element === this.element && ELEMENT_TOOLS.has(this.tool)) {
      return;
    }
    this.cancelWaiting();
    if (this.paint?.id === press.id) {
      this.endPaint(false);
    }
    this.pickListeners.forEach((fn) => fn(element));
  }

  move(event) {
    const id = event.pointerId;
    const point = { x: event.clientX, y: event.clientY };
    const before = this.pointers.get(id);
    if (before) {
      this.pointers.set(id, point);
    }
    this.pointer = this.view.cellAt(point.x, point.y);
    this.touch = event.pointerType !== "mouse";
    if (this.longPress?.id === id && distance(point, this.longPress) > TOUCH_SLOP) {
      this.cancelLongPress();
    }
    if (this.gesture !== null && before) {
      this.moveGesture();
    } else if (this.panning?.id === id) {
      this.view.pan(point.x - this.panning.x, point.y - this.panning.y);
      this.panning.x = point.x;
      this.panning.y = point.y;
    } else if (this.waiting?.id === id && distance(point, this.waiting) > TOUCH_SLOP) {
      this.startPaint(event);
    } else if (this.paint?.id === id) {
      this.addPoint(point.x, point.y);
    }
  }

  up(event) {
    const id = event.pointerId;
    this.pointers.delete(id);
    if (this.longPress?.id === id) {
      this.cancelLongPress();
    }
    if (this.waiting?.id === id) {
      if (event.type === "pointercancel") {
        // The browser took the touch over: drop the wait without painting
        this.cancelWaiting();
      } else {
        // A quick tap: paint it now
        this.startPaint(event);
      }
    }
    if (this.paint?.id === id) {
      this.endPaint(event.type !== "pointercancel");
    }
    if (this.panning?.id === id) {
      this.panning = null;
    }
    if (this.gesture !== null && this.pointers.size < 2) {
      this.gesture = null;
    }
    if (event.pointerType !== "mouse") {
      this.pointer = null;
    }
  }

  wheel(event) {
    event.preventDefault();
    const lines = event.deltaMode === 1 ? 33 : 1;
    this.view.zoomAt(event.clientX, event.clientY, Math.exp(-event.deltaY * lines * 0.0015));
  }

  // The element in the cell under a screen point, or -1 outside the world
  elementAt(clientX, clientY) {
    const cell = this.view.cellAt(clientX, clientY);
    return cell === null ? -1 : this.getWorld().el[cell[1] * W + cell[0]];
  }

  pick(event) {
    const element = this.elementAt(event.clientX, event.clientY);
    if (element >= 0) {
      this.pickListeners.forEach((fn) => fn(element));
    }
  }

  startGesture() {
    this.cancelWaiting();
    this.cancelLongPress();
    if (this.paint !== null) {
      // A half-dragged outline is dropped; a brush keeps what it has painted
      this.endPaint(!this.paint.drag);
    }
    this.panning = null;
    const [a, b] = [...this.pointers.values()];
    this.gesture = { mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, span: Math.max(1, distance(a, b)) };
  }

  moveGesture() {
    const [a, b] = [...this.pointers.values()];
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const span = Math.max(1, distance(a, b));
    this.view.pan(mid.x - this.gesture.mid.x, mid.y - this.gesture.mid.y);
    this.view.zoomAt(mid.x, mid.y, span / this.gesture.span);
    this.gesture = { mid, span };
  }

  cancelWaiting() {
    if (this.waiting !== null) {
      clearTimeout(this.waiting.timer);
      this.waiting = null;
    }
  }

  startPaint(event) {
    // A finger that waited out the hold or moved starts from where it went down
    const press = this.waiting?.id === event.pointerId ? this.waiting : { x: event.clientX, y: event.clientY };
    this.cancelWaiting();
    const start = this.view.cellAt(press.x, press.y) ?? this.view.cellAt(event.clientX, event.clientY);
    if (start === null || this.paint !== null) {
      return;
    }
    if (this.tool === "picker") {
      this.pick(event);
      return;
    }
    this.startListeners.forEach((fn) => fn());
    if (this.tool === "lightning") {
      // A tap strikes once; holding or dragging does nothing more
      this.strokeListeners.forEach((fn) => fn([STROKE.BOLT, 0, 0, 0, 0, 0, start[0], start[1]]));
    } else if (this.tool === "fill") {
      this.strokeListeners.forEach((fn) => fn([STROKE.FILL, this.element, 0, 0, this.flags(), this.hue, ...start]));
    } else if (DRAG_TOOLS.has(this.tool)) {
      this.drag = { tool: this.tool, start, end: start };
      this.paint = { id: event.pointerId, tool: this.tool, drag: this.drag };
      this.activeListeners.forEach((fn) => fn(true));
    } else {
      this.startBrush(event, start);
    }
  }

  startBrush(event, start) {
    const hand = this.tool === "hand";
    const fresh = hand ? [] : [start];
    const timer = setInterval(() => this.flush(), FLUSH_MS);
    this.paint = { id: event.pointerId, tool: this.tool, hand, last: start, fresh, timer };
    this.activeListeners.forEach((fn) => fn(true));
    if (hand) {
      this.emitHand(HAND_GRAB, start);
    } else {
      this.flush();
    }
  }

  addPoint(clientX, clientY) {
    const cell = this.view.cellAt(clientX, clientY, true);
    if (this.paint.drag) {
      this.drag.end = cell;
      return;
    }
    const tail = this.paint.fresh.at(-1) ?? this.paint.last;
    if (cell[0] !== tail[0] || cell[1] !== tail[1]) {
      this.paint.fresh.push(cell);
    }
  }

  // Lifts the pen. A dragged Line or Box is sent now unless it was cancelled (commit false)
  endPaint(commit = true) {
    const paint = this.paint;
    clearInterval(paint.timer);
    if (paint.drag) {
      if (commit) {
        this.emitDrag(paint.drag);
      }
      this.drag = null;
    } else {
      if (paint.fresh.length > 0) {
        this.flush();
      }
      if (paint.hand) {
        this.emitHand(HAND_RELEASE, paint.last);
      }
    }
    this.paint = null;
    this.activeListeners.forEach((fn) => fn(false));
  }

  // Sends the path since the last stroke, starting from where that one ended; with no movement, the current cell again
  flush() {
    const paint = this.paint;
    const fresh = paint.fresh;
    if (paint.hand) {
      // The hand only needs where the pointer is now, and nothing while it holds still
      if (fresh.length > 0) {
        paint.last = fresh.at(-1);
        paint.fresh = [];
        this.emitHand(HAND_MOVE, paint.last);
      }
      return;
    }
    const points = fresh.length > 0 && fresh[0] === paint.last ? fresh : [paint.last, ...fresh];
    paint.last = points.at(-1);
    paint.fresh = [];
    if (paint.tool === "shove" && points.length < 2) {
      // Pushing needs a direction, and a pointer holding still has none
      return;
    }
    for (const piece of splitPath(points)) {
      this.emit(piece, paint.tool);
    }
  }

  flags() {
    return (this.onlyEmpty ? ONLY_EMPTY : 0) | (this.mirror ? MIRROR : 0);
  }

  emitHand(phase, cell) {
    const stroke = [STROKE.HAND, phase, 0, 0, 0, 0, cell[0], cell[1]];
    this.strokeListeners.forEach((fn) => fn(stroke));
  }

  emitDrag(drag) {
    const [x0, y0] = drag.start;
    const [x1, y1] = drag.end;
    const line = drag.tool === "line";
    const kind = line ? STROKE.LINE : STROKE.BOX;
    const stroke = [kind, this.element, line ? this.size : 0, line ? this.shape : 0, this.flags(), this.hue];
    this.strokeListeners.forEach((fn) => fn([...stroke, x0, y0, x1, y1]));
  }

  // One stroke for a piece of the path, by the tool the drag started with
  emit(points, tool) {
    const other = OTHER_STROKES[tool];
    const head = other ?? [STROKE.PAINT, tool === "eraser" ? 0 : this.element];
    const stroke = [...head, this.size, this.shape, this.flags(), other ? 0 : this.hue, ...points.flat()];
    this.strokeListeners.forEach((fn) => fn(stroke));
  }
}
