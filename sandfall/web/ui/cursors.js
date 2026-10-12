// Other players' cursors in a shared world, drawn on the overlay above everything else: a ring the size of their brush
// in their color, a dot of the element they hold, and their name. A cursor that stops moving for a while fades to just
// its dimmed name. This file also sends this player's own cursor to the bot.
import { addLayer } from "../render/overlay.js";
import { ELEMENTS } from "../sim/index.js";

// Ten player colors, picked by the bot (0..9)
const COLORS = [
  "#ff6b6b",
  "#ffb454",
  "#ffe66d",
  "#7bed9f",
  "#4ecdc4",
  "#54a0ff",
  "#a29bfe",
  "#fd79a8",
  "#e17055",
  "#dfe6e9",
];
// A cursor still this long fades; the ring and dot are gone after another FADE_MS, leaving the dimmed name
const IDLE_MS = 5000;
const FADE_MS = 1000;
const DIMMED = 0.65;
// Names stay readable at any zoom: this is screen pixels, never scaled with the world
const FONT_PX = 11;
const LINE_PX = 14;
const NAME_MAX = 12;
const GAP = 4;
const SEGMENTER =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function characters(text) {
  return SEGMENTER ? Array.from(SEGMENTER.segment(text), (part) => part.segment) : Array.from(text);
}

/** A name cut by whole characters to `max` of them, with an ellipsis as the last one */
export function cut(name, max = NAME_MAX) {
  const letters = characters(name);
  return letters.length > max ? `${letters.slice(0, max - 1).join("")}…` : name;
}

function ringRadius(size, scale) {
  return Math.max(scale * 0.7, (size / 2) * scale);
}

// How strongly a cursor shows: 1 while it moves, fading to 0 for the ring and dot, with the name staying at DIMMED
function fade(age) {
  if (age <= IDLE_MS) {
    return { ring: 1, name: 1 };
  }
  const t = Math.min(1, (age - IDLE_MS) / FADE_MS);
  return { ring: 1 - t, name: 1 - (1 - DIMMED) * t };
}

function drawRing(ctx, cursor, color, alpha, x, y, radius) {
  if (alpha <= 0) {
    return;
  }
  ctx.globalAlpha = alpha;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0, 0, 0, 0.45)";
  ctx.stroke();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = color;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, Math.PI * 2);
  const element = ELEMENTS[cursor.element];
  if (cursor.element === 0 || !element) {
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#fff";
    ctx.stroke();
  } else {
    const [r, g, b] = element.color;
    ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.7)";
    ctx.stroke();
  }
}

// Where a name goes: right of the ring, or left when it would run off the screen, and clear of the names placed before
// it (nudged down). Rects are { x, y, w, h }
function placeLabel(labels, width, height, x, y, radius, textWidth) {
  const w = textWidth + 8;
  const h = LINE_PX + 2;
  let left = x + radius + GAP;
  if (left + w > width - GAP) {
    left = x - radius - GAP - w;
  }
  left = Math.max(GAP, Math.min(width - w - GAP, left));
  let top = y - h / 2;
  for (let tries = 0; tries < 20; tries++) {
    const hit = labels.find((o) => left < o.x + o.w && o.x < left + w && top < o.y + o.h && o.y < top + h);
    if (!hit) {
      break;
    }
    top = hit.y + hit.h + 1;
  }
  top = Math.max(GAP, Math.min(height - h - GAP, top));
  const rect = { x: left, y: top, w, h };
  labels.push(rect);
  return rect;
}

function drawLabel(ctx, name, color, alpha, rect) {
  ctx.globalAlpha = alpha;
  ctx.fillStyle = "rgba(10, 12, 28, 0.62)";
  ctx.beginPath();
  ctx.roundRect(rect.x, rect.y, rect.w, rect.h, 5);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.fillText(name, rect.x + 4, rect.y + rect.h / 2 + 0.5);
}

/** Draws the other members' cursors and keeps this player's own cursor going out to them */
export function buildCursors(state) {
  const { shared, painter } = state;
  let sentWorld = null;
  let sentKey = "";

  // Sent when the cell under the pointer, the brush size or the element changed; a held-back send is retried next frame
  function sendOwn() {
    if (shared.inWorld !== sentWorld) {
      sentWorld = shared.inWorld;
      sentKey = "";
    }
    const cell = painter.pointer;
    if (shared.inWorld === null || cell === null) {
      return;
    }
    const element = painter.tool === "eraser" ? 0 : painter.element;
    const key = `${cell[0]},${cell[1]},${painter.size},${element}`;
    if (key !== sentKey && shared.sendCursor(cell[0], cell[1])) {
      sentKey = key;
    }
  }

  addLayer(60, (ctx, view) => {
    sendOwn();
    if (shared.inWorld === null || shared.cursors.size === 0) {
      return;
    }
    const width = ctx.canvas.clientWidth;
    const height = ctx.canvas.clientHeight;
    const now = performance.now();
    const people = new Map(shared.players.map((p) => [p.id, p]));
    ctx.font = `800 ${FONT_PX}px Nunito, "Segoe UI", sans-serif`;
    ctx.textBaseline = "middle";
    const labels = [];
    // Fixed order (by id) so names that overlap are nudged the same way every frame
    const ids = [...shared.cursors.keys()].sort();
    for (const id of ids) {
      const person = people.get(id);
      if (!person || id === shared.you) {
        continue;
      }
      const cursor = shared.cursors.get(id);
      const color = COLORS[person.color % COLORS.length];
      const [x, y] = view.toScreen(cursor.x + 0.5, cursor.y + 0.5);
      const radius = ringRadius(cursor.size, view.scale);
      const alpha = fade(now - cursor.at);
      drawRing(ctx, cursor, color, alpha.ring, x, y, radius);
      const name = cut(person.name);
      const rect = placeLabel(labels, width, height, x, y, radius, ctx.measureText(name).width);
      drawLabel(ctx, name, color, alpha.name, rect);
    }
  });
}
