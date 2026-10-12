// The 2D canvas over the world: brush ring, drag outlines, previews, creatures and other players' cursors. Each part
// of the page adds a layer; every frame the canvas is cleared and the layers draw in order, lowest first.
import { ELEMENTS, SHAPE, W } from "../sim/index.js";

const layers = [];
let canvas = null;
let ctx = null;
let ratio = 1;

/** Adds fn(ctx, view, state, time) as a layer. Orders: ring 10, outline 20, previews 30, creatures 40-50, cursors 60 */
export function addLayer(order, fn) {
  const at = layers.findIndex((layer) => layer.order > order);
  layers.splice(at < 0 ? layers.length : at, 0, { order, fn });
}

export function setupOverlay(node) {
  canvas = node;
  ctx = node.getContext("2d");
}

export function resizeOverlay(width, height, pixelRatio) {
  ratio = pixelRatio;
  canvas.width = Math.max(1, Math.round(width * pixelRatio));
  canvas.height = Math.max(1, Math.round(height * pixelRatio));
}

/** Clears and redraws every layer. Layers draw in CSS pixels; the device pixel ratio is already applied */
export function drawOverlay(view, state, time) {
  if (ctx === null) {
    return;
  }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const layer of layers) {
    ctx.save();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    try {
      layer.fn(ctx, view, state, time);
    } catch (e) {
      // Once per layer: a broken layer would otherwise fill the console 60 times a second
      if (!layer.warned) {
        layer.warned = true;
        console.warn("Sandfall: an overlay layer failed", e);
      }
    }
    ctx.restore();
  }
}

// The Line or Box being dragged, as a faint copy of what it will paint with a dashed edge: a line is as wide as the
// brush, a box is the rectangle between its corners. A mirrored stroke shows its copy across the middle too.
function drawDrag(ctx, view, state) {
  const painter = state.painter;
  const drag = painter.drag;
  if (!drag) {
    return;
  }
  const [r, g, b] = ELEMENTS[painter.element].color;
  const fill = `rgba(${r}, ${g}, ${b}, 0.45)`;
  const copies = painter.mirror ? [false, true] : [false];
  for (const flipped of copies) {
    const at = (cell) => view.toScreen(flipped ? W - 1 - cell[0] : cell[0], cell[1]);
    const [x0, y0] = at(drag.start);
    const [x1, y1] = at(drag.end);
    const half = view.scale / 2;
    ctx.beginPath();
    if (drag.tool === "box") {
      ctx.rect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0) + view.scale, Math.abs(y1 - y0) + view.scale);
      ctx.fillStyle = fill;
      ctx.fill();
    } else {
      ctx.moveTo(x0 + half, y0 + half);
      ctx.lineTo(x1 + half, y1 + half);
      ctx.lineCap = painter.shape === SHAPE.SQUARE ? "butt" : "round";
      ctx.lineWidth = Math.max(view.scale, painter.size * view.scale);
      ctx.strokeStyle = fill;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x0 + half, y0 + half);
      ctx.lineTo(x1 + half, y1 + half);
    }
    ctx.lineCap = "butt";
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.45)";
    ctx.stroke();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
    ctx.stroke();
  }
}

/** Adds the drag outline layer (order 20) */
export function addOutlineLayer() {
  addLayer(20, drawDrag);
}

const TAG_FONT = '800 13px Nunito, "Segoe UI", sans-serif';
const TAG_PAD_X = 8;
const TAG_HEIGHT = 24;
const TAG_EDGE = 4;

// The element and temperature under the pointer as a small tag, like `Lava · 1,140°`: beside a mouse, above a finger
// so the hand doesn't hide it. It stays away while a stroke, a pan or a pinch is going on, and while a finger is
// still deciding whether it is painting.
function drawCellInfo(ctx, view, state) {
  const painter = state.painter;
  const cell = painter.pointer;
  if (cell === null || painter.paint !== null || painter.waiting !== null || painter.gesture !== null) {
    return;
  }
  if (painter.panning !== null) {
    return;
  }
  const world = state.world;
  const i = cell[1] * W + cell[0];
  const text = `${ELEMENTS[world.el[i]]?.name ?? "?"} · ${world.heat[i].toLocaleString()}°`;
  ctx.font = TAG_FONT;
  const width = Math.ceil(ctx.measureText(text).width) + 2 * TAG_PAD_X;
  const [px, py] = view.toScreen(cell[0] + 0.5, cell[1] + 0.5);
  const room = ctx.canvas.clientWidth;
  const left = painter.touch ? px - width / 2 : px + 16;
  const x = Math.max(TAG_EDGE, Math.min(left, room - width - TAG_EDGE));
  const above = py - (painter.touch ? 56 : TAG_HEIGHT + 12);
  const y = painter.touch || py + 16 + TAG_HEIGHT > ctx.canvas.clientHeight ? Math.max(TAG_EDGE, above) : py + 16;
  ctx.beginPath();
  ctx.roundRect(x, y, width, TAG_HEIGHT, 8);
  ctx.fillStyle = "rgba(18, 20, 40, 0.88)";
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.22)";
  ctx.stroke();
  ctx.fillStyle = "#eef0ff";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + TAG_PAD_X, y + TAG_HEIGHT / 2 + 0.5);
}

/** Adds the cell info tag layer (order 70, above everything else on the canvas) */
export function addCellInfoLayer() {
  addLayer(70, drawCellInfo);
}
