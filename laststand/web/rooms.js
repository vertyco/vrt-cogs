// Rooms: building one from its art and its data, the fade between two rooms, and the camera that follows the player
// through it. The world draws inside one container (the original's `_root.world`) that the camera moves; its layers
// hold the room's art and everything the other systems add to the room, and are emptied on every room change, so a
// system that keeps something across rooms (the player) builds it again in its `build` listener.
//
// Systems hang on a room change with onRoom(stage, fn): "leave" runs while the old room is still whole (zombies and
// bodies are saved here), "build" runs once the new room's art stands and before it shows (lights, bodies, the
// player), and "enter" runs as the new room fades in.
import { Container } from "./vendor/pixi.min.mjs";
import { coreLoaded, prefetchRooms, releaseRooms, roomArt, showLoading } from "./art.js";
import { data } from "./data.js";
import { savePoint } from "./save.js";
import { story } from "./story.js";
import { world } from "./world.js";

// The layers of the world, from the back: the room's art, bodies and decals, everything that moves and is sorted,
// bullets and thrown things, the lamps and the flashlight's beam, the foreground art that hides them, and the effects
// drawn over it
const LAYER_NAMES = ["bg", "back", "actors", "shots", "lights", "fg", "effects"];
// Marker kinds the game hides when it builds a room (F4:22101-22407): their art is only a box to read a place from
const HIDDEN_KINDS = new Set(["trig", "shop", "body", "light"]);
// The floor sits at this screen y under every room (F4:22140)
const FLOOR_SCREEN_Y = 300;
// While the player walks, they stay between these screen x values (F4:10906 with the doubled scroll fixed)
const BAND_LEFT = 340;
const BAND_RIGHT = 420;
// A player further outside the band than this was moved at once (a teleport, a blast), and the camera catches up in
// one step
const SNAP_DISTANCE = 200;
const FADE_SECONDS = 0.5;
// The rooms whose art is kept as well as the current one and its neighbours
const RECENT_ROOMS = 4;
const PAUSE_REASON = "room change";
// A screen shake moves the view this often (F4:27074)
const SHAKE_STEP_MS = 50;
// The sprites whose first frame hangs a picture crooked
const GRAFFITI = 480;
const POSTER = 566;
const ID_PARTS = /^l(\d+)_s(\d+)_b(\d+)_f(\d+)_r(\d+)$/;
// Used until the converted constants load
const DEFAULT_CONSTANTS = {
  moveEdgeBuffer: 50,
  panEdgeBuffer: 10,
  randEdgeBuffer: 50,
  screenShakeXMax: 10,
  screenShakeYMax: 10,
};

// A container that steps the clips inside it, as the root steps the clips attached to it. While the world is paused the
// room's living fighters hold still, so no shot, reload or bite plays out behind a panel (pauseGame F4:25207-25219)
class Layer extends Container {
  advance() {
    const paused = world.paused;
    for (const child of [...this.children]) {
      if (!paused || !fighting(child.owner)) {
        child.advance?.();
      }
    }
  }
}

// The player, a companion, a zombie or a human who is still alive. A dead one's fall plays on, under the death screen
function fighting(actor) {
  if (actor?.alive !== true) {
    return false;
  }
  return actor === world.player || [world.companions, world.zombies, world.humans].some((list) => list.includes(actor));
}

let page = null;
let worldLayer = null;
let seed = 0;
let recent = [];
let changing = Promise.resolve();
const listeners = { leave: [], build: [], enter: [] };

export const layers = {};

// The room being played: its data (def from world.json, art from rooms.json), its clips and its places
export const room = {
  id: null,
  def: null,
  art: null,
  width: 0,
  clip: null,
  fgClip: null,
  layers,
  // Marker name -> { name, kind, x, y, w, h, left, top, clip }; where two share a name the one placed last wins
  markers: {},
  // The block markers, as boxes in room pixels
  blocks: [],
  // The floor's y in room pixels
  floorY: 0,
  // The furthest left and right a character may stand
  edges: { left: 0, right: 0 },
  // Where the player starts in this room
  arrivalX: 0,
};

