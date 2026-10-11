// The farmhouse. Its main room has the farm board on the wall (board.js) and a wardrobe, where the farmer changes
// clothes with a preview first, and the babies waiting for a pen stand on its floor. The extra rooms bought at the
// board hold decorations and a description the player writes; the Yard holds decorations too (decor.js).
import { openBoard, updateBoard } from "./board.js";
import * as decor from "./decor.js";
import { nameSign } from "./market.js";
import { Container, Graphics, Sprite } from "./vendor/pixi.min.mjs";

// The board hangs on the wall, its bottom edge at y; the wardrobe stands on the floor. Where the farmer stands to use
// each, its name and how high the name sits (plates on the furniture), and the label a test finds it by. Both stay
// below where an upright phone puts the side exits
const BOARD = {
  x: 640,
  y: 402,
  width: 400,
  height: 220,
  stand: { x: 640, y: 510 },
  name: "Farm board",
  nameY: 426,
  label: "board",
};
const WARDROBE = {
  x: 990,
  y: 478,
  width: 170,
  height: 300,
  stand: { x: 970, y: 525 },
  name: "Wardrobe",
  nameY: 196,
  label: "wardrobe",
};
// What is pinned to the board's cork, from its bottom middle: paper notes and pictures
const PINNED = [
  { note: 0xfff3b0, x: -120, y: -153, turn: -0.06 },
  { art: "badge/first_crop", x: 0, y: -156, size: 72, turn: 0.04 },
  { note: 0xdcefff, x: 120, y: -150, turn: 0.05 },
  { art: "icon/seed:wildflowers", x: -120, y: -67, size: 66, turn: 0.07 },
  { note: 0xfffaf0, x: 0, y: -65, turn: -0.03 },
  { art: "icon/coin", x: 120, y: -69, size: 60, turn: 0 },
];
const NOTE = { width: 92, height: 68 };
// Where babies waiting for a pen stand, on the floor left of the middle
const BABY_PLACES = [
  { x: 470, y: 605 },
  { x: 390, y: 660 },
  { x: 550, y: 668 },
];
const SLOTS = [
  { key: "hat", name: "Hat", plain: "No hat" },
  { key: "top", name: "Top", plain: "Plain shirt" },
  { key: "bottom", name: "Bottom", plain: "Plain trousers" },
];
const PREVIEW_HEIGHT = 200;
const CHOICE_PICTURE = 40;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const house = {
  // The waiting babies as drawn: [{ look, node, remove }]
  babies: [],
  time: 0,
};
// The wardrobe while it is open: the outfit picked to try, slot by slot
const wardrobe = { root: null, picked: null };
// The description box of the extra room on screen (0 for none): its number and the words the bot keeps
const note = { room: 0, saved: "" };

function $(id) {
  return document.getElementById(id);
}

// ---------- The main room ----------

function enter(ctx) {
  house.babies = [];
  const board = boardPiece(ctx);
  standPiece(ctx, board, BOARD, () => openBoard(ctx));
  standPiece(ctx, wardrobePiece(), WARDROBE, () => openWardrobe(ctx));
  ctx.scene.everyFrame((dt) => stepBabies(ctx, dt));
  update(ctx);
}

function update(ctx) {
  drawBabies(ctx);
  updateBoard(ctx);
  if (wardrobeOpen()) {
    drawWardrobe(ctx);
  }
}

export const houseView = { enter, update };

// A piece of furniture in the room with its name on it, both tapped to use it
function standPiece(ctx, piece, spot, open) {
  piece.position.set(spot.x, spot.y);
  piece.zIndex = spot.y;
  piece.label = spot.label;
  const sign = nameSign(spot.name, spot.x, spot.nameY, spot.y);
  sign.label = `${spot.label}:name`;
  ctx.scene.things.addChild(piece, sign);
  const onTap = ctx.safe(`tapping the ${spot.name}`, open);
  ctx.scene.addTarget(piece, { walkTo: spot.stand, onTap });
  ctx.scene.addTarget(sign, { walkTo: spot.stand, onTap });
}

