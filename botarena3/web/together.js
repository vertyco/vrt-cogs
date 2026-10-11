// The screens for playing together, new to the port and built from the original's own pieces: the shop's backdrop,
// its scrolling lists and their rows, its wide buttons and its info monitor, the arena list's map previews, and the
// pixel font. PvP lists the open fights in this Activity window and opens one in an arena and a weight class. Watch
// lists the battles running in the window. The leaderboard shows the bot's ranking. The page decides nothing: who can
// open or join a fight, which battles run and the ranking all come from the bot. The check before a fight opens only
// mirrors the career view's problems and weight, as the shop's START does, to show the original's error panel.
import { Label, setMatrix } from "./flash.js";
import { cantFight } from "./shop.js";
import { Container, Rectangle, Sprite } from "./vendor/pixi.min.mjs";

// The original's characters these screens build
const BACKDROP = 363;
const LIST = 371;
const ROW_PICTURE = 520;
const MAP = 729;
const WIDE_BUTTON = 378;
const INFO_MONITOR = 477;
// The shop's backdrop, stretched over the stage as root frame 4 places it
const BACKDROP_MATRIX = [25.1852, 0, 0, 40.7843, 320, 239];
// The shop's three columns: lists 200 wide at x 10, 220 and 430 with their headings over them, wide buttons under
// them, and the info monitor in the bottom left. Watch and the leaderboard have one list, in the middle column and
// halfway down the stage
const COLUMNS = [10, 220, 430];
const LIST_TOP = 25;
const ONE_LIST_TOP = 125;
const HEADING_ABOVE = 16.5;
const BUTTON_X = 99.3;
const BUTTON_BELOW = [233.5, 258.5];
const MONITOR_AT = [9, 300];
// The headings are the shop's ("SHOP", "INVENTORY", "BOTS"): the pixel font at 16, white
const FONT = '"04b_03b", monospace';
const HEADING_SIZE = 16;
const HEADING_BASELINE = 12;
const WHITE = "#ffffff";
// A list row is 40 pixels tall and pictured 180 wide; a list shows 220 pixels of rows, and its scroller runs from 15
// to 205 down the list's side, easing a fifth of the way to its place each frame
const ROW_HEIGHT = 40;
const ROW_WIDTH = 180;
const LIST_SHOWS = 220;
const SCROLL_X = 190;
const SCROLL_TOP = 15;
const SCROLL_BOTTOM = 205;
const SCROLL_RANGE = 190;
const SCROLL_EASE = 5;
// A row's white highlight: picked, or under the pointer. Greyed buttons are half see-through
const PICKED = 0.5;
const HOVERED = 0.2;
const GREYED = 0.5;
// The arena list's map preview, small enough for a row's picture, flattened as the arena list shows it
const MAP_SCALE = 0.05;
// A row with no picture starts its words where the picture would be
const NO_PICTURE_SHIFT = 35;
// The menu's music carries on into these screens, and starts again on the way back from a battle
const MUSIC = "dnb";
const ARENAS = 3;
// The arena list's own words for a team too heavy for a battle (its "bad" page)
const TOO_HEAVY =
  "SORRY, YOUR TEAM OF ROBOTS WEIGH TOO MUCH TO ENTER THIS BATTLE.\r\r" +
  "HINT: RETURN TO THE SHOP SCREEN AND DISABLE SOME OF YOUR BOTS.";
const NO_LIMIT = "NO LIMIT";
const COMPUTER = "COMPUTER";

// The screen while it shows, or null
let state = null;

function upper(name) {
  return String(name ?? "").toUpperCase();
}

function effect(name) {
  state.page.sound.effect(name, "misc");
}

// The player's own Discord id, to tell their own fight and leaderboard row from others'
function me(page) {
  return page.hub?.player?.id ?? null;
}

// ---------- Showing and leaving ----------