// The view. x and y are where the world's container sits on the stage; the shake adds to them for a moment
export const camera = {
  x: 0,
  y: 0,
  last: null,
  shaking: null,
  offset: { x: 0, y: 0 },

  // A jolt of px pixels for ms milliseconds, unless the player turned screen shake off or one is already running
  shake(px, ms) {
    if (!story.settings?.screenShake || this.shaking) {
      return;
    }
    const steps = Math.max(1, Math.round(ms / SHAKE_STEP_MS));
    this.shaking = { px, left: steps, every: Math.round((SHAKE_STEP_MS / 1000) * page.lib.fps) || 1, wait: 0 };
  },

  stopShake() {
    this.shaking = null;
    this.offset.x = 0;
    this.offset.y = 0;
  },
};

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULT_CONSTANTS[name];
}

// ---------- Setup ----------

// Makes the world's container and hangs the camera on the step. depth is its band on the root
export function initRooms(owner, depth) {
  page = owner;
  worldLayer = new Layer();
  worldLayer.label = "world";
  worldLayer.zIndex = depth;
  page.root.addChild(worldLayer);
  for (const name of LAYER_NAMES) {
    layers[name] = new Layer();
    layers[name].label = name;
    // Each layer is drawn from its own list, so a zombie's new arm or a fresh casing does not make Pixi walk the room's
    // art again to rebuild one list for the whole stage
    layers[name].enableRenderGroup();
    worldLayer.addChild(layers[name]);
  }
  world.enter = enterRoom;
  world.stage("camera", followPlayer);
  world.stage("interface", stepShake, { whilePaused: true });
  page.steppers.push(placeWorld);
  page.lib.scripts.set(GRAFFITI, graffiti);
  page.lib.scripts.set(POSTER, poster);
}

// Where a stage point shows on the stage, and the stage point under a spot of it
export function toScreen(x, y) {
  return { x: x + worldLayer.x, y: y + worldLayer.y };
}

export function toWorld(x, y) {
  return { x: x - worldLayer.x, y: y - worldLayer.y };
}

// The marker with that name in the room being played, or null
export function marker(name) {
  return room.markers[name] ?? null;
}

// Registers fn(room) for a stage of a room change: "leave", "build" or "enter"
export function onRoom(stage, fn) {
  listeners[stage].push(fn);
}

function notify(stage, ...args) {
  for (const fn of listeners[stage]) {
    try {
      fn(...args);
    } catch (e) {
      console.warn(`Union City: a ${stage} listener failed`, e);
    }
  }
}

// ---------- The camera ----------

// The furthest the world's container may sit left and right: the room's edges plus a little (F4:10906)
function cameraRange() {
  const slack = constant("panEdgeBuffer");
  return { min: page.width - room.width - slack, max: slack };
}

// A room narrower than the stage sits in the middle of it (F4:10880)
function narrow() {
  return room.width < page.width;
}

function clampCamera(x) {
  if (narrow()) {
    return (page.width - room.width) / 2;
  }
  const { min, max } = cameraRange();
  return Math.min(max, Math.max(min, x));
}

// The view that puts a player standing at x in the middle of the stage, kept inside the room
function cameraFor(x) {
  return clampCamera(page.width / 2 - x);
}

// The player walks between screen x 340 and 420 without the view moving; past either, the view moves with them at
// their pace, and stops at the room's edges
function followPlayer() {
  const player = world.player;
  if (!room.id) {
    return;
  }
  if (!player) {
    camera.last = null;
    camera.x = clampCamera(camera.x);
    return;
  }
  const pace = camera.last === null ? 0 : Math.abs(player.x - camera.last);
  camera.last = player.x;
  const screenX = player.x + camera.x;
  const away = screenX > BAND_RIGHT ? BAND_RIGHT - screenX : Math.max(0, BAND_LEFT - screenX);
  const reach = Math.abs(away) > SNAP_DISTANCE ? Math.abs(away) : Math.max(pace, 1);
  camera.x = clampCamera(camera.x + Math.sign(away) * Math.min(Math.abs(away), reach));
}

