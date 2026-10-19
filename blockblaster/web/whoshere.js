// Who's here in Block Blaster: what the player is doing, for the hub's lists; the strip of friends playing beside or
// under the top bar, each a tap away from watching; and the friends' faces on the level path. game.js and play.js call
// these at the right moments; this file only reads the page's state.
// Everyone plays their own level, so the strip shows where each friend is (level and how much of the picture is
// cleared), never a score to beat.
import { cleared as clearedPercent } from "./sim/core.js";
import { failTitle } from "./panels.js";

// The game's key in the hub's people list
const KEY = "blockblaster";
const LEVEL_COUNT = 2600;
const STATES = new Set(["map", "playing", "won", "lost", "watching"]);
// Names are cut at this many characters, with an ellipsis as the last one. The side list has room for more of a name
const NAME_TOP = 7;
const NAME_SIDE = 14;
// A face on the path, and how many show before "+N" (two faces and the count)
const PATH_FACES = 3;
// Room beside the play column for the list: a face and a name, with room for the level and percent under it
const SIDE_MIN = 240;
const SIDE_ROWS = 6;
// The slim strip under the top bar: a row's height, the gap between the bar's buttons and the strip, how far the belt's
// rim rises above the ground box the page measures it by, the room a row takes (face, a short name, level and percent,
// padding) with the gap between rows, and the room held back for "+N"
const TOP_ROW = 24;
const TOP_GAP = 2;
const BELT_RIM = 8;
const TOP_CHIP = 146;
const TOP_SPACE = 6;
const TOP_MORE = 40;
// The gap between the list and the play column's edge, and between the strip and the column's sides
const EDGE = 10;

const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

// The game's page state, and what the hub was last told. `tapped` is whether the level on screen has had a tap (the
// player is mid-round from then on), `levelKey` which level that is
const own = {
  page: null,
  actions: null,
  told: null,
  busy: false,
  closed: false,
  tapped: false,
  levelKey: "",
  calls: 0,
  rows: new Map(),
  more: null,
  look: "",
  place: "none",
  noted: null,
};

function $(id) {
  return document.getElementById(id);
}

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

// Writing the same text again would still swap the text node out
function setText(node, text) {
  if (node.textContent !== text) {
    node.textContent = text;
  }
}

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

function cut(name, most) {
  const letters = characters(name);
  return letters.length > most ? `${letters.slice(0, most - 1).join("")}…` : name;
}

// `page` is game.js's page and `actions.watch(id)` asks to watch a friend
export function initWhoshere(page, actions) {
  Object.assign(own, { page, actions });
  $("invite").addEventListener("click", () => page.hub.openPeople());
  // A note sliding out of the people button covers the strip's right end, so the strip steps aside while it shows
  new MutationObserver(() => {
    const noted = Boolean($("people-slot").querySelector(".hub-note"));
    if (noted !== own.noted) {
      own.noted = noted;
      $("live").classList.toggle("noted", noted);
    }
  }).observe($("people-slot"), { childList: true, subtree: true });
}

// ---------- What the player is doing ----------

// The status line, its data and whether leaving would cost the player a level in play. The level is the one on the
// screen; on the map and while watching it is the player's own current level
function describe(kind, data) {
  const { level, cleared = 0 } = data;
  switch (kind) {
    case "playing":
      return [`Level ${level} · ${cleared}%`, { level, cleared, state: kind }, own.tapped];
    case "won":
      return [`Won level ${level}`, { level, cleared: 100, state: kind }, false];
    case "lost":
      return [`Level ${level} · ${data.reason}`, { level, cleared, state: kind }, false];
    case "watching":
      return [`Watching ${data.name}`, { level, cleared: 0, state: kind }, false];
    default:
      return ["On the map", { level, cleared: 0, state: "map" }, false];
  }
}

// `kind` is "map", "playing", "won", "lost" or "watching". The hub sends whatever it is told, even when nothing changed,
// so only changes go to it. Outside Discord there is nobody to tell, and a closed game has nothing more to say
export function setStatus(kind, data) {
  const { page } = own;
  if (own.closed || !page.hub || page.hub.offline) {
    return;
  }
  const [text, state, busy] = describe(kind, data);
  const look = JSON.stringify([text, state]);
  if (look !== own.told) {
    own.told = look;
    own.calls += 1;
    page.hub.status(text, state);
  }
  if (busy !== own.busy) {
    own.busy = busy;
    page.hub.busy(busy);
  }
}