// The shop's backdrop, the menu's music, and the fader clearing, as the shop does
function begin(page) {
  // erred: the info monitor shows an error. yours: the bot lists a fight of yours
  state = { page, parts: [], lists: [], pictureSize: pictureSize(page), erred: false, yours: false };
  page.fader.gotoAndPlay("fadein");
  if (page.sound.wanted !== MUSIC) {
    page.sound.fadeIn(2);
    page.sound.music(MUSIC);
  }
  setMatrix(place(page.lib.make(BACKDROP)), BACKDROP_MATRIX);
}

function leave() {
  delete document.body.dataset.fights;
  delete document.body.dataset.monitor;
  if (!state) {
    return;
  }
  for (const list of state.lists) {
    clearRows(list);
  }
  for (const part of state.parts) {
    part.destroy({ children: true });
  }
  state = null;
}

// The rows' pictures are drawn again when the window changes size, so they stay sharp
function step() {
  if (!state) {
    return;
  }
  const size = pictureSize(state.page);
  if (size !== state.pictureSize) {
    state.pictureSize = size;
    redrawPictures();
  }
}

// A part on the stage, attached to the root over its empty frame and gone when the screen goes
function place(node, name = null, x = 0, y = 0) {
  state.page.root.attach(node, name);
  node.position.set(x, y);
  state.parts.push(node);
  return node;
}

// ---------- Buttons and the info monitor ----------

function addButton(name, words, x, y, action) {
  const button = place(state.page.lib.make(WIDE_BUTTON), name, x, y);
  button.set("displaytext", words);
  button.setHandler("onPress", () => state && button.vars.ena && action());
  enable(button, true);
  return button;
}

// The shop's enablebutton and voidbutton: a greyed button has no hand cursor and does nothing
function enable(button, on) {
  button.vars.ena = on;
  button.alpha = on ? 1 : GREYED;
  button.useHandCursor = on;
}

// A wide button under a column's list: the first or second row of buttons
function buttonUnder(column, top, row, name, words, action) {
  return addButton(name, words, COLUMNS[column] + BUTTON_X, top + BUTTON_BELOW[row], action);
}

// The original's error page on the info monitor, as the shop shows it when the team can't go
function showError(text) {
  const screen = state.screen;
  screen.gotoAndStop(1);
  screen.gotoAndStop("error");
  state.page.flashMonitor(screen);
  screen.set("txt_displaytext", text);
  document.body.dataset.monitor = "error";
  state.erred = true;
  effect("cons");
}

// The monitor's first page, the original's welcome
function showWelcome() {
  state.screen.gotoAndStop(1);
  state.page.flashMonitor(state.screen);
  delete document.body.dataset.monitor;
  state.erred = false;
}

// ---------- The shop's lists ----------

// One of the shop's lists with its heading. pressed(row) runs on a press of a row; a list that picks keeps the
// pressed row lit until it is pressed again, as the shop's lists do
function addList(name, column, top, heading, { picks = false, pressed = () => {} } = {}) {
  const { lib } = state.page;
  const x = COLUMNS[column];
  const words = new Label([[heading, FONT, false, HEADING_SIZE, WHITE, 0, HEADING_BASELINE]]);
  place(words, null, x + 2, top - HEADING_ABOVE);
  const clip = place(lib.make(LIST), name, x, top);
  const list = { clip, hold: clip.child("itemhold"), scroller: clip.child("scroller"), picks, pressed };
  Object.assign(list, { items: [], pictures: [], rows: [], key: null, picked: null, scrollpos: 0 });
  state.lists.push(list);
  setUpScroller(list);
  return list;
}

// rows: each row's title, details line, color (a frame of the original's row tints), arena map if any, and what a
// press on it asks for. The list is drawn again only when it changed
function showRows(list, rows) {
  const key = JSON.stringify(rows);
  if (key === list.key) {
    return;
  }
  list.key = key;
  clearRows(list);
  list.rows = rows;
  list.picked = null;
  // The list stays where it was scrolled, as far as its new length allows, so rows don't move under the player's
  // finger when the list changes
  list.scrollpos = Math.min(0, Math.max(list.scrollpos, -scrollRoom(list)));
  rows.forEach((row, index) => list.items.push(addRow(list, row, index)));
  setUpScroller(list);
}

