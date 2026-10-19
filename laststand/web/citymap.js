// The city map (openMap F4:3967, setupMap F4:4003, moveMap F4:4045, buttonSetup_locations F4:4062, showTravelDialog
// F4:4121, travelTo F4:3933, scrollMap F4:4204, zoomMapIn and zoomMapOut F4:4256, unlockAreas F4:4300): the screen the
// "[E] EXIT TO MAP" markers open. The world stops and goes out of sight, the map's art (sprite worldMap, 6738) fills the
// stage under the HUD's pause bar, and the map slides to the section the player stands in, with YOU ARE HERE on it and
// the tracked quest's TASK LOCATION.
//
// Each section is a coloured border clip. A locked section is dimmed (a black fill at 35%); an unlocked one is left
// bright, and shows its white outline while the pointer is over it (it fades out again when the pointer leaves, as the
// original's rollOver and rollOut do). Pressing an unlocked section slides the map to it and asks where to go: its
// start, or its far end when that has been unlocked too. Travel lets the hours pass like waiting (passHours: healing,
// no hunger or sleep cost), then fades to the new room. CANCEL TRAVEL goes back to the room the map was opened from,
// 100 px in from its map marker. No encounters happen on the way.
//
// The map is moved by the mouse at the stage edge (the left and right edges, and a band below the top and above the
// bottom bar), the arrow keys and WASD; the wheel steps its zoom between 25, 50 and 60%. On a touch screen a drag
// scrolls it, a pinch steps the zoom, and a tap picks a section (spec 8.3).
//
// Unlocks: unlockSection(n) opens a section and says so; unlockSection(n, true) opens its far end (story.map.ends). The
// quests and triggers call them (Tasks 52 and 55).
import { Rectangle } from "./vendor/pixi.min.mjs";
import { showLoading } from "./art.js";
import { data } from "./data.js";
import { makeFilter } from "./flash.js";
import { help } from "./help.js";
import { hud, setText, tween } from "./hud.js";
import { input } from "./input.js";
import { interact } from "./interact.js";
import { setAlpha, tint } from "./panels.js";
import { rng } from "./rng.js";
import { layers, room } from "./rooms.js";
import { savePoint } from "./save.js";
import { passHours } from "./sleep.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

const PAUSE = "map";
const MAP_EXPORT = "worldMap";
const INTERLACE_EXPORT = "hud_interlace";
const DIALOG_EXPORT = "travelDialog";
// The map and its scan-line cover sit between the world's crosshair (1900) and the HUD (2000), so the pause bar, the
// area box and CANCEL TRAVEL draw over them
const MAP_DEPTH = 1950;
// The zoom steps (zoomTop, zoomMid, zoomBottom F4:26492), as percents
const ZOOMS = [25, 50, 60];
// A section's border is drawn at this share of its size (borderScale F4:26481)
const BORDER_SCALE = 0.985;
// The fill under an unlocked section, and under a locked one, as alpha (F4:4065)
const OPEN_BASE = 0.05;
const LOCKED_BASE = 0.35;
const WHITE = 0xffffff;
// Almost black: a colour with any offset is drawn after the border's glow, as Flash draws a colour transform, where a
// pure black tint would darken the picture first and leave the white glow showing through the dimmed fill
const BLACK = 0x010101;
// The map's slide to a section, and the zoom's fade-in, in seconds
const SLIDE_SECONDS = 1;
const FADE_SECONDS = 0.3;
const BORDER_FADE = 0.2;
// Mouse scrolling (F4:26482): pixels of the stage edge that scroll, the band's inner limit, a step, and the frames
// the pointer waits in the zone first
const EDGE_OUTER = 90;
const EDGE_INNER = 32;
const SCROLL_STEP = 15;
const SCROLL_WAIT = 5;
// A wheel turn zooms one step; the next one waits for the fade to end
const WHEEL_WAIT_SECONDS = 0.3;
// A finger that moves further than this is a drag, not a tap (stage pixels)
const TAP_SLOP = 8;
// A pinch steps the zoom when the fingers' distance has changed by this much
const PINCH_IN = 0.8;
const PINCH_OUT = 1.25;
// The hit test of a section is the fill's alpha, kept at this many stage pixels to a mask pixel
const MASK_STEP = 4;
const MASK_ALPHA = 16;
// Each border's art: the glow it is drawn with, keyed by instance name
const LOCATIONS_SPRITE = 6725;
const BORDER_NAME = /^section(\d+)_border$/;
const MARKER_NAME = /^section\d+$/;
const MOST_RECORDED = 100;