// Each shake step throws the view a random way up to px / 2 each side, and the view is put back when it ends
function stepShake() {
  const shaking = camera.shaking;
  if (!shaking) {
    return;
  }
  shaking.wait -= 1;
  if (shaking.wait > 0) {
    return;
  }
  shaking.wait = shaking.every;
  shaking.left -= 1;
  if (shaking.left < 0) {
    camera.stopShake();
    return;
  }
  const px = Math.min(shaking.px, constant("screenShakeXMax"));
  const py = Math.min(shaking.px, constant("screenShakeYMax"));
  camera.offset.x = (Math.random() - 0.5) * px;
  camera.offset.y = (Math.random() - 0.5) * py;
}

// The container sits where the camera says, every step, paused or not
function placeWorld() {
  worldLayer.x = camera.x + camera.offset.x;
  worldLayer.y = camera.y + camera.offset.y;
}

// ---------- Neighbours ----------

function roomIdOf(l, s, b, f, r) {
  return `l${l}_s${s}_b${b}_f${f}_r${r}`;
}

// The rooms a marker can lead to, by the rules of changeRooms (F4:14284-14440): each takes the room's own numbers
// (location, street, building, floor, room) and the number in the marker's name. A door goes left or right by the side
// the player stands on, so both are neighbours
const LEADS = {
  door: ([l, s, b, f, r]) => [[l, s, b, f, r - 1], [l, s, b, f, r + 1]],
  room: ([l, s, b, f], number) => [[l, s, b, f, number]],
  uprm: ([l, s, b, f], number) => [[l, s, b, f, number]],
  dnrm: ([l, s, b, f], number) => [[l, s, b, f, number]],
  ltrm: ([l, s, b, f, r]) => [[l, s, b, f, r - 1]],
  rtrm: ([l, s, b, f, r]) => [[l, s, b, f, r + 1]],
  entr: ([l, s], number) => [[l, s, number, 1, 1]],
  exit: ([l, s]) => [[l, s, 0, 0, 1]],
  sup: ([l, s, b, f, r]) => [[l, s, b, f + 1, r]],
  sdwn: ([l, s, b, f, r]) => [[l, s, b, f - 1, r]],
  drop: ([l, s, b, f, r]) => [[l, s, b, f - 1, r]],
  strt: ([l, s]) => [[l, s - 1, 0, 0, 1], [l, s + 1, 0, 0, 1]],
}; // fmt: skip

// The ids of the rooms that exist one move from this room
export function neighbours(id) {
  const parts = ID_PARTS.exec(id);
  const art = data.rooms?.[id];
  if (!parts || !art) {
    return [];
  }
  const here = parts.slice(1).map(Number);
  const found = new Set();
  for (const each of art.markers) {
    for (const there of LEADS[each.kind]?.(here, Number(each.name.slice(4))) ?? []) {
      const next = roomIdOf(...there);
      if (next !== id && data.world.rooms[next]) {
        found.add(next);
      }
    }
  }
  return [...found];
}

// ---------- Seeded pictures ----------

// The original's seeded random (getRandom, F4:561): the room's seed makes the same posters hang in the same room every
// time
function seededRandom() {
  seed = (seed * 9301 + 49297) % 233280;
  return seed / 233280;
}

function seededRange(low, high) {
  return Math.floor(low + (high - low + 1) * seededRandom());
}

function turn(node, degrees, scale) {
  node.rotation = (degrees * Math.PI) / 180;
  node.scale.set(scale / 100);
}

// Graffiti hangs at a turn and a size the room's seed picked (S480 frame 1)
function graffiti(clip) {
  const picture = clip.named.graffiti;
  if (picture) {
    turn(picture, seededRange(-30, 30), seededRange(50, 100));
  }
}