function clearRows(list) {
  // A row's picture loses its texture as the row goes, so the textures are let go first
  for (const picture of list.pictures) {
    picture.texture.destroy(true);
  }
  for (const item of list.items) {
    item.destroy({ children: true });
  }
  list.items = [];
  list.pictures = [];
}

function addRow(list, row, index) {
  const item = list.hold.attach(state.page.lib.makeExported("listitem"), `row${index}`);
  // The row's first frame: its second is the shop's robot rows', with a name field of its own
  item.gotoAndStop(1);
  item.vars.ypos = index * ROW_HEIGHT;
  item.set("itemtitle", row.title);
  item.set("itemdetails", row.details);
  const picture = drawRow(row);
  list.pictures.push(picture);
  item.child("bmphold").addChild(picture);
  item.setHandler("onPress", () => state && pressRow(list, index));
  item.onEnterFrame = () => {
    item.y = item.vars.ypos + list.scrollpos;
    const pointer = state.page.lib.pointer;
    const over = item.child("hitarea").getBounds().containsPoint(pointer.x, pointer.y);
    item.child("white").alpha = list.picked === index ? PICKED : over ? HOVERED : 0;
  };
  item.onEnterFrame();
  return item;
}

function pressRow(list, index) {
  effect("cons");
  if (list.picks) {
    list.picked = list.picked === index ? null : index;
  }
  list.pressed(list.rows[index]);
}

// How far the list's rows can scroll up
function scrollRoom(list) {
  return Math.max(0, list.rows.length * ROW_HEIGHT - LIST_SHOWS);
}

// The scroller sits where the list is scrolled to. A drag carries on over a list that changes, following its new
// length
function setUpScroller(list) {
  const scroller = list.scroller;
  const most = scrollRoom(list);
  const scrolls = most > 0;
  scroller.alpha = scrolls ? 1 : GREYED;
  scroller.useHandCursor = scrolls;
  scroller.y = SCROLL_TOP + (scrolls ? (-list.scrollpos * SCROLL_RANGE) / most : 0);
  if (!scrolls) {
    scroller.stopDrag();
    scroller.onEnterFrame = null;
    scroller.setHandler("onPress", () => {});
    scroller.setHandler("onRelease", () => {});
    scroller.setHandler("onReleaseOutside", () => {});
    return;
  }
  scroller.setHandler("onPress", () => {
    scroller.startDrag(false, [SCROLL_X, SCROLL_TOP, SCROLL_X, SCROLL_BOTTOM]);
    scroller.onEnterFrame = () => {
      const wanted = (-(scroller.y - SCROLL_TOP) * scrollRoom(list)) / SCROLL_RANGE;
      list.scrollpos += (wanted - list.scrollpos) / SCROLL_EASE;
    };
  });
  scroller.setHandler("onRelease", () => scroller.stopDrag());
  scroller.setHandler("onReleaseOutside", () => scroller.stopDrag());
}

// ---------- Row pictures ----------

// A row's picture, drawn once from the original's row clip as the shop draws its rows. Names longer than the row's
// fields are drawn smaller to fit
function drawRow(row) {
  const { lib, app } = state.page;
  const render = lib.make(ROW_PICTURE);
  render.set("itemtitle", row.title);
  render.set("itemdetails", row.details);
  render.child("tint").gotoAndStop(row.tint);
  const texts = render.child("texts");
  for (const depth of [1, 2]) {
    texts.at(depth)?.fit();
  }
  const disp = render.child("disp");
  if (row.map) {
    disp.child("item").visible = false;
    disp.attach(mapPreview(lib, row.map));
  } else {
    disp.visible = false;
    texts.x -= NO_PICTURE_SHIFT;
  }
  const scale = lib.filterScale;
  const holder = new Container();
  render.scale.set(scale);
  holder.addChild(render);
  const frame = new Rectangle(0, 0, ROW_WIDTH * scale, ROW_HEIGHT * scale);
  const texture = app.renderer.generateTexture({ target: holder, frame, resolution: app.renderer.resolution });
  holder.destroy({ children: true });
  const picture = new Sprite(texture);
  picture.label = "picture";
  picture.scale.set(1 / scale);
  picture.roundPixels = true;
  picture.eventMode = "none";
  return picture;
}

