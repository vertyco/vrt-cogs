// Playing together (spec 5, D17): the Watch list, the versus lobby, and the faces in a battle.
//
// The Watch list and the versus lobby sit on the menu clip's metal frame. Their panel (the dialog's backing, character
// 1037) and buttons (the options screen's, character 845) are the original's own pieces; the rows are words and faces
// in the page, laid over the stage's exact place (place), because a row carries Discord pictures that the art can't.
// The page decides nothing: which battles run, who watches them and which games are open all come from the bot, and a
// press only asks. A list is changed in place, never rebuilt, so a row under a finger keeps its press (a list can
// arrive four times a second).
//
// In a battle the people who watch show as small faces under the flag of the side they watch from, "+N" past four,
// and a versus opponent's name sits under their flag. A solo player with no watchers sees nothing extra.
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const BACKING = 1037;
const BUTTON = 845;
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const EASE = "easeOutSine";
// The panel the rows sit in, and the middle of the row of buttons under it, in stage pixels (the metal frame's inside
// runs about 28 to 772 across and 20 to 400 down)
const PANEL = { x: 76, y: 73, width: 648, height: 258 };
const BUTTONS_Y = 366;
const BUTTONS_APART = 160;
const BUTTON_PADDING = 24;
const PANEL_FADE_SECONDS = 0.6;
// The menu fades its old part out over 0.8 seconds first (swap), and the words come up after it
const PANEL_DELAY_SECONDS = 0.8;
const FACES_MOST = 4;
const NAME_MOST = 14;
const NOT_CONNECTED = "Not connected. Try again in a moment.";
const SIDE_WORDS = { british: "British", german: "German" };
const KIND_WORDS = { campaign: "Campaign", custom: "Custom battle", versus: "Versus" };
const MAP_WORDS = { short: "short", medium: "medium", long: "long" };
const TITLES = { watch: "WATCH", versus: "VERSUS" };

let page = null;
// The screen on show: { kind, menu, parts, buttons, list, unsubscribe } or null
let state = null;
// Ids of people the hub says are away, and whether the faces in a battle need drawing again
let away = new Set();
let facesLook = null;
let facesShown = false;
let subscribed = false;
const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });

// Gives the module the page it works on. Called once by game.js
export function bindPage(owner) {
  page = owner;
  page.onMessage("watchers", ({ id, people }) => {
    if (page.battle?.id === id) {
      page.battle.watchers = people;
    }
  });
  // A friend's Join lands on the versus lobby when their game is open (the main menu is where a page already is)
  page.onMessage("follow", (where) => {
    if (where === "versus" && page.screen !== "battle") {
      page.show("versus");
    }
  });
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

function el(tag, name = "", text = null) {
  const node = document.createElement(tag);
  if (name) {
    node.className = name;
  }
  if (text !== null) {
    node.textContent = text;
  }
  return node;
}

function firstLetter(name) {
  const first = segmenter.segment(String(name ?? ""))[Symbol.iterator]().next();
  return first.done ? "" : first.value.segment;
}

// The player's own id as the bot writes it
function me() {
  return String(page.hub?.player?.id ?? "");
}

// ---------- Where the words sit ----------

// Lays the words' boxes over the stage, and tells them how many screen pixels a stage pixel is. Called whenever the
// stage moves or resizes
export function place() {
  const canvas = page?.app?.canvas.getBoundingClientRect();
  if (!canvas?.width) {
    return;
  }
  for (const id of ["together", "faces"]) {
    const box = document.getElementById(id);
    box.style.left = `${canvas.left}px`;
    box.style.top = `${canvas.top}px`;
    box.style.width = `${canvas.width}px`;
    box.style.height = `${canvas.height}px`;
    box.style.setProperty("--s", String(canvas.width / 800));
  }
}

// ---------- Faces ----------

// A person's picture, or their name's first letter when it can't load. dim shows an away person
function face(person, tag) {
  const node = el(tag, "face");
  const you = person.id === me();
  const name = you ? "You" : person.name;
  node.title = name;
  node.classList.toggle("away", away.has(person.id));
  const letter = document.createTextNode(firstLetter(name).toUpperCase());
  if (person.avatar) {
    const img = el("img");
    img.alt = "";
    img.addEventListener("error", () => img.replaceWith(letter));
    img.src = person.avatar;
    node.append(img);
  } else {
    node.append(letter);
  }
  return node;
}

// Up to FACES_MOST faces and "+N" for the rest
function faceRow(people, tag) {
  const row = people.slice(0, FACES_MOST).map((person) => face(person, tag));
  const more = people.length - row.length;
  if (more > 0) {
    row.push(el("span", "more", `+${more}`));
  }
  return row;
}

// ---------- Rows ----------

// A row of a list: one button, with its parts made once and changed in place afterwards
function makeRow() {
  const row = el("button", "row");
  row.type = "button";
  const parts = {
    who: el("span", "faces"),
    text: el("span", "text"),
    title: el("span", "title"),
    line: el("span", "line"),
    seen: el("span", "faces"),
    act: el("span", "act"),
    looks: {},
  };
  parts.text.append(parts.title, parts.line);
  row.append(parts.who, parts.text, parts.seen, parts.act);
  row.parts = parts;
  row.addEventListener("click", () => {
    row.blur();
    if (!row.waiting) {
      row.press?.();
    }
  });
  return row;
}

function setText(node, text) {
  if (node.textContent !== text) {
    node.textContent = text;
  }
}

// A row's faces are drawn again only when who they are changed
function setFaces(row, name, people) {
  const look = JSON.stringify(people.map((person) => [person.id, person.avatar, away.has(person.id)]));
  if (row.parts.looks[name] === look) {
    return;
  }
  row.parts.looks[name] = look;
  row.parts[name].replaceChildren(...faceRow(people, "span"));
}

function fillRow(row, data) {
  const { parts } = row;
  row.press = data.press ?? null;
  row.waiting = Boolean(data.waiting);
  row.classList.toggle("waiting", row.waiting);
  row.tabIndex = row.waiting ? -1 : 0;
  setText(parts.title, data.title);
  setText(parts.line, data.line);
  setText(parts.act, data.act ?? "");
  setFaces(row, "who", data.who ?? []);
  setFaces(row, "seen", data.seen ?? []);
}

// The list shows exactly these rows in this order. A row already there keeps its button; only what changed is touched
function reconcile(list, rows) {
  const have = new Map([...list.children].map((node) => [node.dataset.key, node]));
  rows.forEach((data, index) => {
    let row = have.get(data.key);
    if (!row) {
      row = makeRow();
      row.dataset.key = data.key;
    }
    have.delete(data.key);
    fillRow(row, data);
    if (list.children[index] !== row) {
      list.insertBefore(row, list.children[index] ?? null);
    }
  });
  for (const gone of have.values()) {
    gone.remove();
  }
}

function name(text) {
  return page.cutName(text, NAME_MOST);
}

function send(message) {
  if (!page.send(message)) {
    page.toast(NOT_CONNECTED);
  }
}

// ---------- What each screen lists ----------

// Every battle in the window: its title, who commands each side (the computer as CPU), and who watches
function watchRows() {
  return (page.lobby?.battles ?? []).map((battle) => {
    const side = (which) => `${name(battle.names[which] ?? "CPU")} (${SIDE_WORDS[which]})`;
    return {
      key: battle.id,
      title: battle.title,
      line: `${KIND_WORDS[battle.kind] ?? battle.kind} · ${side("british")} vs ${side("german")}`,
      who: battle.players ?? [],
      seen: battle.watchers ?? [],
      act: "Watch",
      press: () => send({ watch: battle.id }),
    };
  });
}

function otherSide(side) {
  return side === "british" ? "german" : "british";
}

// The games waiting for a second player: your own first, then the others' for you to take
function versusRows() {
  const games = page.lobby?.versus ?? [];
  const mine = games.filter((game) => game.user === me());
  const others = games.filter((game) => game.user !== me());
  const own = mine.map((game) => ({
    key: game.id,
    title: "Waiting for an opponent",
    line: `You command the ${SIDE_WORDS[game.side]} · ${MAP_WORDS[game.settings.map]} map`,
    who: [{ id: game.user, name: game.name, avatar: game.avatar }],
    waiting: true,
  }));
  const open = others.map((game) => ({
    key: game.id,
    title: name(game.name),
    line: `You would command the ${SIDE_WORDS[otherSide(game.side)]} · ${MAP_WORDS[game.settings.map]} map`,
    who: [{ id: game.user, name: game.name, avatar: game.avatar }],
    act: "Take",
    press: () => send({ takeVersus: game.id }),
  }));
  return [...own, ...open];
}

// No one else is in the window, so asking friends in is the useful thing to do
function alone() {
  return (page.hub?.people ?? []).length <= 1;
}

// Whether the player's own versus game is open: the lobby's buttons and the page's status line read it
export function waiting() {
  return Boolean(page.lobby?.versus?.some((game) => game.user === me()));
}

function noteWords(kind, rows) {
  if (rows.length) {
    return "";
  }
  if (kind === "watch") {
    return "No battles are running right now.";
  }
  return "Nobody has a game open. Open one and a friend can take the other side.";
}

// ---------- The original's buttons ----------

function sizeTo(clip, width, height) {
  const size = clip.getLocalBounds();
  clip.scale.x = width / size.width;
  clip.scale.y = height / size.height;
  clip.position.set(PANEL.x - size.minX * clip.scale.x, PANEL.y - size.minY * clip.scale.y);
}

function addButton(menu, label, press) {
  const button = menu.attach(page.lib.make(BUTTON), `together${label}`);
  const words = button.child("buttonText");
  words.autoSizeCenter();
  words.text = label;
  // The art is made for one short word; a longer label gets a wider plate behind it
  const backing = button.child("backing");
  const plate = backing.getLocalBounds().width;
  backing.scale.x = Math.max(1, (words.box.width + BUTTON_PADDING) / plate);
  button.setHandler("onRollOver", () => sound.play(ROLL_OVER));
  button.setHandler("onRelease", () => {
    sound.play(CLICK);
    press();
  });
  button.y = BUTTONS_Y;
  button.alpha = 0;
  return button;
}

// The buttons that show now, side by side and centred; the rest are hidden
function layout(names) {
  const shown = names.filter((key) => state.buttons[key]);
  for (const [key, button] of Object.entries(state.buttons)) {
    button.visible = shown.includes(key);
  }
  shown.forEach((key, index) => {
    state.buttons[key].x = 400 + (index - (shown.length - 1) / 2) * BUTTONS_APART;
  });
}

function backToMenu() {
  // A game left open would pull the player into a battle from the main menu when someone took it
  if (waiting()) {
    page.send({ cancelVersus: true });
  }
  page.show("main");
}

function buildButtons(menu, kind) {
  const buttons = { back: addButton(menu, "MAIN MENU", backToMenu) };
  buttons.invite = addButton(menu, "INVITE FRIENDS", () => page.hub?.openPeople());
  if (kind === "versus") {
    buttons.open = addButton(menu, "OPEN A GAME", () => page.show("versusSetup"));
    buttons.cancel = addButton(menu, "CANCEL", () => page.send({ cancelVersus: true }));
  }
  return buttons;
}

// ---------- The screens ----------

// Reads who the hub says is away from its current list, so the rows never draw one update behind
function noteAway() {
  const people = page.hub?.people ?? [];
  away = new Set(people.filter((person) => person.away).map((person) => person.id));
}

// Draws the screen again from what the bot last said. Cheap enough to run on every message
function refresh() {
  if (!state) {
    return;
  }
  noteAway();
  const rows = state.kind === "watch" ? watchRows() : versusRows();
  reconcile(state.list, rows);
  const note = document.getElementById("together-note");
  const words = noteWords(state.kind, rows);
  note.hidden = !words;
  setText(note, words);
  const wanted = state.kind === "watch" ? ["back"] : ["back", waiting() ? "cancel" : "open"];
  if (alone() && !rows.length) {
    wanted.push("invite");
  }
  layout(wanted);
  page.report();
}

async function enter(kind) {
  const mine = { kind, menu: null, buttons: {}, list: document.getElementById("together-list"), unsubscribe: null };
  state = mine;
  await page.lib.need([BACKING, BUTTON]);
  const had = menuClip();
  const menu = had ?? (await menus.loadMenu(kind));
  if (state !== mine) {
    return;
  }
  mine.menu = menu;
  if (had) {
    menus.swap(menu, menus.PARTS[page.previousScreen] ?? null, null);
  } else {
    sound.menuMusic();
  }
  const panel = menu.attach(page.lib.make(BACKING), "togetherPanel");
  sizeTo(panel, PANEL.width, PANEL.height);
  mine.panel = panel;
  mine.buttons = buildButtons(menu, kind);
  for (const part of [panel, ...Object.values(mine.buttons)]) {
    part.alpha = 0;
    tweens.alphaTo(part, 100, PANEL_FADE_SECONDS, EASE, PANEL_DELAY_SECONDS);
  }
  document.getElementById("together-title").textContent = TITLES[kind];
  const words = document.getElementById("together");
  place();
  words.hidden = false;
  watchHub();
  mine.unsubscribe = page.hub?.onPeople(refresh) ?? null;
  refresh();
}

function leave() {
  const old = state;
  state = null;
  if (!old) {
    return;
  }
  old.unsubscribe?.();
  document.getElementById("together").hidden = true;
  old.list.replaceChildren();
  for (const part of [old.panel, ...Object.values(old.buttons)]) {
    part?.destroy({ children: true });
  }
}

function receive(owner, data) {
  if (data.lobby) {
    refresh();
  }
}

export const screens = {
  watch: { enter: () => enter("watch"), leave, receive },
  versus: { enter: () => enter("versus"), leave, receive },
};

// ---------- In a battle ----------

// Whether the battle's own field shows, with nothing laid over it that the faces would sit on top of: the loading
// screen, the in-battle menu, the upgrades screen and the results
function fieldShows() {
  const hud = page.field.hud;
  if (!hud?.clip?.visible || hud.clip.child("inGameMenu")) {
    return false;
  }
  const covers = ["loadScreen", "results", "upgradesOverlay"];
  return !page.root.children.some((child) => !child.destroyed && covers.includes(child.label));
}

function watchHub() {
  if (subscribed || !page.hub) {
    return;
  }
  subscribed = true;
  noteAway();
  page.hub.onPeople(noteAway);
}

function sayWhose(person) {
  page.toast(person.id === me() ? "That's you." : `⁨${name(person.name)}⁩ is watching.`, 2500);
}

// The faces of the battle's watchers under the flag of the side it is seen from, and the versus opponent's name under
// theirs. Drawn again only when who is there changed
function drawFaces(battle) {
  const seen = battle.you ?? battle.map.side;
  const people = battle.watchers ?? [];
  const foe = battle.kind === "versus" ? (battle.names?.[otherSide(seen)] ?? null) : null;
  const who = people.map((person) => [person.id, person.avatar, away.has(person.id)]);
  const look = JSON.stringify([battle.id, seen, foe, who]);
  if (look === facesLook) {
    return;
  }
  facesLook = look;
  const groups = Object.fromEntries(
    [...document.querySelectorAll("#faces .group")].map((group) => [group.dataset.side, group]),
  );
  const row = faceRow(people, "button");
  for (const node of row) {
    if (node.tagName === "BUTTON") {
      node.type = "button";
      node.addEventListener("click", () => {
        node.blur();
        sayWhose(people[row.indexOf(node)]);
      });
    }
  }
  groups[seen].replaceChildren(...row);
  groups[otherSide(seen)].replaceChildren(...(foe ? [el("span", "tag", name(foe))] : []));
}

// Once a page tick: the faces show while the battle's field does, and are drawn when something about them changed
export function sync() {
  const battle = page.screen === "battle" ? page.battle : null;
  const show = Boolean(battle) && fieldShows();
  if (show === facesShown) {
    if (show) {
      drawFaces(battle);
    }
    return;
  }
  facesShown = show;
  document.getElementById("faces").hidden = !show;
  if (show) {
    watchHub();
    place();
    facesLook = null;
    drawFaces(battle);
  }
}