// A poster hangs a little crooked, cut to its mask (S566 frame 1)
function poster(clip) {
  const { poster: picture, posterMask: mask } = clip.named;
  if (!picture || !mask) {
    return;
  }
  const degrees = seededRange(-2, 2);
  const scale = seededRange(85, 100);
  turn(picture, degrees, scale);
  turn(mask, degrees, scale);
  picture.mask = mask;
  mask.renderable = false;
  if (picture.named?.grime) {
    picture.named.grime.mask = mask;
  }
}

// ---------- Building a room ----------

function defaultSeed(id) {
  const [l, s, b, f, r] = ID_PARTS.exec(id).slice(1).map(Number);
  return l * 1000 + s * 1000 + b * 100 + f * 10 + r;
}

// A hidden part stops cutting out what it was masking: the art's bounds box is a mask layer, and the game hides it
function hideMarker(node) {
  node.visible = false;
  for (const sibling of node.parent?.children ?? []) {
    if (sibling.mask === node) {
      sibling.mask = null;
    }
  }
}

function zeroAlpha(node) {
  node.scriptAlpha = 0;
  node.alpha = 0;
}

function triggered(number) {
  return Boolean(story.triggers?.[number]?.triggered);
}

// Runs fn on the room's part at each depth
function eachAt(clip, depths, fn) {
  for (const depth of depths) {
    const node = clip.at(depth);
    if (node) {
      fn(node);
    }
  }
}

// The room's own load handlers from the converted data: parts that start hidden or see-through, doors drawn open or
// shut, and a door that opens once two triggers have fired. Then the markers the game always hides
function applyPlacements(clip, art) {
  eachAt(clip, art.hidden, hideMarker);
  eachAt(clip, art.alpha0, zeroAlpha);
  for (const [depth, label] of Object.entries(art.doorLooks)) {
    clip.at(Number(depth))?.gotoAndStop(label);
  }
  for (const each of art.openIfTriggers ?? []) {
    if (each.triggers.every(triggered)) {
      clip.at(each.depth)?.gotoAndStop(each.look);
    }
  }
  eachAt(
    clip,
    art.markers.filter((each) => HIDDEN_KINDS.has(each.kind)).map((each) => each.depth),
    hideMarker,
  );
}

// The markers by name, each with the clip the art placed. Where two share a name, Flash's lookup by name finds the
// one at the lower depth (Washington Ave's cont1 is Richards' corpse, not the stray copy above the stage)
function indexMarkers(clip, art) {
  const found = {};
  for (const each of art.markers) {
    if (found[each.name] && found[each.name].depth < each.depth) {
      continue;
    }
    found[each.name] = { ...each, clip: clip.at(each.depth) };
  }
  return found;
}

// One bit of rubbish or gore at a random place on the floor
function litterBit(kind, parent, name) {
  const bit = page.lib.makeExported(kind === "Trash" ? "randomTrash" : "randomTrashGore");
  const edge = constant("randEdgeBuffer");
  bit.x = edge + Math.round(Math.random() * (room.width - edge * 2));
  bit.y = room.floorY - 60 + Math.floor(Math.random() * 80) + 20;
  bit.gotoAndStop(1 + Math.floor(Math.random() * bit.totalFrames));
  if (kind === "Trash") {
    bit.scale.set((Math.floor(Math.random() * 60) + 60) / 100);
    bit.rotation = Math.random() * Math.PI * 2;
  } else {
    const size = (Math.floor(Math.random() * 10) + 90) / 100;
    bit.scale.set(Math.random() < 0.5 ? -size : size, size);
  }
  parent.attach(bit, name);
}

// Rubbish and gore scattered over the floor, as many as the room's rate says (randomDecos, F4:23010)
function scatterLitter(clip, def) {
  const count = constant(`randRate_${def.randRate}`);
  if (!["Trash", "Gore"].includes(def.rand) || !count) {
    return;
  }
  for (let i = 0; i < count; i += 1) {
    litterBit(def.rand, clip.named.bg ?? clip, `rt_${i}`);
  }
}