// The arena list's map preview (its floor and its walls) on one of the 3 arena backgrounds
function mapPreview(lib, background) {
  const map = lib.make(MAP);
  for (const layer of ["bg", "ob"]) {
    map.child(layer).child("graphic").gotoAndStop(background);
  }
  // The walls' stacked shadows give them height at the arena list's size; this small they would cover the floor
  map.child("ob").filters = null;
  map.scale.set(MAP_SCALE, MAP_SCALE / 2);
  return map;
}

// The screen pixels per stage pixel the row pictures are drawn at
function pictureSize(page) {
  return page.lib.filterScale * page.app.renderer.resolution;
}

function redrawPictures() {
  for (const list of state.lists) {
    list.pictures.forEach((old, index) => {
      const picture = drawRow(list.rows[index]);
      old.parent.addChild(picture);
      const texture = old.texture;
      old.destroy();
      texture.destroy(true);
      list.pictures[index] = picture;
    });
  }
}

// ---------- PvP ----------

function enterPvp(page) {
  begin(page);
  const fights = addList("fightlist", 0, LIST_TOP, "OPEN FIGHTS", { pressed: (row) => page.send(row.asks) });
  const picked = () => enable(state.open, state.arenas.picked !== null && state.weights.picked !== null);
  state.arenas = addList("arenalist", 1, LIST_TOP, "ARENA", { picks: true, pressed: picked });
  state.weights = addList("weightlist", 2, LIST_TOP, "WEIGHT CLASS", { picks: true, pressed: picked });
  state.fights = fights;
  buttonUnder(0, LIST_TOP, 0, "boardbutton", "LEADERBOARD", () => page.go("board", { keepSound: true }));
  buttonUnder(0, LIST_TOP, 1, "backbutton", "BACK", () => page.go("menu", { keepSound: true }));
  // OPEN FIGHT sits under the arena and weight lists, and works once both are picked
  const between = (COLUMNS[1] + COLUMNS[2]) / 2 + BUTTON_X;
  state.open = addButton("openfight", "OPEN FIGHT", between, LIST_TOP + BUTTON_BELOW[0], () => openFight(page));
  enable(state.open, false);
  state.screen = place(page.lib.make(INFO_MONITOR), "infomon", ...MONITOR_AT).child("screen");
  page.flashMonitor(state.screen);
  const arenas = Array.from({ length: ARENAS }, (_, index) => index + 1);
  showRows(state.arenas, arenas.map((n) => ({ title: `ARENA ${n}`, details: "", tint: "blue", map: n })));
  showClasses(page);
  showFights(page);
}

// No limit and the 6 weight classes: each class's name and the most its team may weigh. No limit comes first, so the
// fight anyone can join needs no scrolling
function classes(page) {
  return [[null, null], ...(page.data?.weight_classes ?? [])];
}

function showClasses(page) {
  const rows = classes(page).map(([name, most]) => ({
    title: name ?? NO_LIMIT,
    details: most === null ? "" : `WEIGHT LIMIT: ${most}`,
    tint: "purple",
  }));
  showRows(state.weights, rows);
}