// The player's own level, once per drawn frame: playing with its percent, or its end
export function frame(sim) {
  const level = sim.level.number;
  if (sim.over === null) {
    setStatus("playing", { level, cleared: clearedPercent(sim) });
  } else if (sim.over.result === "won") {
    setStatus("won", { level });
  } else {
    const reason = failTitle(sim.over.name).toLowerCase().replace(/!$/, "");
    setStatus("lost", { level, cleared: clearedPercent(sim), reason });
  }
}

// A level goes up on screen, fresh or resumed. A level the bot already holds taps for is one the player is in the middle
// of; a new start (another level, or the same one again with a new seed) is not
export function levelShown(levelStart) {
  const key = `${levelStart.n}:${levelStart.seed}`;
  if (key !== own.levelKey) {
    own.levelKey = key;
    own.tapped = false;
  }
  if (levelStart.taps.length > 0) {
    own.tapped = true;
  }
}

// The player's first tap on this level: from now on a friend's Join asks first
export function tapSent() {
  own.tapped = true;
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
export function disconnected() {
  const { page } = own;
  own.closed = true;
  if (page.hub && !page.hub.offline) {
    page.hub.status("Not connected", null);
    if (own.busy) {
      own.busy = false;
      page.hub.busy(false);
    }
  }
}

// The screen changed: the map and the watch view say so, and the strip shows in a level only
export function screenShown(name, watching) {
  const { page } = own;
  if (name === "path" && page.progress) {
    setStatus("map", { level: page.progress.level });
  } else if (name === "watch" && watching && page.progress) {
    setStatus("watching", { level: page.progress.level, name: watching });
  }
  refresh();
}

// ---------- The others here ----------

// What a friend's page says about itself, kept only when it has the right shape: it comes from their own page
function readData(data) {
  if (!data || !STATES.has(data.state)) {
    return null;
  }
  const { level, cleared } = data;
  const levelOk = Number.isInteger(level) && level >= 1 && level <= LEVEL_COUNT;
  const clearedOk = Number.isInteger(cleared) && cleared >= 0 && cleared <= 100;
  if (!levelOk || !clearedOk) {
    return null;
  }
  return { level, cleared, state: data.state };
}

// The others in this game with something to show, in the order they arrived
function friends(people) {
  const found = [];
  for (const person of people) {
    const data = person.game === KEY && !person.you ? readData(person.data) : null;
    if (data) {
      found.push({ id: person.id, name: person.name, avatar: person.avatar, away: person.away, ...data });
    }
  }
  return found;
}

// The picture, or the first letter of the name in a circle when there is none or it can't load
export function makeFace(person, className) {
  const initial = () => make("span", className, characters(person.name)[0]?.toUpperCase() ?? "");
  if (!person.avatar) {
    return initial();
  }
  const picture = make("img", className);
  picture.alt = "";
  picture.addEventListener("error", () => picture.replaceWith(initial()));
  picture.src = person.avatar;
  return picture;
}

// Put `items` in `parent`, moving only what is out of place and removing what is left over, so a node that stays is
// never taken out of the page (a press on it would be lost)
export function syncChildren(parent, items) {
  items.forEach((item, i) => {
    if (parent.children[i] !== item) {
      parent.insertBefore(item, parent.children[i] ?? null);
    }
  });
  while (parent.children.length > items.length) {
    parent.lastElementChild.remove();
  }
}

// The faces on the level path: friends grouped by the level they are on, a group per level, and the friend whose Join
// opened the game when they are playing, so the path can offer "Watch" under their face
export function pathFaces(people) {
  const groups = new Map();
  const follow = own.page.hub.follow;
  for (const friend of friends(people)) {
    if (!groups.has(friend.level)) {
      groups.set(friend.level, { people: [], watch: null });
    }
    const group = groups.get(friend.level);
    group.people.push(friend);
    if (follow && follow.id === friend.id && friend.state === "playing") {
      group.watch = friend;
    }
  }
  own.actions.faces(groups, PATH_FACES);
}

// ---------- The strip ----------

// Where the strip goes: in a column of its own beside the play column when at least SIDE_MIN px are free there, else a
// slim row under the top bar when the belt leaves room for it, else nowhere. Pixels are the screen's, not the column's
function work() {
  const { page } = own;
  const column = $("play").getBoundingClientRect();
  const bar = $("top-layer");
  const top = bar.getBoundingClientRect().bottom - parseFloat(getComputedStyle(bar).paddingBottom) + TOP_GAP;
  if (column.left - 2 * EDGE >= SIDE_MIN) {
    return { place: "side", left: column.left - EDGE - SIDE_MIN, top, width: SIDE_MIN };
  }
  const scene = page.scene;
  if (!scene || !scene.rig.level) {
    return { place: "none" };
  }
  const belt = scene.layout.beltBoxOnScreen().y;
  const picture = scene.layout.pictureBox(scene.rig.level).y;
  if (column.top + Math.min(belt, picture) - BELT_RIM - top < TOP_ROW) {
    return { place: "none" };
  }
  return { place: "top", left: column.left + EDGE, top, width: column.width - 2 * EDGE };
}

// Put the strip's box where it goes. Asked again after every resize and refit of the board
export function placeStrip() {
  const live = $("live");
  const spot = work();
  own.place = spot.place;
  live.dataset.place = spot.place;
  if (spot.place !== "none") {
    live.style.left = `${spot.left}px`;
    live.style.top = `${spot.top}px`;
    live.style.width = `${spot.width}px`;
  }
  placeInvite(spot.place);
  refresh();
}

// Invite stands in the list beside the column. In the slim row under the top bar it would stand over the belt's corner
// and the cats riding past it, so there it moves to the band under the booster buttons, at the column's right end
// (the hub's frame rate counter takes the band's left end)
function placeInvite(place) {
  const invite = $("invite");
  const low = place === "top";
  invite.classList.toggle("low", low);
  invite.style.right = low ? `${window.innerWidth - $("play").getBoundingClientRect().right + EDGE}px` : "";
}

// How many rows the strip shows before "+N"
function rowLimit() {
  if (own.place === "side") {
    return SIDE_ROWS;
  }
  const room = $("live").getBoundingClientRect().width;
  return Math.max(1, Math.floor((room - TOP_MORE) / (TOP_CHIP + TOP_SPACE)));
}

function rowName(person) {
  return cut(person.name, own.place === "side" ? NAME_SIDE : NAME_TOP);
}

// One row, made once per person and updated in place after that. Its picture is only drawn again when the picture or the
// name changes. Pressing it asks to watch that friend
function rowOf(person) {
  let row = own.rows.get(person.id);
  if (!row) {
    const button = make("button", "live-row");
    button.type = "button";
    const face = make("span");
    row = { item: make("li"), button, face, name: make("span", "live-name"), info: make("span", "live-info") };
    row.item.dataset.id = person.id;
    row.button.append(row.face, row.name, row.info);
    row.item.append(row.button);
    row.button.addEventListener("click", () => own.actions.watch(person.id));
    own.rows.set(person.id, row);
  }
  const look = `${person.avatar}|${person.name}`;
  if (row.look !== look) {
    row.look = look;
    row.face.replaceWith(makeFace(person, "live-face"));
    row.face = row.button.firstElementChild;
  }
  // Names come from Discord, so they only ever go in as text
  setText(row.name, rowName(person));
  setText(row.info, `Lv ${person.level} · ${person.cleared}%`);
  row.item.classList.toggle("away", Boolean(person.away));
  row.button.setAttribute("aria-label", `Watch ${person.name}, level ${person.level}, ${person.cleared}% cleared`);
  return row.item;
}

// The strip: the friends playing a level now, or Invite when nobody is. Hidden outside a level, and only redrawn when
// what it shows has changed
export function strip(people) {
  const live = $("live");
  const level = own.page.screen === "level" && own.place !== "none";
  const playing = level ? friends(people).filter((friend) => friend.state === "playing") : [];
  live.hidden = !level;
  $("invite").hidden = !level || playing.length > 0;
  $("live-list").hidden = playing.length === 0;
  if (!level) {
    return;
  }
  const shown = playing.slice(0, rowLimit());
  const more = playing.length - shown.length;
  const look = JSON.stringify([own.place, shown.map((p) => [p.id, p.name, p.avatar, p.level, p.cleared, p.away]), more]);
  if (look === own.look) {
    return;
  }
  own.look = look;
  const keep = new Set(shown.map((person) => person.id));
  for (const id of own.rows.keys()) {
    if (!keep.has(id)) {
      own.rows.delete(id);
    }
  }
  const items = shown.map(rowOf);
  if (more > 0) {
    own.more = own.more || make("li", "live-more");
    setText(own.more, `+${more}`);
    items.push(own.more);
  }
  syncChildren($("live-list"), items);
}

// Both lists, from the hub's people now
export function refresh() {
  if (!own.page.hub) {
    return;
  }
  const people = own.page.hub.people;
  strip(people);
  pathFaces(people);
}

// What checks read through window.blockblaster.whoshere
export const debug = { state: own, friends, work };
