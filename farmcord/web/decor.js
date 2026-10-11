// Decorations, in the Yard and the extra farmhouse rooms. Each placed one stands where the bot keeps it: shares (0 to
// 1) of the room's width and height. The Decorate button opens a tray of the ones not placed yet. While it is open, a
// decoration dragged from the tray onto the room's floor (room.floor in rooms.js) is placed there, a placed one dragged
// across the floor moves, and one dropped anywhere off the floor (the tray included) is put away, so every place sent
// is on the ground. Mouse and touch both drag, through pointer events.
import { ROOM } from "./rooms.js";
import { Graphics } from "./vendor/pixi.min.mjs";

const TRAY_PICTURE = 44;
// A dragged decoration is see-through while it is off the floor, where letting go puts it away
const OFF_ALPHA = 0.45;
const FLOOR_TINT = 0xfff3c4;

const decor = {
  ctx: null,
  // The room on screen, while it holds decorations
  room: null,
  // The placed decorations as drawn: [{ row, node }]
  placed: [],
  // Whether the tray is open
  on: false,
  // The drag in progress: { pointer, id, node, fresh (from the tray, so its node is only a picture of it) }
  drag: null,
  // The floor shown while dragging
  mark: null,
  listening: false,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- The room ----------

// The scene was emptied, so nothing drawn before is left to take down. Drawing the same room again (a new season or
// weather) comes without leave(): the tray stays as it was, and a drag ends, its picture gone with the old scene
export function enter(ctx, room) {
  const again = decor.room === room;
  endDrag();
  Object.assign(decor, { ctx, room, placed: [], on: again && decor.on });
  listen();
  const button = $("decorate");
  button.replaceChildren(ctx.hud.icon("decor/flower_pot", 32, true), ctx.hud.make("span", "", "Decorate"));
  button.onclick = ctx.safe("the Decorate button", () => decorate(ctx, true));
  $("decor-tray").hidden = !decor.on;
  update(ctx);
}

// A drag in progress keeps its picture until it is dropped; the drop draws the room again
export function update(ctx) {
  if (decor.drag) {
    return;
  }
  drawPlaced(ctx);
  $("house-buttons").hidden = decor.on;
  if (decor.on) {
    fillTray(ctx);
  }
}

export function leave() {
  endDrag();
  decor.room = null;
  decor.on = false;
  $("house-buttons").hidden = true;
  $("decor-tray").hidden = true;
}

// Where shares of the room are in it, and back
function spotOf(x, y) {
  return { x: x * ROOM.width, y: y * ROOM.height };
}

function sharesOf(point) {
  return { x: point.x / ROOM.width, y: point.y / ROOM.height };
}

function drawPlaced(ctx) {
  for (const { node } of decor.placed) {
    node.destroy();
  }
  decor.placed = ctx
    .state()
    .decorations.filter((row) => row.room === decor.room.id)
    .map((row) => {
      const at = spotOf(row.x, row.y);
      const node = ctx.scene.sprite(`decor/${row.item}`, at.x, at.y);
      node.label = `decor:${row.id}`;
      ctx.scene.things.addChild(node);
      return { row, node };
    });
}

// ---------- The tray ----------

function decorate(ctx, on) {
  ctx.sound.play("tap");
  decor.on = on;
  $("house-buttons").hidden = on;
  $("decor-tray").hidden = !on;
  if (on) {
    fillTray(ctx);
  }
}

// The decorations not placed yet, by kind in the catalog's order: [{ item, ids }]
function unplaced(ctx) {
  const rows = ctx.state().decorations.filter((row) => row.room === null);
  return ctx
    .catalog()
    .cosmetics.filter((item) => item.kind === "decoration")
    .map((item) => ({ item, ids: rows.filter((row) => row.item === item.key).map((row) => row.id) }))
    .filter((group) => group.ids.length);
}

function fillTray(ctx) {
  const { make } = ctx.hud;
  const top = make("header", "decor-top");
  const done = make("button", "button primary", "Done");
  done.type = "button";
  done.id = "decor-done";
  done.addEventListener("click", ctx.safe("the Done button", () => decorate(ctx, false)));
  const how = "Drag a decoration onto the floor to place it. Drag one off the floor to put it away.";
  top.append(make("p", "", how), done);
  const items = make("ul", "decor-items");
  const groups = unplaced(ctx);
  for (const group of groups) {
    const item = make("li");
    item.append(trayItem(ctx, group));
    items.append(item);
  }
  if (!groups.length) {
    const none = ctx.state().decorations.length ? "Every decoration you own is placed." : "You have no decorations.";
    items.append(make("li", "dim", `${none} Buy them at the Market's shop.`));
  }
  $("decor-tray").replaceChildren(top, items);
}

function trayItem(ctx, { item, ids }) {
  const { make } = ctx.hud;
  const button = make("button", "decor-item");
  button.type = "button";
  button.dataset.item = item.key;
  button.append(ctx.hud.icon(`decor/${item.key}`, TRAY_PICTURE, true), make("span", "", item.name));
  if (ids.length > 1) {
    button.append(make("span", "count", `×${ids.length}`));
  }
  const pick = (event) => pickFromTray(ctx, event, item, ids);
  button.addEventListener("pointerdown", ctx.safe("dragging a decoration", pick));
  return button;
}

// A press on a decoration in the tray picks up one of that kind not already on its way to the bot
function pickFromTray(ctx, event, item, ids) {
  const id = ids.find((one) => !ctx.busy(`decor:${one}`));
  if (!id || decor.drag) {
    return;
  }
  event.preventDefault();
  event.currentTarget.setPointerCapture(event.pointerId);
  const node = ctx.scene.sprite(`decor/${item.key}`, 0, 0);
  node.visible = false;
  ctx.scene.things.addChild(node);
  startDrag(ctx, { pointer: event.pointerId, id, node, fresh: true });
}

// ---------- Dragging ----------

// The page listens once. A press on a placed decoration is taken on its way down to the room's canvas, before the
// scene sees it, so the drag moves the decoration instead of panning the room or walking the farmer
function listen() {
  if (decor.listening) {
    return;
  }
  decor.listening = true;
  const handle = (where, fn) => (event) => decor.ctx.safe(where, fn)(event);
  $("stage").addEventListener("pointerdown", handle("grabbing a decoration", grab), { capture: true });
  window.addEventListener("pointermove", handle("dragging a decoration", move));
  window.addEventListener("pointerup", handle("dropping a decoration", drop));
  window.addEventListener("pointercancel", handle("a dragged decoration", cancel));
}

function grab(event) {
  if (!decor.on || decor.drag || !decor.room) {
    return;
  }
  const screen = canvasPoint(event);
  const hits = decor.placed.filter(({ node }) => node.getBounds().rectangle.contains(screen.x, screen.y));
  hits.sort((a, b) => b.node.zIndex - a.node.zIndex);
  const hit = hits[0];
  if (!hit || decor.ctx.busy(`decor:${hit.row.id}`)) {
    return;
  }
  event.stopPropagation();
  event.preventDefault();
  $("stage").setPointerCapture(event.pointerId);
  startDrag(decor.ctx, { pointer: event.pointerId, id: hit.row.id, node: hit.node, fresh: false });
}

function startDrag(ctx, drag) {
  decor.drag = drag;
  const { left, right, top, bottom } = decor.room.floor;
  decor.mark = new Graphics()
    .roundRect(left, top, right - left, bottom - top, 18)
    .fill({ color: FLOOR_TINT, alpha: 0.16 })
    .stroke({ width: 4, color: FLOOR_TINT, alpha: 0.7 });
  ctx.scene.floor.addChild(decor.mark);
  $("decor-tray").classList.add("dragging");
}

function canvasPoint(event) {
  const box = decor.ctx.scene.app.canvas.getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top };
}