let page = null;
let dialogDepth = 0;
// The map on screen, once its art is in: { map, interlace, locations, sections, ... }; null when none is open
let view = null;
// An open that is waiting for the art, or a map being left: the world stays held until it is done
let busy = false;
// What was opened, picked and travelled, newest last, for checks
const log = [];

function record(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- The unlocks ----------

function unlocks() {
  story.map.ends ??= [];
  return story.map;
}

export function isUnlocked(n) {
  return unlocks().unlocked.includes(n);
}

export function endUnlocked(n) {
  return unlocks().ends.includes(n);
}

// Opens a section (and says NEW MAP AREA UNLOCKED), or with end its far end (unlockEndLoc: no word of it)
export function unlockSection(n, end = false) {
  const state = unlocks();
  if (end) {
    if (!state.ends.includes(n)) {
      state.ends.push(n);
    }
    return;
  }
  if (!state.unlocked.includes(n)) {
    state.unlocked.push(n);
  }
  hud.alert("NEW MAP AREA UNLOCKED", "white");
  if (view) {
    dressSection(view.sections.find((each) => each.n === n));
  }
}

// A quest's or trigger's list of sections: all opened, one alert (unlockAreas)
export function unlockSections(list) {
  for (const n of list) {
    if (!isUnlocked(n)) {
      unlocks().unlocked.push(n);
    }
  }
  if (list.length) {
    hud.alert("NEW MAP AREA UNLOCKED", "white");
  }
  if (view) {
    view.sections.forEach(dressSection);
  }
}

// ---------- Where things are ----------

// The section the player stands in (locationNumber)
function sectionNow() {
  return Number(/^l(\d+)/.exec(room.def?.loc ?? room.id ?? "")?.[1]);
}

function sectionData(n) {
  return data.world.sections[n] ?? null;
}

// Hours of travel between two sections: the markers' distance over 200 (travelTo F4:3934)
function hoursBetween(from, to) {
  const [a, b] = [sectionData(from)?.marker, sectionData(to)?.marker];
  if (!a || !b) {
    return 0;
  }
  return Math.round((Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1])) / 200);
}

function stageOf(event) {
  return page.root.toLocal(event.global);
}

// ---------- Section hit tests ----------

// The fill of a section as a small alpha picture, so a press lands on the section's shape and not its bounding box
function maskOf(base) {
  const lib = page.lib;
  const shape = base.at(1);
  return lib.piecesOf(shape.charId).map((piece) => {
    const frame = piece.texture.frame;
    const wide = Math.max(1, Math.ceil(frame.width / lib.scale / MASK_STEP));
    const high = Math.max(1, Math.ceil(frame.height / lib.scale / MASK_STEP));
    const canvas = document.createElement("canvas");
    canvas.width = wide;
    canvas.height = high;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(piece.texture.source.resource, frame.x, frame.y, frame.width, frame.height, 0, 0, wide, high);
    return { left: piece.left, top: piece.top, wide, high, alpha: ctx.getImageData(0, 0, wide, high).data };
  });
}

function inMask(mask, x, y) {
  return mask.some((piece) => {
    const u = Math.floor((x - piece.left) / MASK_STEP);
    const v = Math.floor((y - piece.top) / MASK_STEP);
    return u >= 0 && v >= 0 && u < piece.wide && v < piece.high && piece.alpha[(v * piece.wide + u) * 4 + 3] > MASK_ALPHA;
  });
}