// A cork board in a wooden frame, with notes and pictures pinned to it, drawn from its bottom middle
function boardPiece(ctx) {
  const { width: w, height: h } = BOARD;
  const piece = new Container();
  const frame = new Graphics()
    .roundRect(-w / 2, -h, w, h, 14)
    .fill(0x9a6233)
    .stroke({ width: 4, color: 0x4a2a12 })
    .roundRect(-w / 2 + 16, -h + 16, w - 32, h - 32, 6)
    .fill(0xd2a76b)
    .stroke({ width: 3, color: 0x7a4a22 });
  piece.addChild(frame);
  for (const pin of PINNED) {
    const thing = pin.note ? paperNote(pin.note) : pinnedPicture(ctx, pin);
    thing.position.set(pin.x, pin.y);
    thing.rotation = pin.turn;
    piece.addChild(thing);
  }
  return piece;
}

function paperNote(color) {
  const { width: w, height: h } = NOTE;
  const paper = new Graphics().rect(-w / 2, -h / 2, w, h).fill(color).stroke({ width: 2, color: 0xb59a6a });
  for (let i = 0; i < 3; i += 1) {
    const y = -h / 2 + 22 + i * 14;
    paper.moveTo(-w / 2 + 12, y).lineTo(w / 2 - (i === 2 ? 34 : 12), y);
  }
  paper.stroke({ width: 3, color: 0x9fb6c9, cap: "round" });
  return paper.circle(0, -h / 2 + 6, 6).fill(0xd8432f).stroke({ width: 2, color: 0x7a1d12 });
}

function pinnedPicture(ctx, pin) {
  const picture = new Sprite(ctx.scene.art.texture(pin.art));
  picture.scale.set(pin.size / Math.max(picture.width, picture.height));
  return picture;
}

// A wooden wardrobe with two doors, drawn from its bottom middle
function wardrobePiece() {
  const { width: w, height: h } = WARDROBE;
  const line = { width: 4, color: 0x4a2a12 };
  const piece = new Graphics()
    .rect(-w / 2 + 10, -16, 18, 16)
    .rect(w / 2 - 28, -16, 18, 16)
    .fill(0x5a3418)
    .roundRect(-w / 2, -h, w, h - 12, 6)
    .fill(0xa86a34)
    .stroke(line)
    .roundRect(-w / 2 - 8, -h - 12, w + 16, 22, 6)
    .fill(0x8a5226)
    .stroke(line);
  const door = { top: -h + 22, height: h - 56, width: w / 2 - 18 };
  for (const left of [-w / 2 + 12, 6]) {
    piece.roundRect(left, door.top, door.width, door.height, 4).fill(0x95592a).stroke({ width: 3, color: 0x5a3418 });
    piece.roundRect(left + 10, door.top + 12, door.width - 20, door.height * 0.42, 4);
    piece.roundRect(left + 10, door.top + door.height * 0.5, door.width - 20, door.height * 0.42, 4);
    piece.fill(0xb27640).stroke({ width: 2, color: 0x7a4a22 });
  }
  return piece.circle(-10, -h / 2, 6).circle(10, -h / 2, 6).fill(0xf2c14e).stroke({ width: 2, color: 0x7a5410 });
}

// ---------- Waiting babies ----------

// Each baby waiting for a pen stands on the floor. A tap opens the board's animals, where it moves into a pen
function drawBabies(ctx) {
  for (const { node, remove } of house.babies) {
    remove();
    node.destroy();
  }
  house.babies = ctx
    .state()
    .waiting.slice(0, BABY_PLACES.length)
    .map((baby, i) => {
      const look = `animal/${baby.kind}/baby`;
      const node = ctx.scene.sprite(`${look}/${ctx.scene.art.animation(look).clips.idle_front.start}`, 0, 0);
      node.position.set(BABY_PLACES[i].x, BABY_PLACES[i].y);
      node.zIndex = node.y;
      node.label = `baby:${baby.id}`;
      ctx.scene.things.addChild(node);
      const onTap = ctx.safe("tapping a waiting baby", () => openBoard(ctx, "animals"));
      return { look, node, remove: ctx.scene.addTarget(node, { onTap }) };
    });
}

// Their front idle plays, unless the player asked for less motion
function stepBabies(ctx, dt) {
  house.time += dt;
  if (reducedMotion.matches) {
    return;
  }
  for (const { look, node } of house.babies) {
    const clip = ctx.scene.art.animation(look).clips.idle_front;
    const frame = clip.start + (Math.floor(house.time * clip.fps) % clip.count);
    node.texture = ctx.scene.art.texture(`${look}/${frame}`);
  }
}

