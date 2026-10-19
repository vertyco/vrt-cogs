// Playing together: every player has their own story, so the hub is told only what each one is doing. The page
// sends one status line with the area and day, and says when leaving would cost the player (a story open in the world,
// panels and the map included). The hub's people button goes where it covers nothing: in the HUD's gap between the
// hunger and sleep icons and the clock while the world shows, and at the top right where the menus' Armor Games badge
// was everywhere else. On the city map each friend in the window who is in Union City shows as a small face beside the
// section they stand in. The street view never gets a face.
//
// The faces are page elements over the canvas, so they take no presses (pointer-events: none) and a list that arrives
// four times a second changes them in place, only when who is shown has changed.
import { citymap } from "./citymap.js";
import { data } from "./data.js";
import { death } from "./death.js";
import { ending } from "./ending.js";
import { openPause } from "./pause.js";
import { onRoom, room } from "./rooms.js";
import { story } from "./story.js";
import { world } from "./world.js";

const GAME_KEY = "laststand";
const SCREEN_LINES = {
  menu: "Main menu",
  slots: "Main menu",
  mode: "Main menu",
  create: "Making a survivor",
  intro: "Watching the intro",
};
// The button's two places, in stage pixels. In the world it hangs from (470, 4) in the 114 px between the hunger and
// sleep icons (to 392) and the day and time text (from 584). On the other screens its right edge is 8 px inside the
// stage and it is centred on the badge's band (y 40 to 80), in the room the badge took
const WORLD_SPOT = { left: 470, centerY: 19, size: 30, width: 110 };
const MENU_SPOT = { right: 752, centerY: 60, size: 30, width: 180 };
// The credits' BACK TO MENU takes the badge's place, so the button waits in the stage's top left corner over them
const CREDITS_SPOT = { left: 8, centerY: 19, size: 30, width: 110 };
const SPOTS = { world: WORLD_SPOT, menu: MENU_SPOT, credits: CREDITS_SPOT };
// The button's size on the screen, in pixels, and how many times the fit loop narrows it before the faces go
const PEOPLE_MIN = 18;
const PEOPLE_MAX = 44;
const PEOPLE_FIT_TRIES = 4;
// A note needs about this much room under the button to slide out there
const NOTE_ROOM = 60;
// Faces beside a section, a name shown beside a lone face, and the room the map's bars keep, in stage pixels
const FACES_MOST = 3;
const NAME_MOST = 10;
const MAP_BAND = { top: 34, bottom: 30 };
const FACE_GAP = 12;

let page = null;
let hub = null;
// The line last sent, so only changes go out
let reported = null;
let pending = false;
// The faces: { box, rows: Map(section -> { node, look, width }) }
let folk = null;
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function $(id) {
  return document.getElementById(id);
}

// Whole characters, so an emoji or an accented letter is never cut in half
function characters(text) {
  return segmenter ? Array.from(segmenter.segment(String(text ?? "")), (part) => part.segment) : Array.from(String(text ?? ""));
}

export function cutName(name, most = NAME_MOST) {
  const letters = characters(name);
  return letters.length > most ? `${letters.slice(0, most - 1).join("")}...` : letters.join("");
}

// ---------- The status line ----------

// What the player is doing in the world: { text, busy, section, day }, or null while no story is up yet
function worldLine() {
  if (ending.active) {
    return { text: "Watching the ending", busy: false, section: null, day: null };
  }
  const def = room.def;
  if (!story.player || !def) {
    return null;
  }
  const section = data.world.locations[def.loc]?.section ?? null;
  const where = { section, day: world.day };
  if (death.isOpen) {
    return { text: `Dead in ${def.areaName}`, busy: false, ...where };
  }
  if (citymap.isOpen) {
    return { text: "City map", busy: true, ...where };
  }
  const hardcore = story.hardcore ? " · Hardcore" : "";
  return { text: `${def.areaName} · Day ${world.day}${hardcore}`, busy: true, ...where };
}

function screenLine(screen) {
  const text = SCREEN_LINES[screen];
  return text ? { text, busy: false, section: null, day: null } : null;
}

// Tells the hub what the player is doing, when that has changed
export function report(screen = page.screen) {
  const line = screen === "world" ? worldLine() : screenLine(screen);
  if (!line || !hub) {
    return;
  }
  const look = `${line.text}|${line.busy}|${line.section}|${line.day}`;
  if (look === reported) {
    return;
  }
  reported = look;
  hub.status(line.text, { section: line.section, day: line.day });
  hub.busy(line.busy);
}