// The section under a stage point, the one drawn on top where two overlap, or null
function sectionAt(sx, sy) {
  const { map, locations } = view;
  const mx = (sx - map.x) / map.scale.x - locations.x;
  const my = (sy - map.y) / map.scale.y - locations.y;
  for (const section of [...view.sections].reverse()) {
    const { border, base } = section;
    const x = (mx - border.x) / border.scale.x - base.x;
    const y = (my - border.y) / border.scale.y - base.y;
    if (inMask(section.mask, x, y)) {
      return section.n;
    }
  }
  return null;
}

// ---------- The sections' look ----------

// Locked sections are dimmed; unlocked ones are bright (buttonSetup_locations F4:4068)
function dressSection(section) {
  if (!section || section.border.destroyed) {
    return;
  }
  const locked = !isUnlocked(section.n);
  setAlpha(section.base, locked ? LOCKED_BASE : OPEN_BASE);
  tint(section.border, locked ? BLACK : WHITE);
}

function rollOver(n) {
  const section = view.sections.find((each) => each.n === n);
  if (!section || !isUnlocked(n)) {
    return;
  }
  view.current = n;
  showInfo();
  tween(section.border, "alpha", 100, BORDER_FADE);
  tween(section.base, "alpha", OPEN_BASE * 100, BORDER_FADE);
}

function rollOut(n) {
  const section = view.sections.find((each) => each.n === n);
  if (!section || !isUnlocked(n)) {
    return;
  }
  tween(section.border, "alpha", 0, BORDER_FADE);
  tween(section.base, "alpha", 0, BORDER_FADE);
}

function setHover(n) {
  if (view.hover === n) {
    return;
  }
  if (view.hover !== null) {
    rollOut(view.hover);
  }
  view.hover = n;
  if (n !== null) {
    rollOver(n);
  }
}

// The glow is drawn at the map's size, so it follows the zoom (Flash's filters scale with their clip)
function fitGlow() {
  const scale = page.lib.filterScale * (view.zoom / 100);
  const specs = page.lib.data.sprites[LOCATIONS_SPRITE].f[0];
  for (const section of view.sections) {
    const entry = specs.find((each) => each[5] === `section${section.n}_border`);
    (entry?.[7]?.filters ?? []).forEach((spec, index) => {
      if (section.border.filters?.[index]) {
        makeFilter(spec, section.border.filters[index], scale);
      }
    });
  }
}

function showInfo() {
  const info = sectionData(view.current);
  hud.mapInfo(info ? { name: info.name, danger: info.danger } : null);
}

// ---------- Moving the map ----------

function mapSize() {
  const { bounds, map } = view;
  return { width: bounds.width * map.scale.x, height: bounds.height * map.scale.y };
}

// Slides the map so that a point of it sits at the middle of the stage (moveMap F4:4045). seconds 0 is at once
function centreOn(x, y, seconds) {
  const { map } = view;
  const toX = page.width / 2 - x * map.scale.x;
  const toY = page.height / 2 - y * map.scale.y;
  if (seconds <= 0) {
    view.slide = null;
    map.x = toX;
    map.y = toY;
    return;
  }
  view.slide = { fromX: map.x, fromY: map.y, toX, toY, age: 0, frames: Math.max(1, Math.round(seconds * page.lib.fps)) };
}

function centreOnSection(n, seconds = SLIDE_SECONDS) {
  const marker = view.map.child(`section${n}`);
  if (marker) {
    centreOn(marker.x, marker.y, seconds);
  }
}

function stepSlide() {
  const slide = view.slide;
  if (!slide) {
    return;
  }
  slide.age += 1;
  const share = Math.sin((Math.min(1, slide.age / slide.frames) * Math.PI) / 2);
  view.map.x = slide.fromX + (slide.toX - slide.fromX) * share;
  view.map.y = slide.fromY + (slide.toY - slide.fromY) * share;
  if (slide.age >= slide.frames) {
    view.slide = null;
  }
}

