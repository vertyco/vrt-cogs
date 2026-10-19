// The level path: a vertical path of numbered hexagon nodes with level 1 at the bottom, a big Play button, and, once a
// player has cleared level 2,600, a level picker (every node tappable and a number box that jumps to any level).
// Only the nodes near the screen exist, so a phone never holds 2,600 of them.
import { loadLevel } from "./levels.js";
import { makeFace, syncChildren } from "./whoshere.js";

const LEVEL_COUNT = 2600;
const DIFFICULTY_HARD = 2;
const DIFFICULTY_VERY_HARD = 3;

// Sizes are fractions of the play column's width, set in style.css (--row and --pad) and mirrored here for scrolling
const ROW_SHARE = 0.3;
const PAD_SHARE = 0.1;
// How far down the screen the chosen node sits when the path opens or jumps
const REST_SHARE = 0.58;
// Nodes drawn beyond the screen's top and bottom edges, so a fast swipe never shows a gap
const SPARE_ROWS = 2;
// A jump of more than this many levels moves at once instead of gliding
const GLIDE_LEVELS = 12;
// The path winds: a node sits this many hundredths of the column's width left or right of the middle (4-step wave)
const SWING = 17;

const el = {};
const state = {
  progress: null,
  selected: 1,
  rows: new Map(),
  frame: 0,
  playHandler: null,
  watchHandler: null,
  // The friends on each level ({people, watch}, by level number) and the part of the path they are drawn in, by level
  groups: new Map(),
  faceLimit: 3,
  faceRows: new Map(),
};

// The handler called with a level number when the player presses Play
export function onPlay(handler) {
  state.playHandler = handler;
}

// The handler called with a friend's user id when the player presses "Watch" under their face
export function onWatch(handler) {
  state.watchHandler = handler;
}

// While the bot is asked for a level, Play waits so a second press can't ask twice
export function setWaiting(waiting) {
  if (el.play) {
    el.play.disabled = waiting;
  }
}

function swingOf(n) {
  return Math.round(Math.sin((n * Math.PI) / 2)) * SWING;
}

function rowHeight() {
  return el.scroll.clientWidth * ROW_SHARE;
}

function padHeight() {
  return el.scroll.clientWidth * PAD_SHARE;
}

function topOf(n) {
  return padHeight() + (LEVEL_COUNT - n) * rowHeight();
}

function cleared() {
  return Boolean(state.progress && state.progress.cleared);
}

// What a node looks like: done (gold), the chosen one (glowing), or still ahead
function lookOf(n) {
  if (n === state.selected) {
    return "current";
  }
  return cleared() || n < state.progress.level ? "done" : "ahead";
}

function applyLook(node, n) {
  node.dataset.look = lookOf(n);
  node.disabled = !cleared();
  node.setAttribute("aria-current", n === state.selected ? "step" : "false");
}

function applyDifficulty(node, difficulty) {
  node.dataset.hard = difficulty === DIFFICULTY_VERY_HARD ? "very" : difficulty === DIFFICULTY_HARD ? "hard" : "";
}

function makeNode(n) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = "node";
  node.dataset.n = String(n);
  node.dataset.digits = String(String(n).length);
  node.style.setProperty("--i", String(LEVEL_COUNT - n));
  node.style.setProperty("--dx", String(swingOf(n)));
  node.setAttribute("aria-label", `Level ${n}`);
  node.innerHTML =
    '<span class="glow" aria-hidden="true"></span><span class="hex" aria-hidden="true"></span>' +
    `<span class="num">${n}</span>`;
  if (n < LEVEL_COUNT) {
    const link = document.createElement("span");
    link.className = "link";
    link.setAttribute("aria-hidden", "true");
    const across = swingOf(n + 1) - swingOf(n);
    link.style.setProperty("--len", String(Math.hypot(across, ROW_SHARE * 100)));
    link.style.setProperty("--angle", `${Math.atan2(-ROW_SHARE * 100, across)}rad`);
    node.append(link);
  }
  applyLook(node, n);
  node.addEventListener("click", () => select(n));
  // A node's red look comes from its level's pack, which may still be on its way
  loadLevel(n)
    .then((level) => {
      if (state.rows.get(n) === node) {
        applyDifficulty(node, level.d);
      }
    })
    .catch((e) => console.warn("Block Blaster: couldn't read a level's difficulty for the path", e));
  return node;
}