// ---------- The wardrobe ----------

function openWardrobe(ctx) {
  ctx.sound.play("tap");
  const body = ctx.hud.openPanel("Wardrobe");
  wardrobe.root = ctx.hud.make("div", "wardrobe");
  wardrobe.picked = { ...ctx.state().outfit };
  body.append(wardrobe.root);
  drawWardrobe(ctx);
}

function wardrobeOpen() {
  return Boolean(wardrobe.root?.isConnected) && $("panel").open;
}

function wearing(ctx) {
  return SLOTS.every((slot) => wardrobe.picked[slot.key] === ctx.state().outfit[slot.key]);
}

// The farmer in the outfit picked, then each slot's choices: the plain look and every piece owned for it
function drawWardrobe(ctx) {
  const { make } = ctx.hud;
  const state = ctx.state();
  const preview = make("div", "wardrobe-preview");
  preview.append(farmerPicture(ctx, wardrobe.picked));
  const slots = make("div", "wardrobe-slots");
  for (const slot of SLOTS) {
    const owned = ctx.catalog().cosmetics.filter((item) => item.kind === slot.key && state.outfits.includes(item.key));
    const choices = make("div", "outfit-row");
    choices.append(outfitChoice(ctx, slot, null, slot.plain));
    choices.append(...owned.map((item) => outfitChoice(ctx, slot, item.key, item.name)));
    const section = make("section", "wardrobe-slot");
    section.append(make("h3", "", slot.name), choices);
    slots.append(section);
  }
  if (!state.outfits.length) {
    slots.append(make("p", "dim", "Clothes bought at the Market's shop hang here."));
  }
  const wear = make("button", "button primary", wearing(ctx) ? "You're wearing this" : "Wear this");
  wear.type = "button";
  wear.id = "wear";
  wear.disabled = wearing(ctx);
  wear.addEventListener("click", ctx.safe("the Wear button", () => wearPicked(ctx, wear)));
  const foot = make("div", "wardrobe-foot");
  foot.append(wear);
  slots.append(foot);
  wardrobe.root.replaceChildren(preview, slots);
}

function outfitChoice(ctx, slot, key, name) {
  const { make } = ctx.hud;
  const button = make("button", "outfit-choice");
  button.type = "button";
  button.dataset.slot = slot.key;
  button.dataset.key = key || "";
  button.setAttribute("aria-pressed", String(wardrobe.picked[slot.key] === key));
  const stand = ctx.scene.art.animation("farmer/base").clips.stand_front.start;
  const picture = key ? ctx.hud.icon(`farmer/${slot.key}/${key}/${stand}`, CHOICE_PICTURE, true) : make("span", "none");
  button.append(picture, make("span", "", name));
  const pick = () => {
    ctx.sound.play("tap");
    wardrobe.picked[slot.key] = key;
    drawWardrobe(ctx);
  };
  button.addEventListener("click", ctx.safe("an outfit choice", pick));
  return button;
}

// Each slot that changed, one after another. A refusal stops the rest
async function wearPicked(ctx, button) {
  button.disabled = true;
  for (const slot of SLOTS) {
    const outfit = wardrobe.picked[slot.key];
    if (outfit !== ctx.state().outfit[slot.key] && !(await ctx.act("wear", { slot: slot.key, outfit }))) {
      break;
    }
  }
  if (wardrobeOpen()) {
    drawWardrobe(ctx);
  }
}