// A zoom step: the middle of the stage stays where it is, and the map fades in at its new size (zoomMapIn F4:4256)
function zoomBy(direction) {
  const { map } = view;
  const at = ZOOMS.indexOf(view.zoom);
  const next = Math.min(ZOOMS.length - 1, Math.max(0, at + direction));
  const x = (page.width / 2 - map.x) / map.scale.x;
  const y = (page.height / 2 - map.y) / map.scale.y;
  if (ZOOMS[next] !== view.zoom) {
    view.zoom = ZOOMS[next];
    map.scale.set(view.zoom / 100);
    fitGlow();
    map.alpha = 0;
    tween(map, "alpha", 100, FADE_SECONDS);
    view.wheelWait = Math.round(WHEEL_WAIT_SECONDS * page.lib.fps);
    record("zoom", { zoom: view.zoom });
  }
  centreOn(x, y, 0);
}

// The mouse at the edge, and the keys, move the map a step at a time (scrollMap F4:4204, scrollMapKeys F4:4163)
function scrollByEdge() {
  const { map } = view;
  const { width, height } = mapSize();
  const mouse = input.mouse;
  const zones = [
    { key: "up", inside: mouse.y < EDGE_OUTER && mouse.y >= EDGE_INNER && map.y < 0, move: () => (map.y += SCROLL_STEP) },
    {
      key: "down",
      inside:
        mouse.y >= page.height - EDGE_OUTER && mouse.y < page.height - EDGE_INNER && map.y > page.height - height,
      move: () => (map.y -= SCROLL_STEP),
    },
    { key: "left", inside: mouse.x < EDGE_INNER && map.x < 0, move: () => (map.x += SCROLL_STEP) },
    {
      key: "right",
      inside: mouse.x >= page.width - EDGE_INNER && map.x > page.width - width,
      move: () => (map.x -= SCROLL_STEP),
    },
  ];
  for (const zone of zones) {
    if (!view.mouseSeen || !zone.inside) {
      view.waits[zone.key] = SCROLL_WAIT;
      continue;
    }
    view.waits[zone.key] -= 1;
    if (view.waits[zone.key] < 0) {
      zone.move();
    }
  }
}

function scrollByKeys() {
  const { map } = view;
  const { width, height } = mapSize();
  if (input.left && map.x < 0) {
    map.x += SCROLL_STEP;
  }
  if (input.right && map.x > page.width - width) {
    map.x -= SCROLL_STEP;
  }
  if ((input.keys.down("KeyS") || input.keys.down("ArrowDown")) && map.y > page.height - height) {
    map.y -= SCROLL_STEP;
  }
  if (input.upHeld && map.y < 0) {
    map.y += SCROLL_STEP;
  }
}

function stepMap() {
  if (!view) {
    return;
  }
  stepSlide();
  if (view.wheelWait > 0) {
    view.wheelWait -= 1;
  } else if (input.wheel !== 0 && view.dialogAt === null) {
    zoomBy(input.wheel < 0 ? 1 : -1);
  }
  if (!view.slide) {
    scrollByEdge();
    scrollByKeys();
  }
}

// ---------- The pointer ----------

// A finger or the mouse went down on the map. Fingers are followed for a drag or a pinch; the mouse presses a section
function pointerDown(event) {
  if (event.pointerType !== "touch" && event.button !== 0) {
    return;
  }
  const at = stageOf(event);
  const touch = event.pointerType === "touch";
  view.pointers.set(event.pointerId, { x: at.x, y: at.y, from: at, touch, far: false, section: sectionAt(at.x, at.y) });
  if (touch) {
    view.mouseSeen = false;
    view.pinch = null;
    if (view.pointers.size === 2) {
      // Two fingers are a pinch, never a tap
      view.pinch = fingerGap();
      view.pointers.forEach((finger) => (finger.far = true));
    }
  }
}