// ---------- The people button ----------

// Where the button goes now: the HUD's gap while the HUD shows, the credits' corner while they roll, the badge's place
// on every other screen
function spotName() {
  if (ending.creditsShowing) {
    return "credits";
  }
  return page.screen === "world" && !ending.active ? "world" : "menu";
}

// Puts the button at its place on the stage, as big as fits there. Called whenever the stage moves or resizes, the button
// grows or shrinks with the people in the window, or the place changes
export function placePeople() {
  const wrap = $("people");
  const canvas = page?.app?.canvas.getBoundingClientRect();
  if (!canvas?.width) {
    return;
  }
  const scale = canvas.width / page.width;
  const name = spotName();
  page.peopleSpot = name;
  const spot = SPOTS[name];
  const limit = spot.width * scale;
  let size = Math.max(PEOPLE_MIN, Math.min(PEOPLE_MAX, spot.size * scale));
  delete wrap.dataset.compact;
  wrap.style.setProperty("--hub-people-size", `${size}px`);
  let box = wrap.getBoundingClientRect();
  // Faces make the button wider, so it is made smaller until it fits. Its words don't shrink with it, so the next guess
  // follows the two widths measured so far
  let before = null;
  for (let tries = 0; tries < PEOPLE_FIT_TRIES && box.width > limit && size > PEOPLE_MIN; tries += 1) {
    const slope = before ? (before.width - box.width) / (before.size - size) : box.width / size;
    before = { size, width: box.width };
    size = Math.max(PEOPLE_MIN, Math.min(size - 0.5, size - (box.width - limit) / slope));
    wrap.style.setProperty("--hub-people-size", `${size}px`);
    box = wrap.getBoundingClientRect();
  }
  if (box.width > limit) {
    // Still too wide on a very small stage: the faces go and the count stays
    wrap.dataset.compact = "true";
    box = wrap.getBoundingClientRect();
  }
  const left = "left" in spot ? canvas.left + spot.left * scale : canvas.left + spot.right * scale - box.width;
  const top = canvas.top + spot.centerY * scale - box.height / 2;
  wrap.style.left = `${Math.round(left)}px`;
  wrap.style.top = `${Math.round(Math.max(0, top))}px`;
  wrap.dataset.placed = "stage";
  wrap.dataset.note = window.innerHeight - (top + box.height) < NOTE_ROOM ? "up" : "down";
}

// ---------- Pausing when hidden ----------

// A locked phone, another app in front, or Discord's chat taking the keys: the pause menu opens so nobody dies while
// away. Only from the world view, and only when nothing already holds the world (a panel, the map or a dialog does)
function pauseIfRunning() {
  if (page.screen !== "world" || !world.active || world.paused) {
    return false;
  }
  return openPause();
}

function goneAway() {
  if (!pauseIfRunning()) {
    pending = page.screen === "world" && world.active;
  }
}

// A hold that was in the way (a room change fading in) is tried again each step while the window stays away
function retryPause() {
  if (!pending) {
    return;
  }
  if (document.hasFocus() && !document.hidden) {
    pending = false;
  } else if (pauseIfRunning()) {
    pending = false;
  }
}

// ---------- Faces on the city map ----------

// The friends in Union City who stand in a section, by section: [{ id, name, avatar, away }, ...]
function friendsBySection() {
  const sections = new Map();
  for (const person of hub?.people ?? []) {
    const section = person.data?.section;
    if (person.you || person.game !== GAME_KEY || !Number.isInteger(section)) {
      continue;
    }
    const list = sections.get(section) ?? [];
    list.push(person);
    sections.set(section, list);
  }
  return sections;
}

function faceNode(person) {
  const face = document.createElement("span");
  face.className = "map-face";
  face.classList.toggle("away", Boolean(person.away));
  const letter = document.createTextNode(characters(person.name)[0]?.toUpperCase() ?? "");
  if (person.avatar) {
    const img = document.createElement("img");
    img.alt = "";
    img.addEventListener("error", () => img.replaceWith(letter));
    img.src = person.avatar;
    face.append(img);
  } else {
    face.append(letter);
  }
  return face;
}

