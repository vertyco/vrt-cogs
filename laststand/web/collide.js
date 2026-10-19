// Hit boxes. The original's hitTest calls (F4:5926-6838) are all box tests: the box a named collision clip inside an
// animated rig covers on the world, as Flash's getBounds gives it. The collision clips are drawn see-through (alpha 0)
// and some are switched off with _visible, but Flash still measures and tests them, so a box here is worked out from
// the timeline's matrices and the shapes' own bounds in the art, never from Pixi's bounds, which skip hidden parts.
//
// Paths read from a rig's root as the original's do: "collisionHead", "arms.collision" (the shove),
// "arms.weapon.collision" (a melee swing), "attackCollision" (a zombie's blow). Whether a box counts on this frame is
// the rule's call: a swing's box only while shown (F4:6607), a zombie's blow box whenever its timeline has placed it
// (F4:6576).
import { Graphics } from "./vendor/pixi.min.mjs";
import { partAt } from "./rig.js";
import { layers } from "./rooms.js";

// The boxes the outline view draws on each actor, and their colours
const BOX_PATHS = {
  collisionHead: 0xff3030,
  collisionChest: 0xff9a00,
  collisionBelly: 0xffe000,
  collisionLegs: 0x30ff60,
  collisionShield: 0x30e0ff,
  attackCollision: 0xff30ff,
  "arms.collision": 0x4080ff,
  "arms.weapon.collision": 0xffffff,
};
const OUTLINE_WIDTH = 1.5;

let page = null;
// Shape id -> [left, top, right, bottom] in the shape's own pixels
const shapeBounds = new Map();
let outlines = null;
let outlinesOn = false;

// ---------- Boxes ----------

// The pixels a shape covers: its art pieces put together, or the size the art gives a shape that draws nothing
function boundsOfShape(id) {
  if (shapeBounds.has(id)) {
    return shapeBounds.get(id);
  }
  const atlas = page.lib.data.atlas;
  let found = atlas.blank[id] ?? null;
  for (const [, , , w, h, left, top] of atlas.shapes[id] ?? []) {
    const piece = [left / atlas.scale, top / atlas.scale, (left + w) / atlas.scale, (top + h) / atlas.scale];
    found = found ? join(found, piece) : piece;
  }
  shapeBounds.set(id, found);
  return found;
}

function join(a, b) {
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
}

// A node's own matrix [a, b, c, d, tx, ty], from where the timeline or a script last put it
function matrixOf(node) {
  node.updateLocalTransform();
  const m = node.localTransform;
  return [m.a, m.b, m.c, m.d, m.tx, m.ty];
}