function fingerGap() {
  const [a, b] = [...view.pointers.values()];
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointerMove(event) {
  if (!view) {
    return;
  }
  const at = stageOf(event);
  const touch = event.pointerType === "touch";
  if (!touch) {
    view.mouseSeen = true;
    setHover(sectionAt(at.x, at.y));
    return;
  }
  const finger = view.pointers.get(event.pointerId);
  if (!finger) {
    return;
  }
  const moved = { x: at.x - finger.x, y: at.y - finger.y };
  finger.x = at.x;
  finger.y = at.y;
  finger.far ||= Math.hypot(at.x - finger.from.x, at.y - finger.from.y) > TAP_SLOP;
  if (view.pointers.size === 2 && view.pinch) {
    pinchMove();
  } else if (view.pointers.size === 1 && finger.far && !view.slide) {
    dragBy(moved.x, moved.y);
  }
}

// The map follows a finger, kept so that it still covers the stage as far as it can. The map opens slid to the
// player's section, which can leave it short of an edge: a drag then never pulls it further out, and never snaps it in
// at the first touch either
function dragBy(dx, dy) {
  const { map } = view;
  const { width, height } = mapSize();
  map.x = follow(map.x, map.x + dx, Math.min(0, page.width - width), 0);
  map.y = follow(map.y, map.y + dy, Math.min(0, page.height - height), 0);
}

// Where one axis goes: next, but no further past low or high than it already stands
function follow(now, next, low, high) {
  return Math.min(Math.max(next, Math.min(low, now)), Math.max(high, now));
}

// Two fingers moving apart or together step the zoom, and the next step needs the same change again
function pinchMove() {
  const gap = fingerGap();
  const ratio = gap / view.pinch;
  if (ratio >= PINCH_OUT) {
    zoomBy(1);
    view.pinch = gap;
  } else if (ratio <= PINCH_IN) {
    zoomBy(-1);
    view.pinch = gap;
  }
}

function pointerUp(event) {
  if (!view) {
    return;
  }
  const press = view.pointers.get(event.pointerId);
  view.pointers.delete(event.pointerId);
  view.pinch = null;
  if (!press) {
    return;
  }
  const at = stageOf(event);
  if (press.touch) {
    for (const other of view.pointers.values()) {
      other.far = true;
    }
    if (view.pointers.size === 0 && !press.far) {
      tapped(sectionAt(at.x, at.y));
    }
    return;
  }
  // A mouse press picks the section it went down on, if it is released on it too (onRelease)
  const section = sectionAt(at.x, at.y);
  if (section !== null && section === press.section) {
    pick(section);
  }
}

// A finger the browser took away (a system gesture, a call) never comes up, and Pixi passes no word of it on: the page
// hears it, and the finger is dropped, so the next touch is a tap again and not half of a pinch. Losing focus drops
// every finger
function pointerCancel(event) {
  view?.pointers.delete(event.pointerId);
  if (view) {
    view.pinch = null;
  }
}

function dropPointers() {
  view?.pointers.clear();
  if (view) {
    view.pinch = null;
  }
}

// A tap lights the section like the pointer's rollover would, then picks it
function tapped(section) {
  if (section === null) {
    return;
  }
  setHover(section);
  pick(section);
}

function leaveMap() {
  if (view) {
    setHover(null);
  }
}

// ---------- Picking a section and travelling ----------

// An unlocked section: the map slides to it and the travel dialog asks where to go (the section's onRelease F4:4087)
export function pick(n) {
  if (!view || !sectionData(n) || !isUnlocked(n)) {
    return false;
  }
  centreOnSection(n);
  view.current = n;
  showInfo();
  record("pick", { section: n });
  showDialog(n);
  return true;
}

function closeDialog() {
  page.detach("travel");
  if (view) {
    view.dialogAt = null;
  }
}

// TO <AREA>, with its start and, when that has been unlocked, its far end as two choices (showTravelDialog F4:4121)
function showDialog(n) {
  closeDialog();
  const info = sectionData(n);
  const dialog = page.attach(DIALOG_EXPORT, dialogDepth, "travel");
  // Its buttons go straight to a place on a press and may sit where the section was, so the second click of a double
  // click on the section presses nothing
  input.shutByClick();
  dialog.x = page.width / 2;
  dialog.y = page.height / 2;
  view.dialogAt = n;
  setText(dialog.child("txt"), `TO ${info.name.toUpperCase()}`);
  const withEnd = endUnlocked(n);
  const [start, end, single] = ["loc1Button", "loc2Button", "loc3Button"].map((name) => dialog.child(name));
  start.visible = withEnd;
  end.visible = withEnd;
  single.visible = !withEnd;
  setText(start.child("btnText"), info.startLocName);
  setText(single.child("btnText"), info.startLocName);
  setText(end.child("btnText"), info.endLocName);
  const go = (id, arrival) => () => {
    input.swallowPress();
    input.shutByClick();
    travel(n, id, arrival);
  };
  start.setHandler("onPress", go(info.startLoc, "start"));
  single.setHandler("onPress", go(info.startLoc, "start"));
  end.setHandler("onPress", go(info.endLoc, "end"));
  dialog.child("noButton").setHandler("onPress", () => {
    input.swallowPress();
    input.shutByClick();
    closeDialog();
  });
}

// The map goes and the HUD and the clock come back at once, as the original's travelTo does; the room fades in behind a
// black screen, and the world's picture shows again when the new room is built
function leaveFor(enter) {
  const { current: section } = view;
  closeDialog();
  teardown();
  hud.hidePlay(false);
  hud.hideDock(false);
  hud.hideBars(false);
  help.hideAll(false);
  busy = true;
  sound.play(`sound_door${rng.random(2) + 1}`);
  record("leave", { section });
  const entering = Promise.resolve(enter());
  world.resume(PAUSE);
  entering
    .catch((e) => console.warn("Union City: couldn't leave the map", e))
    .finally(() => {
      busy = false;
      showWorld(true);
      if (room.def) {
        hud.showLocation();
      }
    });
}

// The hours go by, and the player arrives at a street's start or a building's end (travelTo F4:3933)
function travel(n, id, arrival) {
  if (!view) {
    return;
  }
  const hours = hoursBetween(sectionNow(), n);
  passHours(hours, { sleep: false });
  record("travel", { section: n, hours, id, arrival });
  leaveFor(() => world.enter(id, arrival));
}

// CANCEL TRAVEL: back to the room the map was opened from, 100 px in from the map marker (changeRooms F4:14630)
export function cancelTravel() {
  if (!view) {
    return false;
  }
  const marker = room.markers.area1;
  let at;
  if (marker) {
    at = marker.x > page.width / 2 ? marker.x - 100 : marker.x + 100;
  }
  passHours(0, { sleep: false });
  record("cancel", { x: at ?? null });
  leaveFor(() => world.enter(room.id, at));
  return true;
}

// ---------- Opening and closing ----------

function hold(on) {
  hud.hidePlay(on);
  hud.hideDock(on);
  hud.hideBars(on);
  help.hideAll(on);
  showWorld(!on);
}

// The world's picture is switched off while the map is up or the new room is being built, so it is never shown halfway
function showWorld(on) {
  const layer = layers.bg?.parent;
  if (layer) {
    layer.renderable = on;
  }
}

// Takes the map off the stage
function teardown() {
  if (!view) {
    return;
  }
  page.detach("map");
  page.detach("mapInterlace");
  page.detach("travel");
  hud.mapInfo(null);
  hud.cancelTravel(false);
  view = null;
}

// The map could not open: the world comes back as it was
function restore() {
  busy = false;
  hold(false);
  world.resume(PAUSE);
}

function sectionsOf(locations) {
  return [...locations.slots.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, slot]) => ({ border: slot.node, match: BORDER_NAME.exec(slot.node.label ?? "") }))
    .filter((each) => each.match)
    .map(({ border, match }) => {
      const base = border.child("base");
      border.scale.set(BORDER_SCALE);
      return { n: Number(match[1]), border, base, mask: maskOf(base) };
    });
}