// The farmer standing in an outfit, in HTML: the plain farmer and each piece cut from its sheet and laid where it sits
// on the canvas the layers share, in the scene's drawing order. The box is the part of that canvas any piece covers, so
// the farmer stands still while pieces change
function farmerPicture(ctx, outfit) {
  const { art } = ctx.scene;
  const stand = art.animation("farmer/base").clips.stand_front.start;
  const pieces = ctx.catalog().cosmetics.filter((item) => item.kind !== "decoration");
  const every = [`farmer/base/${stand}`, ...pieces.map((item) => `farmer/${item.kind}/${item.key}/${stand}`)];
  const boxes = every.map((key) => art.frame(key).spriteSourceSize);
  const area = { x: Math.min(...boxes.map((b) => b.x)), y: Math.min(...boxes.map((b) => b.y)) };
  area.w = Math.max(...boxes.map((b) => b.x + b.w)) - area.x;
  area.h = Math.max(...boxes.map((b) => b.y + b.h)) - area.y;
  const k = PREVIEW_HEIGHT / area.h;
  const picture = ctx.hud.make("span", "art-icon farmer-picture");
  Object.assign(picture.style, { width: `${area.w * k}px`, height: `${area.h * k}px` });
  for (const layer of art.data.farmer.layers) {
    const piece = layer === "base" ? "base" : outfit[layer] && `${layer}/${outfit[layer]}`;
    if (piece) {
      const key = `farmer/${piece}/${stand}`;
      picture.append(layerPicture(ctx, art.frame(key), area, k, layer));
    }
  }
  return picture;
}

function layerPicture(ctx, info, area, k, layer) {
  const piece = ctx.hud.make("span");
  piece.dataset.layer = layer;
  Object.assign(piece.style, {
    left: `${(info.spriteSourceSize.x - area.x) * k}px`,
    top: `${(info.spriteSourceSize.y - area.y) * k}px`,
    width: `${info.frame.w * k}px`,
    height: `${info.frame.h * k}px`,
    backgroundImage: `url("${info.url}")`,
    backgroundSize: `${info.size.w * k}px ${info.size.h * k}px`,
    backgroundPosition: `${-info.frame.x * k}px ${-info.frame.y * k}px`,
  });
  return piece;
}

// ---------- The extra rooms and the Yard ----------

// Drawing the same room again (a new season or weather) comes without leave(), and keeps the box the player may be
// typing in
function enterExtraRoom(ctx, room) {
  decor.enter(ctx, room);
  if (note.room === room.number) {
    refreshNote(ctx);
  } else {
    showNote(ctx, room);
  }
}

function updateExtraRoom(ctx) {
  decor.update(ctx);
  refreshNote(ctx);
}

function leaveExtraRoom() {
  decor.leave();
  note.room = 0;
  $("room-note").hidden = true;
}

export const extraRoomView = { enter: enterExtraRoom, update: updateExtraRoom, leave: leaveExtraRoom };
export const yardView = { enter: decor.enter, update: decor.update, leave: decor.leave };

// The room's description box: the words the bot keeps, at most the catalog's limit, saved with a button
function showNote(ctx, room) {
  const { make } = ctx.hud;
  const limit = ctx.catalog().constants.description_limit;
  const label = make("label", "room-note-label", "About this room");
  label.htmlFor = "room-note-text";
  const text = make("textarea");
  Object.assign(text, { id: "room-note-text", rows: 3, maxLength: limit, placeholder: "Write what this room is for" });
  const count = make("span", "dim");
  count.id = "room-note-count";
  const save = make("button", "button primary", "Save");
  save.type = "button";
  save.id = "room-note-save";
  const foot = make("div", "room-note-foot");
  foot.append(count, save);
  $("room-note").replaceChildren(label, text, foot);
  note.room = room.number;
  note.saved = ctx.state().descriptions[String(room.number)] || "";
  text.value = note.saved;
  text.addEventListener("input", ctx.safe("the room's description", () => showCount(limit)));
  save.addEventListener("click", ctx.safe("saving the room's description", () => saveNote(ctx, save, limit)));
  showCount(limit);
  $("room-note").hidden = false;
}

// The box keeps what the player is typing; the bot's words only replace words not being changed
function refreshNote(ctx) {
  const saved = ctx.state().descriptions[String(note.room)] || "";
  const text = $("room-note-text");
  if (saved !== note.saved && text.value === note.saved) {
    text.value = saved;
  }
  note.saved = saved;
  showCount(ctx.catalog().constants.description_limit);
}

function showCount(limit) {
  const text = $("room-note-text");
  $("room-note-count").textContent = `${text.value.length}/${limit}`;
  $("room-note-save").disabled = text.value.trim() === note.saved;
}

async function saveNote(ctx, button, limit) {
  const reply = await ctx.actButton(button, "describe", { room: note.room, text: $("room-note-text").value });
  if (reply) {
    note.saved = reply.result.text;
    $("room-note-text").value = reply.result.text;
    ctx.hud.toast("Saved");
  }
  showCount(limit);
}
