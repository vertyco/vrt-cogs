// Who's here in Boulder Bash: what the player is doing, for the hub's lists; the strip of everyone's scores while a
// game is on; and "You passed Ann!" notes. game.js runs the game and calls these at the right moments; this file only
// reads the game's page state, and draws beside the stage at the screen's own size so names stay readable on a small
// stage.

// The game's key in the hub's people list, and its modes as the bot numbers them and the mode signs name them
const KEY = "boulderbash";
export const ZEN = 0;
const MODE_NAMES = ["Zen", "Normal", "Extreme", "Normal x2", "Extreme x2"];
const PASS_MS = 1600;
// Passing notes this close together share one
const PASS_MERGE_MS = 1000;
const STRIP_MAX = 5;
const STRIP_MAX_SMALL = 3;
// Names longer than this many characters are cut, with an ellipsis as the last one
const NAME_MAX = 12;
// On the 800 x 600 stage: the boards' left and right edges, and where the row under the score ends (End Game is at
// 606)
const BOARDS_LEFT = 60;
const BOARDS_RIGHT = 740;
const ROW_END = 598;
// Gap between the strip or the passing note and the boards or the screen's edge
const GAP = 10;
// Gap above and below the passing note in the band over the boards, where room is short
const NOTE_EDGE = 2;
// Narrower room than this is no place for the passing note
const NOTE_MIN = 60;
// The note's looks, tried in turn where room is short: as it is, smaller, and smaller with long words broken
const NORMAL = { small: false, tight: false };
const SMALL = { small: true, tight: false };
const SMALL_TIGHT = { small: true, tight: true };
// Room beside the boards for the strip's column: a picture, a rank and a few letters of a name
const COLUMN_MIN = 95;
// What the row under the score leaves for the people button beside it, and what one entry of the row needs without
// its score: padding, rank, picture, gaps and three letters of the name with the ellipsis
const BUTTON_ROOM = 120;
const ENTRY_BASE = 96;
const DIGIT_WIDTH = 7.5;
const MORE_WIDTH = 44;
const ENTRY_GAP = 4;
// Phones held either way get a shorter strip
const phone = window.matchMedia("(max-width: 520px), (max-height: 520px)");
// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