function placeMark(map, name, n) {
  const mark = map.child(name);
  const at = map.child(`section${n}`);
  if (mark && at) {
    mark.x = at.x;
    mark.y = at.y;
  }
}

// The tracked quest's section, for the TASK LOCATION flag, or null
function questSection() {
  const id = Object.keys(story.quests ?? {}).find((each) => story.quests[each].tracking && !story.quests[each].completed);
  return data.story.quests[id]?.section ?? null;
}

function build() {
  const map = page.attach(MAP_EXPORT, MAP_DEPTH, "map");
  const interlace = page.attach(INTERLACE_EXPORT, MAP_DEPTH + 1, "mapInterlace");
  interlace.eventMode = "none";
  for (const [name, node] of Object.entries(map.named)) {
    if (MARKER_NAME.test(name)) {
      node.visible = false;
    }
  }
  const locations = map.child("locations");
  view = {
    map,
    interlace,
    locations,
    sections: sectionsOf(locations),
    zoom: ZOOMS[0],
    current: sectionNow(),
    hover: null,
    slide: null,
    pointers: new Map(),
    pinch: null,
    mouseSeen: false,
    waits: { up: SCROLL_WAIT, down: SCROLL_WAIT, left: SCROLL_WAIT, right: SCROLL_WAIT },
    wheelWait: 0,
    dialogAt: null,
    bounds: null,
  };
  view.sections.forEach(dressSection);
  map.scale.set(view.zoom / 100);
  fitGlow();
  placeMark(map, "youAreHere", view.current);
  const quest = questSection();
  if (quest !== null) {
    placeMark(map, "questMarker", quest);
  } else {
    map.child("questMarker").visible = false;
  }
  const box = map.getLocalBounds();
  view.bounds = { width: box.width, height: box.height };
  map.hitArea = new Rectangle(box.x, box.y, box.width, box.height);
  map.eventMode = "static";
  map.interactiveChildren = false;
  map.cursor = "default";
  map.on("pointerdown", pointerDown);
  map.on("globalpointermove", pointerMove);
  map.on("pointerup", pointerUp);
  map.on("pointerupoutside", pointerUp);
  map.on("pointerout", leaveMap);
  centreOnSection(view.current);
  hud.cancelTravel(true);
  showInfo();
}