// The window's open fights: the opener's name, the arena's map, and the weight class. A press on someone else's
// asks to join it; your own says CANCEL, and a press on it cancels it
function showFights(page) {
  const fights = page.lobby?.fights ?? [];
  const rows = fights.map((fight) => {
    const yours = fight.user === me(page);
    return {
      title: upper(fight.name),
      details: yours ? "CANCEL" : (fight.weight ?? NO_LIMIT),
      tint: yours ? "orange" : "green",
      map: fight.background,
      asks: yours ? { cancel: true } : { join: fight.id },
    };
  });
  showRows(state.fights, rows);
  document.body.dataset.fights = String(fights.length);
  // Your fight newly listed means the bot opened it, so an error from an earlier try no longer stands
  const yours = fights.some((fight) => fight.user === me(page));
  if (yours && !state.yours && state.erred) {
    showWelcome();
  }
  state.yours = yours;
}

// The original's error panel when the team can't go, as the shop's START shows it; otherwise the bot is asked, and
// it checks everything again
function openFight(page) {
  const [weight, most] = classes(page)[state.weights.picked];
  const view = page.career;
  if (view?.problems.length) {
    showError(cantFight(view.problems));
    return;
  }
  if (view && most !== null && view.weight > most) {
    showError(TOO_HEAVY);
    return;
  }
  page.send({ open: [state.arenas.picked + 1, weight] });
}

function receivePvp(page, data) {
  if (!state) {
    return;
  }
  if (data.lobby) {
    showFights(page);
  }
  if (data.data) {
    showClasses(page);
  }
}

// ---------- Watch ----------

function enterWatch(page) {
  begin(page);
  // The bot's answer is the whole battle, which takes the page to the battle screen to watch
  state.battles = addList("watchlist", 1, ONE_LIST_TOP, "BATTLES", { pressed: (row) => page.send(row.asks) });
  buttonUnder(1, ONE_LIST_TOP, 0, "backbutton", "BACK", () => page.go("menu", { keepSound: true }));
  showBattles(page);
}

// The window's battles: each one's arena or challenge (or PVP), and who fights it, the computer as COMPUTER
function showBattles(page) {
  const battles = page.lobby?.battles ?? [];
  const rows = battles.map((battle) => ({
    title: upper(battle.title),
    details: battle.names.map((name) => upper(name ?? COMPUTER)).join(" VS "),
    tint: "green",
    asks: { watch: battle.id },
  }));
  showRows(state.battles, rows);
}

function receiveWatch(page, data) {
  if (state && data.lobby) {
    showBattles(page);
  }
}

// ---------- The leaderboard ----------

function enterBoard(page) {
  begin(page);
  const list = addList("boardlist", 1, ONE_LIST_TOP, "LEADERBOARD");
  buttonUnder(1, ONE_LIST_TOP, 0, "backbutton", "BACK", () => page.go("pvp", { keepSound: true }));
  showBoard(page, list);
}

// The bot's top ten, and your own row under them when you are further down
async function showBoard(page, list) {
  const asked = state;
  let board;
  try {
    board = await page.hub.api("leaderboard");
  } catch (e) {
    console.error("Bot Arena 3: couldn't get the leaderboard", e);
    if (state === asked) {
      page.toast(e.message);
    }
    return;
  }
  if (state !== asked) {
    return;
  }
  const { top, you } = board;
  const rows = you && !top.some((entry) => entry.id === you.id) ? [...top, you] : top;
  showRows(
    list,
    rows.map((entry) => ({
      title: `${entry.rank}. ${upper(entry.name)}`,
      details: `WON ${entry.wins}, LOST ${entry.losses}, DREW ${entry.draws}`,
      tint: entry.id === me(page) ? "orange" : "green",
    })),
  );
}

// The parts these screens build, on the root's empty frame
const art = [BACKDROP, LIST, ROW_PICTURE, MAP, WIDE_BUTTON, INFO_MONITOR];

export const pvp = { frame: "blank", art, enter: enterPvp, leave, receive: receivePvp, step };
export const watch = { frame: "blank", art, enter: enterWatch, leave, receive: receiveWatch, step };
export const board = { frame: "blank", art, enter: enterBoard, leave, step };