// Create the nodes now on screen (and a few more each side) and drop the ones that left
function drawWindow() {
  state.frame = 0;
  const row = rowHeight();
  const first = Math.floor((el.scroll.scrollTop - padHeight()) / row) - SPARE_ROWS;
  const last = Math.ceil((el.scroll.scrollTop + el.scroll.clientHeight - padHeight()) / row) + SPARE_ROWS;
  const wanted = new Set();
  for (let i = Math.max(first, 0); i <= Math.min(last, LEVEL_COUNT - 1); i++) {
    wanted.add(LEVEL_COUNT - i);
  }
  for (const [n, node] of state.rows) {
    if (!wanted.has(n)) {
      node.remove();
      state.rows.delete(n);
    }
  }
  for (const n of wanted) {
    if (!state.rows.has(n)) {
      const node = makeNode(n);
      state.rows.set(n, node);
      el.track.append(node);
    }
  }
  drawFaces();
}

// ---------- Friends' faces ----------

// One level's faces, made once and updated in place after that: the faces side by side (with "+N" past the limit)
// beside the node, on the side of it with more room, and "Watch <name>" under them for the friend Join followed
function makeFaceRow(n) {
  const wrap = document.createElement("div");
  wrap.className = "node-faces";
  wrap.style.setProperty("--i", String(LEVEL_COUNT - n));
  wrap.style.setProperty("--dx", String(swingOf(n)));
  wrap.dataset.side = swingOf(n) > 0 ? "left" : "right";
  const faces = document.createElement("div");
  faces.className = "faces";
  const row = document.createElement("div");
  row.className = "face-row";
  const watch = document.createElement("button");
  watch.type = "button";
  watch.className = "face-watch";
  watch.addEventListener("click", () => state.watchHandler && state.watchHandler(watch.dataset.id));
  faces.append(row, watch);
  wrap.append(faces);
  return { wrap, row, watch, people: new Map(), more: null };
}

// A face's picture and name only change with the friend's, so it is made again only then
function faceOf(part, friend) {
  let face = part.people.get(friend.id);
  const look = `${friend.avatar}|${friend.name}`;
  if (!face || face.look !== look) {
    face = { node: makeFace(friend, "face"), look };
    part.people.set(friend.id, face);
  }
  face.node.title = friend.name;
  face.node.classList.toggle("away", Boolean(friend.away));
  return face.node;
}

function drawFaceRow(part, group) {
  const { people } = group;
  const over = people.length > state.faceLimit;
  const shown = over ? people.slice(0, state.faceLimit - 1) : people;
  const keep = new Set(shown.map((friend) => friend.id));
  for (const id of part.people.keys()) {
    if (!keep.has(id)) {
      part.people.delete(id);
    }
  }
  const nodes = shown.map((friend) => faceOf(part, friend));
  if (over) {
    part.more = part.more || Object.assign(document.createElement("span"), { className: "face more" });
    const text = `+${people.length - shown.length}`;
    if (part.more.textContent !== text) {
      part.more.textContent = text;
    }
    nodes.push(part.more);
  }
  syncChildren(part.row, nodes);
  const friend = group.watch;
  part.watch.hidden = !friend;
  if (friend) {
    part.watch.dataset.id = friend.id;
    const words = `Watch ${friend.name}`;
    if (part.watch.textContent !== words) {
      part.watch.textContent = words;
    }
  }
}