// Opens the map over the world (openMap F4:3967): the world stops, the art comes in, the map slides to the player's
// section. Resolves once it is on screen; false when it could not open
export async function openMap() {
  if (view || busy || !world.active || !story.player) {
    return false;
  }
  busy = true;
  world.pause(PAUSE);
  hold(true);
  const lib = page.lib;
  const ids = [MAP_EXPORT, INTERLACE_EXPORT, DIALOG_EXPORT].map((name) => lib.exported(name));
  const cold = [...lib.pagesFor(ids)].some((index) => !lib.textures[index]);
  try {
    if (cold) {
      showLoading(true);
    }
    await lib.need(ids);
    if (!busy) {
      return false;
    }
    build();
    record("open", { section: view.current });
  } catch (e) {
    console.warn("Union City: couldn't open the city map", e);
    teardown();
    restore();
    return false;
  } finally {
    if (cold) {
      showLoading(false);
    }
  }
  busy = false;
  return true;
}

// Where a section's marker is on the map as it shows now, in the canvas's pixels, or null while the map is not on screen
// or its travel dialog is over it
export function sectionPoint(n) {
  const mark = view && view.dialogAt === null ? view.map.child(`section${n}`) : null;
  if (!mark) {
    return null;
  }
  const { x, y } = mark.getGlobalPosition();
  return { x, y };
}

export const citymap = {
  open: openMap,
  sectionPoint,
  cancel: cancelTravel,
  pick,
  unlock: unlockSection,
  unlockSections,
  isUnlocked,
  endUnlocked,
  get isOpen() {
    return view !== null;
  },
  log,
};