// The box a matrix carries a [left, top, right, bottom] box to
function carry(m, [left, top, right, bottom]) {
  const xs = [];
  const ys = [];
  for (const [x, y] of [
    [left, top],
    [right, top],
    [left, bottom],
    [right, bottom],
  ]) {
    xs.push(m[0] * x + m[2] * y + m[4]);
    ys.push(m[1] * x + m[3] * y + m[5]);
  }
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// What a node covers in its own pixels, hidden parts included, as Flash measures it. Null when it covers nothing
function ownBounds(node) {
  const atlas = page.lib.data.atlas;
  if (!node.def && !node.records && (atlas.shapes[node.charId] || atlas.blank[node.charId])) {
    return boundsOfShape(node.charId);
  }
  if (node.box) {
    return [node.box.x, node.box.y, node.box.x + node.box.width, node.box.y + node.box.height];
  }
  if (!node.children?.length) {
    const own = node.texture ? node.getLocalBounds() : null;
    return own && own.width > 0 ? [own.minX, own.minY, own.maxX, own.maxY] : null;
  }
  let found = null;
  for (const child of node.children) {
    const inner = ownBounds(child);
    if (inner) {
      const carried = carry(matrixOf(child), inner);
      found = found ? join(found, carried) : carried;
    }
  }
  return found;
}

// The matrix from a node's own pixels to the world's (the room's layers sit at the world's origin)
function toWorldMatrix(node) {
  const top = layers.bg?.parent ?? null;
  let m = [1, 0, 0, 1, 0, 0];
  for (let up = node; up && up !== top && up !== page.root; up = up.parent) {
    const p = matrixOf(up);
    m = [
      p[0] * m[0] + p[2] * m[1],
      p[1] * m[0] + p[3] * m[1],
      p[0] * m[2] + p[2] * m[3],
      p[1] * m[2] + p[3] * m[3],
      p[0] * m[4] + p[2] * m[5] + p[4],
      p[1] * m[4] + p[3] * m[5] + p[5],
    ];
  }
  return m;
}

// The matrix [a, b, c, d, tx, ty] from a node's own pixels to the world's, as the timelines have placed it now
export function worldMatrix(node) {
  return toWorldMatrix(node);
}

// Where a node's own origin stands on the world (a marker point inside an animated rig)
export function originOf(node) {
  const m = toWorldMatrix(node);
  return { x: m[4], y: m[5] };
}

// The box { x, y, w, h } in world pixels of the part at path inside clip (the clip itself without a path), whether it
// shows or not. Null when the timeline has no such part on this frame, or it covers nothing
export function boxOf(clip, path = null) {
  const node = path ? partAt(clip, path) : clip;
  if (!node || node.destroyed) {
    return null;
  }
  const own = ownBounds(node);
  if (!own) {
    return null;
  }
  const [left, top, right, bottom] = carry(toWorldMatrix(node), own);
  return { x: left, y: top, w: right - left, h: bottom - top };
}

// Flash's _visible on the part itself: whether a swing's box is switched on this frame. False when it isn't there
export function shown(clip, path) {
  const node = partAt(clip, path);
  return Boolean(node && !node.destroyed && node.visible);
}

// Two boxes overlap (Flash's hitTest between two clips). Either missing is no hit
export function overlap(a, b) {
  if (!a || !b) {
    return false;
  }
  return a.x <= b.x + b.w && b.x <= a.x + a.w && a.y <= b.y + b.h && b.y <= a.y + a.h;
}

export const hits = overlap;

// A world point inside a box (Flash's hitTest(x, y) without the shape flag, F4:6838)
export function inside(box, x, y) {
  return Boolean(box) && x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h;
}

// ---------- The outline view ----------

// Outlines every box that counts on each actor in the room: body boxes always, a swing's or blow's box while shown.
// Drawn at the screen's rate over everything in the world, paused or not. A room change empties the layers, so the
// drawing is made again when it has gone with them
function drawOutlines() {
  if (!layers.effects) {
    return;
  }
  if (!outlines || outlines.destroyed) {
    outlines = new Graphics();
    outlines.label = "hitBoxes";
    outlines.eventMode = "none";
  }
  if (outlines.parent !== layers.effects) {
    layers.effects.addChild(outlines);
  }
  outlines.clear();
  for (const actor of layers.actors?.children ?? []) {
    for (const [path, colour] of Object.entries(BOX_PATHS)) {
      const box = shown(actor, path) ? boxOf(actor, path) : null;
      if (box) {
        outlines.rect(box.x, box.y, box.w, box.h).stroke({ width: OUTLINE_WIDTH, color: colour });
      }
    }
  }
}

// Shows or hides the outline of every hit box, for checks. Returns whether they show
export function debugBoxes(on) {
  if (on && !outlinesOn) {
    page.app.ticker.add(drawOutlines);
  } else if (!on && outlinesOn) {
    page.app.ticker.remove(drawOutlines);
    if (outlines && !outlines.destroyed) {
      outlines.destroy();
    }
    outlines = null;
  }
  outlinesOn = Boolean(on);
  return outlinesOn;
}

export function initCollide(owner) {
  page = owner;
}

export const collide = { boxOf, shown, overlap, hits, inside, debugBoxes };
