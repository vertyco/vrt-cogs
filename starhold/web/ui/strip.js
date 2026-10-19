// Who's here in Starhold: what the player is doing, for the hub's lists, and the strip of everyone's wave and score
// during a run. main.js runs the game and calls these at the right moments; this file only reads the page's state.
// The strip takes no taps, and each entry is made once per person and changed in place, so a list arriving (up to 4
// times a second) never disturbs anything. Alone, there is no strip: the hub's people button offers Invite.
const KEY = "starhold";
// Names longer than this many characters (as a person sees them) are cut, with an ellipsis as the last one
const NAME_MAX = 12;
const STRIP_MAX = 5;
// How wide an entry is with no name (phones) and with one, and the gap between entries and in the bar, for working out
// how many fit
const ENTRY = 100;
const ENTRY_NAMED = 170;
const ENTRY_GAP = 4;
const MORE = 40;
const BAR_GAP = 6;
// Phones held either way show faces with no names, and shorten big scores
const phone = window.matchMedia("(max-width: 520px), (max-height: 520px)");
// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

// The game's page state, handed over once by main.js
let page = null;
const own = {
  // What the hub was last told, and whether the game's connection has closed for good
  told: null,
  busy: false,
  closed: false,
  // What the strip shows, each entry's parts by person, and the "+N" entry
  key: "",
  rows: new Map(),
  more: null,
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

// ---------- What the player is doing ----------

// The status line everyone in the window sees, its data, and whether leaving now would cost the player a run
function activity() {
  const run = page.run;
  const done = page.finished && page.final;
  if (page.screen === "play" && run && !page.finished) {
    const wave = Math.max(1, run.wave);
    return [`Wave ${wave} · ${run.score.toLocaleString()}`, { state: "playing", wave, score: run.score }, true];
  }
  if ((page.screen === "over" || page.screen === "play") && done) {
    const { score, wave } = page.final;
    return [`Game over · ${score.toLocaleString()}`, { state: "over", wave, score }, false];
  }
  return ["In the menu", null, false];
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
  if (page?.hub && !page.hub.offline && !own.closed) {
    tell(...activity());
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
export function disconnected() {
  if (!page?.hub || page.hub.offline) {
    return;
  }
  own.closed = true;
  tell("Not connected", null, false);
}

export function onPeople() {
  showLive();
}

// ---------- The strip ----------

// The others here with a Starhold score. Their data comes from their own pages, so it is only ever shown
function rivals() {
  return page.hub.people
    .filter((p) => p.game === KEY && !p.you && p.data && Number.isFinite(p.data.score))
    .map((p) => ({
      id: p.id,
      name: p.name,
      avatar: p.avatar,
      score: p.data.score,
      wave: Number.isFinite(p.data.wave) ? p.data.wave : 1,
      away: p.away,
    }));
}

// Phones have no room for six-digit scores beside two others, so 100,000 and up shorten ("123k", "1.2M")
function points(score) {
  if (!phone.matches || score < 100000) {
    return score.toLocaleString();
  }
  if (score < 1000000) {
    return `${Math.floor(score / 1000)}k`;
  }
  return `${Math.floor(score / 100000) / 10}M`;
}

// The room the strip has: its own width under an upright bar, or what the bar's numbers and buttons leave
function stripRoom() {
  if (document.body.classList.contains("tall")) {
    return parseFloat($("strip").style.width) || 0;
  }
  return $("controls").getBoundingClientRect().left - $("stats").getBoundingClientRect().right - 2 * BAR_GAP;
}

// How many people's entries show, out of `count`: as many as fit, keeping room for the "+N" entry when not all do
function stripMax(count) {
  const each = (phone.matches ? ENTRY : ENTRY_NAMED) + ENTRY_GAP;
  const room = stripRoom() + ENTRY_GAP;
  const fit = count * each <= room ? count : Math.floor((room - MORE - ENTRY_GAP) / each);
  return Math.max(1, Math.min(STRIP_MAX, fit));
}

// Everyone here with a score, the player included, best first, while a run is on
export function showLive() {
  if (!page) {
    return;
  }
  const strip = $("strip");
  const playing = page.screen === "play" && Boolean(page.run) && Boolean(page.hub) && !page.hub.offline;
  const others = playing ? rivals() : [];
  if (!others.length) {
    if (!strip.hidden) {
      strip.hidden = true;
    }
    own.key = "";
    own.rows.clear();
    return;
  }
  const wave = Math.max(1, page.run.wave);
  const you = { id: "you", name: "You", avatar: page.hub.player?.avatar || "", wave, score: page.run.score, you: true };
  const rows = [...others, you].sort((a, b) => b.score - a.score || Boolean(b.you) - Boolean(a.you));
  const shown = rows.slice(0, stripMax(rows.length));
  if (!shown.includes(you)) {
    shown[shown.length - 1] = you;
  }
  const more = rows.length - shown.length;
  const key = JSON.stringify([phone.matches, shown.map((r) => [r.id, r.name, r.avatar, r.wave, r.score, r.away]), more]);
  if (key === own.key) {
    return;
  }
  own.key = key;
  drawLive(shown.map(liveRow), more);
}

function drawLive(items, more) {
  const strip = $("strip");
  const keep = new Set(own.rows.keys());
  items.forEach((item) => keep.delete(item.dataset.id));
  keep.forEach((id) => own.rows.delete(id));
  if (more > 0) {
    own.more = own.more || make("li", "more");
    setText(own.more, `+${more}`);
    items.push(own.more);
  }
  const same = items.length === strip.children.length && items.every((item, i) => strip.children[i] === item);
  if (!same) {
    strip.replaceChildren(...items);
  }
  if (strip.hidden) {
    strip.hidden = false;
  }
}

// Writing the same text again would still swap the text out
function setText(node, text) {
  if (node.textContent !== text) {
    node.textContent = text;
  }
}

// One entry, made once per person and updated in place after that. Its picture is only made again when the picture
// or the name changes
function liveRow(row) {
  let entry = own.rows.get(row.id);
  if (!entry) {
    entry = { item: make("li"), name: make("span", "name"), wave: make("span", "wave"), points: make("b", "points") };
    entry.item.dataset.id = row.id;
    entry.item.append(make("span"), entry.name, entry.wave, entry.points);
    own.rows.set(row.id, entry);
  }
  const look = `${row.avatar}|${row.name}`;
  if (entry.look !== look) {
    entry.look = look;
    entry.item.children[0].replaceWith(liveFace(row));
  }
  // Names come from Discord, so they only ever go in as text
  setText(entry.name, row.you ? row.name : cut(row.name));
  setText(entry.wave, `W${row.wave}`);
  setText(entry.points, points(row.score));
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