function roomPoint(event) {
  return decor.ctx.scene.world.toLocal(canvasPoint(event));
}

// On the room's floor, and not on anything over the room, like the tray
function onFloor(event) {
  const { left, right, top, bottom } = decor.room.floor;
  const point = roomPoint(event);
  const under = document.elementFromPoint(event.clientX, event.clientY);
  const inside = point.x >= left && point.x <= right && point.y >= top && point.y <= bottom;
  return inside && under === decor.ctx.scene.app.canvas;
}

function move(event) {
  const drag = decor.drag;
  if (!drag || drag.pointer !== event.pointerId) {
    return;
  }
  const point = roomPoint(event);
  drag.node.position.set(point.x, point.y);
  drag.node.zIndex = point.y;
  drag.node.alpha = onFloor(event) ? 1 : OFF_ALPHA;
  drag.node.visible = true;
}

async function drop(event) {
  const drag = decor.drag;
  if (!drag || drag.pointer !== event.pointerId) {
    return;
  }
  const { ctx, room } = decor;
  const place = onFloor(event) && sharesOf(roomPoint(event));
  endDrag();
  const key = `decor:${drag.id}`;
  let reply = null;
  if (place) {
    drag.node.alpha = 1;
    reply = await ctx.act("place", { decoration: drag.id, room: room.id, ...place }, { key });
  } else if (!drag.fresh) {
    drag.node.visible = false;
    reply = await ctx.act("pick_up", { decoration: drag.id }, { key });
  }
  if (drag.fresh && !drag.node.destroyed) {
    drag.node.destroy();
  }
  // Turned down: a moved decoration goes back where the bot keeps it
  if (!reply && !drag.fresh && decor.room === room) {
    drawPlaced(ctx);
  }
}

function cancel(event) {
  const drag = decor.drag;
  if (!drag || drag.pointer !== event.pointerId) {
    return;
  }
  endDrag();
  if (drag.fresh && !drag.node.destroyed) {
    drag.node.destroy();
  } else if (!drag.fresh && decor.room) {
    drawPlaced(decor.ctx);
  }
}

function endDrag() {
  decor.drag = null;
  if (decor.mark && !decor.mark.destroyed) {
    decor.mark.destroy();
  }
  decor.mark = null;
  $("decor-tray").classList.remove("dragging");
}