// A row of up to three faces, "+N" past them, and the name of a lone friend
function buildRow(people) {
  const row = document.createElement("div");
  row.className = "map-folk";
  const shown = people.slice(0, FACES_MOST);
  row.append(...shown.map(faceNode));
  if (people.length > shown.length) {
    const more = document.createElement("span");
    more.className = "map-more";
    more.textContent = `+${people.length - shown.length}`;
    row.append(more);
  }
  if (people.length === 1) {
    const name = document.createElement("span");
    name.className = "map-name";
    name.textContent = cutName(people[0].name);
    row.append(name);
  }
  return row;
}

function folkLook(people) {
  return JSON.stringify([people.length, ...people.slice(0, FACES_MOST).map((p) => [p.id, p.name, p.avatar, p.away])]);
}

function folkBox() {
  if (!folk) {
    const box = document.createElement("div");
    box.id = "map-folk";
    box.hidden = true;
    document.body.append(box);
    folk = { box, rows: new Map() };
  }
  return folk;
}

function dropRows(keep) {
  for (const [section, row] of folk.rows) {
    if (!keep.has(section)) {
      row.node.remove();
      folk.rows.delete(section);
    }
  }
}

// Each row beside its section's marker, or off while the marker is under the map's bars or off the stage. A row that
// would run off the stage's right edge sits to the marker's left
function placeRow(row, point, canvas, scale) {
  const inside =
    point &&
    point.x > 0 &&
    point.x < canvas.width &&
    point.y > MAP_BAND.top * scale &&
    point.y < canvas.height - MAP_BAND.bottom * scale;
  row.node.hidden = !inside;
  if (!inside) {
    return;
  }
  const width = row.node.offsetWidth;
  const gap = FACE_GAP * scale;
  const flip = point.x + gap + width > canvas.width;
  const x = Math.round(canvas.left + (flip ? point.x - gap - width : point.x + gap));
  const y = Math.round(canvas.top + point.y);
  const placed = `translate(${x}px, ${y}px) translateY(-50%)`;
  if (row.node.style.transform !== placed) {
    row.node.style.transform = placed;
  }
}

// Called every step and whenever a list arrives. A row is rebuilt only when who it shows has changed
export function updateFolk() {
  const showing = citymap.isOpen && page.app;
  if (!showing && !folk?.rows.size) {
    return;
  }
  const { box, rows } = folkBox();
  box.hidden = !showing;
  const groups = showing ? friendsBySection() : new Map();
  dropRows(groups);
  if (!showing || !groups.size) {
    return;
  }
  const canvas = page.app.canvas.getBoundingClientRect();
  const scale = canvas.width / page.width;
  box.style.setProperty("--face", `${Math.max(16, Math.round(14 * scale))}px`);
  for (const [section, people] of groups) {
    const look = folkLook(people);
    let row = rows.get(section);
    if (row?.look !== look) {
      row?.node.remove();
      row = { node: buildRow(people), look };
      rows.set(section, row);
      box.append(row.node);
    }
    placeRow(row, citymap.sectionPoint(section), canvas, scale);
  }
}

// ---------- Starting ----------

function step() {
  retryPause();
  report();
  if (spotName() !== page.peopleSpot) {
    placePeople();
  }
  updateFolk();
}

// The hub and the page each arrive on their own: once both are here, what the player is doing goes out and the lists
// start to move the button and the faces
function connect() {
  if (!hub || !page) {
    return;
  }
  reported = null;
  report();
  placePeople();
  hub.onPeople?.(() => {
    placePeople();
    updateFolk();
  });
}

export function bindHub(connected) {
  hub = connected;
  connect();
}

export function initTogether(owner) {
  page = owner;
  page.steppers.push(step);
  onRoom("enter", () => report());
  window.addEventListener("blur", goneAway);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      goneAway();
    }
  });
  connect();
}

// Helpers for page.py checks
export const togetherDebug = {
  // What the hub was last told, where the button is, and the faces on the map
  togetherState() {
    const wrap = $("people");
    const box = wrap.getBoundingClientRect();
    return {
      reported,
      spot: page.peopleSpot,
      button: { x: box.x, y: box.y, width: box.width, height: box.height, placed: wrap.dataset.placed },
      faces: folk
        ? [...folk.rows].map(([section, row]) => ({
            section,
            hidden: row.node.hidden,
            faces: row.node.querySelectorAll(".map-face").length,
            away: row.node.querySelectorAll(".map-face.away").length,
            more: row.node.querySelector(".map-more")?.textContent ?? null,
            name: row.node.querySelector(".map-name")?.textContent ?? null,
          }))
        : [],
    };
  },
};