// The game's page state (hub, screen, game, boards, scene), handed over once by game.js
let page = null;
const own = {
  // What the hub was last told, and whether the game's connection has closed for good
  told: null,
  busy: false,
  closed: false,
  // Where the strip is: a "column" beside the boards, a "row" under the score, or "tall" on an upright phone. The
  // row's width, for working out how many entries fit in it. The screen's safe edges
  place: "tall",
  rowRoom: 0,
  safe: null,
  // What the strip shows, each entry's parts by person so a change only touches what moved, and "+N"
  stripKey: "",
  liveRows: new Map(),
  liveMore: null,
  // The others with a score the player can still pass, and the passing note on show: its names, when it began, and
  // whether a second pass has already joined it. Names held back while the level's popup leaves no room for the note
  ahead: new Set(),
  passNames: [],
  passAt: -Infinity,
  passExtended: false,
  passTimer: null,
  passWaiting: [],
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

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

function cut(name) {
  const letters = characters(name);
  return letters.length > NAME_MAX ? `${letters.slice(0, NAME_MAX - 1).join("")}…` : name;
}

export function watchPeople(gamePage) {
  page = gamePage;
}

// ---------- Where it all goes ----------

// From game.js's layout. On wide screens `stage` is where the 800 x 600 stage is drawn ({ x, y, scale }), and
// style.css places everything from it. With room beside the boards the strip stands in a column there and the
// passing note in the room on the other side; without it, the strip is a row under the score and the note goes in the
// band above the boards. An upright phone passes no stage
export function placePeople(stage, safe) {
  own.safe = safe;
  if (stage) {
    const { x, y, scale } = stage;
    const root = document.documentElement.style;
    root.setProperty("--stage-x", `${x}px`);
    root.setProperty("--stage-y", `${y}px`);
    root.setProperty("--stage-s", String(scale));
    const left = x + BOARDS_LEFT * scale - GAP - (safe.left + GAP);
    const right = window.innerWidth - safe.right - GAP - (x + BOARDS_RIGHT * scale + GAP);
    const gutter = Math.min(left, right);
    root.setProperty("--gutter", `${gutter}px`);
    own.rowRoom = ROW_END * scale - BUTTON_ROOM - 8 * scale;
    root.setProperty("--row-room", `${own.rowRoom}px`);
    own.place = gutter >= COLUMN_MIN ? "column" : "row";
  } else {
    own.place = "tall";
  }
  document.body.classList.toggle("strip-row", own.place === "row");
  document.body.classList.toggle("strip-column", own.place === "column");
  showLive();
  if (!$("pass").hidden) {
    placeNote($("pass"));
  }
}

// ---------- What the player is doing ----------

// The status line everyone in the window sees, its data, and whether a game is on for them. Zen never scores, so it
// has no score to show or compare
function activity() {
  const game = page.game;
  if (page.screen === "play" && game) {
    if (game.mode === ZEN) {
      return ["Playing Zen", { state: "playing", score: null }, true];
    }
    // Two boards each have their own level
    const level = Math.max(...page.boards.map((board) => board.level));
    const text = `${MODE_NAMES[game.mode]} · level ${level} · ${game.score.toLocaleString()}`;
    return [text, { state: "playing", score: game.score }, true];
  }
  if (page.screen === "over" && game) {
    if (game.mode === ZEN) {
      return ["Finished Zen", { state: "over", score: null }, false];
    }
    return [`Scored ${game.score.toLocaleString()}`, { state: "over", score: game.score }, false];
  }
  return ["Getting ready", { state: "idle", score: null }, false];
}

// The hub passes on whatever it is told, even when nothing changed, so only changes go to it
function tell(text, data, busy) {
  const look = JSON.stringify([text, data]);
  if (look !== own.told) {
    own.told = look;
    page.hub.status(text, data);
  }
  if (busy !== own.busy) {
    own.busy = busy;
    page.hub.busy(busy);
  }
}

// Outside Discord there is nobody to tell, and a closed game has nothing more to say
export function report() {
  if (page.hub && !page.hub.offline && !own.closed) {
    tell(...activity());
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
export function disconnected() {
  own.closed = true;
  tell("Not connected", null, false);
}

export function onPeople() {
  if (page.screen === "play" && page.game) {
    followRivals();
  }
  showLive();
}

// ---------- The strip ----------

// The others here with a Boulder Bash score. Their data comes from their own pages, so it is only ever shown
function rivals() {
  if (!page.hub) {
    return [];
  }
  return page.hub.people
    .filter((p) => p.game === KEY && !p.you && p.data && Number.isFinite(p.data.score))
    .map((p) => ({ id: p.id, name: p.name, avatar: p.avatar, score: p.data.score, state: p.data.state, away: p.away }));
}

// How many entries the strip shows before "+N"
function stripMax(rows) {
  if (own.place === "column") {
    return phone.matches ? STRIP_MAX_SMALL : STRIP_MAX;
  }
  if (own.place === "tall") {
    return STRIP_MAX_SMALL;
  }
  // The row has a set width: as many entries as keep a few letters of every name, with room for "+N" after them
  const digits = Math.max(...rows.map((row) => row.score.toLocaleString().length));
  const entry = ENTRY_BASE + digits * DIGIT_WIDTH;
  const width = (count) => count * (entry + ENTRY_GAP) + (count < rows.length ? MORE_WIDTH : -ENTRY_GAP);
  let count = Math.min(rows.length, STRIP_MAX_SMALL);
  while (count > 1 && width(count) > own.rowRoom) {
    count -= 1;
  }
  return count;
}

// Everyone here with a score, the player included, best first, while a game that scores is on. The player's own score
// comes from this page, so it keeps up with every point; the player always sees their own place, before anyone with
// the same score. It takes no taps, and is only redrawn when what it shows has changed, entry by entry
export function showLive() {
  const strip = $("live");
  const game = page.game;
  const others = page.screen === "play" && game && game.mode !== ZEN ? rivals() : [];
  if (!others.length) {
    strip.hidden = true;
    own.stripKey = "";
    own.liveRows.clear();
    return;
  }
  const you = { id: "you", name: "You", avatar: page.hub.player?.avatar || "", score: game.score, you: true };
  const rows = [...others, you].sort((a, b) => b.score - a.score || Boolean(b.you) - Boolean(a.you));
  const shown = rows.slice(0, stripMax(rows));
  if (!shown.includes(you)) {
    shown[shown.length - 1] = you;
  }
  const ranked = shown.map((row) => [rows.indexOf(row) + 1, row]);
  const more = rows.length - shown.length;
  const key = JSON.stringify([ranked.map(([rank, r]) => [rank, r.id, r.name, r.avatar, r.score, r.away]), more]);
  if (key === own.stripKey) {
    return;
  }
  own.stripKey = key;
  drawLive(ranked.map(([rank, row]) => liveRow(row, rank)), more);
}

function drawLive(items, more) {
  const strip = $("live");
  const keep = new Set(own.liveRows.keys());
  items.forEach((item) => keep.delete(item.dataset.id));
  keep.forEach((id) => own.liveRows.delete(id));
  if (more > 0) {
    own.liveMore = own.liveMore || make("li", "more");
    setText(own.liveMore, `+${more}`);
    items.push(own.liveMore);
  }
  const same = items.length === strip.children.length && items.every((item, i) => strip.children[i] === item);
  if (!same) {
    strip.replaceChildren(...items);
  }
  strip.hidden = false;
}

// Writing the same text again would still swap the text out
function setText(node, text) {
  if (node.textContent !== text) {
    node.textContent = text;
  }
}

// One entry, made once per person and updated in place after that. Its picture is only drawn again when the picture
// or the name changes
function liveRow(row, rank) {
  let entry = own.liveRows.get(row.id);
  if (!entry) {
    entry = { item: make("li"), rank: make("span", "rank"), name: make("span", "name"), points: make("b", "points") };
    entry.item.dataset.id = row.id;
    entry.item.append(entry.rank, make("span"), entry.name, entry.points);
    own.liveRows.set(row.id, entry);
  }
  const look = `${row.avatar}|${row.name}`;
  if (entry.look !== look) {
    entry.look = look;
    entry.item.children[1].replaceWith(liveFace(row));
  }
  setText(entry.rank, String(rank));
  // Names come from Discord, so they only ever go in as text
  setText(entry.name, row.you ? row.name : cut(row.name));
  setText(entry.points, row.score.toLocaleString());
  const kind = row.you ? "mine" : row.away ? "away" : "";
  if (entry.item.className !== kind) {
    entry.item.className = kind;
  }
  return entry.item;
}

// The picture, or the first letter of the name in a circle when there is none or it can't load
function liveFace(row) {
  const initial = () => make("span", "avatar", characters(row.name)[0]?.toUpperCase() ?? "");
  if (!row.avatar) {
    return initial();
  }
  const picture = make("img", "avatar");
  picture.alt = "";
  picture.addEventListener("error", () => picture.replaceWith(initial()));
  picture.src = row.avatar;
  return picture;
}

// ---------- Passing notes ----------

// The others with a score the player can still pass, whether their game is on or over: those seen at or above the
// player's score. One who drops below without the player scoring has started over, and was not passed
function followRivals() {
  const score = page.game.score;
  const others = rivals();
  for (const id of own.ahead) {
    const rival = others.find((r) => r.id === id);
    if (!rival || rival.score < score) {
      own.ahead.delete(id);
    }
  }
  others.filter((r) => r.score >= score).forEach((r) => own.ahead.add(r.id));
}

// A game starts, or is seen again after a reload or a dropped connection. Only those at or above the score now can be
// passed, so coming back never notes a pass that happened while the page was away
export function startPassing() {
  own.ahead.clear();
  own.passWaiting = [];
  followRivals();
}

// "You passed Ann!" when the player's score goes above someone in the strip who was at or above it, with a score above
// 0. Zen doesn't score, so it passes nobody, and a Zen player is never in the strip
export function checkPassed() {
  const game = page.game;
  if (page.screen !== "play" || !game || game.mode === ZEN) {
    return;
  }
  const others = rivals();
  const passed = others.filter((r) => own.ahead.has(r.id) && r.score > 0 && game.score > r.score);
  passed.forEach((r) => own.ahead.delete(r.id));
  others.filter((r) => r.score >= game.score).forEach((r) => own.ahead.add(r.id));
  const names = passed.map((r) => cut(r.name));
  // A note held back by the level's popup shows once it closes
  if (own.passWaiting.length && !page.popupOpen) {
    names.unshift(...own.passWaiting);
    own.passWaiting = [];
  }
  if (names.length) {
    passNote(names);
  }
}

// Shows the note for these names. A pass within a second of the note's start joins it, once
function passNote(names) {
  const now = performance.now();
  if (now - own.passAt < PASS_MERGE_MS && !own.passExtended) {
    own.passNames = [...own.passNames, ...names];
    own.passExtended = true;
  } else {
    own.passNames = names;
    own.passAt = now;
    own.passExtended = false;
  }
  // Each name sits in its own <bdi>, so a name written right to left can't reorder the words around it
  const parts = ["You passed "];
  own.passNames.forEach((name, i) => {
    if (i > 0) {
      parts.push(i === own.passNames.length - 1 ? " and " : ", ");
    }
    parts.push(make("bdi", "", name));
  });
  parts.push("!");
  const note = $("pass");
  note.replaceChildren(...parts);
  note.classList.remove("show");
  note.hidden = false;
  if (!placeNote(note)) {
    note.hidden = true;
    clearTimeout(own.passTimer);
    own.passWaiting.push(...own.passNames);
    own.passNames = [];
    own.passAt = -Infinity;
    return;
  }
  void note.offsetWidth;
  note.classList.add("show");
  clearTimeout(own.passTimer);
  own.passTimer = setTimeout(hidePass, PASS_MS);
}

// Puts the note in its spot. False when there is no room for it until the level's popup closes
function placeNote(note) {
  note.style.left = "";
  note.style.top = "";
  note.style.maxWidth = "";
  note.classList.remove("small", "tight");
  return own.place === "tall" ? placeTallNote(note) : placeWideNote(note);
}

// On a wide screen, the first of these the note fits in: the room right of the boards under End Game, then the band
// above the boards between the score and the people button (above the strip when that is a row under the score),
// each at full size and then smaller, and last the room right of the boards with long words broken. The band stops
// above the people button's foot, where its arrival notes slide out. A small window with no room in any of them gets
// the band anyway, down to the boards, over the strip if it must
function placeWideNote(note) {
  const safe = own.safe;
  const boards = page.scene.boardsBox();
  const button = ($("people").querySelector(".hub-people") || $("people")).getBoundingClientRect();
  const strip = $("live");
  const underStrip = own.place === "row" && !strip.hidden ? strip.getBoundingClientRect().top : boards.top;
  const side = {
    left: boards.right + GAP,
    right: window.innerWidth - safe.right - GAP,
    top: $("end").getBoundingClientRect().bottom + GAP,
    bottom: window.innerHeight - safe.bottom - GAP,
  };
  const band = {
    left: document.querySelector("#hud-top .score").getBoundingClientRect().right + GAP,
    right: button.left - GAP,
    top: safe.top + NOTE_EDGE,
    bottom: Math.min(underStrip, button.bottom, boards.top) - NOTE_EDGE,
    middle: true,
  };
  const tries = [
    [side, NORMAL],
    [band, NORMAL],
    [band, SMALL],
    [side, SMALL],
    [side, SMALL_TIGHT],
  ];
  if (!tries.some(([spot, look]) => fitNote(note, spot, look))) {
    fitNote(note, { ...band, bottom: boards.top - NOTE_EDGE, middle: false }, SMALL_TIGHT, true);
  }
  return true;
}

// Tries the note in a spot with a look: no wider than the spot, and no taller unless it must go there anyway. It sits
// in the spot's middle across, and at the spot's top or, in the band, its middle
function fitNote(note, spot, look, anyway = false) {
  const width = spot.right - spot.left;
  if (width < NOTE_MIN && !anyway) {
    return false;
  }
  note.classList.toggle("small", look.small);
  note.classList.toggle("tight", look.tight);
  note.style.maxWidth = `${width}px`;
  note.style.left = `${spot.left}px`;
  note.style.top = `${spot.top}px`;
  const box = note.getBoundingClientRect();
  const room = spot.bottom - spot.top;
  if (!anyway && (box.height > room || note.scrollWidth > note.clientWidth + 1)) {
    return false;
  }
  note.style.left = `${spot.left + (width - box.width) / 2}px`;
  note.style.top = `${spot.middle ? spot.top + (room - box.height) / 2 : spot.top}px`;
  return true;
}

// On an upright phone the note goes in the sky between the bars at the top (with the strip) and the boards, and
// above the level's popup while that is up. Where the sky is too short, it sits just above the boards. False when the
// popup leaves no room above it, so the note waits for the popup to close
function placeTallNote(note) {
  const above = ["hud-top", "people", "live"].map((id) => $(id)).filter((node) => !node.hidden);
  const top = Math.max(...above.map((node) => node.getBoundingClientRect().bottom)) + GAP;
  const height = note.getBoundingClientRect().height;
  const boards = page.scene.boardsBox().top;
  const floor = $("popup").hidden ? boards : Math.min(boards, $("popup").getBoundingClientRect().top);
  const room = floor - GAP - top;
  if (room < height && floor < boards) {
    return false;
  }
  note.style.top = `${room >= height ? top + (room - height) / 2 : floor - GAP - height}px`;
  return true;
}

export function hidePass() {
  clearTimeout(own.passTimer);
  own.passWaiting = [];
  $("pass").hidden = true;
}