function build(id, def, art) {
  seed = def.seed ?? defaultSeed(id);
  const clip = page.lib.makeExported(art.export);
  layers.bg.addChild(clip);
  applyPlacements(clip, art);
  room.id = id;
  room.def = def;
  room.art = art;
  room.width = art.width;
  room.clip = clip;
  room.markers = indexMarkers(clip, art);
  room.blocks = art.blocks;
  room.floorY = room.markers.floorMarker?.y ?? 0;
  const edge = constant("moveEdgeBuffer");
  room.edges = { left: edge, right: art.width - edge };
  if (art.fg) {
    room.fgClip = page.lib.makeExported(art.fg);
    layers.fg.addChild(room.fgClip);
  }
  scatterLitter(clip, def);
}

// Where the player starts: a marker's place, an edge ("start" or "end") or a number; the room's middle when the marker
// is not there
function arrivalPlace(arrival) {
  const low = room.edges.left;
  const high = room.edges.right;
  let x = room.width / 2;
  if (typeof arrival === "number") {
    x = arrival;
  } else if (arrival === "start") {
    x = low;
  } else if (arrival === "end") {
    x = high;
  } else if (arrival && room.markers[arrival]) {
    x = room.markers[arrival].x;
  }
  return Math.min(high, Math.max(low, x));
}

// ---------- Changing rooms ----------

// Resolves after that many steps of the original's clock, paused or not
function afterSteps(count) {
  return new Promise((resolve) => {
    let left = count;
    const tick = () => {
      left -= 1;
      if (left <= 0) {
        resolve();
        // Taken off once the steps being run are done
        queueMicrotask(() => {
          page.steppers.splice(page.steppers.indexOf(tick), 1);
        });
      }
    };
    page.steppers.push(tick);
  });
}

function emptyLayers() {
  for (const layer of Object.values(layers)) {
    for (const child of [...layer.children]) {
      child.destroy({ children: true });
    }
  }
  room.clip = null;
  room.fgClip = null;
  room.markers = {};
  room.blocks = [];
  camera.stopShake();
}

// The room's pictures go, for a story that is left (SAVE AND QUIT)
export function clearRoom() {
  emptyLayers();
}

function showRoom(id, def, art, arrival) {
  emptyLayers();
  recent = [id, ...recent.filter((each) => each !== id)].slice(0, RECENT_ROOMS);
  const next = neighbours(id);
  releaseRooms([...recent, ...next]);
  build(id, def, art);
  room.arrivalX = arrivalPlace(arrival);
  camera.last = null;
  camera.x = cameraFor(room.arrivalX);
  camera.y = FLOOR_SCREEN_Y - room.floorY;
  placeWorld();
  world.room = room;
  notify("build", room);
  return next;
}

async function change(id, arrival) {
  const def = data.world.rooms[id];
  const art = data.rooms[id];
  if (!def || !art) {
    throw new Error(`Union City: no room called ${id}`);
  }
  if (world.room && story.player) {
    savePoint("room");
  }
  world.leaveRoom();
  world.pause(PAUSE_REASON);
  try {
    const ready = Promise.all([roomArt(id), coreLoaded()]);
    showLoading(true, FADE_SECONDS);
    await Promise.all([ready, afterSteps(Math.round(FADE_SECONDS * page.lib.fps))]);
    notify("leave", world.room);
    const next = showRoom(id, def, art, arrival);
    world.resume(PAUSE_REASON);
    showLoading(false, FADE_SECONDS);
    notify("enter", room);
    prefetchRooms(next);
    savePoint("room");
  } catch (e) {
    console.warn(`Union City: couldn't enter ${id}`, e);
    showLoading(false, FADE_SECONDS);
    throw e;
  } finally {
    world.resume(PAUSE_REASON);
  }
}

// Moves the player to a room: a fade to black, the new room, a fade in. arrival is the name of a marker to stand at
// ("exit2"), an edge ("start" or "end"), or an x; the room's middle when the marker is missing. Resolves once the new
// room is drawn. Changes made while one is under way wait their turn
export function enterRoom(id, arrival) {
  const run = changing.then(() => change(id, arrival));
  // A failed change is logged where it happens; the next one still goes ahead
  changing = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}