export function initCityMap(owner, depth) {
  page = owner;
  dialogDepth = depth;
  interact.hooks.map = openMap;
  hud.onOpen("cancelTravel", cancelTravel);
  page.steppers.push(stepMap);
  window.addEventListener("pointercancel", pointerCancel);
  window.addEventListener("blur", dropPointers);
  world.onReset(() => {
    if (view || busy) {
      teardown();
      hold(false);
    }
    busy = false;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const citymapDebug = {
  // Opens the map as the area marker does; resolves with the map's state
  async mapOpen() {
    savePoint("map");
    await openMap();
    return citymapDebug.mapState();
  },

  // Where the map, its zoom and its dialog stand
  mapState() {
    if (!view) {
      return { open: false, busy, paused: world.paused, reasons: [...world.reasons] };
    }
    const { map } = view;
    const size = mapSize();
    return {
      open: true,
      current: view.current,
      zoom: view.zoom,
      x: Math.round(map.x),
      y: Math.round(map.y),
      width: Math.round(size.width),
      height: Math.round(size.height),
      sliding: view.slide !== null,
      hover: view.hover,
      dialog: view.dialogAt,
      unlocked: [...unlocks().unlocked],
      ends: [...unlocks().ends],
      info: hud.part("mapInfo")?.visible ? hud.part("mapInfo").child("locName")?.text : null,
      danger: hud.part("mapInfo")?.visible ? hud.part("mapInfo").child("dangerLevel")?.text : null,
      cancel: hud.part("cancelTravel")?.visible ?? null,
      world: layers.bg?.parent?.renderable ?? null,
      paused: world.paused,
      sections: view.sections.map((each) => ({
        n: each.n,
        base: Math.round(each.base.alpha * 100),
        border: Math.round(each.border.alpha * 100),
      })),
    };
  },

  // What the travel dialog shows; null when none is open
  mapDialog() {
    const dialog = page.root.children.find((each) => each.label === "travel");
    if (!dialog || dialog.destroyed) {
      return null;
    }
    const shown = (name) => dialog.child(name).visible;
    const words = (name) => dialog.child(name).child("btnText")?.text ?? null;
    return {
      title: dialog.child("txt").text,
      loc1: shown("loc1Button") ? words("loc1Button") : null,
      loc2: shown("loc2Button") ? words("loc2Button") : null,
      loc3: shown("loc3Button") ? words("loc3Button") : null,
    };
  },

  // The middle of a part of the map screen in the game frame's CSS pixels, for page.py's tap: "section9", "cancel", or a
  // dialog button ("loc1Button", "loc2Button", "loc3Button", "noButton")
  mapPoint(name) {
    let node = null;
    if (name.startsWith("section")) {
      node = view?.sections.find((each) => `section${each.n}` === name)?.base ?? null;
    } else if (name === "cancel") {
      node = hud.part("cancelTravel");
    } else {
      node = page.root.children.find((each) => each.label === "travel")?.child(name) ?? null;
    }
    if (!node) {
      return null;
    }
    const box = node.getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: Math.round(canvas.left + (box.x + box.width / 2) * (canvas.width / page.app.screen.width)),
      y: Math.round(canvas.top + (box.y + box.height / 2) * (canvas.height / page.app.screen.height)),
    };
  },

  // A stage point as the game frame's CSS pixels
  stagePoint(x, y) {
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: Math.round(canvas.left + x * (canvas.width / page.width)),
      y: Math.round(canvas.top + y * (canvas.height / page.height)),
    };
  },

  mapPick(n) {
    return pick(n);
  },

  // Puts a section's marker in the middle of the stage at once
  mapCentre(n) {
    centreOnSection(n, 0);
    return citymapDebug.mapState();
  },

  mapZoom(direction) {
    zoomBy(direction);
    return citymapDebug.mapState();
  },

  mapUnlock(n, end = false) {
    unlockSection(n, end);
    return citymapDebug.mapState();
  },

  mapCancel() {
    return cancelTravel();
  },

  // Presses a travel dialog button as a click on it would
  mapChoose(name) {
    const dialog = page.root.children.find((each) => each.label === "travel");
    dialog?.child(name)?.handlers.onPress?.();
    return dialog !== undefined;
  },

  // What was opened, picked and travelled so far
  mapLog() {
    return log.map((each) => ({ ...each }));
  },
};