// Faces for the levels on screen: made when a level's node is, taken away when the node goes or its friends leave
function drawFaces() {
  for (const [n, part] of state.faceRows) {
    if (!state.rows.has(n) || !state.groups.has(n)) {
      part.wrap.remove();
      state.faceRows.delete(n);
    }
  }
  for (const n of state.rows.keys()) {
    const group = state.groups.get(n);
    if (!group) {
      continue;
    }
    if (!state.faceRows.has(n)) {
      const part = makeFaceRow(n);
      state.faceRows.set(n, part);
      el.track.append(part.wrap);
    }
    drawFaceRow(state.faceRows.get(n), group);
  }
}

// The friends on the path: `groups` maps a level number to {people, watch} (watch is the friend to offer "Watch" for,
// or null), and at most `limit` faces show on one level
export function showFaces(groups, limit) {
  state.groups = groups;
  state.faceLimit = limit;
  if (state.progress) {
    drawFaces();
  }
}

function scheduleWindow() {
  if (!state.frame) {
    state.frame = requestAnimationFrame(drawWindow);
  }
}

// Scroll so level n sits at the resting place. `glide` lets a short move animate
function scrollToLevel(n, glide) {
  const middle = topOf(n) + rowHeight() / 2;
  const furthest = el.scroll.scrollHeight - el.scroll.clientHeight;
  const top = Math.max(0, Math.min(middle - el.scroll.clientHeight * REST_SHARE, furthest));
  const calm = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scroll.scrollTo({ top, behavior: glide && calm ? "smooth" : "instant" });
  drawWindow();
}

function paintLooks() {
  for (const [n, node] of state.rows) {
    applyLook(node, n);
  }
  el.jumpBox.value = String(state.selected);
}

function select(n) {
  if (!cleared() || n === state.selected) {
    return;
  }
  const from = state.selected;
  state.selected = n;
  paintLooks();
  if (Math.abs(n - from) > GLIDE_LEVELS) {
    scrollToLevel(n, false);
  }
}

function jump(event) {
  event.preventDefault();
  const n = Number(el.jumpBox.value);
  if (!Number.isInteger(n) || n < 1 || n > LEVEL_COUNT) {
    el.jumpBox.value = String(state.selected);
    return;
  }
  const from = state.selected;
  state.selected = n;
  paintLooks();
  scrollToLevel(n, Math.abs(n - from) <= GLIDE_LEVELS);
}

function press() {
  if (state.playHandler && state.progress) {
    state.playHandler(state.selected);
  }
}

// Show the path for this progress: the player's current level in view and glowing (the picked one, once every level
// is cleared), the picker only for a player who cleared them all
export function showPath(progress) {
  state.progress = progress;
  const picker = cleared();
  state.selected = Math.min(Math.max(progress.level, 1), LEVEL_COUNT);
  el.picker.hidden = !picker;
  el.jumpBox.value = String(state.selected);
  el.track.style.height = `${padHeight() * 2 + LEVEL_COUNT * rowHeight()}px`;
  for (const node of state.rows.values()) {
    node.remove();
  }
  state.rows.clear();
  for (const part of state.faceRows.values()) {
    part.wrap.remove();
  }
  state.faceRows.clear();
  scrollToLevel(state.selected, false);
  paintLooks();
}

function resize() {
  if (!state.progress || el.scroll.clientWidth === 0) {
    return;
  }
  el.track.style.height = `${padHeight() * 2 + LEVEL_COUNT * rowHeight()}px`;
  scrollToLevel(state.selected, false);
}

export function initMap() {
  el.scroll = document.getElementById("path-scroll");
  el.track = document.getElementById("path-track");
  el.picker = document.getElementById("picker");
  el.jumpBox = document.getElementById("jump-box");
  el.scroll.addEventListener("scroll", scheduleWindow, { passive: true });
  document.getElementById("jump").addEventListener("submit", jump);
  el.play = document.getElementById("play-button");
  el.play.addEventListener("click", press);
  new ResizeObserver(resize).observe(el.scroll);
}
